from __future__ import annotations

from dataclasses import dataclass

from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin


def validate_active_tick(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("active tick must be an integer")
    if value < 0:
        raise ValueError("active tick must be >= 0")


def validate_external_sensory_window(window: NFPWindow) -> None:
    if not isinstance(window, NFPWindow):
        raise TypeError("window must be NFPWindow")
    if window.modality != PatternModality.VISUAL:
        raise ValueError("window modality must be VISUAL")
    if any(frame.origin != PatternOrigin.EXTERNAL_SENSORY for frame in window.frames):
        raise ValueError("all window frames must be EXTERNAL_SENSORY")
    for frame in window.frames:
        validate_active_tick(frame.active_tick)


def validate_action_frame(frame: NFPFrame) -> None:
    if not isinstance(frame, NFPFrame):
        raise TypeError("action must be NFPFrame")
    if frame.modality != PatternModality.ACTION:
        raise ValueError("action modality must be ACTION")
    if frame.origin != PatternOrigin.ACTION_GENERATED:
        raise ValueError("action origin must be ACTION_GENERATED")
    validate_active_tick(frame.active_tick)


@dataclass(frozen=True)
class PendingCausalTransition:
    """Unresolved immediate temporal relation in active context."""

    transition_id: str
    before_sensory_window: NFPWindow
    action_frame: NFPFrame
    action_tick: int
    expected_observation_tick: int

    def __post_init__(self) -> None:
        if not isinstance(self.transition_id, str):
            raise TypeError("transition_id must be a string")
        if not self.transition_id.strip():
            raise ValueError("transition_id must be non-empty")
        validate_external_sensory_window(self.before_sensory_window)
        validate_action_frame(self.action_frame)
        validate_active_tick(self.action_tick)
        validate_active_tick(self.expected_observation_tick)
        if self.action_frame.active_tick != self.action_tick:
            raise ValueError("action_tick must equal action frame tick")
        if self.expected_observation_tick != self.action_tick + 1:
            raise ValueError("expected observation tick must equal action_tick + 1")
        if self.before_sensory_window.end_tick > self.action_tick:
            raise ValueError("before window must not end after the action")


@dataclass(frozen=True)
class RecentCausalTransition:
    """Observed before/action/after; does not assert exclusive causation."""

    transition_id: str
    before_sensory_window: NFPWindow
    action_frame: NFPFrame
    after_sensory_window: NFPWindow
    action_tick: int
    observation_tick: int

    def __post_init__(self) -> None:
        PendingCausalTransition(
            self.transition_id, self.before_sensory_window, self.action_frame,
            self.action_tick, self.observation_tick,
        )
        validate_external_sensory_window(self.after_sensory_window)
        if self.after_sensory_window.end_tick != self.observation_tick:
            raise ValueError("observation_tick must equal after window end_tick")
        if self.before_sensory_window.topology != self.after_sensory_window.topology:
            raise ValueError("before and after visual topologies must match")
