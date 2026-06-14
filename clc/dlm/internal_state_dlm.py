from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.dlm.base_dlm import BaseDLM


class InternalStateDLM(BaseDLM):
    module_name = "internal_state_dlm"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.internal_risk_id = pattern_registry.id("internal_state_risk")
        self.sensor_risk_ids = {
            pattern_registry.id("sen_cpu_temp_high"),
            pattern_registry.id("sen_memory_pressure"),
            pattern_registry.id("sen_integrity_warning"),
            pattern_registry.id("sen_resource_pressure"),
        }
        self._last_labeled_tick = 0

    def run(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        frames = [frame for frame in memory.get_recent_frames(4) if frame.source == "sen"]
        if not frames or frames[-1].tick == self._last_labeled_tick:
            return []
        current = frames[-1]
        signals = {
            key: value
            for key, value in current.activations.items()
            if key in self.sensor_risk_ids and value >= 0.6
        }
        if not signals:
            return []
        self._last_labeled_tick = current.tick
        payload = {
            "label_id": self.id_gen.next("label"),
            "label_kind": self.internal_risk_id,
            "label_pattern_id": self.internal_risk_id,
            "target_frame": current.frame_id,
            "confidence": max(signals.values()),
            "risk": max(signals.values()),
            "ttl": 3,
            "decay": 0.15,
            "activation_focus": signals,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.LABEL, tick, self.module_name, None, payload)]
