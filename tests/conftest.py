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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def browser_page(playwright_browser):
    """A fresh page (own context) for browser unit tests."""
    ctx = playwright_browser.new_context()
    page = ctx.new_page()
    yield page
    ctx.close()
