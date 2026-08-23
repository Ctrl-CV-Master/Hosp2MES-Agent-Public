"""Run the real-LLM Recovery Hero (MES-DEMO-RECOVERY-001) end-to-end.

Starts an isolated backend + serves the prebuilt Vue dist, injects a fault via
the *test harness* (``benchmark/faults``), then runs ``Hosp2MESAgent`` in browser
mode with ``--policy llm-strict``. The fault is injected through the agent's
generic subgoal-completion observer — the agent's decision logic, prompt and
observation never see the fault id / type / trigger.

The real DeepSeek credentials come from the local, git-ignored ``.env``.

Usage:
    python run_llm_recovery.py [--policy llm-strict] [--headless true]
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
for p in (BACKEND, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import httpx  # noqa: E402
import uvicorn  # noqa: E402

import app.database as dbmod  # noqa: E402
import app.models as models  # noqa: E402
from app.database import configure_engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
from benchmark.faults.faults import FaultInjector, FaultSpec  # noqa: E402
from hosp2mes.agent.agent import TaskLoader  # noqa: E402
from hosp2mes.agents.hosp2mes_agent import Hosp2MESAgent  # noqa: E402
from hosp2mes.config import Config  # noqa: E402
from hosp2mes.observation.browser_env import BrowserEnv  # noqa: E402
from tests._frontend_server import start_frontend_server  # noqa: E402


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def wait_http(url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"service did not start: {url}")


def make_discard_bom_fn(bom_code: str):
    """Return a fault effect that discards (deletes) a just-created BOM."""

    def discard(target: str):
        db = dbmod.SessionLocal()
        try:
            bom = db.query(models.BOM).filter(models.BOM.bom_code == bom_code).first()
            if bom is not None:
                db.delete(bom)
                db.commit()
                print(f"[fault] discarded BOM {bom_code} (effect=discard_state_change)", flush=True)
        finally:
            db.close()

    return discard


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="MES-DEMO-RECOVERY-001")
    ap.add_argument("--policy", default="llm-strict")
    ap.add_argument("--headless", default="true")
    args = ap.parse_args()

    bp = free_port()
    configure_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'recovery.db')}")
    init_db()
    db = dbmod.SessionLocal(); seed(db); db.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=bp, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    backend_url = f"http://127.0.0.1:{bp}"
    wait_http(backend_url + "/health")

    frontend_dist = os.path.join(ROOT, "frontend", "dist")
    assert os.path.isdir(frontend_dist), "frontend/dist not found; build it first"
    fe = start_frontend_server(frontend_dist, backend_url, free_port())
    frontend_url = fe.url
    wait_http(frontend_url)

    config = Config.load()
    config.backend_base_url = backend_url
    config.frontend_url = frontend_url
    config.headless = args.headless.strip().lower() in ("1", "true", "yes", "on")
    config.policy = args.policy
    config.artifacts_root = os.path.join(ROOT, "artifacts")
    if config.policy in ("llm", "llm-strict"):
        config.llm_provider = "deepseek"
        if not config.llm_api_key:
            print("[error] llm-strict needs a DeepSeek API key in .env / OPENAI_API_KEY", file=sys.stderr)
            fe.shutdown(); srv.should_exit = True
            return 3

    task = TaskLoader.from_yaml(os.path.join(ROOT, "benchmark", "tasks", f"{args.task}.yaml"))

    env = BrowserEnv(base_url=frontend_url, backend_url=backend_url,
                     headless=config.headless, artifacts_dir=None)
    agent = Hosp2MESAgent(config, env, task)

    # Fault injection (harness-side, independent of the agent's decision logic).
    fault = FaultInjector(discard_fn=make_discard_bom_fn(task.bom_code))
    fault.arm(FaultSpec(
        fault_id="FAULT-BOM-001",
        trigger="after_subgoal_completed",
        target_subgoal="create_bom",
        effect="discard_state_change",
        target="bom",
        once=True,
    ))
    agent.on_subgoal_completed.append(fault.on_subgoal_completed)

    report, trace, memory = agent.run()

    print("\n================ Recovery Hero Result ================", flush=True)
    print(f"run_id              = {agent.run_id}")
    print(f"task_success        = {report.task_success}")
    print(f"final_state_verified= {report.verifier_passed}")
    print(f"verifier_observed   = {report.verifier_observed}")
    print(f"gui_steps           = {agent.gui_steps}")
    print(f"total_llm_calls     = {agent.total_llm_calls}")
    print(f"fallback_count      = {agent.fallback_count}")
    print(f"premature_done      = {report.premature_done}")
    print(f"FAULT_TRIGGERED     = {fault.triggered}")
    print(f"fault_history       = {fault.history}")
    print(f"recovery_metrics    = {agent.recovery.to_metrics()}")
    print(f"failed_subgoal      = {agent.failed_subgoal or '-'}")
    print(f"failure_reason      = {agent.failure_reason or '-'}")
    print(f"evidence_dir        = artifacts/runs/{agent.run_id}")
    print("=====================================================", flush=True)

    fe.shutdown()
    srv.should_exit = True
    return 0 if report.task_success else 2


if __name__ == "__main__":
    raise SystemExit(main())
