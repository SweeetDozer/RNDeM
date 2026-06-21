from clc.context.context_memory import ContextMemory
from clc.context.context_ops_pool import ContextOpsPool
from clc.context.context_retention_policy import (
    ContextRetentionPolicy,
    ContextRetentionResult,
    SideListRetentionPolicy,
    SideListRetentionResult,
)
from clc.core.markers import OperationMarker


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
