from collections.abc import Mapping
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.system.system_state import SystemState


MAX_AUDIT_ALTERNATIVES = 8


class DecisionAuditObserver:
    """Observation-only audit of selected internal decisions."""

    module_name = "decision_audit_observer"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.audit_kind = pattern_registry.id("decision_audit_observed")
        self.confidence_patterns = {
            "clear_win": pattern_registry.id("decision_audit_clear_win"),
            "narrow_win": pattern_registry.id("decision_audit_narrow_win"),
            "tie_like": pattern_registry.id("decision_audit_tie_like"),
            "single_candidate": pattern_registry.id("decision_audit_single_candidate"),
        }
        self.ranking_patterns = {
            "promoted": pattern_registry.id("decision_audit_value_promoted"),
            "demoted": pattern_registry.id("decision_audit_value_demoted"),
            "unchanged": pattern_registry.id("decision_audit_value_unchanged"),
        }
        self.influence_patterns = {
            "positive_bonus": pattern_registry.id("decision_audit_value_positive_bonus"),
            "negative_penalty": pattern_registry.id("decision_audit_value_negative_penalty"),
            "none_or_tiny": pattern_registry.id("decision_audit_value_none_or_tiny"),
        }
        self.scope_patterns = {
            "target_specific": pattern_registry.id("decision_audit_target_specific_value"),
            "generic_fallback": pattern_registry.id("decision_audit_generic_value"),
            "no_value": pattern_registry.id("decision_audit_no_value"),
        }
        self._observed_decision_ids: set[str] = set()

    def run(self, tick: int, memory: ContextMemory, system_state: SystemState | None = None) -> list[ContextOperation]:
        operations: list[ContextOperation] = []
        for decision in memory.get_recent_decisions(8):
            if decision.get("_event_tick") != tick:
                continue
            decision_id = str(decision.get("decision_id", ""))
            if not decision_id or decision_id in self._observed_decision_ids:
                continue
            self._observed_decision_ids.add(decision_id)
            operations.append(self._build_operation(tick, decision, system_state))
        return operations

    def _build_operation(
        self,
        tick: int,
        decision: dict[str, Any],
        system_state: SystemState | None,
    ) -> ContextOperation:
        selected = _selected_snapshot(decision, self.pattern_registry)
        alternatives = _alternative_snapshots(decision, selected, self.pattern_registry)
        audit = self._audit(selected, alternatives, decision)
        payload = {
            "decision_audit_id": self.id_gen.next("decision_audit"),
            "audit_kind": self.audit_kind,
            "source_decision_id": decision.get("decision_id"),
            "system_mode_at_audit": system_state.mode if system_state is not None else decision.get("system_mode_at_selection"),
            "selected": selected,
            "alternatives": alternatives,
            "audit": audit,
            "activation": 0.45,
            "ttl": 8,
            "permanent_memory_modified": False,
            "selector_modified": False,
            "candidate_field_modified": False,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.DECISION_AUDIT_OBSERVED,
            tick,
            self.module_name,
            None,
            payload,
        )

    def _audit(
        self,
        selected: dict[str, Any],
        alternatives: list[dict[str, Any]],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        selected_score = _float_or_none(selected.get("final_score"))
        best_alt_score = _float_or_none(alternatives[0].get("final_score")) if alternatives else None
        margin = None if selected_score is None or best_alt_score is None else round(selected_score - best_alt_score, 3)
        confidence = _audit_confidence(margin, bool(alternatives))
        source_type = _selected_source_type(selected.get("source"))
        value_delta = _value_delta(selected)
        influence = _value_influence(value_delta)
        scope = _value_scope(selected)
        ranks = _rank_effect(decision, selected)
        ranking_effect = ranks.get("ranking_effect", "unknown")
        return {
            "score_margin": margin,
            "audit_confidence": confidence,
            "audit_confidence_pattern": self.confidence_patterns[confidence],
            "selected_source_type": source_type,
            "value_delta": value_delta,
            "value_influence": influence,
            "value_influence_pattern": self.influence_patterns[influence],
            "value_scope": scope,
            "value_scope_pattern": self.scope_patterns[scope],
            "selected_base_rank": ranks.get("base_rank"),
            "selected_adjusted_rank": ranks.get("adjusted_rank"),
            "selected_final_rank": ranks.get("final_rank"),
            "ranking_effect": ranking_effect,
            "ranking_effect_pattern": self.ranking_patterns.get(ranking_effect),
        }


def _selected_snapshot(decision: dict[str, Any], registry: PatternRegistry) -> dict[str, Any]:
    selected = _selected_from_candidate_snapshot(decision)
    if selected is None:
        selected = dict(decision)
        selected["action_pattern"] = decision.get("decision_pattern_id")
        selected["final_score"] = decision.get("candidate_score")
    action_pattern = str(selected.get("action_pattern") or selected.get("decision_pattern_id") or "")
    selected["action_pattern"] = action_pattern
    selected["action_debug_name"] = registry.debug_name(action_pattern)
    selected["source"] = _selected_source_type(selected.get("source"))
    selected["final_score"] = _round_float(selected.get("final_score"))
    return _audit_item(selected)


def _selected_from_candidate_snapshot(decision: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = decision.get("decision_candidate_audit_snapshot", ())
    if not isinstance(snapshot, (list, tuple)):
        return None
    for item in snapshot:
        if isinstance(item, Mapping) and item.get("selected"):
            return dict(item)
    return None


def _alternative_snapshots(
    decision: dict[str, Any],
    selected: dict[str, Any],
    registry: PatternRegistry,
) -> list[dict[str, Any]]:
    selected_candidate_id = selected.get("candidate_id")
    snapshot = decision.get("decision_candidate_audit_snapshot", ())
    if not isinstance(snapshot, (list, tuple)):
        return []
    alternatives: list[dict[str, Any]] = []
    for item in snapshot:
        if not isinstance(item, Mapping):
            continue
        if item.get("selected") or (selected_candidate_id and item.get("candidate_id") == selected_candidate_id):
            continue
        alt = dict(item)
        action_pattern = str(alt.get("action_pattern") or "")
        alt["action_debug_name"] = registry.debug_name(action_pattern)
        alt["source"] = _selected_source_type(alt.get("source"))
        alt["final_score"] = _round_float(alt.get("final_score"))
        alternatives.append(_audit_item(alt))
    alternatives.sort(key=lambda item: float(item.get("final_score") or 0.0), reverse=True)
    return alternatives[:MAX_AUDIT_ALTERNATIVES]


def _audit_item(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "candidate_id",
        "action_pattern",
        "action_debug_name",
        "source",
        "final_score",
        "activation",
        "confidence",
        "urgency",
        "risk",
        "cost",
        "source_experience_id",
        "source_activation_id",
        "source_mechanism_search_id",
        "source_target_pattern_id",
        "source_target_kind",
        "source_mechanism_purpose",
        "source_base_mechanism_score",
        "source_value_adjusted_score",
        "source_mechanism_score",
        "source_value_scoring_mode",
        "source_target_specific_value_bonus",
        "source_target_specific_value_penalty",
        "source_generic_value_bonus",
        "source_generic_value_penalty",
        "score_breakdown",
    )
    return {key: _safe_value(item.get(key)) for key in keys if key in item and item.get(key) is not None}


def _audit_confidence(margin: float | None, has_alternatives: bool) -> str:
    if not has_alternatives:
        return "single_candidate"
    if margin is None:
        return "tie_like"
    if margin >= 0.20:
        return "clear_win"
    if margin >= 0.05:
        return "narrow_win"
    return "tie_like"


def _selected_source_type(source: object) -> str:
    if source == "expsm_activation":
        return "expsm_activation"
    if source == "expsm_mechanism_search":
        return "expsm_mechanism_search"
    if source in {None, "", "baseline", "internal", "baseline/internal"}:
        return "baseline/internal"
    return "unknown"


def _value_delta(selected: dict[str, Any]) -> float | None:
    adjusted = _float_or_none(selected.get("source_value_adjusted_score"))
    base = _float_or_none(selected.get("source_base_mechanism_score"))
    if adjusted is None or base is None:
        return None
    return round(adjusted - base, 3)


def _value_influence(delta: float | None) -> str:
    if delta is None or abs(delta) < 0.01:
        return "none_or_tiny"
    if delta > 0.0:
        return "positive_bonus"
    return "negative_penalty"


def _value_scope(selected: dict[str, Any]) -> str:
    mode = selected.get("source_value_scoring_mode")
    if mode == "target_specific":
        return "target_specific"
    if mode == "generic_fallback":
        return "generic_fallback"
    return "no_value"


def _rank_effect(decision: dict[str, Any], selected: dict[str, Any]) -> dict[str, object]:
    snapshot = decision.get("decision_candidate_audit_snapshot", ())
    if not isinstance(snapshot, (list, tuple)):
        return {"ranking_effect": "unknown"}
    mechanisms = [
        dict(item)
        for item in snapshot
        if isinstance(item, Mapping)
        and item.get("source") == "expsm_mechanism_search"
        and _float_or_none(item.get("source_base_mechanism_score")) is not None
        and _float_or_none(item.get("source_value_adjusted_score")) is not None
    ]
    selected_candidate_id = selected.get("candidate_id")
    if not mechanisms or not selected_candidate_id:
        return {"ranking_effect": "unknown"}
    base_rank = _rank_of(mechanisms, selected_candidate_id, "source_base_mechanism_score")
    adjusted_rank = _rank_of(mechanisms, selected_candidate_id, "source_value_adjusted_score")
    final_rank = _rank_of(mechanisms, selected_candidate_id, "final_score")
    if base_rank is None or adjusted_rank is None:
        effect = "unknown"
    elif adjusted_rank < base_rank:
        effect = "promoted"
    elif adjusted_rank > base_rank:
        effect = "demoted"
    else:
        effect = "unchanged"
    return {
        "base_rank": base_rank,
        "adjusted_rank": adjusted_rank,
        "final_rank": final_rank,
        "ranking_effect": effect,
    }


def _rank_of(items: list[dict[str, Any]], candidate_id: object, key: str) -> int | None:
    ranked = sorted(items, key=lambda item: float(item.get(key) or 0.0), reverse=True)
    for index, item in enumerate(ranked, start=1):
        if item.get("candidate_id") == candidate_id:
            return index
    return None


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
