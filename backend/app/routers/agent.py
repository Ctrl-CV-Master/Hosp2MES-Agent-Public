"""Agent run persistence for the live Monitor and evaluation."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AgentRun

router = APIRouter(prefix="/api/agent", tags=["agent"])


class RunCreate(BaseModel):
    task_id: str
    goal: str = ""
    mode: str = "hosp2mes"


class StepUpdate(BaseModel):
    current_subgoal: str = ""
    step_count: int = 0
    recovery_count: int = 0
    status: str = "RUNNING"
    trace_step: dict | None = None


class FinishUpdate(BaseModel):
    status: str = "DONE"
    success: bool | None = None
    final_verification: str = ""
    step_count: int = 0
    recovery_count: int = 0


@router.get("/runs", response_model=list[dict])
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(AgentRun).order_by(AgentRun.id.desc()).all()
    return [r.to_dict() for r in runs]


@router.post("/runs", response_model=dict, status_code=201)
def create_run(payload: RunCreate, db: Session = Depends(get_db)):
    run = AgentRun(task_id=payload.task_id, goal=payload.goal, mode=payload.mode)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run.to_dict()


@router.get("/runs/{run_id}", response_model=dict)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run.to_dict()


@router.post("/runs/{run_id}/step", response_model=dict)
def append_step(run_id: int, payload: StepUpdate, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    run.current_subgoal = payload.current_subgoal
    run.step_count = payload.step_count
    run.recovery_count = payload.recovery_count
    run.status = payload.status
    if payload.trace_step:
        trace = json.loads(run.trace or "[]")
        trace.append(payload.trace_step)
        run.trace = json.dumps(trace, ensure_ascii=False)
    db.commit()
    db.refresh(run)
    return run.to_dict()


@router.post("/runs/{run_id}/finish", response_model=dict)
def finish_run(run_id: int, payload: FinishUpdate, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    run.status = payload.status
    run.success = payload.success
    run.final_verification = payload.final_verification
    run.step_count = payload.step_count
    run.recovery_count = payload.recovery_count
    db.commit()
    db.refresh(run)
    return run.to_dict()


@router.delete("/runs/{run_id}", response_model=dict)
def delete_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    db.delete(run)
    db.commit()
    return {"detail": "deleted"}


class LaunchRequest(BaseModel):
    task_id: str
    mode: str = "hosp2mes"
    provider: str = "mock"
    backend_url: str = ""  # where the agent should operate / publish traces


@router.post("/runs/launch", response_model=dict, status_code=202)
def launch_run(payload: LaunchRequest, db: Session = Depends(get_db)):
    """Launch an agent run as a background task and stream its trace to this
    same backend so the live Monitor can display it. The agent operates the
    running Mock MES over its REST API (loopback)."""
    import os
    import sys
    import threading

    # Ensure the hosp2mes agent package is importable from the backend process.
    # agent.py lives at <repo>/backend/app/routers/agent.py, so four dirname
    # calls from the file land on the repository root (parent of backend/).
    _here = os.path.abspath(__file__)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_here))))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    run = AgentRun(task_id=payload.task_id, goal=payload.task_id, mode=payload.mode, status="RUNNING")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    public_url = (payload.backend_url
                   or os.environ.get("BACKEND_PUBLIC_URL", "http://127.0.0.1:8000")).rstrip("/")

    def _worker() -> None:
        try:
            from hosp2mes.agent.agent import Agent, TaskLoader
            from hosp2mes.config import Config
            from hosp2mes.observation.api_env import ApiEnv

            task_path = os.path.join(repo_root, "benchmark", "tasks", f"{payload.task_id}.yaml")
            task = TaskLoader.from_yaml(task_path)
            cfg = Config()
            cfg.agent_mode = payload.mode
            cfg.llm_provider = payload.provider
            cfg.publish_url = public_url
            cfg.backend_base_url = public_url
            env = ApiEnv(base_url=public_url)
            agent = Agent(cfg, env, task)
            agent.trace.run_id = run_id  # reuse the pre-created run record
            agent.run()
        except Exception as exc:  # surface failures into the run record
            try:
                with db.session_scope() if hasattr(db, "session_scope") else None:
                    pass
            except Exception:
                pass
            # Best-effort: append a failure step via the runs API.
            try:
                import httpx

                with httpx.Client(timeout=10) as c:
                    c.post(f"{public_url}/api/agent/runs/{run_id}/step",
                           json={"current_subgoal": "error", "step_count": 0,
                                 "trace_step": {"step": 0, "subgoal": "error",
                                                "observation": "launch", "reasoning_summary": "run failed",
                                                "action": "error", "result": f"ERROR: {exc}",
                                                "evidence": {}, "memory_state": {}, "recovery_count": 0,
                                                "timestamp": ""}})
                    c.post(f"{public_url}/api/agent/runs/{run_id}/finish",
                           json={"status": "DONE", "success": False,
                                 "final_verification": f"launch error: {exc}",
                                 "step_count": 0, "recovery_count": 0})
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()
    return run.to_dict()
