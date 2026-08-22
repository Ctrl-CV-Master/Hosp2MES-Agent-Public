# Development Status

> Living status log for Hosp2MES-Agent-Public. Each phase is run and verified
> before moving on (Plan → Implement → Run → Test → Inspect → Fix → Retest →
> Document).

## Current Version

**V1.2 — Agent decision loop: Skill baseline + Agent S3 adapter + Hosp2MES policy agent**

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

- `pytest tests/ -q`: **39 passed** (32 prior + 3 agent-policy + 4 s3-adapter).
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
