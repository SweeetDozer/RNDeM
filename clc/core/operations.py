from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from .markers import OperationMarker


@dataclass(frozen=True)
class ContextOperation:
    op_id: str
    marker: OperationMarker
    tick: int
    source_module: str
    target: str | None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_payload(dict(self.payload)))


def freeze_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze_payload(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze_payload(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze_payload(item) for item in value)
    return value


def thaw_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: thaw_payload(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_payload(item) for item in value]
    return value
