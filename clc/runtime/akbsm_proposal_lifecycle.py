from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from clc.runtime.akbsm_draft_proposal import AKBSMAssociationProposal


class AKBSMProposalLifecycleState(str, Enum):
    CREATED = "created"
    REVIEW_PENDING = "review_pending"
    ACCEPTED_FOR_OBSERVATION = "accepted_for_observation"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    EXPIRED = "expired"


AKBSM_PROPOSAL_ALLOWED_TRANSITIONS: MappingProxyType[
    AKBSMProposalLifecycleState, tuple[AKBSMProposalLifecycleState, ...]
] = MappingProxyType(
    {
        AKBSMProposalLifecycleState.CREATED: (AKBSMProposalLifecycleState.REVIEW_PENDING,),
        AKBSMProposalLifecycleState.REVIEW_PENDING: (
            AKBSMProposalLifecycleState.ACCEPTED_FOR_OBSERVATION,
            AKBSMProposalLifecycleState.DEFERRED,
            AKBSMProposalLifecycleState.REJECTED,
            AKBSMProposalLifecycleState.EXPIRED,
        ),
        AKBSMProposalLifecycleState.ACCEPTED_FOR_OBSERVATION: (
            AKBSMProposalLifecycleState.EXPIRED,
        ),
        AKBSMProposalLifecycleState.DEFERRED: (
            AKBSMProposalLifecycleState.REVIEW_PENDING,
            AKBSMProposalLifecycleState.EXPIRED,
        ),
        AKBSMProposalLifecycleState.REJECTED: (AKBSMProposalLifecycleState.EXPIRED,),
        AKBSMProposalLifecycleState.EXPIRED: (),
    }
)

AKBSM_PROPOSAL_FORBIDDEN_WRITE_LIKE_STATE_NAMES = frozenset(
    (
        "committed",
        "applied",
        "persisted",
        "written",
        "saved",
        "accepted_for_write",
        "ready_to_write",
        "approved_for_akbsm",
    )
)


@dataclass(frozen=True)
class AKBSMProposalReviewRecord:
    """Immutable metadata-only lifecycle review record."""

    proposal: AKBSMAssociationProposal
    state: AKBSMProposalLifecycleState
    created_tick: int
    updated_tick: int
    ttl_ticks: int | None = None
    review_reason: str = ""
    review_notes: str = ""
    transition_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, AKBSMAssociationProposal):
            raise TypeError("proposal must be AKBSMAssociationProposal metadata")
        state = _coerce_state(self.state)
        created_tick = _non_negative_int(self.created_tick, "created_tick")
        updated_tick = _non_negative_int(self.updated_tick, "updated_tick")
        if updated_tick < created_tick:
            raise ValueError("updated_tick must not be less than created_tick")
        ttl_ticks = self.ttl_ticks
        if ttl_ticks is not None:
            ttl_ticks = _non_negative_int(ttl_ticks, "ttl_ticks")
        if self.proposal.commit_allowed:
            raise ValueError("proposal commit_allowed must remain False")
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "created_tick", created_tick)
        object.__setattr__(self, "updated_tick", updated_tick)
        object.__setattr__(self, "ttl_ticks", ttl_ticks)
        object.__setattr__(self, "review_reason", str(self.review_reason))
        object.__setattr__(self, "review_notes", str(self.review_notes))
        object.__setattr__(
            self,
            "transition_history",
            tuple(str(item) for item in self.transition_history),
        )


@dataclass(frozen=True)
class AKBSMProposalTransitionResult:
    """Immutable metadata-only transition report."""

    proposal: AKBSMAssociationProposal
    from_state: AKBSMProposalLifecycleState
    to_state: AKBSMProposalLifecycleState
    allowed: bool
    reason: str
    tick: int

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, AKBSMAssociationProposal):
            raise TypeError("proposal must be AKBSMAssociationProposal metadata")
        if self.proposal.commit_allowed:
            raise ValueError("proposal commit_allowed must remain False")
        object.__setattr__(self, "from_state", _coerce_state(self.from_state))
        object.__setattr__(self, "to_state", _coerce_state(self.to_state))
        object.__setattr__(self, "allowed", bool(self.allowed))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "tick", _non_negative_int(self.tick, "tick"))


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
