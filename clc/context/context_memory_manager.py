from __future__ import annotations

from typing import TYPE_CHECKING

from clc.context.context_memory import ContextMemory
from clc.context.context_ops_pool import ContextOpsPool
from clc.context.context_retention_policy import (
    ContextRetentionPolicy,
    ContextRetentionResult,
    SideListRetentionPolicy,
    SideListRetentionResult,
)
from clc.core.markers import OperationMarker

if TYPE_CHECKING:
    from clc.context.causal_transition import PendingCausalTransition, RecentCausalTransition
    from clc.patterns import NFPFrame, NFPWindow


class ContextMemoryManager:
    """Single writer that applies queued operations to context memory."""

    def __init__(
        self,
        memory: ContextMemory,
        ops_pool: ContextOpsPool,
        retention_policy: ContextRetentionPolicy | None = None,
        side_list_retention_policy: SideListRetentionPolicy | None = None,
    ) -> None:
        self.memory = memory
        self.ops_pool = ops_pool
        self.retention_policy = retention_policy or ContextRetentionPolicy()
        self.side_list_retention_policy = side_list_retention_policy or SideListRetentionPolicy()
        self.last_retention_result: ContextRetentionResult | None = None
        self.last_side_list_retention_result: SideListRetentionResult | None = None
        self._current_external_sensory_window: NFPWindow | None = None
        self._current_action_frame: NFPFrame | None = None
        self._pending_causal_transition: PendingCausalTransition | None = None
        self._nfp_current_tick = 0
        self._next_transition_id = 1

    @property
    def current_external_sensory_window(self) -> NFPWindow | None:
        return self._current_external_sensory_window

    @property
    def current_action_frame(self) -> NFPFrame | None:
        return self._current_action_frame

    @property
    def pending_causal_transition(self) -> PendingCausalTransition | None:
        return self._pending_causal_transition

    def observe_external_sensory_window(self, window: NFPWindow) -> RecentCausalTransition | None:
        from clc.context.causal_transition import (
            RecentCausalTransition, validate_external_sensory_window,
        )

        validate_external_sensory_window(window)
        self._validate_nfp_tick(window.end_tick)
        pending = self._pending_causal_transition
        completed = None
        if pending is not None and window.end_tick == pending.expected_observation_tick:
            completed = RecentCausalTransition(
                pending.transition_id, pending.before_sensory_window,
                pending.action_frame, window, pending.action_tick, window.end_tick,
            )
        # Validate completion before changing any active state. Late evidence expires
        # the old relation but can still become the current sensory window.
        if pending is not None and window.end_tick >= pending.expected_observation_tick:
            self._pending_causal_transition = None
            self._current_action_frame = None
        self._current_external_sensory_window = window
        self._nfp_current_tick = window.end_tick
        return completed

    def observe_action_frame(self, action_frame: NFPFrame) -> PendingCausalTransition:
        from clc.context.causal_transition import PendingCausalTransition, validate_action_frame

        validate_action_frame(action_frame)
        self._validate_nfp_tick(action_frame.active_tick)
        if self._pending_causal_transition is not None:
            raise ValueError("an immediate causal transition is already pending")
        before = self._current_external_sensory_window
        if before is None:
            raise ValueError("an external sensory window is required before action")
        if before.end_tick != action_frame.active_tick:
            raise ValueError("the immediate context window must end at the action tick")
        pending = PendingCausalTransition(
            f"causal_transition:{self._next_transition_id:06d}", before, action_frame,
            action_frame.active_tick, action_frame.active_tick + 1,
        )
        self._pending_causal_transition = pending
        self._current_action_frame = action_frame
        self._nfp_current_tick = action_frame.active_tick
        self._next_transition_id += 1
        return pending

    def expire_pending_if_overdue(self, current_tick: int) -> PendingCausalTransition | None:
        self._validate_nfp_tick(current_tick)
        pending = self._pending_causal_transition
        expired = None
        if pending is not None and current_tick > pending.expected_observation_tick:
            expired = pending
            self._pending_causal_transition = None
            self._current_action_frame = None
        self._nfp_current_tick = current_tick
        return expired

    def _validate_nfp_tick(self, tick: int) -> None:
        from clc.context.causal_transition import validate_active_tick

        validate_active_tick(tick)
        if tick < self._nfp_current_tick:
            raise ValueError("active context time must not go backwards")

    def apply_pending(self) -> None:
        applied = False
        for operation in self.ops_pool.drain():
            if operation.marker in {OperationMarker.RAW_INPUT_WRITE, OperationMarker.SELF_GENERATED_THOUGHT}:
                self.memory.add_frame(operation.payload["frame"])
            self.memory.add_event(operation)
            applied = True
        if applied:
            self.last_retention_result = self.memory.apply_retention(self.retention_policy)
            self.last_side_list_retention_result = self.memory.apply_side_list_retention(
                self.side_list_retention_policy,
                oldest_event_tick=self.last_retention_result.oldest_remaining_tick,
            )
