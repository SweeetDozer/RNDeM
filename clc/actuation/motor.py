from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

from clc.patterns import NFPFrame, PatternModality, PatternOrigin, PatternTopology


ACTION_MOTOR_TOPOLOGY = PatternTopology((2,))


@dataclass(frozen=True)
class ActuatorSignal:
    """Immutable numeric actuator-boundary signal."""

    values: tuple[float, ...]
    active_tick: int
    signal_id: int
    source_frame_ref: str

    def __post_init__(self) -> None:
        values = tuple(float(value) for value in self.values)
        if len(values) != 2:
            raise ValueError("values length must be 2")
        for value in values:
            if not math.isfinite(value):
                raise ValueError("values must be finite")
            if value < 0.0 or value > 1.0:
                raise ValueError("values must be in [0.0, 1.0]")
        active_tick = _non_negative_int(self.active_tick, "active_tick")
        signal_id = _non_negative_int(self.signal_id, "signal_id")
        source_frame_ref = str(self.source_frame_ref).strip()
        if not source_frame_ref:
            raise ValueError("source_frame_ref must be non-empty")

        object.__setattr__(self, "values", values)
        object.__setattr__(self, "active_tick", active_tick)
        object.__setattr__(self, "signal_id", signal_id)
        object.__setattr__(self, "source_frame_ref", source_frame_ref)


class ActionTransducer:
    """Convert executable ACTION frames into numeric actuator signals."""

    def __init__(self) -> None:
        self._next_signal_id = 1

    def transduce(self, action_frame: NFPFrame) -> ActuatorSignal:
        if not isinstance(action_frame, NFPFrame):
            raise TypeError("action_frame must be NFPFrame")
        if action_frame.modality != PatternModality.ACTION:
            raise ValueError("action_frame modality must be ACTION")
        if action_frame.origin != PatternOrigin.ACTION_GENERATED:
            raise ValueError("action_frame origin must be ACTION_GENERATED")
        if action_frame.topology != ACTION_MOTOR_TOPOLOGY:
            raise ValueError("action_frame topology must be PatternTopology((2,))")

        signal = ActuatorSignal(
            values=tuple(action_frame.values),
            active_tick=action_frame.active_tick,
            signal_id=self._next_signal_id,
            source_frame_ref=_opaque_frame_ref(action_frame.frame_id),
        )
        self._next_signal_id += 1
        return signal


def _opaque_frame_ref(frame_id: str) -> str:
    digest = hashlib.sha256(str(frame_id).encode("utf-8")).hexdigest()[:16]
    return f"action_frame_ref:{digest}"


def _non_negative_int(value: int, field_name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value
