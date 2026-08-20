"""Long-horizon planner.

Generates an ordered list of subgoals from the high-level goal and the task's
*expected final state*. The planner is deliberately **data-driven**, not
hardcoded to any product name: it inspects which conditions the task must
satisfy (material_exists / bom_exists / production_order_status / storage_status)
and emits the matching subgoals. This is what keeps the agent a real planner
instead of a fixed RPA script.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hosp2mes.config import Config
from hosp2mes.llm import MockLLM


@dataclass
class Subgoal:
    id: str
    description: str


@dataclass
class Plan:
    goal: str
    subgoals: list[Subgoal] = field(default_factory=list)

    def ids(self) -> list[str]:
        return [s.id for s in self.subgoals]


# Subgoal templates keyed by the expected-state condition that triggers them.
SUBGOAL_TEMPLATES = {
    "material_exists": Subgoal("create_material", "Locate / create the required material"),
    "bom_exists": Subgoal("create_bom", "Configure the Bill of Materials for the product"),
    "production_order_status": Subgoal("create_production_order", "Create and verify the production order"),
    "storage_status": Subgoal("execute_production", "Execute production stages through storage"),
}


class Planner:
    def __init__(self, config: Config | None = None, llm: MockLLM | None = None):
        self.config = config or Config()
        self.llm = llm or MockLLM()

    def plan(self, goal: str, expected_state: dict) -> Plan:
        if self.config.use_real_llm():
            return self._plan_with_llm(goal, expected_state)
        return self._plan_from_state(goal, expected_state)

    def _plan_from_state(self, goal: str, expected_state: dict) -> Plan:
        subgoals: list[Subgoal] = []
        # Fixed canonical order of MES workflow phases.
        for key in ["material_exists", "bom_exists",
                    "production_order_status", "storage_status"]:
            if key in expected_state:
                subgoals.append(SUBGOAL_TEMPLATES[key])
        # De-duplicate (storage_status implies production order work already).
        seen = set()
        ordered = []
        for s in subgoals:
            if s.id not in seen:
                seen.add(s.id)
                ordered.append(s)
        return Plan(goal=goal, subgoals=ordered)

    def _plan_with_llm(self, goal: str, expected_state: dict) -> Plan:
        # Reserved structured-LLM path. Falls back to the deterministic planner
        # when the model output cannot be parsed, so the agent never dead-locks.
        try:
            from hosp2mes.llm import DeepSeekLLM, build_llm

            llm = build_llm(self.config)
            assert isinstance(llm, DeepSeekLLM)
            system = (
                "You are a manufacturing execution planner. Given a goal and the "
                "required final business state, return a JSON list of subgoal ids "
                "from: create_material, create_bom, create_production_order, "
                "execute_production. Respond with only a JSON object "
                '{"subgoals":[...]}.'
            )
            user = f"GOAL: {goal}\nEXPECTED: {expected_state}"
            text = llm.complete(system, user)
            parsed = DeepSeekLLM.parse_json_block(text)
            ids = [s for s in parsed.get("subgoals", []) if s in SUBGOAL_TEMPLATES]
            if not ids:
                raise ValueError("empty plan")
            return Plan(goal=goal, subgoals=[SUBGOAL_TEMPLATES[i] for i in ids])
        except Exception:
            return self._plan_from_state(goal, expected_state)
