# Development Status

> Living status log for Hosp2MES-Agent-Public. Each phase is run and verified
> before moving on (Plan → Implement → Run → Test → Inspect → Fix → Retest →
> Document).

## Current Version

**V1.2.2 — Real DeepSeek long-horizon Hero verification (llm-strict)**

## Real LLM Hero verification (V1.2.2, honest)

- `REAL_LLM_HERO = PASS` — run_id `MES-DEMO-003-20260823T011158Z`:
  31 decision steps, **all** `policy_source=deepseek`, `fallback_count=0`,
  `invalid_action_count=0`, `premature_done_count=0`, `llm_model=deepseek-v4-flash`,
  `planner_source=deterministic`. Independent verification:
  `material_exists=true`, `bom_exists=true`, `production_order_status=COMPLETED`,
  `storage_status=STORED`, `4/4` subgoals completed.
- Full business chain via real GUI: Material → BOM → Production Order →
  称量 → 溶解 → 过滤 → 分装 → 贴签 → 包装 → 入库. REST API does not participate
  in GUI action decisions or business-state mutation; it is used only as an
  independent read-only verifier for subgoal completion checks and final-state
  verification.
- Per-subgoal stats: create_material 8 steps/8 calls, create_bom 7/7,
  create_production_order 7/7, execute_production 9/9.

### Failure analysis notes (from earlier attempts, fixed generically)

- `LLM_FORMAT`: `deepseek-v4-flash` is a reasoning model; it occasionally
  returned empty `content` (reasoning spent the token budget). Fixed generically
  by raising `max_tokens` to 8000 + bounded same-LLM retries with a trimmed
  prompt (never a deterministic fallback).
- `UI_TIMING` / infra: a transient SQLite "database is locked" surfaced as HTTP
  500 on the read-back. Fixed by a SQLite `timeout` and by making the
  read-back check tolerate transient errors (re-check next iteration).

## Completed (V1.2.2)

- [x] **Long-horizon prompt** — the LLM policy now receives `bom_materials`,
  `route`, `bom_version`, `production_stages` (with Chinese labels) and a
  workflow-aware system prompt (scoped targets, select, wait conditions).
- [x] **Long-horizon metrics** — `total_llm_latency_ms` / `avg_llm_latency_ms` /
  `invalid_action_count` / `llm_retry_count` / `premature_done_count` /
  `subgoals_total` / `subgoals_completed` / `per_subgoal_stats`.
- [x] **P0.3 provenance fields** — each step records `goal` + `memory_snapshot`
  (+ `value`) alongside the existing provenance; no private chain-of-thought.
- [x] **Premature-DONE guard** — a policy `done` is rejected unless the
  independent read-back agrees; `premature_done_count` is recorded.
- [x] **LONG_HORIZON_CONTEXT_AUDIT.md** — documents the bounded per-step context
  (no unbounded history accumulation).

## Real LLM verification (V1.2.1, honest)

- `REAL_LLM_GUI_001 = PASS` — run_id `MES-DEMO-GUI-001-20260822T151624Z`:
  8 decision steps, all `policy_source=deepseek`, `fallback_used=false`,
  `llm_model=deepseek-v4-flash`, `total_llm_calls=8`, `fallback_count=0`,
  independent verification `material_exists=true`.
- `REAL_LLM_VARIANT = PASS` — perturbed page (reordered fields, moved button,
  extra "草稿" button, irrelevant card) filled correctly by DeepSeek
  (`policy_source=deepseek` for all steps, no fallback, no draft-button hit).
- Evidence under `artifacts/runs/`: every step records `policy_source`,
  `llm_model`, `llm_latency_ms`, `llm_call_success`, `llm_parse_success`,
  `fallback_used`, `decision_rationale` + before/after screenshots.

## Completed (V1.2.1)

- [x] **Policy modes** — `--policy deterministic|llm|llm-strict` (CLI + Config +
  `AGENT_POLICY` env). `llm-strict` raises `PolicyStrictFailure` on any LLM
  call failure / JSON parse failure / invalid action / invalid target (no
  fallback).
- [x] **Policy provenance** — `PolicyDecision` carries `policy_source`,
  `llm_model`, `llm_latency_ms`, `llm_call_success`, `llm_parse_success`,
  `fallback_used`, `decision_rationale`; persisted per-step in evidence. No
  private chain-of-thought is stored.
- [x] **Local .env** — `Config.load()` loads a git-ignored `.env` (via
  python-dotenv with a fallback parser) and falls back to `OPENAI_*` for
  DeepSeek-compatible endpoints. The real key lives only in local `.env`.
- [x] **Planner provenance** — `planner_source` recorded (deterministic for now).
- [x] **Tests** — added `test_llm_strict_never_fallback`,
  `test_policy_provenance_llm_success_and_fallback`,
  `test_invalid_llm_action_fails_in_strict_mode` (mock responses; do not
  replace the real run evidence).

## Completed (V1.2)

- [x] **Agent collection** — new `hosp2mes/agents/` package: `skill_agent.py`
  (SemanticSkillAgent), `hosp2mes_agent.py` (Hosp2MESAgent + ActionPolicy),
  `agent_s3_adapter.py` (AgentS3Adapter).
- [x] **Skill baseline preserved** — V1.1 `BrowserAgent` is now
  `SemanticSkillAgent` (deterministic GUI baseline); `BrowserAgent` kept as a
  backward-compatible alias. It still passes the full Hero.
- [x] **Hosp2MESAgent decision loop** — one-action-per-step:
  `GOAL + SUBGOAL + MEMORY + OBSERVATION -> ActionPolicy.next_action() -> ONE
  action -> BrowserExecutor -> observe again`. Strictly structured output
  (`action/target/value/rationale`), no private chain-of-thought. A real LLM
  path is wired (DeepSeek-compatible), with a deterministic observation-driven
  fallback for `mock`/CI.
- [x] **Planner dynamic schema** — `Subgoal` carries `id` / `description` /
  `dependencies` / `success_condition` / `capabilities`; the LLM path may emit
  arbitrary subgoals; the deterministic planner is kept as fallback + test mode.
- [x] **Autonomy hardening** — the executor prefers an *exact* accessible-name
  match (so "新建指令" is not confused with "新建指令(草稿)"), surfaced by the
  variant-layout autonomy test.
- [x] **Agent S3 adapter** — real `gui-agents` import + construction verified.

## Agent S3 status (honest)

- **Identity**: `simular-ai/Agent-S` (12k+ stars), PyPI `gui-agents` v0.3.2,
  license **Apache-2.0**, Python `>=3.9,<=3.12`.
- **Real install**: `pip install gui-agents` succeeded in a Python 3.10 venv
  (pulls `paddlepaddle` / `paddleocr` / `pyautogui` / `pytesseract` /
  `pywinauto` …).
- **Real API**: `gui_agents.s3.agents.agent_s.AgentS3(worker_engine_params,
  grounding_agent, platform, ...).predict(instruction, observation)` and
  `gui_agents.s3.agents.grounding.OSWorldACI(...)` import and **construct**
  with their real signatures.
- **Real prediction**: BLOCKED. A real `predict()` needs (a) a worker LLM API
  key (OpenAI/Anthropic/Gemini/…), (b) a UI-TARS grounding-model endpoint
  (HF/vLLM/TGI), and (c) an OS-level ACI environment controller — none are
  available here. A live call raises honestly (no credentials / no endpoint).
  **Not executed, not faked.**

## Verified

- `pytest tests/ -q`: **42 passed** (32 prior + 3 agent-policy + 4 s3-adapter + 3 llm-policy-mode).
- `benchmark/e2e_probe.py`: MES-DEMO-001/002/003 api mode all success.
- SemanticSkillAgent (Skill baseline) full Hero: PASS (`COMPLETED` / `STORED`).
- Hosp2MESAgent (one-action-per-step) GUI-001: PASS via the policy loop.

## History (V1.0 → V1.1.1)

- V1.0 — Mock MES backend (20 REST endpoints), modular Agent (Planner / Memory
  / Verifier / Recovery / Evaluator / Trace), Vue 3 console, 20 tests, 3 api
  benchmark tasks.
- P0.1–P0.9 — BrowserEnv (Playwright), structured observation, semantic action
  executor, accessibility, GUI material E2E, Hero + CLI `--env`, evidence,
  tests, README.
- V1.1.1 — scoped semantic targets, state-based wait sync, execution-page
  `aria-label`, autonomy audit; full browser Hero PASS.

## Known Issues

- `ApiEnv` is the deterministic test / CI backend; it is not the GUI path.
- Agent S3 real execution is gated on external credentials + a grounding-model
  endpoint; the adapter is wired but cannot run here.
- `./mes_demo.db` is auto-created and git-ignored.
- (environment-only) `vite build` must run from the real path when the workspace
  is a junction; GUI tests use a prebuilt `dist/` + Python proxy.

## Commands Tested

```bash
# agent — api mode (deterministic CI)
PYTHONPATH=.:backend python -m hosp2mes.run --task MES-DEMO-001 --env api

# agent — browser mode, skill baseline (deterministic)
PYTHONPATH=.:backend python -m hosp2mes.run --task MES-DEMO-003 --env browser

# agent — browser mode, one-action-per-step policy
PYTHONPATH=.:backend python -m hosp2mes.run --task MES-DEMO-GUI-001 --env browser --agent hosp2mes

# tests
.venv/Scripts/python.exe -m pytest tests/ -q
```
