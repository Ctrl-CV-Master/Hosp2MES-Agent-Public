"""Canonical business state representation (V1.3).

A single, unified, *nested* view of the MES business state that every part of
the recovery pipeline (state reader, state diff, diagnosis, repair planner)
agrees on. It is deliberately independent of the agent's own progress memory:
the canonical state is produced by the independent read-only verifier, never by
the agent self-reporting.

Canonical shape::

    {
      "material":         {"exists": bool, "status": str | None},
      "bom":              {"exists": bool, "status": str | None},
      "production_order": {"exists": bool, "status": str | None},
      "stages":           {stage_name: stage_status, ...},
    }

``exists`` is always present (``False`` when the object is absent) so the state
diff never has to guess about "absent vs false".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Canonical production execution stages (order matters; mirrors the backend).
PRODUCTION_STAGES = [
    "weighing", "dissolution", "filtration",
    "filling", "labeling", "packaging", "storage",
]

# Chinese labels for the canonical stages (mirrors the Vue view).
STAGE_LABELS_ZH = {
    "weighing": "称量",
    "dissolution": "溶解",
    "filtration": "过滤",
    "filling": "分装",
    "labeling": "贴签",
    "packaging": "包装",
    "storage": "入库",
}

_MISSING = object()


def _obj() -> dict:
    return {"exists": False, "status": None}


@dataclass
class BusinessState:
    """A read-only snapshot of the canonical MES business state."""

    material: dict = field(default_factory=_obj)
    bom: dict = field(default_factory=_obj)
    production_order: dict = field(default_factory=_obj)
    stages: dict = field(default_factory=dict)  # stage_name -> stage_status

    def to_dict(self) -> dict:
        return {
            "material": dict(self.material),
            "bom": dict(self.bom),
            "production_order": dict(self.production_order),
            "stages": dict(self.stages),
        }

    def get(self, path: str, default: Any = _MISSING) -> Any:
        """Read a dotted path, e.g. ``material.exists`` or ``stages.storage``."""
        node: Any = self.to_dict()
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default if default is not _MISSING else _MISSING
            node = node[part]
        return node

    @staticmethod
    def flatten(state: dict, prefix: str = "") -> dict:
        """Flatten a nested state dict into dotted paths (for the state diff)."""
        out: dict = {}
        for key, value in state.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                out.update(BusinessState.flatten(value, path))
            else:
                out[path] = value
        return out


def expected_state_for_subgoal(subgoal_id: str) -> dict:
    """Return the nested expected business state for a canonical subgoal.

    These are the *success conditions* expressed as business state (section 三
    of the V1.3 spec): a subgoal is satisfied by the live state, not by "having
    clicked the button".
    """
    return {
        "create_material": {
            "material": {"exists": True},
        },
        "create_bom": {
            "material": {"exists": True},
            "bom": {"exists": True},
        },
        "create_production_order": {
            "bom": {"exists": True},
            "production_order": {"exists": True},
        },
        "execute_production": {
            "production_order": {"status": "COMPLETED"},
            "stages": {"storage": "COMPLETED"},
        },
    }.get(subgoal_id, {})


def canonicalize_expected(flat_or_nested: dict) -> dict:
    """Normalize a legacy *flat* expected-state dict into the canonical nested form.

    Accepts both the legacy flat keys (``material_exists`` / ``bom_exists`` /
    ``production_order_status`` / ``storage_status``) and an already-nested
    canonical dict, so existing tasks keep working without changes.
    """
    if not flat_or_nested:
        return {}
    # Already nested? (any value is a dict) -> assume canonical.
    if any(isinstance(v, dict) for v in flat_or_nested.values()):
        return flat_or_nested

    out: dict = {}
    mapping = {
        "material_exists": ("material", "exists"),
        "bom_exists": ("bom", "exists"),
        "production_order_status": ("production_order", "status"),
        "storage_status": ("stages", "storage"),
    }
    for key, value in flat_or_nested.items():
        target = mapping.get(key)
        if target is None:
            continue
        section, leaf = target
        out.setdefault(section, {})
        out[section][leaf] = value
    return out


def first_incomplete_stage(stages: dict) -> str | None:
    """Return the first production stage (in canonical order) that is not COMPLETED."""
    for stage in PRODUCTION_STAGES:
        if stages.get(stage) != "COMPLETED":
            return stage
    return None
