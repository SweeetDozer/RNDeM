from dataclasses import dataclass
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.markers import OperationMarker
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField


MAX_IF_PATTERNS = 8
MAX_ACTIVE_CONTEXT_PATTERNS = 5
MAX_LABEL_PATTERNS = 5


@dataclass(frozen=True)
class DraftInputContext:
    if_patterns: list[str]
    source: str
    filtered_out_count: int
    fallback_used: bool

    def as_metadata(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "if_pattern_count": len(self.if_patterns),
            "filtered_out_count": self.filtered_out_count,
            "fallback_used": self.fallback_used,
        }


class DraftInputContextEnricher:
    """Builds compact situation-pattern context for safe ExpSM draft records."""

    module_name = "draft_input_context_enricher"

    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.pattern_registry = pattern_registry
        self.tone_ids = {
            "tension_high": pattern_registry.id("tone_tension_high"),
            "fatigue_high": pattern_registry.id("tone_fatigue_high"),
            "risk_sensitivity_high": pattern_registry.id("tone_risk_sensitivity_high"),
            "pain_high": pattern_registry.id("tone_pain_high"),
            "stability_low": pattern_registry.id("tone_stability_low"),
            "integrity_low": pattern_registry.id("tone_integrity_low"),
        }

    def build_if_patterns(
        self,
        review_payload: dict[str, Any],
        memory: ContextMemory,
        active_field: ActiveContextField,
    ) -> DraftInputContext:
        source = _SourceIndex(memory)
        source_candidate = source.consolidation_candidate(review_payload.get("source_consolidation_candidate_id"))
        source_experience_candidates = source.experience_candidates(source_candidate.get("candidate_ids", ()) if source_candidate else ())
        filtered_out_count = 0
        selected: list[str] = []
        selected_source = "none"

        label_patterns, filtered = self._label_patterns(source_candidate, source_experience_candidates, source)
        filtered_out_count += filtered
        selected.extend(label_patterns)
        if label_patterns:
            selected_source = "labels/context_refs"

        prediction_patterns, filtered = self._prediction_patterns(review_payload, source_candidate, source_experience_candidates, source)
        filtered_out_count += filtered
        selected.extend(prediction_patterns)
        if prediction_patterns and selected_source == "none":
            selected_source = "predictions/core_chain"

        frame_patterns, filtered = self._frame_patterns(source_candidate, source_experience_candidates, memory)
        filtered_out_count += filtered
        selected.extend(frame_patterns)
        if frame_patterns and selected_source == "none":
            selected_source = "frames/context_refs"

        active_patterns, filtered = self._active_patterns(source_candidate, source_experience_candidates, active_field)
        filtered_out_count += filtered
        selected.extend(active_patterns)
        if active_patterns and selected_source == "none":
            selected_source = "active_field/context_summary"

        selected = _unique(selected)[:MAX_IF_PATTERNS]
        fallback_used = False
        if len(selected) < MAX_IF_PATTERNS:
            tone_patterns = self._tone_patterns(memory)
            room = MAX_IF_PATTERNS - len(selected)
            selected.extend(pattern for pattern in tone_patterns if pattern not in selected and len(selected) < MAX_IF_PATTERNS)
            if tone_patterns and selected_source == "none":
                selected_source = "tone_state"
                fallback_used = True
            elif tone_patterns and len(selected) <= room:
                fallback_used = True

        return DraftInputContext(
            if_patterns=selected[:MAX_IF_PATTERNS],
            source=selected_source,
            filtered_out_count=filtered_out_count,
            fallback_used=fallback_used,
        )

    def _label_patterns(
        self,
        source_candidate: dict[str, Any] | None,
        experience_candidates: list[dict[str, Any]],
        source: "_SourceIndex",
    ) -> tuple[list[str], int]:
        event_ids = _context_values(source_candidate, "label_event_ids")
        for candidate in experience_candidates:
            event_ids.extend(_context_values(candidate, "label_event_ids"))
        patterns: list[str] = []
        filtered = 0
        for event_id in _unique(event_ids):
            label = source.event_payload(event_id)
            if not label:
                continue
            candidates = [
                label.get("label_kind"),
                label.get("label_pattern_id"),
            ]
            candidates.extend(label.get("matched_patterns", ()))
            accepted, rejected = self._filter_patterns(candidates)
            patterns.extend(accepted)
            filtered += rejected
            if len(patterns) >= MAX_LABEL_PATTERNS:
                break
        return _unique(patterns)[:MAX_LABEL_PATTERNS], filtered

    def _prediction_patterns(
        self,
        review_payload: dict[str, Any],
        source_candidate: dict[str, Any] | None,
        experience_candidates: list[dict[str, Any]],
        source: "_SourceIndex",
    ) -> tuple[list[str], int]:
        patterns: list[str] = []
        filtered = 0
        for container in [review_payload, source_candidate or {}, *experience_candidates]:
            core_chain = container.get("core_chain", {})
            accepted, rejected = self._filter_patterns(core_chain.get("predicted_patterns", ()))
            patterns.extend(accepted)
            filtered += rejected
        event_ids = _context_values(source_candidate, "nearby_prediction_event_ids")
        for candidate in experience_candidates:
            event_ids.extend(_context_values(candidate, "nearby_prediction_event_ids"))
        for event_id in _unique(event_ids):
            prediction = source.event_payload(event_id)
            if not prediction:
                continue
            candidates = [prediction.get("prediction_kind"), prediction.get("prediction_pattern_id")]
            candidates.extend(prediction.get("predicted_patterns", ()))
            accepted, rejected = self._filter_patterns(candidates)
            patterns.extend(accepted)
            filtered += rejected
        return _unique(patterns), filtered

    def _frame_patterns(
        self,
        source_candidate: dict[str, Any] | None,
        experience_candidates: list[dict[str, Any]],
        memory: ContextMemory,
    ) -> tuple[list[str], int]:
        frame_ids = _context_values(source_candidate, "frame_ids")
        for candidate in experience_candidates:
            frame_ids.extend(_context_values(candidate, "frame_ids"))
        frame_by_id = {frame.frame_id: frame for frame in memory.all_frames()}
        patterns: list[str] = []
        filtered = 0
        for frame_id in _unique(frame_ids):
            frame = frame_by_id.get(frame_id)
            if frame is None:
                continue
            accepted, rejected = self._filter_patterns(frame.activations.keys())
            patterns.extend(accepted)
            filtered += rejected
        return _unique(patterns), filtered

    def _active_patterns(
        self,
        source_candidate: dict[str, Any] | None,
        experience_candidates: list[dict[str, Any]],
        active_field: ActiveContextField,
    ) -> tuple[list[str], int]:
        candidates = _context_values(source_candidate, "active_patterns")
        for candidate in experience_candidates:
            candidates.extend(_context_values(candidate, "active_patterns"))
        if not candidates:
            candidates = [pattern.pattern_id for pattern in active_field.get_top_patterns(MAX_ACTIVE_CONTEXT_PATTERNS)]
        accepted, filtered = self._filter_patterns(candidates)
        return _unique(accepted)[:MAX_ACTIVE_CONTEXT_PATTERNS], filtered

    def _tone_patterns(self, memory: ContextMemory) -> list[str]:
        tone = memory.get_current_tone()
        patterns: list[str] = []
        if tone.tension >= 0.65:
            patterns.append(self.tone_ids["tension_high"])
        if tone.fatigue >= 0.6:
            patterns.append(self.tone_ids["fatigue_high"])
        if tone.risk_sensitivity >= 0.7:
            patterns.append(self.tone_ids["risk_sensitivity_high"])
        if tone.pain >= 0.25:
            patterns.append(self.tone_ids["pain_high"])
        if tone.stability <= 0.45:
            patterns.append(self.tone_ids["stability_low"])
        if tone.integrity <= 0.85:
            patterns.append(self.tone_ids["integrity_low"])
        return patterns

    def _filter_patterns(self, values: Any) -> tuple[list[str], int]:
        accepted: list[str] = []
        filtered = 0
        for value in values or ():
            if not value:
                continue
            pattern_id = str(value)
            if self._is_context_pattern(pattern_id):
                accepted.append(pattern_id)
            else:
                filtered += 1
        return accepted, filtered

    def _is_context_pattern(self, pattern_id: str) -> bool:
        debug_name = self.pattern_registry.debug_name(pattern_id)
        excluded_exact = {
            "memory_draft_written",
            "memory_draft_pending_commit",
            "memory_write_review",
            "memory_review_approved_for_expsm",
            "consolidation_pressure",
            "consolidation_candidate",
            "experience_candidate",
        }
        excluded_prefixes = (
            "action_",
            "state_consolidation_",
            "state_pending_candidates_",
            "state_context_load_",
            "system_mode_",
            "consolidation_",
            "memory_",
            "homeostasis_",
            "learnability_",
            "outcome_",
            "experience_",
        )
        if debug_name in excluded_exact:
            return False
        return not debug_name.startswith(excluded_prefixes)


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

    def event_payload(self, event_id: str) -> dict[str, Any]:
        event = self._events_by_id.get(event_id)
        if event is None:
            return {}
        if event.marker not in {OperationMarker.LABEL, OperationMarker.PREDICTION}:
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


def _context_values(container: dict[str, Any] | None, key: str) -> list[str]:
    if not container:
        return []
    values: list[str] = []
    for parent_key in ("context_summary", "context_refs"):
        parent = container.get(parent_key, {})
        if isinstance(parent, dict) and isinstance(parent.get(key), (list, tuple)):
            values.extend(str(value) for value in parent[key] if value)
    if isinstance(container.get(key), (list, tuple)):
        values.extend(str(value) for value in container[key] if value)
    return values


def _unique(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(values) if value]
