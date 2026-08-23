"""Shared pytest fixtures for Hosp2MES-Agent-Public.

Tests never touch the developer's live ``mes_demo.db``. Every fixture rebinds
the backend engine to a throw-away SQLite file so tests are isolated and
reproducible.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
for p in (BACKEND, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import uvicorn  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.database as dbmod  # noqa: E402
from app.database import configure_engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _fresh_db() -> str:
    tmp = tempfile.mkdtemp(prefix="hosp2mes-test-")
    return f"sqlite:///{os.path.join(tmp, 'test.db')}"


@pytest.fixture
def client():
    """FastAPI TestClient backed by a fresh, seeded database."""
    configure_engine(_fresh_db())
    init_db()
    db = dbmod.SessionLocal()  # live module attribute (post-configure_engine)
    try:
        seed(db)
    finally:
        db.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def live_server():
    """A real uvicorn backend on an isolated DB, for end-to-end agent runs.

    Seeds the database *in this process* before starting the server (the same
    pattern the benchmark harness uses) so the agent always sees a clean,
    populated Mock MES.
    """
    port = _free_port()
    configure_engine(_fresh_db())
    init_db()
    db = dbmod.SessionLocal()  # live module attribute (post-configure_engine)
    try:
        seed(db)
    finally:
        db.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    ok = False
    for _ in range(100):
        try:
            r = __import__("httpx").get(f"{base}/health", timeout=2)
            if r.json().get("status") == "ok":
                ok = True
                break
        except Exception:
            pass
    assert ok, "live backend did not start"
    yield base
    server.should_exit = True


# ---- browser (Playwright) fixtures ----------------------------------------
@pytest.fixture(scope="session")
def playwright_browser():
    """A single shared headless Chromium for browser-mode tests."""
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    # GitHub Actions and other containerized CI may restrict the Chromium
    # sandbox (unprivileged user namespaces). Apply --no-sandbox ONLY in CI;
    # local runs keep the sandbox enabled. This is a test-infrastructure
    # portability fix, not an agent-behaviour change.
    launch_args = ["--no-sandbox"] if os.environ.get("CI") else []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=launch_args)
        yield browser
        browser.close()


@pytest.fixture
def browser_page(playwright_browser):
    """A fresh page (own context) for browser unit tests."""
    ctx = playwright_browser.new_context()
    page = ctx.new_page()
    yield page
    ctx.close()


def _wait_http(url: str, timeout: float = 30.0) -> None:
    import httpx

    deadline = __import__("time").time() + timeout
    while __import__("time").time() < deadline:
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except Exception:
            pass
        __import__("time").sleep(0.3)
    raise RuntimeError(f"service did not start: {url}")


@pytest.fixture(scope="module")
def browser_stack():
    """A real backend (isolated DB) + served prebuilt Vue dist, for GUI E2E.

    Yields ``(frontend_url, backend_url)``. The frontend is served by the
    Python ``FrontendProxyServer`` (no Node subprocess), proxying ``/api`` to
    the backend. Requires ``frontend/dist`` to be built first.
    """
    from tests._frontend_server import start_frontend_server

    backend_port = _free_port()
    configure_engine(_fresh_db())
    init_db()
    db = dbmod.SessionLocal()  # live module attribute (post-configure_engine)
    try:
        seed(db)
    finally:
        db.close()

    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=backend_port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    backend_url = f"http://127.0.0.1:{backend_port}"
    _wait_http(backend_url + "/health")

    frontend_dist = os.path.join(ROOT, "frontend", "dist")
    assert os.path.isdir(frontend_dist), (
        "frontend/dist not found; run `npm run build` (or `vite build`) in "
        "the frontend directory before running browser tests"
    )
    fe = start_frontend_server(frontend_dist, backend_url, _free_port())
    _wait_http(fe.url)

    yield fe.url, backend_url
    fe.shutdown()
    server.should_exit = True
