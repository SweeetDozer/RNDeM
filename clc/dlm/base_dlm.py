from abc import ABC, abstractmethod

from clc.context.context_memory import ContextMemory
from clc.core.operations import ContextOperation


class BaseDLM(ABC):
    module_name: str

    @abstractmethod
    def run(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        raise NotImplementedError
