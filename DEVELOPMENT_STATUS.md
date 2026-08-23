# Development Status

> Living status log for Hosp2MES-Agent-Public. Each phase is run and verified
> before moving on (Plan → Implement → Run → Test → Inspect → Fix → Retest →
> Document).

## Current Version

**V1.3.0 — Adaptive Recovery + State-Diff Local Replanning (final core algorithm version)**

## Real LLM Recovery Hero verification (V1.3, honest)

- `REAL_LLM_RECOVERY_HERO = PASS` — run_id `MES-DEMO-RECOVERY-001-20260823T035901Z`
  (clean final run, `--agent hosp2mes --policy llm-strict`, `planner=deterministic`).
- Fault `FAULT-BOM-001` (`discard_state_change`, once) was injected by the
  **test harness** via the agent's generic subgoal-completion observer — the
  agent's policy/prompt/observation never saw the fault id/type/trigger.
  `FAULT_TRIGGERED=true`.
- After `create_bom` completed, the harness discarded the BOM; the agent then
  hit `create_production_order` with the BOM missing, detected the state diff
  (`bom.exists` expected true / actual false), diagnosed `MISSING_PREREQUISITE`,
  locally re-planned (`preserve create_material`, `reactivate create_bom`,
  `invalidate create_bom/create_production_order/execute_production`,
  `resume_from create_bom`), repaired the BOM through the GUI and resumed.
- Metrics: `gui_steps=41`, `total_llm_calls=41`, **all** `policy_source=deepseek`,
  `fallback_count=0`, `premature_done_count=3` (bounded premature-DONE budget
  triggered recovery), `recovery_count=1`, `recovery_success_count=1`,
  `recovery_failure_count=0`, `total_recovery_steps=15`,
  `reexecuted_completed_subgoals=0`, `local_replan_count=1`, `state_diff_count=1`.
- Independent verification: `material_exists=true`, `bom_exists=true`,
  `production_order_status=COMPLETED`, `storage_status=STORED`. The material
  subgoal was **never** re-executed (local recovery, not a restart).

## V1.3 — Adaptive Recovery (what was built)

- [x] **Canonical business state + state diff** — `hosp2mes/state/`:
  `BusinessState` (material/bom/production_order/stages), `StateReader` (reads
  only from the independent read-only verifier), generic nested-path `diff()`
  with `matched/missing/mismatched/conflicting/satisfied/unexpected`.
- [x] **Failure diagnosis** — `hosp2mes/recovery/diagnosis.py`: generic
  categories (`MISSING_PREREQUISITE`/`STATE_MISMATCH`/`ACTION_FAILED`/
  `UI_TIMING`/`NAVIGATION_ERROR`/`FORM_VALIDATION`/`PREMATURE_DONE`/
  `TRANSIENT_BACKEND`/`UNKNOWN`); no task-specific category.
- [x] **Dependency-aware local replanning** — `repair_planner.py` finds the
  earliest unsatisfied subgoal and emits `preserve`/`reactivate`/`invalidate`/
  `resume_from` against the plan dependency graph.
- [x] **Recovery decision loop** — `RecoveryEngine` (state diff → diagnosis →
  local repair plan) with `max_recovery_attempts=3` retry budget. The
  `Hosp2MESAgent` now runs a mutable subgoal queue and re-plans locally on
  failure instead of restarting. Subgoal satisfaction is decided by the live
  state diff (never "clicked the button", never agent memory).
- [x] **Recovery trace + metrics** — `recovery-XXX.json` under
  `artifacts/runs/<run_id>/recovery/`; `recovery_metrics` (recovery_count/
  success/failure, total_recovery_steps, reexecuted_completed_subgoals,
  local_replan_count, state_diff_count) in `summary.json`; `recovery_history`
  appended to ProgressMemory (kept bounded).
- [x] **Fault injection decoupled** — `benchmark/faults/` `FaultInjector`/
  `FaultSpec` (test harness only). The agent only observes GUI result + read-only
  business state; it never learns the fault id/type/trigger.
- [x] **Bounded premature-DONE budget** — a policy `done` that persistently
  disagrees with the read-back (≥3×) triggers recovery instead of looping.
- [x] **Regression tests** — `tests/agent/test_recovery.py`: state diff, missing
  BOM repair plan, stage-interruption repair plan, retry budget,
  reexecuted_completed_subgoals==0, premature-DONE diagnosis, full local-replan
  E2E (scripted policy + fault injector). 52 tests total, all green.

> State-diff-based local recovery demonstrated in synthetic MES fault scenarios
> (not a general-purpose self-healing industrial agent claim).



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
