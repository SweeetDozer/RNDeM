from dataclasses import dataclass
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.evaluation_field import EvaluationEntry, EvaluationField
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


TARGET_SATISFACTION_COOLDOWN_TICKS = 4
REQUIRED_SOURCE_FIELDS = (
    "source_experience_id",
    "source_mechanism_search_id",
    "source_target_observation_id",
    "source_target_pattern_id",
    "source_target_kind",
    "source_target_roles",
    "source_mechanism_purpose",
    "source_mechanism_score",
)


@dataclass(frozen=True)
class _EmissionMemory:
    tick: int
    status: str
    evidence_ids: tuple[str, ...]


class TargetSatisfactionObserver:
    """Observes whether a mechanism-source decision helped its original target."""

    module_name = "target_satisfaction_observer"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.observer_kind = pattern_registry.id("target_satisfaction_observer")
        self.observed_kind = pattern_registry.id("target_satisfaction_observed")
        self.status_patterns = {
            "satisfied": pattern_registry.id("target_satisfied"),
            "partially_satisfied": pattern_registry.id("target_partially_satisfied"),
            "not_satisfied": pattern_registry.id("target_not_satisfied"),
            "worsened": pattern_registry.id("target_worsened"),
            "inconclusive": pattern_registry.id("target_satisfaction_inconclusive"),
        }
        self.positive_evidence = pattern_registry.id("target_satisfaction_positive_evidence")
        self.negative_evidence = pattern_registry.id("target_satisfaction_negative_evidence")
        self._emitted: dict[str, _EmissionMemory] = {}

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        evaluation_field: EvaluationField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        if system_state.mode not in {"active", "recovery", "consolidation"}:
            return []
        operations: list[ContextOperation] = []
        for decision in memory.get_recent_decisions(12):
            if decision.get("source") != "expsm_mechanism_search":
                continue
            if any(not decision.get(field) for field in REQUIRED_SOURCE_FIELDS):
                continue
            if tick <= int(decision.get("_event_tick", tick)):
                continue
            observation = self._observe(tick, decision, memory, active_field, evaluation_field)
            if observation is None:
                continue
            key = (
                f"{decision.get('decision_id')}|"
                f"{decision.get('source_target_observation_id')}|"
                f"{decision.get('source_mechanism_search_id')}"
            )
            evidence_ids = _evidence_ids(observation["evidence"])
            if not self._should_emit(tick, key, observation["satisfaction_status"], evidence_ids):
                continue
            self._emitted[key] = _EmissionMemory(tick, observation["satisfaction_status"], evidence_ids)
            operations.append(
                ContextOperation(
                    self.id_gen.next("op"),
                    OperationMarker.TARGET_SATISFACTION_OBSERVED,
                    tick,
                    self.module_name,
                    None,
                    observation,
                )
            )
        if len(self._emitted) > 256:
            self._emitted = dict(list(self._emitted.items())[-128:])
        return operations

    def _observe(
        self,
        tick: int,
        decision: dict[str, Any],
        memory: ContextMemory,
        active_field: ActiveContextField,
        evaluation_field: EvaluationField,
    ) -> dict[str, Any] | None:
        decision_id = str(decision.get("decision_id", ""))
        target_pattern_id = str(decision.get("source_target_pattern_id", ""))
        target_kind = str(decision.get("source_target_kind", ""))
        role_names = tuple(str(role) for role in decision.get("source_target_roles", ()))
        if not decision_id or not target_pattern_id:
            return None

        effects = _linked_effects(decision_id, decision, memory)
        outcomes = _linked_outcomes(decision_id, effects, decision, memory)
        signals = _linked_evaluation_signals(target_pattern_id, decision, outcomes, memory)
        evaluation_entry = evaluation_field.get(target_pattern_id)

        direct_mentions = _direct_target_mentions(target_pattern_id, effects, outcomes, signals)
        positive_dimensions, negative_dimensions = _dimensions(evaluation_entry, signals)
        score, evidence_strength = _score_observation(
            target_pattern_id,
            target_kind,
            role_names,
            effects,
            outcomes,
            direct_mentions,
            positive_dimensions,
            negative_dimensions,
            active_field,
        )
        status = _status(score, evidence_strength)
        if evidence_strength <= 0.0:
            return None
        activation = _clamp(max(0.35, abs(score) * 0.65 + evidence_strength * 0.35))
        evidence = {
            "outcome_event_ids": [str(outcome.get("outcome_id")) for outcome in outcomes if outcome.get("outcome_id")],
            "effect_event_ids": [str(effect.get("effect_id")) for effect in effects if effect.get("effect_id")],
            "evaluation_signal_ids": [str(signal.get("evaluation_id")) for signal in signals if signal.get("evaluation_id")],
            "direct_target_mentions": list(direct_mentions),
            "positive_dimensions": positive_dimensions,
            "negative_dimensions": negative_dimensions,
        }
        return {
            "target_satisfaction_id": self.id_gen.next("target_satisfaction"),
            "observer_kind": self.observer_kind,
            "observation_kind": self.observed_kind,
            "status_pattern_id": self.status_patterns[status],
            "positive_evidence_pattern_id": self.positive_evidence if positive_dimensions else None,
            "negative_evidence_pattern_id": self.negative_evidence if negative_dimensions else None,
            "source_decision_id": decision_id,
            "source_experience_id": str(decision.get("source_experience_id", "")),
            "source_mechanism_search_id": str(decision.get("source_mechanism_search_id", "")),
            "source_target_observation_id": str(decision.get("source_target_observation_id", "")),
            "target_pattern_id": target_pattern_id,
            "target_pattern_name": self.pattern_registry.debug_name(target_pattern_id),
            "target_kind": target_kind,
            "target_role_names": list(role_names),
            "mechanism_purpose": str(decision.get("source_mechanism_purpose", "")),
            "mechanism_score": round(_safe_float(decision.get("source_mechanism_score")), 3),
            "satisfaction_status": status,
            "satisfaction_score": round(score, 3),
            "evidence_strength": round(evidence_strength, 3),
            "evidence": evidence,
            "memory_modified": False,
            "permanent_memory_modified": False,
            "expsm_modified": False,
            "akbsm_modified": False,
            "activation": round(activation, 3),
            "ttl": 10,
        }

    def _should_emit(self, tick: int, key: str, status: str, evidence_ids: tuple[str, ...]) -> bool:
        previous = self._emitted.get(key)
        if previous is None:
            return True
        if status != previous.status:
            return True
        if evidence_ids != previous.evidence_ids:
            return True
        return tick - previous.tick >= TARGET_SATISFACTION_COOLDOWN_TICKS


def _linked_effects(decision_id: str, decision: dict[str, Any], memory: ContextMemory) -> list[dict[str, Any]]:
    decision_tick = int(decision.get("_event_tick", 0) or 0)
    return [
        effect
        for effect in memory.get_recent_effects(16)
        if effect.get("source_decision_id") == decision_id and int(effect.get("_event_tick", 0) or 0) >= decision_tick
    ]


def _linked_outcomes(
    decision_id: str,
    effects: list[dict[str, Any]],
    decision: dict[str, Any],
    memory: ContextMemory,
) -> list[dict[str, Any]]:
    decision_tick = int(decision.get("_event_tick", 0) or 0)
    effect_ids = {str(effect.get("effect_id")) for effect in effects if effect.get("effect_id")}
    outcomes: list[dict[str, Any]] = []
    for outcome in memory.get_recent_outcomes(20):
        if int(outcome.get("_event_tick", 0) or 0) < decision_tick:
            continue
        if outcome.get("source_decision_id") == decision_id:
            outcomes.append(outcome)
            continue
        if str(outcome.get("source_event_id")) in effect_ids:
            outcomes.append(outcome)
            continue
        if int(outcome.get("_event_tick", 0) or 0) - decision_tick <= 3 and outcome.get("source_kind") in {"decision", "effect"}:
            outcomes.append(outcome)
    return _unique_dicts(outcomes, "outcome_id")


def _linked_evaluation_signals(
    target_pattern_id: str,
    decision: dict[str, Any],
    outcomes: list[dict[str, Any]],
    memory: ContextMemory,
) -> list[dict[str, Any]]:
    decision_tick = int(decision.get("_event_tick", 0) or 0)
    outcome_ids = {str(outcome.get("outcome_id")) for outcome in outcomes if outcome.get("outcome_id")}
    signals: list[dict[str, Any]] = []
    for signal in memory.get_recent_evaluation_signals(24):
        signal_tick = int(signal.get("_event_tick", 0) or 0)
        if signal_tick < decision_tick:
            continue
        target_patterns = {str(pattern_id) for pattern_id in signal.get("target_patterns", ())}
        if target_pattern_id in target_patterns:
            signals.append(signal)
            continue
        if str(signal.get("source_event_id")) in outcome_ids:
            signals.append(signal)
    return _unique_dicts(signals, "evaluation_id")


def _direct_target_mentions(
    target_pattern_id: str,
    effects: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> tuple[str, ...]:
    mentions: list[str] = []
    for effect in effects:
        if effect.get("effect_pattern_id") == target_pattern_id:
            mentions.append(target_pattern_id)
        if target_pattern_id in set(effect.get("secondary_effect_patterns", ())):
            mentions.append(target_pattern_id)
    for outcome in outcomes:
        if outcome.get("outcome_pattern_id") == target_pattern_id:
            mentions.append(target_pattern_id)
        if target_pattern_id in set(outcome.get("matched_patterns", ())):
            mentions.append(target_pattern_id)
    for signal in signals:
        if target_pattern_id in set(signal.get("target_patterns", ())):
            mentions.append(target_pattern_id)
    return tuple(dict.fromkeys(mentions))


def _dimensions(
    evaluation_entry: EvaluationEntry | None,
    signals: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, float]]:
    positive = {"usefulness": 0.0, "need": 0.0, "want": 0.0, "safety": 0.0, "priority": 0.0}
    negative = {"harmfulness": 0.0, "avoid": 0.0}
    if evaluation_entry is not None:
        for key in positive:
            positive[key] = max(positive[key], _safe_float(getattr(evaluation_entry, key)))
        for key in negative:
            negative[key] = max(negative[key], _safe_float(getattr(evaluation_entry, key)))
    for signal in signals:
        dims = signal.get("evaluation_dimensions", {})
        if not isinstance(dims, dict):
            continue
        for key in positive:
            positive[key] = max(positive[key], _safe_float(dims.get(key)))
        for key in negative:
            negative[key] = max(negative[key], _safe_float(dims.get(key)))
    return (
        {key: round(value, 3) for key, value in positive.items() if value > 0.0},
        {key: round(value, 3) for key, value in negative.items() if value > 0.0},
    )


def _score_observation(
    target_pattern_id: str,
    target_kind: str,
    role_names: tuple[str, ...],
    effects: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    direct_mentions: tuple[str, ...],
    positive_dimensions: dict[str, float],
    negative_dimensions: dict[str, float],
    active_field: ActiveContextField,
) -> tuple[float, float]:
    positive_signal = (
        positive_dimensions.get("usefulness", 0.0) * 0.30
        + positive_dimensions.get("need", 0.0) * 0.20
        + positive_dimensions.get("want", 0.0) * 0.15
        + positive_dimensions.get("safety", 0.0) * 0.25
        + positive_dimensions.get("priority", 0.0) * 0.10
    )
    negative_signal = (
        negative_dimensions.get("harmfulness", 0.0) * 0.45
        + negative_dimensions.get("avoid", 0.0) * 0.35
    )
    score = 0.0
    evidence_strength = 0.0
    if direct_mentions:
        score += 0.45
        evidence_strength += 0.35
    if positive_signal > 0.0:
        score += min(0.45, positive_signal)
        evidence_strength += min(0.35, positive_signal)
    if negative_signal > 0.0:
        score -= min(0.45, negative_signal)
        evidence_strength += min(0.35, negative_signal)
    for outcome in outcomes:
        status = outcome.get("outcome_status")
        if status == "confirmed":
            score += 0.20
            evidence_strength += 0.15
        elif status == "partially_confirmed":
            score += 0.10
            evidence_strength += 0.10
        elif status == "failed":
            score -= 0.25
            evidence_strength += 0.15
    if target_kind in {"avoidance_target", "harmful_target"} or set(role_names) & {"avoidance_target", "harmful_target"}:
        score = -negative_signal + positive_signal + (0.25 if any(o.get("outcome_status") == "confirmed" for o in outcomes) else 0.0)
    active_targets = {pattern.pattern_id: pattern.activation for pattern in active_field.get_patterns_above(0.25)}
    if active_targets.get(target_pattern_id, 0.0) >= 0.35:
        score += 0.08
        evidence_strength += 0.08
    if effects:
        evidence_strength += 0.08
    return _clamp_signed(score), _clamp(evidence_strength)


def _status(satisfaction_score: float, evidence_strength: float) -> str:
    if evidence_strength < 0.20:
        return "inconclusive"
    if satisfaction_score >= 0.55:
        return "satisfied"
    if satisfaction_score >= 0.20:
        return "partially_satisfied"
    if satisfaction_score <= -0.35:
        return "worsened"
    return "not_satisfied"


def _evidence_ids(evidence: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("outcome_event_ids", "effect_event_ids", "evaluation_signal_ids"):
        values.extend(str(item) for item in evidence.get(key, ()) if item)
    return tuple(dict.fromkeys(values))


def _unique_dicts(values: list[dict[str, Any]], id_key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        key = str(value.get(id_key, ""))
        fallback = str(id(value))
        unique_key = key or fallback
        if unique_key in seen:
            continue
        seen.add(unique_key)
        result.append(value)
    return result


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))
