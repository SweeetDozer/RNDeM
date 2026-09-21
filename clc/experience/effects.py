from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from clc.context.causal_transition import RecentCausalTransition, validate_external_sensory_window
from clc.patterns import PatternModality, PatternTopology
from clc.patterns.similarity import NFPSimilarityResult


@dataclass(frozen=True)
class ObservedEffect:
    """Non-semantic signed change between two sensory endpoint occurrences."""

    effect_id: str
    source_transition_id: str
    modality: PatternModality
    topology: PatternTopology
    delta_values: tuple[float, ...]
    before_endpoint_ref: str
    after_endpoint_ref: str
    action_tick: int
    observation_tick: int

    def __post_init__(self) -> None:
        for field_name in ("effect_id", "source_transition_id", "before_endpoint_ref", "after_endpoint_ref"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        if not isinstance(self.modality, PatternModality):
            raise TypeError("modality must be PatternModality")
        if not isinstance(self.topology, PatternTopology):
            raise TypeError("topology must be PatternTopology")
        values = tuple(float(value) for value in self.delta_values)
        if len(values) != self.topology.size:
            raise ValueError("delta length must equal topology size")
        if any(not math.isfinite(value) for value in values):
            raise ValueError("delta values must be finite")
        if any(value < -1.0 or value > 1.0 for value in values):
            raise ValueError("delta values must be in [-1.0, 1.0]")
        if not isinstance(self.action_tick, int) or isinstance(self.action_tick, bool):
            raise TypeError("action_tick must be an integer")
        if self.action_tick < 0:
            raise ValueError("action_tick must be >= 0")
        if not isinstance(self.observation_tick, int) or isinstance(self.observation_tick, bool):
            raise TypeError("observation_tick must be an integer")
        if self.observation_tick != self.action_tick + 1:
            raise ValueError("observation_tick must equal action_tick + 1")
        object.__setattr__(self, "delta_values", values)


class ObservedEffectExtractor:
    """Pure endpoint-based structural effect extraction."""

    @staticmethod
    def extract(transition: RecentCausalTransition) -> ObservedEffect:
        if not isinstance(transition, RecentCausalTransition):
            raise TypeError("effect extraction requires RecentCausalTransition")
        validate_external_sensory_window(transition.before_sensory_window)
        validate_external_sensory_window(transition.after_sensory_window)
        before = transition.before_sensory_window.frames[-1]
        after = transition.after_sensory_window.frames[-1]
        if before.modality != after.modality:
            raise ValueError("sensory endpoints must share modality")
        if before.topology != after.topology:
            raise ValueError("sensory endpoints must share topology")
        if len(before.values) != len(after.values):
            raise ValueError("sensory endpoints must have equal activation length")
        return ObservedEffect(
            effect_id=_opaque_id("effect", transition.transition_id, before.frame_id, after.frame_id),
            source_transition_id=transition.transition_id,
            modality=before.modality,
            topology=before.topology,
            delta_values=tuple(after_value - before_value for before_value, after_value in zip(before.values, after.values)),
            before_endpoint_ref=_opaque_id("endpoint", before.frame_id),
            after_endpoint_ref=_opaque_id("endpoint", after.frame_id),
            action_tick=transition.action_tick,
            observation_tick=transition.observation_tick,
        )


class ObservedEffectSimilarity:
    """Deterministic signed-delta similarity; this is not NFP similarity."""

    @staticmethod
    def compare(left: ObservedEffect, right: ObservedEffect) -> NFPSimilarityResult:
        if not isinstance(left, ObservedEffect) or not isinstance(right, ObservedEffect):
            raise TypeError("ObservedEffectSimilarity.compare requires ObservedEffect objects")
        if left.modality != right.modality:
            return NFPSimilarityResult(False, None, "different_modality")
        if left.topology != right.topology:
            return NFPSimilarityResult(False, None, "different_topology")
        if len(left.delta_values) != len(right.delta_values):
            return NFPSimilarityResult(False, None, "different_delta_length")
        distance = sum(abs(a - b) for a, b in zip(left.delta_values, right.delta_values))
        score = 1.0 - (distance / len(left.delta_values)) / 2.0
        if score < 0.0 and score > -1e-12:
            score = 0.0
        if score > 1.0 and score < 1.0 + 1e-12:
            score = 1.0
        return NFPSimilarityResult(True, score, None)


def _opaque_id(prefix: str, *parts: str) -> str:
    material = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(material).hexdigest()[:24]}"
