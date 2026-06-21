from dataclasses import dataclass
from typing import Any

from clc.core.ids import IdGenerator
from clc.evaluation.decision_cycle_history_view import DecisionCycleHistorySnapshot
from clc.evaluation.need_more_evidence_signal import NeedMoreEvidenceSignal
from clc.evaluation.reflection_candidate_builder import ReflectionCandidate


MAX_RECENT_REFLECTION_REVIEWS = 50


@dataclass(frozen=True)
class ReflectionReview:
    review_id: str
    tick: int
    review_status: str
    severity: str
    confidence: float
    primary_issue: str
    summary: str
    source_trend_label: str | None
    need_more_evidence_active: bool
    source_reflection_types: tuple[str, ...]
    recommended_future_operation: str
    apply_now: bool
    evidence: dict[str, Any]
    tags: tuple[str, ...]


class ReflectionReviewBuilder:
    module_name = "reflection_review_builder"

    def __init__(
        self,
        id_gen: IdGenerator,
        max_recent_reflection_reviews: int = MAX_RECENT_REFLECTION_REVIEWS,
    ) -> None:
        if max_recent_reflection_reviews <= 0:
            raise ValueError("ReflectionReviewBuilder max_recent_reflection_reviews must be positive")
        self.id_gen = id_gen
        self.max_recent_reflection_reviews = max_recent_reflection_reviews
        self.latest_review: ReflectionReview | None = None
        self._recent_reviews: list[ReflectionReview] = []

    def build(
        self,
        *,
        tick: int,
        history_snapshot: DecisionCycleHistorySnapshot | None,
        reflection_candidates: list[ReflectionCandidate],
        need_more_evidence_signal: NeedMoreEvidenceSignal | None,
    ) -> ReflectionReview:
        decision = _review_decision(history_snapshot, reflection_candidates, need_more_evidence_signal)
        review = ReflectionReview(
            review_id=self.id_gen.next("reflection_review"),
            tick=tick,
            review_status=decision["review_status"],
            severity=decision["severity"],
            confidence=_confidence(history_snapshot, reflection_candidates, need_more_evidence_signal),
            primary_issue=decision["primary_issue"],
            summary=_summary(decision["review_status"]),
            source_trend_label=history_snapshot.trend_label if history_snapshot is not None else None,
            need_more_evidence_active=bool(need_more_evidence_signal and need_more_evidence_signal.active),
            source_reflection_types=tuple(sorted({candidate.reflection_type for candidate in reflection_candidates})),
            recommended_future_operation=decision["recommended_future_operation"],
            apply_now=False,
            evidence=_evidence(history_snapshot, reflection_candidates, need_more_evidence_signal),
            tags=("reflection_review", decision["review_status"], decision["primary_issue"]),
        )
        return self._store(review)

    def recent_reviews(self, limit: int = 8) -> list[ReflectionReview]:
        return self._recent_reviews[-limit:]

    def _store(self, review: ReflectionReview) -> ReflectionReview:
        self.latest_review = review
        self._recent_reviews.append(review)
        if len(self._recent_reviews) > self.max_recent_reflection_reviews:
            self._recent_reviews = self._recent_reviews[-self.max_recent_reflection_reviews :]
        return review


def _review_decision(
    history_snapshot: DecisionCycleHistorySnapshot | None,
    reflection_candidates: list[ReflectionCandidate],
    need_more_evidence_signal: NeedMoreEvidenceSignal | None,
) -> dict[str, str]:
    if history_snapshot is None or history_snapshot.observed_count == 0:
        return {
            "review_status": "no_reflection_data",
            "severity": "info",
            "primary_issue": "no_decision_history",
            "recommended_future_operation": "collect_initial_decision_history",
        }
    if need_more_evidence_signal is not None and need_more_evidence_signal.active:
        return {
            "review_status": "needs_more_evidence",
            "severity": need_more_evidence_signal.severity,
            "primary_issue": need_more_evidence_signal.reason,
            "recommended_future_operation": need_more_evidence_signal.recommended_future_operation,
        }
    guard_candidate = _first_candidate(reflection_candidates, "guard_policy_tension")
    if guard_candidate is not None:
        return {
            "review_status": "guard_policy_tension",
            "severity": guard_candidate.severity,
            "primary_issue": "guard_policy_tension",
            "recommended_future_operation": "inspect_guard_policy_tension",
        }
    if _first_candidate(reflection_candidates, "weak_value_influence") is not None:
        return {
            "review_status": "weak_value_signal",
            "severity": "low",
            "primary_issue": "weak_value_influence",
            "recommended_future_operation": "inspect_value_signal_coverage",
        }
    if history_snapshot.trend_label == "mostly_clean":
        return {
            "review_status": "stable_recent_behavior",
            "severity": "info",
            "primary_issue": "stable_clean_selection",
            "recommended_future_operation": "maintain_current_policy",
        }
    if history_snapshot.trend_label == "uncertain_recent_history":
        return {
            "review_status": "uncertain_recent_behavior",
            "severity": "medium",
            "primary_issue": "repeated_uncertain_selection",
            "recommended_future_operation": "inspect_candidate_discrimination",
        }
    return {
        "review_status": "mixed_reflection_state",
        "severity": "low",
        "primary_issue": "mixed_cycle_history",
        "recommended_future_operation": "review_mixed_history",
    }


def _confidence(
    history_snapshot: DecisionCycleHistorySnapshot | None,
    reflection_candidates: list[ReflectionCandidate],
    need_more_evidence_signal: NeedMoreEvidenceSignal | None,
) -> float:
    if need_more_evidence_signal is not None and need_more_evidence_signal.active:
        return _clamp(need_more_evidence_signal.confidence)
    if reflection_candidates:
        return _clamp(max(candidate.confidence for candidate in reflection_candidates))
    if history_snapshot is not None and history_snapshot.window_size > 0:
        return _clamp(history_snapshot.observed_count / history_snapshot.window_size)
    return 0.0


def _summary(review_status: str) -> str:
    summaries = {
        "no_reflection_data": "No decision history is available yet.",
        "stable_recent_behavior": "Recent decisions are mostly clean; current policy can be maintained.",
        "needs_more_evidence": (
            "Recent decisions are often uncertain; more evidence should be collected before stronger future conclusions."
        ),
        "uncertain_recent_behavior": "Recent decisions are often uncertain; candidate discrimination should be inspected.",
        "guard_policy_tension": (
            "Guard constraints frequently affect high-scoring candidates; guard policy tension should be inspected."
        ),
        "weak_value_signal": "Value signals rarely influence recent decisions; value signal coverage should be inspected.",
        "mixed_reflection_state": "Recent reflective signals are mixed; recent decision context should be reviewed.",
    }
    return summaries.get(review_status, "Recent reflective state is mixed.")


def _evidence(
    history_snapshot: DecisionCycleHistorySnapshot | None,
    reflection_candidates: list[ReflectionCandidate],
    need_more_evidence_signal: NeedMoreEvidenceSignal | None,
) -> dict[str, Any]:
    return {
        "history_observed_count": history_snapshot.observed_count if history_snapshot is not None else 0,
        "history_trend_label": history_snapshot.trend_label if history_snapshot is not None else None,
        "reflection_candidate_count": len(reflection_candidates),
        "reflection_types": [candidate.reflection_type for candidate in reflection_candidates],
        "need_more_evidence_active": bool(need_more_evidence_signal and need_more_evidence_signal.active),
        "need_more_evidence_reason": (
            need_more_evidence_signal.reason if need_more_evidence_signal is not None else None
        ),
        "status_counts": dict(history_snapshot.status_counts) if history_snapshot is not None else {},
        "flag_counts": dict(history_snapshot.flag_counts) if history_snapshot is not None else {},
    }


def _first_candidate(
    reflection_candidates: list[ReflectionCandidate],
    reflection_type: str,
) -> ReflectionCandidate | None:
    for candidate in reflection_candidates:
        if candidate.reflection_type == reflection_type:
            return candidate
    return None


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)
