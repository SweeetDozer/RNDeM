from __future__ import annotations

import hashlib
from dataclasses import dataclass

from clc.context.causal_transition import (
    RecentCausalTransition,
    validate_action_frame,
    validate_external_sensory_window,
)
from clc.experience.effects import ObservedEffect, ObservedEffectExtractor, ObservedEffectSimilarity
from clc.patterns import NFPFrame, NFPWindow
from clc.patterns.similarity import NFPFrameSimilarity, NFPWindowSimilarity


@dataclass(frozen=True)
class ExperienceEvidence:
    """One raw observed occurrence, without operational evaluation."""

    evidence_id: str
    source_transition_id: str
    context_window: NFPWindow
    action_frame: NFPFrame
    observed_effect: ObservedEffect
    action_tick: int
    observation_tick: int

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ValueError("evidence_id must be a non-empty string")
        if not isinstance(self.source_transition_id, str) or not self.source_transition_id.strip():
            raise ValueError("source_transition_id must be a non-empty string")
        validate_external_sensory_window(self.context_window)
        validate_action_frame(self.action_frame)
        if not isinstance(self.observed_effect, ObservedEffect):
            raise TypeError("observed_effect must be ObservedEffect")
        if self.observed_effect.source_transition_id != self.source_transition_id:
            raise ValueError("effect and evidence must share source transition")
        if self.context_window.modality != self.observed_effect.modality:
            raise ValueError("context and effect must share modality")
        if self.context_window.topology != self.observed_effect.topology:
            raise ValueError("context and effect must share topology")
        if self.action_tick != self.action_frame.active_tick:
            raise ValueError("action_tick must equal action frame tick")
        if self.action_tick != self.observed_effect.action_tick:
            raise ValueError("action_tick must equal effect action tick")
        if self.observation_tick != self.observed_effect.observation_tick:
            raise ValueError("observation_tick must equal effect observation tick")


class ExperienceEvidenceFactory:
    """Pure RecentCausalTransition to occurrence-evidence boundary."""

    @staticmethod
    def build(transition: RecentCausalTransition) -> ExperienceEvidence:
        if not isinstance(transition, RecentCausalTransition):
            raise TypeError("evidence creation requires RecentCausalTransition")
        effect = ObservedEffectExtractor.extract(transition)
        material = f"{transition.transition_id}\x1f{effect.effect_id}".encode("utf-8")
        return ExperienceEvidence(
            evidence_id=f"evidence:{hashlib.sha256(material).hexdigest()[:24]}",
            source_transition_id=transition.transition_id,
            context_window=transition.before_sensory_window,
            action_frame=transition.action_frame,
            observed_effect=effect,
            action_tick=transition.action_tick,
            observation_tick=transition.observation_tick,
        )


@dataclass(frozen=True)
class ExperienceEvidenceComparison:
    context_comparable: bool
    context_similarity: float | None
    action_comparable: bool
    action_similarity: float | None
    effect_comparable: bool
    effect_similarity: float | None

    @classmethod
    def compare(cls, left: ExperienceEvidence, right: ExperienceEvidence) -> ExperienceEvidenceComparison:
        if not isinstance(left, ExperienceEvidence) or not isinstance(right, ExperienceEvidence):
            raise TypeError("evidence comparison requires ExperienceEvidence objects")
        context = NFPWindowSimilarity.compare(left.context_window, right.context_window)
        action = NFPFrameSimilarity.compare(left.action_frame, right.action_frame)
        effect = ObservedEffectSimilarity.compare(left.observed_effect, right.observed_effect)
        return cls(
            context.comparable, context.score,
            action.comparable, action.score,
            effect.comparable, effect.score,
        )
