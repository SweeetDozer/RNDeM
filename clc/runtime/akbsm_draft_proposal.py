from dataclasses import dataclass
from typing import Any

from clc.runtime.memory_mutation_policy import MemoryMutationPolicy


@dataclass(frozen=True)
class AKBSMAssociationProposal:
    """Immutable metadata-only draft association proposal payload."""

    source: str
    tick: int
    subject_id: str
    relation_type: str
    object_id: str
    confidence: float
    evidence: tuple[str, ...]
    reason: str
    commit_allowed: bool = False

    def __post_init__(self) -> None:
        confidence = float(self.confidence)
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.commit_allowed:
            raise ValueError("AKBSM association proposals cannot be commit-enabled")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be string metadata")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "evidence", tuple(str(item) for item in self.evidence))


@dataclass(frozen=True)
class AKBSMDraftProposalProvider:
    """Disabled no-op scaffold for future draft-only AKBSM association proposals."""

    policy: MemoryMutationPolicy

    def from_association_evidence(self, *_args: Any, **_kwargs: Any) -> tuple[AKBSMAssociationProposal, ...]:
        if not self.policy.akbsm_draft_proposals_enabled:
            return ()
        return ()
