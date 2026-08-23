"""Dependency-aware local repair planning (V1.3).

The repair planner is the heart of "local recovery, not a full restart". Given
the current plan (with dependencies), the progress memory and the *observed*
business state, it decides:

* which subgoals to **preserve** (state still agrees — do NOT re-run them),
* which to **reactivate** (the earliest broken subgoal — re-execute it),
* which to **invalidate** (downstream subgoals whose completion claims are now
  suspect — re-verify, and re-execute only if needed),
* where to **resume**.

The result is expressed against the subgoal *dependency graph*, so it generalizes
to any plan shape — never against a specific task id or product.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hosp2mes.planner.planner import Plan, Subgoal
from hosp2mes.state.business_state import expected_state_for_subgoal
from hosp2mes.state.state_diff import diff


@dataclass
class RepairPlan:
    repair_goal: str = ""
    affected_subgoal: str = ""
    preserved_subgoals: list[str] = field(default_factory=list)
    reactivated_subgoals: list[str] = field(default_factory=list)
    invalidated_subgoals: list[str] = field(default_factory=list)
    resume_subgoal: str = ""
    success_condition: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "repair_goal": self.repair_goal,
            "affected_subgoal": self.affected_subgoal,
            "preserved_subgoals": list(self.preserved_subgoals),
            "reactivated_subgoals": list(self.reactivated_subgoals),
            "invalidated_subgoals": list(self.invalidated_subgoals),
            "resume_subgoal": self.resume_subgoal,
            "success_condition": dict(self.success_condition),
        }

    def dependency_view(self) -> dict:
        """The section-六 style view (preserve / reactivate / invalidate / resume_from)."""
        return {
            "preserve": list(self.preserved_subgoals),
            "reactivate": list(self.reactivated_subgoals),
            "invalidate": list(self.invalidated_subgoals),
            "resume_from": self.resume_subgoal,
        }


class RepairPlanner:
    """Deterministic dependency-aware repair planner (LLM path optional later)."""

    def __init__(self, config=None):
        self.config = config

    def plan(
        self,
        *,
        goal: str,
        current_plan: Plan,
        progress_memory,
        expected_state: dict,
        observed_state: dict,
        state_diff,
        failure_diagnosis,
        recent_actions: list[dict] | None = None,
    ) -> RepairPlan:
        """Decide a local repair from the dependency graph + observed state."""
        subgoals = current_plan.subgoals
        by_id = {s.id: s for s in subgoals}

        # 1. Find the earliest (topological) subgoal whose success condition is
        #    not met by the observed state. This is the broken link.
        affected = self._first_unsatisfied(subgoals, observed_state)

        # 2. Preserve every subgoal that is *before* the affected one and whose
        #    state still agrees (they are truly complete).
        ordered = current_plan.ordered_ids()
        affected_idx = ordered.index(affected) if affected in ordered else len(ordered)

        preserved = []
        for sg_id in ordered[:affected_idx]:
            if self._satisfied(sg_id, observed_state):
                preserved.append(sg_id)

        # 3. Invalidate the affected subgoal and every subgoal that (transitively)
        #    depends on it — their completion claims are now suspect.
        invalidated = [affected] + sorted(_dependents(affected, by_id))

        # 4. Reactivate = the affected subgoal (plus any not-satisfied upstream,
        #    in case several links broke at once).
        reactivated = [affected]
        for sg_id in ordered[:affected_idx]:
            if sg_id not in preserved and not self._satisfied(sg_id, observed_state):
                reactivated.append(sg_id)

        # 5. Success condition to aim for = the affected subgoal's expected state.
        success_condition = expected_state_for_subgoal(affected) if affected else {}

        return RepairPlan(
            repair_goal=self._repair_goal(affected, state_diff, failure_diagnosis),
            affected_subgoal=affected,
            preserved_subgoals=preserved,
            reactivated_subgoals=reactivated,
            invalidated_subgoals=invalidated,
            resume_subgoal=affected,
            success_condition=success_condition,
        )

    # ---- helpers ---------------------------------------------------------
    @staticmethod
    def _satisfied(sg_id: str, observed_state: dict) -> bool:
        expected = expected_state_for_subgoal(sg_id)
        if not expected:
            return True
        return diff(expected, observed_state).is_clean

    @staticmethod
    def _first_unsatisfied(subgoals: list[Subgoal], observed_state: dict) -> str:
        # Reuse the plan's topological order.
        plan = Plan(goal="", subgoals=subgoals)
        for sg_id in plan.ordered_ids():
            if not RepairPlanner._satisfied(sg_id, observed_state):
                return sg_id
        return ""

    @staticmethod
    def _repair_goal(affected: str, state_diff, diagnosis) -> str:
        if affected:
            return f"Restore missing state for subgoal '{affected}'"
        if diagnosis is not None:
            return f"Repair {diagnosis.failure_category}"
        return "Restore missing business state"


def _dependents(sg_id: str, by_id: dict[str, Subgoal]) -> set[str]:
    """All subgoal ids that (transitively) depend on ``sg_id``."""
    result: set[str] = set()
    for other in by_id.values():
        if sg_id in other.dependencies:
            result.add(other.id)
            result |= _dependents(other.id, by_id)
    return result
