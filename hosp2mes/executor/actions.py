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
    target: Any = ""          # element / page / stage identifier, or a scoped
                              # target dict: {"within": {"role","text"},
                              #                 "role": ..., "name": ...}
    value: Any = None         # input value
    params: dict = field(default_factory=dict)
    reasoning: str = ""       # short, public-safe rationale (NOT private CoT)

    def summary(self) -> str:
        target = _summarize_target(self.target)
        if self.value is not None:
            return f"{self.verb}:{target}={self.value}"
        if self.params:
            return f"{self.verb}:{target} {self.params}"
        return f"{self.verb}:{target}"


def _summarize_target(target: Any) -> str:
    """Human-readable form of a target (string or scoped dict)."""
    if isinstance(target, dict):
        within = target.get("within")
        parts = []
        if within:
            scope = within.get("text") or within.get("name") or ""
            parts.append(f"within:{within.get('role', 'row')}[{scope}]")
        parts.append(f"{target.get('role', '?')}:{target.get('name') or target.get('text') or ''}")
        return " ".join(parts)
    return str(target)

