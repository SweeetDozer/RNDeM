import json
import math
from pathlib import Path
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


FEEDBACK_DELAY_TICKS = 2
FEEDBACK_CONFIDENCE_CAP = 0.60
HIT_SATURATION = 20.0
CONFIDENCE_SMOOTHING_OLD = 0.75
CONFIDENCE_SMOOTHING_NEW = 0.25
LEGACY_CONFIDENCE_SOFT_CAP = 0.75
REPEATABILITY_CAP = 0.90
REPEATABILITY_SATURATION = 10.0
CONFIDENCE_MODEL = "simple_hit_miss_diminishing_returns"


class ExpSMOutcomeFeedback:
    """Applies simple hit/miss feedback to existing active-mode ExpSM experiences."""

    module_name = "expsm_outcome_feedback"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry, expsm_path: str | Path) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.expsm_path = Path(expsm_path)
        self.feedback_kind = pattern_registry.id("expsm_feedback")
        self._processed_keys: set[tuple[str, str, str]] = set()

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        del active_field
        if system_state.mode != "active":
            return []
        data = self._load_data()
        experiences = data.get("experience")
        if not isinstance(experiences, dict):
            return []
        events_by_id = {event.op_id: event for event in memory.events}
        operations: list[ContextOperation] = []
        for activation_event in memory.events:
            if activation_event.marker != OperationMarker.EXPSM_ACTIVATION:
                continue
            if tick - activation_event.tick < FEEDBACK_DELAY_TICKS:
                continue
            activation = dict(activation_event.payload)
            experience_id = str(activation.get("experience_id", ""))
            if experience_id not in experiences:
                continue
            then_patterns = _as_set(activation.get("then_patterns"))
            if not then_patterns:
                continue
            for decision_event in self._selected_decisions(memory, activation_event, then_patterns):
                decision = dict(decision_event.payload)
                decision_id = str(decision.get("decision_id", ""))
                trace_source = "direct_decision_source" if decision.get("source") == "expsm_activation" else "activation_event_link"
                outcome_event = self._linked_outcome(tick, memory, decision_event)
                if outcome_event is None:
                    continue
                outcome = dict(outcome_event.payload)
                status = self._feedback_status(activation, decision, memory, decision_event, outcome_event, events_by_id)
                if status == "no_feedback":
                    continue
                key = (experience_id, str(activation.get("activation_id", "")), decision_id)
                if key in self._processed_keys:
                    continue
                if self._metadata_already_processed(experiences[experience_id], key):
                    self._processed_keys.add(key)
                    continue
                operation = self._apply_feedback(
                    tick,
                    data,
                    experiences,
                    memory,
                    experience_id,
                    activation,
                    decision,
                    decision_event.op_id,
                    outcome,
                    outcome_event,
                    status,
                    key,
                    trace_source,
                )
                if operation is not None:
                    operations.append(operation)
                    self._processed_keys.add(key)
                    self._write_data(data)
        return operations

    def _selected_decisions(
        self,
        memory: ContextMemory,
        activation_event: ContextOperation,
        then_patterns: set[str],
    ) -> list[ContextOperation]:
        activation_id = activation_event.payload.get("activation_id")
        selected: list[ContextOperation] = []
        for event in memory.events:
            if event.marker != OperationMarker.INTERNAL_DECISION:
                continue
            if event.tick < activation_event.tick:
                continue
            payload = dict(event.payload)
            if payload.get("source") == "expsm_activation":
                if (
                    str(payload.get("source_experience_id", "")) == str(activation_event.payload.get("experience_id", ""))
                    and str(payload.get("source_activation_id", "")) == str(activation_id)
                    and payload.get("decision_pattern_id") in then_patterns
                ):
                    selected.append(event)
                continue
            if payload.get("decision_pattern_id") not in then_patterns:
                continue
            source_event_ids = set(payload.get("source_event_ids", ()))
            if activation_event.op_id in source_event_ids or activation_id in source_event_ids:
                selected.append(event)
                continue
            if event.tick - activation_event.tick <= FEEDBACK_DELAY_TICKS:
                selected.append(event)
        return selected

    def _linked_outcome(
        self,
        tick: int,
        memory: ContextMemory,
        decision_event: ContextOperation,
    ) -> ContextOperation | None:
        decision = dict(decision_event.payload)
        decision_id = decision.get("decision_id")
        effect_events = [
            event
            for event in memory.events
            if event.marker == OperationMarker.INTERNAL_ACTION_EFFECT
            and event.tick >= decision_event.tick
            and event.payload.get("source_decision_id") == decision_id
        ]
        effect_event_ids = {event.op_id for event in effect_events}
        direct: list[ContextOperation] = []
        nearby: list[ContextOperation] = []
        for event in memory.events:
            if event.marker != OperationMarker.OUTCOME_EVALUATION:
                continue
            if event.tick < decision_event.tick or event.tick > tick:
                continue
            source_event_id = event.payload.get("source_event_id")
            if source_event_id == decision_event.op_id or source_event_id in effect_event_ids:
                direct.append(event)
            elif event.tick - decision_event.tick <= FEEDBACK_DELAY_TICKS + 1:
                nearby.append(event)
        if direct:
            return sorted(direct, key=lambda event: (event.tick, event.op_id))[0]
        return sorted(nearby, key=lambda event: (event.tick, event.op_id))[0] if nearby else None

    def _feedback_status(
        self,
        activation: dict[str, Any],
        decision: dict[str, Any],
        memory: ContextMemory,
        decision_event: ContextOperation,
        outcome_event: ContextOperation,
        events_by_id: dict[str, ContextOperation],
    ) -> str:
        del decision, decision_event, events_by_id
        outcome = dict(outcome_event.payload)
        outcome_status = outcome.get("outcome_status")
        if outcome_status == "inconclusive":
            return "no_feedback"
        if outcome_status in {"failed", "expired"}:
            return "miss"
        if outcome_status == "partially_confirmed":
            return "partial_hit"
        if outcome_status == "confirmed":
            expected = _as_set(activation.get("result_patterns")) | _as_set(activation.get("recommendation_patterns"))
            actual = self._actual_patterns(memory, outcome_event)
            if expected and actual and not expected.intersection(actual):
                return "partial_hit"
            return "hit"
        return "no_feedback"

    def _actual_patterns(self, memory: ContextMemory, outcome_event: ContextOperation) -> set[str]:
        outcome = dict(outcome_event.payload)
        actual = _as_set(outcome.get("matched_patterns"))
        actual.update(_as_set([outcome.get("outcome_pattern_id")]))
        source_event_id = outcome.get("source_event_id")
        source_event = next((event for event in memory.events if event.op_id == source_event_id), None)
        if source_event is not None and source_event.marker == OperationMarker.INTERNAL_ACTION_EFFECT:
            actual.update(_as_set([source_event.payload.get("effect_kind"), source_event.payload.get("effect_pattern_id")]))
        return {pattern for pattern in actual if pattern}

    def _apply_feedback(
        self,
        tick: int,
        data: dict[str, Any],
        experiences: dict[str, Any],
        memory: ContextMemory,
        experience_id: str,
        activation: dict[str, Any],
        decision: dict[str, Any],
        decision_event_id: str,
        outcome: dict[str, Any],
        outcome_event: ContextOperation,
        status: str,
        key: tuple[str, str, str],
        trace_source: str,
    ) -> ContextOperation | None:
        del data
        record = experiences.get(experience_id)
        if not isinstance(record, dict):
            return None
        old_hits = int(record.get("hits", 0) or 0)
        old_misses = int(record.get("misses", 0) or 0)
        old_confidence = float(record.get("confidence", 0.0) or 0.0)
        old_repeatability = float(record.get("repeatability", 0.0) or 0.0)
        new_hits = old_hits + (1 if status in {"hit", "partial_hit"} else 0)
        new_misses = old_misses + (1 if status == "miss" else 0)
        target_confidence = _confidence_from_simple_feedback(new_hits, new_misses)
        old_confidence_for_update = min(old_confidence, LEGACY_CONFIDENCE_SOFT_CAP)
        new_confidence = _clamp(
            (old_confidence_for_update * CONFIDENCE_SMOOTHING_OLD)
            + (target_confidence * CONFIDENCE_SMOOTHING_NEW),
            0.0,
            LEGACY_CONFIDENCE_SOFT_CAP,
        )
        evidence_total = new_hits + new_misses
        target_repeatability = REPEATABILITY_CAP * (1.0 - math.exp(-evidence_total / REPEATABILITY_SATURATION))
        new_repeatability = _clamp(max(old_repeatability * 0.85, target_repeatability), 0.0, REPEATABILITY_CAP)
        success_ratio = new_hits / max(1, evidence_total)
        hit_strength = FEEDBACK_CONFIDENCE_CAP * (1.0 - math.exp(-new_hits / HIT_SATURATION))
        legacy_confidence_soft_cap_applied = old_confidence > LEGACY_CONFIDENCE_SOFT_CAP or new_confidence >= LEGACY_CONFIDENCE_SOFT_CAP
        metadata = record.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            record["metadata"] = metadata
        if status == "partial_hit":
            metadata["partial_hits"] = int(metadata.get("partial_hits", 0) or 0) + 1
        metadata["last_feedback_tick"] = tick
        metadata["last_feedback_status"] = status
        metadata["last_feedback_activation_id"] = activation.get("activation_id")
        metadata["last_feedback_decision_id"] = decision.get("decision_id")
        metadata["feedback_count"] = int(metadata.get("feedback_count", 0) or 0) + 1
        metadata["feedback_confidence_cap"] = FEEDBACK_CONFIDENCE_CAP
        metadata["feedback_confidence_model"] = CONFIDENCE_MODEL
        metadata["confidence_requires_evaluation_for_high_values"] = True
        metadata["last_feedback_target_confidence"] = round(target_confidence, 3)
        metadata["last_feedback_success_ratio"] = round(success_ratio, 3)
        metadata["last_feedback_hit_strength"] = round(hit_strength, 3)
        applied = list(metadata.get("applied_feedback_keys", ()))
        feedback_key = _feedback_key(key)
        applied.append(feedback_key)
        metadata["applied_feedback_keys"] = applied[-24:]
        record["hits"] = new_hits
        record["misses"] = new_misses
        record["confidence"] = round(new_confidence, 3)
        record["repeatability"] = round(new_repeatability, 3)
        effect_event = self._effect_for_outcome(memory, outcome_event, decision.get("decision_id"))
        expected = sorted(_as_set(activation.get("result_patterns")) | _as_set(activation.get("recommendation_patterns")))
        actual = sorted(self._actual_patterns_from_payload(outcome, effect_event))
        matched_expected = sorted(set(expected).intersection(actual))
        payload = {
            "feedback_id": self.id_gen.next("expsm_feedback"),
            "feedback_kind": self.feedback_kind,
            "experience_id": experience_id,
            "activation_id": activation.get("activation_id"),
            "decision_id": decision.get("decision_id"),
            "decision_event_id": decision_event_id,
            "effect_id": effect_event.payload.get("effect_id") if effect_event is not None else None,
            "outcome_id": outcome.get("outcome_id"),
            "feedback_status": status,
            "trace_source": trace_source,
            "selected_action": decision.get("decision_pattern_id"),
            "expected_patterns": expected,
            "actual_patterns": actual,
            "matched_expected_patterns": matched_expected,
            "old_hits": old_hits,
            "new_hits": new_hits,
            "old_misses": old_misses,
            "new_misses": new_misses,
            "old_confidence": round(old_confidence, 3),
            "target_confidence": round(target_confidence, 3),
            "new_confidence": round(new_confidence, 3),
            "old_repeatability": round(old_repeatability, 3),
            "new_repeatability": round(new_repeatability, 3),
            "confidence_model": CONFIDENCE_MODEL,
            "feedback_confidence_cap": FEEDBACK_CONFIDENCE_CAP,
            "success_ratio": round(success_ratio, 3),
            "hit_strength": round(hit_strength, 3),
            "legacy_confidence_soft_cap_applied": legacy_confidence_soft_cap_applied,
            "semantic_core_modified": False,
            "new_record_created": False,
            "reflexes_modified": False,
            "akbsm_modified": False,
            "permanent_memory_modified": True,
            "activation": 0.8,
            "ttl": 12,
        }
        return ContextOperation(self.id_gen.next("op"), OperationMarker.EXPSM_FEEDBACK, tick, self.module_name, None, payload)

    def _effect_for_outcome(
        self,
        memory: ContextMemory,
        outcome_event: ContextOperation,
        decision_id: Any,
    ) -> ContextOperation | None:
        source_event_id = outcome_event.payload.get("source_event_id")
        for event in memory.events:
            if event.op_id == source_event_id and event.marker == OperationMarker.INTERNAL_ACTION_EFFECT:
                return event
        for event in memory.events:
            if event.marker == OperationMarker.INTERNAL_ACTION_EFFECT and event.payload.get("source_decision_id") == decision_id:
                return event
        return None

    def _actual_patterns_from_payload(self, outcome: dict[str, Any], effect_event: ContextOperation | None) -> set[str]:
        actual = _as_set(outcome.get("matched_patterns"))
        actual.update(_as_set([outcome.get("outcome_pattern_id")]))
        if effect_event is not None:
            actual.update(_as_set([effect_event.payload.get("effect_kind"), effect_event.payload.get("effect_pattern_id")]))
        return {pattern for pattern in actual if pattern}

    def _metadata_already_processed(self, record: Any, key: tuple[str, str, str]) -> bool:
        if not isinstance(record, dict):
            return False
        metadata = record.get("metadata", {})
        if not isinstance(metadata, dict):
            return False
        target_core = key
        for stored_key in metadata.get("applied_feedback_keys", ()):
            if _feedback_key_core(str(stored_key)) == target_core:
                return True
        return False

    def _load_data(self) -> dict[str, Any]:
        if not self.expsm_path.exists():
            return {}
        try:
            with self.expsm_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_data(self, data: dict[str, Any]) -> None:
        self.expsm_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.expsm_path.with_suffix(self.expsm_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        tmp_path.replace(self.expsm_path)


def _as_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if item}
    return set()


def _feedback_key(key: tuple[str, str, str]) -> str:
    return "|".join(key)


def _feedback_key_core(key: str) -> tuple[str, str, str] | None:
    parts = key.split("|")
    if len(parts) < 3:
        return None
    return (parts[0], parts[1], parts[2])


def _confidence_from_simple_feedback(hits: int, misses: int) -> float:
    total = hits + misses
    if total <= 0:
        return 0.0
    hit_strength = FEEDBACK_CONFIDENCE_CAP * (1.0 - math.exp(-hits / HIT_SATURATION))
    success_ratio = hits / max(1, total)
    return _clamp(hit_strength * success_ratio, 0.0, FEEDBACK_CONFIDENCE_CAP)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
