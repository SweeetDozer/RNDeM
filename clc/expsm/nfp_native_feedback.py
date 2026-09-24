from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from clc.actuation.remembered_action_execution import (
    NFPRememberedActionExecutionResult,
    NFPRememberedActionExecutionStatus,
)
from clc.context.causal_transition import RecentCausalTransition
from clc.experience.effects import ObservedEffect, ObservedEffectExtractor
from clc.experience.expsm_representation import SerializedObservedEffectV1
from clc.expsm.nfp_feedback_target import NFPFeedbackTargetCore


class NFPFeedbackEvaluationStatus(str, Enum):
    HIT = "hit"
    MISS = "miss"
    NOT_ELIGIBLE_EXECUTION = "not_eligible_execution"
    OBSERVATION_PENDING = "observation_pending"
    CAUSAL_TRACKING_UNAVAILABLE = "causal_tracking_unavailable"
    TRANSITION_MISMATCH = "transition_mismatch"
    INCOMPARABLE_EFFECT = "incomparable_effect"
    INVALID_ACTUAL_EFFECT = "invalid_actual_effect"
    INVALID_PREDICTION = "invalid_prediction"


@dataclass(frozen=True)
class NFPFeedbackEvaluationConfig:
    native_effect_agreement_threshold: float

    def __post_init__(self) -> None:
        threshold = float(self.native_effect_agreement_threshold)
        if not math.isfinite(threshold) or threshold < 0.0 or threshold > 1.0:
            raise ValueError("native_effect_agreement_threshold must be in [0.0, 1.0]")
        object.__setattr__(self, "native_effect_agreement_threshold", threshold)


@dataclass(frozen=True)
class NFPFeedbackEvidence:
    source_experience_id: str
    target_core: NFPFeedbackTargetCore
    action_frame_id: str
    action_tick: int
    predicted_effect: SerializedObservedEffectV1
    actual_effect: ObservedEffect
    effect_similarity: float
    agreement_threshold: float
    classification: NFPFeedbackEvaluationStatus

    def __post_init__(self) -> None:
        if self.classification not in {
            NFPFeedbackEvaluationStatus.HIT, NFPFeedbackEvaluationStatus.MISS,
        }:
            raise ValueError("evidence classification must be HIT or MISS")


@dataclass(frozen=True)
class NFPFeedbackEvaluationResult:
    status: NFPFeedbackEvaluationStatus
    evidence: NFPFeedbackEvidence | None = None
    effect_similarity: float | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        has_evidence = self.evidence is not None
        if has_evidence != (self.status in {NFPFeedbackEvaluationStatus.HIT, NFPFeedbackEvaluationStatus.MISS}):
            raise ValueError("only HIT/MISS results carry Feedback evidence")


class NativePredictedObservedEffectComparator:
    """Direct signed structural comparison without fabricated occurrences."""

    @staticmethod
    def compare(
        predicted: SerializedObservedEffectV1,
        actual: ObservedEffect,
    ) -> tuple[bool, float | None, str | None]:
        if not isinstance(predicted, SerializedObservedEffectV1):
            raise TypeError("predicted effect must be SerializedObservedEffectV1")
        if not isinstance(actual, ObservedEffect):
            raise TypeError("actual effect must be ObservedEffect")
        if predicted.modality != actual.modality.value:
            return False, None, "different_modality"
        if predicted.topology != actual.topology.shape:
            return False, None, "different_topology"
        if len(predicted.delta_values) != len(actual.delta_values):
            return False, None, "different_delta_length"
        mean_abs_error = sum(
            abs(expected - observed)
            for expected, observed in zip(predicted.delta_values, actual.delta_values)
        ) / len(predicted.delta_values)
        return True, 1.0 - mean_abs_error / 2.0, None


class NFPFeedbackEvaluator:
    """Pure prediction-reliability evaluation; owns no mutation authority."""

    @staticmethod
    def evaluate(
        execution: NFPRememberedActionExecutionResult,
        transition: RecentCausalTransition | None,
        config: NFPFeedbackEvaluationConfig,
    ) -> NFPFeedbackEvaluationResult:
        if not isinstance(execution, NFPRememberedActionExecutionResult):
            raise TypeError("execution must be NFPRememberedActionExecutionResult")
        if not isinstance(config, NFPFeedbackEvaluationConfig):
            raise TypeError("config must be NFPFeedbackEvaluationConfig")

        status = execution.status
        if status is NFPRememberedActionExecutionStatus.ACTION_EXECUTED_CAUSAL_TRACKING_FAILED:
            return NFPFeedbackEvaluationResult(
                NFPFeedbackEvaluationStatus.CAUSAL_TRACKING_UNAVAILABLE,
                detail="execution causal tracking failed",
            )
        if status is NFPRememberedActionExecutionStatus.ACTION_EXECUTED_OBSERVATION_PENDING and transition is None:
            return NFPFeedbackEvaluationResult(
                NFPFeedbackEvaluationStatus.OBSERVATION_PENDING,
                detail="matching completed transition is not available",
            )
        if status not in {
            NFPRememberedActionExecutionStatus.EXECUTED_AND_OBSERVED,
            NFPRememberedActionExecutionStatus.ACTION_EXECUTED_OBSERVATION_PENDING,
        }:
            return NFPFeedbackEvaluationResult(
                NFPFeedbackEvaluationStatus.NOT_ELIGIBLE_EXECUTION,
                detail=f"execution status {status.value} is not eligible",
            )

        current_transition = transition or execution.recent_transition
        if current_transition is None:
            return NFPFeedbackEvaluationResult(
                NFPFeedbackEvaluationStatus.OBSERVATION_PENDING,
                detail="matching completed transition is not available",
            )
        frame = execution.action_frame
        if frame is None or (
            frame.frame_id != current_transition.action_frame.frame_id
            or frame.active_tick != current_transition.action_frame.active_tick
            or current_transition.action_tick != frame.active_tick
            or current_transition.observation_tick != current_transition.action_tick + 1
        ):
            return NFPFeedbackEvaluationResult(
                NFPFeedbackEvaluationStatus.TRANSITION_MISMATCH,
                detail="transition occurrence does not match execution action",
            )

        predicted = execution.predicted_effect
        target_core = execution.target_core
        if (
            not isinstance(predicted, SerializedObservedEffectV1)
            or not isinstance(target_core, NFPFeedbackTargetCore)
            or predicted != target_core.effect
            or not isinstance(execution.source_experience_id, str)
            or not execution.source_experience_id.strip()
        ):
            return NFPFeedbackEvaluationResult(
                NFPFeedbackEvaluationStatus.INVALID_PREDICTION,
                detail="prediction, TargetCore, or source identity is invalid",
            )
        try:
            actual = ObservedEffectExtractor.extract(current_transition)
        except (TypeError, ValueError) as exc:
            return NFPFeedbackEvaluationResult(
                NFPFeedbackEvaluationStatus.INVALID_ACTUAL_EFFECT,
                detail=str(exc),
            )
        try:
            comparable, similarity, reason = NativePredictedObservedEffectComparator.compare(predicted, actual)
        except (TypeError, ValueError) as exc:
            return NFPFeedbackEvaluationResult(
                NFPFeedbackEvaluationStatus.INVALID_PREDICTION,
                detail=str(exc),
            )
        if not comparable:
            return NFPFeedbackEvaluationResult(
                NFPFeedbackEvaluationStatus.INCOMPARABLE_EFFECT,
                detail=reason or "effects are structurally incomparable",
            )
        assert similarity is not None
        classification = (
            NFPFeedbackEvaluationStatus.HIT
            if similarity >= config.native_effect_agreement_threshold
            else NFPFeedbackEvaluationStatus.MISS
        )
        evidence = NFPFeedbackEvidence(
            source_experience_id=execution.source_experience_id,
            target_core=target_core,
            action_frame_id=frame.frame_id,
            action_tick=frame.active_tick,
            predicted_effect=predicted,
            actual_effect=actual,
            effect_similarity=similarity,
            agreement_threshold=config.native_effect_agreement_threshold,
            classification=classification,
        )
        return NFPFeedbackEvaluationResult(classification, evidence, similarity)


def evaluate_native_feedback(
    execution: NFPRememberedActionExecutionResult,
    transition: RecentCausalTransition | None,
    config: NFPFeedbackEvaluationConfig,
) -> NFPFeedbackEvaluationResult:
    return NFPFeedbackEvaluator.evaluate(execution, transition, config)
