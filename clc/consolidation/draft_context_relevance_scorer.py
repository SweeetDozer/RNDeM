from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.markers import OperationMarker
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.consolidation.draft_semantic_filters import (
    competing_draft_family,
    different_modality_without_link,
    draft_core_families,
    is_confirmed_outcome,
    is_draft_technical_noise,
    is_generic_draft_context,
    matches_draft_core_family,
)


MAX_FINAL_IF_PATTERNS = 5
MIN_RELEVANCE_SCORE = 0.25


class DraftContextRelevanceScorer:
    """Scores candidate IF patterns by proximity to the reviewed causal chain."""

    module_name = "draft_context_relevance_scorer"

    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.pattern_registry = pattern_registry

    def score_if_patterns(
        self,
        candidate_patterns: list[str],
        review_payload: dict[str, Any],
        memory: ContextMemory,
        active_field: ActiveContextField,
    ) -> list[dict[str, Any]]:
        source = _SourceIndex(memory)
        source_candidate = source.consolidation_candidate(review_payload.get("source_consolidation_candidate_id"))
        experience_candidates = source.experience_candidates(source_candidate.get("candidate_ids", ()) if source_candidate else ())
        evidence = _Evidence.from_sources(review_payload, source_candidate, experience_candidates, source, memory, active_field)
        core_families = _core_families(review_payload, self.pattern_registry)
        outcome_confirmed = _outcome_confirmed(review_payload, source_candidate, experience_candidates, self.pattern_registry)
        records: list[dict[str, Any]] = []
        for pattern_id in _unique([str(pattern) for pattern in candidate_patterns if pattern]):
            if is_draft_technical_noise(self.pattern_registry, pattern_id):
                records.append(
                    {
                        "pattern": pattern_id,
                        "score": 0.0,
                        "sources": [],
                        "reasons": ["rejected_technical_pattern"],
                        "rejected": True,
                    }
                )
                continue
            score = 0.0
            sources: list[str] = []
            reasons: list[str] = []
            if pattern_id in evidence.label_patterns:
                score += 0.35
                sources.append("label")
                reasons.append("source_label")
            if pattern_id in evidence.core_prediction_patterns:
                score += 0.35
                sources.append("core_prediction")
                reasons.append("source_core_prediction")
            if pattern_id in evidence.trace_context_patterns:
                score += 0.25
                sources.append("trace_context")
                reasons.append("source_causal_trace_context")
            if pattern_id in evidence.near_outcome_active_patterns:
                score += 0.20
                sources.append("near_outcome_active")
                reasons.append("active_near_source_outcome")
            family_match = matches_draft_core_family(self.pattern_registry, pattern_id, core_families)
            if family_match:
                score += 0.30
                reasons.append("matches_core_effect_family")
            if pattern_id in evidence.core_prediction_patterns and outcome_confirmed:
                score += 0.25
                reasons.append("predicted_pattern_confirmed")
            active_only = pattern_id in evidence.current_active_patterns and not (
                pattern_id in evidence.label_patterns
                or pattern_id in evidence.core_prediction_patterns
                or pattern_id in evidence.trace_context_patterns
                or pattern_id in evidence.near_outcome_active_patterns
            )
            if active_only:
                score -= 0.15
                sources.append("active_field")
                reasons.append("active_field_only_penalty")
            if not family_match:
                score -= 0.20
                reasons.append("unrelated_to_core_family")
            if different_modality_without_link(self.pattern_registry, pattern_id, core_families):
                score -= 0.10
                reasons.append("different_modality_without_link")
            if competing_draft_family(self.pattern_registry, pattern_id, core_families):
                score -= 0.20
                reasons.append("competing_action_family_penalty")
            if is_generic_draft_context(self.pattern_registry, pattern_id):
                score -= 0.05
                reasons.append("generic_pattern_penalty")
            records.append(
                {
                    "pattern": pattern_id,
                    "score": round(max(0.0, min(1.0, score)), 3),
                    "sources": _unique(sources),
                    "reasons": _unique(reasons),
                }
            )
        return sorted(records, key=lambda record: record["score"], reverse=True)


class _SourceIndex:
    def __init__(self, memory: ContextMemory) -> None:
        self._events_by_id = {event.op_id: event for event in memory.events}
        self._consolidation_by_id = {
            item.get("consolidation_candidate_id"): item
            for item in memory.get_recent_consolidation_candidates(64)
            if item.get("consolidation_candidate_id")
        }
        self._experience_by_id = {
            item.get("candidate_id"): item
            for item in memory.get_recent_experience_candidates(128)
            if item.get("candidate_id")
        }

    def event_payload(self, event_id: str, markers: set[OperationMarker]) -> dict[str, Any]:
        event = self._events_by_id.get(event_id)
        if event is None or event.marker not in markers:
            return {}
        return dict(event.payload)

    def consolidation_candidate(self, candidate_id: Any) -> dict[str, Any] | None:
        if not candidate_id:
            return None
        return self._consolidation_by_id.get(candidate_id)

    def experience_candidates(self, candidate_ids: Any) -> list[dict[str, Any]]:
        if not isinstance(candidate_ids, (list, tuple)):
            return []
        return [
            self._experience_by_id[candidate_id]
            for candidate_id in candidate_ids
            if candidate_id in self._experience_by_id
        ]


class _Evidence:
    def __init__(
        self,
        label_patterns: set[str],
        core_prediction_patterns: set[str],
        trace_context_patterns: set[str],
        near_outcome_active_patterns: set[str],
        current_active_patterns: set[str],
    ) -> None:
        self.label_patterns = label_patterns
        self.core_prediction_patterns = core_prediction_patterns
        self.trace_context_patterns = trace_context_patterns
        self.near_outcome_active_patterns = near_outcome_active_patterns
        self.current_active_patterns = current_active_patterns

    @classmethod
    def from_sources(
        cls,
        review_payload: dict[str, Any],
        source_candidate: dict[str, Any] | None,
        experience_candidates: list[dict[str, Any]],
        source: _SourceIndex,
        memory: ContextMemory,
        active_field: ActiveContextField,
    ) -> "_Evidence":
        containers = [review_payload, source_candidate or {}, *experience_candidates]
        label_patterns = set(_label_patterns(containers, source))
        core_prediction_patterns = set(_core_prediction_patterns(containers, source))
        trace_context_patterns = set(_trace_context_patterns(source_candidate, experience_candidates, memory))
        near_outcome_active_patterns = set(_near_outcome_active_patterns(source_candidate, experience_candidates))
        current_active_patterns = {pattern.pattern_id for pattern in active_field.get_top_patterns(limit=12)}
        return cls(
            label_patterns=label_patterns,
            core_prediction_patterns=core_prediction_patterns,
            trace_context_patterns=trace_context_patterns,
            near_outcome_active_patterns=near_outcome_active_patterns,
            current_active_patterns=current_active_patterns,
        )


def _label_patterns(containers: list[dict[str, Any]], source: _SourceIndex) -> list[str]:
    event_ids: list[str] = []
    for container in containers:
        event_ids.extend(_context_values(container, "label_event_ids"))
    patterns: list[str] = []
    for event_id in _unique(event_ids):
        label = source.event_payload(event_id, {OperationMarker.LABEL})
        if not label:
            continue
        for key in ("label_kind", "label_pattern_id"):
            if label.get(key):
                patterns.append(str(label[key]))
        patterns.extend(str(pattern) for pattern in label.get("matched_patterns", ()) if pattern)
    return _unique(patterns)


def _core_prediction_patterns(containers: list[dict[str, Any]], source: _SourceIndex) -> list[str]:
    patterns: list[str] = []
    event_ids: list[str] = []
    for container in containers:
        core_chain = container.get("core_chain", {})
        if isinstance(core_chain, dict):
            patterns.extend(str(pattern) for pattern in core_chain.get("predicted_patterns", ()) if pattern)
        event_ids.extend(_context_values(container, "nearby_prediction_event_ids"))
        event_ids.extend(_context_values(container, "prediction_event_ids"))
    for event_id in _unique(event_ids):
        prediction = source.event_payload(event_id, {OperationMarker.PREDICTION})
        if not prediction:
            continue
        for key in ("prediction_kind", "prediction_pattern_id"):
            if prediction.get(key):
                patterns.append(str(prediction[key]))
        patterns.extend(str(pattern) for pattern in prediction.get("predicted_patterns", ()) if pattern)
    return _unique(patterns)


def _trace_context_patterns(
    source_candidate: dict[str, Any] | None,
    experience_candidates: list[dict[str, Any]],
    memory: ContextMemory,
) -> list[str]:
    frame_ids = _context_values(source_candidate, "frame_ids")
    patterns = _context_values(source_candidate, "active_patterns")
    for candidate in experience_candidates:
        frame_ids.extend(_context_values(candidate, "frame_ids"))
        patterns.extend(_context_values(candidate, "active_patterns"))
    frame_by_id = {frame.frame_id: frame for frame in memory.all_frames()}
    for frame_id in _unique(frame_ids):
        frame = frame_by_id.get(frame_id)
        if frame is not None:
            patterns.extend(str(pattern) for pattern in frame.activations.keys())
    return _unique(patterns)


def _near_outcome_active_patterns(
    source_candidate: dict[str, Any] | None,
    experience_candidates: list[dict[str, Any]],
) -> list[str]:
    patterns = _context_values(source_candidate, "active_patterns")
    for candidate in experience_candidates:
        patterns.extend(_context_values(candidate, "active_patterns"))
    return _unique(patterns)


def _core_families(review_payload: dict[str, Any], pattern_registry: PatternRegistry) -> set[str]:
    core_chain = review_payload.get("core_chain", {})
    pattern_ids: list[str] = []
    for key in ("decision_patterns", "effect_patterns"):
        pattern_ids.extend(str(pattern) for pattern in core_chain.get(key, ()) if pattern)
    return draft_core_families(pattern_registry, pattern_ids)


def _outcome_confirmed(
    review_payload: dict[str, Any],
    source_candidate: dict[str, Any] | None,
    experience_candidates: list[dict[str, Any]],
    pattern_registry: PatternRegistry,
) -> bool:
    containers = [review_payload, source_candidate or {}, *experience_candidates]
    for container in containers:
        core_chain = container.get("core_chain", {})
        if not isinstance(core_chain, dict):
            continue
        for pattern_id in core_chain.get("outcome_patterns", ()):
            if str(pattern_id):
                # The scorer only has ids; exact confirmed/non-confirmed split is by debug name below.
                pass
    return any(
        item.get("source_outcome_status") == "confirmed"
        for item in experience_candidates
    ) or _contains_confirmed_outcome(review_payload, pattern_registry)


def _contains_confirmed_outcome(review_payload: dict[str, Any], pattern_registry: PatternRegistry) -> bool:
    core_chain = review_payload.get("core_chain", {})
    if not isinstance(core_chain, dict):
        return False
    return any(is_confirmed_outcome(pattern_registry, str(pattern)) for pattern in core_chain.get("outcome_patterns", ()))


def _context_values(container: dict[str, Any] | None, key: str) -> list[str]:
    if not container:
        return []
    values: list[str] = []
    for parent_key in ("context_summary", "context_refs", "core_chain"):
        parent = container.get(parent_key, {})
        if isinstance(parent, dict) and isinstance(parent.get(key), (list, tuple)):
            values.extend(str(value) for value in parent[key] if value)
    if isinstance(container.get(key), (list, tuple)):
        values.extend(str(value) for value in container[key] if value)
    return values



def _unique(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(values) if value]
