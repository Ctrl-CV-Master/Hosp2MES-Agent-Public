"""Agent package.

Imports only the leaf REST-agent module eagerly. The browser skill baseline is
re-exported lazily (``BrowserAgent`` / ``SemanticSkillAgent``) to avoid a
circular import with ``hosp2mes.agents`` (which itself imports ``hosp2mes.agent.agent``).
"""
from .agent import Agent, Task, TaskLoader

__all__ = ["Agent", "Task", "TaskLoader", "BrowserAgent", "SemanticSkillAgent"]


def __getattr__(name):
    if name in ("BrowserAgent", "SemanticSkillAgent"):
        from .browser_agent import BrowserAgent, SemanticSkillAgent

        return {"BrowserAgent": BrowserAgent, "SemanticSkillAgent": SemanticSkillAgent}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
