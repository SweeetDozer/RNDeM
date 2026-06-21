from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.experience.candidate_group import CandidateGroup
from clc.field.active_context_field import ActiveContextField


MIN_SUPPORT = 2
MIN_AVG_CONFIDENCE = 0.45
HIGH_CONFIDENCE = 0.85
STRONG_VALENCE = 0.65


class ExperienceCandidateBuffer:
    """Groups similar experience candidates before any permanent memory write."""

    module_name = "experience_candidate_buffer"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.candidate_kind = pattern_registry.id("consolidation_candidate")
        self._processed_candidate_ids: set[str] = set()
        self._groups_by_signature: dict[tuple[Any, ...], CandidateGroup] = {}

    def run(self, tick: int, memory: ContextMemory, active_field: ActiveContextField) -> list[ContextOperation]:
        del active_field
        changed_groups: dict[tuple[Any, ...], CandidateGroup] = {}
        for candidate in memory.get_recent_experience_candidates(24):
            candidate_id = candidate.get("candidate_id")
            if not candidate_id or candidate_id in self._processed_candidate_ids:
                continue
            self._processed_candidate_ids.add(candidate_id)
            group = self._add_to_group(tick, candidate)
            changed_groups[group.signature] = group
        operations: list[ContextOperation] = []
        for group in changed_groups.values():
            if self._is_ready(group) and self._should_emit(group):
                group.emitted_ready = True
                group.last_emitted_support_count = group.support_count
                operations.append(self._operation(tick, group))
        return operations

    def debug_snapshot(self) -> list[dict[str, Any]]:
        return [
            group.debug_snapshot()
            for group in sorted(self._groups_by_signature.values(), key=lambda item: item.support_count, reverse=True)
        ]

    def _add_to_group(self, tick: int, candidate: dict[str, Any]) -> CandidateGroup:
        signature = _signature(candidate)
        group = self._groups_by_signature.get(signature)
        if group is None:
            group = CandidateGroup(
                group_id=self.id_gen.next("group"),
                signature=signature,
                first_seen_tick=tick,
                last_seen_tick=tick,
            )
            self._groups_by_signature[signature] = group
        candidate_id = candidate["candidate_id"]
        group.candidate_ids.add(candidate_id)
        group.source_event_ids.add(candidate.get("source_outcome_event_id", ""))
        group.support_count += 1
        group.confidence_sum += float(candidate.get("confidence", 0.5))
        group.priority_sum += float(candidate.get("priority", 0.5))
        group.valence_sum += _candidate_valence(candidate)
        group.last_seen_tick = tick
        core_chain = candidate.get("core_chain") or candidate.get("pattern_refs", {})
        for key in group.core_chain:
            group.core_chain[key].update(core_chain.get(key, ()))
        context_refs = candidate.get("context_refs", {})
        group.context_summary["label_event_ids"].update(context_refs.get("label_event_ids", ()))
        group.context_summary["frame_ids"].update(context_refs.get("frame_ids", ()))
        group.context_summary["active_patterns"].update(context_refs.get("active_patterns", ()))
        return group

    def _is_ready(self, group: CandidateGroup) -> bool:
        if group.support_count >= MIN_SUPPORT and group.avg_confidence >= MIN_AVG_CONFIDENCE:
            return True
        if group.avg_confidence >= HIGH_CONFIDENCE:
            return True
        if abs(group.avg_valence) >= STRONG_VALENCE and group.support_count >= MIN_SUPPORT:
            return True
        if group.signature[0] == "negative_candidate" and group.support_count >= MIN_SUPPORT:
            return True
        return False

    def _should_emit(self, group: CandidateGroup) -> bool:
        if not group.emitted_ready:
            return True
        return group.support_count > group.last_emitted_support_count

    def _operation(self, tick: int, group: CandidateGroup) -> ContextOperation:
        activation = max(0.1, min(1.0, group.avg_confidence))
        payload = {
            "consolidation_candidate_id": self.id_gen.next("cons_cand"),
            "candidate_kind": self.candidate_kind,
            "group_id": group.group_id,
            "core_signature": _signature_for_payload(group.signature),
            "support_count": group.support_count,
            "avg_confidence": round(group.avg_confidence, 3),
            "avg_valence": round(group.avg_valence, 3),
            "avg_priority": round(group.avg_priority, 3),
            "candidate_ids": sorted(group.candidate_ids),
            "source_event_ids": sorted(event_id for event_id in group.source_event_ids if event_id),
            "suggested_target": "ExpSM",
            "write_status": "pending_memory_consolidation",
            "core_chain": {
                key: sorted(values)
                for key, values in group.core_chain.items()
            },
            "context_summary": {
                key: sorted(values)
                for key, values in group.context_summary.items()
            },
            "pattern_refs": {
                key: sorted(values)
                for key, values in group.core_chain.items()
            },
            "activation": round(activation, 3),
            "ttl": 12,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.CONSOLIDATION_CANDIDATE,
            tick,
            self.module_name,
            None,
            payload,
        )


def _signature(candidate: dict[str, Any]) -> tuple[Any, ...]:
    refs = candidate.get("core_chain") or candidate.get("pattern_refs", {})
    return (
        candidate.get("candidate_status", ""),
        tuple(sorted(refs.get("decision_patterns", ()))),
        tuple(sorted(refs.get("effect_patterns", ()))),
        tuple(sorted(refs.get("predicted_patterns", ()))),
        tuple(sorted(refs.get("outcome_patterns", ()))),
    )


def _signature_for_payload(signature: tuple[Any, ...]) -> list[Any]:
    return [signature[0], list(signature[1]), list(signature[2]), list(signature[3]), list(signature[4])]


def _candidate_valence(candidate: dict[str, Any]) -> float:
    tone_result = candidate.get("tone_result", {})
    if "valence" in tone_result:
        return float(tone_result["valence"])
    status = candidate.get("candidate_status")
    if status == "positive_candidate":
        return 0.5
    if status == "negative_candidate":
        return -0.5
    return 0.1
