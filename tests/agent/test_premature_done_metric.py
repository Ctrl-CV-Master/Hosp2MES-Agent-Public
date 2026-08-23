"""Regression test: premature-DONE count must reach the Evaluator.

Before the fix, ``Hosp2MESAgent._run`` called
``Evaluator().evaluate(..., premature_done=0, ...)`` with a hard-coded zero, so
the evaluator never saw the real ``premature_done_count`` even though the
decision loop incremented it. This test drives a real (fake-env) run where the
policy keeps claiming ``done`` while the independent read-back disagrees, and
asserts the final evaluation report carries ``premature_done > 0``.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from hosp2mes.agent.agent import Task  # noqa: E402
from hosp2mes.agents.hosp2mes_agent import (  # noqa: E402
    ActionPolicy,
    Hosp2MESAgent,
    PolicyDecision,
)
from hosp2mes.config import Config  # noqa: E402
from hosp2mes.observation.api_env import ActionResult  # noqa: E402
from hosp2mes.observation.browser_observation import BrowserObservation  # noqa: E402


class _AlwaysDonePolicy(ActionPolicy):
    """A policy that always claims the subgoal is done (never emits a real action)."""

    def __init__(self, config, ctx):
        super().__init__(config, ctx)

    def next_action(self, context):
        return PolicyDecision(action="done", policy_source="deterministic",
                              rationale="simulated premature done")


class _FakeEnv:
    """Minimal env: read-backs always report the material as missing."""

    artifacts_dir = None

    def start(self):
        return self

    def reset(self):
        pass

    def close(self):
        pass

    def observe(self):
        return BrowserObservation(current_url="http://x/materials", title="t",
                                  visible_text="", interactive_elements=[],
                                  accessibility=[], timestamp="")

    def screenshot(self, name=None):
        return None, None

    def execute(self, action):
        return ActionResult(ok=True)

    def get_material(self, code):
        return None

    def get_bom(self, code):
        return None

    def get_order(self, code):
        return None

    def system_state(self, product=None, material_code=None):
        return {}


def test_premature_done_reaches_evaluator(tmp_path):
    task = Task(
        task_id="T-PD", instruction="create a material", product="P",
        expected_final_state={"material_exists": True},
        target_material_code="M", max_steps=3,
    )
    config = Config(llm_provider="mock", policy="deterministic",
                    artifacts_root=str(tmp_path))
    env = _FakeEnv()
    agent = Hosp2MESAgent(config, env, task)
    agent.policy = _AlwaysDonePolicy(config, agent.ctx)

    report, trace, memory = agent.run()

    # The decision loop saw 3 premature DONE claims (one per loop step) and the
    # Evaluator must have received that count (not a hard-coded 0).
    assert agent.premature_done_count > 0
    assert report.premature_done == agent.premature_done_count
    assert report.premature_done > 0
    # And the run still fails end-to-end, because the material was never created.
    assert report.task_success is False
