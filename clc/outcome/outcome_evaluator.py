from dataclasses import dataclass
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.field.active_pattern import ActivePattern
from clc.neuromodulation.tone_state import ToneState


@dataclass(frozen=True)
class OutcomeJudgement:
    status: str
    confidence: float
    matched_patterns: list[str]
    missing_patterns: list[str]
    tone_delta: dict[str, float]


class OutcomeEvaluator:
    """Checks old predictions/decisions/effects against later context."""

    module_name = "outcome_evaluator"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        evaluation_delay_ticks: int = 2,
    ) -> None:
        self.id_gen = id_gen
        self.evaluation_delay_ticks = evaluation_delay_ticks
        self.active_threshold = 0.35
        self.confirmed_ratio = 0.6
        self.partial_ratio = 0.25
        self._evaluated_source_event_ids: set[str] = set()
        self.outcome_patterns = {
            "confirmed": pattern_registry.id("outcome_confirmed"),
            "partially_confirmed": pattern_registry.id("outcome_partially_confirmed"),
            "failed": pattern_registry.id("outcome_failed"),
            "expired": pattern_registry.id("outcome_expired"),
            "inconclusive": pattern_registry.id("outcome_inconclusive"),
        }
        self.decision_effects = {
            pattern_registry.id("action_wait_more_data"): pattern_registry.id("state_waiting_for_more_data"),
            pattern_registry.id("action_increase_attention"): pattern_registry.id("state_attention_increased"),
            pattern_registry.id("action_inspect_pattern"): pattern_registry.id("state_pattern_inspection"),
            pattern_registry.id("action_store_memory_candidate"): pattern_registry.id("state_memory_candidate_created"),
            pattern_registry.id("action_reduce_load"): pattern_registry.id("state_load_reduced"),
            pattern_registry.id("action_preserve_integrity"): pattern_registry.id("state_integrity_preservation"),
            pattern_registry.id("action_continue_observation"): pattern_registry.id("state_observation_continues"),
            pattern_registry.id("action_generate_more_thought"): pattern_registry.id("state_more_thought_requested"),
            pattern_registry.id("action_enter_consolidation_mode"): pattern_registry.id("state_consolidation_mode_entered"),
            pattern_registry.id("action_exit_consolidation_mode"): pattern_registry.id("state_consolidation_mode_exited"),
        }

    def run(self, tick: int, memory: ContextMemory, active_field: ActiveContextField) -> list[ContextOperation]:
        operations: list[ContextOperation] = []
        for event in memory.events:
            if event.marker not in {
                OperationMarker.PREDICTION,
                OperationMarker.INTERNAL_DECISION,
                OperationMarker.INTERNAL_ACTION_EFFECT,
            }:
                continue
            if event.op_id in self._evaluated_source_event_ids:
                continue
            if tick - event.tick < self.evaluation_delay_ticks:
                continue
            judgement = self._evaluate_event(tick, event.op_id, event.marker, event.tick, dict(event.payload), memory, active_field)
            self._evaluated_source_event_ids.add(event.op_id)
            operations.append(self._operation(tick, event.op_id, event.marker, judgement))
        return operations

    def _evaluate_event(
        self,
        tick: int,
        source_event_id: str,
        marker: OperationMarker,
        source_tick: int,
        payload: dict[str, Any],
        memory: ContextMemory,
        active_field: ActiveContextField,
    ) -> OutcomeJudgement:
        if marker == OperationMarker.PREDICTION:
            return self._evaluate_prediction(tick, source_event_id, source_tick, payload, memory, active_field)
        if marker == OperationMarker.INTERNAL_DECISION:
            return self._evaluate_decision(source_tick, payload, memory, active_field)
        if marker == OperationMarker.INTERNAL_ACTION_EFFECT:
            return self._evaluate_effect(source_tick, payload, memory, active_field)
        return self._judgement("inconclusive", 0.1, [], [], "inconclusive")

    def _evaluate_prediction(
        self,
        tick: int,
        source_event_id: str,
        source_tick: int,
        payload: dict[str, Any],
        memory: ContextMemory,
        active_field: ActiveContextField,
    ) -> OutcomeJudgement:
        predicted_patterns = list(payload.get("predicted_patterns", ()))
        active_patterns = {pattern.pattern_id: pattern for pattern in active_field.get_patterns_above(self.active_threshold)}
        matched = [
            pattern_id
            for pattern_id in predicted_patterns
            if self._is_confirming_active_pattern(active_patterns.get(pattern_id), source_event_id, source_tick, memory)
        ]
        missing = [pattern_id for pattern_id in predicted_patterns if pattern_id not in matched]
        ratio = len(matched) / len(predicted_patterns) if predicted_patterns else 0.0
        tone_support = self._tone_support(source_tick, payload.get("expected_tone_delta", {}), memory)
        if predicted_patterns:
            if ratio >= self.confirmed_ratio:
                return self._judgement("confirmed", max(0.65, ratio), matched, missing, "confirmed")
            if ratio >= self.partial_ratio or tone_support >= 0.5:
                return self._judgement("partially_confirmed", max(0.35, ratio, tone_support * 0.6), matched, missing, "partially_confirmed")
            ttl = payload.get("ttl")
            if ttl is not None and tick >= source_tick + int(ttl):
                return self._judgement("failed", 0.65, matched, missing, "failed")
            return self._judgement("inconclusive", 0.25, matched, missing, "inconclusive")
        if payload.get("expected_tone_delta"):
            if tone_support >= 0.6:
                return self._judgement("partially_confirmed", tone_support, [], [], "partially_confirmed")
            return self._judgement("inconclusive", 0.2, [], [], "inconclusive")
        return self._judgement("inconclusive", 0.1, [], [], "inconclusive")

    def _evaluate_decision(
        self,
        source_tick: int,
        payload: dict[str, Any],
        memory: ContextMemory,
        active_field: ActiveContextField,
    ) -> OutcomeJudgement:
        action_pattern_id = payload.get("decision_pattern_id")
        expected_effect = self.decision_effects.get(action_pattern_id)
        if expected_effect is None:
            return self._judgement("inconclusive", 0.1, [], [], "inconclusive")
        source_decision_id = payload.get("decision_id")
        later_effects = [
            effect
            for effect in memory.effects
            if effect.get("_event_tick", 0) >= source_tick and effect.get("source_decision_id") == source_decision_id
        ]
        matched = [effect.get("effect_pattern_id") for effect in later_effects if effect.get("effect_pattern_id") == expected_effect]
        if matched:
            return self._judgement("confirmed", 0.85, [expected_effect], [], "confirmed")
        active = {pattern.pattern_id: pattern.activation for pattern in active_field.get_patterns_above(0.2)}
        if active.get(expected_effect, 0.0) >= self.active_threshold:
            return self._judgement("partially_confirmed", 0.5, [expected_effect], [], "partially_confirmed")
        return self._judgement("failed", 0.65, [], [expected_effect], "failed")

    def _evaluate_effect(
        self,
        source_tick: int,
        payload: dict[str, Any],
        memory: ContextMemory,
        active_field: ActiveContextField,
    ) -> OutcomeJudgement:
        matched: list[str] = []
        missing: list[str] = []
        checks = 0
        confirmations = 0.0
        effect_pattern_id = payload.get("effect_pattern_id")
        if effect_pattern_id:
            checks += 1
            active = {pattern.pattern_id: pattern.activation for pattern in active_field.get_patterns_above(0.2)}
            if active.get(effect_pattern_id, 0.0) >= 0.25:
                confirmations += 1.0
                matched.append(effect_pattern_id)
            else:
                missing.append(effect_pattern_id)
        for thought_pattern_id in payload.get("generate_thought_patterns", ()):
            checks += 1
            if self._thought_pattern_appeared(thought_pattern_id, source_tick, memory, active_field):
                confirmations += 1.0
                matched.append(thought_pattern_id)
            else:
                missing.append(thought_pattern_id)
        if payload.get("memory_candidate"):
            checks += 1
            confirmations += 1.0
        tone_delta = payload.get("tone_delta", {})
        if tone_delta:
            checks += 1
            confirmations += self._tone_support(source_tick, tone_delta, memory)
        if checks == 0:
            return self._judgement("inconclusive", 0.1, matched, missing, "inconclusive")
        ratio = confirmations / checks
        if ratio >= self.confirmed_ratio:
            return self._judgement("confirmed", max(0.6, ratio), matched, missing, "confirmed")
        if ratio >= self.partial_ratio:
            return self._judgement("partially_confirmed", max(0.35, ratio), matched, missing, "partially_confirmed")
        return self._judgement("failed", 0.6, matched, missing, "failed")

    def _operation(
        self,
        tick: int,
        source_event_id: str,
        source_marker: OperationMarker,
        judgement: OutcomeJudgement,
    ) -> ContextOperation:
        payload = {
            "outcome_id": self.id_gen.next("outcome"),
            "source_event_id": source_event_id,
            "source_marker": source_marker.value,
            "source_kind": _source_kind(source_marker),
            "outcome_status": judgement.status,
            "outcome_pattern_id": self.outcome_patterns[judgement.status],
            "confidence": round(judgement.confidence, 3),
            "matched_patterns": judgement.matched_patterns,
            "missing_patterns": judgement.missing_patterns,
            "tone_delta": {key: round(value, 3) for key, value in judgement.tone_delta.items()},
            "activation": round(judgement.confidence, 3),
            "ttl": 5,
        }
        return ContextOperation(self.id_gen.next("op"), OperationMarker.OUTCOME_EVALUATION, tick, self.module_name, None, payload)

    def _judgement(
        self,
        status: str,
        confidence: float,
        matched: list[str],
        missing: list[str],
        tone_delta_kind: str,
    ) -> OutcomeJudgement:
        tone_delta_by_status = {
            "confirmed": {"satisfaction": 0.04, "stability": 0.02, "pain": -0.02},
            "partially_confirmed": {"satisfaction": 0.015, "stability": 0.005},
            "failed": {"pain": 0.05, "stability": -0.03, "tension": 0.02},
            "expired": {"pain": 0.03, "stability": -0.02},
            "inconclusive": {"tension": 0.005},
        }
        return OutcomeJudgement(
            status=status,
            confidence=max(0.0, min(1.0, confidence)),
            matched_patterns=matched,
            missing_patterns=missing,
            tone_delta=tone_delta_by_status[tone_delta_kind],
        )

    def _is_confirming_active_pattern(
        self,
        pattern: ActivePattern | None,
        source_event_id: str,
        source_tick: int,
        memory: ContextMemory,
    ) -> bool:
        if pattern is None:
            return False
        events_by_id = {event.op_id: event for event in memory.events}
        confirming_markers = {
            OperationMarker.RAW_INPUT_WRITE,
            OperationMarker.SELF_GENERATED_THOUGHT,
            OperationMarker.LABEL,
            OperationMarker.INTERNAL_ACTION_EFFECT,
        }
        for event_id in pattern.source_event_ids:
            if event_id == source_event_id:
                continue
            event = events_by_id.get(event_id)
            if event is None:
                continue
            if event.tick > source_tick and event.marker in confirming_markers:
                return True
        return False

    def _thought_pattern_appeared(
        self,
        thought_pattern_id: str,
        source_tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
    ) -> bool:
        for frame in memory.thought_frames:
            if frame.tick >= source_tick and thought_pattern_id in frame.activations:
                return True
        return any(pattern.pattern_id == thought_pattern_id for pattern in active_field.get_patterns_above(0.25))

    def _tone_support(self, source_tick: int, expected_delta: dict[str, float], memory: ContextMemory) -> float:
        if not expected_delta:
            return 0.0
        baseline = self._tone_before(memory, source_tick)
        current = memory.get_current_tone()
        supported = 0
        total = 0
        for key, expected in expected_delta.items():
            if not hasattr(current, key) or not hasattr(baseline, key):
                continue
            total += 1
            observed = float(getattr(current, key)) - float(getattr(baseline, key))
            if expected > 0 and observed > 0.0:
                supported += 1
            elif expected < 0 and observed < 0.0:
                supported += 1
            elif expected == 0:
                supported += 1
        return supported / total if total else 0.0

    def _tone_before(self, memory: ContextMemory, tick: int) -> ToneState:
        tone = ToneState()
        for update in memory.neuromodulation_updates:
            update_tick = update.get("_event_tick", 0)
            if update_tick >= tick:
                continue
            candidate = update.get("tone_state")
            if isinstance(candidate, ToneState):
                tone = candidate
        return tone


def _source_kind(marker: OperationMarker) -> str:
    if marker == OperationMarker.PREDICTION:
        return "prediction"
    if marker == OperationMarker.INTERNAL_DECISION:
        return "decision"
    if marker == OperationMarker.INTERNAL_ACTION_EFFECT:
        return "effect"
    return "unknown"
