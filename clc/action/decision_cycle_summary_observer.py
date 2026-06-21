from collections.abc import Mapping
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.system.system_state import SystemState


DECISION_CYCLE_SUMMARY_COOLDOWN_TICKS = 6


class DecisionCycleSummaryObserver:
    """Observation-only compact summary of one decision/audit/guard cycle."""

    module_name = "decision_cycle_summary_observer"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.summary_kind = pattern_registry.id("decision_cycle_summary")
        self.status_patterns = {
            "clean_selection": pattern_registry.id("decision_cycle_clean_selection"),
            "value_influenced_selection": pattern_registry.id("decision_cycle_value_influenced_selection"),
            "guard_constrained_selection": pattern_registry.id("decision_cycle_guard_constrained_selection"),
            "uncertain_selection": pattern_registry.id("decision_cycle_uncertain_selection"),
            "risky_or_constrained_selection": pattern_registry.id("decision_cycle_risky_or_constrained_selection"),
        }
        self.confidence_patterns = {
            "high": pattern_registry.id("decision_cycle_confidence_high"),
            "medium": pattern_registry.id("decision_cycle_confidence_medium"),
            "low": pattern_registry.id("decision_cycle_confidence_low"),
        }
        self.flag_patterns = {
            "value_promoted_selected": pattern_registry.id("decision_cycle_value_promoted_selected"),
            "value_penalized_selected": pattern_registry.id("decision_cycle_value_penalized_selected"),
            "guard_blocked_high_score": pattern_registry.id("decision_cycle_guard_blocked_high_score"),
            "narrow_decision": pattern_registry.id("decision_cycle_narrow_decision"),
            "tie_like_decision": pattern_registry.id("decision_cycle_tie_like_decision"),
            "single_candidate": pattern_registry.id("decision_cycle_single_candidate"),
            "target_specific_value_used": pattern_registry.id("decision_cycle_target_specific_value_used"),
            "no_value_influence": pattern_registry.id("decision_cycle_no_value_influence"),
            "guard_summary_missing": pattern_registry.id("decision_cycle_guard_summary_missing"),
        }
        self._emitted: dict[str, tuple[int, tuple[object, ...]]] = {}

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        guard_by_decision = {
            str(audit.get("source_decision_id", "")): audit
            for audit in memory.get_recent_action_guard_audits(12)
            if audit.get("source_decision_id")
        }
        operations: list[ContextOperation] = []
        for decision_audit in memory.get_recent_decision_audits(12):
            decision_id = str(decision_audit.get("source_decision_id", ""))
            if not decision_id:
                continue
            guard_audit = guard_by_decision.get(decision_id)
            signature = _signature(decision_audit, guard_audit)
            previous = self._emitted.get(decision_id)
            if previous is not None:
                previous_tick, previous_signature = previous
                if previous_signature == signature and tick - previous_tick < DECISION_CYCLE_SUMMARY_COOLDOWN_TICKS:
                    continue
            self._emitted[decision_id] = (tick, signature)
            operations.append(self._operation(tick, decision_audit, guard_audit, system_state))
        if len(self._emitted) > 256:
            self._emitted = dict(list(self._emitted.items())[-128:])
        return operations

    def _operation(
        self,
        tick: int,
        decision_audit: dict[str, Any],
        guard_audit: dict[str, Any] | None,
        system_state: SystemState,
    ) -> ContextOperation:
        selected = _selected_summary(decision_audit.get("selected", {}), self.pattern_registry)
        decision_summary = _decision_summary(decision_audit)
        guard_summary = _guard_summary(guard_audit)
        cycle_status = _cycle_status(decision_summary, guard_summary)
        cycle_confidence = _cycle_confidence(decision_summary, guard_summary)
        flags = _flags(decision_summary, guard_summary)
        payload = {
            "decision_cycle_summary_id": self.id_gen.next("decision_cycle_summary"),
            "summary_kind": self.summary_kind,
            "source_decision_id": decision_audit.get("source_decision_id"),
            "source_decision_audit_id": decision_audit.get("decision_audit_id"),
            "source_action_guard_audit_id": guard_audit.get("action_guard_audit_id") if isinstance(guard_audit, dict) else None,
            "system_mode_at_summary": system_state.mode,
            "selected": selected,
            "decision_summary": decision_summary,
            "guard_summary": guard_summary,
            "cycle_summary": {
                "cycle_status": cycle_status,
                "cycle_status_pattern_id": self.status_patterns[cycle_status],
                "cycle_confidence": cycle_confidence,
                "cycle_confidence_pattern_id": self.confidence_patterns.get(cycle_confidence),
                "flags": flags,
                "flag_pattern_ids": [self.flag_patterns[flag] for flag in flags if flag in self.flag_patterns],
            },
            "memory_modified": False,
            "permanent_memory_modified": False,
            "expsm_modified": False,
            "akbsm_modified": False,
            "activation": 0.45,
            "ttl": 8,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.DECISION_CYCLE_SUMMARY,
            tick,
            self.module_name,
            None,
            payload,
        )


def _selected_summary(selected: object, registry: PatternRegistry) -> dict[str, Any]:
    selected = dict(selected) if isinstance(selected, Mapping) else {}
    action_pattern = str(selected.get("action_pattern") or selected.get("action_pattern_id") or "")
    return {
        "action_pattern_id": action_pattern,
        "action_pattern_name": selected.get("action_debug_name") or registry.debug_name(action_pattern),
        "source": selected.get("source"),
        "final_score": _round_or_none(selected.get("final_score")),
        "source_experience_id": selected.get("source_experience_id"),
        "source_activation_id": selected.get("source_activation_id"),
        "source_mechanism_search_id": selected.get("source_mechanism_search_id"),
        "source_target_pattern_id": selected.get("source_target_pattern_id"),
        "source_target_kind": selected.get("source_target_kind"),
        "source_mechanism_purpose": selected.get("source_mechanism_purpose"),
    }


def _decision_summary(decision_audit: dict[str, Any]) -> dict[str, Any]:
    audit = decision_audit.get("audit", {})
    if not isinstance(audit, Mapping):
        audit = {}
    alternatives = decision_audit.get("alternatives", ())
    alternatives_count = len(alternatives) if isinstance(alternatives, (list, tuple)) else 0
    return {
        "audit_confidence": audit.get("audit_confidence"),
        "score_margin": _round_or_none(audit.get("score_margin")),
        "alternatives_count": alternatives_count,
        "value_influence": audit.get("value_influence"),
        "value_influence_scope": audit.get("value_scope"),
        "value_delta": _round_or_none(audit.get("value_delta")),
        "value_ranking_effect": audit.get("ranking_effect"),
    }


def _guard_summary(guard_audit: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(guard_audit, Mapping):
        return {"available": False}
    summary = guard_audit.get("summary", {})
    if not isinstance(summary, Mapping):
        summary = {}
    selected = guard_audit.get("selected", {})
    if not isinstance(selected, Mapping):
        selected = {}
    return {
        "available": True,
        "action_guard_audit_id": guard_audit.get("action_guard_audit_id"),
        "proposed_count": summary.get("proposed_count", 0),
        "allowed_count": summary.get("allowed_count", 0),
        "blocked_count": summary.get("blocked_count", 0),
        "guard_effect": summary.get("guard_effect"),
        "severity": summary.get("severity"),
        "selected_guard_status": selected.get("guard_status"),
        "selected_guard_reason": selected.get("guard_reason"),
        "blocked_candidates": list(guard_audit.get("blocked_candidates", ()))[:8],
    }


def _cycle_confidence(decision_summary: dict[str, Any], guard_summary: dict[str, Any]) -> str:
    audit_confidence = decision_summary.get("audit_confidence")
    guard_severity = guard_summary.get("severity")
    if audit_confidence == "clear_win" and guard_severity in {"none", "low", None}:
        return "high"
    if audit_confidence in {"narrow_win", "single_candidate"} or guard_severity == "medium":
        return "medium"
    if audit_confidence == "tie_like" or guard_severity == "high":
        return "low"
    return "unknown"


def _flags(decision_summary: dict[str, Any], guard_summary: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    value_influence = decision_summary.get("value_influence")
    value_scope = decision_summary.get("value_influence_scope")
    audit_confidence = decision_summary.get("audit_confidence")
    guard_effect = guard_summary.get("guard_effect")
    if value_influence == "positive_bonus":
        flags.append("value_promoted_selected")
    if value_influence == "negative_penalty":
        flags.append("value_penalized_selected")
    if guard_effect == "blocked_high_score_candidate":
        flags.append("guard_blocked_high_score")
    if audit_confidence == "narrow_win":
        flags.append("narrow_decision")
    if audit_confidence == "tie_like":
        flags.append("tie_like_decision")
    if audit_confidence == "single_candidate":
        flags.append("single_candidate")
    if value_influence in {"none_or_tiny", None}:
        flags.append("no_value_influence")
    if value_scope == "target_specific":
        flags.append("target_specific_value_used")
    if not guard_summary.get("available"):
        flags.append("guard_summary_missing")
    return flags


def _cycle_status(decision_summary: dict[str, Any], guard_summary: dict[str, Any]) -> str:
    guard_severity = guard_summary.get("severity")
    guard_effect = guard_summary.get("guard_effect")
    value_influence = decision_summary.get("value_influence")
    audit_confidence = decision_summary.get("audit_confidence")
    if guard_severity == "high":
        return "risky_or_constrained_selection"
    if guard_effect in {"blocked_high_score_candidate", "selected_was_only_allowed_candidate"}:
        return "guard_constrained_selection"
    if value_influence in {"positive_bonus", "negative_penalty"}:
        return "value_influenced_selection"
    if audit_confidence in {"narrow_win", "tie_like"}:
        return "uncertain_selection"
    return "clean_selection"


def _signature(decision_audit: dict[str, Any], guard_audit: dict[str, Any] | None) -> tuple[object, ...]:
    audit = decision_audit.get("audit", {})
    if not isinstance(audit, Mapping):
        audit = {}
    guard_summary = guard_audit.get("summary", {}) if isinstance(guard_audit, Mapping) else {}
    if not isinstance(guard_summary, Mapping):
        guard_summary = {}
    return (
        decision_audit.get("decision_audit_id"),
        audit.get("audit_confidence"),
        audit.get("score_margin"),
        audit.get("value_influence"),
        audit.get("value_scope"),
        audit.get("value_delta"),
        audit.get("ranking_effect"),
        guard_audit.get("action_guard_audit_id") if isinstance(guard_audit, Mapping) else None,
        guard_summary.get("guard_effect"),
        guard_summary.get("severity"),
        guard_summary.get("blocked_count"),
    )


def _round_or_none(value: object) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None
