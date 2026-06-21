from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.neuromodulation.tone_state import ToneState
from clc.system.system_state import SystemState


class ConsolidationModeProcessor:
    """Internal low-external-attention processing during consolidation mode."""

    module_name = "consolidation_mode_processor"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.effects = {
            "processing": pattern_registry.id("state_consolidation_processing"),
            "reviewed": pattern_registry.id("state_pending_candidates_reviewed"),
            "load_reduced": pattern_registry.id("state_context_load_reduced"),
        }
        self.update_kind = pattern_registry.id("homeostasis_update")
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
        if system_state.mode != "consolidation" or tick == self._last_tick:
            return []
        self._last_tick = tick
        pending_candidates = [
            candidate
            for candidate in memory.get_recent_experience_candidates(16)
            if candidate.get("write_status") == "pending_consolidation"
        ][-6:]
        pending_groups = [
            candidate
            for candidate in memory.get_recent_consolidation_candidates(16)
            if candidate.get("write_status") == "pending_memory_consolidation"
        ][-6:]
        workload = len(pending_candidates) + len(pending_groups)
        fatigue_relief = -0.04 if workload <= 6 else -0.02
        delta = {
            "fatigue": fatigue_relief,
            "tension": -0.03,
            "stability": 0.02,
            "curiosity": -0.01,
        }
        activation = 0.65 + min(workload * 0.03, 0.25)
        reviewed_candidate_ids = [candidate.get("candidate_id", "") for candidate in pending_candidates if candidate.get("candidate_id")]
        reviewed_group_ids = [candidate.get("group_id", "") for candidate in pending_groups if candidate.get("group_id")]

        effect_payload = {
            "effect_id": self.id_gen.next("cons_effect"),
            "effect_pattern_id": self.effects["processing"],
            "effect_kind": self.effects["processing"],
            "secondary_effect_patterns": [self.effects["reviewed"], self.effects["load_reduced"]],
            "reviewed_candidate_ids": reviewed_candidate_ids,
            "reviewed_group_ids": reviewed_group_ids,
            "tone_delta": {key: round(value, 3) for key, value in delta.items()},
            "activation": round(min(1.0, activation), 3),
            "ttl": 5,
        }
        next_tone = tone_state.shifted(**delta)
        tone_payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "update_id": self.id_gen.next("consolidation_processing"),
            "update_kind": self.update_kind,
            "tone_state": next_tone,
            "tone_delta": {key: round(value, 3) for key, value in delta.items()},
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_experience_candidate_ids": reviewed_candidate_ids,
            "based_on_consolidation_group_ids": reviewed_group_ids,
            "activation": round(min(1.0, activation), 3),
            "ttl": 4,
        }
        return [
            ContextOperation(
                self.id_gen.next("op"),
                OperationMarker.INTERNAL_ACTION_EFFECT,
                tick,
                self.module_name,
                None,
                effect_payload,
            ),
            ContextOperation(
                self.id_gen.next("op"),
                OperationMarker.NEUROMODULATION_UPDATE,
                tick,
                self.module_name,
                None,
                tone_payload,
            ),
        ]
