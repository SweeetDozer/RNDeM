from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from clc.experience.evidence import ExperienceEvidence, ExperienceEvidenceComparison


@dataclass(frozen=True)
class ExperienceGroupingConfig:
    context_similarity_threshold: float
    action_similarity_threshold: float
    effect_similarity_threshold: float
    min_support: int

    def __post_init__(self) -> None:
        for name in (
            "context_similarity_threshold", "action_similarity_threshold", "effect_similarity_threshold",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{name} must be numeric")
            if float(value) < 0.0 or float(value) > 1.0:
                raise ValueError(f"{name} must be in [0,1]")
            object.__setattr__(self, name, float(value))
        if not isinstance(self.min_support, int) or isinstance(self.min_support, bool):
            raise TypeError("min_support must be an integer")
        if self.min_support <= 0:
            raise ValueError("min_support must be > 0")


@dataclass(frozen=True)
class ExpSMConsolidationCandidate:
    """Read-only snapshot of transient observational support."""

    candidate_id: str
    representative_evidence: ExperienceEvidence
    supporting_evidence_ids: tuple[str, ...]
    support_count: int
    first_observation_tick: int
    last_observation_tick: int


@dataclass(frozen=True)
class ExpSMConsolidationProposal:
    """Explicit transient handoff; not an active or persistent ExpSM record."""

    proposal_id: str
    candidate_id: str
    representative_evidence_id: str
    support_count: int
    supporting_evidence_ids: tuple[str, ...]
    first_observation_tick: int
    last_observation_tick: int
    created_active_tick: int


class GroupingStatus(str, Enum):
    CREATED = "created"
    ADDED = "added"
    DUPLICATE = "duplicate"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class GroupingResult:
    status: GroupingStatus
    evidence_id: str
    candidate_id: str | None = None
    eligible_candidate_ids: tuple[str, ...] = ()


@dataclass
class _MutableCandidate:
    candidate_id: str
    representative_evidence: ExperienceEvidence
    supporting_evidence_ids: list[str]
    first_observation_tick: int
    last_observation_tick: int

    def snapshot(self) -> ExpSMConsolidationCandidate:
        ids = tuple(self.supporting_evidence_ids)
        return ExpSMConsolidationCandidate(
            self.candidate_id, self.representative_evidence, ids, len(ids),
            self.first_observation_tick, self.last_observation_tick,
        )


class ExperienceEvidenceGrouper:
    """Conservative in-memory pre-ExpSM evidence grouping."""

    def __init__(self, config: ExperienceGroupingConfig) -> None:
        if not isinstance(config, ExperienceGroupingConfig):
            raise TypeError("config must be ExperienceGroupingConfig")
        self.config = config
        self._candidates: list[_MutableCandidate] = []
        self._observed_evidence_ids: set[str] = set()
        self._candidate_counter = 0
        self._proposal_counter = 0

    @property
    def candidates(self) -> tuple[ExpSMConsolidationCandidate, ...]:
        return tuple(candidate.snapshot() for candidate in self._candidates)

    def observe(self, evidence: ExperienceEvidence) -> GroupingResult:
        if not isinstance(evidence, ExperienceEvidence):
            raise TypeError("grouper accepts only ExperienceEvidence")
        if evidence.evidence_id in self._observed_evidence_ids:
            return GroupingResult(GroupingStatus.DUPLICATE, evidence.evidence_id)
        eligible = tuple(
            candidate for candidate in self._candidates
            if self._eligible(ExperienceEvidenceComparison.compare(
                evidence, candidate.representative_evidence,
            ))
        )
        self._observed_evidence_ids.add(evidence.evidence_id)
        if len(eligible) > 1:
            return GroupingResult(
                GroupingStatus.AMBIGUOUS, evidence.evidence_id,
                eligible_candidate_ids=tuple(item.candidate_id for item in eligible),
            )
        if len(eligible) == 1:
            candidate = eligible[0]
            candidate.supporting_evidence_ids.append(evidence.evidence_id)
            candidate.first_observation_tick = min(candidate.first_observation_tick, evidence.observation_tick)
            candidate.last_observation_tick = max(candidate.last_observation_tick, evidence.observation_tick)
            return GroupingResult(GroupingStatus.ADDED, evidence.evidence_id, candidate.candidate_id)
        self._candidate_counter += 1
        candidate = _MutableCandidate(
            candidate_id=f"candidate:{self._candidate_counter:06d}",
            representative_evidence=evidence,
            supporting_evidence_ids=[evidence.evidence_id],
            first_observation_tick=evidence.observation_tick,
            last_observation_tick=evidence.observation_tick,
        )
        self._candidates.append(candidate)
        return GroupingResult(GroupingStatus.CREATED, evidence.evidence_id, candidate.candidate_id)

    def make_proposal(self, candidate_id: str, *, current_tick: int) -> ExpSMConsolidationProposal | None:
        if not isinstance(current_tick, int) or isinstance(current_tick, bool):
            raise TypeError("current_tick must be an integer")
        if current_tick < 0:
            raise ValueError("current_tick must be >= 0")
        candidate = next((item for item in self._candidates if item.candidate_id == candidate_id), None)
        if candidate is None:
            raise KeyError(candidate_id)
        snapshot = candidate.snapshot()
        if snapshot.support_count < self.config.min_support:
            return None
        self._proposal_counter += 1
        return ExpSMConsolidationProposal(
            proposal_id=f"proposal:{self._proposal_counter:06d}",
            candidate_id=snapshot.candidate_id,
            representative_evidence_id=snapshot.representative_evidence.evidence_id,
            support_count=snapshot.support_count,
            supporting_evidence_ids=snapshot.supporting_evidence_ids,
            first_observation_tick=snapshot.first_observation_tick,
            last_observation_tick=snapshot.last_observation_tick,
            created_active_tick=current_tick,
        )

    def _eligible(self, comparison: ExperienceEvidenceComparison) -> bool:
        return (
            comparison.context_comparable
            and comparison.context_similarity is not None
            and comparison.context_similarity >= self.config.context_similarity_threshold
            and comparison.action_comparable
            and comparison.action_similarity is not None
            and comparison.action_similarity >= self.config.action_similarity_threshold
            and comparison.effect_comparable
            and comparison.effect_similarity is not None
            and comparison.effect_similarity >= self.config.effect_similarity_threshold
        )
