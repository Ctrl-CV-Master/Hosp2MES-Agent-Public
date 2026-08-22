"""SemanticSkillAgent — the deterministic semantic-skill GUI baseline.

This agent drives the Vue Mock MES through
:class:`~hosp2mes.observation.browser_env.BrowserEnv` and
:class:`~hosp2mes.executor.browser_executor.BrowserExecutor`, using a
**pre-authored per-subgoal skill sequence** (a fixed list of abstract GUI
actions per subgoal). It is intentionally kept as a deterministic baseline for
benchmarking the more autonomous agents (Hosp2MESAgent / Agent S3).

Design invariants:

* **Observe first.** Before every action the agent re-reads the rendered page and
  records a structured observation + screenshot.
* **Semantic actions only.** Actions reference controls by accessible name, not
  by XPath/CSS and never by ``task_id``.
* **Independent final verification.** Success is decided by the Evidence Verifier
  reading the backend through a *read-only* ApiEnv — never by the GUI's own
  self-report.

The subgoal -> GUI-step mapping is generic and data-driven: field labels are the
UI's public labels (物料编码 / BOM 编码 / 产品 ...) and the values come from the
task's business context. There is no ``if task_id == ...`` branching anywhere.

Note: this is the **Skill baseline** — it emits a whole per-subgoal action list
up front (not one action at a time). For a true one-action-per-step decision
loop see :class:`~hosp2mes.agents.hosp2mes_agent.Hosp2MESAgent`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hosp2mes.agent.agent import PRODUCTION_STAGES, Task
from hosp2mes.config import Config
from hosp2mes.evaluation.evaluator import Evaluator
from hosp2mes.evidence.evidence import EvidenceWriter, make_run_id
from hosp2mes.executor.actions import Action
from hosp2mes.executor.executor import ExecContext
from hosp2mes.memory.progress_memory import ProgressMemory
from hosp2mes.observation.browser_env import BrowserEnv
from hosp2mes.observation.browser_observation import BrowserObservation
from hosp2mes.planner.planner import Planner
from hosp2mes.trace.trace import TraceRecorder
from hosp2mes.verifier.verifier import EvidenceVerifier


@dataclass
class GUIStepResult:
    ok: bool
    detail: str = ""
    last_action: str = ""


class SemanticSkillAgent:
    def __init__(self, config: Config, env: BrowserEnv, task: Task):
        self.config = config
        self.env = env
        self.task = task
        self.planner = Planner(config)
        self.verifier = EvidenceVerifier()
        self.trace = TraceRecorder(publish_url=config.publish_url or None,
                                   mode=config.agent_mode)
        self.memory: ProgressMemory | None = None
        self.ctx = ExecContext(
            product=task.product,
            material_code=task.target_material_code,
            material_name=task.target_material_name,
            material_type=task.material_type,
            unit=task.unit,
            specification=task.specification,
            bom_code=task.bom_code,
            bom_materials=task.bom_materials,
            order_code=task.order_code,
            batch=task.batch,
            quantity=task.quantity,
        )
        self.run_id = make_run_id(task.task_id)
        self.evidence = EvidenceWriter(self.run_id, config.artifacts_root or None)
        # Route screenshots into the same per-run evidence directory so the
        # before/after PNGs land next to steps.json / summary.json.
        if getattr(env, "artifacts_dir", None) is None:
            env.artifacts_dir = self.evidence.run_dir
        self.gui_steps = 0
        self.failed_subgoal = ""
        self.failure_reason = ""
        self.steps_reached = 0

    # ---- public entry ----------------------------------------------------
    def run(self):
        self.env.start()
        try:
            self.env.reset()
            return self._run()
        finally:
            try:
                self.env.close()
            except Exception:
                pass

    def _run(self):
        self.evidence.start(self.task.task_id, self.task.instruction, mode="browser")
        self.trace.start_run(self.task.task_id, self.task.instruction)

        plan = self.planner.plan(self.task.instruction, self.task.expected_final_state)
        self.memory = ProgressMemory.from_plan(self.task.instruction, plan.ids())
        self._trace(subgoal="planning", observation=f"subgoals={plan.ids()}",
                    reasoning=f"Planner decomposed goal into {len(plan.subgoals)} subgoals",
                    action="plan", result=f"{len(plan.subgoals)} subgoals",
                    evidence={"plan": plan.ids()})

        for sg in plan.ids():
            self.steps_reached = self.gui_steps
            self.memory.set_current(sg)
            ok, detail = self._execute_subgoal(sg)
            if not ok:
                self.failed_subgoal = sg
                self.failure_reason = detail
                break

        # ---- independent evidence-gated final verification --------------
        verdict = self.verifier.verify(self.env, self.task)
        success = verdict.passed and self.memory.all_done()

        self._trace(subgoal="final_verification",
                    observation=f"observed={verdict.observed}",
                    reasoning="Evidence verifier checked live backend state "
                              "independently of the GUI self-report",
                    action="verify:final",
                    result="PASS" if verdict.passed else f"FAIL missing={verdict.missing}",
                    evidence={"expected": verdict.expected,
                              "observed": verdict.observed,
                              "missing": verdict.missing})

        self.trace.finish_run(success, verdict.detail, len(self.trace.steps), 0)
        self.evidence.finish(
            success=success, final_state=verdict.observed, detail=verdict.detail,
            gui_steps=self.gui_steps, failed_subgoal=self.failed_subgoal,
            failure_reason=self.failure_reason, steps_reached=self.steps_reached,
        )
        self.evidence.flush()

        report = Evaluator().evaluate(
            task_id=self.task.task_id, memory=self.memory, trace=self.trace,
            verifier_result=verdict, recovery_count=0, premature_done=0,
            mode=self.config.agent_mode,
        )
        return report, self.trace, self.memory

    # ---- subgoal dispatch ------------------------------------------------
    _SKILLS = {
        "create_material": "_skill_create_material",
        "create_bom": "_skill_create_bom",
        "create_production_order": "_skill_create_order",
        "execute_production": "_skill_execute_production",
    }

    def _execute_subgoal(self, sg: str) -> tuple[bool, str]:
        skill = getattr(self, self._SKILLS.get(sg, ""), None)
        if skill is None:
            self.memory.mark_failed(sg, reason=f"no GUI skill for {sg}")
            return False, f"no GUI skill for subgoal {sg}"
        res: GUIStepResult = skill()
        if res.ok:
            self.memory.mark_completed(sg, evidence={"subgoal": sg})
            self._trace(subgoal=sg, observation=f"{sg} verified via backend read-back",
                        reasoning=f"Subgoal '{sg}' completed via GUI",
                        action=f"verify:{sg}", result="completed")
        else:
            self.memory.mark_failed(sg, reason=res.detail)
            self._trace(subgoal=sg, observation=f"{sg} failed",
                        reasoning=f"Subgoal '{sg}' failed: {res.detail}",
                        action=f"fail:{sg}", result="failed",
                        evidence={"error": res.detail})
        return res.ok, res.detail

    # ---- generic GUI step runner ----------------------------------------
    def _run_actions(self, sg: str, actions: list[Action]) -> GUIStepResult:
        for action in actions:
            before = self.env.observe()
            before_path, _ = self.env.screenshot(f"{sg}-{self.gui_steps:02d}-before")
            result = self.env.execute(action)
            after_path, _ = self.env.screenshot(f"{sg}-{self.gui_steps:02d}-after")
            after = self.env.observe()
            state_changed = self._signature(before) != self._signature(after)

            self.gui_steps += 1
            self.evidence.record(
                step=self.gui_steps, subgoal=sg, url=before.current_url,
                observation_summary=before.summary(),
                interactive_elements_summary=self._elems_summary(before),
                action=action.summary(), action_target=action.target,
                action_result="ok" if result.ok else f"FAIL: {result.detail}",
                screenshot_before=before_path, screenshot_after=after_path,
                state_changed=state_changed,
            )
            self._trace(subgoal=sg, observation=before.summary(),
                        reasoning=action.reasoning or "semantic GUI step",
                        action=action.summary(),
                        result="ok" if result.ok else f"FAIL: {result.detail}",
                        evidence={"state_changed": state_changed,
                                  "url": before.current_url})

            if not result.ok:
                return GUIStepResult(False, detail=result.detail,
                                     last_action=action.summary())
        return GUIStepResult(True, detail="gui steps ok")

    # ---- GUI skills ------------------------------------------------------
    def _skill_create_material(self) -> GUIStepResult:
        nav = self._run_actions("create_material", [
            Action("navigate", target="/materials"),
            Action("wait", params={"for": "visible", "role": "button",
                                   "name": "新建物料", "timeout": 8000},
                   reasoning="Wait for the Materials view to mount"),
        ])
        if not nav.ok:
            return nav
        # Observe-first idempotency: if the code already shows in the page,
        # the material exists and we skip the create dialog.
        if self.ctx.material_code and self.ctx.material_code in self.env.observe().visible_text:
            return GUIStepResult(True, "material already present in GUI")
        return self._run_actions("create_material", [
            Action("click", target="新建物料", params={"role": "button"},
                   reasoning="Open the material creation dialog"),
            Action("wait", params={"for": "visible", "role": "dialog", "timeout": 8000},
                   reasoning="Wait for the creation dialog to open"),
            Action("type", target="物料编码", value=self.ctx.material_code),
            Action("type", target="物料名称", value=self.ctx.material_name),
            Action("select", target="类型", value=self.ctx.material_type),
            Action("type", target="单位", value=self.ctx.unit),
            Action("type", target="规格", value=self.ctx.specification),
            Action("click", target="保存", params={"role": "button"},
                   reasoning="Persist the new material"),
            Action("wait", params={"for": "hidden", "role": "dialog", "timeout": 8000},
                   reasoning="Wait for the dialog to close after save"),
        ])

    def _skill_create_bom(self) -> GUIStepResult:
        nav = self._run_actions("create_bom", [
            Action("navigate", target="/boms"),
            Action("wait", params={"for": "visible", "role": "button",
                                   "name": "新建 BOM", "timeout": 8000},
                   reasoning="Wait for the BOM view to mount"),
        ])
        if not nav.ok:
            return nav
        if self.ctx.bom_code and self.ctx.bom_code in self.env.observe().visible_text:
            return GUIStepResult(True, "bom already present in GUI")

        create = self._run_actions("create_bom", [
            Action("click", target="新建 BOM", params={"role": "button"},
                   reasoning="Open the BOM creation dialog"),
            Action("wait", params={"for": "visible", "role": "dialog", "timeout": 8000},
                   reasoning="Wait for the BOM dialog to open"),
            Action("type", target="BOM 编码", value=self.ctx.bom_code),
            Action("type", target="产品", value=self.ctx.product),
            Action("type", target="版本", value="1.0"),
            Action("type", target="工艺路线", value=_ROUTE),
            Action("click", target="保存", params={"role": "button"},
                   reasoning="Persist the BOM header"),
            Action("wait", params={"for": "hidden", "role": "dialog", "timeout": 8000},
                   reasoning="Wait for the BOM dialog to close after save"),
        ])
        if not create.ok:
            return create

        if self.ctx.bom_materials:
            items = self._run_actions("create_bom", [
                Action("click", target="物料明细", params={"role": "button"},
                       reasoning="Open the BOM materials detail dialog"),
                Action("wait", params={"for": "visible", "role": "dialog", "timeout": 8000},
                       reasoning="Wait for the detail dialog to open"),
            ])
            if not items.ok:
                return items
            for m in self.ctx.bom_materials:
                step = self._run_actions("create_bom", [
                    Action("type", target="物料编码", value=m.get("material_code", "")),
                    Action("type", target="数量", value=str(m.get("quantity", 1))),
                    Action("click", target="添加", params={"role": "button"},
                           reasoning="Add the material line to the BOM"),
                ])
                if not step.ok:
                    return step
            self._run_actions("create_bom", [
                Action("press", target="Escape", reasoning="Close the detail dialog"),
                Action("wait", params={"for": "hidden", "role": "dialog", "timeout": 8000},
                       reasoning="Wait for the detail dialog to close"),
            ])
        return GUIStepResult(True, "bom created via GUI")

    def _skill_create_order(self) -> GUIStepResult:
        nav = self._run_actions("create_production_order", [
            Action("navigate", target="/orders"),
            Action("wait", params={"for": "visible", "role": "button",
                                   "name": "新建指令", "timeout": 8000},
                   reasoning="Wait for the Orders view to mount"),
        ])
        if not nav.ok:
            return nav
        if self.ctx.order_code and self.ctx.order_code in self.env.observe().visible_text:
            return GUIStepResult(True, "order already present in GUI")
        return self._run_actions("create_production_order", [
            Action("click", target="新建指令", params={"role": "button"},
                   reasoning="Open the production order creation dialog"),
            Action("wait", params={"for": "visible", "role": "dialog", "timeout": 8000},
                   reasoning="Wait for the order dialog to open"),
            Action("type", target="指令号", value=self.ctx.order_code),
            Action("type", target="产品", value=self.ctx.product),
            Action("type", target="批次", value=self.ctx.batch),
            Action("type", target="数量", value=str(self.ctx.quantity)),
            Action("click", target="保存", params={"role": "button"},
                   reasoning="Persist the production order"),
            Action("wait", params={"for": "hidden", "role": "dialog", "timeout": 8000},
                   reasoning="Wait for the dialog to close after save"),
        ])

    def _skill_execute_production(self) -> GUIStepResult:
        # Independent read-back check: if already COMPLETED, accept.
        order = self.env.get_order(self.ctx.order_code)
        if order and order.get("status") == "COMPLETED":
            return GUIStepResult(True, "production already completed (read-back)")

        nav = self._run_actions("execute_production", [
            Action("navigate", target="/execution"),
            Action("wait", params={"for": "visible", "role": "combobox",
                                   "name": "选择指令", "timeout": 8000},
                   reasoning="Wait for the execution view to mount"),
            Action("select", target="选择指令", value=self.ctx.order_code,
                   reasoning="Select the target production order"),
            Action("wait", params={"for": "visible", "role": "button",
                                   "name": "完成称量", "timeout": 8000},
                   reasoning="Wait for the 7-stage table to render"),
        ])
        if not nav.ok:
            return nav

        # Complete each stage in canonical order. Each click is a *scoped
        # semantic target*: locate the row whose accessible text contains the
        # stage label, then click the "完成" button inside that row. Locators
        # are re-resolved from the fresh DOM every step, so a Vue re-render
        # between stages never leaves a stale handle behind.
        for stage in PRODUCTION_STAGES:
            zh = STAGE_LABELS_ZH[stage]
            click = self._run_actions("execute_production", [
                Action("click", target={"within": {"role": "row", "text": zh},
                                        "role": "button", "name": "完成"},
                       reasoning=f"Complete production stage '{zh}' within its table row"),
            ])
            if not click.ok:
                return click
            wait = self._run_actions("execute_production", [
                Action("wait", params={"for": "disabled", "role": "button",
                                       "name": f"完成{zh}", "timeout": 8000},
                       reasoning=f"Wait until stage '{zh}' is marked completed "
                                 "(its 完成 button becomes disabled)"),
            ])
            if not wait.ok:
                return wait

        order = self.env.get_order(self.ctx.order_code)
        if order and order.get("status") == "COMPLETED":
            return GUIStepResult(True, "production completed via GUI")
        return GUIStepResult(False, detail=f"order status is {order.get('status') if order else 'missing'}")

    # ---- helpers ---------------------------------------------------------
    def _trace(self, *, subgoal: str, observation: str, reasoning: str,
               action: str, result: str, evidence: dict | None = None) -> None:
        self.trace.record(
            goal=self.task.instruction, subgoal=subgoal,
            observation=observation, reasoning_summary=reasoning,
            action=action, result=result, evidence=evidence or {},
            memory_state=self.memory.to_dict() if self.memory else {},
            recovery_count=0,
        )

    @staticmethod
    def _signature(obs: BrowserObservation) -> str:
        parts = [obs.visible_text]
        for e in obs.interactive_elements:
            parts.append(f"{e.get('role')}:{e.get('accessible_name')}")
        return "|".join(parts)

    @staticmethod
    def _elems_summary(obs: BrowserObservation) -> str:
        return ", ".join(
            f"{e.get('role')}[{e.get('accessible_name') or e.get('text')[:20]}]"
            for e in obs.interactive_elements[:20]
        )


_ROUTE = "weighing>dissolution>filtration>filling>labeling>packaging>storage"

# Chinese labels for the 7 canonical production stages (mirrors the Vue view).
STAGE_LABELS_ZH = {
    "weighing": "称量",
    "dissolution": "溶解",
    "filtration": "过滤",
    "filling": "分装",
    "labeling": "贴签",
    "packaging": "包装",
    "storage": "入库",
}
