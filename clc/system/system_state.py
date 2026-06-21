from dataclasses import dataclass
from typing import Any


@dataclass
class SystemState:
    mode: str = "active"
    mode_entered_tick: int = 0
    last_consolidation_tick: int = 0
    consolidation_depth: float = 0.0
    runtime_profile: str = "safe_demo"
    memory_mutation_policy: dict[str, Any] | None = None
