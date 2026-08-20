"""End-to-end evaluation metrics.

Implements the metrics required by the project spec:
  * Task Success (overall)
  * Subgoal Completion Rate
  * End-to-End Success (only when the *final* system state fully verifies)
  * Steps
  * Recovery Count
  * Premature DONE (times the agent claimed completion while state was unmet)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class EvaluationReport:
    task_id: str
    task_success: bool
    end_to_end_success: bool
    subgoal_completion_rate: float
    subgoals_completed: int
    subgoals_total: int
    steps: int
    recovery_count: int
    premature_done: int
    verifier_passed: bool
    verifier_missing: list[str] = field(default_factory=list)
    verifier_observed: dict = field(default_factory=dict)
    mode: str = "hosp2mes"

    def to_dict(self) -> dict:
        return asdict(self)


class Evaluator:
    def evaluate(self, *, task_id: str, memory, trace, verifier_result,
                  recovery_count: int, premature_done: int,
                  mode: str = "hosp2mes") -> EvaluationReport:
        total = len(memory.subgoals) or 1
        completed = len(memory.completed_subgoals)
        rate = round(completed / total, 3)

        vpass = verifier_result.passed
        # End-to-end success requires the live system state to fully verify AND
        # no subgoals left pending/failed.
        e2e = vpass and memory.all_done()
        # Overall task success = end-to-end pass (the strict definition).
        success = e2e

        return EvaluationReport(
            task_id=task_id,
            task_success=success,
            end_to_end_success=e2e,
            subgoal_completion_rate=rate,
            subgoals_completed=completed,
            subgoals_total=total,
            steps=len(trace.steps),
            recovery_count=recovery_count,
            premature_done=premature_done,
            verifier_passed=vpass,
            verifier_missing=list(verifier_result.missing),
            verifier_observed=dict(verifier_result.observed),
            mode=mode,
        )
