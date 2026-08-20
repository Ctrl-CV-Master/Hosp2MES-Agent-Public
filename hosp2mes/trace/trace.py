"""Agent Trace recorder.

Every action the agent takes is recorded as a small, *public* structured entry.
We deliberately store only short reasoning summaries / action rationales — never
the raw model chain-of-thought. The trace is what the Agent Monitor renders and
what makes a run reproducible for evaluation.

When a ``publish_url`` (a running Mock MES backend) is supplied, each step and
the final result are streamed to the backend's ``/api/agent/runs`` endpoint so
the live Monitor can show the agent working in real time.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field


@dataclass
class TraceStep:
    step: int
    goal: str
    subgoal: str
    observation: str
    reasoning_summary: str
    action: str
    result: str
    evidence: dict = field(default_factory=dict)
    memory_state: dict = field(default_factory=dict)
    recovery_count: int = 0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class TraceRecorder:
    def __init__(self, publish_url: str = "", mode: str = "hosp2mes",
                 run_id: str | None = None):
        self.publish_url = (publish_url or "").rstrip("/")
        self.mode = mode
        self.run_id = run_id
        self.steps: list[TraceStep] = []
        self.started_at: str = ""
        self.finished: bool = False
        self.final_success: bool | None = None
        self.final_detail: str = ""
        self.final_steps: int = 0
        self.final_recovery: int = 0

    # ---- run lifecycle ---------------------------------------------------
    def start_run(self, task_id: str, instruction: str) -> None:
        self.run_id = self.run_id or task_id
        self.started_at = _now()
        # Only auto-create a run when we were not handed a pre-existing run id
        # (e.g. the backend launch endpoint creates the record first).
        if self.publish_url and self.run_id == task_id:
            self._ensure_run(task_id, instruction)

    def record(self, *, goal: str, subgoal: str, observation, reasoning_summary: str,
               action: str, result: str, evidence: dict | None = None,
               memory_state: dict | None = None, recovery_count: int = 0) -> TraceStep:
        step = TraceStep(
            step=len(self.steps) + 1,
            goal=goal, subgoal=subgoal,
            observation=str(observation),
            reasoning_summary=reasoning_summary,
            action=action, result=result,
            evidence=evidence or {}, memory_state=memory_state or {},
            recovery_count=recovery_count,
            timestamp=_now(),
        )
        self.steps.append(step)
        if self.publish_url and self.run_id is not None:
            self._publish_step(step)
        return step

    def finish_run(self, success: bool, detail: str,
                   step_count: int, recovery_count: int) -> None:
        self.finished = True
        self.final_success = success
        self.final_detail = detail
        self.final_steps = step_count
        self.final_recovery = recovery_count
        if self.publish_url and self.run_id is not None:
            self._publish_finish(success, detail, step_count, recovery_count)

    # ---- persistence -----------------------------------------------------
    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished": self.finished,
            "final_success": self.final_success,
            "final_detail": self.final_detail,
            "final_steps": self.final_steps,
            "final_recovery": self.final_recovery,
            "steps": [s.to_dict() for s in self.steps],
        }

    # ---- live publishing -------------------------------------------------
    def _ensure_run(self, task_id: str, instruction: str) -> None:
        import httpx

        try:
            with httpx.Client(timeout=10) as c:
                r = c.post(f"{self.publish_url}/api/agent/runs", json={
                    "task_id": task_id, "goal": instruction, "mode": self.mode,
                })
                if r.status_code < 400:
                    self.run_id = r.json().get("id")
        except Exception:
            pass

    def _publish_step(self, step: TraceStep) -> None:
        import httpx

        try:
            with httpx.Client(timeout=10) as c:
                c.post(
                    f"{self.publish_url}/api/agent/runs/{self.run_id}/step",
                    json={"current_subgoal": step.subgoal,
                          "step_count": step.step,
                          "trace_step": step.to_dict()},
                )
        except Exception:
            pass

    def _publish_finish(self, success: bool, detail: str,
                        step_count: int, recovery_count: int) -> None:
        import httpx

        try:
            with httpx.Client(timeout=10) as c:
                c.post(
                    f"{self.publish_url}/api/agent/runs/{self.run_id}/finish",
                    json={"success": success, "final_verification": detail,
                          "steps": step_count, "recovery_count": recovery_count},
                )
        except Exception:
            pass


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
