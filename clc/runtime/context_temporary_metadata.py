from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY = "explicit_test_scenario_harness"
CONTEXT_TEMPORARY_METADATA_STORAGE_KIND = "metadata_only"
CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND = "local_temporary_metadata"

FORBIDDEN_TEMPORARY_METADATA_FRAGMENTS = frozenset(
    (
        "commit",
        "apply",
        "save",
        "write",
        "persist",
        "mutate",
        "store",
        "enqueue",
        "flush",
        "sync",
        "akbsm_write",
        "approved_for_akbsm",
        "accepted_for_write",
        "ready_to_write",
        "behavior_instruction",
        "scoring_instruction",
        "guard_instruction",
        "mode_c_instruction",
        "policy_pressure_instruction",
    )
)


@dataclass(frozen=True)
class ContextTemporaryMetadataPlacementPolicy:
    """Scenario/test-only policy for local temporary metadata placement."""

    authority: str | None = None
    require_ttl: bool = True
    metadata_only: bool = True
    temporary: bool = True
    normal_runtime_wiring: bool = False
    behavior_influence: bool = False
    contextmemory_manager_called: bool = False
    permanent_files_created: bool = False
    permanent_queues_created: bool = False
    akbsm_write_authorized: bool = False
    expsm_write_authorized: bool = False

    def __post_init__(self) -> None:
        if self.require_ttl is not True:
            raise ValueError("temporary metadata placement requires TTL/expiration")
        if self.metadata_only is not True or self.temporary is not True:
            raise ValueError("placement policy must remain temporary metadata-only")
        if (
            self.normal_runtime_wiring
            or self.behavior_influence
            or self.contextmemory_manager_called
            or self.permanent_files_created
            or self.permanent_queues_created
            or self.akbsm_write_authorized
            or self.expsm_write_authorized
        ):
            raise ValueError("temporary metadata placement cannot authorize side effects")

    def allows(self, authority: str | None) -> bool:
        active_authority = authority if authority is not None else self.authority
        return active_authority == CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY


@dataclass(frozen=True)
class ContextTemporaryMetadataEntry:
    """Immutable temporary metadata entry for explicit scenario/test use."""

    entry_id: str
    namespace: str
    source: str
    payload_kind: str
    payload_reference: tuple[tuple[str, str], ...]
    payload: tuple[tuple[str, Any], ...]
    created_tick: int
    updated_tick: int
    ttl_ticks: int | None = None
    expires_at_tick: int | None = None
    notes: str = ""
    temporary: bool = True
    storage_kind: str = CONTEXT_TEMPORARY_METADATA_STORAGE_KIND
    placement_kind: str = CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND
    metadata_only: bool = True
    observation_only: bool = True
    pending_commit: bool = False
    write_authorized: bool = False
    akbsm_write_approved: bool = False
    behavior_influence: bool = False

    def __post_init__(self) -> None:
        created_tick = _non_negative_int(self.created_tick, "created_tick")
        updated_tick = _non_negative_int(self.updated_tick, "updated_tick")
        if updated_tick < created_tick:
            raise ValueError("updated_tick must not be less than created_tick")
        ttl_ticks = self.ttl_ticks
        if ttl_ticks is not None:
            ttl_ticks = _positive_int(ttl_ticks, "ttl_ticks")
        expires_at_tick = self.expires_at_tick
        if expires_at_tick is not None:
            expires_at_tick = _non_negative_int(expires_at_tick, "expires_at_tick")
            if expires_at_tick <= created_tick:
                raise ValueError("expires_at_tick must be greater than created_tick")
        if ttl_ticks is None and expires_at_tick is None:
            raise ValueError("temporary metadata requires ttl_ticks or expires_at_tick")
        if not str(self.entry_id).strip():
            raise ValueError("entry_id must be non-empty metadata")
        if not str(self.namespace).strip():
            raise ValueError("namespace must be non-empty metadata")
        if not str(self.source).strip():
            raise ValueError("source must be non-empty metadata")
        if not str(self.payload_kind).strip():
            raise ValueError("payload_kind must be non-empty metadata")
        if self.temporary is not True or self.metadata_only is not True:
            raise ValueError("entry must remain temporary metadata-only")
        if self.storage_kind != CONTEXT_TEMPORARY_METADATA_STORAGE_KIND:
            raise ValueError("storage_kind must remain metadata_only")
        if self.placement_kind != CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND:
            raise ValueError("placement_kind must remain local_temporary_metadata")
        if self.observation_only is not True:
            raise ValueError("entry must remain observation-only")
        if self.pending_commit or self.write_authorized or self.akbsm_write_approved:
            raise ValueError("entry cannot authorize pending commits or writes")
        if self.behavior_influence:
            raise ValueError("entry cannot influence behavior")
        payload = _freeze_mapping_pairs(dict(self.payload), "payload")
        payload_reference = _freeze_reference_pairs(self.payload_reference)
        _reject_forbidden_content(
            {
                "namespace": self.namespace,
                "source": self.source,
                "payload_kind": self.payload_kind,
                "payload_reference": payload_reference,
                "payload": payload,
                "notes": self.notes,
            }
        )
        object.__setattr__(self, "entry_id", str(self.entry_id).strip())
        object.__setattr__(self, "namespace", str(self.namespace).strip())
        object.__setattr__(self, "source", str(self.source).strip())
        object.__setattr__(self, "payload_kind", str(self.payload_kind).strip())
        object.__setattr__(self, "payload_reference", payload_reference)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "created_tick", created_tick)
        object.__setattr__(self, "updated_tick", updated_tick)
        object.__setattr__(self, "ttl_ticks", ttl_ticks)
        object.__setattr__(self, "expires_at_tick", expires_at_tick or created_tick + ttl_ticks)
        object.__setattr__(self, "notes", str(self.notes))

    def is_expired(self, current_tick: int) -> bool:
        return _non_negative_int(current_tick, "current_tick") >= int(self.expires_at_tick)

    def as_metadata(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(
            {
                "entry_id": self.entry_id,
                "namespace": self.namespace,
                "source": self.source,
                "payload_kind": self.payload_kind,
                "payload_reference": self.payload_reference,
                "payload": self.payload,
                "created_tick": self.created_tick,
                "updated_tick": self.updated_tick,
                "ttl_ticks": self.ttl_ticks,
                "expires_at_tick": self.expires_at_tick,
                "notes": self.notes,
                "temporary": self.temporary,
                "storage_kind": self.storage_kind,
                "placement_kind": self.placement_kind,
                "metadata_only": self.metadata_only,
                "observation_only": self.observation_only,
                "pending_commit": self.pending_commit,
                "write_authorized": self.write_authorized,
                "akbsm_write_approved": self.akbsm_write_approved,
                "behavior_influence": self.behavior_influence,
            }
        )

    def as_payload(self) -> MappingProxyType[str, Any]:
        return self.as_metadata()


@dataclass(frozen=True)
class ContextTemporaryMetadataPlacementResult:
    """Immutable result for scenario/test-only temporary metadata placement."""

    entry: ContextTemporaryMetadataEntry | None
    accepted: bool
    reason: str
    metadata_only: bool = True
    temporary: bool = True
    local_only: bool = True
    observation_only: bool = True
    pending_commit: bool = False
    write_authorized: bool = False
    akbsm_write_approved: bool = False
    contextmemory_written: bool = False
    contextmemory_manager_called: bool = False
    normal_runtime_wiring: bool = False
    behavior_influence: bool = False
    permanent_files_created: bool = False
    permanent_queues_created: bool = False

    def __post_init__(self) -> None:
        if self.entry is not None and not isinstance(self.entry, ContextTemporaryMetadataEntry):
            raise TypeError("entry must be ContextTemporaryMetadataEntry metadata")
        if self.accepted and self.entry is None:
            raise ValueError("accepted placement requires an entry")
        if self.metadata_only is not True or self.temporary is not True or self.local_only is not True:
            raise ValueError("placement result must remain local temporary metadata-only")
        if self.observation_only is not True:
            raise ValueError("placement result must remain observation-only")
        if (
            self.pending_commit
            or self.write_authorized
            or self.akbsm_write_approved
            or self.contextmemory_written
            or self.contextmemory_manager_called
            or self.normal_runtime_wiring
            or self.behavior_influence
            or self.permanent_files_created
            or self.permanent_queues_created
        ):
            raise ValueError("placement result cannot authorize side effects")

    def as_metadata(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(
            {
                "entry": self.entry.as_metadata() if self.entry is not None else None,
                "accepted": self.accepted,
                "reason": self.reason,
                "metadata_only": self.metadata_only,
                "temporary": self.temporary,
                "local_only": self.local_only,
                "observation_only": self.observation_only,
                "pending_commit": self.pending_commit,
                "write_authorized": self.write_authorized,
                "akbsm_write_approved": self.akbsm_write_approved,
                "contextmemory_written": self.contextmemory_written,
                "contextmemory_manager_called": self.contextmemory_manager_called,
                "normal_runtime_wiring": self.normal_runtime_wiring,
                "behavior_influence": self.behavior_influence,
                "permanent_files_created": self.permanent_files_created,
                "permanent_queues_created": self.permanent_queues_created,
            }
        )

    def as_payload(self) -> MappingProxyType[str, Any]:
        return self.as_metadata()


@dataclass
class ContextTemporaryMetadataPlacement:
    """Local-only placement scaffold for explicit scenario/test harnesses."""

    policy: ContextTemporaryMetadataPlacementPolicy = field(
        default_factory=ContextTemporaryMetadataPlacementPolicy
    )
    _entries: list[ContextTemporaryMetadataEntry] = field(default_factory=list)

    def place_temporary_metadata(
        self,
        payload: dict[str, Any] | MappingProxyType[str, Any],
        *,
        namespace: str,
        source: str,
        authority: str | None,
        created_tick: int,
        ttl_ticks: int | None = None,
        expires_at_tick: int | None = None,
        notes: str = "",
        payload_kind: str = "metadata",
        payload_reference: dict[str, Any] | tuple[tuple[str, Any], ...] | None = None,
    ) -> ContextTemporaryMetadataPlacementResult:
        if not self.policy.allows(authority):
            return _rejected_result("unauthorized")
        try:
            entry = ContextTemporaryMetadataEntry(
                entry_id=_entry_id(namespace, source, created_tick, len(self._entries)),
                namespace=namespace,
                source=source,
                payload_kind=payload_kind,
                payload_reference=_reference_from(payload_reference),
                payload=_freeze_mapping_pairs(dict(payload), "payload"),
                created_tick=created_tick,
                updated_tick=created_tick,
                ttl_ticks=ttl_ticks,
                expires_at_tick=expires_at_tick,
                notes=notes,
            )
        except (TypeError, ValueError):
            return _rejected_result("invalid_metadata")
        self._entries.append(entry)
        return ContextTemporaryMetadataPlacementResult(
            entry=entry,
            accepted=True,
            reason="temporary_metadata_accepted",
        )

    def list_active_metadata(
        self,
        current_tick: int,
        *,
        authority: str | None,
    ) -> tuple[ContextTemporaryMetadataEntry, ...]:
        if not self.policy.allows(authority):
            return ()
        tick = _non_negative_int(current_tick, "current_tick")
        return tuple(entry for entry in self._entries if not entry.is_expired(tick))

    def expire_metadata(
        self,
        current_tick: int,
        *,
        authority: str | None,
    ) -> tuple[ContextTemporaryMetadataEntry, ...]:
        if not self.policy.allows(authority):
            return ()
        tick = _non_negative_int(current_tick, "current_tick")
        expired = tuple(entry for entry in self._entries if entry.is_expired(tick))
        self._entries = [entry for entry in self._entries if not entry.is_expired(tick)]
        return expired


def place_temporary_metadata(
    payload: dict[str, Any] | MappingProxyType[str, Any],
    *,
    namespace: str,
    source: str,
    authority: str | None,
    created_tick: int,
    ttl_ticks: int | None = None,
    expires_at_tick: int | None = None,
    notes: str = "",
    payload_kind: str = "metadata",
    payload_reference: dict[str, Any] | tuple[tuple[str, Any], ...] | None = None,
) -> ContextTemporaryMetadataPlacementResult:
    placement = ContextTemporaryMetadataPlacement()
    return placement.place_temporary_metadata(
        payload,
        namespace=namespace,
        source=source,
        authority=authority,
        created_tick=created_tick,
        ttl_ticks=ttl_ticks,
        expires_at_tick=expires_at_tick,
        notes=notes,
        payload_kind=payload_kind,
        payload_reference=payload_reference,
    )


def _rejected_result(reason: str) -> ContextTemporaryMetadataPlacementResult:
    return ContextTemporaryMetadataPlacementResult(
        entry=None,
        accepted=False,
        reason=reason,
    )


def _entry_id(namespace: str, source: str, created_tick: int, index: int) -> str:
    return f"{str(namespace).strip()}:{str(source).strip()}:{int(created_tick)}:{int(index)}"


def _reference_from(
    value: dict[str, Any] | tuple[tuple[str, Any], ...] | None,
) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if isinstance(value, dict):
        items = value.items()
    else:
        items = value
    return tuple((str(key), str(item)) for key, item in items)


def _freeze_mapping_pairs(value: dict[str, Any], field_name: str) -> tuple[tuple[str, Any], ...]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be metadata mapping")
    return tuple((str(key), _freeze_value(item)) for key, item in value.items())


def _freeze_value(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return _freeze_mapping_pairs(dict(value), "payload")
    if isinstance(value, dict):
        return _freeze_mapping_pairs(value, "payload")
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_value(item) for item in value))
    return value


def _freeze_reference_pairs(value: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    return tuple((str(key), str(item)) for key, item in value)


def _reject_forbidden_content(value: Any) -> None:
    for item in _flatten(value):
        if not isinstance(item, str):
            continue
        lowered = item.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_TEMPORARY_METADATA_FRAGMENTS):
            raise ValueError("temporary metadata cannot contain forbidden instructions")


def _flatten(value: Any) -> tuple[Any, ...]:
    if isinstance(value, MappingProxyType):
        return _flatten(dict(value))
    if isinstance(value, dict):
        flattened: list[Any] = []
        for key, item in value.items():
            flattened.extend(_flatten(key))
            flattened.extend(_flatten(item))
        return tuple(flattened)
    if isinstance(value, (tuple, list, set)):
        flattened = []
        for item in value:
            flattened.extend(_flatten(item))
        return tuple(flattened)
    return (value,)


def _non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be a non-negative integer") from exc
    if result < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return result


def _positive_int(value: Any, field_name: str) -> int:
    result = _non_negative_int(value, field_name)
    if result <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return result
