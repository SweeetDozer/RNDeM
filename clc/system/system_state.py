from dataclasses import dataclass


@dataclass
class SystemState:
    mode: str = "active"
    mode_entered_tick: int = 0
    last_consolidation_tick: int = 0
    consolidation_depth: float = 0.0
