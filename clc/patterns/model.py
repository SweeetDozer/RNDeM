from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class PatternModality(str, Enum):
    """Activation domain for a pattern occurrence."""

    VISUAL = "visual"
    AUDIO = "audio"
    INTERNAL = "internal"
    PAIN_DAMAGE = "pain_damage"
    REWARD_SUCCESS = "reward_success"
    ACTION = "action"


class PatternOrigin(str, Enum):
    """How an activation pattern entered the substrate."""

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
class ActivationPattern:
    """Immutable occurrence-level activation snapshot."""

    pattern_id: str
    modality: PatternModality
    origin: PatternOrigin
    topology: PatternTopology
    values: tuple[float, ...]
    active_tick: int
    provenance_ref: str | None = None
    debug_name: str | None = None

    def __post_init__(self) -> None:
        pattern_id = str(self.pattern_id).strip()
        if not pattern_id:
            raise ValueError("pattern_id must be non-empty")
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
        object.__setattr__(self, "pattern_id", pattern_id)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "active_tick", active_tick)
        object.__setattr__(self, "provenance_ref", provenance_ref or None)
        object.__setattr__(self, "debug_name", debug_name)


@dataclass(frozen=True)
class PatternFrame:
    """Temporal grouping of distinct pattern occurrences at one active tick."""

    active_tick: int
    patterns: tuple[ActivationPattern, ...]

    def __post_init__(self) -> None:
        active_tick = _non_negative_int(self.active_tick, "active_tick")
        patterns = tuple(self.patterns)
        seen_ids: set[str] = set()
        for pattern in patterns:
            if not isinstance(pattern, ActivationPattern):
                raise TypeError("patterns must contain ActivationPattern objects")
            if pattern.active_tick != active_tick:
                raise ValueError("pattern active_tick must match frame active_tick")
            if pattern.pattern_id in seen_ids:
                raise ValueError("duplicate pattern_id values are not allowed in one frame")
            seen_ids.add(pattern.pattern_id)
        object.__setattr__(self, "active_tick", active_tick)
        object.__setattr__(self, "patterns", patterns)


@dataclass(frozen=True)
class PatternTrace:
    """Bounded ordered in-memory trace of pattern frames."""

    trace_id: str
    frames: tuple[PatternFrame, ...]
    provenance_ref: str | None = None

    def __post_init__(self) -> None:
        trace_id = str(self.trace_id).strip()
        if not trace_id:
            raise ValueError("trace_id must be non-empty")
        frames = tuple(self.frames)
        previous_tick: int | None = None
        for frame in frames:
            if not isinstance(frame, PatternFrame):
                raise TypeError("frames must contain PatternFrame objects")
            if previous_tick is not None and frame.active_tick <= previous_tick:
                raise ValueError("frame ticks must be strictly increasing")
            previous_tick = frame.active_tick
        provenance_ref = None if self.provenance_ref is None else str(self.provenance_ref).strip()
        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "frames", frames)
        object.__setattr__(self, "provenance_ref", provenance_ref or None)

    @property
    def start_tick(self) -> int | None:
        return self.frames[0].active_tick if self.frames else None

    @property
    def end_tick(self) -> int | None:
        return self.frames[-1].active_tick if self.frames else None


def _non_negative_int(value: int, field_name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value
