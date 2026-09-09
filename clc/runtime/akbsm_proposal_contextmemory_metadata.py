from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewRecord,
    AKBSMProposalTransitionResult,
)


AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY = (
    AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY
)
AKBSM_PROPOSAL_CONTEXT_METADATA_SOURCE = "akbsm_proposal_lifecycle"
AKBSM_PROPOSAL_CONTEXT_METADATA_STORAGE_KIND = "metadata_only"


@dataclass(frozen=True)
class AKBSMProposalContextMemoryMetadata:
    """Immutable metadata payload for future scenario/test-only ContextMemory use."""

    proposal_id: str
    proposal_reference: tuple[tuple[str, str], ...]
    lifecycle_state: AKBSMProposalLifecycleState
    created_tick: int
    updated_tick: int
    ttl_ticks: int | None
    expires_at_tick: int | None
    review_reason: str
    review_notes: str
    transition_history: tuple[str, ...]
    controller_result: tuple[tuple[str, Any], ...] = ()
    source: str = AKBSM_PROPOSAL_CONTEXT_METADATA_SOURCE
    temporary: bool = True
    storage_kind: str = AKBSM_PROPOSAL_CONTEXT_METADATA_STORAGE_KIND
    observation_only: bool = True
    pending_commit: bool = False
    akbsm_write_approved: bool = False
    write_authorized: bool = False

    def __post_init__(self) -> None:
        state = _coerce_state(self.lifecycle_state)
        created_tick = _non_negative_int(self.created_tick, "created_tick")
        updated_tick = _non_negative_int(self.updated_tick, "updated_tick")
        ttl_ticks = self.ttl_ticks
        if ttl_ticks is not None:
            ttl_ticks = _non_negative_int(ttl_ticks, "ttl_ticks")
        expires_at_tick = self.expires_at_tick
        if expires_at_tick is not None:
            expires_at_tick = _non_negative_int(expires_at_tick, "expires_at_tick")
        if expires_at_tick is not None and expires_at_tick < created_tick:
            raise ValueError("expires_at_tick must not be less than created_tick")
        if not str(self.proposal_id).strip():
            raise ValueError("proposal_id must be non-empty metadata")
        if self.source != AKBSM_PROPOSAL_CONTEXT_METADATA_SOURCE:
            raise ValueError("source must identify AKBSM proposal lifecycle metadata")
        if self.storage_kind != AKBSM_PROPOSAL_CONTEXT_METADATA_STORAGE_KIND:
            raise ValueError("storage_kind must remain metadata_only")
        if self.temporary is not True:
            raise ValueError("metadata must remain temporary")
        if self.observation_only is not True:
            raise ValueError("metadata must remain observation-only")
        if self.pending_commit or self.akbsm_write_approved or self.write_authorized:
            raise ValueError("metadata cannot authorize writes or pending commits")
        object.__setattr__(self, "proposal_id", str(self.proposal_id).strip())
        object.__setattr__(
            self,
            "proposal_reference",
            tuple((str(key), str(value)) for key, value in self.proposal_reference),
        )
        object.__setattr__(self, "lifecycle_state", state)
        object.__setattr__(self, "created_tick", created_tick)
        object.__setattr__(self, "updated_tick", updated_tick)
        object.__setattr__(self, "ttl_ticks", ttl_ticks)
        object.__setattr__(self, "expires_at_tick", expires_at_tick)
        object.__setattr__(self, "review_reason", str(self.review_reason))
        object.__setattr__(self, "review_notes", str(self.review_notes))
        object.__setattr__(
            self,
            "transition_history",
            tuple(str(item) for item in self.transition_history),
        )
        object.__setattr__(
            self,
            "controller_result",
            tuple((str(key), value) for key, value in self.controller_result),
        )

    def to_metadata(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(
            {
                "proposal_id": self.proposal_id,
                "proposal_reference": self.proposal_reference,
                "lifecycle_state": self.lifecycle_state.value,
                "created_tick": self.created_tick,
                "updated_tick": self.updated_tick,
                "ttl_ticks": self.ttl_ticks,
                "expires_at_tick": self.expires_at_tick,
                "review_reason": self.review_reason,
                "review_notes": self.review_notes,
                "transition_history": self.transition_history,
                "controller_result": self.controller_result,
                "source": self.source,
                "temporary": self.temporary,
                "storage_kind": self.storage_kind,
                "observation_only": self.observation_only,
                "pending_commit": self.pending_commit,
                "akbsm_write_approved": self.akbsm_write_approved,
                "write_authorized": self.write_authorized,
            }
        )

    def as_payload(self) -> MappingProxyType[str, Any]:
        return self.to_metadata()


@dataclass(frozen=True)
class AKBSMProposalContextMemoryMetadataBuilder:
    """Scenario/test-only builder for immutable proposal review metadata payloads."""

    authority: str | None = None

    def build_metadata(
        self,
        record: AKBSMProposalReviewRecord,
        transition_result: AKBSMProposalTransitionResult | None = None,
        *,
        authority: str | None = None,
        expires_at_tick: int | None = None,
    ) -> AKBSMProposalContextMemoryMetadata | None:
        active_authority = authority if authority is not None else self.authority
        if active_authority != AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY:
            return None
        if not isinstance(record, AKBSMProposalReviewRecord):
            raise TypeError("record must be AKBSMProposalReviewRecord metadata")
        controller_result = ()
        if transition_result is not None:
            if not isinstance(transition_result, AKBSMProposalTransitionResult):
                raise TypeError("transition_result must be AKBSMProposalTransitionResult metadata")
            if transition_result.proposal is not record.proposal:
                raise ValueError("transition_result proposal must match record proposal")
            controller_result = _transition_result_metadata(transition_result)
        if record.proposal.commit_allowed:
            raise ValueError("proposal commit_allowed must remain False")
        derived_expires_at = expires_at_tick
        if derived_expires_at is None and record.ttl_ticks is not None:
            derived_expires_at = record.created_tick + record.ttl_ticks
        return AKBSMProposalContextMemoryMetadata(
            proposal_id=_proposal_id(record),
            proposal_reference=_proposal_reference(record),
            lifecycle_state=record.state,
            created_tick=record.created_tick,
            updated_tick=record.updated_tick,
            ttl_ticks=record.ttl_ticks,
            expires_at_tick=derived_expires_at,
            review_reason=record.review_reason,
            review_notes=record.review_notes,
            transition_history=record.transition_history,
            controller_result=controller_result,
        )


def build_metadata(
    record: AKBSMProposalReviewRecord,
    transition_result: AKBSMProposalTransitionResult | None = None,
    *,
    authority: str | None = None,
    expires_at_tick: int | None = None,
) -> AKBSMProposalContextMemoryMetadata | None:
    builder = AKBSMProposalContextMemoryMetadataBuilder()
    return builder.build_metadata(
        record,
        transition_result,
        authority=authority,
        expires_at_tick=expires_at_tick,
    )


def _proposal_id(record: AKBSMProposalReviewRecord) -> str:
    proposal = record.proposal
    return ":".join(
        (
            str(proposal.source),
            str(proposal.tick),
            str(proposal.subject_id),
            str(proposal.relation_type),
            str(proposal.object_id),
        )
    )


def _proposal_reference(record: AKBSMProposalReviewRecord) -> tuple[tuple[str, str], ...]:
    proposal = record.proposal
    return (
        ("source", str(proposal.source)),
        ("tick", str(proposal.tick)),
        ("subject_id", str(proposal.subject_id)),
        ("relation_type", str(proposal.relation_type)),
        ("object_id", str(proposal.object_id)),
        ("confidence", str(proposal.confidence)),
        ("reason", str(proposal.reason)),
    )


def _transition_result_metadata(
    result: AKBSMProposalTransitionResult,
) -> tuple[tuple[str, Any], ...]:
    return (
        ("from_state", result.from_state.value),
        ("to_state", result.to_state.value),
        ("allowed", result.allowed),
        ("reason", result.reason),
        ("tick", result.tick),
    )


def _coerce_state(value: AKBSMProposalLifecycleState | str) -> AKBSMProposalLifecycleState:
    try:
        return AKBSMProposalLifecycleState(value)
    except ValueError as exc:
        raise ValueError(f"unknown AKBSM proposal lifecycle state: {value!r}") from exc


def _non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be a non-negative integer") from exc
    if result < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return result
