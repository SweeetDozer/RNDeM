"""Deterministic visual NFP expectations, independent of legacy label prediction.

A feature is a topology coordinate. Zero at a coordinate is observed absence,
not missing input. Opposing coordinates must be supplied explicitly: a different
pattern alone never establishes contradiction or object identity. Windows are
compared by their last frame (the current slice), not by temporal alignment.
"""
from dataclasses import dataclass, replace

from clc.context.causal_transition import validate_active_tick, validate_external_sensory_window
from clc.context.short_memory import ShortMemory
from clc.patterns import NFPWindow, NFPFrameSimilarity


@dataclass(frozen=True)
class EchoMatch:
    expectation_id: str
    tick: int
    outcome: str
    observation_id: str | None
    source_window_id: str
    history_transition_id: str | None
    possible_continuation: bool = False
    identity_confirmed: bool = False
    similarity: float | None = None


@dataclass(frozen=True)
class Expectation:
    expectation_id: str
    source: NFPWindow
    expected_coordinates: tuple[int, ...]
    opposing_coordinates: tuple[int, ...]
    expires_at: int
    history_transition_id: str | None = None
    state: str = 'open'
    last_match: EchoMatch | None = None


class EchoExpectations:
    """In-process bounded registry. Deadlines are inclusive and never renewed.

    Explicit creation avoids silently predicting persistence for every sensor
    sample. The caller supplies a raw source or a retained ShortMemory transition.
    No access to hidden world state, labels, weights or permanent memory.
    """

    def __init__(self, *, max_entries: int = 32, active_threshold: float = .5,
                 continuation_threshold: float = .8) -> None:
        validate_active_tick(max_entries)
        if max_entries == 0:
            raise ValueError('max_entries must be positive')
        if not 0 < active_threshold <= 1 or not 0 <= continuation_threshold <= 1:
            raise ValueError('invalid thresholds')
        self.max_entries = max_entries
        self.active_threshold = active_threshold
        self.continuation_threshold = continuation_threshold
        self._entries: tuple[Expectation, ...] = ()
        self._tick = -1
        self._counter = 0

    def snapshot(self) -> tuple[Expectation, ...]:
        return self._entries

    def expect(self, source: NFPWindow, *, expected_coordinates: tuple[int, ...],
               ttl: int, opposing_coordinates: tuple[int, ...] = ()) -> Expectation:
        validate_external_sensory_window(source)
        validate_active_tick(ttl)
        if ttl == 0 or source.end_tick < self._tick:
            raise ValueError('positive lifetime and non-stale source required')
        expected = tuple(expected_coordinates)
        opposing = tuple(opposing_coordinates)
        if not expected or set(expected) & set(opposing):
            raise ValueError('expected coordinates required; opposing coordinates must be disjoint')
        for coordinate in expected + opposing:
            if type(coordinate) is not int or not 0 <= coordinate < source.topology.size:
                raise ValueError('coordinate outside topology')
        if len(self._entries) >= self.max_entries:
            raise ValueError('expectation capacity exhausted; advance time to expire entries')
        self._counter += 1
        entry = Expectation(f'echo:{self._counter}', source, expected, opposing,
                            source.end_tick + ttl)
        self._entries += (entry,)
        return entry

    def expect_transition(self, memory: ShortMemory, transition_id: str, **spec) -> Expectation:
        """Read only a currently retained causal transition, never query old history."""
        transition = next((t for t in memory.snapshot() if t.transition_id == transition_id), None)
        if transition is None:
            raise ValueError('transition is not retained in ShortMemory')
        entry = self.expect(transition.after_sensory_window, **spec)
        entry = replace(entry, history_transition_id=transition.transition_id)
        self._entries = self._entries[:-1] + (entry,)
        return entry

    def advance(self, tick: int, observation: NFPWindow | None) -> tuple[EchoMatch, ...]:
        validate_active_tick(tick)
        if tick <= self._tick:
            raise ValueError('Echo ticks must strictly increase')
        if observation is not None:
            validate_external_sensory_window(observation)
            if observation.end_tick != tick:
                raise ValueError('observation must be fresh')
        results = []
        retained = []
        for entry in self._entries:
            # A newly created expectation cannot be judged by its own source.
            if tick <= entry.source.end_tick:
                retained.append(entry)
                continue
            score = None
            continuation = False
            if tick > entry.expires_at:
                outcome = 'expired'
            elif entry.state == 'contradicted':
                retained.append(entry)
                continue
            elif observation is None:
                outcome = 'no_data'
            else:
                comparison = NFPFrameSimilarity.compare(entry.source.frames[-1], observation.frames[-1])
                score = comparison.score
                if not comparison.comparable:
                    outcome = 'incomparable'
                else:
                    values = observation.frames[-1].values
                    if any(values[i] >= self.active_threshold for i in entry.opposing_coordinates):
                        outcome = 'contradiction'
                    elif all(values[i] >= self.active_threshold for i in entry.expected_coordinates):
                        outcome = 'support'
                        continuation = score >= self.continuation_threshold
                    elif all(values[i] == 0 for i in entry.expected_coordinates):
                        outcome = 'observed_absence'
                    else:
                        outcome = 'inconclusive'
            match = EchoMatch(entry.expectation_id, tick, outcome,
                              observation.window_id if observation is not None else None,
                              entry.source.window_id, entry.history_transition_id,
                              continuation, False, score)
            results.append(match)
            if outcome != 'expired':
                state = 'contradicted' if outcome == 'contradiction' else entry.state
                if outcome == 'support':
                    state = 'supported'
                retained.append(replace(entry, state=state, last_match=match))
        self._entries = tuple(retained)
        self._tick = tick
        return tuple(results)
