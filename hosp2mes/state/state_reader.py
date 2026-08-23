"""Read the canonical business state from the independent read-only verifier.

The state is read through the environment's read-only REST client
(``get_material`` / ``get_bom`` / ``get_order``) — the SAME client the Evidence
Verifier uses. It is never derived from the agent's own progress memory, and it
never performs a business mutation.
"""
from __future__ import annotations

from typing import Any

from hosp2mes.state.business_state import PRODUCTION_STAGES, BusinessState


class StateReader:
    """Build a :class:`BusinessState` snapshot from the environment."""

    def __init__(self, env: Any, material_code: str = "",
                 bom_code: str = "", order_code: str = ""):
        self.env = env
        self.material_code = material_code
        self.bom_code = bom_code
        self.order_code = order_code

    def read(self) -> BusinessState:
        """Produce a fresh canonical state snapshot (read-only)."""
        state = BusinessState()

        if self.material_code:
            m = _safe(lambda: self.env.get_material(self.material_code))
            state.material = {
                "exists": m is not None,
                "status": (m or {}).get("status"),
            }

        if self.bom_code:
            b = _safe(lambda: self.env.get_bom(self.bom_code))
            state.bom = {
                "exists": b is not None,
                "status": (b or {}).get("status"),
            }

        order = None
        if self.order_code:
            order = _safe(lambda: self.env.get_order(self.order_code))
        if order is None:
            state.production_order = {"exists": False, "status": None}
            state.stages = {s: "NOT_STARTED" for s in PRODUCTION_STAGES}
        else:
            state.production_order = {
                "exists": True,
                "status": order.get("status"),
            }
            stage_map = {
                s.get("stage_name"): s.get("stage_status")
                for s in (order.get("stages") or [])
            }
            state.stages = {
                s: stage_map.get(s, "NOT_STARTED") for s in PRODUCTION_STAGES
            }
        return state


def _safe(fn):
    """Return None on any transient read error (e.g. a momentary lock)."""
    try:
        return fn()
    except Exception:
        return None
