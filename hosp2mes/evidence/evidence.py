"""Per-run GUI evidence recorder.

Every GUI action is persisted as a small, *public* record under
``artifacts/runs/<run_id>/`` so a run is independently reproducible and auditable.
We store only public action rationales and observation summaries — never private
model chain-of-thought.

Layout produced::

    artifacts/runs/<run_id>/
        summary.json           # run metadata + final verification + honest status
        steps.json             # ordered list of per-step evidence
        <seq>-<label>.png      # before/after screenshots

Each step record contains: step, subgoal, url, observation_summary,
interactive_elements_summary, action, action_target, action_result,
screenshot_before, screenshot_after, state_changed, timestamp.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class StepEvidence:
    step: int
    subgoal: str
    url: str
    observation_summary: str
    interactive_elements_summary: str
    action: str
    action_target: str
    action_result: str
    screenshot_before: str | None = None
    screenshot_after: str | None = None
    state_changed: bool = False
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class EvidenceWriter:
    def __init__(self, run_id: str, artifacts_root: str | None = None):
        self.run_id = run_id
        self.artifacts_root = artifacts_root or _default_artifacts_root()
        self.run_dir = os.path.join(self.artifacts_root, "runs", run_id)
        self._steps: list[StepEvidence] = []
        self._meta: dict[str, Any] = {"run_id": run_id, "started_at": _now()}

    def start(self, task_id: str, instruction: str, mode: str = "browser") -> None:
        self._meta.update({
            "task_id": task_id, "instruction": instruction, "mode": mode,
            "started_at": _now(),
        })

    def record(self, *, step: int, subgoal: str, url: str,
               observation_summary: str, interactive_elements_summary: str,
               action: str, action_target: str, action_result: str,
               screenshot_before: str | None, screenshot_after: str | None,
               state_changed: bool) -> StepEvidence:
        ev = StepEvidence(
            step=step, subgoal=subgoal, url=url,
            observation_summary=observation_summary,
            interactive_elements_summary=interactive_elements_summary,
            action=action, action_target=action_target,
            action_result=action_result,
            screenshot_before=screenshot_before, screenshot_after=screenshot_after,
            state_changed=state_changed, timestamp=_now(),
        )
        self._steps.append(ev)
        return ev

    def finish(self, *, success: bool, final_state: dict, detail: str,
               gui_steps: int, failed_subgoal: str = "", failure_reason: str = "",
               steps_reached: int = 0) -> None:
        self._meta.update({
            "finished_at": _now(),
            "success": success,
            "final_state": final_state,
            "detail": detail,
            "gui_steps": gui_steps,
            "failed_subgoal": failed_subgoal,
            "failure_reason": failure_reason,
            "steps_reached": steps_reached,
        })

    def flush(self) -> str:
        os.makedirs(self.run_dir, exist_ok=True)
        with open(os.path.join(self.run_dir, "steps.json"), "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self._steps], f, ensure_ascii=False, indent=2)
        with open(os.path.join(self.run_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)
        return self.run_dir

    @property
    def steps(self) -> list[StepEvidence]:
        return self._steps


def _default_artifacts_root() -> str:
    # <repo>/artifacts
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "artifacts",
    )


def make_run_id(task_id: str) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{task_id}-{stamp}"
