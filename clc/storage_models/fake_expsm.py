from clc.core.nfp import NFPFrame
from clc.core.pattern_registry import PatternRegistry


class FakeExpSM:
    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.risk_patterns: dict[str, float] = {
            pattern_registry.id("sen_integrity_warning"): 0.95,
            pattern_registry.id("sen_memory_pressure"): 0.75,
            pattern_registry.id("sen_cpu_temp_high"): 0.65,
            pattern_registry.id("sen_resource_pressure"): 0.55,
        }

    def risk_score(self, frames: list[NFPFrame]) -> float:
        score = 0.0
        for frame in frames:
            for activation_id, value in frame.activations.items():
                if activation_id in self.risk_patterns:
                    score = max(score, value * self.risk_patterns[activation_id])
        return round(score, 3)
