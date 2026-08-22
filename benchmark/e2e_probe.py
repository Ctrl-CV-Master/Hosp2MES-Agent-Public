"""End-to-end benchmark runner for Hosp2MES-Agent.

Each benchmark task is executed by the agent against a *fresh* Mock MES
backend (isolated database), exactly as a real benchmark resets the
environment between tasks. This makes runs reproducible and avoids any
cross-task state contamination.

The Hero task (MES-DEMO-003) injects a BOM save-failure anomaly so the run
also exercises the local Recovery Manager.

Usage:
    python benchmark/e2e_probe.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
for p in (BACKEND, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import httpx
import uvicorn

from app.main import app
import app.database as _dbmod
from app.database import configure_engine, init_db
from app.seed import seed
from hosp2mes.config import Config
from hosp2mes.agent.agent import Agent, TaskLoader
from hosp2mes.observation.api_env import ApiEnv

TASKS = ["MES-DEMO-001", "MES-DEMO-002", "MES-DEMO-003"]


def _run_task(tid: str, port: int) -> dict:
    """Start a fresh backend, run the agent on one task, return the report."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "mes.db")
    # Rebind the engine to an isolated database so tasks never share state.
    configure_engine(f"sqlite:///{db_path}")

    init_db()
    db = _dbmod.SessionLocal()  # attribute access -> picks up configured engine
    seed(db)
    db.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(80):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health").json().get("status") == "ok":
                break
        except Exception:
            pass
        time.sleep(0.1)

    cfg = Config()
    cfg.backend_base_url = f"http://127.0.0.1:{port}"
    cfg.agent_mode = "hosp2mes"
    cfg.llm_provider = "mock"

    task = TaskLoader.from_yaml(os.path.join(ROOT, "benchmark", "tasks", f"{tid}.yaml"))
    env = ApiEnv(base_url=cfg.backend_base_url)
    agent = Agent(cfg, env, task)
    report, trace, memory = agent.run()

    server.should_exit = True
    return report.to_dict()


def main() -> int:
    all_pass = True
    for i, tid in enumerate(TASKS):
        port = 8200 + i
        rep = _run_task(tid, port)
        ok = rep["task_success"]
        all_pass = all_pass and ok
        print(f"\n=== {tid} ===")
        print("success:", ok,
              "| steps:", rep["steps"],
              "| recovery:", rep["recovery_count"],
              "| subgoal_rate:", rep["subgoal_completion_rate"],
              "| verifier_passed:", rep["verifier_passed"])
        if not ok:
            print("  missing:", rep["verifier_missing"],
                  "| failed_subgoals:", memory_failed(rep))
    print("\n" + ("ALL TASKS PASSED" if all_pass else "SOME TASKS FAILED"))
    return 0 if all_pass else 1


def memory_failed(rep: dict) -> list:
    # failure detail is not in the report; placeholder kept simple
    return []


if __name__ == "__main__":
    raise SystemExit(main())
