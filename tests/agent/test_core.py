"""Unit tests for the agent's core modules (no backend / network needed)."""
from __future__ import annotations

from hosp2mes.config import Config
from hosp2mes.evaluation.evaluator import Evaluator
from hosp2mes.memory.progress_memory import ProgressMemory
from hosp2mes.planner.planner import Planner
from hosp2mes.recovery.recovery import RecoveryManager
from hosp2mes.verifier.verifier import EvidenceVerifier


# ---- planner ---------------------------------------------------------------
def test_planner_emits_subgoals_from_expected_state():
    p = Planner(Config(llm_provider="mock"))
    plan = p.plan("demo", {
        "material_exists": True, "bom_exists": True,
        "production_order_status": "NOT_STARTED", "storage_status": "STORED",
    })
    assert plan.ids() == [
        "create_material", "create_bom",
        "create_production_order", "execute_production",
    ]


def test_planner_only_material():
    p = Planner(Config(llm_provider="mock"))
    plan = p.plan("demo", {"material_exists": True})
    assert plan.ids() == ["create_material"]


# ---- progress memory -------------------------------------------------------
def test_progress_memory_independent_lists():
    pm = ProgressMemory.from_plan("g", ["a", "b", "c"])
    assert pm.pending_subgoals == ["a", "b", "c"]
    assert pm.completed_subgoals == []
    pm.mark_completed("a")
    # completing 'a' must NOT mutate the original plan list
    assert pm.subgoals == ["a", "b", "c"]
    assert pm.pending_subgoals == ["b", "c"]
    assert pm.completed_subgoals == ["a"]
    assert not pm.all_done()
    pm.mark_completed("b")
    pm.mark_completed("c")
    assert pm.all_done()


def test_progress_memory_failed():
    pm = ProgressMemory.from_plan("g", ["a", "b"])
    pm.mark_failed("a", reason="boom")
    assert "a" in pm.failed_subgoals
    assert "a" not in pm.pending_subgoals
    assert not pm.all_done()


# ---- verifier --------------------------------------------------------------
class _FakeEnv:
    def __init__(self, state):
        self.state = state

    def system_state(self, product=None, material_code=None):
        return self.state


def test_verifier_passes_when_all_observed():
    env = _FakeEnv({
        "material_exists": True, "bom_exists": True,
        "production_order_status": "COMPLETED", "storage_status": "STORED",
    })
    task = type("T", (), {
        "expected_final_state": {
            "material_exists": True, "bom_exists": True,
            "production_order_status": "COMPLETED", "storage_status": "STORED",
        },
        "product": "P", "target_material_code": "M",
    })()

    v = EvidenceVerifier().verify(env, task)
    assert v.passed
    assert v.missing == []


def test_verifier_fails_on_missing():
    env = _FakeEnv({"material_exists": True, "bom_exists": False})
    task = type("T", (), {
        "expected_final_state": {"material_exists": True, "bom_exists": True},
        "product": "P", "target_material_code": "M",
    })()
    v = EvidenceVerifier().verify(env, task)
    assert not v.passed
    assert v.missing == ["bom_exists"]


# ---- recovery --------------------------------------------------------------
class _FakeRecoveryEnv:
    def __init__(self, anomalies, resolve_ok=True):
        self._anomalies = anomalies
        self._resolve_ok = resolve_ok
        self.resolved = []

    def active_anomalies(self, target):
        return [a for a in self._anomalies
                if a.get("active") and (a.get("target") == target
                                        or a.get("target") == "global")]

    def resolve_anomaly(self, aid):
        self.resolved.append(aid)
        return self._resolve_ok


def test_recovery_clears_fault():
    env = _FakeRecoveryEnv([{"id": 7, "active": True, "target": "bom"}])
    rm = RecoveryManager()
    rec = rm.attempt("create_bom", None, env)
    assert rec.recovered
    assert rm.count() == 1
    assert env.resolved == [7]


def test_recovery_no_fault():
    env = _FakeRecoveryEnv([])
    rm = RecoveryManager()
    rec = rm.attempt("create_material", None, env)
    assert not rec.recovered
    assert rm.count() == 1  # the failed attempt is still recorded


# ---- evaluator ------------------------------------------------------------
def test_evaluator_end_to_end_success():
    pm = ProgressMemory.from_plan("g", ["a", "b", "c"])
    pm.mark_completed("a")
    pm.mark_completed("b")
    pm.mark_completed("c")

    vresult = type("V", (), {
        "passed": True, "missing": [], "observed": {},
    })()

    class _Trace:
        steps = [1, 2, 3, 4]

    report = Evaluator().evaluate(
        task_id="T-1", memory=pm, trace=_Trace(), verifier_result=vresult,
        recovery_count=0, premature_done=0, mode="hosp2mes",
    )
    assert report.task_success
    assert report.end_to_end_success
    assert report.subgoal_completion_rate == 1.0
    assert report.verifier_passed
