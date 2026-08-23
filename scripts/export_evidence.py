"""Export curated, sanitized public evidence from real local run artifacts.

Reads a real ``artifacts/runs/<run_id>/`` directory and produces a compact,
sanitized copy under ``examples/evidence/<kind>/``. It never fabricates data:
``summary.json`` is copied verbatim (it already contains only public fields),
``selected_steps.json`` keeps only representative steps with public-safe fields,
and only a handful of representative screenshots are copied (renamed to friendly
phase names). Absolute local paths, private chain-of-thought and any credential
are stripped out.

Usage:
    python scripts/export_evidence.py hero     <run_id>
    python scripts/export_evidence.py recovery <run_id>
"""
from __future__ import annotations

import argparse
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# CLI kind -> public evidence directory name.
KIND_DIR = {"hero": "long_horizon_hero", "recovery": "recovery_hero"}

# Fields we keep per step (public-safe; no screenshot paths, no raw memory).
STEP_KEEP = [
    "step", "subgoal", "action", "action_target", "value", "action_result",
    "policy_source", "llm_model", "llm_latency_ms", "llm_call_success",
    "llm_parse_success", "fallback_used", "decision_rationale",
    "state_changed", "url",
]

# phase name -> (subgoal | None, "first" | "last")
HERO_PHASES = [
    ("01-material", "create_material", "last"),
    ("02-bom", "create_bom", "last"),
    ("03-order", "create_production_order", "last"),
    ("04-execution", "execute_production", "last"),
    ("05-final", None, "last"),
]

RECOVERY_PHASES = [
    ("01-before-fault", "create_bom", "first"),
    ("02-failure-detected", "create_production_order", "last"),
    ("03-local-repair", "create_bom", "repair_start"),
    ("04-repair-verified", None, "repair_end"),
    ("05-final-pass", None, "last"),
]


def _screenshot_basename(step: dict) -> str | None:
    for key in ("screenshot_after", "screenshot_before"):
        p = step.get(key)
        if p:
            return os.path.basename(p)
    return None


def _sanitize_url(url: str) -> str:
    """Strip scheme/host/port (local IP) and keep only the route path."""
    if not isinstance(url, str):
        return url
    for sep in ("://",):
        if sep in url:
            rest = url.split(sep, 1)[1]
            if "/" in rest:
                return "/" + rest.split("/", 1)[1]
            return "/"
    return url


def _sanitize_step(step: dict) -> dict:
    out = {k: step.get(k) for k in STEP_KEEP}
    out["goal"] = (step.get("goal") or "")[:120]
    out["url"] = _sanitize_url(step.get("url", ""))
    return out


def _copy_shot(src_dir: str, step: dict, dst: str, name: str) -> None:
    base = _screenshot_basename(step)
    if base is None:
        return
    src = os.path.join(src_dir, base)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(dst, f"{name}.png"))


def _steps_by_subgoal(steps: list[dict], subgoal: str) -> list[dict]:
    return [s for s in steps if s.get("subgoal") == subgoal]


def _resolve_step(steps: list[dict], which: str, subgoal: str | None,
                  repair_end_step: int, trigger_step: int = 0) -> dict | None:
    if which == "repair_end":
        for s in steps:
            if s.get("step") == repair_end_step:
                return s
        return None
    if which == "repair_start":
        # First step after the failure trigger (the repair navigation action).
        for s in steps:
            if s.get("step", 0) > trigger_step and s.get("subgoal") == subgoal:
                return s
        return None
    pool = _steps_by_subgoal(steps, subgoal) if subgoal else steps
    if not pool:
        return None
    return pool[-1] if which == "last" else pool[0]


def export(kind: str, run_id: str) -> str:
    src_dir = os.path.join(ROOT, "artifacts", "runs", run_id)
    if not os.path.isdir(src_dir):
        raise SystemExit(f"source run dir not found: {src_dir}")

    with open(os.path.join(src_dir, "summary.json"), encoding="utf-8") as f:
        summary = json.load(f)
    with open(os.path.join(src_dir, "steps.json"), encoding="utf-8") as f:
        steps = json.load(f)

    # repair_end_step + trigger_step (recovery kind only) — from the trace.
    repair_end_step = 0
    trigger_step = 0
    rec = None
    rec_dir = os.path.join(src_dir, "recovery")
    if kind == "recovery" and os.path.isdir(rec_dir):
        traces = sorted(os.listdir(rec_dir))
        if traces:
            with open(os.path.join(rec_dir, traces[0]), encoding="utf-8") as f:
                rec = json.load(f)
            repair_end_step = int(rec.get("repair_end_step", 0) or 0)
            trigger_step = int(rec.get("trigger_step", 0) or 0)

    dst = os.path.join(ROOT, "examples", "evidence", KIND_DIR[kind])
    os.makedirs(os.path.join(dst, "screenshots"), exist_ok=True)

    with open(os.path.join(dst, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    if rec is not None:
        # Strip any absolute-path-looking string values defensively.
        rec = {k: v for k, v in rec.items()
               if not isinstance(v, str) or ("\\" not in v and not v.startswith("/"))}
        with open(os.path.join(dst, "recovery-001.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)

    # selected steps: the representative step for each phase + the last step.
    phases = HERO_PHASES if kind == "hero" else RECOVERY_PHASES
    selected_indices: set[int] = set()
    for _name, subgoal, which in phases:
        step = _resolve_step(steps, which, subgoal, repair_end_step, trigger_step)
        if step is not None:
            selected_indices.add(steps.index(step))
    selected_indices.add(len(steps) - 1)
    selected = [steps[i] for i in sorted(selected_indices)]
    with open(os.path.join(dst, "selected_steps.json"), "w", encoding="utf-8") as f:
        json.dump([_sanitize_step(s) for s in selected], f, ensure_ascii=False, indent=2)

    for name, subgoal, which in phases:
        step = _resolve_step(steps, which, subgoal, repair_end_step, trigger_step)
        if step is not None:
            _copy_shot(src_dir, step, os.path.join(dst, "screenshots"), name)

    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["hero", "recovery"])
    ap.add_argument("run_id")
    args = ap.parse_args()
    dst = export(args.kind, args.run_id)
    print(f"exported {args.kind} evidence to {os.path.relpath(dst, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
