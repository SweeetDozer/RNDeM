from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.dlm.base_dlm import BaseDLM
from clc.storage_models.expsm_adapter import ExpSMAdapter
from clc.storage_models.fake_expsm import FakeExpSM


class RiskDLM(BaseDLM):
    module_name = "risk_dlm"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry, expsm_adapter: ExpSMAdapter, fallback_expsm: FakeExpSM) -> None:
        self.id_gen = id_gen
        self.risk_id = pattern_registry.id("experienced_risk_pattern")
        self.expsm_adapter = expsm_adapter
        self.fallback_expsm = fallback_expsm
        self._last_labeled_tick = 0

    def run(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        current_frames = [frame for frame in memory.get_recent_frames(4) if frame.tick == tick and frame.origin != "self_generated"]
        frames = current_frames
        if not frames or frames[-1].tick == self._last_labeled_tick:
            return []
        window = memory.build_window(len(frames), source=frames[-1].source, origin=frames[-1].origin)
        if window is None:
            return []
        reflex_matches = self.expsm_adapter.match_reflexes(window, memory, threshold=0.4)
        experience_matches = self.expsm_adapter.match_experiences(window, memory, threshold=0.45)
        matches = reflex_matches + experience_matches
        if matches:
            risk_score = max(match.similarity * match.confidence for match in matches)
            self._last_labeled_tick = frames[-1].tick
            payload = {
                "label_id": self.id_gen.next("label"),
                "label_kind": self.risk_id,
                "label_pattern_id": self.risk_id,
                "target_window": window.window_id,
                "confidence": round(risk_score, 3),
                "risk": round(risk_score, 3),
                "matched_records": [
                    {
                        "record_id": match.record_id,
                        "record_type": match.record_type,
                        "similarity": match.similarity,
                        "confidence": match.confidence,
                        "priority": match.priority,
                        "suggested_patterns": list(match.suggested_patterns),
                    }
                    for match in matches[:4]
                ],
                "ttl": 5,
                "decay": 0.1,
                "activation": round(risk_score, 3),
            }
            return [ContextOperation(self.id_gen.next("op"), OperationMarker.LABEL, tick, self.module_name, None, payload)]
        risk_score = self.fallback_expsm.risk_score(frames)
        if risk_score < 0.5:
            return []
        self._last_labeled_tick = frames[-1].tick
        payload = {
            "label_id": self.id_gen.next("label"),
            "label_kind": self.risk_id,
            "label_pattern_id": self.risk_id,
            "target_window": window.window_id,
            "confidence": risk_score,
            "risk": risk_score,
            "matched_records": [],
            "ttl": 3,
            "decay": 0.1,
            "activation": risk_score,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.LABEL, tick, self.module_name, None, payload)]
