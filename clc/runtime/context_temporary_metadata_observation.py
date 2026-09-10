from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from clc.runtime.context_temporary_metadata import (
    CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataEntry,
    ContextTemporaryMetadataPlacement,
)


CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY = (
    "explicit_observation_diagnostic_harness"
)
CONTEXT_TEMPORARY_METADATA_OBSERVATION_KIND = "local_temporary_metadata_observation"


@dataclass(frozen=True)
class ContextTemporaryMetadataObservationView:
    """Read-only diagnostic view of one local temporary metadata entry."""

    entry_id: str
    namespace: str
    source: str
    payload_kind: str
    payload_reference: tuple[tuple[str, str], ...]
    created_tick: int
    updated_tick: int
    ttl_ticks: int | None
    expires_at_tick: int
    notes: str
    active: bool
    expired: bool
    lifecycle_state: str | None = None
    transition_result_metadata: tuple[tuple[str, Any], ...] = ()
    metadata_only: bool = True
    diagnostic_only: bool = True
    observation_only: bool = True
    write_authorized: bool = False
    pending_commit: bool = False
    behavior_influence: bool = False
    scoring_influence: bool = False
    guard_influence: bool = False

    def __post_init__(self) -> None:
        if self.metadata_only is not True or self.diagnostic_only is not True:
            raise ValueError("observation view must remain diagnostic metadata only")
        if self.observation_only is not True:
            raise ValueError("observation view must remain observation-only")
        if (
            self.write_authorized
            or self.pending_commit
            or self.behavior_influence
            or self.scoring_influence
            or self.guard_influence
        ):
            raise ValueError("observation view cannot authorize side effects")
        if self.active and self.expired:
            raise ValueError("observation view cannot be both active and expired")
        object.__setattr__(self, "entry_id", str(self.entry_id))
        object.__setattr__(self, "namespace", str(self.namespace))
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "payload_kind", str(self.payload_kind))
        object.__setattr__(
            self,
            "payload_reference",
            tuple((str(key), str(value)) for key, value in self.payload_reference),
        )
        object.__setattr__(self, "created_tick", _non_negative_int(self.created_tick))
        object.__setattr__(self, "updated_tick", _non_negative_int(self.updated_tick))
        object.__setattr__(
            self,
            "ttl_ticks",
            None if self.ttl_ticks is None else _non_negative_int(self.ttl_ticks),
        )
        object.__setattr__(self, "expires_at_tick", _non_negative_int(self.expires_at_tick))
        object.__setattr__(self, "notes", str(self.notes))
        object.__setattr__(
            self,
            "transition_result_metadata",
            tuple((str(key), _freeze_value(value)) for key, value in self.transition_result_metadata),
        )

    def as_metadata(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(
            {
                "entry_id": self.entry_id,
                "namespace": self.namespace,
                "source": self.source,
                "payload_kind": self.payload_kind,
                "payload_reference": self.payload_reference,
                "created_tick": self.created_tick,
                "updated_tick": self.updated_tick,
                "ttl_ticks": self.ttl_ticks,
                "expires_at_tick": self.expires_at_tick,
                "notes": self.notes,
                "active": self.active,
                "expired": self.expired,
                "lifecycle_state": self.lifecycle_state,
                "transition_result_metadata": self.transition_result_metadata,
                "metadata_only": self.metadata_only,
                "diagnostic_only": self.diagnostic_only,
                "observation_only": self.observation_only,
                "write_authorized": self.write_authorized,
                "pending_commit": self.pending_commit,
                "behavior_influence": self.behavior_influence,
                "scoring_influence": self.scoring_influence,
                "guard_influence": self.guard_influence,
            }
        )

    def as_payload(self) -> MappingProxyType[str, Any]:
        return self.as_metadata()


@dataclass(frozen=True)
class ContextTemporaryMetadataObservation:
    """Immutable aggregate of active and optional expired diagnostic views."""

    current_tick: int
    active_entries: tuple[ContextTemporaryMetadataObservationView, ...]
    expired_diagnostics: tuple[ContextTemporaryMetadataObservationView, ...] = ()
    include_expired_diagnostics: bool = False
    observation_kind: str = CONTEXT_TEMPORARY_METADATA_OBSERVATION_KIND
    metadata_only: bool = True
    diagnostic_only: bool = True
    observation_only: bool = True
    behavior_influence: bool = False
    scoring_influence: bool = False
    guard_influence: bool = False
    write_authorized: bool = False
    pending_commit: bool = False

    def __post_init__(self) -> None:
        if self.observation_kind != CONTEXT_TEMPORARY_METADATA_OBSERVATION_KIND:
            raise ValueError("observation_kind must remain local diagnostic observation")
        if self.metadata_only is not True or self.diagnostic_only is not True:
            raise ValueError("observation must remain diagnostic metadata only")
        if self.observation_only is not True:
            raise ValueError("observation must remain observation-only")
        if (
            self.behavior_influence
            or self.scoring_influence
            or self.guard_influence
            or self.write_authorized
            or self.pending_commit
        ):
            raise ValueError("observation cannot authorize side effects")
        if any(view.expired for view in self.active_entries):
            raise ValueError("expired metadata cannot be active observation metadata")
        object.__setattr__(self, "current_tick", _non_negative_int(self.current_tick))
        object.__setattr__(self, "active_entries", tuple(self.active_entries))
        object.__setattr__(self, "expired_diagnostics", tuple(self.expired_diagnostics))

    @property
    def active_count(self) -> int:
        return len(self.active_entries)

    @property
    def namespaces_present(self) -> tuple[str, ...]:
        return tuple(sorted({entry.namespace for entry in self.active_entries}))

    @property
    def payload_kinds_present(self) -> tuple[str, ...]:
        return tuple(sorted({entry.payload_kind for entry in self.active_entries}))

    def as_metadata(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(
            {
                "current_tick": self.current_tick,
                "active_count": self.active_count,
                "namespaces_present": self.namespaces_present,
                "payload_kinds_present": self.payload_kinds_present,
                "active_entries": tuple(entry.as_metadata() for entry in self.active_entries),
                "expired_diagnostics": tuple(
                    entry.as_metadata() for entry in self.expired_diagnostics
                ),
                "include_expired_diagnostics": self.include_expired_diagnostics,
                "observation_kind": self.observation_kind,
                "metadata_only": self.metadata_only,
                "diagnostic_only": self.diagnostic_only,
                "observation_only": self.observation_only,
                "behavior_influence": self.behavior_influence,
                "scoring_influence": self.scoring_influence,
                "guard_influence": self.guard_influence,
                "write_authorized": self.write_authorized,
                "pending_commit": self.pending_commit,
            }
        )

    def as_payload(self) -> MappingProxyType[str, Any]:
        return self.as_metadata()


@dataclass(frozen=True)
class ContextTemporaryMetadataObservationReport:
    """Top-level read-only diagnostic report for temporary metadata observation."""

    observation: ContextTemporaryMetadataObservation
    accepted: bool = True
    reason: str = "temporary_metadata_observed"
    metadata_only: bool = True
    diagnostic_only: bool = True
    observation_only: bool = True
    local_only: bool = True
    contextmemory_written: bool = False
    contextmemory_manager_called: bool = False
    normal_runtime_wiring: bool = False
    behavior_influence: bool = False
    scoring_influence: bool = False
    guard_influence: bool = False
    mode_c_influence: bool = False
    policy_pressure_review_influence: bool = False
    write_authorized: bool = False
    pending_commit: bool = False
    akbsm_write_approved: bool = False
    expsm_write_approved: bool = False
    permanent_files_created: bool = False
    permanent_queues_created: bool = False
    proposal_storage_added: bool = False
    review_record_persistence_added: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.observation, ContextTemporaryMetadataObservation):
            raise TypeError("observation must be ContextTemporaryMetadataObservation")
        if self.metadata_only is not True or self.diagnostic_only is not True:
            raise ValueError("observation report must remain diagnostic metadata only")
        if self.observation_only is not True or self.local_only is not True:
            raise ValueError("observation report must remain local observation-only")
        if (
            self.contextmemory_written
            or self.contextmemory_manager_called
            or self.normal_runtime_wiring
            or self.behavior_influence
            or self.scoring_influence
            or self.guard_influence
            or self.mode_c_influence
            or self.policy_pressure_review_influence
            or self.write_authorized
            or self.pending_commit
            or self.akbsm_write_approved
            or self.expsm_write_approved
            or self.permanent_files_created
            or self.permanent_queues_created
            or self.proposal_storage_added
            or self.review_record_persistence_added
        ):
            raise ValueError("observation report cannot authorize side effects")

    def as_metadata(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(
            {
                "accepted": self.accepted,
                "reason": self.reason,
                "observation": self.observation.as_metadata(),
                "metadata_only": self.metadata_only,
                "diagnostic_only": self.diagnostic_only,
                "observation_only": self.observation_only,
                "local_only": self.local_only,
                "contextmemory_written": self.contextmemory_written,
                "contextmemory_manager_called": self.contextmemory_manager_called,
                "normal_runtime_wiring": self.normal_runtime_wiring,
                "behavior_influence": self.behavior_influence,
                "scoring_influence": self.scoring_influence,
                "guard_influence": self.guard_influence,
                "mode_c_influence": self.mode_c_influence,
                "policy_pressure_review_influence": self.policy_pressure_review_influence,
                "write_authorized": self.write_authorized,
                "pending_commit": self.pending_commit,
                "akbsm_write_approved": self.akbsm_write_approved,
                "expsm_write_approved": self.expsm_write_approved,
                "permanent_files_created": self.permanent_files_created,
                "permanent_queues_created": self.permanent_queues_created,
                "proposal_storage_added": self.proposal_storage_added,
                "review_record_persistence_added": self.review_record_persistence_added,
            }
        )

    def as_payload(self) -> MappingProxyType[str, Any]:
        return self.as_metadata()


@dataclass(frozen=True)
class ContextTemporaryMetadataObserver:
    """Authority-gated observer for local temporary metadata scaffold state."""

    authority: str | None = None

    def observe(
        self,
        placement: ContextTemporaryMetadataPlacement,
        *,
        authority: str | None = None,
        current_tick: int,
        include_expired_diagnostics: bool = False,
    ) -> ContextTemporaryMetadataObservationReport | None:
        active_authority = authority if authority is not None else self.authority
        if active_authority != CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY:
            return None
        if active_authority == CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY:
            return None
        if not isinstance(placement, ContextTemporaryMetadataPlacement):
            raise TypeError("placement must be ContextTemporaryMetadataPlacement")
        tick = _non_negative_int(current_tick)
        active_views: list[ContextTemporaryMetadataObservationView] = []
        expired_views: list[ContextTemporaryMetadataObservationView] = []
        for entry in tuple(getattr(placement, "_entries", ())):
            if not isinstance(entry, ContextTemporaryMetadataEntry):
                continue
            expired = entry.is_expired(tick)
            view = _view_from_entry(entry, current_tick=tick, expired=expired)
            if expired:
                if include_expired_diagnostics:
                    expired_views.append(view)
            else:
                active_views.append(view)
        observation = ContextTemporaryMetadataObservation(
            current_tick=tick,
            active_entries=tuple(active_views),
            expired_diagnostics=tuple(expired_views),
            include_expired_diagnostics=include_expired_diagnostics,
        )
        return ContextTemporaryMetadataObservationReport(observation=observation)


def build_temporary_metadata_observation(
    placement: ContextTemporaryMetadataPlacement,
    *,
    authority: str,
    current_tick: int,
    include_expired_diagnostics: bool = False,
) -> ContextTemporaryMetadataObservationReport | None:
    return ContextTemporaryMetadataObserver().observe(
        placement,
        authority=authority,
        current_tick=current_tick,
        include_expired_diagnostics=include_expired_diagnostics,
    )


def _view_from_entry(
    entry: ContextTemporaryMetadataEntry,
    *,
    current_tick: int,
    expired: bool,
) -> ContextTemporaryMetadataObservationView:
    metadata = entry.as_metadata()
    payload = dict(metadata["payload"])
    return ContextTemporaryMetadataObservationView(
        entry_id=metadata["entry_id"],
        namespace=metadata["namespace"],
        source=metadata["source"],
        payload_kind=metadata["payload_kind"],
        payload_reference=metadata["payload_reference"],
        created_tick=metadata["created_tick"],
        updated_tick=metadata["updated_tick"],
        ttl_ticks=metadata["ttl_ticks"],
        expires_at_tick=metadata["expires_at_tick"],
        notes=metadata["notes"],
        active=not expired,
        expired=expired,
        lifecycle_state=_optional_str(payload.get("lifecycle_state")),
        transition_result_metadata=_metadata_pairs(payload.get("transition_result_metadata")),
    )


def _metadata_pairs(value: Any) -> tuple[tuple[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, MappingProxyType):
        return tuple((str(key), _freeze_value(item)) for key, item in dict(value).items())
    if isinstance(value, dict):
        return tuple((str(key), _freeze_value(item)) for key, item in value.items())
    if isinstance(value, tuple):
        try:
            return tuple((str(key), _freeze_value(item)) for key, item in value)
        except (TypeError, ValueError):
            return (("value", _freeze_value(value)),)
    return (("value", _freeze_value(value)),)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _freeze_value(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return tuple((str(key), _freeze_value(item)) for key, item in dict(value).items())
    if isinstance(value, dict):
        return tuple((str(key), _freeze_value(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_value(item) for item in value))
    return value


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError("value must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("value must be a non-negative integer") from exc
    if result < 0:
        raise ValueError("value must be a non-negative integer")
    return result
