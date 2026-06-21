from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.dlm.base_dlm import BaseDLM
from clc.storage_models.akbsm_adapter import AKBSMAdapter
from clc.storage_models.pattern_store import PatternStore


class NoveltyDLM(BaseDLM):
    module_name = "novelty_dlm"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry, pattern_store: PatternStore, akbsm: AKBSMAdapter) -> None:
        self.id_gen = id_gen
        self.novelty_id = pattern_registry.id("novel_activation_pattern")
        self.known_id = pattern_registry.id("known_memory_pattern")
        self.pattern_store = pattern_store
        self.akbsm = akbsm
        self._last_labeled_tick = 0

    def run(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        latest = memory.get_recent_frames(1)
        if not latest or latest[-1].source != "img":
            return []
        frames = latest
        if frames[-1].tick == self._last_labeled_tick:
            return []
        window = memory.build_window(len(frames), source=frames[-1].source, origin=frames[-1].origin)
        if window is None:
            return []
        matches = self.pattern_store.find_similar_to_window(window, memory, threshold=0.5)
        weak_matches = self.pattern_store.find_similar_to_window(window, memory, threshold=0.0)[:3]
        related = self.akbsm.find_related_from_matches(matches)
        self._last_labeled_tick = frames[-1].tick
        if matches:
            payload = {
                "label_id": self.id_gen.next("label"),
                "label_kind": self.known_id,
                "label_pattern_id": self.known_id,
                "target_window": window.window_id,
                "confidence": matches[0].similarity,
                "risk": 0.05,
                "known_score": matches[0].similarity,
                "similar_matches": _match_payloads(matches[:3]),
                "related_patterns": [
                    {
                        "pattern_id": item.pattern_id,
                        "relation_type": item.relation_type,
                        "confidence": item.confidence,
                        "source_edge_id": item.source_edge_id,
                    }
                    for item in related[:3]
                ],
                "ttl": 4,
                "decay": 0.1,
                "activation": matches[0].similarity,
            }
            return [ContextOperation(self.id_gen.next("op"), OperationMarker.LABEL, tick, self.module_name, None, payload)]
        novelty_score = 1.0
        if weak_matches:
            novelty_score = round(1.0 - max(match.similarity for match in weak_matches), 3)
        payload = {
            "label_id": self.id_gen.next("label"),
            "label_kind": self.novelty_id,
            "label_pattern_id": self.novelty_id,
            "target_window": window.window_id,
            "confidence": novelty_score,
            "risk": 0.15,
            "novelty_score": novelty_score,
            "similar_matches": _match_payloads(weak_matches),
            "ttl": 5,
            "decay": 0.12,
            "activation": novelty_score,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.LABEL, tick, self.module_name, None, payload)]


def _match_payloads(matches: list) -> list[dict]:
    return [
        {
            "pattern_id": match.pattern_id,
            "similarity": match.similarity,
            "pattern_ref": match.pattern_ref,
        }
        for match in matches
    ]
