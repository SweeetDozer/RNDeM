from clc.action.action_candidate_field import ActionCandidateField
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField


class ModeTransitionCleanup:
    """Removes stale transition-action traces after a committed mode change."""

    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.pattern_registry = pattern_registry
        self.actions = {
            "enter": pattern_registry.id("action_enter_consolidation_mode"),
            "exit": pattern_registry.id("action_exit_consolidation_mode"),
            "store_memory": pattern_registry.id("action_store_memory_candidate"),
        }
        self._recent_events: list[dict[str, object]] = []

    def cleanup(
        self,
        tick: int,
        from_mode: str,
        to_mode: str,
        active_field: ActiveContextField,
        action_candidate_field: ActionCandidateField,
    ) -> dict[str, object]:
        pattern_ids = self._patterns_for_transition(from_mode, to_mode)
        removed_active: list[str] = []
        removed_candidates: list[str] = []
        for pattern_id in pattern_ids:
            before_active = any(pattern.pattern_id == pattern_id for pattern in active_field.get_patterns_above(0.0))
            active_field.suppress(pattern_id, 1.0)
            if before_active:
                removed_active.append(pattern_id)
            if action_candidate_field.remove(pattern_id):
                removed_candidates.append(pattern_id)
        event = {
            "tick": tick,
            "from_mode": from_mode,
            "to_mode": to_mode,
            "removed_active_patterns": removed_active,
            "removed_action_candidates": removed_candidates,
        }
        if removed_active or removed_candidates:
            self._recent_events.append(event)
            self._recent_events = self._recent_events[-16:]
        return event

    def recent_events(self, tick: int, limit: int = 4) -> list[dict[str, object]]:
        return [event for event in self._recent_events if event["tick"] == tick][-limit:]

    def debug_name(self, pattern_id: str) -> str:
        return self.pattern_registry.debug_name(pattern_id)

    def _patterns_for_transition(self, from_mode: str, to_mode: str) -> set[str]:
        if from_mode == "active" and to_mode == "consolidation":
            return {self.actions["enter"]}
        if from_mode == "consolidation" and to_mode == "recovery":
            return {self.actions["enter"], self.actions["exit"], self.actions["store_memory"]}
        if from_mode == "recovery" and to_mode == "active":
            return {self.actions["enter"], self.actions["exit"]}
        if to_mode == "consolidation":
            return {self.actions["enter"]}
        if to_mode == "recovery":
            return {self.actions["enter"], self.actions["exit"], self.actions["store_memory"]}
        if to_mode == "active":
            return {self.actions["enter"], self.actions["exit"]}
        return set()
