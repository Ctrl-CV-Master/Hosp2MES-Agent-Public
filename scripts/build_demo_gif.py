"""Assemble the Hero demo GIF from a real run's per-step "after" screenshots.

Reads ``artifacts/runs/<run_id>/`` (excluded from Git) and writes
``assets/demo/hosp2mes-agent-demo.gif`` — a curated, captioned GIF that
shows the agent driving the full long-horizon workflow (Material → BOM →
Order → 7 stages → Final Verify).

The screenshots are genuine captures of a real DeepSeek (or deterministic
skill) run; this script only resizes, adds a caption bar and assembles.

Usage:
    python scripts/build_demo_gif.py <run_id> [--out path] [--width 960] [--frame-ms 700]
"""
from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Phase (subgoal) -> human-readable caption + color.
PHASES = {
    "create_material": ("1 / 10  Material", "#2563eb"),
    "create_bom": ("2 / 10  BOM", "#0d9488"),
    "create_production_order": ("3 / 10  Production Order", "#7c3aed"),
    "execute_production": ("4-10 / 10  Production Stages", "#ea580c"),
}

# ZH -> EN stage caption (for the 7 production stages).
STAGE_ZH = {
    "weighing": "Weighing", "dissolution": "Dissolution", "filtration": "Filtration",
    "filling": "Filling", "labeling": "Labeling", "packaging": "Packaging",
    "storage": "Storage",
}


def _stage_label(action_target: Any) -> str:
    """Extract a human stage label from a scoped action target (e.g. row.text='称量')."""
    if isinstance(action_target, dict):
        within = action_target.get("within") or {}
        text = within.get("text") if isinstance(within, dict) else None
        if text and text in STAGE_ZH.values():
            for en in STAGE_ZH.values():
                if en == text:
                    return text
        # Chinese labels in MES UI map to the English stage names.
        for zh, en in STAGE_ZH.items():
            if text == zh or text == "称量" and zh == "weighing" or text == "溶解" and zh == "dissolution":
                return f"{en} ({text})"
        if text:
            return f"Stage: {text}"
    return "Production Stage"


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("seguiemj.ttf", "msyh.ttc", "arialbd.ttf", "DejaVuSans-Bold.ttf",
                 "Arial-Bold.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _caption_for(step: dict) -> tuple[str, str]:
    subgoal = step.get("subgoal", "")
    base, color = PHASES.get(subgoal, (subgoal or "—", "#475569"))
    if subgoal == "execute_production":
        stage = _stage_label(step.get("action_target"))
        action = step.get("action", "")
        if "click" in action and "within" in (step.get("action_target") or {}):
            text = f"{base}  •  {stage}"
        else:
            text = f"{base}  •  {stage} ({action.split(':',1)[0] if action else 'observe'})"
        return text, color
    return base, color


def build(run_id: str, out_path: str, width: int, frame_ms: int) -> str:
    src_dir = os.path.join(ROOT, "artifacts", "runs", run_id)
    if not os.path.isdir(src_dir):
        raise SystemExit(f"source run dir not found: {src_dir}")
    with open(os.path.join(src_dir, "steps.json"), encoding="utf-8") as f:
        steps = json.load(f)

    # Match screenshots: filename "<seq>-<subgoal>-<idx>-after.png" -> step number = seq.
    # In the run layout, the seq equals the 1-based step index.
    pat = re.compile(r"^(\d{3})-([a-z_]+)-(\d{2})-after\.png$")
    pairs: list[tuple[Image.Image, str, str]] = []
    for s in steps:
        seq = s.get("step", 0)
        if seq <= 0:
            continue
        sub = s.get("subgoal", "")
        idx = seq - 1  # filename index starts at 00
        fn = f"{seq:03d}-{sub}-{idx:02d}-after.png"
        p = os.path.join(src_dir, fn)
        if not os.path.exists(p):
            # Best-effort fallback: find by step's screenshot_after basename.
            base = os.path.basename(s.get("screenshot_after") or "")
            if base and os.path.exists(os.path.join(src_dir, base)):
                p = os.path.join(src_dir, base)
            else:
                continue
        text, color = _caption_for(s)
        pairs.append((p, text, color))

    if not pairs:
        raise SystemExit("no after-screenshots matched any step")

    images: list[Image.Image] = []
    f_title = _font(28)
    f_small = _font(16)
    for path, text, color in pairs:
        im = Image.open(path).convert("RGB")
        w0, h0 = im.size
        scale = width / w0
        new_h = int(h0 * scale)
        im = im.resize((width, new_h), Image.LANCZOS)
        # Caption bar
        bar_h = 50
        canvas = Image.new("RGB", (width, new_h + bar_h), (15, 23, 42))
        canvas.paste(im, (0, bar_h))
        draw = ImageDraw.Draw(canvas)
        # Coloured accent
        draw.rectangle([0, 0, 6, bar_h], fill=color)
        draw.text((20, 10), text, fill=(255, 255, 255), font=f_title)
        images.append(canvas)

    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    images[0].save(
        out_path, save_all=True, append_images=images[1:],
        duration=frame_ms, loop=0, optimize=True,
    )
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id", help="real run id, e.g. MES-DEMO-003-20260823T011158Z")
    ap.add_argument("--out", default="assets/demo/hosp2mes-agent-demo.gif")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--frame-ms", type=int, default=700)
    args = ap.parse_args()
    out = build(args.run_id, args.out, args.width, args.frame_ms)
    size_kb = os.path.getsize(out) / 1024
    print(f"wrote {out}  ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
