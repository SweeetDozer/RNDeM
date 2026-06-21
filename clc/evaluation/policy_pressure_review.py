from dataclasses import dataclass
from typing import Any

from clc.core.ids import IdGenerator
from clc.evaluation.policy_pressure import PolicyPressure


MAX_RECENT_POLICY_PRESSURE_REVIEWS = 50


@dataclass(frozen=True)
class PolicyPressureReview:
    review_id: str
    tick: int
    review_status: str
    severity: str
    confidence: float
    pressure_type: str
    pressure_active: bool
    primary_issue: str
    summary: str
    recommended_future_operation: str
    apply_now: bool
    evidence: dict[str, Any]
    tags: tuple[str, ...]


class PolicyPressureReviewBuilder:
    module_name = "policy_pressure_review_builder"

    def __init__(
        self,
        id_gen: IdGenerator,
        max_recent_policy_pressure_reviews: int = MAX_RECENT_POLICY_PRESSURE_REVIEWS,
    ) -> None:
        if max_recent_policy_pressure_reviews <= 0:
            raise ValueError("PolicyPressureReviewBuilder max_recent_policy_pressure_reviews must be positive")
        self.id_gen = id_gen
        self.max_recent_policy_pressure_reviews = max_recent_policy_pressure_reviews
        self.latest_review: PolicyPressureReview | None = None
        self._recent_reviews: list[PolicyPressureReview] = []

    def build(
        self,
        *,
        tick: int,
        policy_pressure: PolicyPressure | None,
    ) -> PolicyPressureReview:
        decision = _review_decision(policy_pressure)
        review = PolicyPressureReview(
            review_id=self.id_gen.next("policy_pressure_review"),
            tick=tick,
            review_status=decision["review_status"],
            severity=decision["severity"],
            confidence=_confidence(policy_pressure),
            pressure_type=decision["pressure_type"],
            pressure_active=decision["pressure_active"],
            primary_issue=decision["primary_issue"],
            summary=decision["summary"],
            recommended_future_operation=decision["recommended_future_operation"],
            apply_now=False,
            evidence=_evidence(policy_pressure),
            tags=("policy_pressure_review", decision["review_status"], decision["pressure_type"]),
        )
        return self._store(review)

    def recent_reviews(self, limit: int = 8) -> list[PolicyPressureReview]:
        return self._recent_reviews[-limit:]

    def _store(self, review: PolicyPressureReview) -> PolicyPressureReview:
        self.latest_review = review
        self._recent_reviews.append(review)
        if len(self._recent_reviews) > self.max_recent_policy_pressure_reviews:
            self._recent_reviews = self._recent_reviews[-self.max_recent_policy_pressure_reviews :]
        return review


def _review_decision(policy_pressure: PolicyPressure | None) -> dict[str, Any]:
    if policy_pressure is None:
        return {
            "review_status": "no_pressure_data",
            "severity": "info",
            "pressure_type": "no_policy_pressure",
            "pressure_active": False,
            "primary_issue": "no_pressure_data",
            "summary": "No policy pressure data is available yet.",
            "recommended_future_operation": "collect_initial_pressure_data",
        }
    if policy_pressure.pressure_type == "no_policy_pressure":
        return {
            "review_status": "no_active_pressure",
            "severity": "info",
            "pressure_type": policy_pressure.pressure_type,
            "pressure_active": False,
            "primary_issue": "none",
            "summary": "No active policy pressure is present; initial decision history should continue to accumulate.",
            "recommended_future_operation": "collect_initial_decision_history",
        }
    if policy_pressure.pressure_type == "stability_pressure":
        return {
            "review_status": "stability_pressure_review",
            "severity": "info",
            "pressure_type": policy_pressure.pressure_type,
            "pressure_active": policy_pressure.active,
            "primary_issue": "stable_recent_behavior",
            "summary": "Recent behavior appears stable; no active policy pressure is applied.",
            "recommended_future_operation": "maintain_current_policy",
        }
    if policy_pressure.pressure_type == "evidence_pressure":
        return {
            "review_status": "evidence_pressure_review",
            "severity": policy_pressure.severity,
            "pressure_type": policy_pressure.pressure_type,
            "pressure_active": policy_pressure.active,
            "primary_issue": policy_pressure.source_primary_issue,
            "summary": "Evidence pressure is active; recent decision history suggests more evidence should be collected.",
            "recommended_future_operation": policy_pressure.recommended_future_operation,
        }
    if policy_pressure.pressure_type == "uncertainty_pressure":
        return {
            "review_status": "uncertainty_pressure_review",
            "severity": policy_pressure.severity,
            "pressure_type": policy_pressure.pressure_type,
            "pressure_active": policy_pressure.active,
            "primary_issue": policy_pressure.source_primary_issue,
            "summary": "Uncertainty pressure is active; candidate discrimination should be inspected.",
            "recommended_future_operation": "inspect_candidate_discrimination",
        }
    if policy_pressure.pressure_type == "guard_pressure":
        return {
            "review_status": "guard_pressure_review",
            "severity": policy_pressure.severity,
            "pressure_type": policy_pressure.pressure_type,
            "pressure_active": policy_pressure.active,
            "primary_issue": "guard_policy_tension",
            "summary": "Guard pressure is active; guard policy tension should be inspected.",
            "recommended_future_operation": "inspect_guard_policy_tension",
        }
    if policy_pressure.pressure_type == "value_signal_pressure":
        return {
            "review_status": "value_signal_pressure_review",
            "severity": policy_pressure.severity,
            "pressure_type": policy_pressure.pressure_type,
            "pressure_active": policy_pressure.active,
            "primary_issue": "weak_value_influence",
            "summary": "Value signal pressure is active; value signal coverage should be inspected.",
            "recommended_future_operation": "inspect_value_signal_coverage",
        }
    if policy_pressure.pressure_type == "mixed_policy_pressure":
        return {
            "review_status": "mixed_pressure_review",
            "severity": policy_pressure.severity,
            "pressure_type": policy_pressure.pressure_type,
            "pressure_active": policy_pressure.active,
            "primary_issue": "mixed_cycle_history",
            "summary": "Mixed policy pressure is active; mixed recent decision history should be reviewed.",
            "recommended_future_operation": "review_mixed_history",
        }
    return {
        "review_status": "mixed_pressure_review",
        "severity": policy_pressure.severity,
        "pressure_type": policy_pressure.pressure_type,
        "pressure_active": policy_pressure.active,
        "primary_issue": policy_pressure.source_primary_issue or "mixed_cycle_history",
        "summary": "Policy pressure state is mixed; recent decision history should be reviewed.",
        "recommended_future_operation": "review_mixed_history",
    }


def _confidence(policy_pressure: PolicyPressure | None) -> float:
    if policy_pressure is None:
        return 0.0
    return _clamp(policy_pressure.confidence)


def _evidence(policy_pressure: PolicyPressure | None) -> dict[str, Any]:
    if policy_pressure is None:
        return {
            "pressure_active": False,
            "pressure_type": "no_policy_pressure",
            "pressure_severity": "info",
            "pressure_confidence": 0.0,
            "source_review_status": "missing_pressure",
            "source_primary_issue": "no_pressure_data",
            "pressure_recommended_future_operation": "collect_initial_pressure_data",
        }
    return {
        "pressure_active": policy_pressure.active,
        "pressure_type": policy_pressure.pressure_type,
        "pressure_severity": policy_pressure.severity,
        "pressure_confidence": policy_pressure.confidence,
        "source_review_status": policy_pressure.source_review_status,
        "source_primary_issue": policy_pressure.source_primary_issue,
        "pressure_recommended_future_operation": policy_pressure.recommended_future_operation,
    }


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)
