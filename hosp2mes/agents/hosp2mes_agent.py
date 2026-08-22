"""Hosp2MESAgent — a true one-action-per-step decision loop.

Unlike :class:`~hosp2mes.agents.skill_agent.SemanticSkillAgent` (which emits a
whole per-subgoal action list up front), this agent runs a **decision loop**:

    GOAL + CURRENT SUBGOAL + STRUCTURED MEMORY + CURRENT BROWSER OBSERVATION
        -> ActionPolicy.predict_one() -> ONE NEXT ACTION
        -> BrowserExecutor -> new observation
        -> ActionPolicy.predict_one() -> ...

Every iteration produces exactly one next GUI action. The action is decided from
the *live* observation (url / visible text / interactive elements) plus the
structured progress memory, never from a pre-written action array.

Two policy backends share the same interface:

* **LLM** (``ActionPolicy`` with a real model) — builds a prompt from the
  context and asks the model to return one structured action. Used when an LLM
  provider + API key are configured.
* **Deterministic fallback** — an observation-driven form/flow policy used in
  ``mock`` mode (CI / offline), so the loop is still genuinely observable and
  emits one action at a time.

The policy output is strictly structured and public-safe::

    {
      "action": "click|type|select|scroll|wait|back|done",
      "target": {...} | "...",
      "value": ...,
      "rationale": "short public rationale"
    }

No private chain-of-thought is emitted or stored.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
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
from hosp2mes.planner.planner import Plan, Planner, Subgoal
from hosp2mes.trace.trace import TraceRecorder
from hosp2mes.verifier.verifier import EvidenceVerifier


# Generic form specs keyed by *capability* (NOT task id). Each spec describes a
# business form in terms of public UI semantics plus the ExecContext field that
# provides the value. This is the same data a human would read off the form.
_FORM_SPECS: dict[str, dict] = {
    "create_material": {
        "page": "/materials",
        "open": "新建物料",
        "save": "保存",
        "fields": [
            ("物料编码", "material_code", "type"),
            ("物料名称", "material_name", "type"),
            ("类型", "material_type", "select"),
            ("单位", "unit", "type"),
            ("规格", "specification", "type"),
        ],
    },
    "create_bom": {
        "page": "/boms",
        "open": "新建 BOM",
        "save": "保存",
        "fields": [
            ("BOM 编码", "bom_code", "type"),
            ("产品", "product", "type"),
            ("版本", "version", "type"),
            ("工艺路线", "route", "type"),
        ],
    },
    "create_production_order": {
        "page": "/orders",
        "open": "新建指令",
        "save": "保存",
        "fields": [
            ("指令号", "order_code", "type"),
            ("产品", "product", "type"),
            ("批次", "batch", "type"),
            ("数量", "quantity", "type"),
        ],
    },
}


class ActionPolicy:
    """Produces ONE next action from a policy context (LLM or deterministic)."""

    def __init__(self, config: Config, ctx: ExecContext):
        self.config = config
        self.ctx = ctx
        self._llm = None
        if config.use_real_llm():
            from hosp2mes.llm import build_llm

            self._llm = build_llm(config)

    # ---- public ----------------------------------------------------------
    def next_action(self, context: dict) -> dict | None:
        """Return one structured next action, or None to signal 'done'."""
        if self._llm is not None:
            decision = self._llm_next_action(context)
            if decision is not None:
                return decision
        return self._deterministic_next_action(context)

    # ---- LLM path --------------------------------------------------------
    def _llm_next_action(self, context: dict) -> dict | None:
        from hosp2mes.llm import DeepSeekLLM

        try:
            system = (
                "You are a GUI agent controlling a web page. Given the goal, the "
                "current subgoal, the structured progress memory and the current "
                "browser observation (URL, visible text, interactive elements), "
                "return exactly ONE next action. Respond with only a JSON object: "
                '{"action": "<click|type|select|scroll|wait|back|done>", '
                '"target": <string or {"within": {"role","text"}, "role","name"}>, '
                '"value": <optional>, "rationale": "<short public rationale>"}. '
                "Never reveal internal chain-of-thought."
            )
            user = json.dumps(self._promptable(context), ensure_ascii=False)
            text = self._llm.complete(system, user)
            parsed = DeepSeekLLM.parse_json_block(text)
            if "action" not in parsed:
                return None
            return {
                "action": parsed.get("action"),
                "target": parsed.get("target"),
                "value": parsed.get("value"),
                "rationale": parsed.get("rationale", ""),
            }
        except Exception:
            return None

    @staticmethod
    def _promptable(context: dict) -> dict:
        # Trim the observation to a bounded, prompt-safe size.
        elements = context.get("interactive_elements", [])
        summary = [
            {"role": e.get("role"), "name": e.get("accessible_name") or e.get("text")}
            for e in elements[:60]
        ]
        return {
            "goal": context.get("goal"),
            "current_subgoal": context.get("current_subgoal"),
            "progress_memory": context.get("progress_memory"),
            "current_url": context.get("current_url"),
            "visible_text": (context.get("visible_text") or "")[:3000],
            "interactive_elements": summary,
            "recent_actions": context.get("recent_actions", [])[-8:],
        }

    # ---- deterministic fallback -----------------------------------------
    def _deterministic_next_action(self, context: dict) -> dict | None:
        sg = context.get("current_subgoal") or {}
        sg_id = sg.get("id", "")
        capabilities = sg.get("capabilities", []) or []
        cap = capabilities[0] if capabilities else sg_id
        elements = context.get("interactive_elements", [])
        recent = context.get("recent_actions", [])

        if cap in _FORM_SPECS:
            return self._form_next(cap, context, elements, recent)

        if cap == "execute_production":
            return self._production_next(context, recent)

        # Unknown capability: signal done so the loop defers to verification.
        return {"action": "done", "rationale": f"no GUI policy for capability {cap!r}"}

    def _form_next(self, cap, context, elements, recent) -> dict:
        spec = _FORM_SPECS[cap]

        # If the last action was a save click, wait for the dialog to close.
        last = recent[-1] if recent else None
        if last and last.get("action") == "click" and _target_name(last.get("target")) == spec["save"]:
            return {
                "action": "wait",
                "params": {"for": "hidden", "role": "dialog", "timeout": 8000},
                "rationale": "wait for the dialog to close after save",
            }

        # If we are not on the target page yet, navigate there.
        url = context.get("current_url") or ""
        if spec.get("page") and spec["page"] not in url:
            return {
                "action": "navigate",
                "target": spec["page"],
                "rationale": f"navigate to {spec['page']}",
            }

        # After navigating, wait for the open button to appear (Vue mounted).
        if last and last.get("action") == "navigate":
            return {
                "action": "wait",
                "params": {"for": "visible", "role": "button",
                           "name": spec["open"], "timeout": 8000},
                "rationale": f"wait for the '{spec['open']}' button to render",
            }

        names = [e.get("accessible_name") or e.get("text") or "" for e in elements]
        dialog_open = any(spec["save"] in n for n in names)

        if not dialog_open:
            return {
                "action": "click",
                "target": {"role": "button", "name": spec["open"]},
                "rationale": f"open the {spec['open']} dialog",
            }

        # Dialog is open: fill the next field that hasn't been set yet.
        done_labels = {_target_name(r.get("target")) for r in recent}
        for label, ctx_attr, kind in spec["fields"]:
            if label in done_labels:
                continue
            value = getattr(self.ctx, ctx_attr, "")
            if kind == "select":
                return {
                    "action": "select",
                    "target": {"role": "combobox", "name": label},
                    "value": str(value or ""),
                    "rationale": f"select '{label}' = {value}",
                }
            return {
                "action": "type",
                "target": {"role": "textbox", "name": label},
                "value": str(value or ""),
                "rationale": f"fill '{label}' = {value}",
            }

        # All fields set -> save.
        return {
            "action": "click",
            "target": {"role": "button", "name": spec["save"]},
            "rationale": "save the form",
        }

    def _production_next(self, context, recent) -> dict:
        # Deterministic fallback for production execution. Each stage is
        # completed by a scoped semantic click; after a click the next decision
        # is a state-based wait for that stage's 完成 button to become disabled.
        url = context.get("current_url") or ""
        if "/execution" not in url:
            return {"action": "navigate", "target": "/execution",
                    "rationale": "navigate to the production execution view"}

        last = recent[-1] if recent else None
        if last and last.get("action") == "navigate":
            return {
                "action": "wait",
                "params": {"for": "visible", "role": "combobox",
                           "name": "选择指令", "timeout": 8000},
                "rationale": "wait for the execution view to render",
            }

        if last and last.get("action") == "click" and _target_name(last.get("target")) == "完成":
            zh = _target_scope_text(last.get("target"))
            return {
                "action": "wait",
                "params": {"for": "disabled", "role": "button",
                           "name": f"完成{zh}", "timeout": 8000},
                "rationale": f"wait until stage '{zh}' is completed",
            }

        done = set()
        for r in recent:
            if r.get("action") == "click" and _target_name(r.get("target")) == "完成":
                done.add(_target_scope_text(r.get("target")))

        for stage in PRODUCTION_STAGES:
            zh = _STAGE_ZH[stage]
            if zh in done:
                continue
            return {
                "action": "click",
                "target": {"within": {"role": "row", "text": zh},
                           "role": "button", "name": "完成"},
                "rationale": f"complete production stage '{zh}'",
            }

        return {"action": "done", "rationale": "all production stages completed"}


class Hosp2MESAgent:
    """One-action-per-step LLM policy agent."""

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
        if getattr(env, "artifacts_dir", None) is None:
            env.artifacts_dir = self.evidence.run_dir
        self.policy = ActionPolicy(config, self.ctx)
        self.gui_steps = 0
        self.failed_subgoal = ""
        self.failure_reason = ""
        self.steps_reached = 0

    # ---- lifecycle -------------------------------------------------------
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
        self.evidence.start(self.task.task_id, self.task.instruction, mode="hosp2mes")
        self.trace.start_run(self.task.task_id, self.task.instruction)

        plan = self.planner.plan(self.task.instruction, self.task.expected_final_state)
        self.memory = ProgressMemory.from_plan(self.task.instruction, plan.ordered_ids())
        subgoal_by_id = {s.id: s for s in plan.subgoals}
        self._trace(subgoal="planning", observation=f"subgoals={plan.ids()}",
                    reasoning=f"Planner produced {len(plan.subgoals)} dependency-aware subgoals",
                    action="plan", result=plan.ordered_ids(),
                    evidence={"plan": plan.to_dict()})

        for sg_id in plan.ordered_ids():
            self.steps_reached = self.gui_steps
            self.memory.set_current(sg_id)
            sg = subgoal_by_id.get(sg_id, Subgoal(id=sg_id))
            ok = self._run_subgoal_loop(sg)
            if not ok:
                self.failed_subgoal = sg_id
                break

        verdict = self.verifier.verify(self.env, self.task)
        success = verdict.passed and self.memory.all_done()
        self._trace(subgoal="final_verification", observation=f"observed={verdict.observed}",
                    reasoning="Evidence verifier checked live backend state independently",
                    action="verify:final",
                    result="PASS" if verdict.passed else f"FAIL missing={verdict.missing}",
                    evidence={"expected": verdict.expected, "observed": verdict.observed,
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

    # ---- per-subgoal decision loop ---------------------------------------
    def _run_subgoal_loop(self, sg: Subgoal) -> bool:
        max_steps = self.task.max_steps or self.config.max_steps
        recent: list[dict] = []
        for _ in range(max_steps):
            if self._subgoal_satisfied(sg):
                self.memory.mark_completed(sg.id, evidence={"success_condition": sg.success_condition})
                self._trace(subgoal=sg.id, observation=f"{sg.id} satisfied (read-back)",
                            reasoning=f"Subgoal '{sg.id}' verified via independent read-back",
                            action=f"verify:{sg.id}", result="completed")
                return True

            obs = self.env.observe()
            context = {
                "goal": self.task.instruction,
                "current_subgoal": sg.to_dict(),
                "progress_memory": self.memory.to_dict(),
                "current_url": obs.current_url,
                "visible_text": obs.visible_text,
                "interactive_elements": obs.interactive_elements,
                "recent_actions": recent,
            }
            decision = self.policy.next_action(context) or {"action": "done"}

            before_path, _ = self.env.screenshot(f"{sg.id}-{self.gui_steps:02d}-before")
            action = self._to_action(decision)
            result = self.env.execute(action) if action is not None else None
            after_path, _ = self.env.screenshot(f"{sg.id}-{self.gui_steps:02d}-after")
            after = self.env.observe()
            state_changed = self._signature(obs) != self._signature(after)

            self.gui_steps += 1
            result_str = "ok" if (result is None or result.ok) else f"FAIL: {result.detail}"
            self.evidence.record(
                step=self.gui_steps, subgoal=sg.id, url=obs.current_url,
                observation_summary=obs.summary(),
                interactive_elements_summary=self._elems_summary(obs),
                action=(action.summary() if action is not None else "done"),
                action_target=decision.get("target"),
                action_result=result_str,
                screenshot_before=before_path, screenshot_after=after_path,
                state_changed=state_changed,
            )
            self._trace(subgoal=sg.id, observation=obs.summary(),
                        reasoning=decision.get("rationale", "policy step"),
                        action=(action.summary() if action is not None else "done"),
                        result=result_str,
                        evidence={"state_changed": state_changed, "url": obs.current_url})

            recent.append({
                "action": decision.get("action"),
                "target": decision.get("target"),
                "value": decision.get("value"),
                "result": result_str,
            })
            if len(recent) > 12:
                recent = recent[-12:]

            if decision.get("action") == "done":
                # Policy claims done; the next loop iteration verifies via read-back.
                if not self._subgoal_satisfied(sg):
                    # Premature done: record and keep trying for a few rounds.
                    self.failure_reason = "policy claimed done but read-back disagrees"
                    continue

        self.memory.mark_failed(sg.id, reason="exhausted decision-loop steps")
        self.failure_reason = self.failure_reason or f"exhausted {max_steps} steps"
        return self._subgoal_satisfied(sg)

    # ---- helpers ---------------------------------------------------------
    def _to_action(self, decision: dict) -> Action | None:
        verb = decision.get("action")
        if not verb or verb == "done":
            return None
        return Action(
            verb=verb,
            target=decision.get("target", ""),
            value=decision.get("value"),
            params=decision.get("params", {}),
            reasoning=decision.get("rationale", ""),
        )

    def _subgoal_satisfied(self, sg: Subgoal) -> bool:
        sid = sg.id
        if sid == "create_material":
            return self.env.get_material(self.ctx.material_code) is not None
        if sid == "create_bom":
            return self.env.get_bom(self.ctx.bom_code) is not None
        if sid == "create_production_order":
            return self.env.get_order(self.ctx.order_code) is not None
        if sid == "execute_production":
            order = self.env.get_order(self.ctx.order_code)
            return bool(order and order.get("status") == "COMPLETED")
        return False

    def _trace(self, *, subgoal, observation, reasoning, action, result, evidence=None):
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


# Chinese labels for the 7 canonical production stages (mirrors the Vue view).
_STAGE_ZH = {
    "weighing": "称量",
    "dissolution": "溶解",
    "filtration": "过滤",
    "filling": "分装",
    "labeling": "贴签",
    "packaging": "包装",
    "storage": "入库",
}


def _target_name(target: Any) -> str:
    if isinstance(target, dict):
        return target.get("name") or target.get("text") or ""
    return str(target or "")


def _target_scope_text(target: Any) -> str:
    if isinstance(target, dict) and target.get("within"):
        return target["within"].get("text") or ""
    return ""

