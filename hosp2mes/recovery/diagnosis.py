"""Failure diagnosis (V1.3).

Given a failed subgoal and the observed business state (from the independent
read-only verifier), classify the failure into a small, *generic* category and
identify the affected state paths. No category or rule is specific to a demo
task or product.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hosp2mes.state.business_state import BusinessState

# Generic failure categories (used across all tasks).
MISSING_PREREQUISITE = "MISSING_PREREQUISITE"
STATE_MISMATCH = "STATE_MISMATCH"
ACTION_FAILED = "ACTION_FAILED"
UI_TIMING = "UI_TIMING"
NAVIGATION_ERROR = "NAVIGATION_ERROR"
FORM_VALIDATION = "FORM_VALIDATION"
PREMATURE_DONE = "PREMATURE_DONE"
TRANSIENT_BACKEND = "TRANSIENT_BACKEND"
UNKNOWN = "UNKNOWN"

_RECOVERABLE = {
    MISSING_PREREQUISITE, STATE_MISMATCH, ACTION_FAILED, UI_TIMING,
    NAVIGATION_ERROR, FORM_VALIDATION, PREMATURE_DONE, TRANSIENT_BACKEND,
}

# Which canonical state paths are prerequisites for each subgoal (generic
# dependency graph, not task-specific). A missing prerequisite is the classic
# "downstream subgoal ran while an upstream object was absent" failure.
SUBGOAL_PREREQUISITE_PATHS: dict[str, list[str]] = {
    "create_material": [],
    "create_bom": ["material.exists"],
    "create_production_order": ["bom.exists"],
    "execute_production": ["production_order.exists"],
}


@dataclass
class FailureDiagnosis:
    failure_category: str
    failed_subgoal: str
    affected_state: list[str] = field(default_factory=list)
    root_cause_summary: str = ""
    recoverable: bool = True

    def to_dict(self) -> dict:
        return {
            "failure_category": self.failure_category,
            "failed_subgoal": self.failed_subgoal,
            "affected_state": list(self.affected_state),
            "root_cause_summary": self.root_cause_summary,
            "recoverable": self.recoverable,
        }


def diagnose(
    failed_subgoal: str,
    observed_state: dict | None = None,
    state_diff: Any = None,
    recent_actions: list[dict] | None = None,
    *,
    premature_done: bool = False,
) -> FailureDiagnosis:
    """Classify a subgoal failure from the *observed* state (never memory)."""
    observed_state = observed_state or {}
    observed_flat = BusinessState.flatten(observed_state)
    recent_actions = recent_actions or []

    category = UNKNOWN
    affected: list[str] = []
    summary = ""

    prereqs = SUBGOAL_PREREQUISITE_PATHS.get(failed_subgoal, [])
    missing_prereq = [p for p in prereqs if not observed_flat.get(p)]

    if missing_prereq:
        category = MISSING_PREREQUISITE
        affected = missing_prereq
        summary = (
            f"Expected prerequisite state {missing_prereq} is absent before "
            f"'{failed_subgoal}'."
        )
    elif premature_done:
        category = PREMATURE_DONE
        summary = (
            "Policy reported the subgoal as done while the live business state "
            "was still incomplete."
        )
    elif state_diff is not None and getattr(state_diff, "mismatched", None):
        category = STATE_MISMATCH
        affected = list(state_diff.mismatched)
        summary = "Observed state conflicts with the expected state."
    elif _last_action_failed(recent_actions):
        category = ACTION_FAILED
        summary = "The most recent GUI action failed (or produced no state change)."
    elif state_diff is not None and getattr(state_diff, "missing", None):
        category = STATE_MISMATCH
        affected = list(state_diff.missing)
        summary = "Expected state conditions are not yet observed."
    else:
        category = UNKNOWN
        summary = "No clear, generic cause identified."

    return FailureDiagnosis(
        failure_category=category,
        failed_subgoal=failed_subgoal,
        affected_state=affected,
        root_cause_summary=summary,
        recoverable=category in _RECOVERABLE,
    )


def _last_action_failed(recent: list[dict]) -> bool:
    if not recent:
        return False
    last = recent[-1]
    result = str(last.get("result", "") or "")
    return result.startswith("FAIL") or result == ""
