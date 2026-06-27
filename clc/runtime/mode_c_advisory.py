from dataclasses import dataclass
from typing import Any

from clc.runtime.memory_mutation_policy import MemoryMutationPolicy


@dataclass(frozen=True)
class MemoryGateAdvisory:
    """Metadata-only future Mode C advisory payload for memory review gates."""

    source: str
    tick: int
    advisory_type: str
    severity: str
    confidence: float
    recommendation: str
    reason: str
    apply_now: bool = False


@dataclass(frozen=True)
class ModeCMemoryGateAdvisoryProvider:
    """Builds metadata-only advisory payloads when an explicit policy enables them."""

    policy: MemoryMutationPolicy

    def from_policy_pressure_review(self, review: Any | None) -> tuple[MemoryGateAdvisory, ...]:
        if not self.policy.mode_c_memory_gate_advisory_enabled or review is None:
            return ()
        return (
            MemoryGateAdvisory(
                source="PolicyPressureReview",
                tick=int(getattr(review, "tick", 0)),
                advisory_type=str(getattr(review, "pressure_type", "policy_pressure_review")),
                severity=str(getattr(review, "severity", "info")),
                confidence=_clamp_float(getattr(review, "confidence", 0.0)),
                recommendation=str(getattr(review, "recommended_future_operation", "observe_only")),
                reason=str(getattr(review, "primary_issue", "no_primary_issue")),
                apply_now=False,
            ),
        )


def _clamp_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, number)), 3)
