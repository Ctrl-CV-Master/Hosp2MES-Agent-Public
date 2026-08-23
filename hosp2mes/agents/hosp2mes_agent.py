"""Hosp2MESAgent — a true one-action-per-step decision loop.

Unlike :class:`~hosp2mes.agents.skill_agent.SemanticSkillAgent` (which emits a
whole per-subgoal action list up front), this agent runs a **decision loop**:

    GOAL + CURRENT SUBGOAL + STRUCTURED MEMORY + CURRENT BROWSER OBSERVATION
        -> ActionPolicy.predict_one() -> ONE NEXT ACTION
        -> BrowserExecutor -> new observation
        -> ActionPolicy.predict_one() -> ...

Every iteration produces exactly one next GUI action. The action is decided from
the *live* observation (url / visible text / interactive elements) plus the
structured progress memory, never from a pre-written action array.

Two policy backends share the same interface:

* **LLM** (``ActionPolicy`` with a real model) — builds a prompt from the
  context and asks the model to return one structured action. Used when an LLM
  provider + API key are configured.
* **Deterministic fallback** — an observation-driven form/flow policy used in
  ``mock`` mode (CI / offline), so the loop is still genuinely observable and
  emits one action at a time.

The policy output is strictly structured and public-safe::

    {
      "action": "click|type|select|scroll|wait|back|done",
      "target": {...} | "...",
      "value": ...,
      "rationale": "short public rationale"
    }

No private chain-of-thought is emitted or stored.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from hosp2mes.agent.agent import PRODUCTION_STAGES, Task
from hosp2mes.config import Config
from hosp2mes.evaluation.evaluator import Evaluator
from hosp2mes.evidence.evidence import EvidenceWriter, make_run_id
from hosp2mes.executor.actions import Action
from hosp2mes.executor.executor import ExecContext
from hosp2mes.memory.progress_memory import ProgressMemory
from hosp2mes.observation.browser_env import BrowserEnv
from hosp2mes.observation.browser_observation import BrowserObservation
from hosp2mes.planner.planner import Plan, Planner, Subgoal
from hosp2mes.trace.trace import TraceRecorder
from hosp2mes.verifier.verifier import EvidenceVerifier


# Generic form specs keyed by *capability* (NOT task id). Each spec describes a
# business form in terms of public UI semantics plus the ExecContext field that
# provides the value. This is the same data a human would read off the form.
_FORM_SPECS: dict[str, dict] = {
    "create_material": {
        "page": "/materials",
        "open": "新建物料",
        "save": "保存",
        "fields": [
            ("物料编码", "material_code", "type"),
            ("物料名称", "material_name", "type"),
            ("类型", "material_type", "select"),
            ("单位", "unit", "type"),
            ("规格", "specification", "type"),
        ],
    },
    "create_bom": {
        "page": "/boms",
        "open": "新建 BOM",
        "save": "保存",
        "fields": [
            ("BOM 编码", "bom_code", "type"),
            ("产品", "product", "type"),
            ("版本", "version", "type"),
            ("工艺路线", "route", "type"),
        ],
    },
    "create_production_order": {
        "page": "/orders",
        "open": "新建指令",
        "save": "保存",
        "fields": [
            ("指令号", "order_code", "type"),
            ("产品", "product", "type"),
            ("批次", "batch", "type"),
            ("数量", "quantity", "type"),
        ],
    },
}


VALID_ACTIONS = {"click", "type", "input", "select", "scroll", "press",
                 "wait", "back", "navigate", "extract", "done"}


@dataclass
class PolicyDecision:
    """One decision from the action policy, with full provenance.

    The provenance fields make it auditable *which* source produced the action
    and whether the LLM path was used honestly. No private chain-of-thought is
    stored — ``rationale`` is a short public rationale only.
    """
    action: str = "done"
    target: Any = ""
    value: Any = None
    params: dict = field(default_factory=dict)
    rationale: str = ""
    policy_source: str = "deterministic"   # deepseek | deterministic | agent_s3
    llm_model: str = ""
    llm_latency_ms: int | None = None
    llm_call_success: bool = False
    llm_parse_success: bool = False
    fallback_used: bool = False
    llm_error: str = ""

    @staticmethod
    def from_dict(d: dict, **prov) -> "PolicyDecision":
        return PolicyDecision(
            action=d.get("action", "done"),
            target=d.get("target", ""),
            value=d.get("value"),
            params=d.get("params", {}) or {},
            rationale=d.get("rationale", ""),
            **prov,
        )

    def provenance(self) -> dict:
        return {
            "policy_source": self.policy_source,
            "llm_model": self.llm_model,
            "llm_latency_ms": self.llm_latency_ms,
            "llm_call_success": self.llm_call_success,
            "llm_parse_success": self.llm_parse_success,
            "fallback_used": self.fallback_used,
            "decision_rationale": self.rationale,
        }


class PolicyStrictFailure(RuntimeError):
    """Raised in ``llm-strict`` mode when the LLM path fails (no fallback)."""

    def __init__(self, decision: "PolicyDecision"):
        super().__init__(
            f"llm-strict: LLM decision failed "
            f"(call_success={decision.llm_call_success}, "
            f"parse_success={decision.llm_parse_success}, error={decision.llm_error!r})"
        )
        self.decision = decision


class ActionPolicy:
    """Produces ONE next action from a policy context.

    Three modes:

    * ``deterministic`` — always use the deterministic observation-driven policy.
    * ``llm`` — prefer the real LLM; on failure, fall back to deterministic and
      mark ``fallback_used=True``.
    * ``llm-strict`` — only the real LLM. Any call failure / parse failure /
      invalid action / invalid target raises :class:`PolicyStrictFailure`
      (the whole task FAILS, no fallback).
    """

    def __init__(self, config: Config, ctx: ExecContext, llm=None):
        self.config = config
        self.ctx = ctx
        self.mode = (config.policy or "deterministic").strip().lower()
        if self.mode not in ("deterministic", "llm", "llm-strict"):
            raise ValueError(f"unknown policy mode: {self.mode!r}")

        self._llm = llm
        if self._llm is None and (config.use_real_llm() or self.mode in ("llm", "llm-strict")):
            from hosp2mes.llm import build_llm

            self._llm = build_llm(config)

        if self.mode in ("llm", "llm-strict"):
            from hosp2mes.llm import MockLLM

            if self._llm is None or isinstance(self._llm, MockLLM):
                raise ValueError(
                    f"policy mode {self.mode!r} requires a real LLM provider + API key"
                )
        self.invalid_action_count = 0
        self.llm_retry_count = 0

    # ---- public ----------------------------------------------------------
    def next_action(self, context: dict) -> PolicyDecision | None:
        """Return one provenance-carrying decision, or None to signal done."""
        if self.mode == "deterministic":
            d = self._deterministic_next_action(context)
            return PolicyDecision.from_dict(d, policy_source="deterministic") if d else None

        decision = self._try_llm(context)
        if decision.action:
            return decision

        if self.mode == "llm-strict":
            raise PolicyStrictFailure(decision)

        # "llm" mode: honest fallback, provenance preserved.
        d = self._deterministic_next_action(context)
        if d is None:
            return None
        return PolicyDecision.from_dict(
            d,
            policy_source="deterministic",
            llm_model=decision.llm_model,
            llm_latency_ms=decision.llm_latency_ms,
            llm_call_success=decision.llm_call_success,
            llm_parse_success=decision.llm_parse_success,
            fallback_used=True,
            llm_error=decision.llm_error,
        )

    # ---- LLM path --------------------------------------------------------
    def _try_llm(self, context: dict) -> PolicyDecision:
        from hosp2mes.llm import DeepSeekLLM

        model = getattr(self._llm, "model", self.config.llm_model) or ""
        base = PolicyDecision(action="", policy_source="deepseek", llm_model=model)

        # A DeepSeek reasoning model occasionally returns an empty ``content``
        # (reasoning spent but no final answer — a known behaviour when the
        # reasoning consumes the token budget) or an unparseable JSON. Retry the
        # *same* LLM (never a deterministic fallback) a bounded number of times,
        # with a large token budget and a progressively trimmed prompt. This is
        # a generic robustness mechanism, not task-specific.
        max_attempts = 5
        for attempt in range(max_attempts):
            t0 = time.time()
            try:
                trim = attempt >= 2
                user = json.dumps(self._promptable(context, trim=trim),
                                  ensure_ascii=False)
                text = self._llm.complete(_LONG_HORIZON_SYSTEM_PROMPT, user, max_tokens=8000)
                base.llm_call_success = True
                base.llm_latency_ms = int((time.time() - t0) * 1000)
                if not text or not text.strip():
                    raise ValueError("empty LLM content")
                parsed = DeepSeekLLM.parse_json_block(text)
                base.llm_parse_success = True
                break
            except Exception as exc:
                base.llm_latency_ms = int((time.time() - t0) * 1000)
                base.llm_error = f"{type(exc).__name__}: {exc}"
                if attempt < max_attempts - 1:
                    self.llm_retry_count += 1
                    continue
                return base

        # Parse + validate (already parsed above).
        action = parsed.get("action")
        error = self._validate_action(parsed)
        if error:
            self.invalid_action_count += 1
            base.llm_error = error
            return base  # action stays "" -> caller treats as failure
        base.action = action
        base.target = parsed.get("target")
        base.value = parsed.get("value")
        base.params = parsed.get("params", {}) or {}
        base.rationale = parsed.get("rationale", "")
        return base

    @staticmethod
    def _validate_action(parsed: dict) -> str | None:
        action = parsed.get("action")
        if action not in VALID_ACTIONS:
            return f"invalid action {action!r}"
        target = parsed.get("target")
        if action in ("click", "type", "input", "select", "scroll", "press", "extract"):
            if not target:
                return f"action {action} requires a target"
            if isinstance(target, dict) and not (target.get("name") or target.get("text")
                                                 or target.get("within")):
                return f"action {action} target dict missing name/within"
        if action == "select" and not parsed.get("value"):
            return "select requires a value"
        if action == "navigate" and not target:
            return "navigate requires a target"
        if action == "wait" and not (parsed.get("params") or parsed.get("value")):
            return "wait requires params or value"
        return None

    def _promptable(self, context: dict, trim: bool = False) -> dict:
        # Trim the observation to a bounded, prompt-safe size.
        elements = context.get("interactive_elements", [])
        max_elements = 40 if trim else 60
        max_text = 800 if trim else 3000
        summary = [
            {"role": e.get("role"), "name": e.get("accessible_name") or e.get("text")}
            for e in elements[:max_elements]
        ]
        return {
            "goal": context.get("goal"),
            "current_subgoal": context.get("current_subgoal"),
            "business_data": {
                "product": self.ctx.product,
                "material_code": self.ctx.material_code,
                "material_name": self.ctx.material_name,
                "material_type": self.ctx.material_type,
                "unit": self.ctx.unit,
                "specification": self.ctx.specification,
                "bom_code": self.ctx.bom_code,
                "bom_version": _BOM_VERSION,
                "route": _ROUTE,
                "bom_materials": [
                    {"material_code": m.get("material_code"), "quantity": m.get("quantity")}
                    for m in (self.ctx.bom_materials or [])
                ],
                "order_code": self.ctx.order_code,
                "batch": self.ctx.batch,
                "quantity": self.ctx.quantity,
                "production_stages": _PRODUCTION_STAGE_HINTS,
            },
            "progress_memory": context.get("progress_memory"),
            "current_url": context.get("current_url"),
            "visible_text": (context.get("visible_text") or "")[:max_text],
            "interactive_elements": summary,
            "recent_actions": context.get("recent_actions", [])[-8:],
        }

    # ---- deterministic fallback -----------------------------------------
    def _deterministic_next_action(self, context: dict) -> dict | None:
        sg = context.get("current_subgoal") or {}
        sg_id = sg.get("id", "")
        capabilities = sg.get("capabilities", []) or []
        cap = capabilities[0] if capabilities else sg_id
        elements = context.get("interactive_elements", [])
        recent = context.get("recent_actions", [])

        if cap in _FORM_SPECS:
            return self._form_next(cap, context, elements, recent)

        if cap == "execute_production":
            return self._production_next(context, recent)

        # Unknown capability: signal done so the loop defers to verification.
        return {"action": "done", "rationale": f"no GUI policy for capability {cap!r}"}

    def _form_next(self, cap, context, elements, recent) -> dict:
        spec = _FORM_SPECS[cap]

        # If the last action was a save click, wait for the dialog to close.
        last = recent[-1] if recent else None
        if last and last.get("action") == "click" and _target_name(last.get("target")) == spec["save"]:
            return {
                "action": "wait",
                "params": {"for": "hidden", "role": "dialog", "timeout": 8000},
                "rationale": "wait for the dialog to close after save",
            }

        # If we are not on the target page yet, navigate there.
        url = context.get("current_url") or ""
        if spec.get("page") and spec["page"] not in url:
            return {
                "action": "navigate",
                "target": spec["page"],
                "rationale": f"navigate to {spec['page']}",
            }

        # After navigating, wait for the open button to appear (Vue mounted).
        if last and last.get("action") == "navigate":
            return {
                "action": "wait",
                "params": {"for": "visible", "role": "button",
                           "name": spec["open"], "timeout": 8000},
                "rationale": f"wait for the '{spec['open']}' button to render",
            }

        names = [e.get("accessible_name") or e.get("text") or "" for e in elements]
        dialog_open = any(spec["save"] in n for n in names)

        if not dialog_open:
            return {
                "action": "click",
                "target": {"role": "button", "name": spec["open"]},
                "rationale": f"open the {spec['open']} dialog",
            }

        # Dialog is open: fill the next field that hasn't been set yet.
        done_labels = {_target_name(r.get("target")) for r in recent}
        for label, ctx_attr, kind in spec["fields"]:
            if label in done_labels:
                continue
            value = getattr(self.ctx, ctx_attr, "")
            if kind == "select":
                return {
                    "action": "select",
                    "target": {"role": "combobox", "name": label},
                    "value": str(value or ""),
                    "rationale": f"select '{label}' = {value}",
                }
            return {
                "action": "type",
                "target": {"role": "textbox", "name": label},
                "value": str(value or ""),
                "rationale": f"fill '{label}' = {value}",
            }

        # All fields set -> save.
        return {
            "action": "click",
            "target": {"role": "button", "name": spec["save"]},
            "rationale": "save the form",
        }

    def _production_next(self, context, recent) -> dict:
        # Deterministic fallback for production execution. Each stage is
        # completed by a scoped semantic click; after a click the next decision
        # is a state-based wait for that stage's 完成 button to become disabled.
        url = context.get("current_url") or ""
        if "/execution" not in url:
            return {"action": "navigate", "target": "/execution",
                    "rationale": "navigate to the production execution view"}

        last = recent[-1] if recent else None
        if last and last.get("action") == "navigate":
            return {
                "action": "wait",
                "params": {"for": "visible", "role": "combobox",
                           "name": "选择指令", "timeout": 8000},
                "rationale": "wait for the execution view to render",
            }

        if last and last.get("action") == "click" and _target_name(last.get("target")) == "完成":
            zh = _target_scope_text(last.get("target"))
            return {
                "action": "wait",
                "params": {"for": "disabled", "role": "button",
                           "name": f"完成{zh}", "timeout": 8000},
                "rationale": f"wait until stage '{zh}' is completed",
            }

        done = set()
        for r in recent:
            if r.get("action") == "click" and _target_name(r.get("target")) == "完成":
                done.add(_target_scope_text(r.get("target")))

        for stage in PRODUCTION_STAGES:
            zh = _STAGE_ZH[stage]
            if zh in done:
                continue
            return {
                "action": "click",
                "target": {"within": {"role": "row", "text": zh},
                           "role": "button", "name": "完成"},
                "rationale": f"complete production stage '{zh}'",
            }

        return {"action": "done", "rationale": "all production stages completed"}


class Hosp2MESAgent:
    """One-action-per-step LLM policy agent."""

    def __init__(self, config: Config, env: BrowserEnv, task: Task):
        self.config = config
        self.env = env
        self.task = task
        self.planner = Planner(config)
        self.verifier = EvidenceVerifier()
        self.trace = TraceRecorder(publish_url=config.publish_url or None,
                                   mode=config.agent_mode)
        self.memory: ProgressMemory | None = None
        self.ctx = ExecContext(
            product=task.product,
            material_code=task.target_material_code,
            material_name=task.target_material_name,
            material_type=task.material_type,
            unit=task.unit,
            specification=task.specification,
            bom_code=task.bom_code,
            bom_materials=task.bom_materials,
            order_code=task.order_code,
            batch=task.batch,
            quantity=task.quantity,
        )
        self.run_id = make_run_id(task.task_id)
        self.evidence = EvidenceWriter(self.run_id, config.artifacts_root or None)
        if getattr(env, "artifacts_dir", None) is None:
            env.artifacts_dir = self.evidence.run_dir
        self.policy = ActionPolicy(config, self.ctx)
        self.gui_steps = 0
        self.failed_subgoal = ""
        self.failure_reason = ""
        self.steps_reached = 0
        self.total_llm_calls = 0
        self.fallback_count = 0
        self.retry_count = 0
        self.premature_done_count = 0
        self.total_llm_latency_ms = 0
        self.per_subgoal_stats: dict[str, dict] = {}

    # ---- lifecycle -------------------------------------------------------
    def run(self):
        self.env.start()
        try:
            self.env.reset()
            return self._run()
        finally:
            try:
                self.env.close()
            except Exception:
                pass

    def _run(self):
        self.evidence.start(self.task.task_id, self.task.instruction, mode="hosp2mes")
        self.trace.start_run(self.task.task_id, self.task.instruction)

        plan = self.planner.plan(self.task.instruction, self.task.expected_final_state)
        self.memory = ProgressMemory.from_plan(self.task.instruction, plan.ordered_ids())
        subgoal_by_id = {s.id: s for s in plan.subgoals}
        self._trace(subgoal="planning", observation=f"subgoals={plan.ids()}",
                    reasoning=f"Planner produced {len(plan.subgoals)} dependency-aware subgoals",
                    action="plan", result=plan.ordered_ids(),
                    evidence={"plan": plan.to_dict(),
                              "planner_source": "deterministic"})

        for sg_id in plan.ordered_ids():
            self.steps_reached = self.gui_steps
            self.memory.set_current(sg_id)
            sg = subgoal_by_id.get(sg_id, Subgoal(id=sg_id))
            ok = self._run_subgoal_loop(sg)
            if not ok:
                self.failed_subgoal = sg_id
                break

        verdict = self.verifier.verify(self.env, self.task)
        success = verdict.passed and self.memory.all_done()
        self._trace(subgoal="final_verification", observation=f"observed={verdict.observed}",
                    reasoning="Evidence verifier checked live backend state independently",
                    action="verify:final",
                    result="PASS" if verdict.passed else f"FAIL missing={verdict.missing}",
                    evidence={"expected": verdict.expected, "observed": verdict.observed,
                              "missing": verdict.missing})

        self.trace.finish_run(success, verdict.detail, len(self.trace.steps), 0)
        avg_latency = (self.total_llm_latency_ms / self.total_llm_calls
                       if self.total_llm_calls else 0.0)
        self.evidence.finish(
            success=success, final_state=verdict.observed, detail=verdict.detail,
            gui_steps=self.gui_steps, failed_subgoal=self.failed_subgoal,
            failure_reason=self.failure_reason, steps_reached=self.steps_reached,
            policy_mode=self.policy.mode,
            total_llm_calls=self.total_llm_calls,
            fallback_count=self.fallback_count,
            llm_model=getattr(self.policy._llm, "model", self.config.llm_model) or "",
            planner_source="deterministic",
            total_llm_latency_ms=self.total_llm_latency_ms,
            avg_llm_latency_ms=round(avg_latency, 1),
            invalid_action_count=self.policy.invalid_action_count,
            retry_count=self.retry_count,
            llm_retry_count=self.policy.llm_retry_count,
            premature_done_count=self.premature_done_count,
            subgoals_total=len(plan.subgoals),
            subgoals_completed=sum(1 for s in plan.subgoals
                                   if self.memory.is_completed(s.id)),
            per_subgoal_stats=self.per_subgoal_stats,
        )
        self.evidence.flush()

        report = Evaluator().evaluate(
            task_id=self.task.task_id, memory=self.memory, trace=self.trace,
            verifier_result=verdict, recovery_count=0,
            premature_done=self.premature_done_count,
            mode=self.config.agent_mode,
        )
        return report, self.trace, self.memory

    # ---- per-subgoal decision loop ---------------------------------------
    def _run_subgoal_loop(self, sg: Subgoal) -> bool:
        max_steps = self.task.max_steps or self.config.max_steps
        recent: list[dict] = []
        sg_llm_calls = 0
        sg_steps = 0
        for _ in range(max_steps):
            if self._subgoal_satisfied(sg):
                self.memory.mark_completed(sg.id, evidence={"success_condition": sg.success_condition})
                self._trace(subgoal=sg.id, observation=f"{sg.id} satisfied (read-back)",
                            reasoning=f"Subgoal '{sg.id}' verified via independent read-back",
                            action=f"verify:{sg.id}", result="completed")
                self.per_subgoal_stats[sg.id] = {"steps": sg_steps, "llm_calls": sg_llm_calls}
                return True

            obs = self.env.observe()
            context = {
                "goal": self.task.instruction,
                "current_subgoal": sg.to_dict(),
                "progress_memory": self.memory.to_dict(),
                "current_url": obs.current_url,
                "visible_text": obs.visible_text,
                "interactive_elements": obs.interactive_elements,
                "recent_actions": recent,
            }

            try:
                decision = self.policy.next_action(context)
            except PolicyStrictFailure as exc:
                self.failure_reason = str(exc)
                self.memory.mark_failed(sg.id, reason=self.failure_reason)
                self._trace(subgoal=sg.id, observation=obs.summary(),
                            reasoning="llm-strict policy failed (no fallback)",
                            action="fail:llm-strict", result=str(exc),
                            evidence=exc.decision.provenance())
                self.per_subgoal_stats[sg.id] = {"steps": sg_steps, "llm_calls": sg_llm_calls}
                return False

            if decision is None:
                decision = PolicyDecision(action="done")

            if decision.policy_source == "deepseek":
                self.total_llm_calls += 1
                sg_llm_calls += 1
            if decision.fallback_used:
                self.fallback_count += 1
            if decision.llm_latency_ms is not None:
                self.total_llm_latency_ms += decision.llm_latency_ms

            before_path, _ = self.env.screenshot(f"{sg.id}-{self.gui_steps:02d}-before")
            action = self._to_action(decision)
            result = self.env.execute(action) if action is not None else None
            after_path, _ = self.env.screenshot(f"{sg.id}-{self.gui_steps:02d}-after")
            after = self.env.observe()
            state_changed = self._signature(obs) != self._signature(after)

            self.gui_steps += 1
            sg_steps += 1
            result_str = "ok" if (result is None or result.ok) else f"FAIL: {result.detail}"
            if result is not None and not result.ok:
                self.retry_count += 1
            self.evidence.record(
                step=self.gui_steps, subgoal=sg.id, url=obs.current_url,
                observation_summary=obs.summary(),
                interactive_elements_summary=self._elems_summary(obs),
                action=(action.summary() if action is not None else "done"),
                action_target=decision.target,
                action_result=result_str,
                value=decision.value,
                screenshot_before=before_path, screenshot_after=after_path,
                state_changed=state_changed,
                provenance=decision.provenance(),
                goal=self.task.instruction,
                memory_snapshot=self.memory.to_dict(),
            )
            self._trace(subgoal=sg.id, observation=obs.summary(),
                        reasoning=decision.rationale or "policy step",
                        action=(action.summary() if action is not None else "done"),
                        result=result_str,
                        evidence={"state_changed": state_changed, "url": obs.current_url,
                                  **decision.provenance()})

            recent.append({
                "action": decision.action,
                "target": decision.target,
                "value": decision.value,
                "result": result_str,
            })
            if len(recent) > 12:
                recent = recent[-12:]

            if decision.action == "done":
                # Policy claims done; the next loop iteration verifies via read-back.
                if not self._subgoal_satisfied(sg):
                    self.premature_done_count += 1
                    self.failure_reason = "policy claimed done but read-back disagrees"
                    continue

        self.memory.mark_failed(sg.id, reason="exhausted decision-loop steps")
        self.failure_reason = self.failure_reason or f"exhausted {max_steps} steps"
        self.per_subgoal_stats[sg.id] = {"steps": sg_steps, "llm_calls": sg_llm_calls}
        return self._subgoal_satisfied(sg)

    # ---- helpers ---------------------------------------------------------
    def _to_action(self, decision: PolicyDecision) -> Action | None:
        verb = decision.action
        if not verb or verb == "done":
            return None
        return Action(
            verb=verb,
            target=decision.target,
            value=decision.value,
            params=decision.params,
            reasoning=decision.rationale,
        )

    def _subgoal_satisfied(self, sg: Subgoal) -> bool:
        sid = sg.id
        try:
            if sid == "create_material":
                return self.env.get_material(self.ctx.material_code) is not None
            if sid == "create_bom":
                return self.env.get_bom(self.ctx.bom_code) is not None
            if sid == "create_production_order":
                return self.env.get_order(self.ctx.order_code) is not None
            if sid == "execute_production":
                order = self.env.get_order(self.ctx.order_code)
                return bool(order and order.get("status") == "COMPLETED")
        except Exception:
            # A transient read-back error (e.g. a momentary backend lock) must
            # not crash the run; treat it as "not yet satisfied" and let the
            # next loop iteration re-check. This is a generic robustness guard.
            return False
        return False

    def _trace(self, *, subgoal, observation, reasoning, action, result, evidence=None):
        self.trace.record(
            goal=self.task.instruction, subgoal=subgoal,
            observation=observation, reasoning_summary=reasoning,
            action=action, result=result, evidence=evidence or {},
            memory_state=self.memory.to_dict() if self.memory else {},
            recovery_count=0,
        )

    @staticmethod
    def _signature(obs: BrowserObservation) -> str:
        parts = [obs.visible_text]
        for e in obs.interactive_elements:
            parts.append(f"{e.get('role')}:{e.get('accessible_name')}")
        return "|".join(parts)

    @staticmethod
    def _elems_summary(obs: BrowserObservation) -> str:
        return ", ".join(
            f"{e.get('role')}[{e.get('accessible_name') or e.get('text')[:20]}]"
            for e in obs.interactive_elements[:20]
        )


# Chinese labels for the 7 canonical production stages (mirrors the Vue view).
_STAGE_ZH = {
    "weighing": "称量",
    "dissolution": "溶解",
    "filtration": "过滤",
    "filling": "分装",
    "labeling": "贴签",
    "packaging": "包装",
    "storage": "入库",
}

# Canonical production route + BOM version. These are generic MES business
# constants (not task-specific): the same values apply to any product.
_ROUTE = ">".join(PRODUCTION_STAGES)
_BOM_VERSION = "1.0"

# The production stages, in canonical order, with their Chinese UI labels.
_PRODUCTION_STAGE_HINTS = [{"key": s, "label": _STAGE_ZH[s]} for s in PRODUCTION_STAGES]


_LONG_HORIZON_SYSTEM_PROMPT = (
    "You are a GUI agent controlling a manufacturing execution system (MES) web "
    "app. Given the goal, the current subgoal, the business data to enter, the "
    "structured progress memory and the current browser observation (URL, visible "
    "text, interactive elements), return exactly ONE next action.\n\n"
    "The app has a left sidebar (仪表盘 / 物品主文件 / BOM 管理 / 生产指令 / "
    "生产执行 / ...). You may click a menu item, or use action \"navigate\" with "
    "target \"/materials\", \"/boms\", \"/orders\" or \"/execution\".\n\n"
    "Respond with ONLY a JSON object (no markdown, no surrounding text):\n"
    '{"action":"<click|type|select|scroll|wait|back|navigate|done>", '
    '"target":<string or {"within":{"role","text"},"role","name"}>, '
    '"value":<optional>, "params":<optional dict>, '
    '"rationale":"<short public rationale>"}\n\n'
    "Rules:\n"
    "- Use the exact accessible names from interactive_elements.\n"
    '- Fill a field: {"action":"type","target":{"role":"textbox","name":"<label>"},"value":"<v>"}.\n'
    '- Choose a dropdown: {"action":"select","target":{"role":"combobox","name":"<label>"},"value":"<option text or code>"}.\n'
    '- Click a button: {"action":"click","target":{"role":"button","name":"<button text>"}}.\n'
    '- Click a button inside a specific table row (e.g. a production stage), use a scoped target: '
    '{"within":{"role":"row","text":"<row text like 称量>"},"role":"button","name":"完成"}.\n'
    '- Wait for a condition: {"action":"wait","params":{"for":"<visible|hidden|enabled|disabled>","role":"<role>","name":"<name>","timeout":8000}}.\n'
    "- When the current subgoal is already satisfied by the live state, return {\"action\":\"done\"}.\n\n"
    "Workflow guidance (generic, by subgoal):\n"
    "- create_material: navigate /materials, click 新建物料, fill 物料编码/物料名称/类型(select)/单位/规格, click 保存.\n"
    "- create_bom: navigate /boms, click 新建 BOM, fill BOM 编码/产品/版本/工艺路线, click 保存; then click 物料明细 and, for each item in business_data.bom_materials, type 物料编码 and 数量 and click 添加.\n"
    "- create_production_order: navigate /orders, click 新建指令, fill 指令号/产品/批次/数量, click 保存.\n"
    "- execute_production: navigate /execution, select the order (select 选择指令 = business_data.order_code), then complete each stage in business_data.production_stages order by clicking 完成 within that stage's row (scoped target), waiting for it to become disabled before the next.\n\n"
    "Never reveal internal chain-of-thought; rationale is a short public reason only."
)


def _target_name(target: Any) -> str:
    if isinstance(target, dict):
        return target.get("name") or target.get("text") or ""
    return str(target or "")


def _target_scope_text(target: Any) -> str:
    if isinstance(target, dict) and target.get("within"):
        return target["within"].get("text") or ""
    return ""

