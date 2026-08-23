"""LLM policy-mode tests (mock responses; do NOT replace the real run evidence).

These tests use a fake LLM to pin the *contract* of the three policy modes and
of provenance. The real DeepSeek run evidence is produced separately by
``run_llm_policy.py`` / ``run_llm_variant.py`` and recorded under
``artifacts/runs/``.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from hosp2mes.agents.hosp2mes_agent import (  # noqa: E402
    ActionPolicy,
    PolicyDecision,
    PolicyStrictFailure,
)
from hosp2mes.config import Config  # noqa: E402
from hosp2mes.executor.executor import ExecContext  # noqa: E402


class FakeLLM:
    model = "fake-model"

    def __init__(self, responses=None, exc=None):
        self.responses = list(responses or [])
        self.exc = exc
        self.calls = 0

    def complete(self, system, user, **kwargs):
        self.calls += 1
        if self.exc:
            raise self.exc
        if self.responses:
            return self.responses[min(self.calls - 1, len(self.responses) - 1)]
        return "{}"


def _ctx():
    return ExecContext(material_code="M", material_name="N", material_type="raw",
                       unit="kg", specification="s")


def _context():
    return {
        "goal": "create a material",
        "current_subgoal": {"id": "create_material", "capabilities": ["create_material"]},
        "progress_memory": {},
        "current_url": "http://x/materials",
        "visible_text": "",
        "interactive_elements": [{"role": "button", "accessible_name": "新建物料"}],
        "recent_actions": [],
    }


def test_llm_strict_never_fallback():
    fake = FakeLLM(exc=RuntimeError("network down"))
    policy = ActionPolicy(Config(llm_provider="deepseek", policy="llm-strict"),
                          _ctx(), llm=fake)
    with pytest.raises(PolicyStrictFailure) as exc_info:
        policy.next_action(_context())
    # The strict mode must NOT have produced a deterministic fallback action;
    # it retried the LLM (bounded) and then failed honestly.
    assert fake.calls == 5
    assert exc_info.value.decision.llm_call_success is False
    assert exc_info.value.decision.fallback_used is False


def test_policy_provenance_llm_success_and_fallback():
    ok_resp = ('{"action":"click","target":{"role":"button","name":"新建物料"},'
               '"rationale":"open dialog"}')
    # success path
    fake_ok = FakeLLM(responses=[ok_resp])
    p_ok = ActionPolicy(Config(llm_provider="deepseek", policy="llm"), _ctx(), llm=fake_ok)
    d = p_ok.next_action(_context())
    assert isinstance(d, PolicyDecision)
    assert d.policy_source == "deepseek"
    assert d.llm_model == "fake-model"
    assert d.llm_call_success is True
    assert d.llm_parse_success is True
    assert d.fallback_used is False
    assert d.action == "click"

    # fallback path (llm mode): LLM fails -> deterministic + fallback_used.
    fake_fail = FakeLLM(exc=RuntimeError("boom"))
    p_fb = ActionPolicy(Config(llm_provider="deepseek", policy="llm"), _ctx(), llm=fake_fail)
    d2 = p_fb.next_action(_context())
    assert d2.policy_source == "deterministic"
    assert d2.fallback_used is True
    assert d2.llm_call_success is False
    assert d2.action == "click"  # deterministic fallback still produces an action


def test_invalid_llm_action_fails_in_strict_mode():
    # invalid verb
    fake_bad_action = FakeLLM(responses=['{"action":"frobnicate","target":"x"}'])
    p = ActionPolicy(Config(llm_provider="deepseek", policy="llm-strict"), _ctx(),
                     llm=fake_bad_action)
    with pytest.raises(PolicyStrictFailure):
        p.next_action(_context())

    # invalid target (click without a target)
    fake_bad_target = FakeLLM(responses=['{"action":"click"}'])
    p2 = ActionPolicy(Config(llm_provider="deepseek", policy="llm-strict"), _ctx(),
                      llm=fake_bad_target)
    with pytest.raises(PolicyStrictFailure):
        p2.next_action(_context())
