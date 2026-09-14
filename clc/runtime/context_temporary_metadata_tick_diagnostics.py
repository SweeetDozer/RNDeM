from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable

from clc.runtime.context_temporary_metadata import (
    CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataPlacement,
)
from clc.runtime.context_temporary_metadata_diagnostics import (
    CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
    RuntimeTemporaryMetadataDiagnosticReport,
    build_runtime_temporary_metadata_diagnostics,
)
from clc.runtime.context_temporary_metadata_observation import (
    CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
)


CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY = (
    "explicit_tick_diagnostic_harness"
)
CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_KIND = (
    "temporary_metadata_tick_diagnostic_snapshot"
)


@dataclass(frozen=True)
class TemporaryMetadataTickDiagnosticSnapshot:
    """Separate read-only tick-near diagnostic snapshot."""

    diagnostic_report: RuntimeTemporaryMetadataDiagnosticReport
    diagnostic_tick: int
    authority_used: str
    diagnostics_enabled: bool = True
    diagnostic_kind: str = CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_KIND
    metadata_only: bool = True
    diagnostic_only: bool = True
    read_only: bool = True
    local_only: bool = True
    behavior_influence: bool = False
    scoring_influence: bool = False
    guard_influence: bool = False
    mode_c_influence: bool = False
    policy_pressure_review_influence: bool = False
    write_authorized: bool = False
    pending_commit: bool = False
    akbsm_write_approved: bool = False
    expsm_write_approved: bool = False
    contextmemory_manager_called: bool = False
    contextmemory_read: bool = False
    contextmemory_written: bool = False
    normal_runtime_default: bool = False
    run_tick_default: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.diagnostic_report, RuntimeTemporaryMetadataDiagnosticReport):
            raise TypeError("diagnostic_report must be RuntimeTemporaryMetadataDiagnosticReport")
        if self.authority_used != CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY:
            raise ValueError("tick diagnostic snapshot requires tick diagnostic authority")
        if self.diagnostic_kind != CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_KIND:
            raise ValueError("diagnostic_kind must remain tick diagnostic metadata")
        if (
            self.metadata_only is not True
            or self.diagnostic_only is not True
            or self.read_only is not True
            or self.local_only is not True
            or self.diagnostics_enabled is not True
        ):
            raise ValueError("tick diagnostic snapshot must remain enabled read-only metadata")
        if (
            self.behavior_influence
            or self.scoring_influence
            or self.guard_influence
            or self.mode_c_influence
            or self.policy_pressure_review_influence
            or self.write_authorized
            or self.pending_commit
            or self.akbsm_write_approved
            or self.expsm_write_approved
            or self.contextmemory_manager_called
            or self.contextmemory_read
            or self.contextmemory_written
            or self.normal_runtime_default
            or self.run_tick_default
        ):
            raise ValueError("tick diagnostic snapshot cannot authorize side effects")
        object.__setattr__(self, "diagnostic_tick", _non_negative_int(self.diagnostic_tick))

    def as_metadata(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(
            {
                "diagnostic_kind": self.diagnostic_kind,
                "diagnostic_tick": self.diagnostic_tick,
                "authority_used": self.authority_used,
                "diagnostics_enabled": self.diagnostics_enabled,
                "diagnostic_report": self.diagnostic_report.as_payload(),
                "metadata_only": self.metadata_only,
                "diagnostic_only": self.diagnostic_only,
                "read_only": self.read_only,
                "local_only": self.local_only,
                "behavior_influence": self.behavior_influence,
                "scoring_influence": self.scoring_influence,
                "guard_influence": self.guard_influence,
                "mode_c_influence": self.mode_c_influence,
                "policy_pressure_review_influence": self.policy_pressure_review_influence,
                "write_authorized": self.write_authorized,
                "pending_commit": self.pending_commit,
                "akbsm_write_approved": self.akbsm_write_approved,
                "expsm_write_approved": self.expsm_write_approved,
                "contextmemory_manager_called": self.contextmemory_manager_called,
                "contextmemory_read": self.contextmemory_read,
                "contextmemory_written": self.contextmemory_written,
                "normal_runtime_default": self.normal_runtime_default,
                "run_tick_default": self.run_tick_default,
            }
        )

    def as_payload(self) -> MappingProxyType[str, Any]:
        return self.as_metadata()


@dataclass(frozen=True)
class TemporaryMetadataTickDiagnosticWrapperResult:
    """Behavior output plus optional separate diagnostics."""

    behavior_output: Any
    diagnostic_snapshot: TemporaryMetadataTickDiagnosticSnapshot | None
    diagnostics_enabled: bool
    diagnostic_authority: str
    diagnostic_tick: int
    metadata_only: bool = True
    diagnostic_only: bool = True
    read_only: bool = True
    local_only: bool = True
    external_wrapper: bool = True
    behavior_output_unchanged: bool = True
    diagnostic_data_passed_to_tick: bool = False
    normal_runtime_default: bool = False
    run_tick_default: bool = False
    tick_order_changed: bool = False
    apply_pending_timing_changed: bool = False
    behavior_influence: bool = False
    scoring_influence: bool = False
    guard_influence: bool = False
    mode_c_influence: bool = False
    policy_pressure_review_influence: bool = False
    write_authorized: bool = False
    pending_commit: bool = False
    akbsm_write_approved: bool = False
    expsm_write_approved: bool = False
    contextmemory_manager_called: bool = False
    contextmemory_read: bool = False
    contextmemory_written: bool = False
    permanent_files_created: bool = False
    permanent_queues_created: bool = False
    proposal_storage_added: bool = False
    review_record_persistence_added: bool = False

    def __post_init__(self) -> None:
        if self.diagnostic_authority != CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY:
            raise ValueError("wrapper result requires tick diagnostic authority")
        if self.diagnostic_snapshot is not None and not isinstance(
            self.diagnostic_snapshot, TemporaryMetadataTickDiagnosticSnapshot
        ):
            raise TypeError("diagnostic_snapshot must be TemporaryMetadataTickDiagnosticSnapshot")
        if bool(self.diagnostics_enabled) != (self.diagnostic_snapshot is not None):
            raise ValueError("diagnostics_enabled must match diagnostic snapshot presence")
        if (
            self.metadata_only is not True
            or self.diagnostic_only is not True
            or self.read_only is not True
            or self.local_only is not True
            or self.external_wrapper is not True
            or self.behavior_output_unchanged is not True
        ):
            raise ValueError("wrapper result must remain external read-only diagnostics")
        if (
            self.diagnostic_data_passed_to_tick
            or self.normal_runtime_default
            or self.run_tick_default
            or self.tick_order_changed
            or self.apply_pending_timing_changed
            or self.behavior_influence
            or self.scoring_influence
            or self.guard_influence
            or self.mode_c_influence
            or self.policy_pressure_review_influence
            or self.write_authorized
            or self.pending_commit
            or self.akbsm_write_approved
            or self.expsm_write_approved
            or self.contextmemory_manager_called
            or self.contextmemory_read
            or self.contextmemory_written
            or self.permanent_files_created
            or self.permanent_queues_created
            or self.proposal_storage_added
            or self.review_record_persistence_added
        ):
            raise ValueError("wrapper result cannot authorize side effects")
        object.__setattr__(self, "diagnostic_tick", _non_negative_int(self.diagnostic_tick))
        object.__setattr__(self, "diagnostics_enabled", bool(self.diagnostics_enabled))

    def as_metadata(self) -> MappingProxyType[str, Any]:
        snapshot = (
            None if self.diagnostic_snapshot is None else self.diagnostic_snapshot.as_payload()
        )
        return MappingProxyType(
            {
                "behavior_output": self.behavior_output,
                "diagnostic_snapshot": snapshot,
                "diagnostics_enabled": self.diagnostics_enabled,
                "diagnostic_authority": self.diagnostic_authority,
                "diagnostic_tick": self.diagnostic_tick,
                "metadata_only": self.metadata_only,
                "diagnostic_only": self.diagnostic_only,
                "read_only": self.read_only,
                "local_only": self.local_only,
                "external_wrapper": self.external_wrapper,
                "behavior_output_unchanged": self.behavior_output_unchanged,
                "diagnostic_data_passed_to_tick": self.diagnostic_data_passed_to_tick,
                "normal_runtime_default": self.normal_runtime_default,
                "run_tick_default": self.run_tick_default,
                "tick_order_changed": self.tick_order_changed,
                "apply_pending_timing_changed": self.apply_pending_timing_changed,
                "behavior_influence": self.behavior_influence,
                "scoring_influence": self.scoring_influence,
                "guard_influence": self.guard_influence,
                "mode_c_influence": self.mode_c_influence,
                "policy_pressure_review_influence": self.policy_pressure_review_influence,
                "write_authorized": self.write_authorized,
                "pending_commit": self.pending_commit,
                "akbsm_write_approved": self.akbsm_write_approved,
                "expsm_write_approved": self.expsm_write_approved,
                "contextmemory_manager_called": self.contextmemory_manager_called,
                "contextmemory_read": self.contextmemory_read,
                "contextmemory_written": self.contextmemory_written,
                "permanent_files_created": self.permanent_files_created,
                "permanent_queues_created": self.permanent_queues_created,
                "proposal_storage_added": self.proposal_storage_added,
                "review_record_persistence_added": self.review_record_persistence_added,
            }
        )

    def as_payload(self) -> MappingProxyType[str, Any]:
        return self.as_metadata()


@dataclass(frozen=True)
class TemporaryMetadataTickDiagnosticWrapper:
    """External harness wrapper for tick-near temporary metadata diagnostics."""

    authority: str | None = None

    def run(
        self,
        tick_callable: Callable[..., Any],
        *,
        placement: ContextTemporaryMetadataPlacement,
        authority: str | None = None,
        current_tick: int,
        include_expired_diagnostics: bool = False,
        diagnostics_enabled: bool = True,
        tick_args: tuple[Any, ...] = (),
        tick_kwargs: dict[str, Any] | None = None,
    ) -> TemporaryMetadataTickDiagnosticWrapperResult | None:
        active_authority = authority if authority is not None else self.authority
        if active_authority != CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY:
            return None
        if active_authority in (
            CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
            CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
            CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
        ):
            return None
        if not callable(tick_callable):
            raise TypeError("tick_callable must be callable")
        if not isinstance(placement, ContextTemporaryMetadataPlacement):
            raise TypeError("placement must be ContextTemporaryMetadataPlacement")
        tick = _non_negative_int(current_tick)
        args = tuple(tick_args)
        kwargs = dict(tick_kwargs or {})
        behavior_output = tick_callable(*args, **kwargs)
        snapshot = None
        if diagnostics_enabled:
            report = build_runtime_temporary_metadata_diagnostics(
                placement,
                authority=CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
                current_tick=tick,
                include_expired_diagnostics=include_expired_diagnostics,
            )
            if report is None:
                return None
            snapshot = TemporaryMetadataTickDiagnosticSnapshot(
                diagnostic_report=report,
                diagnostic_tick=tick,
                authority_used=active_authority,
            )
        return TemporaryMetadataTickDiagnosticWrapperResult(
            behavior_output=behavior_output,
            diagnostic_snapshot=snapshot,
            diagnostics_enabled=bool(diagnostics_enabled),
            diagnostic_authority=active_authority,
            diagnostic_tick=tick,
        )


def run_tick_with_temporary_metadata_diagnostics(
    tick_callable: Callable[..., Any],
    *,
    placement: ContextTemporaryMetadataPlacement,
    authority: str,
    current_tick: int,
    include_expired_diagnostics: bool = False,
    diagnostics_enabled: bool = True,
    tick_args: tuple[Any, ...] = (),
    tick_kwargs: dict[str, Any] | None = None,
) -> TemporaryMetadataTickDiagnosticWrapperResult | None:
    return TemporaryMetadataTickDiagnosticWrapper().run(
        tick_callable,
        placement=placement,
        authority=authority,
        current_tick=current_tick,
        include_expired_diagnostics=include_expired_diagnostics,
        diagnostics_enabled=diagnostics_enabled,
        tick_args=tick_args,
        tick_kwargs=tick_kwargs,
    )


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
