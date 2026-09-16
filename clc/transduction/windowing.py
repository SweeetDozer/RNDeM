from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology


@dataclass
class NFPWindowAssembler:
    """Non-semantic sliding assembler for external sensory NFP frames."""

    window_size: int
    _frames: deque[NFPFrame] = field(init=False, repr=False)
    _modality: PatternModality | None = field(default=None, init=False, repr=False)
    _topology: PatternTopology | None = field(default=None, init=False, repr=False)
    _last_tick: int | None = field(default=None, init=False, repr=False)
    _seen_frame_ids: set[str] = field(default_factory=set, init=False, repr=False)
    _next_window_id: int = field(default=1, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.window_size, int):
            raise TypeError("window_size must be an integer")
        if self.window_size <= 0:
            raise ValueError("window_size must be > 0")
        self._frames = deque(maxlen=self.window_size)

    def push(self, frame: NFPFrame) -> NFPWindow | None:
        if not isinstance(frame, NFPFrame):
            raise TypeError("frame must be NFPFrame")
        if frame.origin != PatternOrigin.EXTERNAL_SENSORY:
            raise ValueError("sensory windows accept EXTERNAL_SENSORY frames only")
        if self._modality is None:
            self._modality = frame.modality
            self._topology = frame.topology
        if frame.modality != self._modality:
            raise ValueError("all sensory window frames must share modality")
        if frame.topology != self._topology:
            raise ValueError("all sensory window frames must share topology")
        if frame.frame_id in self._seen_frame_ids:
            raise ValueError("duplicate frame_id values are not allowed")
        if self._last_tick is not None and frame.active_tick <= self._last_tick:
            raise ValueError("frame ticks must be strictly increasing")

        self._frames.append(frame)
        self._seen_frame_ids.add(frame.frame_id)
        self._last_tick = frame.active_tick

        if len(self._frames) < self.window_size:
            return None
        window = NFPWindow(
            window_id=f"nfp_window:{self._next_window_id:06d}",
            frames=tuple(self._frames),
            provenance_ref=None,
            debug_name=None,
        )
        self._next_window_id += 1
        return window
