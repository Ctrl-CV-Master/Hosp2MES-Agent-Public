# Public Run Evidence

These files are curated, sanitized evidence exported from **real local runs** of
Hosp2MES-Agent-Public. They are intended to be viewable directly on GitHub.

Full local artifacts are intentionally excluded from Git (see `artifacts/` in
`.gitignore`), because each browser run generates dozens of screenshots plus
per-step records. What lives here is a compact, representative subset.

> Full artifacts are generated locally under `artifacts/runs/` and are
> intentionally excluded from Git.

## Sanitization

Before export, every file was scanned and stripped of anything sensitive:

- API keys / `Authorization` / `Bearer` / `Cookie` / tokens
- local usernames and absolute disk paths
- local IP addresses / ports (URLs are reduced to their route path)
- `.env` contents
- private chain-of-thought (only short public `decision_rationale` is kept)

Retained fields are exactly the public ones: `run_id`, `model name`,
`policy_source`, `llm_latency_ms`, `action`, `target`, `value`, `rationale`,
business state and metrics.

## Long-Horizon Hero

`long_horizon_hero/` — `MES-DEMO-003-20260823T011158Z`.

- **model**: `deepseek-v4-flash`
- **policy mode**: `llm-strict`
- **planner source**: `deterministic`
- **total GUI steps**: 31
- **total LLM calls**: 31 (all `policy_source=deepseek`)
- **fallback count**: 0
- **final verification**: `material_exists=true`, `bom_exists=true`,
  `production_order_status=COMPLETED`, `storage_status=STORED`
- **task success**: true

Files:

- `summary.json` — full run metadata + final verification.
- `selected_steps.json` — representative decision steps (one per business phase).
- `screenshots/` — `01-material.png` → `05-final.png`.

## Adaptive Recovery Hero

`recovery_hero/` — `MES-DEMO-RECOVERY-001-20260823T042516Z`.

- **fault scenario**: `FAULT-BOM-001` — the BOM is discarded right after
  `create_bom` completes (`discard_state_change`, once), injected by the test
  harness (never visible to the agent's policy/prompt/observation).
- **state diff**: `bom.exists` expected `true` / observed `false`.
- **failure diagnosis**: `MISSING_PREREQUISITE` (failed subgoal:
  `create_production_order`).
- **local replan**: `preserve [create_material]`, `reactivate [create_bom]`,
  `invalidate [create_bom, create_production_order, execute_production]`,
  `resume_from create_bom`.
- **recovery count**: 1 (success)
- **recovery steps**: 7 (only the BOM repair episode, `repair_end_step - repair_start_step`)
- **reexecuted completed subgoals**: 0 (material was never re-executed)
- **final verification**: `material_exists=true`, `bom_exists=true`,
  `production_order_status=COMPLETED`, `storage_status=STORED`
- **task success**: true

Files:

- `summary.json` — full run metadata + final verification + metrics.
- `recovery-001.json` — the recovery trace (trigger step, state diff, diagnosis,
  repair plan, repair episode boundaries, repair steps, verification result).
- `selected_steps.json` — representative steps across the failure → repair → resume.
- `screenshots/` — `01-before-fault.png` → `05-final-pass.png`.

## How this was exported

`scripts/export_evidence.py` reads a real `artifacts/runs/<run_id>/` directory
and writes the curated copy here. Re-run it against any local run with:

```bash
python scripts/export_evidence.py hero     <run_id>
python scripts/export_evidence.py recovery <run_id>
```
