"""Capture clean portfolio screenshots from the Mock MES frontend.

Starts backend + serves the prebuilt Vue dist, then uses Playwright to
navigate to each main view and screenshot it to ``assets/portfolio/``.
Also re-uses representative screenshots from the public evidence folders
for the workflow / recovery / architecture images.

Usage:
    python scripts/capture_portfolio_screenshots.py
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import httpx  # noqa: E402
import uvicorn  # noqa: E402

import app.database as dbmod  # noqa: E402
from app.database import configure_engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
from tests._frontend_server import start_frontend_server  # noqa: E402


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _wait_http(url: str, timeout: float = 30.0) -> None:
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
    from playwright.sync_api import sync_playwright

    bp = _free_port()
    configure_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'portfolio.db')}")
    init_db()
    db = dbmod.SessionLocal(); seed(db); db.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=bp, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    backend_url = f"http://127.0.0.1:{bp}"
    _wait_http(backend_url + "/health")

    frontend_dist = os.path.join(ROOT, "frontend", "dist")
    assert os.path.isdir(frontend_dist), "frontend/dist not found; build it first"
    fe = start_frontend_server(frontend_dist, backend_url, _free_port())
    frontend_url = fe.url
    _wait_http(frontend_url)

    out = os.path.join(ROOT, "assets", "portfolio")
    os.makedirs(out, exist_ok=True)

    try:
        httpx.post(f"{backend_url}/api/materials", json={
            "material_code": "MAT-DEMO", "material_name": "DEMO Material",
            "material_type": "raw", "unit": "kg", "specification": "synthetic",
        }, timeout=5)
    except Exception:
        pass

    targets = [
        ("dashboard.png", "/dashboard"),
        ("material.png", "/materials"),
        ("bom.png", "/boms"),
        ("order.png", "/orders"),
        ("execution.png", "/execution"),
        ("agent-monitor.png", "/agent"),
        ("benchmark.png", "/benchmark"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  device_scale_factor=1)
        page = ctx.new_page()
        for fname, route in targets:
            page.goto(frontend_url + route, wait_until="networkidle")
            time.sleep(0.6)
            page.screenshot(path=os.path.join(out, fname), full_page=False)
            print(f"  {fname}  <-  {frontend_url}{route}")
        browser.close()

    src_arch = os.path.join(ROOT, "assets", "architecture.png")
    if os.path.exists(src_arch):
        shutil.copy2(src_arch, os.path.join(out, "architecture.png"))

    src_hero = os.path.join(ROOT, "examples", "evidence", "long_horizon_hero", "screenshots")
    if os.path.isdir(src_hero):
        for src, dst in [
            ("01-material.png", "hero-material.png"),
            ("03-order.png", "hero-order.png"),
            ("05-final.png", "hero-final.png"),
        ]:
            p = os.path.join(src_hero, src)
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(out, dst))
    src_rec = os.path.join(ROOT, "examples", "evidence", "recovery_hero", "screenshots")
    if os.path.isdir(src_rec):
        for src, dst in [
            ("01-before-fault.png", "recovery-before-fault.png"),
            ("02-failure-detected.png", "recovery-failure-detected.png"),
            ("03-local-repair.png", "recovery-local-repair.png"),
            ("04-repair-verified.png", "recovery-repair-verified.png"),
            ("05-final-pass.png", "recovery-final-pass.png"),
        ]:
            p = os.path.join(src_rec, src)
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(out, dst))

    fe.shutdown()
    srv.should_exit = True
    print(f"\nportfolio screenshots saved to {os.path.relpath(out, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
