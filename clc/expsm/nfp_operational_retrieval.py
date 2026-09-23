from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from clc.experience.expsm_representation import (
    ExpSMRecordAdapter,
    LegacyOperationalRecord,
    MalformedRecord,
    NFPNativeOperationalRecordV1,
    SerializedNFPActionV1,
    SerializedNFPContextV1,
    SerializedObservedEffectV1,
    UnsupportedRecord,
)
from clc.patterns import NFPWindow, PatternOrigin
from clc.patterns.similarity import NFPSimilarityResult


class NFPExpSMRetrievalStatus(str, Enum):
    OK = "ok"
    NO_COMPARABLE_RECORDS = "no_comparable_records"
    INVALID_QUERY = "invalid_query"
    STORE_INVALID = "store_invalid"
    UNSUPPORTED_MEMORY_PRESENT = "unsupported_memory_present"


@dataclass(frozen=True)
class NFPExpSMRetrievalQuery:
    current_context: NFPWindow

    def __post_init__(self) -> None:
        if not isinstance(self.current_context, NFPWindow):
            raise TypeError("current_context must be NFPWindow")

    @property
    def is_authorized(self) -> bool:
        return all(frame.origin is PatternOrigin.EXTERNAL_SENSORY for frame in self.current_context.frames)


@dataclass(frozen=True)
class NFPExpSMRetrievalConfig:
    context_similarity_threshold: float

    def __post_init__(self) -> None:
        threshold = float(self.context_similarity_threshold)
        if not math.isfinite(threshold) or threshold < 0.0 or threshold > 1.0:
            raise ValueError("context_similarity_threshold must be in [0.0, 1.0]")
        object.__setattr__(self, "context_similarity_threshold", threshold)


class LivePersistentNFPContextSimilarity:
    """Direct structural comparison without reconstructing stored occurrences."""

    @staticmethod
    def compare(live: NFPWindow, stored: SerializedNFPContextV1) -> NFPSimilarityResult:
        if not isinstance(live, NFPWindow):
            raise TypeError("live context must be NFPWindow")
        if not isinstance(stored, SerializedNFPContextV1):
            raise TypeError("stored context must be SerializedNFPContextV1")
        if live.modality.value != stored.modality:
            return NFPSimilarityResult(False, None, "different_modality")
        if live.topology.shape != stored.topology:
            return NFPSimilarityResult(False, None, "different_topology")
        if live.length != len(stored.frames):
            return NFPSimilarityResult(False, None, "different_frame_count")
        size = live.topology.size
        scores = tuple(
            1.0 - sum(abs(a - b) for a, b in zip(frame.values, values)) / size
            for frame, values in zip(live.frames, stored.frames)
        )
        score = sum(max(0.0, min(1.0, value)) for value in scores) / live.length
        return NFPSimilarityResult(True, max(0.0, min(1.0, score)), None)


@dataclass(frozen=True)
class NFPExpSMRetrievalCandidate:
    candidate_id: str
    source_experience_id: str
    context_similarity: float
    action: SerializedNFPActionV1
    effect: SerializedObservedEffectV1
    hits: int
    misses: int
    confidence: float
    repeatability: float
    creation_provenance: object | None = None


@dataclass(frozen=True)
class NFPExpSMRetrievalResult:
    status: NFPExpSMRetrievalStatus
    candidates: tuple[NFPExpSMRetrievalCandidate, ...] = ()
    reason: str = ""
    legacy_records_seen: int = 0


@dataclass(frozen=True)
class ActivatedNFPExpSMCandidate:
    activation_id: str
    retrieval_candidate_id: str
    source_experience_id: str
    context_similarity: float
    activation: float
    action: SerializedNFPActionV1
    effect: SerializedObservedEffectV1
    hits: int
    misses: int
    confidence: float
    effective_confidence: float
    repeatability: float
    viability: float


@dataclass(frozen=True)
class SelectedNFPExpSMExperience:
    selection_id: str
    activation_id: str
    retrieval_candidate_id: str
    source_experience_id: str
    context_similarity: float
    activation: float
    action: SerializedNFPActionV1
    effect: SerializedObservedEffectV1
    confidence: float
    repeatability: float
    viability: float


class NFPExpSMRetriever:
    """Fresh, strict, read-only mixed-store retrieval service."""

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)

    def retrieve(
        self,
        query: NFPExpSMRetrievalQuery,
        config: NFPExpSMRetrievalConfig,
    ) -> NFPExpSMRetrievalResult:
        if not isinstance(query, NFPExpSMRetrievalQuery) or not query.is_authorized:
            return NFPExpSMRetrievalResult(NFPExpSMRetrievalStatus.INVALID_QUERY, reason="external_sensory_required")
        if not isinstance(config, NFPExpSMRetrievalConfig):
            raise TypeError("config must be NFPExpSMRetrievalConfig")
        try:
            raw_store = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return NFPExpSMRetrievalResult(NFPExpSMRetrievalStatus.STORE_INVALID, reason=str(exc))
        if not isinstance(raw_store, dict):
            return NFPExpSMRetrievalResult(NFPExpSMRetrievalStatus.STORE_INVALID, reason="store must be an object")
        experiences = raw_store.get("experience")
        reflexes = raw_store.get("reflexes")
        if not isinstance(experiences, dict) or not isinstance(reflexes, dict):
            return NFPExpSMRetrievalResult(NFPExpSMRetrievalStatus.STORE_INVALID, reason="experience and reflexes must be objects")

        parsed = tuple(ExpSMRecordAdapter.parse(record_id, raw) for record_id, raw in experiences.items())
        malformed = next((record for record in parsed if isinstance(record, MalformedRecord)), None)
        if malformed is not None:
            return NFPExpSMRetrievalResult(NFPExpSMRetrievalStatus.STORE_INVALID, reason="; ".join(malformed.errors))
        unsupported = next((record for record in parsed if isinstance(record, UnsupportedRecord)), None)
        if unsupported is not None:
            return NFPExpSMRetrievalResult(
                NFPExpSMRetrievalStatus.UNSUPPORTED_MEMORY_PRESENT,
                reason=unsupported.reason,
            )

        legacy_count = sum(isinstance(record, LegacyOperationalRecord) for record in parsed)
        candidates: list[NFPExpSMRetrievalCandidate] = []
        comparable_count = 0
        for record in parsed:
            if not isinstance(record, NFPNativeOperationalRecordV1):
                continue
            native = record.record
            comparison = LivePersistentNFPContextSimilarity.compare(query.current_context, native.context)
            if not comparison.comparable:
                continue
            comparable_count += 1
            assert comparison.score is not None
            if comparison.score < config.context_similarity_threshold:
                continue
            candidates.append(
                NFPExpSMRetrievalCandidate(
                    candidate_id=f"nfp_retrieval_candidate:{len(candidates) + 1}",
                    source_experience_id=native.record_id,
                    context_similarity=comparison.score,
                    action=native.action,
                    effect=native.effect,
                    hits=native.operational.hits,
                    misses=native.operational.misses,
                    confidence=native.operational.confidence,
                    repeatability=native.operational.repeatability,
                    creation_provenance=native.creation_metadata,
                )
            )
        if candidates:
            return NFPExpSMRetrievalResult(NFPExpSMRetrievalStatus.OK, tuple(candidates), legacy_records_seen=legacy_count)
        reason = "below_native_threshold" if comparable_count else "no_structurally_comparable_native_records"
        return NFPExpSMRetrievalResult(
            NFPExpSMRetrievalStatus.NO_COMPARABLE_RECORDS,
            reason=reason,
            legacy_records_seen=legacy_count,
        )
