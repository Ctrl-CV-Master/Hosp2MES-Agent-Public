"""True GUI end-to-end test: the agent creates a material through the browser.

This test proves the GUI path end to end:

1. a fresh Mock MES backend starts on an isolated database (material absent);
2. the built Vue Mock MES frontend is served (vite preview of dist/) with the
   ``/api`` proxy pointed at that backend;
3. the BrowserAgent opens the page in real Chromium and creates the material
   purely through Playwright GUI actions;
4. success is verified by an *independent* REST read-back (a fresh ApiEnv),
   not by the GUI's own rendering;
5. before/after screenshots and a structured evidence file are written.

The test also asserts the agent never issued a business REST verb (e.g.
``create_material``) — every recorded action is a GUI verb.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

pytest.importorskip("playwright.sync_api")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND = os.path.join(ROOT, "backend")
for p in (BACKEND, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from hosp2mes.agent.browser_agent import BrowserAgent  # noqa: E402
from hosp2mes.agent.agent import TaskLoader  # noqa: E402
from hosp2mes.config import Config  # noqa: E402
from hosp2mes.observation.api_env import ApiEnv  # noqa: E402
from hosp2mes.observation.browser_env import BrowserEnv  # noqa: E402


def test_gui_material_creation_e2e(browser_stack, playwright_browser):
    frontend_url, backend_url = browser_stack

    # 1. Initial state: the target material does NOT exist.
    verify_before = ApiEnv(base_url=backend_url)
    assert verify_before.get_material("MAT-GUI-001") is None

    # 2. Run the agent in browser mode against the live Vue app.
    tmp = tempfile.mkdtemp(prefix="hosp2mes-gui-e2e-")
    cfg = Config(
        agent_mode="hosp2mes", llm_provider="mock",
        backend_base_url=backend_url, frontend_url=frontend_url,
        headless=True, artifacts_root=tmp,
    )
    task = TaskLoader.from_yaml(
        os.path.join(ROOT, "benchmark", "tasks", "MES-DEMO-GUI-001.yaml")
    )
    env = BrowserEnv(base_url=frontend_url, backend_url=backend_url,
                     headless=True, _browser=playwright_browser)
    agent = BrowserAgent(cfg, env, task)
    report, trace, memory = agent.run()

    if not report.task_success:
        print("\n=== browser console / pageerror messages ===")
        for m in env.console_messages:
            print(m)
        try:
            env._page.screenshot(path=os.path.join(tmp, "failure.png"))
        except Exception:
            pass
    assert report.task_success, report.to_dict()
    assert report.verifier_passed

    # 3. Independent REST read-back confirms the state change (not GUI self-report).
    verify_after = ApiEnv(base_url=backend_url)
    created = verify_after.get_material("MAT-GUI-001")
    assert created is not None
    assert created["material_name"] == "GUI演示物料"

    # 4. Evidence: before/after screenshots + structured step records.
    run_dir = os.path.join(tmp, "runs", agent.run_id)
    assert os.path.isfile(os.path.join(run_dir, "summary.json"))
    steps_path = os.path.join(run_dir, "steps.json")
    assert os.path.isfile(steps_path)

    steps = json.load(open(steps_path, encoding="utf-8"))
    assert len(steps) > 0
    # Every recorded action is a GUI verb — the agent must NOT call business REST.
    gui_verbs = {"click", "type", "select", "scroll", "press", "wait",
                 "navigate", "back", "extract"}
    for s in steps:
        verb = s["action"].split(":")[0]
        assert verb in gui_verbs, f"non-GUI action recorded: {s['action']}"
        assert "create_material" not in s["action"]
    # The save click must be present.
    assert any("保存" in s["action"] for s in steps)

    # At least one before + one after screenshot.
    pngs = [f for f in os.listdir(run_dir) if f.endswith(".png")]
    assert any("-before" in f for f in pngs)
    assert any("-after" in f for f in pngs)

    # 5. The evidence summary records a successful, GUI-driven run.
    summary = json.load(open(os.path.join(run_dir, "summary.json"), encoding="utf-8"))
    assert summary["success"] is True
    assert summary["gui_steps"] > 0