"""Hosp2MES agent: the long-horizon orchestrator.

The agent ties together every module:
  planner  -> decompose the goal into subgoals
  memory   -> explicit progress tracking
  executor -> translate abstract actions into environment operations
  verifier -> evidence-gated completion (read real system state)
  recovery -> local recovery on failure
  trace    -> per-step structured log
  evaluation -> end-to-end metrics

It supports two modes (see README "Baseline vs Hosp2MES"):
  * hosp2mes  - full pipeline: planner + memory + verifier + recovery
  * baseline   - classic GUI-agent behaviour: executes the plan, trusts the
                 action-level outcome, no evidence gate and no recovery.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

from hosp2mes.config import Config
from hosp2mes.evaluation.evaluator import Evaluator
from hosp2mes.executor.actions import Action
from hosp2mes.executor.executor import ExecContext, Executor
from hosp2mes.memory.progress_memory import ProgressMemory
from hosp2mes.observation.api_env import ActionResult, ApiEnv
from hosp2mes.planner.planner import Planner
from hosp2mes.recovery.recovery import RecoveryManager
from hosp2mes.trace.trace import TraceRecorder
from hosp2mes.verifier.verifier import EvidenceVerifier


# Canonical production stages (must match backend PRODUCTION_STAGES).
PRODUCTION_STAGES = [
    "weighing", "dissolution", "filtration",
    "filling", "labeling", "packaging", "storage",
]


@dataclass
class Task:
    task_id: str
    instruction: str
    product: str
    expected_final_state: dict = field(default_factory=dict)
    goal: str = ""
    # parameters the agent needs (synthetic, never real data)
    target_material_code: str = ""
    target_material_name: str = ""
    material_type: str = "raw"
    unit: str = "kg"
    specification: str = ""
    bom_code: str = ""
    bom_materials: list[dict] = field(default_factory=list)
    order_code: str = ""
    batch: str = ""
    quantity: int = 1
    max_steps: int = 100
    inject_anomaly: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class TaskLoader:
    @staticmethod
    def from_yaml(path: str) -> Task:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return Task(
            task_id=data["task_id"],
            instruction=data["instruction"],
            product=data["product"],
            expected_final_state=data.get("expected_final_state", {}),
            goal=data.get("goal", data["instruction"]),
            target_material_code=data.get("target_material_code", ""),
            target_material_name=data.get("target_material_name", ""),
            material_type=data.get("material_type", "raw"),
            unit=data.get("unit", "kg"),
            specification=data.get("specification", ""),
            bom_code=data.get("bom_code", ""),
            bom_materials=data.get("bom_materials", []),
            order_code=data.get("order_code", ""),
            batch=data.get("batch", ""),
            quantity=data.get("quantity", 1),
            max_steps=data.get("max_steps", 100),
            inject_anomaly=data.get("inject_anomaly"),
        )

    @staticmethod
    def from_dict(data: dict) -> Task:
        return Task(**data)


@dataclass
class SkillResult:
    ok: bool
    evidence: dict = field(default_factory=dict)
    error: str = ""
    last_result: ActionResult | None = None


class Agent:
    def __init__(self, config: Config, env: ApiEnv, task: Task):
        self.config = config
        self.env = env
        self.task = task
        self.planner = Planner(config)
        self.executor = Executor()
        self.verifier = EvidenceVerifier()
        self.recovery = RecoveryManager()
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
        self.premature_done = 0
        self.max_steps = task.max_steps or config.max_steps
        self._current_sg = "init"
        self.use_recovery = config.agent_mode == "hosp2mes"
        self.use_verifier = config.agent_mode == "hosp2mes"

    # ---- helpers --------------------------------------------------------
    def _trace(self, observation, reasoning, action, result, evidence=None):
        return self.trace.record(
            goal=self.task.instruction,
            subgoal=self._current_sg,
            observation=observation,
            reasoning_summary=reasoning,
            action=action,
            result=result,
            evidence=evidence,
            memory_state=self.memory.to_dict() if self.memory else {},
            recovery_count=self.recovery.count(),
        )

    def _do(self, action: Action, reasoning: str, observation: str) -> ActionResult:
        res = self.executor.execute(action, self.env, self.ctx)
        self._trace(observation=observation, reasoning=reasoning,
                    action=action.summary(),
                    result="ok" if res.ok else f"FAIL: {res.detail}",
                    evidence=res.evidence)
        return res

    # ---- skills ----------------------------------------------------------
    # Each skill is *observe-first / idempotent*: if the required business
    # object already exists in the system, the agent treats it as already done
    # and proceeds straight to verification. This is what keeps a long-horizon
    # agent robust to re-runs and shared environments instead of crashing on a
    # "already exists" error.
    def _skill_create_material(self) -> SkillResult:
        self._do(Action("navigate", "materials"),
                 "Open Materials master-file module", "page=materials")
        existing = self.env.get_material(self.ctx.material_code)
        if existing is None:
            res = self._do(Action("create_material"),
                           f"Create material {self.ctx.material_code}",
                           "materials form filled")
            if not res.ok:
                return SkillResult(False, error=res.detail, last_result=res)
        v = self._do(Action("verify", params={"material_code": self.ctx.material_code}),
                     "Verify material persisted in system", "materials list")
        return SkillResult(v.ok, evidence={"material_code": self.ctx.material_code})

    def _skill_create_bom(self) -> SkillResult:
        self._do(Action("navigate", "boms"),
                 "Open BOM management module", "page=boms")
        # Idempotent on the resource's own code (not the product): re-runs do
        # not duplicate, but a unique code still triggers a real create that can
        # hit an injected fault and exercise local recovery.
        existing = self.env.get_bom(self.ctx.bom_code)
        if existing is None:
            res = self._do(Action("create_bom"),
                           f"Create BOM {self.ctx.bom_code} for {self.ctx.product}",
                           "bom form filled")
            if not res.ok:
                return SkillResult(False, error=res.detail, last_result=res)
        v = self._do(Action("verify", params={"product": self.ctx.product}),
                     "Verify BOM persisted in system", "bom list")
        return SkillResult(v.ok, evidence={"bom_code": self.ctx.bom_code})

    def _skill_create_order(self) -> SkillResult:
        self._do(Action("navigate", "orders"),
                 "Open Production Order module", "page=orders")
        existing = self.env.get_order(self.ctx.order_code)
        if existing is None:
            res = self._do(Action("create_order"),
                           f"Create production order {self.ctx.order_code}",
                           "order form filled")
            if not res.ok:
                return SkillResult(False, error=res.detail, last_result=res)
        v = self._do(Action("verify", params={"product": self.ctx.product,
                                              "require_order": True}),
                     "Verify production order exists", "order list")
        return SkillResult(v.ok, evidence={"order_code": self.ctx.order_code})

    def _skill_execute_production(self) -> SkillResult:
        order = self.env.get_order_for_product(self.ctx.product)
        if order and order.get("status") == "COMPLETED":
            # Already executed in a prior run; observe and accept.
            self._do(Action("navigate", "execution"),
                     "Open execution view (already complete)", "page=execution")
            v = self._do(Action("verify", params={"product": self.ctx.product}),
                         "Verify production already completed", "execution")
            return SkillResult(v.ok, evidence={"stages": PRODUCTION_STAGES})
        self._do(Action("start_order"),
                 f"Start production order for {self.ctx.product}", "order started")
        for stage in PRODUCTION_STAGES:
            self._do(Action("navigate", "execution"),
                     f"Open execution view for stage {stage}", "page=execution")
            res = self._do(Action("complete_stage", stage),
                           f"Complete stage {stage}", f"stage={stage}")
            if not res.ok:
                return SkillResult(False, error=res.detail, last_result=res)
        return SkillResult(True, evidence={"stages": PRODUCTION_STAGES})

    SKILLS = {
        "create_material": "_skill_create_material",
        "create_bom": "_skill_create_bom",
        "create_production_order": "_skill_create_order",
        "execute_production": "_skill_execute_production",
    }

    # ---- main loop -------------------------------------------------------
    def run(self):
        self.trace.start_run(self.task.task_id, self.task.instruction)

        # Optional injected anomaly for the recovery demo.
        if self.task.inject_anomaly:
            a = self.task.inject_anomaly
            aid = self.env.inject_anomaly(a.get("type", "save_failure"),
                                          a.get("target", "bom"),
                                          a.get("message", "injected for demo"))
            self._trace(observation=f"anomaly injected id={aid}",
                        reasoning="Environment injected a fault to exercise recovery",
                        action="inject_anomaly", result="injected",
                        evidence={"anomaly_id": aid})

        plan = self.planner.plan(self.task.instruction, self.task.expected_final_state)
        self.memory = ProgressMemory.from_plan(self.task.instruction, plan.ids())
        self._current_sg = "planning"
        self._trace(observation=f"subgoals={plan.ids()}",
                    reasoning=f"Planner decomposed goal into {len(plan.subgoals)} subgoals",
                    action="plan", result=f"{len(plan.subgoals)} subgoals",
                    evidence={"plan": plan.ids()})

        for sg in plan.ids():
            self._current_sg = sg
            self.memory.set_current(sg)
            self._execute_subgoal(sg)

        # ---- Evidence-Gated Completion ----------------------------------
        verdict = self.verifier.verify(self.env, self.task)
        if not verdict.passed and self.use_verifier:
            # Agent may believe it is done while the system disagrees
            # (premature DONE) -> attempt a final recovery pass.
            if self.memory.all_done():
                self.premature_done += 1
            if self.use_recovery:
                self._final_recovery(verdict)
                verdict = self.verifier.verify(self.env, self.task)

        success = verdict.passed and (not self.use_verifier or self.memory.all_done())
        self._current_sg = "final_verification"
        self._trace(
            observation=f"observed={verdict.observed}",
            reasoning="Evidence verifier checked live system state against expected final state",
            action="verify:final",
            result="PASS" if verdict.passed else f"FAIL missing={verdict.missing}",
            evidence={"expected": verdict.expected, "observed": verdict.observed,
                      "missing": verdict.missing},
        )

        self.trace.finish_run(success, verdict.detail,
                              len(self.trace.steps), self.recovery.count())

        report = Evaluator().evaluate(
            task_id=self.task.task_id, memory=self.memory, trace=self.trace,
            verifier_result=verdict, recovery_count=self.recovery.count(),
            premature_done=self.premature_done, mode=self.config.agent_mode,
        )
        return report, self.trace, self.memory

    def _execute_subgoal(self, sg: str) -> None:
        attempts = 0
        max_attempts = 3
        while not self.memory.is_completed(sg) and attempts < max_attempts:
            skill = getattr(self, self.SKILLS[sg])
            res: SkillResult = skill()
            if res.ok:
                self.memory.mark_completed(sg, evidence=res.evidence)
                self._trace(observation=f"{sg} verified in system",
                            reasoning=f"Subgoal '{sg}' completed and verified",
                            action=f"verify:{sg}", result="completed",
                            evidence=res.evidence)
                return
            # failure -> recovery (hosp2mes mode only)
            if self.use_recovery:
                rec = self.recovery.attempt(sg, res.last_result, self.env)
                if rec.recovered:
                    self._trace(observation=f"recovery on {sg}",
                                reasoning=rec.reason,
                                action="recover", result=rec.detail,
                                evidence={"recovery_action": rec.action})
                    attempts += 1
                    continue  # retry the skill
            self.memory.mark_failed(sg, reason=res.error)
            self._trace(observation=f"{sg} failed",
                        reasoning=f"Subgoal '{sg}' failed: {res.error}",
                        action=f"fail:{sg}", result="failed",
                        evidence={"error": res.error})
            return
        if not self.memory.is_completed(sg):
            self.memory.mark_failed(sg, reason="exhausted recovery attempts")

    def _final_recovery(self, verdict) -> None:
        # Repair any still-unmet expected conditions by re-running the planner
        # for the missing subgoals only (local recovery, not a full restart).
        missing = set(verdict.missing)
        repair_map = {
            "material_exists": "create_material",
            "bom_exists": "create_bom",
            "production_order_status": "create_production_order",
            "storage_status": "execute_production",
        }
        for cond in missing:
            sg = repair_map.get(cond)
            if sg and not self.memory.is_completed(sg):
                self._current_sg = sg
                self.memory.set_current(sg)
                self._trace(observation=f"replan repair for {cond}",
                            reasoning=f"Final verifier missing {cond}; repairing subgoal {sg}",
                            action="replan", result="repair")
                self._execute_subgoal(sg)
