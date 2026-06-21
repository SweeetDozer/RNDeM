from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.neuromodulation.tone_state import ToneState
from clc.system.system_state import SystemState


class ConsolidationPressureModule:
    """Creates marker 12 pressure from pending memory-like material."""

    module_name = "consolidation_pressure_module"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.pressure_kind = pattern_registry.id("consolidation_pressure")
        self.level_patterns = {
            "low": pattern_registry.id("consolidation_pressure_low"),
            "medium": pattern_registry.id("consolidation_pressure_medium"),
            "high": pattern_registry.id("consolidation_pressure_high"),
        }
        self.novelty_id = pattern_registry.id("novel_activation_pattern")
        self._last_tick = 0

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        tone_state: ToneState,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        del active_field
        if tick == self._last_tick:
            return []
        self._last_tick = tick
        pending_experience = _pending_experience_count(memory)
        pending_consolidation = _pending_consolidation_count(memory)
        recent_novelty = _recent_novelty_count(tick, memory, self.novelty_id)
        recent_failed = _recent_failed_or_partial_count(tick, memory)
        recent_event_count = len([event for event in memory.get_recent_events(40) if tick - event.tick <= 4])
        ticks_since_last = max(0, tick - system_state.last_consolidation_tick)

        pressure = 0.0
        pressure += min(pending_experience * 0.08, 0.3)
        pressure += min(pending_consolidation * 0.12, 0.35)
        pressure += min(recent_novelty * 0.05, 0.2)
        pressure += min(recent_failed * 0.08, 0.25)
        pressure += max(0.0, tone_state.fatigue - 0.45) * 0.5
        pressure += max(0.0, tone_state.tension - 0.75) * 0.2
        pressure += min(ticks_since_last * 0.01, 0.2)
        pressure += min(recent_event_count * 0.005, 0.12)
        if system_state.mode == "consolidation":
            pressure *= 0.5
        pressure = round(max(0.0, min(1.0, pressure)), 3)
        level = _level(pressure)

        payload = {
            "pressure_id": self.id_gen.next("cons_pressure"),
            "pressure_kind": self.pressure_kind,
            "pressure_level": level,
            "pressure_value": pressure,
            "sources": {
                "pending_experience_candidates": pending_experience,
                "pending_consolidation_candidates": pending_consolidation,
                "recent_novelty_count": recent_novelty,
                "recent_failed_outcomes": recent_failed,
                "recent_event_count": recent_event_count,
                "fatigue": round(tone_state.fatigue, 3),
                "tension": round(tone_state.tension, 3),
                "ticks_since_last_consolidation": ticks_since_last,
            },
            "pressure_patterns": [self.level_patterns[level]],
            "activation": pressure,
            "ttl": 6,
        }
        return [
            ContextOperation(
                self.id_gen.next("op"),
                OperationMarker.CONSOLIDATION_PRESSURE,
                tick,
                self.module_name,
                None,
                payload,
            )
        ]


def _pending_experience_count(memory: ContextMemory) -> int:
    return sum(1 for candidate in memory.experience_candidates if candidate.get("write_status") == "pending_consolidation")


def _pending_consolidation_count(memory: ContextMemory) -> int:
    return sum(
        1
        for candidate in memory.consolidation_candidates
        if candidate.get("write_status") == "pending_memory_consolidation"
    )


def _recent_novelty_count(tick: int, memory: ContextMemory, novelty_id: str) -> int:
    return sum(
        1
        for label in memory.recent_labels(16)
        if tick - label.get("_event_tick", tick) <= 6 and label.get("label_pattern_id") == novelty_id
    )


def _recent_failed_or_partial_count(tick: int, memory: ContextMemory) -> int:
    return sum(
        1
        for outcome in memory.get_recent_outcomes(16)
        if tick - outcome.get("_event_tick", tick) <= 6
        and outcome.get("outcome_status") in {"failed", "partially_confirmed"}
    )


def _level(pressure: float) -> str:
    if pressure >= 0.65:
        return "high"
    if pressure >= 0.35:
        return "medium"
    return "low"
