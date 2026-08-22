"""Backward-compatible alias for the browser skill baseline.

``BrowserAgent`` was the V1.1 name for what is now
:class:`hosp2mes.agents.skill_agent.SemanticSkillAgent`. This module keeps the
old import path working (``from hosp2mes.agent.browser_agent import BrowserAgent``)
while the canonical class lives in ``hosp2mes.agents``.
"""
from __future__ import annotations

from hosp2mes.agents.skill_agent import (  # noqa: F401
    STAGE_LABELS_ZH,
    GUIStepResult,
    SemanticSkillAgent,
)

BrowserAgent = SemanticSkillAgent

__all__ = ["BrowserAgent", "SemanticSkillAgent", "STAGE_LABELS_ZH", "GUIStepResult"]
