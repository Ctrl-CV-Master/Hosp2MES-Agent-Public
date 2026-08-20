"""Structured Progress Memory.

The agent maintains an explicit, inspectable record of task progress instead of
relying solely on the (unbounded) chat history. This is a deliberate design
choice for long-horizon agents: the memory is a small JSON document that can be
rendered in the Agent Monitor and persisted for reproducibility.

It tracks, for every subgoal: whether it is pending / completed / failed, and any
evidence collected when it was verified.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProgressMemory:
    goal: str
    subgoals: list[str] = field(default_factory=list)
    current_subgoal: str = ""
    completed_subgoals: list[str] = field(default_factory=list)
    pending_subgoals: list[str] = field(default_factory=list)
    failed_subgoals: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_plan(cls, goal: str, plan_ids: list[str]) -> "ProgressMemory":
        ids = list(plan_ids)
        # NB: subgoals and pending_subgoals must be *independent* lists. Sharing
        # the same reference would let mark_completed() empty subgoals too.
        return cls(goal=goal, subgoals=ids, pending_subgoals=list(ids))

    def set_current(self, sg: str) -> None:
        self.current_subgoal = sg

    def is_completed(self, sg: str) -> bool:
        return sg in self.completed_subgoals

    def mark_completed(self, sg: str, evidence: dict | None = None) -> None:
        if sg not in self.completed_subgoals:
            self.completed_subgoals.append(sg)
        if sg in self.pending_subgoals:
            self.pending_subgoals.remove(sg)
        if sg in self.failed_subgoals:
            self.failed_subgoals.remove(sg)
        if evidence:
            self.evidence[sg] = evidence

    def mark_failed(self, sg: str, reason: str = "") -> None:
        if sg not in self.failed_subgoals:
            self.failed_subgoals.append(sg)
        if sg in self.pending_subgoals:
            self.pending_subgoals.remove(sg)
        if reason:
            self.evidence.setdefault(sg, {})
            self.evidence[sg]["failure_reason"] = reason

    def all_done(self) -> bool:
        return (
            not self.pending_subgoals
            and not self.failed_subgoals
            and len(self.completed_subgoals) == len(self.subgoals)
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["all_done"] = self.all_done()
        return d
