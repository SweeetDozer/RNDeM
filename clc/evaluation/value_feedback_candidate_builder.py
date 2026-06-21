from dataclasses import dataclass
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.system.system_state import SystemState


MIN_EVIDENCE_STRENGTH = 0.25
VALUE_FEEDBACK_CANDIDATE_COOLDOWN_TICKS = 6
SIGNIFICANT_SCORE_DELTA = 0.10
REQUIRED_FIELDS = (
    "target_satisfaction_id",
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
class _CandidateMemory:
    tick: int
    status: str
    satisfaction_score: float
    evidence_strength: float


class ValueFeedbackCandidateBuilder:
    """Builds reviewable value feedback candidates from target satisfaction observations."""

    module_name = "value_feedback_candidate_builder"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.candidate_kind = pattern_registry.id("value_feedback_candidate")
        self.candidate_type_ids = {
            "value_positive_candidate": pattern_registry.id("value_positive_candidate"),
            "value_negative_candidate": pattern_registry.id("value_negative_candidate"),
            "value_mixed_candidate": pattern_registry.id("value_mixed_candidate"),
            "value_inconclusive_candidate": pattern_registry.id("value_inconclusive_candidate"),
        }
        self.recommendation_ids = {
            "increase_value_confidence": pattern_registry.id("value_feedback_increase_candidate"),
            "decrease_value_confidence": pattern_registry.id("value_feedback_decrease_candidate"),
            "increase_target_usefulness_link": pattern_registry.id("value_feedback_increase_candidate"),
            "increase_avoidance_warning": pattern_registry.id("value_feedback_decrease_candidate"),
            "request_more_evidence": pattern_registry.id("value_feedback_request_more_evidence"),
            "no_value_update": pattern_registry.id("value_feedback_review_candidate"),
        }
        self._emitted: dict[str, _CandidateMemory] = {}

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        if system_state.mode not in {"active", "recovery", "consolidation"}:
            return []
        operations: list[ContextOperation] = []
        for observation in memory.get_recent_target_satisfaction_observations(12):
            if not _has_required_fields(observation):
                continue
            if _safe_float(observation.get("evidence_strength")) < MIN_EVIDENCE_STRENGTH:
                continue
            source_id = str(observation.get("target_satisfaction_id", ""))
            status = str(observation.get("satisfaction_status", ""))
            score = _safe_float(observation.get("satisfaction_score"))
            evidence = _safe_float(observation.get("evidence_strength"))
            if not self._should_emit(tick, source_id, status, score, evidence):
                continue
            self._emitted[source_id] = _CandidateMemory(tick, status, score, evidence)
            operations.append(self._operation(tick, observation))
        if len(self._emitted) > 256:
            self._emitted = dict(list(self._emitted.items())[-128:])
        return operations

    def _operation(self, tick: int, observation: dict[str, Any]) -> ContextOperation:
        status = str(observation.get("satisfaction_status", ""))
        score = _safe_float(observation.get("satisfaction_score"))
        evidence = _safe_float(observation.get("evidence_strength"))
        mechanism_score = _safe_float(observation.get("mechanism_score"))
        candidate_type = _candidate_type(status, score, evidence)
        value_direction = _value_direction(status, score, evidence)
        recommendation = _recommended_future_operation(status, score, evidence)
        candidate_strength = _clamp(abs(score) * 0.60 + evidence * 0.25 + mechanism_score * 0.15)
        activation = _clamp(max(0.35, candidate_strength * 0.75))
        payload = {
            "value_feedback_candidate_id": self.id_gen.next("value_feedback_candidate"),
            "candidate_kind": self.candidate_kind,
            "candidate_type": candidate_type,
            "candidate_type_pattern_id": self.candidate_type_ids[candidate_type],
            "value_direction": value_direction,
            "candidate_strength": round(candidate_strength, 3),
            "recommended_future_operation": recommendation,
            "recommended_operation_pattern_id": self.recommendation_ids[recommendation],
            "apply_now": False,
            "source_target_satisfaction_id": str(observation.get("target_satisfaction_id", "")),
            "source_decision_id": str(observation.get("source_decision_id", "")),
            "source_experience_id": str(observation.get("source_experience_id", "")),
            "source_mechanism_search_id": str(observation.get("source_mechanism_search_id", "")),
            "source_target_observation_id": str(observation.get("source_target_observation_id", "")),
            "target_pattern_id": str(observation.get("target_pattern_id", "")),
            "target_pattern_name": str(observation.get("target_pattern_name") or self.pattern_registry.debug_name(str(observation.get("target_pattern_id", "")))),
            "target_kind": str(observation.get("target_kind", "")),
            "target_role_names": [str(role) for role in observation.get("target_role_names", ())],
            "mechanism_purpose": str(observation.get("mechanism_purpose", "")),
            "mechanism_score": round(mechanism_score, 3),
            "satisfaction_status": status,
            "satisfaction_score": round(score, 3),
            "evidence_strength": round(evidence, 3),
            "memory_modified": False,
            "permanent_memory_modified": False,
            "expsm_modified": False,
            "akbsm_modified": False,
            "activation": round(activation, 3),
            "ttl": 10,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.VALUE_FEEDBACK_CANDIDATE,
            tick,
            self.module_name,
            None,
            payload,
        )

    def _should_emit(self, tick: int, source_id: str, status: str, score: float, evidence: float) -> bool:
        previous = self._emitted.get(source_id)
        if previous is None:
            return True
        if status != previous.status:
            return True
        if abs(score - previous.satisfaction_score) >= SIGNIFICANT_SCORE_DELTA:
            return True
        if abs(evidence - previous.evidence_strength) >= SIGNIFICANT_SCORE_DELTA:
            return True
        return tick - previous.tick >= VALUE_FEEDBACK_CANDIDATE_COOLDOWN_TICKS


def _has_required_fields(observation: dict[str, Any]) -> bool:
    for field in REQUIRED_FIELDS:
        value = observation.get(field)
        if value is None or value == "":
            return False
        if isinstance(value, (list, tuple, set, dict)) and not value:
            return False
    return True


def _candidate_type(status: str, satisfaction_score: float, evidence_strength: float) -> str:
    if status in {"satisfied", "partially_satisfied"}:
        return "value_positive_candidate"
    if status == "worsened":
        return "value_negative_candidate"
    if status == "not_satisfied":
        if evidence_strength >= 0.60 and satisfaction_score <= -0.35:
            return "value_negative_candidate"
        return "value_mixed_candidate"
    return "value_inconclusive_candidate"


def _value_direction(status: str, score: float, evidence_strength: float) -> str:
    if status == "worsened":
        return "negative"
    if status == "not_satisfied":
        if evidence_strength >= 0.60 and score <= -0.35:
            return "negative"
        return "mixed_or_unclear"
    if score > 0.20:
        return "positive"
    if score < -0.20:
        return "negative"
    return "mixed_or_unclear"


def _recommended_future_operation(status: str, satisfaction_score: float, evidence_strength: float) -> str:
    if status in {"satisfied", "partially_satisfied"}:
        return "increase_value_confidence"
    if status == "worsened":
        return "increase_avoidance_warning"
    if status == "not_satisfied":
        if evidence_strength >= 0.60 and satisfaction_score <= -0.35:
            return "decrease_value_confidence"
        return "request_more_evidence"
    return "request_more_evidence"


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
