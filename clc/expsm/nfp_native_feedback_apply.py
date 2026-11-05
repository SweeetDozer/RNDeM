from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable
from uuid import UUID

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
    ALREADY_APPLIED = "already_applied"
    EVENT_CONFLICT = "event_conflict"


class NFPFeedbackApplyAuthorityState(str, Enum):
    CONFIRMED = "confirmed"
    NOT_UPDATED = "not_updated"
    INDETERMINATE_FROM_CALLER_PERSPECTIVE = "indeterminate_from_caller_perspective"


@dataclass(frozen=True)
class NativeFeedbackEventKeyV1:
    source_experience_id: str
    execution_occurrence_id: str
    feedback_event_identity_version: int = 1

    def __post_init__(self) -> None:
        if self.feedback_event_identity_version != 1:
            raise ValueError("unsupported Feedback event identity version")
        if not isinstance(self.source_experience_id, str) or not self.source_experience_id.strip():
            raise ValueError("source_experience_id must be non-empty")
        try:
            if str(UUID(self.execution_occurrence_id, version=4)) != self.execution_occurrence_id:
                raise ValueError
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("execution_occurrence_id must be a canonical UUIDv4") from exc

    def to_json_data(self) -> dict[str, object]:
        return {
            "feedback_event_identity_version": self.feedback_event_identity_version,
            "source_experience_id": self.source_experience_id,
            "execution_occurrence_id": self.execution_occurrence_id,
        }


@dataclass(frozen=True)
class FeedbackEvidenceDigestV1:
    sha256: str
    feedback_evidence_digest_version: int = 1

    def __post_init__(self) -> None:
        if self.feedback_evidence_digest_version != 1:
            raise ValueError("unsupported Feedback evidence digest version")
        if (
            not isinstance(self.sha256, str) or len(self.sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.sha256)
        ):
            raise ValueError("Feedback evidence digest must be lowercase SHA-256")


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
    event_key_digest: str | None = None
    evidence_digest: str | None = None
    event_key: NativeFeedbackEventKeyV1 | None = None
    intended_receipt: dict[str, object] | None = None

    @property
    def retry_safe(self) -> bool:
        return self.status is not NFPFeedbackApplyStatus.READBACK_FAILED


class NFPFeedbackApplyRecoveryStatus(str, Enum):
    RECONCILED_APPLIED = "reconciled_applied"
    RECONCILED_NOT_APPLIED = "reconciled_not_applied"
    RECONCILIATION_CONFLICT = "reconciliation_conflict"
    # Source-compatible aliases for the v1.10 recovery API.
    CONFIRMED_PERSISTED = "reconciled_applied"
    CONFIRMED_NOT_APPLIED = "reconciled_not_applied"
    UNRESOLVED_OR_STORE_INVALID = "reconciliation_conflict"


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
        if evidence.execution_occurrence_id is None:
            return self._result(evidence, NFPFeedbackApplyStatus.EVENT_CONFLICT, "missing occurrence identity")
        event_key = NativeFeedbackEventKeyV1(
            evidence.source_experience_id, evidence.execution_occurrence_id,
        )
        event_key_digest = _sha256_json(event_key)
        evidence_digest_value = FeedbackEvidenceDigestV1(
            _sha256_json(_evidence_digest_payload(evidence))
        )
        evidence_digest = evidence_digest_value.sha256
        identity = {
            "event_key_digest": event_key_digest,
            "evidence_digest": evidence_digest,
            "event_key": event_key,
        }

        previous: NFPExpSMRecordV1 | None = None
        intended: NFPExpSMRecordV1 | None = None
        with self.transaction.mutation():
            try:
                store = self.transaction.load_for_mutation_strict()
                receipts = _receipts_for(store)
            except ExpSMStoreInvalidError as exc:
                return self._result(evidence, NFPFeedbackApplyStatus.STORE_INVALID, str(exc), **identity)

            occurrence_binding = receipts["execution_occurrence_index"].get(evidence.execution_occurrence_id)
            existing = receipts["by_event_key"].get(event_key_digest)
            if occurrence_binding is not None and occurrence_binding != event_key_digest:
                return self._result(evidence, NFPFeedbackApplyStatus.EVENT_CONFLICT,
                                    "occurrence already attributed to another source", **identity)
            if existing is not None:
                if existing.get("event_key") == event_key.to_json_data() and existing.get("evidence_digest") == evidence_digest:
                    return self._result(
                        evidence, NFPFeedbackApplyStatus.ALREADY_APPLIED,
                        "durable receipt confirms prior application",
                        authority_state=NFPFeedbackApplyAuthorityState.CONFIRMED, **identity,
                    )
                return self._result(evidence, NFPFeedbackApplyStatus.EVENT_CONFLICT,
                                    "event key is bound to different evidence", **identity)

            raw = store["experience"].get(source_id)
            if raw is None:
                return self._result(evidence, NFPFeedbackApplyStatus.TARGET_NOT_FOUND,
                                    "exact source ID is absent", **identity)
            parsed = ExpSMRecordAdapter.parse(source_id, raw)
            if not isinstance(parsed, NFPNativeOperationalRecordV1):
                return self._result(evidence, NFPFeedbackApplyStatus.TARGET_NOT_NATIVE,
                                    "target is not NFP_NATIVE_V1", **identity)
            previous = parsed.record
            if NFPFeedbackTargetCore.from_record(previous) != evidence.target_core:
                return self._result(
                    evidence,
                    NFPFeedbackApplyStatus.STALE_OR_CHANGED_TARGET,
                    "fresh TargetCore differs from evaluated TargetCore",
                    previous_record=previous,
                    **identity,
                )
            if not self.memory_mutation_policy.allow_expsm_update:
                return self._result(
                    evidence,
                    NFPFeedbackApplyStatus.DENIED_BY_POLICY,
                    "policy_disallows_expsm_update",
                    previous_record=previous,
                    **identity,
                )

            intended_updated_at_world = self.now_provider()
            intended = _updated_record(previous, classification, intended_updated_at_world)
            candidate = _as_v2_store(store, receipts)
            candidate["experience"] = dict(store["experience"])
            candidate["experience"][source_id] = intended.to_json_data()
            receipt = {
                "feedback_event_identity_version": 1,
                "event_key": event_key.to_json_data(),
                "feedback_evidence_digest_version": 1,
                "evidence_digest": evidence_digest,
                "source_experience_id": source_id,
                "execution_occurrence_id": evidence.execution_occurrence_id,
                "classification": classification.value,
                "applied_record_id": source_id,
                "applied_at_world": intended_updated_at_world,
                "post_update_record_fingerprint": _sha256_json(intended.to_json_data()),
            }
            ledger = candidate["native_feedback_receipts"]
            ledger["by_event_key"][event_key_digest] = receipt
            ledger["execution_occurrence_index"][evidence.execution_occurrence_id] = event_key_digest
            try:
                ExpSMStoreTransaction.normalize_store(candidate)
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
                    **identity,
                )

            try:
                self._inject("post_replace_readback")
                confirmed_state = self.transaction.load_state_strict()
                confirmed = _record_from_state(confirmed_state, source_id)
                if confirmed is None or confirmed.to_json_data() != intended.to_json_data():
                    raise ValueError("fresh readback did not match intended native Feedback update")
                confirmed_ledger = confirmed_state.native_feedback_receipts or {}
                if confirmed_ledger.get("by_event_key", {}).get(event_key_digest) != receipt:
                    raise ValueError("fresh readback did not match intended Feedback receipt")
                if confirmed_ledger.get("execution_occurrence_index", {}).get(
                    evidence.execution_occurrence_id
                ) != event_key_digest:
                    raise ValueError("fresh readback did not match occurrence index")
            except (OSError, TypeError, ValueError, ExpSMStoreInvalidError) as exc:
                return self._result(
                    evidence,
                    NFPFeedbackApplyStatus.READBACK_FAILED,
                    str(exc),
                    previous_record=previous,
                    intended_record=intended,
                    authority_state=NFPFeedbackApplyAuthorityState.INDETERMINATE_FROM_CALLER_PERSPECTIVE,
                    intended_receipt=receipt,
                    **identity,
                )
        return self._result(
            evidence,
            NFPFeedbackApplyStatus.UPDATED,
            "fresh_readback_confirmed",
            record=confirmed,
            previous_record=previous,
            intended_record=intended,
            authority_state=NFPFeedbackApplyAuthorityState.CONFIRMED,
            **identity,
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
        state = transaction.load_state_strict()
        current = _record_from_state(state, source_id)
    except (OSError, TypeError, ValueError, ExpSMStoreInvalidError) as exc:
        return NFPFeedbackApplyRecoveryResult(
            NFPFeedbackApplyRecoveryStatus.RECONCILIATION_CONFLICT,
            source_id,
            reason=str(exc),
        )
    if current is None:
        return NFPFeedbackApplyRecoveryResult(
            NFPFeedbackApplyRecoveryStatus.RECONCILIATION_CONFLICT,
            source_id,
            reason="target absent after indeterminate update",
        )
    ledger = state.native_feedback_receipts or {}
    by_key = ledger.get("by_event_key", {})
    occurrence_index = ledger.get("execution_occurrence_index", {})
    receipt = by_key.get(failed_result.event_key_digest)
    intended_receipt = failed_result.intended_receipt
    occurrence_id = (
        failed_result.event_key.execution_occurrence_id
        if failed_result.event_key is not None else None
    )
    if (
        current.to_json_data() == failed_result.intended_record.to_json_data()
        and intended_receipt is not None
        and receipt == intended_receipt
        and occurrence_index.get(occurrence_id) == failed_result.event_key_digest
    ):
        return NFPFeedbackApplyRecoveryResult(
            NFPFeedbackApplyRecoveryStatus.RECONCILED_APPLIED,
            source_id,
            record=current,
            reason="intended update is authoritative",
        )
    if (
        current.to_json_data() == failed_result.previous_record.to_json_data()
        and receipt is None
        and occurrence_index.get(occurrence_id) is None
    ):
        return NFPFeedbackApplyRecoveryResult(
            NFPFeedbackApplyRecoveryStatus.RECONCILED_NOT_APPLIED,
            source_id,
            record=current,
            reason="pre-update state remains authoritative",
        )
    return NFPFeedbackApplyRecoveryResult(
        NFPFeedbackApplyRecoveryStatus.RECONCILIATION_CONFLICT,
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


def _evidence_digest_payload(evidence: NFPFeedbackEvidence) -> dict[str, object]:
    return {
        "feedback_evidence_digest_version": 1,
        "evaluator_representation_version": 1,
        "source_experience_id": evidence.source_experience_id,
        "execution_occurrence_id": evidence.execution_occurrence_id,
        "target_core": asdict(evidence.target_core),
        "action_frame_id": evidence.action_frame_id,
        "action_tick": evidence.action_tick,
        "predicted_effect": asdict(evidence.predicted_effect),
        "actual_effect": asdict(evidence.actual_effect),
        "effect_similarity": evidence.effect_similarity,
        "agreement_threshold": evidence.agreement_threshold,
        "classification": evidence.classification,
    }


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _receipts_for(store: dict[str, object]) -> dict[str, object]:
    raw = store.get("native_feedback_receipts")
    if raw is None:
        return {
            "identity_version": 1, "digest_version": 1,
            "by_event_key": {}, "execution_occurrence_index": {},
        }
    if (
        not isinstance(raw, dict)
        or raw.get("identity_version") != 1
        or raw.get("digest_version") != 1
        or not isinstance(raw.get("by_event_key"), dict)
        or not isinstance(raw.get("execution_occurrence_index"), dict)
    ):
        raise ExpSMStoreInvalidError("invalid native Feedback receipt ledger")
    return {
        **raw,
        "by_event_key": dict(raw["by_event_key"]),
        "execution_occurrence_index": dict(raw["execution_occurrence_index"]),
    }


def _as_v2_store(store: dict[str, object], receipts: dict[str, object]) -> dict[str, object]:
    return {
        **store,
        "store_schema_version": 2,
        "experience": dict(store["experience"]),
        "reflexes": dict(store["reflexes"]),
        "native_feedback_receipts": {
            **receipts,
            "by_event_key": dict(receipts["by_event_key"]),
            "execution_occurrence_index": dict(receipts["execution_occurrence_index"]),
        },
    }


def _record_from_state(state: object, source_id: str) -> NFPExpSMRecordV1 | None:
    raw = state.experience.get(source_id)
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
