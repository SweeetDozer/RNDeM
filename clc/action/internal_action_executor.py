from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState


class InternalActionExecutor:
    """Converts selected internal decisions into internal effects only."""

    module_name = "internal_action_executor"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.handled_decision_ids: set[str] = set()
        self.actions = {
            pattern_registry.id("action_wait_more_data"): self._wait_more_data,
            pattern_registry.id("action_increase_attention"): self._increase_attention,
            pattern_registry.id("action_inspect_pattern"): self._inspect_pattern,
            pattern_registry.id("action_store_memory_candidate"): self._store_memory_candidate,
            pattern_registry.id("action_commit_memory_draft"): self._commit_memory_draft,
            pattern_registry.id("action_review_committed_memory_update"): self._review_committed_memory_update,
            pattern_registry.id("action_update_committed_expsm_record"): self._update_committed_expsm_record,
            pattern_registry.id("action_reduce_load"): self._reduce_load,
            pattern_registry.id("action_preserve_integrity"): self._preserve_integrity,
            pattern_registry.id("action_continue_observation"): self._continue_observation,
            pattern_registry.id("action_generate_more_thought"): self._generate_more_thought,
            pattern_registry.id("action_enter_consolidation_mode"): self._enter_consolidation_mode,
            pattern_registry.id("action_exit_consolidation_mode"): self._exit_consolidation_mode,
        }
        self.effects = {
            "waiting": pattern_registry.id("state_waiting_for_more_data"),
            "attention": pattern_registry.id("state_attention_increased"),
            "inspection": pattern_registry.id("state_pattern_inspection"),
            "memory_candidate": pattern_registry.id("state_memory_candidate_created"),
            "memory_draft_commit_requested": pattern_registry.id("state_memory_draft_commit_requested"),
            "committed_memory_update_review_requested": pattern_registry.id("state_committed_memory_update_review_requested"),
            "committed_expsm_update_requested": pattern_registry.id("state_committed_expsm_update_requested"),
            "load_reduced": pattern_registry.id("state_load_reduced"),
            "integrity": pattern_registry.id("state_integrity_preservation"),
            "observation": pattern_registry.id("state_observation_continues"),
            "more_thought": pattern_registry.id("state_more_thought_requested"),
            "consolidation_entered": pattern_registry.id("state_consolidation_mode_entered"),
            "consolidation_exited": pattern_registry.id("state_consolidation_mode_exited"),
        }
        self.thoughts = {
            "need_more_data": pattern_registry.id("thought_need_more_data"),
            "inspect": pattern_registry.id("thought_inspect_pattern"),
        }

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        system_state: SystemState | None = None,
        mode_action_guard: ModeActionGuard | None = None,
    ) -> list[ContextOperation]:
        operations: list[ContextOperation] = []
        for decision in memory.get_recent_decisions(8):
            decision_id = decision.get("decision_id")
            action_pattern_id = decision.get("decision_pattern_id")
            if not decision_id or decision_id in self.handled_decision_ids:
                continue
            builder = self.actions.get(action_pattern_id)
            if builder is None:
                continue
            self.handled_decision_ids.add(decision_id)
            if system_state is not None and mode_action_guard is not None and not mode_action_guard.is_allowed(action_pattern_id, system_state, tick):
                operations.append(
                    ContextOperation(
                        op_id=self.id_gen.next("op"),
                        marker=OperationMarker.MODULE_UPDATE,
                        tick=tick,
                        source_module=self.module_name,
                        target=None,
                        payload={
                            "update_id": self.id_gen.next("guard_block"),
                            "blocked_decision_id": decision_id,
                            "blocked_action_pattern_id": action_pattern_id,
                            "mode": system_state.mode,
                            "reason": "blocked_by_mode_action_guard",
                            "activation": 0.5,
                            "ttl": 2,
                        },
                    )
                )
                continue
            payload = builder(decision_id, action_pattern_id)
            operations.append(
                ContextOperation(
                    op_id=self.id_gen.next("op"),
                    marker=OperationMarker.INTERNAL_ACTION_EFFECT,
                    tick=tick,
                    source_module=self.module_name,
                    target=None,
                    payload=payload,
                )
            )
        return operations

    def _base(self, decision_id: str, action_pattern_id: str, effect_pattern_id: str, activation: float, ttl: int) -> dict:
        return {
            "effect_id": self.id_gen.next("effect"),
            "effect_pattern_id": effect_pattern_id,
            "source_decision_id": decision_id,
            "source_action_pattern_id": action_pattern_id,
            "activation": activation,
            "ttl": ttl,
        }

    def _wait_more_data(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["waiting"], 0.7, 3)
        payload["tone_delta"] = {"tension": -0.03}
        return payload

    def _increase_attention(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["attention"], 0.8, 3)
        payload["tone_delta"] = {"tension": 0.02, "fatigue": 0.03}
        return payload

    def _inspect_pattern(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["inspection"], 0.75, 4)
        payload["generate_thought_patterns"] = [self.thoughts["inspect"]]
        payload["tone_delta"] = {"curiosity": 0.03}
        return payload

    def _store_memory_candidate(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["memory_candidate"], 0.7, 5)
        payload["memory_candidate"] = {"candidate_type": "pattern_store_candidate", "status": "pending"}
        payload["tone_delta"] = {"satisfaction": 0.02}
        return payload

    def _commit_memory_draft(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["memory_draft_commit_requested"], 0.65, 4)
        payload["memory_draft_commit"] = {"status": "requested", "permanent_memory_modified": False}
        payload["tone_delta"] = {"stability": 0.01}
        return payload

    def _review_committed_memory_update(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["committed_memory_update_review_requested"], 0.65, 4)
        payload["memory_update_review"] = {"status": "requested", "permanent_memory_modified": False}
        payload["tone_delta"] = {"stability": 0.005, "curiosity": 0.005}
        return payload

    def _update_committed_expsm_record(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["committed_expsm_update_requested"], 0.65, 4)
        payload["expsm_update"] = {"status": "requested", "permanent_memory_modified": False}
        payload["tone_delta"] = {"stability": 0.005}
        return payload

    def _reduce_load(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["load_reduced"], 0.8, 4)
        payload["tone_delta"] = {"fatigue": -0.08, "tension": -0.05}
        return payload

    def _preserve_integrity(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["integrity"], 0.9, 4)
        payload["tone_delta"] = {"tension": -0.04, "stability": 0.03}
        return payload

    def _continue_observation(self, decision_id: str, action_pattern_id: str) -> dict:
        return self._base(decision_id, action_pattern_id, self.effects["observation"], 0.65, 3)

    def _generate_more_thought(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["more_thought"], 0.7, 3)
        payload["generate_thought_patterns"] = [self.thoughts["need_more_data"]]
        return payload

    def _enter_consolidation_mode(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["consolidation_entered"], 1.0, 6)
        payload["effect_kind"] = self.effects["consolidation_entered"]
        payload["tone_delta"] = {"tension": -0.03, "curiosity": -0.02}
        return payload

    def _exit_consolidation_mode(self, decision_id: str, action_pattern_id: str) -> dict:
        payload = self._base(decision_id, action_pattern_id, self.effects["consolidation_exited"], 0.9, 5)
        payload["effect_kind"] = self.effects["consolidation_exited"]
        payload["tone_delta"] = {"fatigue": -0.05, "stability": 0.02}
        return payload
