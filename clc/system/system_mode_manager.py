from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


MIN_CONSOLIDATION_TICKS = 3
MAX_CONSOLIDATION_TICKS = 6
RECOVERY_TICKS = 2


class SystemModeManager:
    """Applies internal mode-change decisions to the small system state."""

    module_name = "system_mode_manager"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.enter_action = pattern_registry.id("action_enter_consolidation_mode")
        self.exit_action = pattern_registry.id("action_exit_consolidation_mode")
        self.pressure_high = pattern_registry.id("consolidation_pressure_high")
        self.mode_patterns = {
            "active": pattern_registry.id("system_mode_active"),
            "consolidation": pattern_registry.id("system_mode_consolidation"),
            "recovery": pattern_registry.id("system_mode_recovery"),
        }
        self._handled_decision_ids: set[str] = set()

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        system_state: SystemState,
        active_field: ActiveContextField,
    ) -> list[ContextOperation]:
        del active_field
        operations: list[ContextOperation] = []
        for decision in memory.get_recent_decisions(8):
            decision_id = decision.get("decision_id")
            if not decision_id or decision_id in self._handled_decision_ids:
                continue
            action_pattern_id = decision.get("decision_pattern_id")
            if action_pattern_id == self.enter_action and system_state.mode == "active":
                self._handled_decision_ids.add(decision_id)
                operation = self._enter_consolidation(tick, system_state)
                if operation is not None:
                    operations.append(operation)
            elif action_pattern_id == self.enter_action:
                self._handled_decision_ids.add(decision_id)
            elif action_pattern_id == self.exit_action and system_state.mode == "consolidation":
                elapsed = tick - system_state.mode_entered_tick
                if elapsed >= MIN_CONSOLIDATION_TICKS:
                    self._handled_decision_ids.add(decision_id)
                    operation = self._exit_consolidation(tick, system_state, "decision")
                    if operation is not None:
                        operations.append(operation)
            elif action_pattern_id == self.exit_action:
                self._handled_decision_ids.add(decision_id)

        if system_state.mode == "consolidation" and tick - system_state.mode_entered_tick >= MAX_CONSOLIDATION_TICKS:
            operation = self._exit_consolidation(tick, system_state, "max_duration")
            if operation is not None:
                operations.append(operation)

        if system_state.mode == "recovery" and tick - system_state.mode_entered_tick >= RECOVERY_TICKS:
            operation = self._set_mode(tick, system_state, "active", "recovery_complete", [], 0.85, 4)
            if operation is not None:
                operations.append(operation)

        return operations

    def _enter_consolidation(self, tick: int, system_state: SystemState) -> ContextOperation | None:
        return self._set_mode(
            tick,
            system_state,
            "consolidation",
            "consolidation_pressure",
            [self.pressure_high],
            1.0,
            8,
        )

    def _exit_consolidation(self, tick: int, system_state: SystemState, reason: str) -> ContextOperation | None:
        system_state.last_consolidation_tick = tick
        system_state.consolidation_depth = 0.35
        return self._set_mode(tick, system_state, "recovery", reason, [self.mode_patterns["consolidation"]], 0.9, 5)

    def _set_mode(
        self,
        tick: int,
        system_state: SystemState,
        to_mode: str,
        reason: str,
        reason_patterns: list[str],
        activation: float,
        ttl: int,
    ) -> ContextOperation | None:
        if system_state.mode == to_mode:
            return None
        from_mode = system_state.mode
        system_state.mode = to_mode
        system_state.mode_entered_tick = tick
        if to_mode == "consolidation":
            system_state.consolidation_depth = 1.0
        elif to_mode == "active":
            system_state.consolidation_depth = 0.0
        payload = {
            "mode_change_id": self.id_gen.next("mode_change"),
            "from_mode": from_mode,
            "to_mode": to_mode,
            "mode_pattern_id": self.mode_patterns[to_mode],
            "reason": reason,
            "reason_patterns": reason_patterns,
            "activation": activation,
            "ttl": ttl,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.SYSTEM_MODE_CHANGE,
            tick,
            self.module_name,
            None,
            payload,
        )
