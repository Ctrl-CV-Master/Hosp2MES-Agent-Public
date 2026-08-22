# Development Status

> Living status log for Hosp2MES-Agent-Public. Each phase is run and verified
> before moving on (Plan → Implement → Run → Test → Inspect → Fix → Retest →
> Document).

## Current Version

**V1.1.1 — Browser Hero Task hardened and passing; scoped semantic targets + state-based sync**

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
- [x] **V1.1.1 Scoped semantic targets** — `BrowserExecutor` resolves a target dict `{"within": {"role": "row", "text": "过滤"}, "role": "button", "name": "完成"}` by locating the semantic container first, then searching inside it against the *fresh* DOM every step.
- [x] **V1.1.1 SPA re-render sync** — `wait` gained state-based conditions (`visible` / `hidden` / `enabled` / `disabled` / `text_contains` / `text_not_contains`); every action is `observe → resolve fresh → execute → wait for state change → observe again`. No fixed `sleep` as the primary sync, no cached `ElementHandle` across Vue re-renders.
- [x] **V1.1.1 Execution page semantics** — each stage's "完成" button gained `aria-label="完成称量" / "完成溶解" / ...` (plain accessibility enhancement; no `data-next-action` / `agent-target` leaks).
- [x] **V1.1.1 Autonomy audit** — `AUTONOMY_AUDIT.md` confirms no task-id branching, no fixed per-task action array, no fixed-button-index targeting.

## Verified

- `pytest tests/ -q`: 32 passed (20 original + 3 V1.1 browser + 1 material GUI E2E + 3 V1.1.1 robustness tests + 5 helper/unit).
- `benchmark/e2e_probe.py`: MES-DEMO-001/002/003 api mode all success.
- Browser GUI material E2E (`MES-DEMO-GUI-001`): success, verified by independent REST read-back.
- Browser production-execution GUI E2E (`GUI-EXEC-001`): success.

## Browser Hero Task Status (MES-DEMO-003, `--env browser`)

> Honest status — updated after each run.

**V1.1.1 latest run (`MES-DEMO-003-20260822T131135Z`) — FULL PASS.**

```
run_id           : MES-DEMO-003-20260822T131135Z
gui_steps        : 61
success          : true
verifier_passed  : true
verifier_missing : []
final_state      : material_exists=true, bom_exists=true,
                   production_order_status=COMPLETED,
                   storage_status=STORED
```

The complete flow — 物料 → BOM → 生产指令 → 称量 → 溶解 → 过滤 → 分装 →
贴签 → 包装 → 入库 → 独立 Final State Verification — passes end-to-end through
real Chromium, with 61 before/61 after screenshots saved under
`artifacts/runs/MES-DEMO-003-20260822T131135Z/`.

## Known Issues

- `ApiEnv` is the deterministic test / CI backend; it is not the GUI path.
- `./mes_demo.db` is auto-created and git-ignored.
- (environment-only) `vite build` must run from the real path when the workspace
  is a junction; see README / tests use a prebuilt `dist/` + Python proxy.

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
