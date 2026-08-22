"""Agent-policy tests: one-action-per-step loop + autonomy against a variant page."""
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

from hosp2mes.agents.hosp2mes_agent import ActionPolicy, Hosp2MESAgent  # noqa: E402
from hosp2mes.agent.agent import TaskLoader  # noqa: E402
from hosp2mes.config import Config  # noqa: E402
from hosp2mes.executor.actions import Action  # noqa: E402
from hosp2mes.executor.executor import ExecContext  # noqa: E402
from hosp2mes.observation.browser_env import BrowserEnv  # noqa: E402


# ---- 1. one action per call (unit) ---------------------------------------
def test_policy_emits_single_action():
    ctx = ExecContext(material_code="MAT-X", material_name="X物料",
                      material_type="raw", unit="kg", specification="spec")
    policy = ActionPolicy(Config(llm_provider="mock"), ctx)

    context = {
        "goal": "create material",
        "current_subgoal": {"id": "create_material", "capabilities": ["create_material"]},
        "progress_memory": {},
        "current_url": "http://x/materials",
        "visible_text": "",
        "interactive_elements": [{"role": "button", "accessible_name": "新建物料"}],
        "recent_actions": [],
    }
    d1 = policy.next_action(context)
    # A single action dict, never a list.
    assert isinstance(d1, dict)
    assert d1["action"] == "click"

    # Next call, with the dialog open, produces the next single action.
    context["interactive_elements"] = [
        {"role": "button", "accessible_name": "保存"},
        {"role": "textbox", "accessible_name": "物料编码"},
        {"role": "combobox", "accessible_name": "类型"},
    ]
    context["recent_actions"] = [{"action": "click",
                                  "target": {"role": "button", "name": "新建物料"},
                                  "result": "ok"}]
    d2 = policy.next_action(context)
    assert isinstance(d2, dict)
    assert d2["action"] == "type"
    assert d2["target"] == {"role": "textbox", "name": "物料编码"}


# ---- 2. autonomy: a variant page (reordered, distractors) -----------------
_VARIANT_HTML = """
<html><body>
  <div class="card" style="border:1px solid #ccc;padding:8px;margin:4px">
    <h4>无关信息卡片</h4><p>这里是无关文本，用于干扰依赖固定位置的 Agent。</p>
  </div>
  <button id="draft">新建指令(草稿)</button>
  <button id="export">导出报表</button>

  <button id="open">新建指令</button>

  <div id="form" style="display:none">
    <label>产品 <input id="product"></label>
    <label>数量 <input id="qty"></label>
    <label>批次 <input id="batch"></label>
    <label>指令号 <input id="code"></label>
    <button id="save">保存</button>
  </div>

  <script>
    document.getElementById('open').addEventListener('click', () => {
      document.getElementById('form').style.display = 'block';
    });
    document.getElementById('draft').addEventListener('click', () => { window.__draft = true; });
    document.getElementById('save').addEventListener('click', () => {
      window.__saved = {
        '指令号': document.getElementById('code').value,
        '产品': document.getElementById('product').value,
        '批次': document.getElementById('batch').value,
        '数量': document.getElementById('qty').value,
      };
    });
  </script>
</body></html>
"""


def _drive(env, policy, cap, open_button_name, page_path):
    recent = []
    for _ in range(40):
        obs = env.observe()
        context = {
            "goal": "create a production order",
            "current_subgoal": {"id": cap, "capabilities": [cap]},
            "progress_memory": {},
            # The static test page is served via set_content (about:blank), so
            # present a URL that satisfies the policy's navigation check.
            "current_url": f"http://localhost{page_path}",
            "visible_text": obs.visible_text,
            "interactive_elements": obs.interactive_elements,
            "recent_actions": recent,
        }
        d = policy.next_action(context) or {"action": "done"}
        if d.get("action") == "done":
            break
        action = Action(verb=d["action"], target=d.get("target"),
                        value=d.get("value"), params=d.get("params", {}),
                        reasoning=d.get("rationale", ""))
        res = env.execute(action)
        recent.append({"action": d.get("action"), "target": d.get("target"),
                       "value": d.get("value"), "result": "ok" if res.ok else f"fail:{res.detail}"})
        if len(recent) > 12:
            recent = recent[-12:]
        if env._page.evaluate("() => !!window.__saved"):
            break
    return env._page.evaluate("() => window.__saved || {}")


def test_autonomy_variant_layout(playwright_browser):
    env = BrowserEnv(base_url="http://localhost", _browser=playwright_browser)
    env.start()
    try:
        env._page.set_content(_VARIANT_HTML)
        ctx = ExecContext(order_code="ORD-X", product="DEMO-X", batch="B1", quantity=7)
        policy = ActionPolicy(Config(llm_provider="mock"), ctx)
        saved = _drive(env, policy, "create_production_order", "新建指令", "/orders")

        assert saved.get("指令号") == "ORD-X"
        assert saved.get("产品") == "DEMO-X"
        assert saved.get("批次") == "B1"
        assert saved.get("数量") == "7"
        # The distracting draft button must not have been triggered.
        assert env._page.evaluate("() => !!window.__draft") is False
    finally:
        env.close()


# ---- 3. Hosp2MESAgent completes GUI-001 via the policy loop ---------------
def test_hosp2mes_agent_completes_gui_001(browser_stack, playwright_browser):
    frontend_url, backend_url = browser_stack
    from hosp2mes.observation.api_env import ApiEnv

    assert ApiEnv(base_url=backend_url).get_material("MAT-GUI-001") is None

    tmp = tempfile.mkdtemp(prefix="hosp2mes-policy-")
    cfg = Config(agent_mode="hosp2mes", llm_provider="mock",
                 backend_base_url=backend_url, frontend_url=frontend_url,
                 headless=True, artifacts_root=tmp)
    task = TaskLoader.from_yaml(
        os.path.join(ROOT, "benchmark", "tasks", "MES-DEMO-GUI-001.yaml"))
    env = BrowserEnv(base_url=frontend_url, backend_url=backend_url,
                     headless=True, _browser=playwright_browser)
    agent = Hosp2MESAgent(cfg, env, task)
    report, _trace, _memory = agent.run()

    if not report.task_success:
        print("\n=== console ===")
        for m in env.console_messages:
            print(m)
    assert report.task_success, report.to_dict()
    assert report.verifier_passed

    created = ApiEnv(base_url=backend_url).get_material("MAT-GUI-001")
    assert created is not None
    assert created["material_name"] == "GUI演示物料"
