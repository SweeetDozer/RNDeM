from __future__ import annotations

from collections.abc import Iterable
import math

from clc.transduction import VisualFieldSnapshot


class SyntheticVisualWorld:
    """External mutable numeric visual field for scenario/test support."""

    def __init__(
        self,
        shape: tuple[int, int] = (16, 16),
        hidden_debug_description: str | None = None,
    ) -> None:
        self.shape = _validate_shape(shape)
        self.hidden_debug_description = hidden_debug_description
        self._field = [0.0] * (self.shape[0] * self.shape[1])
        self._next_snapshot_id = 0

    def clear(self, value: float = 0.0) -> None:
        normalized = _validate_value(value)
        self._field = [normalized] * len(self._field)

    def set_activation(self, row: int, column: int, value: float) -> None:
        if not isinstance(row, int) or not isinstance(column, int):
            raise TypeError("row and column must be integers")
        rows, columns = self.shape
        if row < 0 or row >= rows or column < 0 or column >= columns:
            raise ValueError("activation coordinate out of bounds")
        self._field[(row * columns) + column] = _validate_value(value)

    def set_field(self, values: Iterable[float]) -> None:
        field = tuple(_validate_value(value) for value in values)
        if len(field) != len(self._field):
            raise ValueError("field values length must equal rows * columns")
        self._field = list(field)

    def snapshot(self, active_tick: int) -> VisualFieldSnapshot:
        snapshot = VisualFieldSnapshot(
            shape=self.shape,
            values=tuple(self._field),
            active_tick=active_tick,
            snapshot_id=self._next_snapshot_id,
        )
        self._next_snapshot_id += 1
        return snapshot


def _validate_shape(shape: tuple[int, int]) -> tuple[int, int]:
    shape = tuple(shape)
    if len(shape) != 2:
        raise ValueError("shape must have exactly 2 dimensions")
    if any(not isinstance(dimension, int) for dimension in shape):
        raise TypeError("shape dimensions must be integers")
    if any(dimension <= 0 for dimension in shape):
        raise ValueError("shape dimensions must be positive")
    return shape


def _validate_value(value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError("field values must be finite")
    if normalized < 0.0 or normalized > 1.0:
        raise ValueError("field values must be in [0.0, 1.0]")
    return normalized
