from collections.abc import Mapping
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


class ExpSMCompetitionObserver:
    """Chronicles soft competition between ExpSM-sourced action candidates."""

    module_name = "expsm_competition_observer"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.observation_kind = pattern_registry.id("expsm_competition_observed")

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        del active_field
        if system_state.mode != "active":
            return []
        observed_decision_ids = {
            str(observation.get("decision_id"))
            for observation in memory.get_recent_expsm_competition_observations(24)
            if observation.get("decision_id")
        }
        operations: list[ContextOperation] = []
        for decision in memory.get_recent_decisions(8):
            if decision.get("_event_tick") != tick:
                continue
            decision_id = str(decision.get("decision_id", ""))
            if not decision_id or decision_id in observed_decision_ids:
                continue
            if decision.get("source") != "expsm_activation":
                continue
            payload = self._payload(decision)
            if payload is None:
                continue
            observed_decision_ids.add(decision_id)
            operations.append(
                ContextOperation(
                    self.id_gen.next("op"),
                    OperationMarker.EXPSM_COMPETITION_OBSERVED,
                    tick,
                    self.module_name,
                    None,
                    payload,
                )
            )
        return operations

    def _payload(self, decision: dict[str, Any]) -> dict[str, Any] | None:
        candidates = [
            dict(candidate)
            for candidate in decision.get("expsm_candidate_snapshot", ())
            if isinstance(candidate, Mapping)
        ]
        unique_sources = {
            (str(candidate.get("experience_id", "")), str(candidate.get("activation_id", "")))
            for candidate in candidates
        }
        unique_sources.discard(("", ""))
        if len(candidates) < 2 or len(unique_sources) < 2:
            return None
        selected = self._selected_candidate(decision, candidates)
        if selected is None:
            return None
        alternatives = [
            self._alternative_summary(candidate)
            for candidate in candidates
            if not _same_source(candidate, selected)
        ]
        if not alternatives:
            return None
        action_patterns = {str(candidate.get("action_pattern", "")) for candidate in [selected, *alternatives] if candidate.get("action_pattern")}
        same_action_pattern = len(action_patterns) == 1
        return {
            "competition_observation_id": self.id_gen.next("expsm_competition"),
            "observation_kind": self.observation_kind,
            "decision_id": decision.get("decision_id"),
            "selected_action": decision.get("selected_action") or decision.get("decision_pattern_id"),
            "selected": self._selected_summary(selected, decision),
            "alternatives": alternatives,
            "candidate_count": len(candidates),
            "same_action_pattern": same_action_pattern,
            "unused_records_punished": False,
            "memory_modified": False,
            "permanent_memory_modified": False,
            "activation": 0.65,
            "ttl": 12,
        }

    def _selected_candidate(self, decision: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        decision_source = (
            str(decision.get("source_experience_id", "")),
            str(decision.get("source_activation_id", "")),
        )
        decision_action = str(decision.get("decision_pattern_id", ""))
        for candidate in candidates:
            if candidate.get("selected"):
                return candidate
        for candidate in candidates:
            if (
                str(candidate.get("experience_id", "")),
                str(candidate.get("activation_id", "")),
            ) == decision_source and str(candidate.get("action_pattern", "")) == decision_action:
                return candidate
        return None

    def _selected_summary(self, candidate: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        return {
            "experience_id": str(candidate.get("experience_id", decision.get("source_experience_id", ""))),
            "activation_id": str(candidate.get("activation_id", decision.get("source_activation_id", ""))),
            "action_pattern": str(candidate.get("action_pattern", decision.get("decision_pattern_id", ""))),
            "final_score": _score(candidate, decision),
            "score_breakdown": dict(candidate.get("score_breakdown") or decision.get("score_breakdown") or {}),
            "match_score": _float_or_none(candidate.get("match_score", decision.get("source_match_score"))),
            "viability": _float_or_none(candidate.get("viability", decision.get("source_viability"))),
            "effective_confidence": _float_or_none(candidate.get("effective_confidence", decision.get("source_effective_confidence"))),
        }

    def _alternative_summary(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "experience_id": str(candidate.get("experience_id", "")),
            "activation_id": str(candidate.get("activation_id", "")),
            "action_pattern": str(candidate.get("action_pattern", "")),
            "final_score": _score(candidate),
            "score_breakdown": dict(candidate.get("score_breakdown") or {}),
            "match_score": _float_or_none(candidate.get("match_score")),
            "viability": _float_or_none(candidate.get("viability")),
            "effective_confidence": _float_or_none(candidate.get("effective_confidence")),
            "unused_not_punished": True,
        }


def _same_source(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        str(a.get("experience_id", "")),
        str(a.get("activation_id", "")),
    ) == (
        str(b.get("experience_id", "")),
        str(b.get("activation_id", "")),
    )


def _score(candidate: dict[str, Any], fallback: dict[str, Any] | None = None) -> float:
    value = candidate.get("final_score")
    if value is None and fallback is not None:
        value = fallback.get("candidate_score")
    return round(float(value or 0.0), 3)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None
