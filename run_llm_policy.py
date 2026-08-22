"""Run the real-LLM policy (Hosp2MESAgent) end-to-end and capture the result.

Starts an isolated backend + serves the prebuilt Vue dist, then invokes the CLI
in browser mode with ``--agent hosp2mes`` and a configurable policy mode. The
real DeepSeek credentials come from the local, git-ignored ``.env`` (never
committed). Output is printed for the acceptance report.

Usage:
    python run_llm_policy.py [--task MES-DEMO-GUI-001] [--policy llm-strict]
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
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
from app.database import configure_engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="MES-DEMO-GUI-001")
    ap.add_argument("--policy", default="llm-strict")
    ap.add_argument("--agent", default="hosp2mes")
    args = ap.parse_args()

    bp = free_port()
    configure_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'llm.db')}")
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

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{BACKEND}" + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["BACKEND_BASE_URL"] = backend_url
    env["FRONTEND_URL"] = frontend_url
    env["AGENT_ARTIFACTS_ROOT"] = os.path.join(ROOT, "artifacts")

    cmd = [sys.executable, "-m", "hosp2mes.run",
           "--task", args.task, "--env", "browser",
           "--agent", args.agent, "--policy", args.policy,
           "--backend", backend_url, "--frontend", frontend_url,
           "--headless", "true"]
    print(">>", " ".join(cmd), flush=True)
    rc = subprocess.call(cmd, env=env, cwd=ROOT)
    print(f"\nCLI exit code: {rc}", flush=True)

    fe.shutdown()
    srv.should_exit = True
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
