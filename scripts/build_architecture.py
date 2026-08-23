"""Render the architecture diagram to assets/architecture.png.

Writes a self-contained HTML page describing the Hosp2MES-Agent loop and the
adaptive-recovery path, then screenshots it with a headless Chromium so the
final PNG is a clean, wide, vector-quality diagram (no matplotlib needed).
"""
from __future__ import annotations

import argparse
import os
import tempfile

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  body { margin: 0; font: 16px/1.4 -apple-system, "Segoe UI", Arial, sans-serif;
         background: #0b1220; color: #e2e8f0; }
  .wrap { width: 1400px; padding: 40px 50px; }
  h1 { font-size: 28px; font-weight: 700; margin: 0 0 6px; color: #f8fafc; }
  .sub { color: #94a3b8; font-size: 14px; margin-bottom: 28px; }
  .row { display: flex; gap: 16px; align-items: center; margin: 10px 0; }
  .box { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
         padding: 14px 18px; text-align: center; min-width: 200px;
         box-shadow: 0 2px 6px rgba(0,0,0,.35); }
  .box b { color: #f8fafc; font-size: 15px; }
  .box .d { color: #94a3b8; font-size: 12px; margin-top: 4px; }
  .acc { background: #2563eb22; border-color: #2563eb; }
  .teal { background: #0d948822; border-color: #0d9488; }
  .orange { background: #ea580c22; border-color: #ea580c; }
  .purple { background: #7c3aed22; border-color: #7c3aed; }
  .gray { background: #1e293b; }
  .arrow { color: #64748b; font-size: 22px; }
  .verdict { display: flex; gap: 18px; margin: 14px 0 0 60px; align-items: center; }
  .verdict .box { min-width: 110px; }
  .pass { border-color: #16a34a; background: #16a34a22; }
  .fail { border-color: #dc2626; background: #dc262622; }
  .stack { display: flex; flex-direction: column; gap: 8px; background: #111827;
           border: 1px dashed #475569; border-radius: 10px; padding: 10px 14px; }
  .stack b { color: #f8fafc; }
  .stack .d { color: #94a3b8; font-size: 12px; }
  .branch { margin-top: 4px; }
  .recovery { background: #1f2937; border: 1px solid #f59e0b; border-radius: 10px;
              padding: 10px 16px; color: #fbbf24; }
  .recovery b { color: #fde68a; }
  .legend { color: #64748b; font-size: 12px; margin-top: 24px; }
</style></head>
<body><div class="wrap">
  <h1>Hosp2MES-Agent — Architecture</h1>
  <div class="sub">Long-horizon GUI agent for manufacturing execution — observe, decide, act, verify, recover.</div>

  <div class="row">
    <div class="box"><b>Natural Language Task</b><div class="d">"Create product, BOM, order, run 7 stages, store."</div></div>
  </div>
  <div class="row"><div class="arrow">↓</div></div>

  <div class="row">
    <div class="box acc"><b>Long-Horizon Planner</b><div class="d">decompose into dependency-aware subgoals</div></div>
  </div>
  <div class="row"><div class="arrow">↓</div></div>

  <div class="row">
    <div class="box teal"><b>Structured Progress Memory</b><div class="d">goal / subgoals / pending / completed / evidence</div></div>
  </div>
  <div class="row"><div class="arrow">↓</div></div>

  <div class="row">
    <div class="box orange" style="min-width:560px"><b>Hosp2MESAgent — Observe → Decide → Act</b>
      <div class="d" style="margin-top:10px">
        <div class="stack" style="text-align:left">
          <div><b>Browser Observation</b> <span class="d">DOM + accessibility + screenshot</span></div>
          <div><b>DeepSeek Action Policy</b> <span class="d">one structured action per step (deterministic / llm / llm-strict)</span></div>
          <div><b>BrowserExecutor</b> <span class="d">semantic locator → click / type / select / wait (no XPath, no fixed coords)</span></div>
        </div>
      </div>
    </div>
  </div>
  <div class="row"><div class="arrow">↓</div></div>

  <div class="row">
    <div class="box gray"><b>Mock MES</b><div class="d">Vue 3 + FastAPI + SQLite (synthetic data only)</div></div>
  </div>
  <div class="row"><div class="arrow">↓</div></div>

  <div class="row">
    <div class="box purple"><b>Independent Verifier</b><div class="d">read-only REST client — never mutates state</div></div>
  </div>
  <div class="row"><div class="arrow">↓</div></div>

  <div class="verdict">
    <div class="arrow">↓</div>
    <div class="box"><b>Evidence Gate</b><div class="d">agent DONE ≠ task success</div></div>
    <div class="branch">
      <div class="box pass"><b>PASS</b><div class="d">next subgoal</div></div>
    </div>
    <div class="branch">
      <div class="box fail"><b>FAIL</b><div class="d">state diff → diagnosis</div></div>
    </div>
  </div>

  <div class="row">
    <div class="recovery">
      <b>Adaptive Recovery (V1.3)</b> &nbsp; State diff &rarr; Failure diagnosis &rarr; Dependency-aware local replan &rarr; GUI repair &rarr; Independent verification &rarr; <b>Resume</b>
    </div>
  </div>

  <div class="legend">REST API does not participate in GUI action decisions or business-state mutation; it is used only as an independent read-only verifier for subgoal-completion checks and final-state verification.</div>
</div></body></html>"""


def build(out_path: str, width: int, height: int) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(HTML)
        html_path = f.name
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": width, "height": height},
                                  device_scale_factor=2)
        page = ctx.new_page()
        page.goto("file://" + html_path, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=out_path, full_page=True, omit_background=False)
        browser.close()
    os.unlink(html_path)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="assets/architecture.png")
    ap.add_argument("--width", type=int, default=1500)
    ap.add_argument("--height", type=int, default=1050)
    args = ap.parse_args()
    out = build(args.out, args.width, args.height)
    size_kb = os.path.getsize(out) / 1024
    print(f"wrote {out}  ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
