from dataclasses import dataclass
from typing import Any

from clc.core.ids import IdGenerator
from clc.evaluation.reflection_review import ReflectionReview


MAX_RECENT_POLICY_PRESSURES = 50


@dataclass(frozen=True)
class PolicyPressure:
    pressure_id: str
    tick: int
    active: bool
    pressure_type: str
    severity: str
    confidence: float
    source_review_status: str
    source_primary_issue: str
    recommended_future_operation: str
    apply_now: bool
    evidence: dict[str, Any]
    tags: tuple[str, ...]


class PolicyPressureBuilder:
    module_name = "policy_pressure_builder"

    def __init__(
        self,
        id_gen: IdGenerator,
        max_recent_policy_pressures: int = MAX_RECENT_POLICY_PRESSURES,
    ) -> None:
        if max_recent_policy_pressures <= 0:
            raise ValueError("PolicyPressureBuilder max_recent_policy_pressures must be positive")
        self.id_gen = id_gen
        self.max_recent_policy_pressures = max_recent_policy_pressures
        self.latest_pressure: PolicyPressure | None = None
        self._recent_pressures: list[PolicyPressure] = []

    def build(
        self,
        *,
        tick: int,
        reflection_review: ReflectionReview | None,
    ) -> PolicyPressure:
        decision = _pressure_decision(reflection_review)
        pressure = PolicyPressure(
            pressure_id=self.id_gen.next("policy_pressure"),
            tick=tick,
            active=decision["active"],
            pressure_type=decision["pressure_type"],
            severity=decision["severity"],
            confidence=_confidence(reflection_review, decision["pressure_type"]),
            source_review_status=reflection_review.review_status if reflection_review is not None else "missing_review",
            source_primary_issue=reflection_review.primary_issue if reflection_review is not None else "none",
            recommended_future_operation=decision["recommended_future_operation"],
            apply_now=False,
            evidence=_evidence(reflection_review),
            tags=("policy_pressure", decision["pressure_type"]),
        )
        return self._store(pressure)

    def recent_pressures(self, limit: int = 8) -> list[PolicyPressure]:
        return self._recent_pressures[-limit:]

    def _store(self, pressure: PolicyPressure) -> PolicyPressure:
        self.latest_pressure = pressure
        self._recent_pressures.append(pressure)
        if len(self._recent_pressures) > self.max_recent_policy_pressures:
            self._recent_pressures = self._recent_pressures[-self.max_recent_policy_pressures :]
        return pressure


def _pressure_decision(reflection_review: ReflectionReview | None) -> dict[str, Any]:
    if reflection_review is None or reflection_review.review_status == "no_reflection_data":
        return {
            "active": False,
            "pressure_type": "no_policy_pressure",
            "severity": "info",
            "recommended_future_operation": "collect_initial_decision_history",
        }
    if reflection_review.review_status == "needs_more_evidence":
        return {
            "active": True,
            "pressure_type": "evidence_pressure",
            "severity": reflection_review.severity,
            "recommended_future_operation": reflection_review.recommended_future_operation,
        }
    if reflection_review.review_status == "uncertain_recent_behavior":
        return {
            "active": True,
            "pressure_type": "uncertainty_pressure",
            "severity": "medium",
            "recommended_future_operation": "inspect_candidate_discrimination",
        }
    if reflection_review.review_status == "guard_policy_tension":
        return {
            "active": True,
            "pressure_type": "guard_pressure",
            "severity": reflection_review.severity,
            "recommended_future_operation": "inspect_guard_policy_tension",
        }
    if reflection_review.review_status == "weak_value_signal":
        return {
            "active": True,
            "pressure_type": "value_signal_pressure",
            "severity": "low",
            "recommended_future_operation": "inspect_value_signal_coverage",
        }
    if reflection_review.review_status == "mixed_reflection_state":
        return {
            "active": True,
            "pressure_type": "mixed_policy_pressure",
            "severity": "low",
            "recommended_future_operation": "review_mixed_history",
        }
    if reflection_review.review_status == "stable_recent_behavior":
        return {
            "active": False,
            "pressure_type": "stability_pressure",
            "severity": "info",
            "recommended_future_operation": "maintain_current_policy",
        }
    return {
        "active": True,
        "pressure_type": "mixed_policy_pressure",
        "severity": "low",
        "recommended_future_operation": "review_mixed_history",
    }


def _confidence(reflection_review: ReflectionReview | None, pressure_type: str) -> float:
    if reflection_review is None:
        return 0.0
    if pressure_type == "no_policy_pressure":
        return 0.0
    return _clamp(reflection_review.confidence)


def _evidence(reflection_review: ReflectionReview | None) -> dict[str, Any]:
    if reflection_review is None:
        return {
            "review_status": "missing_review",
            "primary_issue": "none",
            "review_severity": "info",
            "review_confidence": 0.0,
            "need_more_evidence_active": False,
            "source_trend_label": None,
            "source_reflection_types": [],
        }
    return {
        "review_status": reflection_review.review_status,
        "primary_issue": reflection_review.primary_issue,
        "review_severity": reflection_review.severity,
        "review_confidence": reflection_review.confidence,
        "need_more_evidence_active": reflection_review.need_more_evidence_active,
        "source_trend_label": reflection_review.source_trend_label,
        "source_reflection_types": list(reflection_review.source_reflection_types),
    }


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)
