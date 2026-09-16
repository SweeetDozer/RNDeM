from __future__ import annotations

from dataclasses import dataclass
import math

from clc.patterns import NFPFrame, PatternModality, PatternOrigin, PatternTopology


@dataclass(frozen=True)
class VisualFieldSnapshot:
    """Immutable numeric visual sensor-boundary snapshot."""

    shape: tuple[int, int]
    values: tuple[float, ...]
    active_tick: int
    snapshot_id: int

    def __post_init__(self) -> None:
        shape = tuple(self.shape)
        if len(shape) != 2:
            raise ValueError("shape must have exactly 2 dimensions")
        if any(not isinstance(dimension, int) for dimension in shape):
            raise TypeError("shape dimensions must be integers")
        if any(dimension <= 0 for dimension in shape):
            raise ValueError("shape dimensions must be positive")
        active_tick = _non_negative_int(self.active_tick, "active_tick")
        snapshot_id = _non_negative_int(self.snapshot_id, "snapshot_id")
        values = tuple(float(value) for value in self.values)
        if len(values) != shape[0] * shape[1]:
            raise ValueError("values length must equal rows * columns")
        for value in values:
            if not math.isfinite(value):
                raise ValueError("snapshot values must be finite")
            if value < 0.0 or value > 1.0:
                raise ValueError("snapshot values must be in [0.0, 1.0]")
        object.__setattr__(self, "shape", shape)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "active_tick", active_tick)
        object.__setattr__(self, "snapshot_id", snapshot_id)


class VisualFieldTransducer:
    """Deterministic label-free visual scalar-field transducer."""

    def transduce(self, snapshot: VisualFieldSnapshot, *, frame_id: str) -> NFPFrame:
        if not isinstance(snapshot, VisualFieldSnapshot):
            raise TypeError("snapshot must be VisualFieldSnapshot")
        return NFPFrame(
            frame_id=frame_id,
            modality=PatternModality.VISUAL,
            origin=PatternOrigin.EXTERNAL_SENSORY,
            topology=PatternTopology(snapshot.shape),
            values=tuple(snapshot.values),
            active_tick=snapshot.active_tick,
            provenance_ref=f"sensor_snapshot:{snapshot.snapshot_id:06d}",
            debug_name=None,
        )


def _non_negative_int(value: int, field_name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value
