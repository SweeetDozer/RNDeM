from clc.core.nfp import NFPFrame
from clc.core.pattern_registry import PatternRegistry


class FakeAKBSM:
    """Known activation pattern ids; no text meanings are used by modules."""

    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.known_activation_ids = {
            pattern_registry.id("aud_freq_440"),
            pattern_registry.id("aud_freq_880"),
            pattern_registry.id("aud_freq_1200"),
            pattern_registry.id("sen_cpu_temp_high"),
            pattern_registry.id("sen_memory_pressure"),
            pattern_registry.id("sen_integrity_warning"),
            pattern_registry.id("sen_resource_pressure"),
        }

    def similarity(self, frames: list[NFPFrame]) -> float:
        active_ids = set().union(*(frame.active_ids() for frame in frames)) if frames else set()
        if not active_ids:
            return 1.0
        known = active_ids.intersection(self.known_activation_ids)
        return len(known) / len(active_ids)

    def unknown_ratio(self, frames: list[NFPFrame]) -> float:
        return 1.0 - self.similarity(frames)
