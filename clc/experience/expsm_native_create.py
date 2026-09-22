from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from clc.consolidation.expsm_store_transaction import (
    ExpSMStoreInvalidError,
    ExpSMStoreTransaction,
)
from clc.experience.expsm_representation import (
    NFP_NATIVE_KIND,
    NFP_NATIVE_VERSION,
    ExpSMOperationalMetadataV1,
    ExpSMRecordAdapter,
    ExpSMRecordCreationRequest,
    NFPNativeOperationalRecordV1,
    NFPExpSMRecordV1,
)
from clc.runtime.memory_mutation_policy import MemoryMutationPolicy


class ExpSMCreateStatus(str, Enum):
    CREATED = "created"
    DENIED_BY_POLICY = "denied_by_policy"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_REPRESENTATION = "unsupported_representation"
    STORE_INVALID = "store_invalid"
    WRITE_FAILED = "write_failed"
    READBACK_FAILED = "readback_failed"


class ExpSMAuthorityState(str, Enum):
    CONFIRMED = "confirmed"
    NOT_CREATED = "not_created"
    INDETERMINATE_FROM_CALLER_PERSPECTIVE = "indeterminate_from_caller_perspective"


@dataclass(frozen=True)
class ExpSMCreateResult:
    status: ExpSMCreateStatus
    reason: str
    record_id: str | None = None
    record: NFPExpSMRecordV1 | None = None
    attempted_record_id: str | None = None
    authority_state: ExpSMAuthorityState = ExpSMAuthorityState.NOT_CREATED

    @property
    def retry_safe(self) -> bool:
        return self.status is not ExpSMCreateStatus.READBACK_FAILED


class ExpSMRecoveryStatus(str, Enum):
    CONFIRMED_PERSISTED = "confirmed_persisted"
    CONFIRMED_ABSENT = "confirmed_absent"
    UNRESOLVED_OR_STORE_INVALID = "unresolved_or_store_invalid"


@dataclass(frozen=True)
class ExpSMRecoveryResult:
    status: ExpSMRecoveryStatus
    attempted_record_id: str
    record: NFPExpSMRecordV1 | None = None
    reason: str = ""


FailureHook = Callable[[str], None]


class NFPExpSMCreationRequestValidator:
    """Validate the complete typed handoff before policy or persistence."""

    @staticmethod
    def validate(request: object) -> tuple[ExpSMCreateStatus | None, str]:
        if getattr(request, "record_kind", None) != NFP_NATIVE_KIND:
            return ExpSMCreateStatus.UNSUPPORTED_REPRESENTATION, "unsupported_record_kind"
        if getattr(request, "representation_version", None) != NFP_NATIVE_VERSION:
            return ExpSMCreateStatus.UNSUPPORTED_REPRESENTATION, "unsupported_representation_version"
        if not isinstance(request, ExpSMRecordCreationRequest):
            return ExpSMCreateStatus.INVALID_REQUEST, "request_must_be_typed_creation_request"
        try:
            data = request.to_json_data()
            if "record_id" in data:
                raise ValueError("creation request must not contain record_id")
            expected_keys = {
                "request_id", "record_kind", "representation_version",
                "context_pattern", "action_pattern", "effect_pattern",
                "requested_operational_metadata", "creation_metadata",
            }
            if set(data) != expected_keys:
                raise ValueError("creation request contains unexpected fields")
            operational = ExpSMOperationalMetadataV1()
            if request.requested_operational != operational:
                raise ValueError("unsupported operational initialization profile")
            # Typed rematerialization exercises all v1 range/topology/provenance validators.
            request.materialize_for_validation("0")
        except (TypeError, ValueError) as exc:
            return ExpSMCreateStatus.INVALID_REQUEST, str(exc)
        return None, "valid"


class NFPExpSMCreateWriter:
    """Explicit policy-gated NFP-native CREATE; not wired into normal runtime."""

    def __init__(
        self,
        store_path: str | Path,
        memory_mutation_policy: MemoryMutationPolicy,
        *,
        failure_hook: FailureHook | None = None,
    ) -> None:
        self.transaction = ExpSMStoreTransaction(store_path)
        self.memory_mutation_policy = memory_mutation_policy
        self.failure_hook = failure_hook

    def create(self, request: object) -> ExpSMCreateResult:
        invalid_status, reason = NFPExpSMCreationRequestValidator.validate(request)
        if invalid_status is not None:
            return ExpSMCreateResult(invalid_status, reason)
        assert isinstance(request, ExpSMRecordCreationRequest)
        if not self.memory_mutation_policy.allow_expsm_commit:
            return ExpSMCreateResult(ExpSMCreateStatus.DENIED_BY_POLICY, "policy_disallows_expsm_commit")

        attempted_id: str | None = None
        expected: NFPExpSMRecordV1 | None = None
        with self.transaction.mutation():
            try:
                store = self.transaction.load_strict()
            except ExpSMStoreInvalidError as exc:
                return ExpSMCreateResult(ExpSMCreateStatus.STORE_INVALID, str(exc))
            attempted_id = str(max((int(key) for key in store["experience"]), default=0) + 1)
            expected = request.materialize_for_validation(attempted_id)
            candidate = dict(store)
            candidate["experience"] = dict(store["experience"])
            candidate["experience"][attempted_id] = expected.to_json_data()
            try:
                ExpSMStoreTransaction.validate_store(candidate)
                self.transaction.write_complete_store(
                    candidate,
                    before_replace=lambda: self._inject("pre_replace"),
                )
            except (OSError, TypeError, ValueError) as exc:
                return ExpSMCreateResult(ExpSMCreateStatus.WRITE_FAILED, str(exc))

        try:
            self._inject("post_replace_readback")
            confirmed = _fresh_matching_record(self.transaction, attempted_id, request)
            if confirmed is None:
                raise ValueError("fresh readback did not match the creation request")
        except (OSError, TypeError, ValueError, ExpSMStoreInvalidError) as exc:
            return ExpSMCreateResult(
                ExpSMCreateStatus.READBACK_FAILED,
                str(exc),
                attempted_record_id=attempted_id,
                authority_state=ExpSMAuthorityState.INDETERMINATE_FROM_CALLER_PERSPECTIVE,
            )
        return ExpSMCreateResult(
            ExpSMCreateStatus.CREATED,
            "fresh_readback_confirmed",
            record_id=attempted_id,
            record=confirmed,
            authority_state=ExpSMAuthorityState.CONFIRMED,
        )

    def _inject(self, stage: str) -> None:
        if self.failure_hook is not None:
            self.failure_hook(stage)


def reconcile_expsm_readback_failure(
    store_path: str | Path,
    attempted_record_id: str,
    request: ExpSMRecordCreationRequest,
) -> ExpSMRecoveryResult:
    """Fresh read-only reconciliation; never retries or mutates the store."""
    transaction = ExpSMStoreTransaction(store_path)
    try:
        store = transaction.load_strict()
    except (OSError, TypeError, ValueError, ExpSMStoreInvalidError) as exc:
        return ExpSMRecoveryResult(
            ExpSMRecoveryStatus.UNRESOLVED_OR_STORE_INVALID,
            attempted_record_id,
            reason=str(exc),
        )
    if attempted_record_id not in store["experience"]:
        return ExpSMRecoveryResult(
            ExpSMRecoveryStatus.CONFIRMED_ABSENT,
            attempted_record_id,
            reason="attempted_record_id_absent_from_valid_store",
        )
    try:
        record = _matching_record(store, attempted_record_id, request)
    except (TypeError, ValueError) as exc:
        return ExpSMRecoveryResult(
            ExpSMRecoveryStatus.UNRESOLVED_OR_STORE_INVALID,
            attempted_record_id,
            reason=str(exc),
        )
    if record is None:
        return ExpSMRecoveryResult(
            ExpSMRecoveryStatus.UNRESOLVED_OR_STORE_INVALID,
            attempted_record_id,
            reason="attempted record does not match original request",
        )
    return ExpSMRecoveryResult(
        ExpSMRecoveryStatus.CONFIRMED_PERSISTED,
        attempted_record_id,
        record=record,
        reason="fresh_readback_confirmed",
    )


def _fresh_matching_record(
    transaction: ExpSMStoreTransaction,
    record_id: str,
    request: ExpSMRecordCreationRequest,
) -> NFPExpSMRecordV1 | None:
    store = transaction.load_strict()
    return _matching_record(store, record_id, request)


def _matching_record(
    store: dict[str, object],
    record_id: str,
    request: ExpSMRecordCreationRequest,
) -> NFPExpSMRecordV1 | None:
    experience = store["experience"]
    assert isinstance(experience, dict)
    raw = experience.get(record_id)
    if raw is None:
        return None
    parsed = ExpSMRecordAdapter.parse(record_id, raw)
    if not isinstance(parsed, NFPNativeOperationalRecordV1):
        return None
    expected = request.materialize_for_validation(record_id)
    if parsed.record.to_json_data() != expected.to_json_data():
        return None
    return parsed.record
