# AUTONOMY_AUDIT.md — Browser Agent Autonomy Audit

> Scope: `hosp2mes/agent/browser_agent.py`, `hosp2mes/executor/browser_executor.py`,
> `hosp2mes/observation/browser_env.py`, `hosp2mes/executor/actions.py` and the
> browser runners (`run_hero_browser.py`, `hosp2mes/run.py`).
>
> Conclusion: **TASK_SPECIFIC_HARDCODING = false**. The browser agent contains no
> `if task_id == ...` branch, no fixed per-task action array, no hardcoded
> MES-DEMO-003 click sequence and no fixed-button-index targeting.

---

## 1. How the goal enters the Agent

The goal never appears as a literal inside the agent code. It is loaded from a
task file by `TaskLoader.from_yaml(...)` (`hosp2mes/agent/agent.py`) into a
`Task` dataclass whose fields are **business data**:

- `instruction` / `goal` — the natural-language objective
- `product`, `target_material_code`, `target_material_name`, `material_type`,
  `unit`, `specification` — material data
- `bom_code`, `bom_materials` — BOM data
- `order_code`, `batch`, `quantity` — production-order data
- `expected_final_state` — the acceptance conditions the Verifier checks

`BrowserAgent.__init__` copies these into an `ExecContext` (the same context the
REST agent uses). `MES-DEMO-003`, `MAT-DEMO-KCL`, `ORD-DEMO-003`, etc. appear
**only** in the task YAML (`benchmark/tasks/*.yaml`) and in the runner scripts
that pass a task id to the CLI — never in the decision/action code inside
`hosp2mes/`.

## 2. How observation enters the decision

Every GUI step calls `self.env.observe()` before acting
(`BrowserAgent._run_actions`). `observe()` returns a `BrowserObservation` built
**entirely from the live DOM** by `dom_extractor`:

- `current_url`, `title`, `visible_text`
- `interactive_elements` (role + accessible name + placeholder + text)

The agent uses this snapshot for two things: (a) idempotency checks — e.g.
"is my material code already present in `visible_text`?" — and (b) evidence /
`state_changed` accounting. The *next action* is chosen from the generic GUI
step sequences below, but every action is executed against a **fresh** locator
resolved from the current DOM (no cached `ElementHandle` survives a re-render).

## 3. Who produces the next action

The next action is produced by the subgoal skill methods in `BrowserAgent` as a
**small, generic, data-driven sequence of abstract `Action` objects**, e.g.:

```python
Action("click", target="新建物料", params={"role": "button"})
Action("type", target="物料编码", value=self.ctx.material_code)
Action("select", target="类型", value=self.ctx.material_type)
```

- The element references are **public UI semantics** (button text "新建物料",
  field label "物料编码", combobox "类型"), not XPath/CSS/coordinates.
- The **values** come from `self.ctx` (the task's business data), not from
  literals.
- The production-execution stage loop iterates the canonical `PRODUCTION_STAGES`
  list and, for each stage, targets the row by its **Chinese label** and clicks
  the button **named "完成" inside that row** — a *scoped semantic target*:

```python
Action("click", target={"within": {"role": "row", "text": zh},
                        "role": "button", "name": "完成"})
```

There is no `if task.task_id == "MES-DEMO-003": ...` branch; the same skill
would drive any task whose `expected_final_state` triggers the same subgoals.

## 4. How the Planner decides subgoals

`Planner.plan(goal, expected_final_state)` (`hosp2mes/planner/planner.py`) maps
the task's **expected final state** to an ordered subgoal list via
`SUBGOAL_TEMPLATES`:

| condition | subgoal |
|-----------|---------|
| `material_exists` | `create_material` |
| `bom_exists` | `create_bom` |
| `production_order_status` | `create_production_order` |
| `storage_status` | `execute_production` |

It is **data-driven**: a task with only `material_exists` yields only
`create_material` (that is exactly `MES-DEMO-GUI-001`), while the full Hero
yields all four. Nothing is keyed to a product name or task id.

## 5. What BrowserExecutor is responsible for (and only for)

`BrowserExecutor` is the single place that touches Playwright locators. Its
responsibility is narrow: translate an abstract `Action` into **one** Playwright
operation, resolving the element by role + accessible name / label / placeholder
text — optionally scoped to a semantic container (`within`) or to the topmost
open dialog. It also realizes state-based `wait` conditions
(`visible` / `hidden` / `enabled` / `disabled` / `text_contains` / ...).

It does **not** know about tasks, products, materials, or subgoals. It has no
concept of "MES-DEMO-003" or "the third button".

## 6. Task-specific control flow — present or absent?

**Absent.** Verified by search:

- `task_id` appears in `browser_agent.py` only in docstrings and as opaque
  metadata (`run_id`, trace/evidence records) — never in a branch condition.
- `MES-DEMO-003` / `MAT-DEMO-KCL` / `BOM-DEMO-KCL` / `ORD-DEMO-003` / `DEMO-KCL`
  appear only in `benchmark/tasks/*.yaml` and in `run_hero_browser.py`
  (a CLI wrapper that passes `--task MES-DEMO-003`, exactly like the user would).
- `nth(...)` / `.first` appear only inside executor *helpers* that pick the first
  *visible/enabled* element among semantic matches (`_first_visible`,
  `_topmost_dialog`, `_first_enabled`). They are never a targeting primitive
  chosen by the agent, and no skill emits an index.

## 7. Items to eliminate

None. No task-specific control flow was found, so nothing needed removal in
this audit.
