"""Local Recovery Manager.

When a subgoal fails the agent does NOT restart the whole task. Instead the
``RecoveryManager`` records the failure and, when the failure is caused by an
*injected anomaly* (the mechanism used to demonstrate Agent failure/recovery),
it clears the fault so the affected subgoal can be retried in place. Only the
affected state is repaired — this is "local recovery", not a full restart.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hosp2mes.observation.api_env import ApiEnv, ActionResult


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
    def __init__(self) -> None:
        self._records: list[dict] = []

    def count(self) -> int:
        return len(self._records)

    def records(self) -> list[dict]:
        return list(self._records)

    def attempt(self, failed_subgoal: str,
                last_result: ActionResult | None,
                env: ApiEnv) -> RecoveryAction:
        """Try to repair the failing subgoal locally.

        Returns ``recovered=True`` when a repair was applied and the subgoal can
        be retried. Otherwise the failure is recorded as non-recoverable.
        """
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
