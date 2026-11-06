"""One bounded, cooperative structural NFP comparison, never sensory evidence."""
from dataclasses import dataclass, replace
from uuid import uuid4

from clc.patterns import NFPWindow, PatternOrigin
from clc.runtime.heart import non_negative_integer


@dataclass(frozen=True)
class WorkLimits:
    cells_per_tick: int = 64
    max_cells: int = 4096

    def __post_init__(self):
        for name in ('cells_per_tick', 'max_cells'):
            if not non_negative_integer(getattr(self, name), name):
                raise ValueError(f'{name} must be positive')


def validate_comparison(left: NFPWindow, right: NFPWindow, limits: WorkLimits,
                        current_tick: int) -> int:
    """Shared admission validation; return coordinates retained by both inputs."""
    non_negative_integer(current_tick, "current_tick")
    if not isinstance(left, NFPWindow) or not isinstance(right, NFPWindow):
        raise TypeError('comparison requires native NFP windows')
    if (left.modality, left.topology, left.length) != (right.modality, right.topology, right.length):
        raise ValueError('incompatible NFP windows')
    if max(left.end_tick, right.end_tick) > current_tick:
        raise ValueError('future NFP input')
    if left.length * left.topology.size > limits.max_cells:
        raise ValueError('input exceeds cell budget')
    return 2 * left.length * left.topology.size


@dataclass(frozen=True)
class FrameSourceDescriptor:
    frame_id: str
    origin: PatternOrigin
    active_tick: int
    provenance_ref: str | None


@dataclass(frozen=True)
class WindowSourceDescriptor:
    window_id: str
    provenance_ref: str | None
    frames: tuple[FrameSourceDescriptor, ...]

    @classmethod
    def capture(cls, source: NFPWindow) -> "WindowSourceDescriptor":
        return cls(source.window_id, source.provenance_ref, tuple(
            FrameSourceDescriptor(frame.frame_id, frame.origin, frame.active_tick,
                                  frame.provenance_ref)
            for frame in source.frames
        ))


@dataclass(frozen=True)
class InternalSimilarity:
    result_id: str
    process_id: str
    source_window_ids: tuple[str, str]
    completed_tick: int
    score: float
    origin: PatternOrigin = PatternOrigin.INTERNAL_STATE
    # Ordered (left, right); None preserves the earlier constructor signature.
    source_descriptors: tuple[WindowSourceDescriptor, WindowSourceDescriptor] | None = None


@dataclass(frozen=True)
class WorkSnapshot:
    process_id: str
    state: str
    source_window_ids: tuple[str, str]
    processed_cells: int = 0
    distance: float = 0.0
    result: InternalSimilarity | None = None
    diagnostic: str = ''
    source_descriptors: tuple[WindowSourceDescriptor, WindowSourceDescriptor] | None = None


class MultiTickComparison:
    """Single retained slot, including terminal status. Owner serializes calls.

    Explicit submit authorizes only a structural comparison. Terminal slot must
    be released before reuse. No callbacks, world, writers, or action dependencies.
    """

    def __init__(self, limits: WorkLimits):
        self.limits = limits
        self._snapshot = None
        self._inputs = None
        self._last_tick = -1

    def snapshot(self) -> WorkSnapshot | None:
        return self._snapshot

    def submit(self, left: NFPWindow, right: NFPWindow, *, current_tick: int) -> WorkSnapshot:
        non_negative_integer(current_tick, 'current_tick')
        if self._snapshot is not None:
            raise ValueError('single retained process slot is occupied; release terminal process')
        validate_comparison(left, right, self.limits, current_tick)
        sources = (WindowSourceDescriptor.capture(left), WindowSourceDescriptor.capture(right))
        self._inputs = (left, right)
        self._snapshot = WorkSnapshot(str(uuid4()), 'queued', (left.window_id, right.window_id),
                                      source_descriptors=sources)
        return self._snapshot

    def advance(self, tick: int) -> WorkSnapshot | None:
        non_negative_integer(tick, 'tick')
        if tick <= self._last_tick:
            raise ValueError('internal work ticks must strictly increase; no replay')
        self._last_tick = tick
        s = self._snapshot
        if s is None or s.state not in ('queued', 'running'):
            return s
        try:
            left, right = self._inputs
            size = left.topology.size
            total = left.length * size
            end = min(total, s.processed_cells + self.limits.cells_per_tick)
            distance = s.distance
            for cell in range(s.processed_cells, end):
                frame, coordinate = divmod(cell, size)
                distance += abs(left.frames[frame].values[coordinate] - right.frames[frame].values[coordinate])
            result = None
            state = 'running'
            if end == total:
                state = 'completed'
                result = InternalSimilarity(str(uuid4()), s.process_id, s.source_window_ids,
                                            tick, max(0., min(1., 1. - distance / total)),
                                            source_descriptors=s.source_descriptors)
            self._snapshot = replace(s, state=state, processed_cells=end, distance=distance, result=result)
            if result is not None:
                self._inputs = None
        except Exception as error:
            self._inputs = None
            self._snapshot = replace(s, state='failed', diagnostic=type(error).__name__)
        return self._snapshot

    def cancel(self) -> WorkSnapshot | None:
        if self._snapshot is not None and self._snapshot.state in ('queued', 'running'):
            self._snapshot = replace(self._snapshot, state='cancelled')
        self._inputs = None
        return self._snapshot

    def release(self) -> None:
        if self._snapshot is not None and self._snapshot.state in ('queued', 'running'):
            raise ValueError('cancel active process before release')
        self._snapshot = None
        self._inputs = None
