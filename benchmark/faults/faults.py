"""Independent fault injection for recovery demos (V1.3).

The fault injector is a *test-harness* component — never part of the agent, and
the agent is never told the fault id / type / trigger. The agent only ever
observes the GUI result and the read-only business state.

Fault effects are realized through callbacks supplied by the harness (e.g. a
direct DB discard for ``discard_state_change``), keeping the fault layer fully
decoupled from both the agent's decision logic and the backend business logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class FaultSpec:
    fault_id: str
    trigger: str = "after_subgoal_completed"  # when to fire
    target_subgoal: str = ""                  # subgoal whose completion triggers it
    effect: str = "discard_state_change"      # "discard_state_change" | "save_failure"
    target: str = "bom"                       # affected resource ("bom" | "order" | "execution")
    once: bool = True


class FaultInjector:
    """Fires a fault deterministically via a subgoal-completion observer.

    ``discard_fn(target)`` discards a just-created resource (e.g. deletes the
    BOM row), ``inject_anomaly_fn(target)`` injects a backend anomaly.
    """

    def __init__(self,
                 discard_fn: Callable[[str], Any] | None = None,
                 inject_anomaly_fn: Callable[[str], Any] | None = None):
        self._discard = discard_fn
        self._inject_anomaly = inject_anomaly_fn
        self.spec: FaultSpec | None = None
        self.triggered = False
        self.history: list[dict] = []

    def arm(self, spec: FaultSpec) -> "FaultInjector":
        self.spec = spec
        self.triggered = False
        self.history = []
        return self

    def on_subgoal_completed(self, subgoal_id: str) -> None:
        """Observer entrypoint (registered on the agent by the harness)."""
        spec = self.spec
        if spec is None or (spec.once and self.triggered):
            return
        if spec.trigger == "after_subgoal_completed" and subgoal_id == spec.target_subgoal:
            self.fire()

    def fire(self) -> None:
        spec = self.spec
        if spec is None:
            return
        self.triggered = True
        if spec.effect == "discard_state_change" and self._discard is not None:
            self._discard(spec.target)
        elif spec.effect == "save_failure" and self._inject_anomaly is not None:
            self._inject_anomaly(spec.target)
        self.history.append({
            "fault_id": spec.fault_id,
            "trigger": spec.trigger,
            "target_subgoal": spec.target_subgoal,
            "effect": spec.effect,
            "target": spec.target,
            "triggered": True,
        })
