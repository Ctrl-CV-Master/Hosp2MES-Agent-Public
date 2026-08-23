# Portfolio Audit (V1.3.1)

Honest, item-by-item audit of Hosp2MES-Agent-Public as a portfolio piece.
Nothing in this document is "stretch" — the only claims made are those the
code and `examples/evidence/` actually back up.

## 1. 30-second HR test — *can a non-technical reviewer understand it?*

| question | answer (visible on README first screen) |
|---|---|
| What is it? | "A long-horizon GUI agent for Manufacturing Execution Systems" |
| What stack? | LLM (DeepSeek) + Playwright Chromium + Vue 3 + FastAPI + SQLite |
| What is different? | "Observe → Decide → Act" loop with structured memory, evidence-gated completion and state-diff local recovery |
| Has it really run? | Yes — `Long-Horizon Hero` (31 deepseek decisions, 0 fallback) and `Recovery Hero` (fault → state diff → repair → resume, 0 reexecuted) are real, reproducible runs published under `examples/evidence/` |
| Can I see it? | Demo GIF at the top (`assets/demo/hosp2mes-agent-demo.gif`), architecture diagram (`assets/architecture.png`) |

PASS.

## 2. 3-minute engineer test — *can a reviewer find the important files?*

| reviewer question | where to look |
|---|---|
| Where is the agent loop? | `hosp2mes/agents/hosp2mes_agent.py` — `Hosp2MESAgent._run` + `ActionPolicy` |
| Where is the browser env? | `hosp2mes/observation/browser_env.py` + `hosp2mes/executor/browser_executor.py` |
| Where is the planner? | `hosp2mes/planner/planner.py` — `Planner` + `Subgoal` (dependency graph) |
| Where is memory? | `hosp2mes/memory/progress_memory.py` — `ProgressMemory` |
| Where is the verifier? | `hosp2mes/verifier/verifier.py` — `EvidenceVerifier` |
| Where is recovery? | `hosp2mes/recovery/` (state diff → diagnosis → repair planner → engine) |
| Where are the tests? | `tests/` (54 pytest) — `tests/agent/test_recovery.py` for the recovery E2E |
| Where is the evidence? | `examples/evidence/` + `scripts/export_evidence.py` |
| Where is the demo? | `assets/demo/hosp2mes-agent-demo.gif` (built by `scripts/build_demo_gif.py`) |

PASS.

## 3. Resume-claim audit — *what can I safely say in an interview?*

Format: each claim is tagged **IMPLEMENTED** (in this repo, this commit),
**VERIFIED** (ran and produced the evidence), **ADAPTER ONLY** (wired
but not runtime-evaluated), or **NOT IMPLEMENTED** (do not claim).

| claim | status | backing |
|---|---|---|
| "Real LLM decision loop, one action per step" | **IMPLEMENTED + VERIFIED** | `Hosp2MESAgent._run_subgoal_loop` (31 deepseek decisions, all `policy_source=deepseek`) |
| "Three policy modes (deterministic / llm / llm-strict)" | **IMPLEMENTED + VERIFIED** | `ActionPolicy.next_action`; `tests/agent/test_llm_policy_modes.py`; real `llm-strict` Hero run |
| "Long-horizon Hero (Material → BOM → Order → 7 stages → Storage)" | **IMPLEMENTED + VERIFIED** | `MES-DEMO-003-20260823T011158Z` (31 steps, 0 fallback, all verified) |
| "Evidence-gated completion (agent DONE ≠ task success)" | **IMPLEMENTED + VERIFIED** | `EvidenceVerifier.verify` + independent read-only REST client; final-state verified for both Hero runs |
| "State-diff adaptive recovery" | **IMPLEMENTED + VERIFIED** | `hosp2mes/state/` + `hosp2mes/recovery/`; `MES-DEMO-RECOVERY-001-20260823T042516Z` (fault → `MISSING_PREREQUISITE` → local replan → 7 repair steps → 0 reexecuted) |
| "Real execution counters, not a queue derivation" | **IMPLEMENTED + VERIFIED** | `Hosp2MESAgent.subgoal_execution_counts`; `recovery_metrics.reexecuted_completed_subgoals` is computed from those counters |
| "Recovery steps bounded to the repair episode" | **IMPLEMENTED + VERIFIED** | `RecoveryTrace.repair_start_step / repair_end_step / repair_step_count / repair_verified`; total_recovery_steps = 7 (only the BOM repair), not 15 (was over-counting trigger→task-end) |
| "Public reproducible evidence" | **IMPLEMENTED + VERIFIED** | `examples/evidence/{long_horizon_hero,recovery_hero}/` exported from real runs; URLs sanitized; no secrets |
| "GitHub Actions CI" | **IMPLEMENTED** (verified locally; not yet seen by GitHub Actions until the next push triggers it) | `.github/workflows/ci.yml` — backend pytest + api e2e + frontend build + browser e2e (deterministic) |
| "Agent S3 integration" | **ADAPTER ONLY** | `hosp2mes/agents/agent_s3_adapter.py` — `gui-agents` (Apache-2.0) is installed, `AgentS3` and `OSWorldACI` construct OK, but a real `predict()` requires a worker LLM key **and** a UI-TARS grounding endpoint. Do not claim "Agent S3 benchmark PASS". |
| "Production-ready industrial AGI" | **NOT IMPLEMENTED** | The MES is a synthetic Mock (Vue 3 + FastAPI + SQLite) with fictional data. Do not claim this in an interview. |
| "General-purpose self-healing agent" | **NOT IMPLEMENTED** | Recovery is state-diff local re-planning in a single fault-injection scenario (Missing-BOM). Do not generalize. |

## 4. Things this repo is **not**

- Not a multi-tenant / multi-site MES.
- Not a research paper — it is an engineering portfolio build (V1.0 → V1.3.1,
  `TECHNICAL_CORE_STATUS = FROZEN`).
- Not a plug-and-play connector to a real hospital / factory.
- Not a benchmark against AgentBench / OSWorld — Hero is a single MES
  scenario; Agent S3 is adapter-only.
- Not a guarantee that the Agent S3 runtime works (only the import and
  construction have been verified).

## 5. Self-imposed disciplines

- **No private chain-of-thought is stored or emitted.** Only short
  public `decision_rationale`.
- **No task-specific control flow** in the browser agent — see
  [AUTONOMY_AUDIT.md](AUTONOMY_AUDIT.md).
- **Real DeepSeek is required for the long-horizon Hero**; the
  deterministic `MockLLM` is for CI / offline and never produces an
  `llm-strict` PASS for a real Hero.
- **Honest failure records** — every `REAL_LLM_*` result is documented
  with the real run_id; `PARTIAL` and `FAIL` are recorded as such.

---

*Audit performed against commit `29a62f2` (V1.3.1).*
