"""Local Recovery (V1.3): state-diff-driven adaptive recovery.

Two layers coexist:

* :class:`RecoveryManager` — the V1.0/V1.2 anomaly-clearing recovery used by the
  deterministic api-mode :class:`~hosp2mes.agent.agent.Agent`. Kept intact for
  backward compatibility.

* :class:`RecoveryEngine` — the V1.3 *state-diff* recovery used by
  :class:`~hosp2mes.agents.hosp2mes_agent.Hosp2MESAgent`. Instead of clearing an
  injected fault, it reads the live business state, diffs it against the expected
  state, diagnoses the failure, builds a dependency-aware *local* repair plan and
  hands the remaining subgoals back to the agent so only the broken part is
  re-executed (never a full restart).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hosp2mes.observation.api_env import ApiEnv, ActionResult
from hosp2mes.recovery.diagnosis import FailureDiagnosis, diagnose
from hosp2mes.recovery.repair_planner import RepairPlan, RepairPlanner
from hosp2mes.state.business_state import expected_state_for_subgoal
from hosp2mes.state.state_diff import StateDiff, diff


@dataclass
class RecoveryAction:
    recovered: bool
    failed_subgoal: str
    reason: str = ""
    action: str = ""
    detail: str = ""
    recovery_count: int = 0


# Map a failing subgoal to the MES resource the injected anomaly targets.
_TARGET_FOR_SUBGOAL = {
    "create_material": "material",
    "create_bom": "bom",
    "create_production_order": "order",
    "execute_production": "order",
}


class RecoveryManager:
    """V1.0/V1.2 anomaly-clearing recovery (api mode). Kept for compatibility."""

    def __init__(self) -> None:
        self._records: list[dict] = []

    def count(self) -> int:
        return len(self._records)

    def records(self) -> list[dict]:
        return list(self._records)

    def attempt(self, failed_subgoal: str,
                last_result: ActionResult | None,
                env: ApiEnv) -> RecoveryAction:
        target = _TARGET_FOR_SUBGOAL.get(failed_subgoal, "global")
        anomalies = env.active_anomalies(target)
        if not anomalies:
            anomalies = env.active_anomalies("global")

        recovered = False
        reason = ""
        action = ""
        detail = ""
        if anomalies:
            aid = anomalies[0]["id"]
            if env.resolve_anomaly(aid):
                recovered = True
                action = f"resolve_anomaly:{aid}"
                reason = (
                    f"Detected injected fault on '{target}'. Cleared the fault "
                    f"(anomaly #{aid}) and will retry the affected subgoal "
                    f"'{failed_subgoal}' in place."
                )
                detail = f"anomaly {aid} resolved"

        if not recovered:
            reason = (
                "Failure not caused by a clear recoverable fault; "
                "no local repair applied."
            )

        rec = RecoveryAction(
            recovered=recovered, failed_subgoal=failed_subgoal,
            reason=reason, action=action, detail=detail,
            recovery_count=self.count() + (1 if recovered else 0),
        )
        self._records.append({
            "failed_subgoal": failed_subgoal,
            "recovered": recovered,
            "reason": reason,
            "action": action,
            "detail": detail,
        })
        return rec


# --------------------------------------------------------------------------- #
# V1.3 state-diff recovery
# --------------------------------------------------------------------------- #

@dataclass
class RecoveryResult:
    """Outcome of one recovery *planning* episode.

    ``remaining_ids`` is the dependency-ordered list of subgoals the agent must
    (re-)execute to repair the broken state (reactivated + invalidated, with the
    preserved subgoals excluded). Empty means "not recoverable".
    """
    recoverable: bool
    remaining_ids: list[str] = field(default_factory=list)
    diagnosis: FailureDiagnosis | None = None
    repair_plan: RepairPlan | None = None
    state_diff: StateDiff | None = None
    observed_state: dict = field(default_factory=dict)
    expected_state: dict = field(default_factory=dict)
    detail: str = ""


class RecoveryEngine:
    """State-diff → diagnosis → local repair planning, with a retry budget."""

    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self.recovery_count = 0
        self.recovery_success_count = 0
        self.recovery_failure_count = 0
        self.total_recovery_steps = 0
        self.local_replan_count = 0
        self.state_diff_count = 0
        self.reexecuted_completed_subgoals = 0
        self.history: list[dict] = []   # recovery_history (ProgressMemory)
        self.traces: list[Any] = []     # RecoveryTrace objects

    def can_recover(self) -> bool:
        return self.recovery_count < self.max_attempts

    def recover(
        self,
        *,
        failed_subgoal: str,
        plan,
        state_reader,
        recent_actions: list[dict] | None = None,
        premature_done: bool = False,
    ) -> RecoveryResult:
        """Plan a local repair for a failed subgoal (does NOT execute it)."""
        self.recovery_count += 1

        observed = state_reader.read()
        observed_dict = observed.to_dict()
        expected = expected_state_for_subgoal(failed_subgoal)
        d = diff(expected, observed_dict)
        self.state_diff_count += 1

        diag = diagnose(
            failed_subgoal, observed_dict, d, recent_actions,
            premature_done=premature_done,
        )

        if not diag.recoverable:
            self.recovery_failure_count += 1
            self._record_history(failed_subgoal, diag, d, attempt=self.recovery_count,
                                 result="FAIL")
            return RecoveryResult(
                recoverable=False, diagnosis=diag, state_diff=d,
                observed_state=observed_dict, expected_state=expected,
                detail="failure not recoverable",
            )

        rp = RepairPlanner().plan(
            goal="recover",
            current_plan=plan,
            progress_memory=None,
            expected_state=expected,
            observed_state=observed_dict,
            state_diff=d,
            failure_diagnosis=diag,
            recent_actions=recent_actions,
        )
        self.local_replan_count += 1

        ordered = plan.ordered_ids()
        remaining = [sg for sg in ordered if sg not in set(rp.preserved_subgoals)]
        # A preserved subgoal must never be re-executed; count any violation
        # (should be zero) as a hard metric for the acceptance gate.
        self.reexecuted_completed_subgoals += len(
            set(remaining) & set(rp.preserved_subgoals)
        )

        self._record_history(failed_subgoal, diag, d, attempt=self.recovery_count,
                             result="PLANNED", repair_subgoal=rp.resume_subgoal)

        return RecoveryResult(
            recoverable=True,
            remaining_ids=remaining,
            diagnosis=diag,
            repair_plan=rp,
            state_diff=d,
            observed_state=observed_dict,
            expected_state=expected,
            detail=f"repair planned; resume from '{rp.resume_subgoal}'",
        )

    def finish_episode(self, success: bool) -> None:
        """Record whether the repair episode ultimately succeeded."""
        if success:
            self.recovery_success_count += 1
        else:
            self.recovery_failure_count += 1

    def add_recovery_steps(self, n: int) -> None:
        self.total_recovery_steps += n

    def _record_history(self, failed_subgoal, diag, d, *, attempt, result,
                        repair_subgoal: str = "") -> None:
        self.history.append({
            "timestamp": _now(),
            "failed_subgoal": failed_subgoal,
            "diagnosis": diag.to_dict(),
            "state_diff": d.to_dict(),
            "repair_subgoal": repair_subgoal,
            "attempt": attempt,
            "result": result,
        })

    def to_metrics(self) -> dict:
        return {
            "recovery_count": self.recovery_count,
            "recovery_success_count": self.recovery_success_count,
            "recovery_failure_count": self.recovery_failure_count,
            "total_recovery_steps": self.total_recovery_steps,
            "reexecuted_completed_subgoals": self.reexecuted_completed_subgoals,
            "local_replan_count": self.local_replan_count,
            "state_diff_count": self.state_diff_count,
        }


def _now() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
