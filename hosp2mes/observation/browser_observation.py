"""Structured browser observation.

The ``BrowserObservation`` is what the agent sees after each ``observe()`` call
in browser mode. It is built purely from the live page (URL, title, visible
text, interactive elements, accessibility semantics and a screenshot) — never
from the MES REST API. This is the contract that keeps the GUI agent honest:
all the information needed to decide the *next action* comes from the rendered
page, exactly like a human operator looking at the screen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserObservation:
    """One snapshot of the rendered page.

    Fields
    ------
    current_url:   the page URL at observation time.
    title:         document title.
    visible_text:  flattened visible text of the page body (for reading state).
    interactive_elements: list of dicts describing clickable/fillable controls,
                   each with a ``role``, an ``accessible_name`` (aria-label /
                   associated <label> / placeholder / text), and a ``locator``
                   hint. This is the "semantic information" the agent uses to
                   decide its next action without hardcoded XPath/CSS.
    accessibility: normalized accessibility summary (subset of the above),
                   retained as a dedicated field for tooling that wants an
                   explicit a11y view.
    screenshot_path:  absolute path to the PNG screenshot captured for this
                   observation (None when screenshots are disabled).
    screenshot_bytes: raw PNG bytes (None when not requested).
    timestamp:     ISO-8601 UTC timestamp.
    """

    current_url: str = ""
    title: str = ""
    visible_text: str = ""
    interactive_elements: list[dict[str, Any]] = field(default_factory=list)
    accessibility: list[dict[str, Any]] = field(default_factory=list)
    screenshot_path: str | None = None
    screenshot_bytes: bytes | None = None
    timestamp: str = ""

    def summary(self) -> str:
        elems = ", ".join(
            f"{e.get('role', '?')}[{e.get('accessible_name', '') or e.get('text', '')[:20]}]"
            for e in self.interactive_elements[:12]
        )
        return (
            f"url={self.current_url} title={self.title!r} "
            f"elements({len(self.interactive_elements)})={elems}"
        )

    def to_dict(self) -> dict:
        return {
            "current_url": self.current_url,
            "title": self.title,
            "visible_text": self.visible_text[:4000],
            "interactive_elements": self.interactive_elements,
            "accessibility": self.accessibility,
            "screenshot_path": self.screenshot_path,
            "timestamp": self.timestamp,
        }
