from collections.abc import Mapping
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.system.system_state import SystemState


ACTION_GUARD_AUDIT_COOLDOWN_TICKS = 6
MAX_GUARD_AUDIT_CANDIDATES = 8


class ActionGuardAuditObserver:
    """Observation-only audit of guard effects on action candidates."""

    module_name = "action_guard_audit_observer"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.audit_kind = pattern_registry.id("action_guard_audit_observed")
        self.effect_patterns = {
            "no_blocked_candidates": pattern_registry.id("action_guard_audit_no_blocked_candidates"),
            "blocked_low_score_only": pattern_registry.id("action_guard_audit_blocked_low_score_only"),
            "blocked_high_score_candidate": pattern_registry.id("action_guard_audit_blocked_high_score_candidate"),
            "selected_was_only_allowed_candidate": pattern_registry.id("action_guard_audit_selected_only_allowed"),
        }
        self.status_patterns = {
            "allowed": pattern_registry.id("action_guard_audit_allowed_candidate"),
            "blocked": pattern_registry.id("action_guard_audit_blocked_candidate"),
        }
        self.severity_patterns = {
            "none": pattern_registry.id("action_guard_audit_severity_none"),
            "low": pattern_registry.id("action_guard_audit_severity_low"),
            "medium": pattern_registry.id("action_guard_audit_severity_medium"),
            "high": pattern_registry.id("action_guard_audit_severity_high"),
        }
        self._last_emitted: dict[str, tuple[int, tuple[object, ...]]] = {}

    def run(self, tick: int, memory: ContextMemory, system_state: SystemState) -> list[ContextOperation]:
        operations: list[ContextOperation] = []
        decision_audits = {
            audit.get("source_decision_id"): audit
            for audit in memory.get_recent_decision_audits(8)
            if audit.get("_event_tick") == tick
        }
        for decision in memory.get_recent_decisions(8):
            if decision.get("_event_tick") != tick:
                continue
            decision_id = str(decision.get("decision_id", ""))
            if not decision_id:
                continue
            snapshot = _candidate_snapshot(decision)
            if not snapshot:
                continue
            signature = _signature(snapshot)
            previous = self._last_emitted.get(decision_id)
            if previous is not None:
                previous_tick, previous_signature = previous
                if previous_signature == signature and tick - previous_tick < ACTION_GUARD_AUDIT_COOLDOWN_TICKS:
                    continue
            self._last_emitted[decision_id] = (tick, signature)
            operations.append(self._build_operation(tick, decision, snapshot, decision_audits.get(decision_id), system_state))
        return operations

    def _build_operation(
        self,
        tick: int,
        decision: dict[str, Any],
        snapshot: list[dict[str, Any]],
        decision_audit: dict[str, Any] | None,
        system_state: SystemState,
    ) -> ContextOperation:
        selected = _selected_candidate(decision, snapshot, self.pattern_registry)
        selected_score = _score(selected)
        allowed = [_format_candidate(item, self.pattern_registry, selected_score) for item in snapshot if item.get("guard_status") == "allowed"]
        blocked = [_format_candidate(item, self.pattern_registry, selected_score) for item in snapshot if item.get("guard_status") == "blocked"]
        allowed.sort(key=lambda item: float(item.get("final_score") or 0.0), reverse=True)
        blocked.sort(key=lambda item: float(item.get("final_score") or 0.0), reverse=True)
        summary = self._summary(selected, allowed, blocked)
        payload = {
            "action_guard_audit_id": self.id_gen.next("action_guard_audit"),
            "audit_kind": self.audit_kind,
            "source_decision_id": decision.get("decision_id"),
            "source_decision_audit_id": decision_audit.get("decision_audit_id") if isinstance(decision_audit, dict) else None,
            "mode": system_state.mode or decision.get("system_mode_at_selection"),
            "summary": summary,
            "selected": selected,
            "allowed_candidates": allowed[:MAX_GUARD_AUDIT_CANDIDATES],
            "blocked_candidates": blocked[:MAX_GUARD_AUDIT_CANDIDATES],
            "highest_allowed_candidate": allowed[0] if allowed else None,
            "highest_blocked_candidate": blocked[0] if blocked else None,
            "memory_modified": False,
            "permanent_memory_modified": False,
            "expsm_modified": False,
            "akbsm_modified": False,
            "activation": 0.45,
            "ttl": 8,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.ACTION_GUARD_AUDIT_OBSERVED,
            tick,
            self.module_name,
            None,
            payload,
        )

    def _summary(
        self,
        selected: dict[str, Any],
        allowed: list[dict[str, Any]],
        blocked: list[dict[str, Any]],
    ) -> dict[str, Any]:
        selected_score = _score(selected)
        highest_blocked_score = _score(blocked[0]) if blocked else None
        if not blocked:
            effect = "no_blocked_candidates"
        elif highest_blocked_score is not None and selected_score is not None and highest_blocked_score > selected_score:
            effect = "blocked_high_score_candidate"
        elif selected and len(allowed) == 1 and len(blocked) >= 2:
            effect = "selected_was_only_allowed_candidate"
        else:
            effect = "blocked_low_score_only"
        if not blocked:
            severity = "none"
        elif effect == "blocked_high_score_candidate":
            severity = "high"
        elif len(blocked) >= 2:
            severity = "medium"
        else:
            severity = "low"
        return {
            "proposed_count": len(allowed) + len(blocked),
            "allowed_count": len(allowed),
            "blocked_count": len(blocked),
            "guard_effect": effect,
            "guard_effect_pattern": self.effect_patterns.get(effect),
            "severity": severity,
            "severity_pattern": self.severity_patterns.get(severity),
        }


def _candidate_snapshot(decision: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = decision.get("guard_candidate_audit_snapshot", ())
    if not isinstance(snapshot, (list, tuple)):
        return []
    return [dict(item) for item in snapshot if isinstance(item, Mapping)]


def _selected_candidate(
    decision: dict[str, Any],
    snapshot: list[dict[str, Any]],
    registry: PatternRegistry,
) -> dict[str, Any]:
    selected_action = decision.get("decision_pattern_id")
    selected_score = _float_or_none(decision.get("candidate_score"))
    selected_items = [
        item
        for item in snapshot
        if item.get("action_pattern_id") == selected_action and item.get("guard_status") == "allowed"
    ]
    selected_items.sort(key=lambda item: abs(float(item.get("final_score") or 0.0) - float(selected_score or 0.0)))
    if selected_items:
        return _format_candidate(selected_items[0], registry, selected_score)
    return {
        "action_pattern_id": selected_action,
        "action_pattern_name": registry.debug_name(str(selected_action)),
        "source": decision.get("source"),
        "final_score": _round_float(decision.get("candidate_score")),
        "guard_status": "allowed",
        "guard_reason": "allowed",
    }


def _format_candidate(item: dict[str, Any], registry: PatternRegistry, selected_score: float | None = None) -> dict[str, Any]:
    action_pattern = str(item.get("action_pattern_id") or item.get("action_pattern") or "")
    final_score = _round_float(item.get("final_score"))
    guard_status = str(item.get("guard_status") or "unknown")
    result = {
        "candidate_id": item.get("candidate_id"),
        "action_pattern_id": action_pattern,
        "action_pattern_name": registry.debug_name(action_pattern),
        "source": item.get("source"),
        "final_score": final_score,
        "pre_guard_final_score": _round_float(item.get("pre_guard_final_score")),
        "base_score": _base_score(item),
        "score_breakdown": _safe_value(item.get("score_breakdown", {})),
        "source_experience_id": item.get("source_experience_id"),
        "source_mechanism_search_id": item.get("source_mechanism_search_id"),
        "risk": _round_float(item.get("risk")),
        "cost": _round_float(item.get("cost")),
        "urgency": _round_float(item.get("urgency")),
        "confidence": _round_float(item.get("confidence")),
        "activation": _round_float(item.get("activation")),
        "guard_status": guard_status,
        "guard_reason": item.get("guard_reason") or ("allowed" if guard_status == "allowed" else "blocked_by_policy"),
    }
    if guard_status == "blocked" and selected_score is not None and final_score is not None:
        result["would_have_ranked_above_selected"] = final_score > selected_score
    return {key: value for key, value in result.items() if value is not None}


def _base_score(item: dict[str, Any]) -> float | None:
    breakdown = item.get("score_breakdown")
    if isinstance(breakdown, Mapping):
        return _round_float(breakdown.get("base_score"))
    return None


def _signature(snapshot: list[dict[str, Any]]) -> tuple[object, ...]:
    return tuple(
        (
            item.get("candidate_id"),
            item.get("action_pattern_id"),
            item.get("guard_status"),
            item.get("guard_reason"),
            _round_float(item.get("final_score")),
        )
        for item in snapshot
    )


def _score(item: dict[str, Any]) -> float | None:
    return _float_or_none(item.get("final_score"))


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_float(value: object) -> float | None:
    value = _float_or_none(value)
    return None if value is None else round(value, 3)


def _safe_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 3)
    return value
