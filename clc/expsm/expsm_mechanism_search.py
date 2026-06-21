import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from clc.akbsm.akbsm_association_field import AKBSMAssociationField
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.evaluation_field import EvaluationField
from clc.evaluation.value_feedback_memory_view import ValueFeedbackMemoryView, ValueFeedbackRecordView
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


MAX_TARGETS_PER_TICK = 3
MAX_ASSOCIATED_PATTERNS_PER_TARGET = 8
MAX_MECHANISMS_PER_TARGET = 5
ACTIVE_THRESHOLD = 0.25
MIN_MECHANISM_SCORE = 0.25
MECHANISM_SEARCH_COOLDOWN_TICKS = 4
SIGNIFICANT_TARGET_DELTA = 0.10
MAX_VALUE_BONUS = 0.08
MAX_VALUE_PENALTY = 0.12
MIN_VALUE_CONFIDENCE = 0.10
TARGET_SPECIFIC_BONUS_MULTIPLIER = 1.25
TARGET_SPECIFIC_PENALTY_MULTIPLIER = 1.35


class ExpSMMechanismSearch:
    """Observation-only search for ExpSM records related to current targets."""

    module_name = "expsm_mechanism_search"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        expsm_path: str | Path,
        value_feedback_memory_view: ValueFeedbackMemoryView | None = None,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.expsm_path = Path(expsm_path)
        self.value_feedback_memory_view = value_feedback_memory_view
        self.search_kind = pattern_registry.id("expsm_mechanism_search")
        self._last_emissions: dict[str, tuple[int, float, tuple[str, ...]]] = {}

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        evaluation_field: EvaluationField,
        akbsm_association_field: AKBSMAssociationField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        del evaluation_field
        if system_state.mode not in {"active", "recovery"}:
            return []
        experiences = self._load_experiences()
        if not experiences:
            return []
        active_patterns = {pattern.pattern_id for pattern in active_field.get_patterns_above(ACTIVE_THRESHOLD)}
        targets = [
            target
            for target in memory.get_recent_evaluation_targets(12)
            if target.get("_event_tick") == tick
        ]
        targets.sort(key=lambda item: _as_float(item.get("target_score", 0.0)), reverse=True)
        operations: list[ContextOperation] = []
        for target in targets[:MAX_TARGETS_PER_TICK]:
            target_pattern_id = str(target.get("pattern_id", ""))
            if not target_pattern_id:
                continue
            related_records = self._target_related_patterns(target_pattern_id, akbsm_association_field)
            related_pattern_ids = {record["pattern_id"] for record in related_records}
            mechanisms = self._mechanisms_for_target(target, related_pattern_ids, active_patterns, experiences)
            if not mechanisms:
                continue
            if not self._should_emit(tick, target, mechanisms):
                continue
            operations.append(self._operation(tick, target, related_records, mechanisms))
        return operations

    def _load_experiences(self) -> dict[str, dict[str, Any]]:
        if not self.expsm_path.exists():
            return {}
        try:
            data = json.loads(self.expsm_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, Mapping):
            return {}
        records = data.get("experience", data.get("experiences", {}))
        if isinstance(records, Mapping):
            return {str(record_id): dict(record) for record_id, record in records.items() if isinstance(record, Mapping)}
        if isinstance(records, list):
            return {str(index): dict(record) for index, record in enumerate(records) if isinstance(record, Mapping)}
        return {}

    def _target_related_patterns(
        self,
        target_pattern_id: str,
        akbsm_association_field: AKBSMAssociationField,
    ) -> list[dict[str, Any]]:
        related = [
            {
                "pattern_id": target_pattern_id,
                "pattern_name": self.pattern_registry.debug_name(target_pattern_id),
                "source": "target",
            }
        ]
        for entry in akbsm_association_field.get_associations(target_pattern_id, MAX_ASSOCIATED_PATTERNS_PER_TARGET):
            related.append(
                {
                    "pattern_id": entry.associated_pattern_id,
                    "pattern_name": self.pattern_registry.debug_name(entry.associated_pattern_id),
                    "source": "akbsm_association",
                    "association_score": round(entry.score, 3),
                    "relation_type": entry.relation_type,
                }
            )
        return related

    def _mechanisms_for_target(
        self,
        target: dict[str, Any],
        target_related_patterns: set[str],
        active_patterns: set[str],
        experiences: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        mechanisms: list[dict[str, Any]] = []
        target_pattern = str(target.get("pattern_id", ""))
        associated_only = set(target_related_patterns) - {target_pattern}
        for experience_id, record in experiences.items():
            if _is_archived(record) or not _has_core(record):
                continue
            if_patterns = _pattern_tuple(record.get("if", ()))
            then_patterns = _pattern_tuple(record.get("then", ()))
            result_patterns = _pattern_tuple(record.get("result", ()))
            recommendation_patterns = _pattern_tuple(record.get("recommendation", ()))
            result_overlap = _jaccard(result_patterns, target_related_patterns)
            recommendation_overlap = _jaccard(recommendation_patterns, target_related_patterns)
            then_overlap = _jaccard(then_patterns, target_related_patterns)
            if_overlap = _jaccard(if_patterns, active_patterns)
            viability = _viability(record)
            effective_confidence = min(_as_float(record.get("confidence", 0.5)), 0.75)
            repeatability = _as_float(record.get("repeatability", 0.5))
            mechanism_score = _clamp(
                result_overlap * 0.35
                + recommendation_overlap * 0.20
                + then_overlap * 0.15
                + if_overlap * 0.10
                + viability * 0.10
                + effective_confidence * 0.05
                + repeatability * 0.05
            )
            value_fields = self._value_adjustment(str(experience_id), target, target_related_patterns, mechanism_score)
            adjusted_score = value_fields["value_adjusted_score"]
            if mechanism_score < MIN_MECHANISM_SCORE and not (
                adjusted_score >= MIN_MECHANISM_SCORE and value_fields["value_bonus"] > 0.0
            ):
                continue
            matched_target_patterns = sorted(target_related_patterns & set(result_patterns + recommendation_patterns + then_patterns))
            matched_associated_patterns = sorted(associated_only & set(result_patterns + recommendation_patterns + then_patterns))
            mechanisms.append(
                {
                    "experience_id": str(experience_id),
                    "mechanism_purpose": self._purpose_for(target, result_overlap, recommendation_overlap, then_overlap, record),
                    "mechanism_score": round(mechanism_score, 3),
                    "base_mechanism_score": round(mechanism_score, 3),
                    **value_fields,
                    "result_overlap": round(result_overlap, 3),
                    "recommendation_overlap": round(recommendation_overlap, 3),
                    "then_overlap": round(then_overlap, 3),
                    "if_overlap": round(if_overlap, 3),
                    "viability": round(viability, 3),
                    "effective_confidence": round(effective_confidence, 3),
                    "repeatability": round(repeatability, 3),
                    "if_patterns": list(if_patterns),
                    "then_patterns": list(then_patterns),
                    "result_patterns": list(result_patterns),
                    "recommendation_patterns": list(recommendation_patterns),
                    "matched_target_patterns": matched_target_patterns,
                    "matched_associated_patterns": matched_associated_patterns,
                }
            )
        return sorted(mechanisms, key=lambda item: item["value_adjusted_score"], reverse=True)[:MAX_MECHANISMS_PER_TARGET]

    def _value_adjustment(
        self,
        experience_id: str,
        target: dict[str, Any],
        target_related_pattern_ids: set[str],
        base_score: float,
    ) -> dict[str, Any]:
        base_trace = {
            "has_value_feedback": False,
        }
        if self.value_feedback_memory_view is None:
            return _no_value_fields(base_score, base_trace)
        value_view = self.value_feedback_memory_view.get(experience_id)
        if value_view is None or _is_neutral_value_view(value_view):
            return _no_value_fields(base_score, base_trace)
        linked_overlap = _jaccard_list(value_view.linked_target_patterns, target_related_pattern_ids)
        target_relevance = 0.5 + linked_overlap * 0.5
        generic_bonus, generic_penalty = _generic_value_adjustment(value_view, target_relevance)
        target_kind = str(target.get("target_kind", ""))
        target_roles = [str(role) for role in target.get("target_role_names", ())]
        helpful_matches = [
            match
            for match in self.value_feedback_memory_view.find_helpful_for_target(
                target_related_pattern_ids,
                target_kind=target_kind,
                target_roles=target_roles,
                limit=10,
            )
            if match.experience_id == experience_id
        ]
        risky_matches = [
            match
            for match in self.value_feedback_memory_view.find_risky_for_target(
                target_related_pattern_ids,
                target_kind=target_kind,
                target_roles=target_roles,
                limit=10,
            )
            if match.experience_id == experience_id
        ]
        best_helpful_score = max((match.match_score for match in helpful_matches), default=0.0)
        best_risky_score = max((match.match_score for match in risky_matches), default=0.0)
        target_bonus = 0.0
        target_penalty = 0.0
        if best_helpful_score > 0.0:
            target_bonus = min(
                MAX_VALUE_BONUS,
                best_helpful_score * value_view.value_confidence * MAX_VALUE_BONUS * TARGET_SPECIFIC_BONUS_MULTIPLIER,
            )
        if best_risky_score > 0.0:
            target_penalty = min(
                MAX_VALUE_PENALTY,
                best_risky_score * max(value_view.value_confidence, value_view.value_risk) * MAX_VALUE_PENALTY * TARGET_SPECIFIC_PENALTY_MULTIPLIER,
            )
        value_bonus = max(generic_bonus, target_bonus)
        value_penalty = max(generic_penalty, target_penalty)
        if value_penalty >= 0.06:
            value_bonus *= 0.50
        if value_view.value_risk >= 0.6:
            value_bonus *= 0.35
        mode = "target_specific" if target_bonus > 0.0 or target_penalty > 0.0 else "generic_fallback"
        return {
            "value_bonus": round(value_bonus, 3),
            "value_penalty": round(value_penalty, 3),
            "value_adjusted_score": round(_clamp(base_score + value_bonus - value_penalty), 3),
            "value_balance": round(value_view.value_balance, 3),
            "value_confidence": round(value_view.value_confidence, 3),
            "value_risk": round(value_view.value_risk, 3),
            "value_target_relevance": round(target_relevance, 3),
            "value_trace": _value_trace(value_view, linked_overlap),
            "value_scoring_mode": mode,
            "target_specific_value_bonus": round(target_bonus, 3),
            "target_specific_value_penalty": round(target_penalty, 3),
            "generic_value_bonus": round(generic_bonus, 3),
            "generic_value_penalty": round(generic_penalty, 3),
            "target_helpful_match_score": round(best_helpful_score, 3),
            "target_risky_match_score": round(best_risky_score, 3),
            "target_value_trace": _target_value_trace(helpful_matches, risky_matches),
        }

    def _purpose_for(
        self,
        target: dict[str, Any],
        result_overlap: float,
        recommendation_overlap: float,
        then_overlap: float,
        record: dict[str, Any],
    ) -> str:
        target_kind = str(target.get("target_kind", ""))
        roles = {str(role) for role in target.get("target_role_names", ())}
        is_avoidance = target_kind == "avoidance_target" or bool(roles & {"avoidance_target", "harmful_target"})
        if is_avoidance:
            action_names = " ".join(self.pattern_registry.debug_name(pattern_id) for pattern_id in _pattern_tuple(record.get("then", ())) + _pattern_tuple(record.get("recommendation", ())))
            if any(token in action_names for token in ("preserve", "reduce", "block", "recover")):
                return "mitigate_harm"
            return "avoid_target"
        if result_overlap > 0.0:
            return "obtain_target"
        if recommendation_overlap > 0.0 or then_overlap > 0.0:
            return "preserve_target"
        return "unknown_potential"

    def _should_emit(self, tick: int, target: dict[str, Any], mechanisms: list[dict[str, Any]]) -> bool:
        target_id = str(target.get("target_observation_id", ""))
        if not target_id:
            return False
        experience_ids = tuple(str(mechanism["experience_id"]) for mechanism in mechanisms)
        target_score = _as_float(target.get("target_score", 0.0))
        previous = self._last_emissions.get(target_id)
        if previous is None:
            self._last_emissions[target_id] = (tick, target_score, experience_ids)
            return True
        previous_tick, previous_score, previous_ids = previous
        if experience_ids != previous_ids or abs(target_score - previous_score) >= SIGNIFICANT_TARGET_DELTA:
            self._last_emissions[target_id] = (tick, target_score, experience_ids)
            return True
        if tick - previous_tick >= MECHANISM_SEARCH_COOLDOWN_TICKS:
            self._last_emissions[target_id] = (tick, target_score, experience_ids)
            return True
        return False

    def _operation(
        self,
        tick: int,
        target: dict[str, Any],
        related_records: list[dict[str, Any]],
        mechanisms: list[dict[str, Any]],
    ) -> ContextOperation:
        activation = max([mechanism["value_adjusted_score"] for mechanism in mechanisms] + [0.60])
        target_pattern_id = str(target.get("pattern_id", ""))
        payload = {
            "mechanism_search_id": self.id_gen.next("expsm_mechanism_search"),
            "search_kind": self.search_kind,
            "source_target_observation_id": target.get("target_observation_id"),
            "target_pattern_id": target_pattern_id,
            "target_pattern_name": self.pattern_registry.debug_name(target_pattern_id),
            "target_kind": target.get("target_kind"),
            "target_role_names": list(target.get("target_role_names", ())),
            "target_score": target.get("target_score", 0.0),
            "target_related_patterns": related_records,
            "mechanisms_found": len(mechanisms),
            "mechanisms": mechanisms,
            "memory_modified": False,
            "permanent_memory_modified": False,
            "expsm_modified": False,
            "akbsm_modified": False,
            "activation": round(activation, 3),
            "ttl": 10,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.EXPSM_MECHANISM_SEARCH,
            tick,
            self.module_name,
            None,
            payload,
        )


def _pattern_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        value = (value,)
    patterns: list[str] = []
    for item in value:
        text = str(item)
        if not text or text == "NFP":
            continue
        patterns.append(Path(text).stem if text.endswith(".nfp") else text)
    return tuple(dict.fromkeys(patterns))


def _jaccard(values: tuple[str, ...], target: set[str]) -> float:
    source = set(values)
    if not source or not target:
        return 0.0
    return len(source & target) / len(source | target)


def _jaccard_list(values: list[str], target: set[str]) -> float:
    source = {str(value) for value in values if value}
    if not source or not target:
        return 0.0
    return len(source & target) / len(source | target)


def _value_trace(value_view: ValueFeedbackRecordView, linked_overlap: float) -> dict[str, Any]:
    return {
        "has_value_feedback": True,
        "positive_count": value_view.positive_count,
        "negative_count": value_view.negative_count,
        "positive_avg_strength": round(value_view.positive_avg_strength, 3),
        "negative_avg_strength": round(value_view.negative_avg_strength, 3),
        "linked_target_overlap": round(linked_overlap, 3),
        "linked_target_patterns": list(value_view.linked_target_patterns),
        "target_kinds": list(value_view.target_kinds),
        "target_roles": list(value_view.target_roles),
    }


def _no_value_fields(base_score: float, value_trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "value_bonus": 0.0,
        "value_penalty": 0.0,
        "value_adjusted_score": round(base_score, 3),
        "value_balance": 0.0,
        "value_confidence": 0.0,
        "value_risk": 0.0,
        "value_target_relevance": 0.5,
        "value_trace": value_trace,
        "value_scoring_mode": "no_value",
        "target_specific_value_bonus": 0.0,
        "target_specific_value_penalty": 0.0,
        "generic_value_bonus": 0.0,
        "generic_value_penalty": 0.0,
        "target_helpful_match_score": 0.0,
        "target_risky_match_score": 0.0,
        "target_value_trace": {
            "helpful_matches": [],
            "risky_matches": [],
        },
    }


def _generic_value_adjustment(value_view: ValueFeedbackRecordView, target_relevance: float) -> tuple[float, float]:
    value_bonus = 0.0
    value_penalty = 0.0
    if value_view.value_confidence < MIN_VALUE_CONFIDENCE:
        return value_bonus, value_penalty
    if value_view.value_balance > 0.0:
        value_bonus = min(
            MAX_VALUE_BONUS,
            value_view.value_balance * value_view.value_confidence * target_relevance * MAX_VALUE_BONUS,
        )
    if value_view.value_balance < 0.0 or value_view.value_risk > 0.0:
        negative_pressure = max(abs(min(value_view.value_balance, 0.0)), value_view.value_risk)
        value_penalty = min(
            MAX_VALUE_PENALTY,
            negative_pressure * value_view.value_confidence * target_relevance * MAX_VALUE_PENALTY,
        )
    if value_view.value_risk >= 0.6:
        value_bonus *= 0.35
    return value_bonus, value_penalty


def _target_value_trace(helpful_matches: list[Any], risky_matches: list[Any]) -> dict[str, Any]:
    return {
        "helpful_matches": [_match_trace(match) for match in helpful_matches[:5]],
        "risky_matches": [_match_trace(match) for match in risky_matches[:5]],
    }


def _match_trace(match: Any) -> dict[str, Any]:
    return {
        "experience_id": str(match.experience_id),
        "match_score": round(float(match.match_score), 3),
        "matched_target_patterns": list(match.matched_target_patterns),
        "matched_target_roles": list(match.matched_target_roles),
        "value_direction": match.value_direction,
    }


def _is_neutral_value_view(value_view: ValueFeedbackRecordView) -> bool:
    return (
        value_view.positive_count == 0
        and value_view.negative_count == 0
        and value_view.mixed_count == 0
        and value_view.inconclusive_count == 0
        and not value_view.linked_target_patterns
    )


def _viability(record: dict[str, Any]) -> float:
    hits = int(record.get("hits", 0) or 0)
    misses = int(record.get("misses", 0) or 0)
    return _clamp((hits + 1) / (hits + misses + 2))


def _is_archived(record: dict[str, Any]) -> bool:
    return str(record.get("status", "")).lower() in {"archived", "deleted", "tombstone"}


def _has_core(record: dict[str, Any]) -> bool:
    return bool(_pattern_tuple(record.get("if", ())) and (_pattern_tuple(record.get("then", ())) or _pattern_tuple(record.get("result", ()))))


def _as_float(value: Any) -> float:
    try:
        return _clamp(float(value))
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
