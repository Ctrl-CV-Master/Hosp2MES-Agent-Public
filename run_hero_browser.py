"""Run the browser Hero task (MES-DEMO-003) end-to-end and report the honest result.

Starts backend + frontend proxy, invokes the CLI in browser mode, captures the
final report and prints a summary suitable for DEVELOPMENT_STATUS.md.
"""
from __future__ import annotations

import json
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
            if httpx.get(url, timeout=2).status_code < 500: return
        except Exception: pass
        time.sleep(0.3)
    raise RuntimeError(f"service did not start: {url}")


def main() -> int:
    bp = free_port()
    configure_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'hero.db')}")
    init_db()
    db = dbmod.SessionLocal(); seed(db); db.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=bp, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    backend_url = f"http://127.0.0.1:{bp}"
    wait_http(backend_url + "/health")

    fp = free_port()
    frontend_dist = os.path.join(ROOT, "frontend", "dist")
    if not os.path.isdir(frontend_dist):
        print("[error] frontend/dist not found; run `vite build` first", file=sys.stderr)
        srv.should_exit = True
        return 2
    fe = start_frontend_server(frontend_dist, backend_url, fp)
    frontend_url = fe.url
    wait_http(frontend_url)

    artifacts_root = os.path.join(ROOT, "artifacts")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{BACKEND}" + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["FRONTEND_URL"] = frontend_url
    env["BACKEND_BASE_URL"] = backend_url
    env["AGENT_ARTIFACTS_ROOT"] = artifacts_root

    cmd = [sys.executable, "-m", "hosp2mes.run",
           "--task", "MES-DEMO-003", "--env", "browser",
           "--headless", "true"]
    print(">>", " ".join(cmd), flush=True)
    rc = subprocess.call(cmd, env=env, cwd=ROOT)
    print(f"\nCLI exit code: {rc}", flush=True)

    fe.shutdown()
    srv.should_exit = True
    return rc


if __name__ == "__main__":
    raise SystemExit(main())