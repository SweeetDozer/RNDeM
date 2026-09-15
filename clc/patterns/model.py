from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class PatternModality(str, Enum):
    """Activation domain for a natural frame."""

    VISUAL = "visual"
    AUDIO = "audio"
    INTERNAL = "internal"
    PAIN_DAMAGE = "pain_damage"
    REWARD_SUCCESS = "reward_success"
    ACTION = "action"


class PatternOrigin(str, Enum):
    """How an activation frame entered the substrate."""

    EXTERNAL_SENSORY = "external_sensory"
    INTERNAL_STATE = "internal_state"
    INTERNAL_REACTIVATION = "internal_reactivation"
    ACTION_GENERATED = "action_generated"


@dataclass(frozen=True)
class PatternTopology:
    """Small immutable activation topology descriptor."""

    shape: tuple[int, ...]

    def __post_init__(self) -> None:
        shape = tuple(self.shape)
        if not shape:
            raise ValueError("shape must not be empty")
        if any(not isinstance(dimension, int) for dimension in shape):
            raise TypeError("shape dimensions must be integers")
        if any(dimension <= 0 for dimension in shape):
            raise ValueError("shape dimensions must be positive")
        object.__setattr__(self, "shape", shape)

    @property
    def size(self) -> int:
        return math.prod(self.shape)


@dataclass(frozen=True)
class NFPFrame:
    """One modality-specific activation state at one active tick."""

    frame_id: str
    modality: PatternModality
    origin: PatternOrigin
    topology: PatternTopology
    values: tuple[float, ...]
    active_tick: int
    provenance_ref: str | None = None
    debug_name: str | None = None

    def __post_init__(self) -> None:
        frame_id = str(self.frame_id).strip()
        if not frame_id:
            raise ValueError("frame_id must be non-empty")
        if not isinstance(self.modality, PatternModality):
            raise TypeError("modality must be PatternModality")
        if not isinstance(self.origin, PatternOrigin):
            raise TypeError("origin must be PatternOrigin")
        if not isinstance(self.topology, PatternTopology):
            raise TypeError("topology must be PatternTopology")
        active_tick = _non_negative_int(self.active_tick, "active_tick")
        values = tuple(float(value) for value in self.values)
        if len(values) != self.topology.size:
            raise ValueError("values length must equal topology size")
        for value in values:
            if not math.isfinite(value):
                raise ValueError("activation values must be finite")
            if value < 0.0 or value > 1.0:
                raise ValueError("activation values must be in [0.0, 1.0]")
        provenance_ref = None if self.provenance_ref is None else str(self.provenance_ref).strip()
        debug_name = None if self.debug_name is None else str(self.debug_name)
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "active_tick", active_tick)
        object.__setattr__(self, "provenance_ref", provenance_ref or None)
        object.__setattr__(self, "debug_name", debug_name)


@dataclass(frozen=True)
class PatternMoment:
    """Optional multimodal same-tick grouping; this is not an NFP frame."""

    active_tick: int
    frames: tuple[NFPFrame, ...]

    def __post_init__(self) -> None:
        active_tick = _non_negative_int(self.active_tick, "active_tick")
        frames = tuple(self.frames)
        seen_ids: set[str] = set()
        for frame in frames:
            if not isinstance(frame, NFPFrame):
                raise TypeError("frames must contain NFPFrame objects")
            if frame.active_tick != active_tick:
                raise ValueError("frame active_tick must match moment active_tick")
            if frame.frame_id in seen_ids:
                raise ValueError("duplicate frame_id values are not allowed in one moment")
            seen_ids.add(frame.frame_id)
        object.__setattr__(self, "active_tick", active_tick)
        object.__setattr__(self, "frames", frames)


@dataclass(frozen=True)
class NFPWindow:
    """Short ordered temporal group of compatible NFP frames."""

    window_id: str
    frames: tuple[NFPFrame, ...]
    provenance_ref: str | None = None
    debug_name: str | None = None

    def __post_init__(self) -> None:
        window_id = str(self.window_id).strip()
        if not window_id:
            raise ValueError("window_id must be non-empty")
        frames = tuple(self.frames)
        if not frames:
            raise ValueError("NFPWindow requires at least one frame")
        seen_ids: set[str] = set()
        previous_tick: int | None = None
        modality = frames[0].modality
        topology = frames[0].topology
        for frame in frames:
            if not isinstance(frame, NFPFrame):
                raise TypeError("frames must contain NFPFrame objects")
            if frame.modality != modality:
                raise ValueError("NFPWindow frames must share modality")
            if frame.topology != topology:
                raise ValueError("NFPWindow frames must share topology")
            if previous_tick is not None and frame.active_tick <= previous_tick:
                raise ValueError("NFPWindow frame ticks must be strictly increasing")
            if frame.frame_id in seen_ids:
                raise ValueError("duplicate frame_id values are not allowed in one window")
            seen_ids.add(frame.frame_id)
            previous_tick = frame.active_tick
        provenance_ref = None if self.provenance_ref is None else str(self.provenance_ref).strip()
        debug_name = None if self.debug_name is None else str(self.debug_name)
        object.__setattr__(self, "window_id", window_id)
        object.__setattr__(self, "frames", frames)
        object.__setattr__(self, "provenance_ref", provenance_ref or None)
        object.__setattr__(self, "debug_name", debug_name)

    @property
    def modality(self) -> PatternModality:
        return self.frames[0].modality

    @property
    def topology(self) -> PatternTopology:
        return self.frames[0].topology

    @property
    def start_tick(self) -> int:
        return self.frames[0].active_tick

    @property
    def end_tick(self) -> int:
        return self.frames[-1].active_tick

    @property
    def length(self) -> int:
        return len(self.frames)


@dataclass(frozen=True)
class NFPSequence:
    """Longer ordered temporal structure made from NFP windows."""

    sequence_id: str
    windows: tuple[NFPWindow, ...]
    provenance_ref: str | None = None
    debug_name: str | None = None

    def __post_init__(self) -> None:
        sequence_id = str(self.sequence_id).strip()
        if not sequence_id:
            raise ValueError("sequence_id must be non-empty")
        windows = tuple(self.windows)
        if not windows:
            raise ValueError("NFPSequence requires at least one window")
        modality = windows[0].modality
        topology = windows[0].topology
        previous_start: int | None = None
        for window in windows:
            if not isinstance(window, NFPWindow):
                raise TypeError("windows must contain NFPWindow objects")
            if window.modality != modality:
                raise ValueError("NFPSequence windows must share modality")
            if window.topology != topology:
                raise ValueError("NFPSequence windows must share topology")
            if previous_start is not None and window.start_tick < previous_start:
                raise ValueError("NFPSequence windows must be ordered by temporal position")
            previous_start = window.start_tick
        provenance_ref = None if self.provenance_ref is None else str(self.provenance_ref).strip()
        debug_name = None if self.debug_name is None else str(self.debug_name)
        object.__setattr__(self, "sequence_id", sequence_id)
        object.__setattr__(self, "windows", windows)
        object.__setattr__(self, "provenance_ref", provenance_ref or None)
        object.__setattr__(self, "debug_name", debug_name)

    @property
    def modality(self) -> PatternModality:
        return self.windows[0].modality

    @property
    def topology(self) -> PatternTopology:
        return self.windows[0].topology

    @property
    def start_tick(self) -> int:
        return min(window.start_tick for window in self.windows)

    @property
    def end_tick(self) -> int:
        return max(window.end_tick for window in self.windows)

    @property
    def window_count(self) -> int:
        return len(self.windows)


def _non_negative_int(value: int, field_name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value
