"""Agent S3 adapter tests (honest availability / metadata / mapping).

These tests run in the *core* environment (which does NOT install the heavy
``gui-agents`` dependency graph). They verify that the adapter:

* exposes the correct, verified facts about the official Agent S3;
* fails **honestly** (``AgentS3Unavailable``) instead of faking a prediction
  when ``gui-agents`` / a grounding endpoint is unavailable;
* maps observations and actions structurally.

The real ``AgentS3`` import/construction is exercised separately in a
dedicated environment (see ``hosp2mes/agents/agent_s3_adapter.py`` header and
``DEVELOPMENT_STATUS.md``); a real ``predict()`` additionally requires a worker
LLM API key + a UI-TARS grounding-model endpoint, which are not present here.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND = os.path.join(ROOT, "backend")
for p in (BACKEND, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from hosp2mes.agents.agent_s3_adapter import (  # noqa: E402
    AGENT_S3_IMPORT,
    AGENT_S3_LICENSE,
    AGENT_S3_PYPI,
    AGENT_S3_REPO,
    AgentS3Adapter,
    AgentS3Unavailable,
)
from hosp2mes.config import Config  # noqa: E402
from hosp2mes.observation.browser_observation import BrowserObservation  # noqa: E402


def test_agent_s3_metadata_is_verified():
    assert AGENT_S3_REPO == "https://github.com/simular-ai/Agent-S"
    assert AGENT_S3_PYPI == "gui-agents"
    assert AGENT_S3_LICENSE == "Apache-2.0"
    assert "gui_agents.s3.agents.agent_s" in AGENT_S3_IMPORT


def test_agent_s3_adapter_reports_unavailable_without_grounding():
    adapter = AgentS3Adapter(Config(llm_provider="mock"))
    # Even if gui-agents were installed, no grounding endpoint was supplied,
    # so construction must fail honestly rather than fabricate a prediction.
    with pytest.raises(AgentS3Unavailable):
        adapter._ensure_agent()


def test_agent_s3_observation_mapping():
    obs = BrowserObservation(
        current_url="http://x/materials",
        title="t",
        visible_text="新建物料 保存",
        interactive_elements=[
            {"role": "button", "accessible_name": "新建物料"},
            {"role": "textbox", "accessible_name": "物料编码"},
        ],
    )
    mapped = AgentS3Adapter.to_s3_observation(obs)
    assert set(mapped.keys()) >= {"screenshot", "accessibility_tree", "ocr_text"}
    assert "物料编码" in mapped["accessibility_tree"]
    assert mapped["ocr_text"] == "新建物料 保存"


def test_agent_s3_action_mapping():
    assert AgentS3Adapter.map_action_to_browser({"action": "click"}) == "click"
    assert AgentS3Adapter.map_action_to_browser("click x") == {"action": "click", "raw": "click x"}
    # Unknown coordinate actions are passed through, never fabricated.
    assert AgentS3Adapter.map_action_to_browser("move_mouse(10,20)") == {"raw": "move_mouse(10,20)"}
