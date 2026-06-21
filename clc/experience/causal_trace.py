from dataclasses import dataclass
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField


@dataclass(frozen=True)
class CausalTrace:
    source_outcome_id: str
    source_outcome_status: str
    decision_event_ids: tuple[str, ...]
    effect_event_ids: tuple[str, ...]
    prediction_event_ids: tuple[str, ...]
    decision_patterns: tuple[str, ...]
    effect_patterns: tuple[str, ...]
    predicted_patterns: tuple[str, ...]
    outcome_patterns: tuple[str, ...]
    context_label_event_ids: tuple[str, ...]
    context_frame_ids: tuple[str, ...]
    context_window_ids: tuple[str, ...]
    context_active_patterns: tuple[str, ...]
    context_prediction_event_ids: tuple[str, ...]

    def core_chain(self) -> dict[str, list[str]]:
        return {
            "decision_event_ids": list(self.decision_event_ids),
            "effect_event_ids": list(self.effect_event_ids),
            "prediction_event_ids": list(self.prediction_event_ids),
            "decision_patterns": list(self.decision_patterns),
            "effect_patterns": list(self.effect_patterns),
            "predicted_patterns": list(self.predicted_patterns),
            "outcome_patterns": list(self.outcome_patterns),
        }

    def context_refs(self) -> dict[str, list[str]]:
        return {
            "label_event_ids": list(self.context_label_event_ids),
            "frame_ids": list(self.context_frame_ids),
            "window_ids": list(self.context_window_ids),
            "nearby_prediction_event_ids": list(self.context_prediction_event_ids),
            "active_patterns": list(self.context_active_patterns),
        }


def build_causal_trace(
    outcome: dict[str, Any],
    memory: ContextMemory,
    active_field: ActiveContextField,
    pattern_registry: PatternRegistry,
    context_window_ticks: int = 3,
) -> CausalTrace:
    events_by_id = {event.op_id: event for event in memory.events}
    source_event = events_by_id.get(outcome.get("source_event_id"))
    source_tick = source_event.tick if source_event is not None else outcome.get("_event_tick", 0)
    decision_events: list[ContextOperation] = []
    effect_events: list[ContextOperation] = []
    prediction_events: list[ContextOperation] = []

    if source_event is not None and source_event.marker == OperationMarker.INTERNAL_DECISION:
        decision_events.append(source_event)
        decision_id = source_event.payload.get("decision_id")
        effect_events.extend(
            event
            for event in memory.events
            if event.marker == OperationMarker.INTERNAL_ACTION_EFFECT
            and event.payload.get("source_decision_id") == decision_id
        )
    elif source_event is not None and source_event.marker == OperationMarker.INTERNAL_ACTION_EFFECT:
        effect_events.append(source_event)
        source_decision_id = source_event.payload.get("source_decision_id")
        decision_events.extend(
            event
            for event in memory.events
            if event.marker == OperationMarker.INTERNAL_DECISION
            and event.payload.get("decision_id") == source_decision_id
        )
    elif source_event is not None and source_event.marker == OperationMarker.PREDICTION:
        prediction_events.append(source_event)

    nearby_events = [event for event in memory.events if abs(event.tick - source_tick) <= context_window_ticks]
    source_prediction_ids = {event.op_id for event in prediction_events}
    context_prediction_events = [
        event
        for event in nearby_events
        if event.marker == OperationMarker.PREDICTION and event.op_id not in source_prediction_ids
    ]
    frames = [frame for frame in memory.all_frames() if abs(frame.tick - source_tick) <= context_window_ticks]
    windows = [window for window in memory.windows if abs(window.to_tick - source_tick) <= context_window_ticks]
    outcome_patterns = list(outcome.get("matched_patterns", ()))
    outcome_pattern = outcome.get("outcome_pattern_id") or _outcome_pattern_id(outcome.get("outcome_status"), pattern_registry)
    if outcome_pattern:
        outcome_patterns.append(outcome_pattern)

    return CausalTrace(
        source_outcome_id=outcome.get("outcome_id", ""),
        source_outcome_status=outcome.get("outcome_status", ""),
        decision_event_ids=tuple(_unique([event.op_id for event in decision_events])),
        effect_event_ids=tuple(_unique([event.op_id for event in effect_events])),
        prediction_event_ids=tuple(_unique([event.op_id for event in prediction_events])),
        decision_patterns=tuple(_unique([event.payload.get("decision_pattern_id", "") for event in decision_events])),
        effect_patterns=tuple(_unique([event.payload.get("effect_pattern_id", "") for event in effect_events])),
        predicted_patterns=tuple(_unique(_predicted_patterns(prediction_events))),
        outcome_patterns=tuple(_unique(outcome_patterns)),
        context_label_event_ids=tuple(_unique([event.op_id for event in nearby_events if event.marker == OperationMarker.LABEL])),
        context_frame_ids=tuple(_unique([frame.frame_id for frame in frames[-8:]])),
        context_window_ids=tuple(_unique([window.window_id for window in windows[-8:]])),
        context_active_patterns=tuple(_unique([pattern.pattern_id for pattern in active_field.get_top_patterns(limit=12)])),
        context_prediction_event_ids=tuple(_unique([event.op_id for event in context_prediction_events])),
    )


def _predicted_patterns(prediction_events: list[ContextOperation]) -> list[str]:
    patterns: list[str] = []
    for event in prediction_events:
        patterns.extend(event.payload.get("predicted_patterns", ()))
    return patterns


def _outcome_pattern_id(status: str | None, pattern_registry: PatternRegistry) -> str:
    names = {
        "confirmed": "outcome_confirmed",
        "partially_confirmed": "outcome_partially_confirmed",
        "failed": "outcome_failed",
        "expired": "outcome_expired",
        "inconclusive": "outcome_inconclusive",
    }
    return pattern_registry.id(names.get(status, "outcome_inconclusive"))


def _unique(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(values) if value]
