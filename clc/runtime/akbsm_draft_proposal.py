from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from clc.runtime.memory_mutation_policy import MemoryMutationPolicy


AKBSM_PROBE_PROPOSAL_SOURCE = "AKBSMAssociationProbe"


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
        for field_name in ("source", "subject_id", "relation_type", "object_id", "reason"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty string metadata")
        evidence = tuple(str(item).strip() for item in self.evidence)
        if not evidence or any(not item for item in evidence):
            raise ValueError("evidence must be non-empty metadata")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be string metadata")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True)
class AKBSMDraftProposalProvider:
    """Disabled-by-default provider for temporary AKBSM association proposals."""

    policy: MemoryMutationPolicy

    def from_association_evidence(self, evidence: Any = None, **kwargs: Any) -> tuple[AKBSMAssociationProposal, ...]:
        source = str(kwargs.get("source") or "")
        if source != AKBSM_PROBE_PROPOSAL_SOURCE:
            return ()
        tick = kwargs.get("tick")
        return self.build_from_probe_evidence(tick=tick, probe_payload=evidence)

    def build_from_probe_evidence(
        self,
        *,
        tick: int | None = None,
        probe_payload: Mapping[str, Any] | None = None,
    ) -> tuple[AKBSMAssociationProposal, ...]:
        if not self.policy.akbsm_draft_proposals_enabled:
            return ()
        if self.policy.allow_akbsm_write:
            return ()
        if not isinstance(probe_payload, Mapping):
            return ()
        subject_id = _metadata_text(probe_payload.get("source_pattern_id"))
        if not subject_id:
            return ()
        proposal_tick = _metadata_tick(tick if tick is not None else probe_payload.get("_event_tick"))
        probe_id = _metadata_text(probe_payload.get("probe_id"))
        target_observation_id = _metadata_text(probe_payload.get("source_target_observation_id"))
        proposals: list[AKBSMAssociationProposal] = []
        for association in probe_payload.get("associated_patterns", ()):
            if not isinstance(association, Mapping):
                continue
            object_id = _metadata_text(association.get("pattern_id"))
            relation_type = _metadata_text(association.get("relation_type"))
            if not object_id or not relation_type:
                continue
            path_evidence = _path_evidence(association.get("path"))
            evidence = tuple(
                item
                for item in (
                    f"probe:{probe_id}" if probe_id else "",
                    f"target_observation:{target_observation_id}" if target_observation_id else "",
                    path_evidence,
                )
                if item
            )
            if not evidence:
                continue
            proposals.append(
                AKBSMAssociationProposal(
                    source=AKBSM_PROBE_PROPOSAL_SOURCE,
                    tick=proposal_tick,
                    subject_id=subject_id,
                    relation_type=relation_type,
                    object_id=object_id,
                    confidence=_confidence(probe_payload, association),
                    evidence=evidence,
                    reason="akbsm_association_probe_observed_associative_evidence",
                    commit_allowed=False,
                )
            )
        return tuple(proposals)


def _metadata_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _metadata_tick(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _path_evidence(value: Any) -> str:
    if not isinstance(value, (list, tuple)):
        return ""
    path = tuple(_metadata_text(item) for item in value)
    path = tuple(item for item in path if item)
    if not path:
        return ""
    return "path:" + "->".join(path)


def _confidence(probe_payload: Mapping[str, Any], association: Mapping[str, Any]) -> float:
    association_score = _clamp(association.get("score", 0.0))
    probe_activation = _clamp(probe_payload.get("activation", 0.0))
    return round(max(association_score, probe_activation), 3)


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
