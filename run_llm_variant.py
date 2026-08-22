"""Real-LLM variant run: verify DeepSeek completes a perturbed form.

Serves a *variant* page (reordered fields, moved button, an extra "草稿"
button, an irrelevant card) and drives it with the real DeepSeek policy in
``llm-strict`` mode, one action per step. Success proves the LLM resolves
controls by *semantic* observation, not by fixed page order.

Records per-step provenance (policy_source / llm_model / latency / fallback).
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
for p in (ROOT, os.path.join(ROOT, "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from hosp2mes.agents.hosp2mes_agent import ActionPolicy, PolicyStrictFailure  # noqa: E402
from hosp2mes.config import Config  # noqa: E402
from hosp2mes.executor.actions import Action  # noqa: E402
from hosp2mes.executor.executor import ExecContext  # noqa: E402
from hosp2mes.observation.browser_env import BrowserEnv  # noqa: E402

VARIANT_HTML = """
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


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="llm-strict")
    ap.add_argument("--max-steps", type=int, default=40)
    args = ap.parse_args()

    cfg = Config.load()
    cfg.policy = args.policy
    if args.policy != "deterministic":
        cfg.llm_provider = "deepseek"

    ctx = ExecContext(order_code="ORD-X", product="DEMO-X", batch="B1", quantity=7)
    policy = ActionPolicy(cfg, ctx)

    from playwright.sync_api import sync_playwright

    provenance_log = []
    saved = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        env = BrowserEnv(base_url="http://localhost", _browser=browser)
        env.start()
        try:
            env._page.set_content(VARIANT_HTML)
            recent = []
            for _ in range(args.max_steps):
                obs = env.observe()
                context = {
                    "goal": "创建一条生产指令：指令号 ORD-X，产品 DEMO-X，批次 B1，数量 7。",
                    "current_subgoal": {"id": "create_production_order",
                                        "capabilities": ["create_production_order"]},
                    "progress_memory": {},
                    "current_url": "http://localhost/orders",
                    "visible_text": obs.visible_text,
                    "interactive_elements": obs.interactive_elements,
                    "recent_actions": recent,
                }
                try:
                    decision = policy.next_action(context)
                except PolicyStrictFailure as exc:
                    print("[llm-strict] POLICY FAILURE:", exc)
                    provenance_log.append({"error": str(exc), **exc.decision.provenance()})
                    break

                if decision is None or decision.action == "done":
                    break
                prov = decision.provenance()
                prov["action"] = decision.action
                prov["target"] = json.dumps(decision.target, ensure_ascii=False)
                provenance_log.append(prov)

                action = Action(verb=decision.action, target=decision.target,
                                value=decision.value, params=decision.params,
                                reasoning=decision.rationale)
                res = env.execute(action)
                recent.append({"action": decision.action, "target": decision.target,
                               "value": decision.value,
                               "result": "ok" if res.ok else f"fail:{res.detail}"})
                if len(recent) > 12:
                    recent = recent[-12:]
                if env._page.evaluate("() => !!window.__saved"):
                    break
            saved = env._page.evaluate("() => window.__saved || {}")
            draft_hit = env._page.evaluate("() => !!window.__draft")
        finally:
            env.close()

    print("\n=== REAL LLM VARIANT RESULT ===")
    print("saved:", json.dumps(saved, ensure_ascii=False))
    print("draft_hit:", draft_hit)
    print("steps:", len(provenance_log))
    for i, st in enumerate(provenance_log, 1):
        print(f"  {i} | {st.get('policy_source')} | {st.get('action')} "
              f"{st.get('target')} | fallback={st.get('fallback_used')} | "
              f"latency={st.get('llm_latency_ms')}ms | {st.get('decision_rationale','')[:40]}")

    ok = (saved.get("指令号") == "ORD-X" and saved.get("产品") == "DEMO-X"
          and saved.get("批次") == "B1" and saved.get("数量") == "7"
          and draft_hit is False
          and all(st.get("policy_source") == "deepseek" for st in provenance_log)
          and all(not st.get("fallback_used") for st in provenance_log)
          and len(provenance_log) > 0)
    print("REAL_LLM_VARIANT =", "PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
