# LONG_HORIZON_CONTEXT_AUDIT.md

> Audit of how the Hosp2MESAgent (`hosp2mes/agents/hosp2mes_agent.py`) builds the
> per-step context for the action policy in a long-horizon task, and whether
> history accumulates without bound.

## Conclusion

**The per-step LLM context is bounded.** No full history is ever re-sent, and
the prompt size stays roughly constant across a long task. There is **no
unbounded history accumulation** in the decision loop. (V1.2.2 does not change
this; it only documents and lightly trims the existing bounds.)

---

## 1. What each round's context is composed of

Every decision step builds a context and calls
`ActionPolicy.next_action(context)`. The prompt sent to the LLM is:

```
system prompt (fixed string, ~2.3 KB)
+ user message = JSON of:
    goal                    (the task instruction; fixed)
    current_subgoal         (id / description / success_condition / capabilities; fixed per subgoal)
    business_data           (product, codes, route, bom_materials, stages; fixed per task)
    progress_memory         (structured; bounded by the number of subgoals)
    current_url             (short string)
    visible_text            (page text, TRUNCATED to <= 3000 chars, 800 on trimmed retry)
    interactive_elements    (<= 60 elements, role + accessible_name only; 40 on trimmed retry)
    recent_actions          (ONLY the last 8 entries)
```

Source: `ActionPolicy._promptable()`.

## 2. How history is compressed

- **Recent actions** are a sliding window: `context["recent_actions"][-8:]`.
  The agent also caps its in-memory `recent` list to 12 entries
  (`_run_subgoal_loop`). Older actions are dropped, never re-sent.
- **Observations** are not accumulated in the prompt: only the *current*
  `visible_text` / `interactive_elements` are sent (and those are truncated).
- **Screenshots** are written to disk (`artifacts/runs/<run_id>/`) but are not
  re-sent to the policy (the policy is text-only in V1.2.x).

## 3. How memory updates

`ProgressMemory` is a small structured object (not a chat log):

- `from_plan(goal, plan_ids)` initializes one status entry per subgoal.
- `set_current(sg)` / `mark_completed(sg)` / `mark_failed(sg)` update statuses.
- `to_dict()` serializes it into the prompt — size is bounded by the number of
  subgoals (4 for the Hero), independent of how many GUI steps have run.

## 4. Is there unlimited history accumulation?

**No.** Everything sent to the LLM is either fixed (goal / business_data /
subgoal / system prompt) or explicitly truncated (`visible_text`, `elements`)
or windowed (`recent_actions` last 8). The full trace and per-step evidence
grow on disk, but they are output artifacts, not part of the decision prompt.

## 5. Notes / current limits (not optimized in this round)

- The prompt is **text-only**; screenshots are recorded but not fed to the
  policy. (A multimodal path is reserved for later.)
- `memory_snapshot` is recorded per step in evidence for auditability, but only
  the compact `to_dict()` form is sent to the LLM.
- The trim thresholds (3000/800 chars, 60/40 elements) are conservative and can
  be tuned; they were chosen to be safe, not measured against a token budget.
