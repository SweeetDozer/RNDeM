from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


class MemoryWriteReviewModule:
    """Reviews consolidation candidates for future memory writing without writing."""

    module_name = "memory_write_review_module"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.review_kind = pattern_registry.id("memory_write_review")
        self.status_patterns = {
            "approved_for_expsm": pattern_registry.id("memory_review_approved_for_expsm"),
            "needs_more_support": pattern_registry.id("memory_review_needs_more_support"),
            "rejected_duplicate": pattern_registry.id("memory_review_rejected_duplicate"),
            "rejected_incomplete_core": pattern_registry.id("memory_review_rejected_incomplete_core"),
            "rejected_low_value": pattern_registry.id("memory_review_rejected_low_value"),
            "rejected_unstable": pattern_registry.id("memory_review_rejected_unstable"),
        }
        self.reason_patterns = {
            "sufficient_support": pattern_registry.id("memory_review_sufficient_support"),
            "high_confidence": pattern_registry.id("memory_review_high_confidence"),
            "positive_valence": pattern_registry.id("memory_review_positive_valence"),
            "negative_valence": pattern_registry.id("memory_review_negative_valence"),
            "low_value": pattern_registry.id("memory_review_low_value"),
            "incomplete_core": pattern_registry.id("memory_review_incomplete_core"),
            "duplicate": pattern_registry.id("memory_review_duplicate"),
            "unstable": pattern_registry.id("memory_review_unstable"),
        }
        self._reviewed_support_by_group: dict[str, int] = {}
        self._approved_support_by_signature: dict[tuple[Any, ...], int] = {}

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        del active_field
        if system_state.mode != "consolidation":
            return []
        operations: list[ContextOperation] = []
        for candidate in memory.get_recent_consolidation_candidates(16):
            if candidate.get("write_status") != "pending_memory_consolidation":
                continue
            group_id = candidate.get("group_id")
            support_count = int(candidate.get("support_count", 0))
            if not group_id:
                continue
            if self._reviewed_support_by_group.get(group_id, -1) >= support_count:
                continue
            self._reviewed_support_by_group[group_id] = support_count
            payload = self._review_payload(candidate)
            operations.append(
                ContextOperation(
                    self.id_gen.next("op"),
                    OperationMarker.MEMORY_WRITE_REVIEW,
                    tick,
                    self.module_name,
                    None,
                    payload,
                )
            )
        return operations

    def _review_payload(self, candidate: dict[str, Any]) -> dict[str, Any]:
        status, reasons, score = self._classify(candidate)
        write_status = "approved_pending_writer" if status == "approved_for_expsm" else "not_ready"
        if status.startswith("rejected"):
            write_status = "rejected"
        payload = {
            "review_id": self.id_gen.next("mem_review"),
            "review_kind": self.review_kind,
            "source_consolidation_candidate_id": candidate.get("consolidation_candidate_id"),
            "source_group_id": candidate.get("group_id"),
            "core_signature": list(candidate.get("core_signature", ())),
            "review_status": status,
            "review_status_pattern_id": self.status_patterns[status],
            "suggested_target": candidate.get("suggested_target", "ExpSM"),
            "decision_score": round(score, 3),
            "reasons": reasons,
            "support_count": int(candidate.get("support_count", 0)),
            "avg_confidence": float(candidate.get("avg_confidence", 0.0)),
            "avg_valence": float(candidate.get("avg_valence", 0.0)),
            "avg_priority": float(candidate.get("avg_priority", 0.0)),
            "core_chain": dict(candidate.get("core_chain", {})),
            "write_status": write_status,
            "activation": round(max(0.25, min(1.0, score)), 3),
            "ttl": 14,
        }
        if status == "approved_for_expsm":
            self._approved_support_by_signature[_signature_key(candidate.get("core_signature", ())) ] = int(candidate.get("support_count", 0))
        return payload

    def _classify(self, candidate: dict[str, Any]) -> tuple[str, list[str], float]:
        support_count = int(candidate.get("support_count", 0))
        avg_confidence = float(candidate.get("avg_confidence", 0.0))
        avg_valence = float(candidate.get("avg_valence", 0.0))
        avg_priority = float(candidate.get("avg_priority", 0.0))
        core_chain = candidate.get("core_chain", {})
        core_signature = _signature_key(candidate.get("core_signature", ()))
        approved_support = self._approved_support_by_signature.get(core_signature)
        if approved_support is not None and approved_support >= support_count:
            return "rejected_duplicate", [self.reason_patterns["duplicate"]], 0.55
        if not _has_complete_core(core_chain):
            return "rejected_incomplete_core", [self.reason_patterns["incomplete_core"]], 0.45
        if avg_confidence < 0.35:
            return "rejected_unstable", [self.reason_patterns["unstable"]], avg_confidence
        if support_count < 2 and avg_confidence < 0.9:
            return "needs_more_support", [self.reason_patterns["high_confidence"] if avg_confidence >= 0.75 else self.reason_patterns["sufficient_support"]], 0.42 + avg_confidence * 0.2
        if abs(avg_valence) < 0.08 and avg_priority < 0.35:
            return "rejected_low_value", [self.reason_patterns["low_value"]], 0.4
        if support_count >= 2 and avg_confidence >= 0.55 and avg_valence > 0.15:
            return (
                "approved_for_expsm",
                [self.reason_patterns["sufficient_support"], self.reason_patterns["positive_valence"]],
                min(1.0, avg_confidence * 0.7 + avg_valence * 0.25 + support_count * 0.03),
            )
        if support_count >= 2 and avg_confidence >= 0.5 and avg_valence < -0.15:
            return (
                "approved_for_expsm",
                [self.reason_patterns["sufficient_support"], self.reason_patterns["negative_valence"]],
                min(1.0, avg_confidence * 0.7 + abs(avg_valence) * 0.25 + support_count * 0.03),
            )
        return "needs_more_support", [self.reason_patterns["sufficient_support"]], 0.45


def _has_complete_core(core_chain: dict[str, Any]) -> bool:
    decisions = list(core_chain.get("decision_patterns", ()))
    effects = list(core_chain.get("effect_patterns", ()))
    predictions = list(core_chain.get("predicted_patterns", ()))
    outcomes = list(core_chain.get("outcome_patterns", ()))
    return bool(outcomes and ((decisions and effects) or predictions))


def _signature_key(signature: Any) -> tuple[Any, ...]:
    if not isinstance(signature, (list, tuple)):
        return (signature,)
    items: list[Any] = []
    for item in signature:
        if isinstance(item, (list, tuple)):
            items.append(tuple(item))
        else:
            items.append(item)
    return tuple(items)
