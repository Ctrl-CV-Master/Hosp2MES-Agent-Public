"""Evidence-Gated Completion.

This is the project's central correctness mechanism. The agent is NOT allowed
to declare success on its own say-so. ``EvidenceVerifier.verify`` reads the
*live* system state through the environment and compares it against the task's
expected final state. Only when every expected condition is actually observed
in the system does ``passed`` become ``True``.

Inspired by the "real-world state, not agent self-report" principle emphasized
in BrowserGym / AgentBench evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VerificationResult:
    passed: bool
    expected: dict = field(default_factory=dict)
    observed: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    detail: str = ""


class EvidenceVerifier:
    def verify(self, env, task) -> VerificationResult:
        """Compare the live system state with the task's expected final state.

        ``task`` is duck-typed: it must expose ``expected_final_state`` (dict),
        ``product`` (str) and ``target_material_code`` (str | None).
        """
        expected = dict(getattr(task, "expected_final_state", {}) or {})
        if not expected:
            return VerificationResult(
                passed=True, expected=expected, observed={},
                missing=[], detail="no expected final state declared",
            )

        observed = env.system_state(
            product=getattr(task, "product", None),
            material_code=getattr(task, "target_material_code", None),
        )

        missing = [key for key, exp in expected.items()
                   if not self._matches(observed.get(key), exp)]

        passed = len(missing) == 0
        detail = (
            "all expected conditions observed in live system state"
            if passed else
            f"{len(missing)} condition(s) not met: {missing}"
        )
        return VerificationResult(
            passed=passed, expected=expected, observed=observed,
            missing=missing, detail=detail,
        )

    @staticmethod
    def _matches(got: Any, expected: Any) -> bool:
        if expected is None:
            # "should exist" expectation
            return got is not None
        if isinstance(expected, str) and isinstance(got, str):
            return got.strip().upper() == expected.strip().upper()
        return got == expected
