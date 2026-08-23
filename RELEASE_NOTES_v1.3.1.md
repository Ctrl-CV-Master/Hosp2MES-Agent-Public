# Hosp2MES-Agent v1.3.1 — Release Notes

> **TECHNICAL_CORE_STATUS = FROZEN.** V1.3.1 is the last technical-core
> version. Future work is portfolio release (CI, README, demo, architecture,
> release) only.

## Highlights

- **Real DeepSeek GUI execution** — `Hosp2MESAgent` runs an
  `Observation → ONE GUI Action → Execute → Observe` loop against a real
  Vue 3 MES frontend in Chromium, with `policy_source` (deterministic /
  deepseek), `llm_model`, `llm_latency_ms` and `decision_rationale`
  recorded per step. No pre-written action lists.
- **Long-Horizon Hero PASS** — `MES-DEMO-003-20260823T011158Z`: 31 deepseek
  decisions, **0 fallback**, 4/4 subgoals, independent read-only verifier
  confirmed all of `material_exists / bom_exists / production_order_status /
  storage_status`.
- **Evidence-Gated Completion** — `agent DONE ≠ task success`. The agent
  only passes when the independent read-only REST verifier confirms the
  live business state matches the expected final state.
- **Adaptive Recovery PASS** — `MES-DEMO-RECOVERY-001-20260823T042516Z`:
  harness-injected `FAULT-BOM-001` (BOM discarded after creation)
  → state diff (`bom.exists` false)
  → `MISSING_PREREQUISITE` diagnosis
  → dependency-aware local replan (`preserve create_material`,
  `reactivate create_bom`, `invalidate downstream`, `resume_from
  create_bom`)
  → DeepSeek GUI repair
  → resume, final verified. `REEXECUTED_COMPLETED_SUBGOALS=0`.
- **Honest metrics** — `subgoal_execution_counts` and
  `reexecuted_completed_subgoals` are computed from a **real** execution
  counter (not queue-set algebra). `total_recovery_steps` is bounded to
  the repair episode (trigger → repair-verified), not the full
  trigger→task-end span.
- **Public, reproducible, sanitized evidence** at
  `examples/evidence/{long_horizon_hero,recovery_hero}/`.
- **54 tests, all passing** — unit, GUI E2E, LLM policy modes, recovery
  regression, premature-DONE metrics.
- **GitHub Actions CI** (`.github/workflows/ci.yml`) — backend pytest,
  API E2E, frontend build, browser E2E (deterministic — no LLM key
  required for CI).

## Verified Runs (real, reproducible)

| run | run_id | policy | GUI steps | LLM calls | fallback | result |
|---|---|---|---|---|---|---|
| Long-Horizon Hero | `MES-DEMO-003-20260823T011158Z` | `llm-strict` | 31 | 31 | 0 | PASS — 4/4 subgoals, all state verified |
| Recovery Hero | `MES-DEMO-RECOVERY-001-20260823T042516Z` | `llm-strict` | 39 | 39 | 0 | PASS — 7 repair steps, 0 reexecuted |

## Known Limitations

- **Mock MES** — synthetic data only. No real hospital / factory
  connection. Do not claim "production-ready industrial agent".
- **Agent S3** — `gui-agents` (Apache-2.0) is installed and the adapter is
  constructed, but a real `predict()` requires a worker LLM key **and** a
  UI-TARS grounding endpoint. **Adapter only — runtime not yet evaluated.**
- **Recovery** is state-diff local re-planning in a single
  fault-injection scenario, not general-purpose self-healing.
- **SQLite** demo backend — replace with PostgreSQL etc. for any real
  deployment.

## How to consume

```bash
# clone + deterministic CI smoke
git clone https://github.com/Ctrl-CV-Master/Hosp2MES-Agent-Public.git
cd Hosp2MES-Agent-Public
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
.venv/Scripts/python.exe -m pip install playwright pytest
.venv/Scripts/python.exe -m playwright install chromium
cd frontend && npm ci && npm run build && cd ..
.venv/Scripts/python.exe -m pytest tests/ -q

# (optional) real DeepSeek Hero — needs LLM_API_KEY in .env
.venv/Scripts/python.exe run_llm_recovery.py --policy llm-strict
```

Full local artifacts are excluded from Git. Curated, sanitized evidence
is in `examples/evidence/`. Re-export any local run with
`python scripts/export_evidence.py hero|recovery <run_id>`.

---

<sub>All data is synthetic. Built with the Mesop M-series (MiniMax M3).</sub>
