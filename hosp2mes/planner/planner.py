"""Long-horizon planner.

Generates an ordered, dependency-aware list of subgoals from the high-level goal
and the task's *expected final state*. The planner is deliberately **data-driven**,
not hardcoded to any product name: it inspects which conditions the task must
satisfy (material_exists / bom_exists / production_order_status / storage_status)
and emits the matching subgoals.

V1.2 upgrade: a subgoal is no longer just an id + description. It carries a
structured schema so a policy / executor can drive it dynamically::

    Subgoal(
        id="create_bom",
        description="Configure the Bill of Materials",
        dependencies=["create_material"],
        success_condition="bom_exists == true",
        capabilities=["create_bom"],
    )

Two planning paths exist:

* ``_plan_from_state`` — the deterministic planner (CI / offline fallback),
  which maps expected-state conditions to canonical subgoals.
* ``_plan_with_llm`` — a structured-LLM path that may emit **arbitrary** subgoal
  ids (not just the four fixed ones), parsed from JSON. It falls back to the
  deterministic planner if the model output cannot be parsed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hosp2mes.config import Config
from hosp2mes.llm import MockLLM


@dataclass
class Subgoal:
    id: str
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    success_condition: str = ""
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "dependencies": self.dependencies,
            "success_condition": self.success_condition,
            "capabilities": self.capabilities,
        }


@dataclass
class Plan:
    goal: str
    subgoals: list[Subgoal] = field(default_factory=list)

    def ids(self) -> list[str]:
        return [s.id for s in self.subgoals]

    def ordered_ids(self) -> list[str]:
        """Return subgoal ids topologically sorted by their dependencies."""
        deps = {s.id: list(s.dependencies) for s in self.subgoals}
        ids = set(deps)
        out: list[str] = []
        seen: set[str] = set()
        while len(out) < len(self.subgoals):
            ready = [
                i for i in ids
                if i not in seen and all(d not in ids or d in seen for d in deps[i])
            ]
            if not ready:
                # Cycle or missing dep -> fall back to declaration order.
                for s in self.subgoals:
                    if s.id not in seen:
                        seen.add(s.id)
                        out.append(s.id)
                continue
            for i in ready:
                seen.add(i)
                out.append(i)
        return out

    def to_dict(self) -> dict:
        return {"goal": self.goal, "subgoals": [s.to_dict() for s in self.subgoals]}


# Subgoal templates keyed by the expected-state condition that triggers them.
# Each carries a success condition and a dependency chain so the plan is
# inspectable and can be driven by a policy rather than a fixed skill.
SUBGOAL_TEMPLATES = {
    "material_exists": Subgoal(
        id="create_material",
        description="Locate / create the required material",
        dependencies=[],
        success_condition="material_exists == true",
        capabilities=["create_material"],
    ),
    "bom_exists": Subgoal(
        id="create_bom",
        description="Configure the Bill of Materials for the product",
        dependencies=["create_material"],
        success_condition="bom_exists == true",
        capabilities=["create_bom"],
    ),
    "production_order_status": Subgoal(
        id="create_production_order",
        description="Create and verify the production order",
        dependencies=["create_bom"],
        success_condition="production_order_status matches expected value",
        capabilities=["create_production_order"],
    ),
    "storage_status": Subgoal(
        id="execute_production",
        description="Execute production stages through storage",
        dependencies=["create_production_order"],
        success_condition="storage_status == STORED",
        capabilities=["execute_production"],
    ),
}


class Planner:
    def __init__(self, config: Config | None = None, llm: MockLLM | None = None):
        self.config = config or Config()
        self.llm = llm or MockLLM()

    def plan(
        self,
        goal: str,
        expected_state: dict,
        current_state: dict | None = None,
        capabilities: list[str] | None = None,
    ) -> Plan:
        """Decompose a goal into dependency-aware subgoals.

        ``current_state`` and ``capabilities`` are accepted so a policy-driven
        planner can skip already-satisfied conditions and only plan for what the
        current capabilities can achieve.
        """
        if self.config.use_real_llm():
            return self._plan_with_llm(goal, expected_state, current_state, capabilities)
        return self._plan_from_state(goal, expected_state, current_state, capabilities)

    def _plan_from_state(
        self,
        goal: str,
        expected_state: dict,
        current_state: dict | None = None,
        capabilities: list[str] | None = None,
    ) -> Plan:
        current_state = current_state or {}
        subgoals: list[Subgoal] = []
        for key in ["material_exists", "bom_exists",
                    "production_order_status", "storage_status"]:
            if key not in expected_state:
                continue
            # Skip conditions already satisfied in the current business state.
            if key in current_state and self._satisfied(current_state[key], expected_state[key]):
                continue
            subgoals.append(SUBGOAL_TEMPLATES[key])

        # De-duplicate by id.
        seen: set[str] = set()
        ordered: list[Subgoal] = []
        for s in subgoals:
            if s.id not in seen:
                seen.add(s.id)
                ordered.append(s)

        # Filter out subgoals whose capability isn't available (if a
        # capabilities list was provided).
        if capabilities is not None:
            caps = set(capabilities)
            ordered = [s for s in ordered if not s.capabilities or s.capabilities[0] in caps]

        return Plan(goal=goal, subgoals=ordered)

    @staticmethod
    def _satisfied(got: Any, expected: Any) -> bool:
        if expected is None:
            return got is not None
        if isinstance(expected, str) and isinstance(got, str):
            return got.strip().upper() == expected.strip().upper()
        return got == expected

    def _plan_with_llm(
        self,
        goal: str,
        expected_state: dict,
        current_state: dict | None = None,
        capabilities: list[str] | None = None,
    ) -> Plan:
        """Structured-LLM path: emits arbitrary subgoals with a full schema.

        Falls back to the deterministic planner when the model output cannot be
        parsed, so the agent never dead-locks.
        """
        try:
            from hosp2mes.llm import DeepSeekLLM, build_llm

            llm = build_llm(self.config)
            assert isinstance(llm, DeepSeekLLM)
            system = (
                "You are a manufacturing execution planner. Given a goal, the "
                "required final business state, the current state and the "
                "available capabilities, return a JSON object with a 'subgoals' "
                "list. Each subgoal has 'id', 'description', 'dependencies' "
                "(list of subgoal ids), 'success_condition' (a short condition) "
                "and 'capabilities' (list of capability ids). You may invent any "
                "subgoal id, not only a fixed set. Respond with only the JSON "
                "object."
            )
            user = (
                f"GOAL: {goal}\nEXPECTED: {expected_state}\n"
                f"CURRENT: {current_state or {}}\nCAPABILITIES: {capabilities or []}"
            )
            text = llm.complete(system, user)
            parsed = DeepSeekLLM.parse_json_block(text)
            subgoals = []
            for item in parsed.get("subgoals", []):
                subgoals.append(Subgoal(
                    id=str(item.get("id", "")),
                    description=str(item.get("description", "")),
                    dependencies=list(item.get("dependencies", [])),
                    success_condition=str(item.get("success_condition", "")),
                    capabilities=list(item.get("capabilities", [])),
                ))
            if not subgoals:
                raise ValueError("empty plan")
            return Plan(goal=goal, subgoals=subgoals)
        except Exception:
            return self._plan_from_state(goal, expected_state, current_state, capabilities)
