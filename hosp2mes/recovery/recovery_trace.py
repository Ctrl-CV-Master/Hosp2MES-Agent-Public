"""Recovery trace (V1.3).

Each recovery episode produces one ``recovery-XXX.json`` under
``artifacts/runs/<run_id>/recovery/`` recording the trigger step, failed
subgoal, expected/observed state, state diff, diagnosis, repair plan, the
repair steps taken and the verification result. No private chain-of-thought is
stored.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RecoveryTrace:
    trigger_step: int = 0
    failed_subgoal: str = ""
    expected_state: dict = field(default_factory=dict)
    observed_state: dict = field(default_factory=dict)
    state_diff: dict = field(default_factory=dict)
    diagnosis: dict = field(default_factory=dict)
    repair_plan: dict = field(default_factory=dict)
    repair_steps: list[dict] = field(default_factory=list)
    verification_result: dict = field(default_factory=dict)
    resume_subgoal: str = ""
    # Recovery-episode boundaries (V1.3.1): only the GUI steps between
    # repair_start_step and repair_end_step count as recovery steps.
    repair_start_step: int = 0
    repair_end_step: int = 0
    repair_step_count: int = 0
    repair_success_condition: dict = field(default_factory=dict)
    repair_verified: bool = False
    resume_step: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def write_recovery_trace(run_dir: str, trace: RecoveryTrace, index: int) -> str:
    """Write one recovery trace to ``<run_dir>/recovery/recovery-<n>.json``."""
    out_dir = os.path.join(run_dir, "recovery")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"recovery-{index:03d}.json")
    import json

    with open(path, "w", encoding="utf-8") as f:
        json.dump(trace.to_dict(), f, ensure_ascii=False, indent=2)
    return path
