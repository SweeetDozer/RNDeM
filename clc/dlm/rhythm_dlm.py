from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.dlm.base_dlm import BaseDLM


class RhythmDLM(BaseDLM):
    module_name = "rhythm_dlm"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.aud_440_id = pattern_registry.id("aud_freq_440")
        self.periodic_id = pattern_registry.id("periodic_audio_pattern")
        self._last_labeled_to_tick = 0

    def run(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        frames = [frame for frame in memory.get_recent_frames(6) if frame.source == "aud"]
        if len(frames) < 4 or frames[-1].tick == self._last_labeled_to_tick:
            return []
        values = [frame.activations.get(self.aud_440_id, 0.0) for frame in frames]
        direction_changes = 0
        prev_delta = 0.0
        for left, right in zip(values, values[1:]):
            delta = right - left
            if abs(delta) < 0.05:
                continue
            if prev_delta and (delta > 0) != (prev_delta > 0):
                direction_changes += 1
            prev_delta = delta
        if direction_changes < 2:
            return []
        window = memory.build_window(min(6, len(frames)), source="aud", origin="external")
        self._last_labeled_to_tick = frames[-1].tick
        payload = {
            "label_id": self.id_gen.next("label"),
            "label_kind": self.periodic_id,
            "label_pattern_id": self.periodic_id,
            "target_window": window.window_id if window else None,
            "confidence": 0.72,
            "risk": 0.4,
            "ttl": 4,
            "decay": 0.08,
            "activation_focus": {self.aud_440_id: max(values)},
        }
        return [self._op(tick, payload)]

    def _op(self, tick: int, payload: dict) -> ContextOperation:
        return ContextOperation(self.id_gen.next("op"), OperationMarker.LABEL, tick, self.module_name, None, payload)
