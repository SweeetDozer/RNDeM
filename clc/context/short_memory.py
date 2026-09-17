from __future__ import annotations

from clc.context.causal_transition import RecentCausalTransition, validate_active_tick


class ShortMemory:
    """Bounded recent raw transitions, retained only in process memory."""

    def __init__(self, max_entries: int, max_age_ticks: int) -> None:
        validate_active_tick(max_entries)
        validate_active_tick(max_age_ticks)
        if max_entries == 0:
            raise ValueError("max_entries must be > 0")
        self._max_entries = max_entries
        self._max_age_ticks = max_age_ticks
        self._entries: tuple[RecentCausalTransition, ...] = ()
        self._current_tick = 0
        self._last_observation_tick = -1

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def max_age_ticks(self) -> int:
        return self._max_age_ticks

    def snapshot(self) -> tuple[RecentCausalTransition, ...]:
        return self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def remember(self, transition: RecentCausalTransition, *, current_tick: int) -> None:
        if not isinstance(transition, RecentCausalTransition):
            raise TypeError("ShortMemory accepts only RecentCausalTransition")
        self._validate_tick(current_tick)
        if current_tick < transition.observation_tick:
            raise ValueError("cannot remember a future observation")
        if transition.observation_tick < self._last_observation_tick:
            raise ValueError("transitions must arrive in observation order")
        if any(entry.transition_id == transition.transition_id for entry in self._entries):
            raise ValueError("transition_id is already retained")
        entries = self._entries + (transition,)
        self._entries = self._retained(entries, current_tick)
        self._current_tick = current_tick
        self._last_observation_tick = transition.observation_tick

    def prune(self, current_tick: int) -> None:
        self._validate_tick(current_tick)
        self._entries = self._retained(self._entries, current_tick)
        self._current_tick = current_tick

    def _validate_tick(self, current_tick: int) -> None:
        validate_active_tick(current_tick)
        if current_tick < self._current_tick:
            raise ValueError("active time must not go backwards")

    def _retained(
        self, entries: tuple[RecentCausalTransition, ...], current_tick: int,
    ) -> tuple[RecentCausalTransition, ...]:
        return tuple(
            entry for entry in entries
            if current_tick - entry.observation_tick <= self._max_age_ticks
        )[-self._max_entries:]
