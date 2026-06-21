from dataclasses import dataclass
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.system.system_state import SystemState


READY_STRENGTH = 0.70
READY_EVIDENCE = 0.60
WAIT_STRENGTH = 0.35
WAIT_EVIDENCE = 0.25
REJECT_EVIDENCE = 0.15
VALUE_FEEDBACK_REVIEW_COOLDOWN_TICKS = 8
SIGNIFICANT_REVIEW_DELTA = 0.10
VALID_CANDIDATE_TYPES = {
    "value_positive_candidate",
    "value_negative_candidate",
    "value_mixed_candidate",
    "value_inconclusive_candidate",
}
REQUIRED_FIELDS = (
    "value_feedback_candidate_id",
    "candidate_type",
    "value_direction",
    "candidate_strength",
    "recommended_future_operation",
    "apply_now",
    "source_target_satisfaction_id",
    "source_decision_id",
    "source_experience_id",
    "source_mechanism_search_id",
    "source_target_observation_id",
    "target_pattern_id",
    "target_kind",
    "target_role_names",
    "mechanism_purpose",
    "mechanism_score",
    "satisfaction_status",
    "satisfaction_score",
    "evidence_strength",
)


@dataclass(frozen=True)
class ReviewDecision:
    decision: str
    reason: str


@dataclass(frozen=True)
class _ReviewMemory:
    tick: int
    decision: str
    candidate_strength: float
    evidence_strength: float


class ValueFeedbackReviewGate:
    """Reviews value feedback candidates without applying them to memory."""

    module_name = "value_feedback_review_gate"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.review_kind = pattern_registry.id("value_feedback_review")
        self.decision_patterns = {
            "ready": pattern_registry.id("value_feedback_review_ready"),
            "wait": pattern_registry.id("value_feedback_review_wait"),
            "reject": pattern_registry.id("value_feedback_review_reject"),
            "archive": pattern_registry.id("value_feedback_review_archive"),
        }
        self.readiness_patterns = {
            True: pattern_registry.id("value_feedback_ready_for_future_application"),
            False: pattern_registry.id("value_feedback_not_ready"),
        }
        self.reason_patterns = {
            "strong_positive_value_feedback": pattern_registry.id("value_feedback_review_strong_positive"),
            "strong_negative_value_feedback": pattern_registry.id("value_feedback_review_strong_negative"),
            "weak_evidence_wait": pattern_registry.id("value_feedback_review_weak_evidence"),
            "insufficient_evidence_reject": pattern_registry.id("value_feedback_review_insufficient_evidence"),
            "weak_negative_evidence_wait": pattern_registry.id("value_feedback_review_weak_negative_evidence"),
            "negative_insufficient_evidence_reject": pattern_registry.id("value_feedback_review_negative_insufficient_evidence"),
            "inconclusive_wait": pattern_registry.id("value_feedback_review_inconclusive"),
            "missing_trace_reject": pattern_registry.id("value_feedback_review_insufficient_evidence"),
            "duplicate_archive": pattern_registry.id("value_feedback_review_archive"),
        }
        self._reviewed: dict[str, _ReviewMemory] = {}

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        if system_state.mode not in {"consolidation", "recovery"}:
            return []
        operations: list[ContextOperation] = []
        for candidate in memory.get_recent_value_feedback_candidates(16):
            source_id = str(candidate.get("value_feedback_candidate_id", ""))
            if not source_id:
                continue
            review = self._review_candidate(candidate)
            strength = _safe_float(candidate.get("candidate_strength"))
            evidence = _safe_float(candidate.get("evidence_strength"))
            if not self._should_emit(tick, source_id, review.decision, strength, evidence):
                continue
            self._reviewed[source_id] = _ReviewMemory(tick, review.decision, strength, evidence)
            operations.append(self._operation(tick, candidate, review))
        if len(self._reviewed) > 256:
            self._reviewed = dict(list(self._reviewed.items())[-128:])
        return operations

    def _review_candidate(self, candidate: dict[str, Any]) -> ReviewDecision:
        if candidate.get("apply_now") is not False:
            return ReviewDecision("reject", "missing_trace_reject")
        if not _has_required_fields(candidate):
            return ReviewDecision("reject", "missing_trace_reject")
        candidate_type = str(candidate.get("candidate_type", ""))
        if candidate_type not in VALID_CANDIDATE_TYPES:
            return ReviewDecision("reject", "missing_trace_reject")
        strength = _safe_float(candidate.get("candidate_strength"))
        evidence = _safe_float(candidate.get("evidence_strength"))
        if evidence < REJECT_EVIDENCE:
            return ReviewDecision("reject", "insufficient_evidence_reject")
        if candidate_type == "value_inconclusive_candidate":
            if strength >= WAIT_STRENGTH and evidence >= WAIT_EVIDENCE:
                return ReviewDecision("wait", "inconclusive_wait")
            return ReviewDecision("reject", "insufficient_evidence_reject")
        if candidate_type == "value_negative_candidate":
            if strength >= 0.75 and evidence >= 0.70:
                return ReviewDecision("ready", "strong_negative_value_feedback")
            if strength >= WAIT_STRENGTH and evidence >= WAIT_EVIDENCE:
                return ReviewDecision("wait", "weak_negative_evidence_wait")
            return ReviewDecision("reject", "negative_insufficient_evidence_reject")
        if strength >= READY_STRENGTH and evidence >= READY_EVIDENCE:
            if candidate_type == "value_positive_candidate":
                return ReviewDecision("ready", "strong_positive_value_feedback")
            return ReviewDecision("ready", "weak_evidence_wait")
        if strength >= WAIT_STRENGTH and evidence >= WAIT_EVIDENCE:
            return ReviewDecision("wait", "weak_evidence_wait")
        return ReviewDecision("reject", "insufficient_evidence_reject")

    def _operation(self, tick: int, candidate: dict[str, Any], review: ReviewDecision) -> ContextOperation:
        ready = review.decision == "ready"
        strength = _safe_float(candidate.get("candidate_strength"))
        evidence = _safe_float(candidate.get("evidence_strength"))
        activation = _clamp(0.35 + max(strength, evidence) * 0.35)
        payload = {
            "value_feedback_review_id": self.id_gen.next("value_feedback_review"),
            "review_kind": self.review_kind,
            "review_decision_pattern_id": self.decision_patterns[review.decision],
            "review_reason_pattern_id": self.reason_patterns[review.reason],
            "readiness_pattern_id": self.readiness_patterns[ready],
            "source_value_feedback_candidate_id": str(candidate.get("value_feedback_candidate_id", "")),
            "source_target_satisfaction_id": str(candidate.get("source_target_satisfaction_id", "")),
            "review_decision": review.decision,
            "review_reason": review.reason,
            "candidate_type": str(candidate.get("candidate_type", "")),
            "value_direction": str(candidate.get("value_direction", "")),
            "candidate_strength": round(strength, 3),
            "evidence_strength": round(evidence, 3),
            "satisfaction_status": str(candidate.get("satisfaction_status", "")),
            "satisfaction_score": round(_safe_float(candidate.get("satisfaction_score")), 3),
            "recommended_future_operation": str(candidate.get("recommended_future_operation", "")),
            "apply_now": False,
            "ready_for_future_application": ready,
            "source_decision_id": str(candidate.get("source_decision_id", "")),
            "source_experience_id": str(candidate.get("source_experience_id", "")),
            "source_mechanism_search_id": str(candidate.get("source_mechanism_search_id", "")),
            "source_target_observation_id": str(candidate.get("source_target_observation_id", "")),
            "target_pattern_id": str(candidate.get("target_pattern_id", "")),
            "target_pattern_name": str(
                candidate.get("target_pattern_name")
                or self.pattern_registry.debug_name(str(candidate.get("target_pattern_id", "")))
            ),
            "target_kind": str(candidate.get("target_kind", "")),
            "target_role_names": [str(role) for role in candidate.get("target_role_names", ())],
            "mechanism_purpose": str(candidate.get("mechanism_purpose", "")),
            "mechanism_score": round(_safe_float(candidate.get("mechanism_score")), 3),
            "memory_modified": False,
            "permanent_memory_modified": False,
            "expsm_modified": False,
            "akbsm_modified": False,
            "activation": round(activation, 3),
            "ttl": 12,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.VALUE_FEEDBACK_REVIEW,
            tick,
            self.module_name,
            None,
            payload,
        )

    def _should_emit(
        self,
        tick: int,
        source_id: str,
        decision: str,
        candidate_strength: float,
        evidence_strength: float,
    ) -> bool:
        previous = self._reviewed.get(source_id)
        if previous is None:
            return True
        if decision != previous.decision:
            return True
        if abs(candidate_strength - previous.candidate_strength) >= SIGNIFICANT_REVIEW_DELTA:
            return True
        if abs(evidence_strength - previous.evidence_strength) >= SIGNIFICANT_REVIEW_DELTA:
            return True
        return tick - previous.tick >= VALUE_FEEDBACK_REVIEW_COOLDOWN_TICKS


def _has_required_fields(candidate: dict[str, Any]) -> bool:
    for field in REQUIRED_FIELDS:
        value = candidate.get(field)
        if field == "apply_now":
            if value is not False:
                return False
            continue
        if value is None or value == "":
            return False
        if isinstance(value, (list, tuple, set, dict)) and not value:
            return False
    return True


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
