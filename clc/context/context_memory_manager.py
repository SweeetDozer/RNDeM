from clc.context.context_memory import ContextMemory
from clc.context.context_ops_pool import ContextOpsPool
from clc.core.markers import OperationMarker


class ContextMemoryManager:
    """Single writer that applies queued operations to context memory."""

    def __init__(self, memory: ContextMemory, ops_pool: ContextOpsPool) -> None:
        self.memory = memory
        self.ops_pool = ops_pool

    def apply_pending(self) -> None:
        for operation in self.ops_pool.drain():
            if operation.marker in {OperationMarker.RAW_INPUT_WRITE, OperationMarker.SELF_GENERATED_THOUGHT}:
                self.memory.add_frame(operation.payload["frame"])
            self.memory.add_event(operation)
