from __future__ import annotations

from clc.actuation import ActuatorSignal
from clc.transduction import VisualFieldSnapshot


class SyntheticClosedLoopVisualWorld:
    """External mutable visual world for isolated closed-loop scenarios."""

    def __init__(
        self,
        shape: tuple[int, int] = (16, 16),
        initial_row: int | None = None,
        initial_column: int | None = None,
        initial_tick: int = 0,
        hidden_debug_description: str | None = None,
    ) -> None:
        self.shape = _validate_shape(shape)
        self.current_tick = _non_negative_int(initial_tick, "initial_tick")
        rows, columns = self.shape
        row = rows // 2 if initial_row is None else initial_row
        column = columns // 2 if initial_column is None else initial_column
        self._row = _validate_coordinate(row, rows, "initial_row")
        self._column = _validate_coordinate(column, columns, "initial_column")
        self.hidden_debug_description = hidden_debug_description
        self._next_snapshot_id = 0

    @property
    def hidden_position(self) -> tuple[int, int]:
        return self._row, self._column

    def snapshot(self) -> VisualFieldSnapshot:
        rows, columns = self.shape
        values = [0.0] * (rows * columns)
        values[(self._row * columns) + self._column] = 1.0
        snapshot = VisualFieldSnapshot(
            shape=self.shape,
            values=tuple(values),
            active_tick=self.current_tick,
            snapshot_id=self._next_snapshot_id,
        )
        self._next_snapshot_id += 1
        return snapshot

    def apply_actuator_signal(self, signal: ActuatorSignal) -> None:
        if not isinstance(signal, ActuatorSignal):
            raise TypeError("signal must be ActuatorSignal")
        if signal.active_tick != self.current_tick:
            raise ValueError("signal active_tick must equal world current_tick")

        drive = signal.values[1] - signal.values[0]
        if drive > 0.0:
            self._column = min(self._column + 1, self.shape[1] - 1)
        elif drive < 0.0:
            self._column = max(self._column - 1, 0)
        self.current_tick += 1
        return None


def _validate_shape(shape: tuple[int, int]) -> tuple[int, int]:
    shape = tuple(shape)
    if len(shape) != 2:
        raise ValueError("shape must have exactly 2 dimensions")
    if any(not isinstance(dimension, int) for dimension in shape):
        raise TypeError("shape dimensions must be integers")
    if any(dimension <= 0 for dimension in shape):
        raise ValueError("shape dimensions must be positive")
    return shape


def _validate_coordinate(value: int, upper_bound: int, field_name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0 or value >= upper_bound:
        raise ValueError(f"{field_name} out of bounds")
    return value


def _non_negative_int(value: int, field_name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value
