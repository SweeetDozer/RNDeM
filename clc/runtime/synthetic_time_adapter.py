"""Explicit one-transition contract for an exclusively owned synthetic world."""
from __future__ import annotations


class SyntheticTimeAdapter:
    def __init__(self, world: object) -> None:
        self.world = world
        self._open_tick: int | None = None
        self.blocked = False

    def open(self, tick: int) -> None:
        if self.blocked or self._open_tick is not None or self.world.current_tick != tick:
            self.blocked = True
            raise RuntimeError("Heart/world boundary mismatch; reconciliation required")
        self._open_tick = tick

    def block(self) -> None:
        self.blocked = True

    def finish(self, *, actuator_advanced: bool) -> str:
        if self.blocked or self._open_tick is None:
            raise RuntimeError("no safe open synthetic transition")
        tick = self._open_tick
        try:
            expected = tick + 1 if actuator_advanced else tick
            if self.world.current_tick != expected:
                raise RuntimeError("unexpected world advancement; no repair or retry")
            if not actuator_advanced:
                self.world.advance_idle(expected_tick=tick)
            if self.world.current_tick != tick + 1:
                raise RuntimeError("world must advance exactly once")
        except BaseException:
            self.block()
            raise
        self._open_tick = None
        return "actuator" if actuator_advanced else "idle"
