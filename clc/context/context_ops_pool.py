from collections import deque
from typing import Iterable

from clc.core.operations import ContextOperation


class ContextOpsPool:
    """Queue used by all producers; only the manager drains it into memory."""

    def __init__(self) -> None:
        self._queue: deque[ContextOperation] = deque()

    def push(self, operation: ContextOperation) -> None:
        self._queue.append(operation)

    def extend(self, operations: Iterable[ContextOperation]) -> None:
        for operation in operations:
            self.push(operation)

    def drain(self) -> list[ContextOperation]:
        operations = list(self._queue)
        self._queue.clear()
        return operations

    def __len__(self) -> int:
        return len(self._queue)
