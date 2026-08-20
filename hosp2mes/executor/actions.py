"""Abstract GUI action vocabulary.

The agent reasons in terms of these abstract verbs rather than concrete
XPath / CSS / coordinates. The executor translates them into environment
operations. This keeps the business layer free of low-level automation code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hosp2mes.observation.api_env import ActionResult  # re-export for convenience

# The canonical action verbs required by the project specification.
ACTION_VERBS = [
    "click", "input", "select", "scroll",
    "navigate", "extract", "wait", "verify", "back",
]


@dataclass
class Action:
    verb: str
    target: str = ""          # element / page / stage identifier
    value: Any = None         # input value
    params: dict = field(default_factory=dict)
    reasoning: str = ""       # short, public-safe rationale (NOT private CoT)

    def summary(self) -> str:
        if self.value is not None:
            return f"{self.verb}:{self.target}={self.value}"
        if self.params:
            return f"{self.verb}:{self.target} {self.params}"
        return f"{self.verb}:{self.target}"
