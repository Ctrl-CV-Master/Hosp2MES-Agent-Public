"""Robustness tests for browser-mode production execution.

Three layers:

1. ``test_gui_production_execution_e2e`` — a real end-to-end GUI run of the
   production-execution loop (order → 7 stages → storage) against the built Vue
   app, verified by an independent REST read-back.
2. ``test_scope_locator_multiple_buttons`` — a semantic scoped target
   (``within a row → button "完成"``) picks the *correct* row's button when
   several identical "完成" buttons exist.
3. ``test_locator_re_resolved_after_rerender`` — after a Vue-like DOM re-render
   replaces a button, the executor re-resolves the fresh element instead of
   reusing a stale handle.
"""
from __future__ import annotations

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
from hosp2mes.agent.agent import Task  # noqa: E402
from hosp2mes.config import Config  # noqa: E402
from hosp2mes.executor.actions import Action  # noqa: E402
from hosp2mes.observation.api_env import ApiEnv  # noqa: E402
from hosp2mes.observation.browser_env import BrowserEnv  # noqa: E402


# ---- 1. production execution GUI E2E --------------------------------------
def test_gui_production_execution_e2e(browser_stack, playwright_browser):
    frontend_url, backend_url = browser_stack

    # Seed the prerequisite order via the backend (independent of the GUI) so
    # this test isolates the execution loop itself.
    api = ApiEnv(base_url=backend_url)
    order = api.create_order("ORD-GUI-002", "DEMO-GUI-EXEC", "B2026GUI002", 60)
    assert order.ok, order.detail
    assert api.get_order("ORD-GUI-002")["status"] == "NOT_STARTED"

    tmp = tempfile.mkdtemp(prefix="hosp2mes-gui-exec-")
    cfg = Config(
        agent_mode="hosp2mes", llm_provider="mock",
        backend_base_url=backend_url, frontend_url=frontend_url,
        headless=True, artifacts_root=tmp,
    )
    task = Task(
        task_id="GUI-EXEC-001",
        instruction="通过浏览器 GUI 完成目标生产指令的全部 7 个生产阶段并入库。",
        product="DEMO-GUI-EXEC",
        order_code="ORD-GUI-002",
        expected_final_state={
            "production_order_status": "COMPLETED",
            "storage_status": "STORED",
        },
    )
    env = BrowserEnv(base_url=frontend_url, backend_url=backend_url,
                     headless=True, _browser=playwright_browser)
    agent = BrowserAgent(cfg, env, task)
    report, _trace, _memory = agent.run()

    if not report.task_success:
        print("\n=== browser console / pageerror messages ===")
        for m in env.console_messages:
            print(m)
    assert report.task_success, report.to_dict()
    assert report.verifier_passed

    # Independent read-back: the order is COMPLETED and storage is STORED.
    verify = ApiEnv(base_url=backend_url)
    final = verify.get_order("ORD-GUI-002")
    assert final["status"] == "COMPLETED"
    stored = any(s["stage_name"] == "storage" and s["stage_status"] == "COMPLETED"
                 for s in final["stages"])
    assert stored


# ---- 2. scoped locator among identical buttons ----------------------------
_SCOPE_HTML = """
<table><tbody>
  <tr><td>称量</td><td><button class="done" data-stage="weighing">完成</button></td></tr>
  <tr><td>过滤</td><td><button class="done" data-stage="filtration">完成</button></td></tr>
  <tr><td>入库</td><td><button class="done" data-stage="storage">完成</button></td></tr>
</tbody></table>
<script>
  window.__clicked = null;
  document.querySelectorAll('button.done').forEach(b =>
    b.addEventListener('click', () => { window.__clicked = b.dataset.stage; }));
</script>
"""


def test_scope_locator_multiple_buttons(playwright_browser):
    env = BrowserEnv(base_url="http://localhost", _browser=playwright_browser)
    env.start()
    try:
        env._page.set_content(_SCOPE_HTML)
        res = env.execute(Action("click", target={
            "within": {"role": "row", "text": "过滤"},
            "role": "button", "name": "完成",
        }))
        assert res.ok, res.detail
        clicked = env._page.evaluate("() => window.__clicked")
        assert clicked == "filtration", "scoped click must hit the 过滤 row's button"
    finally:
        env.close()


# ---- 3. locator re-resolved after a DOM re-render -------------------------
_RERENDER_HTML = """
<table><tbody>
  <tr><td>过滤</td><td><button class="done" data-version="1">完成</button></td></tr>
</tbody></table>
<script>
  window.__clicks = [];
  document.addEventListener('click', (e) => {
    const b = e.target.closest('button.done');
    if (b) {
      window.__clicks.push(b.dataset.version);
      // Simulate a Vue re-render: replace the button with a brand-new node.
      const nb = document.createElement('button');
      nb.className = 'done';
      nb.dataset.version = '2';
      nb.textContent = '完成';
      b.replaceWith(nb);
    }
  });
</script>
"""


def test_locator_re_resolved_after_rerender(playwright_browser):
    env = BrowserEnv(base_url="http://localhost", _browser=playwright_browser)
    env.start()
    try:
        env._page.set_content(_RERENDER_HTML)
        target = {"within": {"role": "row", "text": "过滤"},
                  "role": "button", "name": "完成"}
        r1 = env.execute(Action("click", target=target))
        assert r1.ok, r1.detail
        r2 = env.execute(Action("click", target=target))
        assert r2.ok, r2.detail
        clicks = env._page.evaluate("() => window.__clicks")
        # First click hit the original node, second click hit the re-rendered
        # node — proving the executor re-resolved from the fresh DOM instead of
        # reusing a stale ElementHandle.
        assert clicks == ["1", "2"], clicks
    finally:
        env.close()
