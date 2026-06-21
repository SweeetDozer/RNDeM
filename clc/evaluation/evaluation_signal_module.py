from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.neuromodulation.tone_state import ToneState
from clc.system.system_state import SystemState


MAX_EVALUATIONS_PER_TICK = 5
DIMENSION_KEYS = ("usefulness", "harmfulness", "need", "want", "avoid", "safety", "priority")


class EvaluationSignalModule:
    """Emits first-pass value/need/want signals without controlling action choice."""

    module_name = "evaluation_signal_module"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.evaluation_kind = pattern_registry.id("evaluation_signal")
        self.evaluation_patterns = {
            "useful": pattern_registry.id("evaluation_useful"),
            "useless": pattern_registry.id("evaluation_useless"),
            "harmful": pattern_registry.id("evaluation_harmful"),
            "safe": pattern_registry.id("evaluation_safe"),
            "needed": pattern_registry.id("evaluation_needed"),
            "wanted": pattern_registry.id("evaluation_wanted"),
            "unwanted": pattern_registry.id("evaluation_unwanted"),
            "avoid": pattern_registry.id("evaluation_avoid"),
            "priority_high": pattern_registry.id("evaluation_priority_high"),
            "priority_medium": pattern_registry.id("evaluation_priority_medium"),
            "priority_low": pattern_registry.id("evaluation_priority_low"),
        }
        self.positive_patterns = {
            pattern_registry.id("state_integrity_preserved"),
            pattern_registry.id("state_integrity_preservation"),
            pattern_registry.id("state_memory_updated"),
            pattern_registry.id("memory_update_success"),
            pattern_registry.id("expsm_feedback_success"),
            pattern_registry.id("state_load_reduced"),
            pattern_registry.id("state_recovery_progress"),
            pattern_registry.id("outcome_confirmed"),
            pattern_registry.id("outcome_partially_confirmed"),
        }
        self.harm_patterns = {
            pattern_registry.id("state_integrity_risk"),
            pattern_registry.id("state_action_blocked"),
            pattern_registry.id("expsm_feedback_failure"),
            pattern_registry.id("memory_update_failed"),
            pattern_registry.id("prediction_failed"),
            pattern_registry.id("outcome_failed"),
            pattern_registry.id("high_tension"),
            pattern_registry.id("high_pain"),
            pattern_registry.id("high_fatigue"),
            pattern_registry.id("tone_tension_high"),
            pattern_registry.id("tone_pain_high"),
            pattern_registry.id("tone_fatigue_high"),
        }
        self.low_value_patterns = {
            pattern_registry.id("state_no_change"),
            pattern_registry.id("outcome_inconclusive"),
        }
        self.tone_targets = {
            "tension": pattern_registry.id("high_tension"),
            "pain": pattern_registry.id("high_pain"),
            "fatigue": pattern_registry.id("high_fatigue"),
            "risk_sensitivity": pattern_registry.id("tone_risk_sensitivity_high"),
            "stability": pattern_registry.id("state_stability_high"),
            "satisfaction": pattern_registry.id("state_satisfaction_high"),
        }
        self._emitted_keys: set[tuple[object, ...]] = set()

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        if system_state.mode not in {"active", "recovery"}:
            return []
        operations: list[ContextOperation] = []
        for operation in self._event_evaluations(tick, memory):
            operations.append(operation)
            if len(operations) >= MAX_EVALUATIONS_PER_TICK:
                return operations
        for operation in self._tone_evaluations(tick, memory.get_current_tone()):
            operations.append(operation)
            if len(operations) >= MAX_EVALUATIONS_PER_TICK:
                return operations
        for operation in self._active_pattern_evaluations(tick, active_field):
            operations.append(operation)
            if len(operations) >= MAX_EVALUATIONS_PER_TICK:
                return operations
        return operations

    def _event_evaluations(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        operations: list[ContextOperation] = []
        for event in memory.events:
            if event.tick != tick:
                continue
            if event.marker == OperationMarker.INTERNAL_ACTION_EFFECT:
                operation = self._evaluate_effect(tick, event.op_id, dict(event.payload))
            elif event.marker == OperationMarker.OUTCOME_EVALUATION:
                operation = self._evaluate_outcome(tick, event.op_id, dict(event.payload))
            elif event.marker == OperationMarker.EXPSM_FEEDBACK:
                operation = self._evaluate_expsm_feedback(tick, event.op_id, dict(event.payload))
            else:
                continue
            if operation is not None:
                operations.append(operation)
        return operations

    def _evaluate_effect(self, tick: int, source_event_id: str, payload: dict[str, Any]) -> ContextOperation | None:
        targets = _unique([payload.get("effect_pattern_id"), *payload.get("secondary_effect_patterns", ())])
        return self._operation_for_targets(tick, source_event_id, OperationMarker.INTERNAL_ACTION_EFFECT, "effect", targets)

    def _evaluate_outcome(self, tick: int, source_event_id: str, payload: dict[str, Any]) -> ContextOperation | None:
        targets = _unique([payload.get("outcome_pattern_id"), *payload.get("matched_patterns", ()), *payload.get("missing_patterns", ())])
        status = payload.get("outcome_status")
        if status == "failed":
            return self._operation(tick, source_event_id, OperationMarker.OUTCOME_EVALUATION, "outcome", targets, _harm_dimensions())
        if status == "inconclusive":
            return self._operation(tick, source_event_id, OperationMarker.OUTCOME_EVALUATION, "outcome", targets, _low_value_dimensions())
        return self._operation_for_targets(tick, source_event_id, OperationMarker.OUTCOME_EVALUATION, "outcome", targets)

    def _evaluate_expsm_feedback(self, tick: int, source_event_id: str, payload: dict[str, Any]) -> ContextOperation | None:
        targets = _unique([
            payload.get("feedback_kind"),
            payload.get("selected_action"),
            *payload.get("matched_expected_patterns", ()),
        ])
        status = payload.get("feedback_status")
        if status == "hit":
            return self._operation(tick, source_event_id, OperationMarker.EXPSM_FEEDBACK, "expsm_feedback", targets, _positive_dimensions())
        if status == "miss":
            return self._operation(tick, source_event_id, OperationMarker.EXPSM_FEEDBACK, "expsm_feedback", targets, _harm_dimensions())
        return self._operation(tick, source_event_id, OperationMarker.EXPSM_FEEDBACK, "expsm_feedback", targets, _low_value_dimensions())

    def _tone_evaluations(self, tick: int, tone: ToneState) -> list[ContextOperation]:
        operations: list[ContextOperation] = []
        high_targets: list[str] = []
        if tone.tension >= 0.65:
            high_targets.append(self.tone_targets["tension"])
        if tone.pain >= 0.45:
            high_targets.append(self.tone_targets["pain"])
        if tone.fatigue >= 0.65:
            high_targets.append(self.tone_targets["fatigue"])
        if tone.risk_sensitivity >= 0.7:
            high_targets.append(self.tone_targets["risk_sensitivity"])
        if high_targets:
            operations.append(self._operation(tick, None, None, "internal_state", _unique(high_targets), _tone_harm_dimensions()))
        positive_targets: list[str] = []
        if tone.stability >= 0.82:
            positive_targets.append(self.tone_targets["stability"])
        if tone.satisfaction >= 0.55:
            positive_targets.append(self.tone_targets["satisfaction"])
        if positive_targets:
            operations.append(self._operation(tick, None, None, "internal_state", _unique(positive_targets), _tone_positive_dimensions()))
        return [operation for operation in operations if operation is not None]

    def _active_pattern_evaluations(self, tick: int, active_field: ActiveContextField) -> list[ContextOperation]:
        operations: list[ContextOperation] = []
        for active_pattern in active_field.get_top_patterns(limit=12):
            pattern_id = active_pattern.pattern_id
            if pattern_id not in self.positive_patterns and pattern_id not in self.harm_patterns and pattern_id not in self.low_value_patterns:
                continue
            operation = self._operation_for_targets(tick, None, None, "active_pattern", [pattern_id])
            if operation is not None:
                operations.append(operation)
            if len(operations) >= 2:
                break
        return operations

    def _operation_for_targets(
        self,
        tick: int,
        source_event_id: str | None,
        source_marker: OperationMarker | None,
        scope: str,
        target_patterns: list[str],
    ) -> ContextOperation | None:
        targets = set(target_patterns)
        if targets & self.harm_patterns:
            return self._operation(tick, source_event_id, source_marker, scope, target_patterns, _harm_dimensions())
        if targets & self.low_value_patterns:
            return self._operation(tick, source_event_id, source_marker, scope, target_patterns, _low_value_dimensions())
        if targets & self.positive_patterns:
            return self._operation(tick, source_event_id, source_marker, scope, target_patterns, _positive_dimensions())
        return None

    def _operation(
        self,
        tick: int,
        source_event_id: str | None,
        source_marker: OperationMarker | None,
        scope: str,
        target_patterns: list[str],
        dimensions: dict[str, float],
    ) -> ContextOperation | None:
        target_patterns = _unique(target_patterns)
        if not target_patterns:
            return None
        key = (
            source_event_id if source_event_id is not None else tick,
            scope,
            tuple(target_patterns),
        )
        if key in self._emitted_keys:
            return None
        self._emitted_keys.add(key)
        dimensions = _normalized_dimensions(dimensions)
        activation = max(dimensions["usefulness"], dimensions["harmfulness"], dimensions["need"], dimensions["safety"], dimensions["priority"], 0.35)
        payload = {
            "evaluation_id": self.id_gen.next("evaluation_signal"),
            "evaluation_kind": self.evaluation_kind,
            "source_event_id": source_event_id,
            "source_marker": source_marker.value if source_marker is not None else None,
            "source_kind": _source_kind(source_marker),
            "target_patterns": target_patterns,
            "evaluation_dimensions": dimensions,
            "evaluation_patterns": self._patterns_for_dimensions(dimensions),
            "evaluation_scope": scope,
            "memory_modified": False,
            "permanent_memory_modified": False,
            "activation": round(activation, 3),
            "ttl": 10,
        }
        return ContextOperation(self.id_gen.next("op"), OperationMarker.EVALUATION_SIGNAL, tick, self.module_name, None, payload)

    def _patterns_for_dimensions(self, dimensions: dict[str, float]) -> list[str]:
        patterns: list[str] = [self.evaluation_kind]
        if dimensions["usefulness"] >= 0.5:
            patterns.append(self.evaluation_patterns["useful"])
        if dimensions["usefulness"] <= 0.15 and dimensions["priority"] >= 0.2:
            patterns.append(self.evaluation_patterns["useless"])
        if dimensions["harmfulness"] >= 0.5:
            patterns.append(self.evaluation_patterns["harmful"])
        if dimensions["safety"] >= 0.5:
            patterns.append(self.evaluation_patterns["safe"])
        if dimensions["need"] >= 0.5:
            patterns.append(self.evaluation_patterns["needed"])
        if dimensions["want"] >= 0.5:
            patterns.append(self.evaluation_patterns["wanted"])
        if dimensions["avoid"] >= 0.5:
            patterns.append(self.evaluation_patterns["avoid"])
        if dimensions["priority"] >= 0.7:
            patterns.append(self.evaluation_patterns["priority_high"])
        elif dimensions["priority"] >= 0.4:
            patterns.append(self.evaluation_patterns["priority_medium"])
        else:
            patterns.append(self.evaluation_patterns["priority_low"])
        return _unique(patterns)


def _positive_dimensions() -> dict[str, float]:
    return {"usefulness": 0.65, "need": 0.55, "safety": 0.70, "priority": 0.55}


def _harm_dimensions() -> dict[str, float]:
    return {"harmfulness": 0.65, "avoid": 0.70, "need": 0.45, "priority": 0.70}


def _low_value_dimensions() -> dict[str, float]:
    return {"usefulness": 0.10, "safety": 0.30, "priority": 0.20}


def _tone_harm_dimensions() -> dict[str, float]:
    return {"harmfulness": 0.50, "avoid": 0.60, "need": 0.55, "priority": 0.65}


def _tone_positive_dimensions() -> dict[str, float]:
    return {"usefulness": 0.45, "want": 0.35, "safety": 0.50, "priority": 0.35}


def _normalized_dimensions(values: dict[str, float]) -> dict[str, float]:
    return {key: round(_clamp(values.get(key, 0.0)), 3) for key in DIMENSION_KEYS}


def _source_kind(marker: OperationMarker | None) -> str | None:
    if marker == OperationMarker.INTERNAL_ACTION_EFFECT:
        return "internal_action_effect"
    if marker == OperationMarker.OUTCOME_EVALUATION:
        return "outcome_evaluation"
    if marker == OperationMarker.EXPSM_FEEDBACK:
        return "expsm_feedback"
    return None


def _unique(values: list[Any]) -> list[str]:
    return [str(value) for value in dict.fromkeys(values) if value]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
