from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from clc.runtime.context_temporary_metadata import (
    CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataPlacement,
)
from clc.runtime.context_temporary_metadata_observation import (
    CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataObservationReport,
    build_temporary_metadata_observation,
)


CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY = (
    "explicit_runtime_diagnostic_harness"
)
CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_KIND = (
    "runtime_temporary_metadata_diagnostic"
)


@dataclass(frozen=True)
class RuntimeTemporaryMetadataDiagnosticView:
    """Runtime-facing read-only view of temporary metadata diagnostics."""

    active_count: int
    namespaces_present: tuple[str, ...]
    payload_kinds_present: tuple[str, ...]
    active_metadata: tuple[MappingProxyType[str, Any], ...]
    expired_diagnostics: tuple[MappingProxyType[str, Any], ...]
    expired_diagnostics_count: int
    diagnostic_tick: int
    authority_used: str
    metadata_only: bool = True
    diagnostic_only: bool = True
    read_only: bool = True
    observation_only: bool = True
    behavior_influence: bool = False
    scoring_influence: bool = False
    guard_influence: bool = False
    mode_c_influence: bool = False
    policy_pressure_review_influence: bool = False
    write_authorized: bool = False
    pending_commit: bool = False

    def __post_init__(self) -> None:
        if self.metadata_only is not True or self.diagnostic_only is not True:
            raise ValueError("diagnostic view must remain metadata-only diagnostics")
        if self.read_only is not True or self.observation_only is not True:
            raise ValueError("diagnostic view must remain read-only observation")
        if (
            self.behavior_influence
            or self.scoring_influence
            or self.guard_influence
            or self.mode_c_influence
            or self.policy_pressure_review_influence
            or self.write_authorized
            or self.pending_commit
        ):
            raise ValueError("diagnostic view cannot authorize side effects")
        if self.authority_used != CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY:
            raise ValueError("diagnostic view requires runtime diagnostic authority")
        object.__setattr__(self, "active_count", _non_negative_int(self.active_count))
        object.__setattr__(
            self,
            "namespaces_present",
            tuple(str(item) for item in self.namespaces_present),
        )
        object.__setattr__(
            self,
            "payload_kinds_present",
            tuple(str(item) for item in self.payload_kinds_present),
        )
        object.__setattr__(
            self,
            "active_metadata",
            tuple(_freeze_mapping(dict(item)) for item in self.active_metadata),
        )
        object.__setattr__(
            self,
            "expired_diagnostics",
            tuple(_freeze_mapping(dict(item)) for item in self.expired_diagnostics),
        )
        object.__setattr__(
            self,
            "expired_diagnostics_count",
            _non_negative_int(self.expired_diagnostics_count),
        )
        object.__setattr__(self, "diagnostic_tick", _non_negative_int(self.diagnostic_tick))

    def as_metadata(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(
            {
                "active_count": self.active_count,
                "namespaces_present": self.namespaces_present,
                "payload_kinds_present": self.payload_kinds_present,
                "active_metadata": self.active_metadata,
                "expired_diagnostics": self.expired_diagnostics,
                "expired_diagnostics_count": self.expired_diagnostics_count,
                "diagnostic_tick": self.diagnostic_tick,
                "authority_used": self.authority_used,
                "metadata_only": self.metadata_only,
                "diagnostic_only": self.diagnostic_only,
                "read_only": self.read_only,
                "observation_only": self.observation_only,
                "behavior_influence": self.behavior_influence,
                "scoring_influence": self.scoring_influence,
                "guard_influence": self.guard_influence,
                "mode_c_influence": self.mode_c_influence,
                "policy_pressure_review_influence": self.policy_pressure_review_influence,
                "write_authorized": self.write_authorized,
                "pending_commit": self.pending_commit,
            }
        )

    def as_payload(self) -> MappingProxyType[str, Any]:
        return self.as_metadata()


@dataclass(frozen=True)
class RuntimeTemporaryMetadataDiagnosticReport:
    """Explicit runtime-facing diagnostic report for temporary metadata."""

    view: RuntimeTemporaryMetadataDiagnosticView
    accepted: bool = True
    reason: str = "runtime_temporary_metadata_diagnostics_available"
    diagnostic_kind: str = CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_KIND
    metadata_only: bool = True
    diagnostic_only: bool = True
    read_only: bool = True
    local_only: bool = True
    observation_only: bool = True
    normal_runtime_default: bool = False
    run_tick_default: bool = False
    contextmemory_read: bool = False
    contextmemory_written: bool = False
    contextmemory_manager_called: bool = False
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
        if not isinstance(self.view, RuntimeTemporaryMetadataDiagnosticView):
            raise TypeError("view must be RuntimeTemporaryMetadataDiagnosticView")
        if self.diagnostic_kind != CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_KIND:
            raise ValueError("diagnostic_kind must remain runtime diagnostic metadata")
        if self.metadata_only is not True or self.diagnostic_only is not True:
            raise ValueError("diagnostic report must remain metadata-only diagnostics")
        if self.read_only is not True or self.local_only is not True:
            raise ValueError("diagnostic report must remain local read-only diagnostics")
        if self.observation_only is not True:
            raise ValueError("diagnostic report must remain observation-only")
        if (
            self.normal_runtime_default
            or self.run_tick_default
            or self.contextmemory_read
            or self.contextmemory_written
            or self.contextmemory_manager_called
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
            raise ValueError("diagnostic report cannot authorize side effects")

    def as_metadata(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(
            {
                "accepted": self.accepted,
                "reason": self.reason,
                "diagnostic_kind": self.diagnostic_kind,
                "view": self.view.as_metadata(),
                "metadata_only": self.metadata_only,
                "diagnostic_only": self.diagnostic_only,
                "read_only": self.read_only,
                "local_only": self.local_only,
                "observation_only": self.observation_only,
                "normal_runtime_default": self.normal_runtime_default,
                "run_tick_default": self.run_tick_default,
                "contextmemory_read": self.contextmemory_read,
                "contextmemory_written": self.contextmemory_written,
                "contextmemory_manager_called": self.contextmemory_manager_called,
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
class RuntimeTemporaryMetadataObservationDiagnosticProvider:
    """Explicit diagnostic provider over the read-only temporary metadata observer."""

    authority: str | None = None

    def build_diagnostics(
        self,
        placement: ContextTemporaryMetadataPlacement,
        *,
        authority: str | None = None,
        current_tick: int,
        include_expired_diagnostics: bool = False,
    ) -> RuntimeTemporaryMetadataDiagnosticReport | None:
        active_authority = authority if authority is not None else self.authority
        if active_authority != CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY:
            return None
        if active_authority in (
            CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
            CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
        ):
            return None
        if not isinstance(placement, ContextTemporaryMetadataPlacement):
            raise TypeError("placement must be ContextTemporaryMetadataPlacement")
        tick = _non_negative_int(current_tick)
        observation_report = build_temporary_metadata_observation(
            placement,
            authority=CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
            current_tick=tick,
            include_expired_diagnostics=include_expired_diagnostics,
        )
        if observation_report is None:
            return None
        return _report_from_observation(
            observation_report,
            authority_used=active_authority,
            diagnostic_tick=tick,
        )


def build_runtime_temporary_metadata_diagnostics(
    placement: ContextTemporaryMetadataPlacement,
    *,
    authority: str,
    current_tick: int,
    include_expired_diagnostics: bool = False,
) -> RuntimeTemporaryMetadataDiagnosticReport | None:
    return RuntimeTemporaryMetadataObservationDiagnosticProvider().build_diagnostics(
        placement,
        authority=authority,
        current_tick=current_tick,
        include_expired_diagnostics=include_expired_diagnostics,
    )


def _report_from_observation(
    observation_report: ContextTemporaryMetadataObservationReport,
    *,
    authority_used: str,
    diagnostic_tick: int,
) -> RuntimeTemporaryMetadataDiagnosticReport:
    observation = observation_report.as_metadata()["observation"]
    expired = tuple(_freeze_mapping(dict(item)) for item in observation["expired_diagnostics"])
    view = RuntimeTemporaryMetadataDiagnosticView(
        active_count=observation["active_count"],
        namespaces_present=observation["namespaces_present"],
        payload_kinds_present=observation["payload_kinds_present"],
        active_metadata=tuple(_freeze_mapping(dict(item)) for item in observation["active_entries"]),
        expired_diagnostics=expired,
        expired_diagnostics_count=len(expired),
        diagnostic_tick=diagnostic_tick,
        authority_used=authority_used,
    )
    return RuntimeTemporaryMetadataDiagnosticReport(view=view)


def _freeze_mapping(value: dict[str, Any]) -> MappingProxyType[str, Any]:
    return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return _freeze_mapping(dict(value))
    if isinstance(value, dict):
        return _freeze_mapping(value)
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
