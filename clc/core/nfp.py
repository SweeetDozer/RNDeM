from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class NFPFrame:
    """A momentary neuron firing pattern slice.

    The activation mapping is copied and wrapped so raw frames cannot be
    mutated after being written to context memory.
    """

    frame_id: str
    tick: int
    origin: str
    source: str
    activations: Mapping[str, float] = field(default_factory=dict)
    ttl: int | None = None
    decay: float = 0.0

    def __post_init__(self) -> None:
        copied = {key: _clamp(value) for key, value in self.activations.items()}
        object.__setattr__(self, "activations", MappingProxyType(copied))

    def active_ids(self, threshold: float = 0.05) -> set[str]:
        return {key for key, value in self.activations.items() if value >= threshold}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
