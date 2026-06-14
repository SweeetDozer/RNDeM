from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.nfp import NFPFrame
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField


class ThoughtGeneratorModule:
    module_name = "thought_generator"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.novelty_id = pattern_registry.id("novel_activation_pattern")
        self.internal_risk_id = pattern_registry.id("internal_state_risk")
        self.need_more_data_id = pattern_registry.id("thought_need_more_data")
        self.increase_attention_id = pattern_registry.id("thought_increase_attention")
        self.inspect_pattern_id = pattern_registry.id("thought_inspect_pattern")
        self.store_candidate_id = pattern_registry.id("thought_store_candidate")
        self.preserve_integrity_id = pattern_registry.id("thought_preserve_integrity")
        self.reduce_load_id = pattern_registry.id("thought_reduce_load")
        self._last_tick = 0
        self._handled_effect_ids: set[str] = set()

    def run(self, tick: int, memory: ContextMemory, active_field: ActiveContextField | None = None) -> list[ContextOperation]:
        if tick == self._last_tick:
            return []
        self._last_tick = tick
        tone = memory.get_current_tone()
        labels = [label for label in memory.recent_labels(8) if label.get("_event_tick") == tick]
        risk = max([label.get("risk", 0.0) for label in labels] + [0.0])
        novelty = max([label.get("confidence", 0.0) for label in labels if label.get("label_pattern_id") == self.novelty_id] + [0.0])
        internal_risk = max([label.get("risk", 0.0) for label in labels if label.get("label_pattern_id") == self.internal_risk_id] + [0.0])
        field_pressure = 0.0
        if active_field is not None:
            field_pressure = max([pattern.activation for pattern in active_field.get_patterns_above(0.7) if pattern.kind in {"label", "prediction", "predicted_pattern"}] + [0.0])
        activations: dict[str, float] = {}
        if risk >= 0.55 or tone.tension >= 0.45 or field_pressure >= 0.7:
            activations[self.need_more_data_id] = max(risk, tone.tension, field_pressure)
            activations[self.increase_attention_id] = max(0.6, tone.risk_sensitivity)
        if novelty >= 0.55 and risk < 0.4:
            activations[self.inspect_pattern_id] = novelty
            activations[self.store_candidate_id] = 0.65
        if internal_risk >= 0.6:
            activations[self.preserve_integrity_id] = internal_risk
            activations[self.reduce_load_id] = 0.8
        if not activations:
            return []
        frame = NFPFrame(
            frame_id=self.id_gen.next("thought"),
            tick=tick,
            origin="self_generated",
            source="thought_module",
            activations=activations,
            ttl=3,
            decay=0.2,
        )
        return [
            ContextOperation(
                op_id=self.id_gen.next("op"),
                marker=OperationMarker.SELF_GENERATED_THOUGHT,
                tick=tick,
                source_module=self.module_name,
                target=None,
                payload={"frame": frame},
            )
        ]

    def run_effects(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        activations: dict[str, float] = {}
        handled_effects: list[str] = []
        ttl = 3
        for effect in memory.get_recent_effects(8):
            effect_id = effect.get("effect_id")
            if effect.get("_event_tick") != tick or not effect_id or effect_id in self._handled_effect_ids:
                continue
            generated = effect.get("generate_thought_patterns", ())
            if not generated:
                continue
            self._handled_effect_ids.add(effect_id)
            handled_effects.append(effect_id)
            ttl = max(ttl, int(effect.get("ttl", 3)))
            for pattern_id in generated:
                activations[pattern_id] = max(activations.get(pattern_id, 0.0), float(effect.get("activation", 0.6)))
        if not activations:
            return []
        frame = NFPFrame(
            frame_id=self.id_gen.next("thought"),
            tick=tick,
            origin="self_generated",
            source="thought_module",
            activations=activations,
            ttl=ttl,
            decay=0.18,
        )
        return [
            ContextOperation(
                op_id=self.id_gen.next("op"),
                marker=OperationMarker.SELF_GENERATED_THOUGHT,
                tick=tick,
                source_module=self.module_name,
                target=None,
                payload={"frame": frame, "source_effect_ids": handled_effects},
            )
        ]
