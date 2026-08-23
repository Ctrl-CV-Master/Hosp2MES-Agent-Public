"""Generic state diff over nested business-state paths (V1.3).

``diff(expected, observed)`` compares two nested state dicts by flattening them
into dotted paths and classifying each expected path. It is fully generic: the
same function compares material / BOM / order / stages with no per-resource
special-casing.

Classification (documented, deterministic):

* ``matched`` / ``satisfied`` — the observed value equals the expected value.
* ``missing`` — an expected object/condition is absent: either the path is not
  present in the observed state, or an expected ``*.exists=true`` is observed as
  ``false`` (the canonical reader always emits ``exists`` as ``False`` for an
  absent object, so an unmet ``*.exists`` expectation reads as "missing").
* ``mismatched`` / ``conflicting`` — the path is present but its value differs
  (e.g. a status/quantity is wrong). ``conflicting`` is an alias for
  ``mismatched`` so the spec's two wordings are both satisfied.
* ``unexpected`` — a path present in the observed state but not in the expected
  state (informational only; does not affect ``is_clean``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hosp2mes.state.business_state import BusinessState


@dataclass
class StateDiff:
    matched: dict = field(default_factory=dict)     # path -> value
    missing: dict = field(default_factory=dict)     # path -> {"expected", "actual"}
    mismatched: dict = field(default_factory=dict)  # path -> {"expected", "actual"}
    conflicting: dict = field(default_factory=dict) # alias of mismatched
    unexpected: dict = field(default_factory=dict)  # path -> value
    satisfied: dict = field(default_factory=dict)   # alias of matched

    @property
    def is_clean(self) -> bool:
        return not self.missing and not self.mismatched

    @property
    def unsatisfied_paths(self) -> list[str]:
        return sorted(list(self.missing) + list(self.mismatched))

    def to_dict(self) -> dict:
        return {
            "matched": dict(self.matched),
            "missing": dict(self.missing),
            "mismatched": dict(self.mismatched),
            "conflicting": dict(self.conflicting),
            "unexpected": dict(self.unexpected),
            "satisfied": dict(self.satisfied),
            "is_clean": self.is_clean,
        }


def diff(expected: dict, observed: dict) -> StateDiff:
    """Compare an expected nested state against an observed nested state."""
    exp_flat = BusinessState.flatten(expected or {})
    obs_flat = BusinessState.flatten(observed or {})

    d = StateDiff()
    for path, exp in exp_flat.items():
        if path not in obs_flat:
            d.missing[path] = {"expected": exp, "actual": None}
            continue
        got = obs_flat[path]
        if _equal(got, exp):
            d.matched[path] = got
            d.satisfied[path] = got
        elif path.endswith(".exists") and exp is True and not got:
            # Expected object is absent -> "missing".
            d.missing[path] = {"expected": exp, "actual": got}
        else:
            d.mismatched[path] = {"expected": exp, "actual": got}
            d.conflicting[path] = {"expected": exp, "actual": got}

    for path, value in obs_flat.items():
        if path not in exp_flat:
            d.unexpected[path] = value

    return d


def _equal(got: Any, expected: Any) -> bool:
    if isinstance(expected, str) and isinstance(got, str):
        return got.strip().upper() == expected.strip().upper()
    return got == expected
