from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from clc.consolidation.expsm_store_transaction import (
    ExpSMStoreInvalidError,
    ExpSMStoreTransaction,
)
from clc.experience.expsm_representation import (
    ExpSMOperationalMetadataV1,
    ExpSMRecordAdapter,
    NFPNativeOperationalRecordV1,
    NFPExpSMRecordV1,
)
from clc.expsm.expsm_outcome_feedback import (
    CONFIDENCE_SMOOTHING_NEW,
    CONFIDENCE_SMOOTHING_OLD,
    LEGACY_CONFIDENCE_SOFT_CAP,
    REPEATABILITY_CAP,
    REPEATABILITY_SATURATION,
    _confidence_from_simple_feedback,
)
from clc.expsm.nfp_feedback_target import NFPFeedbackTargetCore
from clc.expsm.nfp_native_feedback import (
    NFPFeedbackEvaluationStatus,
    NFPFeedbackEvidence,
)
from clc.runtime.memory_mutation_policy import MemoryMutationPolicy


class NFPFeedbackApplyStatus(str, Enum):
    UPDATED = "updated"
    DENIED_BY_POLICY = "denied_by_policy"
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_NOT_NATIVE = "target_not_native"
    STALE_OR_CHANGED_TARGET = "stale_or_changed_target"
    STORE_INVALID = "store_invalid"
    WRITE_FAILED = "write_failed"
    READBACK_FAILED = "readback_failed"


class NFPFeedbackApplyAuthorityState(str, Enum):
    CONFIRMED = "confirmed"
    NOT_UPDATED = "not_updated"
    INDETERMINATE_FROM_CALLER_PERSPECTIVE = "indeterminate_from_caller_perspective"


@dataclass(frozen=True)
class NFPFeedbackApplyResult:
    status: NFPFeedbackApplyStatus
    source_experience_id: str
    classification: NFPFeedbackEvaluationStatus
    reason: str
    record: NFPExpSMRecordV1 | None = None
    previous_record: NFPExpSMRecordV1 | None = None
    intended_record: NFPExpSMRecordV1 | None = None
    authority_state: NFPFeedbackApplyAuthorityState = NFPFeedbackApplyAuthorityState.NOT_UPDATED

    @property
    def retry_safe(self) -> bool:
        return self.status is not NFPFeedbackApplyStatus.READBACK_FAILED


class NFPFeedbackApplyRecoveryStatus(str, Enum):
    CONFIRMED_PERSISTED = "confirmed_persisted"
    CONFIRMED_NOT_APPLIED = "confirmed_not_applied"
    UNRESOLVED_OR_STORE_INVALID = "unresolved_or_store_invalid"


@dataclass(frozen=True)
class NFPFeedbackApplyRecoveryResult:
    status: NFPFeedbackApplyRecoveryStatus
    source_experience_id: str
    record: NFPExpSMRecordV1 | None = None
    reason: str = ""


FailureHook = Callable[[str], None]
NowProvider = Callable[[], str]


class NFPFeedbackApplyWriter:
    """Explicit exact-record native Feedback update; never runs automatically."""

    def __init__(
        self,
        store_path: str | Path,
        memory_mutation_policy: MemoryMutationPolicy,
        *,
        failure_hook: FailureHook | None = None,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.transaction = ExpSMStoreTransaction(store_path)
        self.memory_mutation_policy = memory_mutation_policy
        self.failure_hook = failure_hook
        self.now_provider = now_provider or _now_iso

    def apply(self, evidence: NFPFeedbackEvidence) -> NFPFeedbackApplyResult:
        if not isinstance(evidence, NFPFeedbackEvidence):
            raise TypeError("native Feedback apply requires NFPFeedbackEvidence")
        source_id = evidence.source_experience_id
        classification = evidence.classification

        previous: NFPExpSMRecordV1 | None = None
        intended: NFPExpSMRecordV1 | None = None
        with self.transaction.mutation():
            try:
                store = self.transaction.load_strict()
            except ExpSMStoreInvalidError as exc:
                return self._result(evidence, NFPFeedbackApplyStatus.STORE_INVALID, str(exc))

            raw = store["experience"].get(source_id)
            if raw is None:
                return self._result(evidence, NFPFeedbackApplyStatus.TARGET_NOT_FOUND, "exact source ID is absent")
            parsed = ExpSMRecordAdapter.parse(source_id, raw)
            if not isinstance(parsed, NFPNativeOperationalRecordV1):
                return self._result(evidence, NFPFeedbackApplyStatus.TARGET_NOT_NATIVE, "target is not NFP_NATIVE_V1")
            previous = parsed.record
            if NFPFeedbackTargetCore.from_record(previous) != evidence.target_core:
                return self._result(
                    evidence,
                    NFPFeedbackApplyStatus.STALE_OR_CHANGED_TARGET,
                    "fresh TargetCore differs from evaluated TargetCore",
                    previous_record=previous,
                )
            if not self.memory_mutation_policy.allow_expsm_update:
                return self._result(
                    evidence,
                    NFPFeedbackApplyStatus.DENIED_BY_POLICY,
                    "policy_disallows_expsm_update",
                    previous_record=previous,
                )

            intended = _updated_record(previous, classification, self.now_provider())
            candidate = dict(store)
            candidate["experience"] = dict(store["experience"])
            candidate["experience"][source_id] = intended.to_json_data()
            try:
                ExpSMStoreTransaction.validate_store(candidate)
                self.transaction.write_complete_store(
                    candidate,
                    before_replace=lambda: self._inject("pre_replace"),
                )
            except (OSError, TypeError, ValueError) as exc:
                return self._result(
                    evidence,
                    NFPFeedbackApplyStatus.WRITE_FAILED,
                    str(exc),
                    previous_record=previous,
                    intended_record=intended,
                )

        try:
            self._inject("post_replace_readback")
            confirmed = _fresh_record(self.transaction, source_id)
            if confirmed is None or confirmed.to_json_data() != intended.to_json_data():
                raise ValueError("fresh readback did not match intended native Feedback update")
        except (OSError, TypeError, ValueError, ExpSMStoreInvalidError) as exc:
            return self._result(
                evidence,
                NFPFeedbackApplyStatus.READBACK_FAILED,
                str(exc),
                previous_record=previous,
                intended_record=intended,
                authority_state=NFPFeedbackApplyAuthorityState.INDETERMINATE_FROM_CALLER_PERSPECTIVE,
            )
        return self._result(
            evidence,
            NFPFeedbackApplyStatus.UPDATED,
            "fresh_readback_confirmed",
            record=confirmed,
            previous_record=previous,
            intended_record=intended,
            authority_state=NFPFeedbackApplyAuthorityState.CONFIRMED,
        )

    def _inject(self, stage: str) -> None:
        if self.failure_hook is not None:
            self.failure_hook(stage)

    @staticmethod
    def _result(
        evidence: NFPFeedbackEvidence,
        status: NFPFeedbackApplyStatus,
        reason: str,
        **kwargs: object,
    ) -> NFPFeedbackApplyResult:
        return NFPFeedbackApplyResult(
            status,
            evidence.source_experience_id,
            evidence.classification,
            reason,
            **kwargs,
        )


def reconcile_nfp_feedback_readback_failure(
    store_path: str | Path,
    failed_result: NFPFeedbackApplyResult,
) -> NFPFeedbackApplyRecoveryResult:
    """Read-only reconciliation of an indeterminate apply; it never retries."""
    if failed_result.status is not NFPFeedbackApplyStatus.READBACK_FAILED:
        raise ValueError("reconciliation requires a READBACK_FAILED apply result")
    if failed_result.previous_record is None or failed_result.intended_record is None:
        raise ValueError("readback failure lacks before/intended record states")
    transaction = ExpSMStoreTransaction(store_path)
    source_id = failed_result.source_experience_id
    try:
        current = _fresh_record(transaction, source_id)
    except (OSError, TypeError, ValueError, ExpSMStoreInvalidError) as exc:
        return NFPFeedbackApplyRecoveryResult(
            NFPFeedbackApplyRecoveryStatus.UNRESOLVED_OR_STORE_INVALID,
            source_id,
            reason=str(exc),
        )
    if current is None:
        return NFPFeedbackApplyRecoveryResult(
            NFPFeedbackApplyRecoveryStatus.UNRESOLVED_OR_STORE_INVALID,
            source_id,
            reason="target absent after indeterminate update",
        )
    if current.to_json_data() == failed_result.intended_record.to_json_data():
        return NFPFeedbackApplyRecoveryResult(
            NFPFeedbackApplyRecoveryStatus.CONFIRMED_PERSISTED,
            source_id,
            record=current,
            reason="intended update is authoritative",
        )
    if current.to_json_data() == failed_result.previous_record.to_json_data():
        return NFPFeedbackApplyRecoveryResult(
            NFPFeedbackApplyRecoveryStatus.CONFIRMED_NOT_APPLIED,
            source_id,
            record=current,
            reason="pre-update state remains authoritative",
        )
    return NFPFeedbackApplyRecoveryResult(
        NFPFeedbackApplyRecoveryStatus.UNRESOLVED_OR_STORE_INVALID,
        source_id,
        record=current,
        reason="authoritative target matches neither before nor intended state",
    )


def _updated_record(
    record: NFPExpSMRecordV1,
    classification: NFPFeedbackEvaluationStatus,
    updated_at_world: str,
) -> NFPExpSMRecordV1:
    old = record.operational
    hits = old.hits + (classification is NFPFeedbackEvaluationStatus.HIT)
    misses = old.misses + (classification is NFPFeedbackEvaluationStatus.MISS)
    target_confidence = _confidence_from_simple_feedback(hits, misses)
    confidence = _clamp(
        CONFIDENCE_SMOOTHING_OLD * min(old.confidence, LEGACY_CONFIDENCE_SOFT_CAP)
        + CONFIDENCE_SMOOTHING_NEW * target_confidence,
        0.0,
        LEGACY_CONFIDENCE_SOFT_CAP,
    )
    repeatability_target = REPEATABILITY_CAP * (
        1.0 - math.exp(-(hits + misses) / REPEATABILITY_SATURATION)
    )
    repeatability = _clamp(max(old.repeatability * 0.85, repeatability_target), 0.0, REPEATABILITY_CAP)
    operational = ExpSMOperationalMetadataV1(
        hits,
        misses,
        round(confidence, 3),
        round(repeatability, 3),
    )
    return replace(record, operational=operational, updated_at_world=updated_at_world)


def _fresh_record(
    transaction: ExpSMStoreTransaction,
    source_id: str,
) -> NFPExpSMRecordV1 | None:
    store = transaction.load_strict()
    raw = store["experience"].get(source_id)
    if raw is None:
        return None
    parsed = ExpSMRecordAdapter.parse(source_id, raw)
    if not isinstance(parsed, NFPNativeOperationalRecordV1):
        raise ValueError("target is not NFP_NATIVE_V1")
    return parsed.record


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
