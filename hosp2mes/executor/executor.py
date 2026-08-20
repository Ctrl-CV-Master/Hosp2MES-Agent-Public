"""Executor: maps abstract Actions onto the environment (the tool layer)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hosp2mes.executor.actions import Action
from hosp2mes.observation.api_env import ActionResult, ApiEnv


@dataclass
class ExecContext:
    """Per-run context the executor needs to fill action parameters."""
    product: str = ""
    material_code: str = ""
    material_name: str = ""
    material_type: str = "raw"
    unit: str = "kg"
    specification: str = ""
    bom_code: str = ""
    bom_materials: list[dict] = field(default_factory=list)
    order_code: str = ""
    batch: str = ""
    quantity: int = 1


class Executor:
    """Translate an abstract ``Action`` into one or more environment calls."""

    def execute(self, action: Action, env: ApiEnv, ctx: ExecContext) -> ActionResult:
        verb = action.verb
        t = action.target

        if verb == "navigate":
            return env.navigate(t or "dashboard")

        if verb == "create_material":
            return env.create_material(
                code=ctx.material_code,
                name=ctx.material_name,
                mtype=ctx.material_type,
                unit=ctx.unit,
                spec=ctx.specification,
            )

        if verb == "create_bom":
            return env.create_bom(
                bom_code=ctx.bom_code,
                product=ctx.product,
                materials=ctx.bom_materials,
            )

        if verb == "create_order":
            return env.create_order(
                order_code=ctx.order_code,
                product=ctx.product,
                batch=ctx.batch,
                quantity=ctx.quantity,
            )

        if verb == "start_order":
            return env.start_order(ctx.product)

        if verb == "complete_stage":
            return env.complete_stage(ctx.product, t)

        if verb == "verify":
            return self._verify(env, ctx, action.params)

        if verb in ("wait", "scroll", "back", "extract", "select", "input", "click"):
            # In the REST environment these are no-ops / page transitions that
            # have already been realized by the higher-level verbs above.
            return ActionResult(ok=True, action=action.summary(),
                                detail=f"noop ({verb})")

        return ActionResult(ok=False, action=action.summary(),
                            detail=f"unknown verb: {verb}")

    def _verify(self, env: ApiEnv, ctx: ExecContext, params: dict) -> ActionResult:
        checks: dict[str, Any] = {}
        ok = True
        if "material_code" in params or ctx.material_code:
            code = params.get("material_code", ctx.material_code)
            exists = env.get_material(code) is not None
            checks["material_exists"] = exists
            ok = ok and exists
        if "product" in params or ctx.product:
            product = params.get("product", ctx.product)
            bom = env.get_bom_for_product(product)
            checks["bom_exists"] = bom is not None
            ok = ok and bom is not None
            order = env.get_order_for_product(product)
            checks["production_order_exists"] = order is not None
            if "require_order" in params:
                ok = ok and order is not None
        return ActionResult(ok=ok, action="verify", detail="verification", evidence=checks)
