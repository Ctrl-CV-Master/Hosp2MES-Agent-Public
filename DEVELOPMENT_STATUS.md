# Development Status

> Living status log for Hosp2MES-Agent-Public. Each phase is run and verified
> before moving on (Plan → Implement → Run → Test → Inspect → Fix → Retest →
> Document).

## Current Version

**V1.1 — Real Browser GUI Agent (Playwright) landed; deterministic ApiEnv kept as CI backend**

## Completed

- [x] **V1.0 Productization** — Mock MES backend (20 REST endpoints), modular Agent (Planner / Memory / Verifier / Recovery / Evaluator / Trace), Vue 3 console, 20 pytest tests, 3 api benchmark tasks.
- [x] **P0.1 BrowserEnv** — `hosp2mes/observation/browser_env.py` (Playwright), `browser_observation.py` (structured `BrowserObservation`), `dom_extractor.py` (semantic DOM/a11y extraction). `observe()` returns current_url / title / visible_text / interactive_elements / accessibility / screenshot / timestamp — never from REST.
- [x] **P0.2 GUI Action Layer** — `hosp2mes/executor/browser_executor.py` realizes the unified verbs (`click` / `type` / `select` / `scroll` / `press` / `wait` / `navigate` / `back` / `extract`) via role + accessible name / label / text. No task-id branching, no hand-written XPath.
- [x] **P0.3 Mock MES Accessibility** — Materials / BOMs / Orders / Execution views gained `aria-label` + form semantics on interactive controls; no agent-only hints (`data-next-action` etc.) added.
- [x] **P0.4 True GUI E2E** — `MES-DEMO-GUI-001` creates a material end-to-end through Chromium; final verification uses an independent read-only ApiEnv; `test_gui_material_creation_e2e` proves the state change came from the GUI (all recorded actions are GUI verbs, no business REST verb).
- [x] **P0.5/P0.6 Hero + CLI** — `BrowserAgent` implements the full workflow intents (material → BOM → order → 7-stage execution); CLI gained `--env api|browser` and `--headless`.
- [x] **P0.7 Evidence** — `artifacts/runs/<run_id>/` with `steps.json`, `summary.json` and per-step before/after screenshots; only public action rationale is stored.
- [x] **P0.8 Tests** — added `test_browser_observation`, `test_browser_executor`, `test_gui_material_creation_e2e`; original 20 tests remain green.
- [x] **P0.9 README** — distinguishes api mode (deterministic CI) from browser mode (real GUI); Quick Start runs from a fresh clone (`git clone` → `python -m venv` → `pip install` → `playwright install chromium` → `npm install`), no author-local `D:\` paths.
- [x] **P0.10 Discipline** — phased commits (see git log).

## Verified

- `pytest tests/ -q`: original 20 tests + 3 browser tests all pass.
- `benchmark/e2e_probe.py`: MES-DEMO-001/002/003 api mode all success.
- Browser GUI material E2E (`MES-DEMO-GUI-001`): success, verified by independent REST read-back.

## Browser Hero Task Status (MES-DEMO-003, `--env browser`)

> Honest status — updated after each run. No claim is faked.

Latest run (`MES-DEMO-003-20260822T123703Z`, evidence under `artifacts/runs/`):

- **Material**: ✅ created via GUI (verified independently).
- **BOM**: ✅ created via GUI (verified independently).
- **Production order**: ✅ created via GUI.
- **7-stage execution**: ⏳ partial — agent completed some stages, then the
  next `click 完成` resolved to a disabled button and timed out. The order
  ended in `IN_PROGRESS`, `storage_status NOT_STORED`.
- **Final independent verification**: ❌ `missing=['production_order_status','storage_status']`.

```
run_id           : MES-DEMO-003-20260822T123703Z
gui_steps        : 53
steps_reached    : 46  (into execute_production)
failed_subgoal   : execute_production
failure_reason   : TimeoutError on `click 完成` — first resolved button was
                   disabled (Element-Plus table re-render race).
final_state      : material_exists=true, bom_exists=true,
                   production_order_status=IN_PROGRESS,
                   storage_status=NOT_STORED
verifier_passed  : False
```

This run is **partial**. The acceptance gate `MES-DEMO-GUI-001` (material
creation through the GUI) passes reliably and is covered by
`tests/agent/test_gui_e2e.py`. The full Hero workflow in browser mode needs
the production-stage click loop hardened (e.g. observe before each click and
re-resolve when the table re-renders) before it can be claimed as stable.

## Known Issues

- `ApiEnv` is the deterministic test / CI backend; it is not the GUI path.
- Browser-mode Hero task may be PARTIAL on first pass — recorded honestly, never faked.
- `./mes_demo.db` is auto-created and git-ignored.

## Commands Tested

```bash
# backend
cd backend && uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm run dev

# agent — api mode (deterministic CI)
cd <repo-root> && PYTHONPATH=.:backend python -m hosp2mes.run --task MES-DEMO-001 --env api

# agent — browser mode (real GUI)
cd <repo-root> && PYTHONPATH=.:backend python -m hosp2mes.run --task MES-DEMO-GUI-001 --env browser --headless true

# benchmark (api, isolated)
cd <repo-root> && PYTHONPATH=.:backend python benchmark/e2e_probe.py

# tests
cd <repo-root> && .venv/Scripts/python.exe -m pytest tests/ -q
```
