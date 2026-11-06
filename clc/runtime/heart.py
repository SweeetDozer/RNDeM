"""A bounded serialized pulse source; no sensor, action or memory authority."""
from __future__ import annotations

import math
import time
from collections.abc import Callable
from enum import Enum


class HeartState(str, Enum):
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


def non_negative_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


class Heart:
    """Owns the next tick. One successful callback consumes one pulse.

    Lifecycle calls are serialized, including calls made from a pulse callback.
    Pause/stop prohibit the next pulse; a current callback finishes at its safe
    boundary. Exceptions latch STOPPED before propagating. Restart is unsupported.
    """

    def __init__(self, *, max_ticks: int, initial_tick: int = 0) -> None:
        self.max_ticks = non_negative_integer(max_ticks, "max_ticks")
        if not self.max_ticks:
            raise ValueError("max_ticks must be positive")
        self._tick = non_negative_integer(initial_tick, "initial_tick")
        self._issued = 0
        self._state = HeartState.READY
        self._inside_step = False
        self._boundary_request: tuple[HeartState, str] | None = None
        self.diagnostic = "ready"

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def state(self) -> HeartState:
        return self._state

    @property
    def admission_open(self) -> bool:
        return self.state is HeartState.RUNNING and self._boundary_request is None

    def start(self) -> None:
        if self.state is HeartState.READY:
            self._state = HeartState.RUNNING
            self.diagnostic = "running"

    def pause(self) -> None:
        if self.state is HeartState.RUNNING:
            if self._inside_step:
                if self._boundary_request is None:
                    self._boundary_request = (HeartState.PAUSED, "paused")
            else:
                self._state = HeartState.PAUSED
                self.diagnostic = "paused"

    def resume(self) -> None:
        if self.state is HeartState.PAUSED:
            self._state = HeartState.RUNNING
            self.diagnostic = "running"

    def stop(self, reason: str = "stopped") -> None:
        if self._inside_step:
            self._boundary_request = (HeartState.STOPPED, reason)
        else:
            self._state = HeartState.STOPPED
            self.diagnostic = reason

    def step(self, pulse: Callable[[int], object]) -> bool:
        if self._inside_step:
            raise RuntimeError("reentrant Heart stepping is forbidden")
        if self.state is not HeartState.RUNNING:
            return False
        self._inside_step = True
        try:
            pulse(self.tick)
            self._tick += 1
            self._issued += 1
            if self._issued == self.max_ticks and (
                self._boundary_request is None
                or self._boundary_request[0] is not HeartState.STOPPED
            ):
                self.stop("tick_budget_exhausted")
            return True
        except BaseException:
            self.stop("pulse_failed; restart_forbidden")
            raise
        finally:
            self._inside_step = False
            if self._boundary_request is not None:
                self._state, self.diagnostic = self._boundary_request
                self._boundary_request = None

    def run(
        self, pulse: Callable[[int], object], *, paced: bool = False,
        interval: float = 0.01, clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval must be finite and positive")
        self.start()
        try:
            # A fresh pacing origin on resume: no catch-up ticks for paused time.
            deadline = clock() if paced else 0.0
            while self.state is HeartState.RUNNING:
                if paced:
                    delay = deadline - clock()
                    while delay > 0 and self.state is HeartState.RUNNING:
                        sleep(min(delay, 0.05))
                        delay = deadline - clock()
                    if self.state is not HeartState.RUNNING:
                        break
                if not self.step(pulse):
                    break
                if paced:
                    deadline = clock() + interval
        except BaseException:
            self.stop("paced_or_pulse_failure; restart_forbidden")
            raise
