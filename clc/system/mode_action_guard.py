from dataclasses import replace

from clc.action.action_candidate import ActionCandidate
from clc.action.action_scoring import score_breakdown
from clc.core.pattern_registry import PatternRegistry
from clc.system.system_state import SystemState


MIN_CONSOLIDATION_TICKS = 3


class ModeActionGuard:
    """Mode-aware final guard for internal action candidates."""

    module_name = "mode_action_guard"

    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.pattern_registry = pattern_registry
        self.actions = {
            "enter_consolidation": pattern_registry.id("action_enter_consolidation_mode"),
            "exit_consolidation": pattern_registry.id("action_exit_consolidation_mode"),
            "store_memory": pattern_registry.id("action_store_memory_candidate"),
            "commit_memory_draft": pattern_registry.id("action_commit_memory_draft"),
            "review_committed_memory_update": pattern_registry.id("action_review_committed_memory_update"),
            "update_committed_expsm": pattern_registry.id("action_update_committed_expsm_record"),
            "increase_attention": pattern_registry.id("action_increase_attention"),
            "wait_more_data": pattern_registry.id("action_wait_more_data"),
            "continue_observation": pattern_registry.id("action_continue_observation"),
            "inspect_pattern": pattern_registry.id("action_inspect_pattern"),
            "generate_more_thought": pattern_registry.id("action_generate_more_thought"),
            "reduce_load": pattern_registry.id("action_reduce_load"),
            "preserve_integrity": pattern_registry.id("action_preserve_integrity"),
        }
        self._recent_events: list[dict[str, object]] = []
        self._recent_candidate_audit: list[dict[str, object]] = []

    def is_allowed(self, action_pattern_id: str, system_state: SystemState, tick: int) -> bool:
        return self._decision(action_pattern_id, system_state, tick)[0]

    def adjust_candidate(
        self,
        candidate: ActionCandidate,
        system_state: SystemState,
        tick: int,
    ) -> ActionCandidate | None:
        allowed, reason, factor = self._decision(candidate.pattern_id, system_state, tick)
        if not allowed:
            self._record(tick, "blocked", candidate.pattern_id, reason)
            self._record_candidate_audit(tick, candidate, system_state, "blocked", reason, factor)
            return None
        if factor < 1.0:
            self._record(tick, "suppressed", candidate.pattern_id, reason)
            adjusted = replace(
                candidate,
                confidence=max(0.0, min(1.0, candidate.confidence * factor)),
                urgency=max(0.0, min(1.0, candidate.urgency * factor)),
            )
            self._record_candidate_audit(tick, adjusted, system_state, "allowed", reason, factor, original_candidate=candidate)
            return adjusted
        self._record_candidate_audit(tick, candidate, system_state, "allowed", reason, factor)
        return candidate

    def recent_events(self, tick: int, limit: int = 8) -> list[dict[str, object]]:
        return [event for event in self._recent_events if event["tick"] == tick][-limit:]

    def recent_candidate_audit(self, tick: int, limit: int = 20) -> list[dict[str, object]]:
        return [event for event in self._recent_candidate_audit if event["tick"] == tick][-limit:]

    def _decision(self, action_pattern_id: str, system_state: SystemState, tick: int) -> tuple[bool, str, float]:
        mode = system_state.mode
        elapsed = tick - system_state.mode_entered_tick
        if mode == "active":
            if action_pattern_id == self.actions["exit_consolidation"]:
                return False, "not_in_consolidation", 0.0
            return True, "active_mode_allowed", 1.0

        if mode == "consolidation":
            if action_pattern_id == self.actions["enter_consolidation"]:
                return False, "already_in_consolidation", 0.0
            if action_pattern_id == self.actions["exit_consolidation"]:
                if elapsed < MIN_CONSOLIDATION_TICKS:
                    return False, "minimum_consolidation_duration", 0.0
                return True, "consolidation_exit_allowed", 1.0
            if action_pattern_id in {
                self.actions["store_memory"],
                self.actions["commit_memory_draft"],
                self.actions["review_committed_memory_update"],
                self.actions["update_committed_expsm"],
                self.actions["inspect_pattern"],
                self.actions["generate_more_thought"],
                self.actions["reduce_load"],
                self.actions["preserve_integrity"],
            }:
                return True, "consolidation_internal_allowed", 1.0
            if action_pattern_id in {
                self.actions["increase_attention"],
                self.actions["wait_more_data"],
                self.actions["continue_observation"],
            }:
                return True, "consolidation_mode_low_external_attention", 0.35
            return False, "consolidation_mode_blocked", 0.0

        if mode == "recovery":
            if action_pattern_id in {self.actions["enter_consolidation"], self.actions["exit_consolidation"]}:
                return False, "recovery_mode_transition_block", 0.0
            return True, "recovery_mode_low_priority", 0.45

        return True, "unknown_mode_default_allowed", 0.7

    def _record(self, tick: int, event_type: str, pattern_id: str, reason: str) -> None:
        item = {
            "tick": tick,
            "event_type": event_type,
            "pattern_id": pattern_id,
            "debug_name": self.pattern_registry.debug_name(pattern_id),
            "reason": reason,
        }
        if item in self._recent_events:
            return
        self._recent_events.append(item)
        self._recent_events = self._recent_events[-64:]

    def _record_candidate_audit(
        self,
        tick: int,
        candidate: ActionCandidate,
        system_state: SystemState,
        guard_status: str,
        reason: str,
        factor: float,
        original_candidate: ActionCandidate | None = None,
    ) -> None:
        original_candidate = original_candidate or candidate
        source = dict(candidate.source_metadata)
        original_breakdown = score_breakdown(original_candidate)
        final_breakdown = score_breakdown(candidate)
        item = {
            "tick": tick,
            "mode": system_state.mode,
            "candidate_id": candidate.candidate_id,
            "action_pattern_id": candidate.pattern_id,
            "action_pattern_name": self.pattern_registry.debug_name(candidate.pattern_id),
            "source": source.get("source"),
            "guard_status": guard_status,
            "guard_reason": _normalize_guard_reason(reason, system_state.mode, guard_status),
            "raw_guard_reason": reason,
            "guard_factor": round(float(factor), 3),
            "final_score": round(final_breakdown["final_score"], 3),
            "score_breakdown": final_breakdown,
            "pre_guard_final_score": round(original_breakdown["final_score"], 3),
            "activation": round(candidate.activation, 3),
            "confidence": round(candidate.confidence, 3),
            "urgency": round(candidate.urgency, 3),
            "risk": round(candidate.risk, 3),
            "cost": round(candidate.cost, 3),
            "source_experience_id": source.get("source_experience_id"),
            "source_activation_id": source.get("source_activation_id"),
            "source_mechanism_search_id": source.get("source_mechanism_search_id"),
        }
        if item in self._recent_candidate_audit:
            return
        self._recent_candidate_audit.append(item)
        self._recent_candidate_audit = self._recent_candidate_audit[-128:]


def _normalize_guard_reason(reason: str, mode: str, guard_status: str) -> str:
    if guard_status == "allowed":
        return "allowed"
    if reason in {"not_in_consolidation", "already_in_consolidation", "minimum_consolidation_duration"}:
        return "blocked_by_mode"
    if mode == "consolidation":
        return "blocked_by_consolidation_mode"
    if mode == "recovery":
        return "blocked_by_recovery_mode"
    if reason == "missing_action":
        return "blocked_by_missing_action"
    if "risk" in reason:
        return "blocked_by_risk"
    if "policy" in reason:
        return "blocked_by_policy"
    if "unknown" in reason:
        return "blocked_by_unknown_action"
    return "blocked_by_internal_only_mode"
