"""V1.3 adaptive-recovery tests (state diff / diagnosis / local replanning).

These tests pin the *mechanisms*: state diff classification, dependency-aware
repair planning (missing BOM + stage interruption), retry budget, preserve /
reexecute accounting, premature-DONE diagnosis, and a full local-replan E2E
driven by a scripted policy + fault injector (no browser / no LLM required).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from hosp2mes.agent.agent import PRODUCTION_STAGES, Task  # noqa: E402
from hosp2mes.agents.hosp2mes_agent import (  # noqa: E402
    ActionPolicy,
    Hosp2MESAgent,
    PolicyDecision,
)
from hosp2mes.config import Config  # noqa: E402
from hosp2mes.observation.api_env import ActionResult  # noqa: E402
from hosp2mes.observation.browser_observation import BrowserObservation  # noqa: E402
from hosp2mes.planner.planner import Planner  # noqa: E402
from hosp2mes.recovery.diagnosis import (  # noqa: E402
    MISSING_PREREQUISITE,
    PREMATURE_DONE,
    diagnose,
)
from hosp2mes.recovery.recovery import RecoveryEngine  # noqa: E402
from hosp2mes.state.business_state import first_incomplete_stage  # noqa: E402
from hosp2mes.state.state_diff import diff  # noqa: E402


def _plan():
    return Planner(Config(llm_provider="mock")).plan(
        "demo", {
            "material_exists": True, "bom_exists": True,
            "production_order_status": "COMPLETED", "storage_status": "STORED",
        })


class _FakeReader:
    def __init__(self, state):
        self._state = state

    def read(self):
        from hosp2mes.state.business_state import BusinessState

        b = BusinessState()
        b.material = self._state.get("material", {"exists": False, "status": None})
        b.bom = self._state.get("bom", {"exists": False, "status": None})
        b.production_order = self._state.get("production_order", {"exists": False, "status": None})
        b.stages = self._state.get("stages", {s: "NOT_STARTED" for s in PRODUCTION_STAGES})
        return b


# ---- state diff -----------------------------------------------------------
def test_state_diff_classification():
    d = diff(
        {"material": {"exists": True}, "bom": {"exists": True},
         "production_order": {"status": "COMPLETED"}, "stages": {"storage": "COMPLETED"}},
        {"material": {"exists": True}, "bom": {"exists": False},
         "production_order": {"exists": True, "status": "IN_PROGRESS"},
         "stages": {"storage": "NOT_STARTED"}},
    )
    assert d.matched == {"material.exists": True}
    assert "bom.exists" in d.missing
    assert "production_order.status" in d.mismatched
    assert d.conflicting == d.mismatched
    assert not d.is_clean


def test_state_diff_clean():
    d = diff({"material": {"exists": True}}, {"material": {"exists": True}})
    assert d.is_clean
    assert not d.missing and not d.mismatched


# ---- dependency-aware repair planning -------------------------------------
def test_repair_plan_missing_bom():  # Test A
    engine = RecoveryEngine()
    reader = _FakeReader({
        "material": {"exists": True, "status": "ACTIVE"},
        "bom": {"exists": False, "status": None},
        "production_order": {"exists": False, "status": None},
    })
    res = engine.recover(failed_subgoal="create_production_order",
                         plan=_plan(), state_reader=reader)
    assert res.recoverable
    assert res.diagnosis.failure_category == MISSING_PREREQUISITE
    assert res.diagnosis.affected_state == ["bom.exists"]
    view = res.repair_plan.dependency_view()
    assert view["preserve"] == ["create_material"]
    assert view["reactivate"] == ["create_bom"]
    assert view["invalidate"] == ["create_bom", "create_production_order", "execute_production"]
    assert view["resume_from"] == "create_bom"
    assert res.remaining_ids == ["create_bom", "create_production_order", "execute_production"]


def test_repair_plan_stage_interrupted():  # Test B
    engine = RecoveryEngine()
    stages = {s: "COMPLETED" for s in ["weighing", "dissolution"]}
    stages.update({s: "NOT_STARTED" for s in
                   ["filtration", "filling", "labeling", "packaging", "storage"]})
    reader = _FakeReader({
        "material": {"exists": True, "status": "ACTIVE"},
        "bom": {"exists": True, "status": "ACTIVE"},
        "production_order": {"exists": True, "status": "IN_PROGRESS"},
        "stages": stages,
    })
    res = engine.recover(failed_subgoal="execute_production",
                         plan=_plan(), state_reader=reader)
    assert res.recoverable
    view = res.repair_plan.dependency_view()
    # Earlier completed subgoals are preserved; only execution is reactivated.
    assert view["preserve"] == ["create_material", "create_bom", "create_production_order"]
    assert view["reactivate"] == ["execute_production"]
    assert view["resume_from"] == "execute_production"
    # The first incomplete stage (not weighing/dissolution) is where execution resumes.
    assert first_incomplete_stage(stages) == "filtration"


# ---- retry budget + preserve accounting -----------------------------------
def test_recovery_retry_budget():
    engine = RecoveryEngine(max_attempts=1)
    reader = _FakeReader({"material": {"exists": True, "status": "ACTIVE"},
                          "bom": {"exists": False, "status": None},
                          "production_order": {"exists": False, "status": None}})
    res = engine.recover(failed_subgoal="create_production_order",
                         plan=_plan(), state_reader=reader)
    assert res.recoverable
    assert engine.recovery_count == 1
    assert not engine.can_recover()  # budget exhausted


def test_reexecuted_completed_subgoals_zero():
    engine = RecoveryEngine()
    reader = _FakeReader({"material": {"exists": True, "status": "ACTIVE"},
                          "bom": {"exists": False, "status": None},
                          "production_order": {"exists": False, "status": None}})
    engine.recover(failed_subgoal="create_production_order", plan=_plan(), state_reader=reader)
    # The preserved (state-verified) material subgoal was never re-executed.
    assert engine.reexecuted_completed_subgoals == 0
    assert engine.local_replan_count == 1
    assert engine.state_diff_count == 1


# ---- diagnosis ------------------------------------------------------------
def test_premature_done_diagnosis():
    d = diagnose("execute_production", {"production_order": {"exists": True, "status": "IN_PROGRESS"},
                                        "stages": {"storage": "NOT_STARTED"}},
                 premature_done=True)
    assert d.failure_category == PREMATURE_DONE
    assert d.recoverable


def test_diagnosis_missing_prerequisite():
    d = diagnose("create_production_order", {"bom": {"exists": False},
                                             "production_order": {"exists": False}})
    assert d.failure_category == MISSING_PREREQUISITE
    assert d.affected_state == ["bom.exists"]


# ---- full local-replan E2E (scripted policy + fault injector) -------------
class _StatefulEnv:
    artifacts_dir = None

    def __init__(self):
        self.materials = {}
        self.boms = {}
        self.orders = {}

    def start(self):
        return self

    def reset(self):
        pass

    def close(self):
        pass

    def observe(self):
        return BrowserObservation(current_url="http://x/", title="t", visible_text="",
                                  interactive_elements=[], accessibility=[], timestamp="")

    def screenshot(self, name=None):
        return None, None

    def execute(self, action):
        return ActionResult(ok=True)

    def get_material(self, code):
        return self.materials.get(code)

    def get_bom(self, code):
        return self.boms.get(code)

    def get_order(self, code):
        return self.orders.get(code)

    def system_state(self, product=None, material_code=None):
        out = {}
        if material_code:
            out["material_exists"] = material_code in self.materials
        if product:
            bom = next((b for b in self.boms.values() if b.get("product") == product), None)
            out["bom_exists"] = bom is not None
            order = next((o for o in self.orders.values() if o.get("product") == product), None)
            out["production_order_status"] = order["status"] if order else None
            stored = order and any(
                s.get("stage_name") == "storage" and s.get("stage_status") == "COMPLETED"
                for s in order.get("stages", []))
            out["storage_status"] = "STORED" if stored else "NOT_STORED"
        return out


class _ScriptedPolicy(ActionPolicy):
    """Creates each business object as a side effect, then returns 'done'."""

    def __init__(self, config, ctx, env):
        super().__init__(config, ctx)
        self.env = env

    def next_action(self, context):
        sg = (context.get("current_subgoal") or {}).get("id", "")
        ctx = self.ctx
        if sg == "create_material" and ctx.material_code not in self.env.materials:
            self.env.materials[ctx.material_code] = {"status": "ACTIVE"}
        elif sg == "create_bom" and ctx.bom_code not in self.env.boms:
            self.env.boms[ctx.bom_code] = {"status": "ACTIVE", "product": ctx.product}
        elif sg == "create_production_order" and ctx.order_code not in self.env.orders:
            self.env.orders[ctx.order_code] = {"status": "IN_PROGRESS",
                                               "product": ctx.product, "stages": []}
        elif sg == "execute_production":
            o = self.env.orders.get(ctx.order_code)
            if o is not None:
                o["status"] = "COMPLETED"
                o["stages"] = [{"stage_name": s, "stage_status": "COMPLETED"}
                               for s in PRODUCTION_STAGES]
        return PolicyDecision(action="done", policy_source="deterministic",
                              rationale="scripted side-effect create")


def test_recovery_loop_local_replan_e2e(tmp_path):
    task = Task(
        task_id="T-REC", instruction="full workflow", product="P",
        expected_final_state={"material_exists": True, "bom_exists": True,
                              "production_order_status": "COMPLETED",
                              "storage_status": "STORED"},
        target_material_code="M", bom_code="B", order_code="O", max_steps=6,
    )
    config = Config(llm_provider="mock", policy="deterministic",
                    artifacts_root=str(tmp_path))
    env = _StatefulEnv()
    agent = Hosp2MESAgent(config, env, task)
    agent.policy = _ScriptedPolicy(config, agent.ctx, env)

    # Harness fault: discard the BOM right after create_bom completes.
    from benchmark.faults.faults import FaultInjector, FaultSpec

    fault = FaultInjector(discard_fn=lambda target: env.boms.pop("B", None))
    fault.arm(FaultSpec(fault_id="FAULT-BOM-001", trigger="after_subgoal_completed",
                        target_subgoal="create_bom", effect="discard_state_change",
                        target="bom", once=True))
    agent.on_subgoal_completed.append(fault.on_subgoal_completed)

    report, trace, memory = agent.run()

    assert fault.triggered, "fault must have fired"
    assert report.task_success is True
    assert report.verifier_passed is True
    # Exactly one recovery episode, and it succeeded.
    assert agent.recovery.recovery_count == 1
    assert agent.recovery.recovery_success_count == 1
    assert agent.recovery.recovery_failure_count == 0
    assert agent.recovery.reexecuted_completed_subgoals == 0
    assert agent.recovery.local_replan_count == 1
    assert agent.recovery.state_diff_count >= 1
    assert agent.recovery.total_recovery_steps > 0
    # Material was created exactly once (preserved, never re-executed).
    assert list(env.materials.keys()) == ["M"]
    # The BOM was recreated after the fault (recovery re-executed create_bom).
    assert "B" in env.boms
    # A recovery trace was written to the run directory.
    rec_dir = os.path.join(tmp_path, "runs", agent.run_id, "recovery")
    assert os.path.isdir(rec_dir)
    assert any(f.startswith("recovery-") for f in os.listdir(rec_dir))
