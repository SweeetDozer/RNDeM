from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.neuromodulation.tone_state import ToneState


TARGETS = {
    "integrity": 0.95,
    "stability": 0.75,
    "curiosity": 0.35,
    "risk_sensitivity": 0.5,
    "fatigue": 0.15,
    "tension": 0.2,
    "satisfaction": 0.0,
    "pain": 0.0,
}


class HomeostasisModule:
    """Keeps ToneState in a workable range through marker 6 updates."""

    module_name = "homeostasis_module"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.update_kind = pattern_registry.id("homeostasis_update")
        self.patterns = {
            "tension_relief": pattern_registry.id("homeostasis_tension_relief"),
            "risk_normalization": pattern_registry.id("homeostasis_risk_normalization"),
            "reduce_load_pressure": pattern_registry.id("homeostasis_reduce_load_pressure"),
            "pain_recovery": pattern_registry.id("homeostasis_pain_recovery"),
            "satisfaction_decay": pattern_registry.id("homeostasis_satisfaction_decay"),
            "stability_recovery": pattern_registry.id("homeostasis_stability_recovery"),
            "curiosity_regulation": pattern_registry.id("homeostasis_curiosity_regulation"),
            "preserve_integrity_pressure": pattern_registry.id("homeostasis_preserve_integrity_pressure"),
        }
        self.risk_patterns = {
            pattern_registry.id("experienced_risk_pattern"),
            pattern_registry.id("internal_state_risk"),
            pattern_registry.id("label_risk"),
        }
        self.outcome_patterns = {
            "confirmed": pattern_registry.id("outcome_confirmed"),
            "failed": pattern_registry.id("outcome_failed"),
        }
        self._last_tick = 0

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        tone_state: ToneState,
        active_field: ActiveContextField,
    ) -> list[ContextOperation]:
        if tick == self._last_tick:
            return []
        self._last_tick = tick
        recent_strong_risk = self._recent_strong_risk(tick, memory, active_field)
        recent_confirmed = self._recent_outcomes(tick, memory, "confirmed")
        recent_failed = self._recent_outcomes(tick, memory, "failed")
        delta: dict[str, float] = {}
        homeostasis_patterns: list[str] = []
        reason_pattern_ids: list[str] = []

        if tone_state.tension > 0.5 and not recent_strong_risk:
            if recent_confirmed:
                _add(delta, "tension", -0.06)
                _add(delta, "satisfaction", 0.01)
                reason_pattern_ids.append(self.outcome_patterns["confirmed"])
            else:
                _add(delta, "tension", -0.04)
            homeostasis_patterns.append(self.patterns["tension_relief"])

        if tone_state.risk_sensitivity > 0.75 and not recent_strong_risk and not recent_failed:
            _add(delta, "risk_sensitivity", -0.03)
            homeostasis_patterns.append(self.patterns["risk_normalization"])

        if tone_state.fatigue > 0.6:
            _add(delta, "tension", 0.02)
            homeostasis_patterns.append(self.patterns["reduce_load_pressure"])

        if tone_state.pain > 0.2 and not recent_failed:
            _add(delta, "pain", -0.03)
            homeostasis_patterns.append(self.patterns["pain_recovery"])

        if tone_state.satisfaction > TARGETS["satisfaction"]:
            _add(delta, "satisfaction", -min(0.02, tone_state.satisfaction))
            homeostasis_patterns.append(self.patterns["satisfaction_decay"])

        if tone_state.stability < TARGETS["stability"] and recent_confirmed and not recent_failed:
            _add(delta, "stability", 0.02)
            homeostasis_patterns.append(self.patterns["stability_recovery"])
            reason_pattern_ids.append(self.outcome_patterns["confirmed"])

        if tone_state.curiosity > 0.7 and tone_state.risk_sensitivity > 0.7:
            _add(delta, "curiosity", -0.03)
            homeostasis_patterns.append(self.patterns["curiosity_regulation"])
        elif tone_state.curiosity < 0.2 and tone_state.risk_sensitivity < 0.6 and tone_state.fatigue < 0.5:
            _add(delta, "curiosity", 0.01)
            homeostasis_patterns.append(self.patterns["curiosity_regulation"])

        if tone_state.integrity < 0.9:
            _add(delta, "tension", 0.03)
            homeostasis_patterns.append(self.patterns["preserve_integrity_pressure"])

        if not delta and not homeostasis_patterns:
            return []

        next_tone = tone_state.shifted(**delta)
        activation = self._activation_for(tone_state, homeostasis_patterns)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "update_id": self.id_gen.next("homeostasis"),
            "update_kind": self.update_kind,
            "tone_state": next_tone,
            "tone_delta": {key: round(value, 3) for key, value in delta.items()},
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "homeostasis_patterns": list(dict.fromkeys(homeostasis_patterns)),
            "reason_pattern_ids": list(dict.fromkeys(reason_pattern_ids)),
            "activation": activation,
            "ttl": 4,
        }
        return [
            ContextOperation(
                self.id_gen.next("op"),
                OperationMarker.NEUROMODULATION_UPDATE,
                tick,
                self.module_name,
                None,
                payload,
            )
        ]

    def _recent_strong_risk(self, tick: int, memory: ContextMemory, active_field: ActiveContextField) -> bool:
        for label in memory.recent_labels(12):
            if tick - label.get("_event_tick", tick) <= 4 and label.get("risk", 0.0) > 0.6:
                return True
        for pattern in active_field.get_patterns_above(0.6):
            if pattern.pattern_id in self.risk_patterns:
                return True
        return False

    def _recent_outcomes(self, tick: int, memory: ContextMemory, status: str) -> list[dict]:
        return [
            outcome
            for outcome in memory.get_recent_outcomes(12)
            if tick - outcome.get("_event_tick", tick) <= 4 and outcome.get("outcome_status") == status
        ]

    def _activation_for(self, tone_state: ToneState, homeostasis_patterns: list[str]) -> float:
        if self.patterns["reduce_load_pressure"] in homeostasis_patterns:
            return 0.7
        if self.patterns["preserve_integrity_pressure"] in homeostasis_patterns:
            return 0.75
        pressure = max(
            tone_state.tension - TARGETS["tension"],
            tone_state.risk_sensitivity - TARGETS["risk_sensitivity"],
            tone_state.fatigue - TARGETS["fatigue"],
            tone_state.pain - TARGETS["pain"],
            TARGETS["stability"] - tone_state.stability,
            0.0,
        )
        return round(max(0.35, min(0.8, pressure)), 3)


def _add(delta: dict[str, float], key: str, amount: float) -> None:
    delta[key] = delta.get(key, 0.0) + amount
