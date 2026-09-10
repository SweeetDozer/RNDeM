from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.akbsm_draft_proposal import AKBSM_PROBE_PROPOSAL_SOURCE, AKBSMAssociationProposal
from clc.runtime.akbsm_proposal_contextmemory_metadata import (
    AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY,
    AKBSMProposalContextMemoryMetadataBuilder,
)
from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewRecord,
)
from clc.runtime.context_temporary_metadata import (
    CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataPlacement,
)
from clc.runtime.context_temporary_metadata_diagnostics import (
    CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
    RuntimeTemporaryMetadataDiagnosticReport,
    RuntimeTemporaryMetadataDiagnosticView,
    RuntimeTemporaryMetadataObservationDiagnosticProvider,
    build_runtime_temporary_metadata_diagnostics,
)
from clc.runtime.context_temporary_metadata_observation import (
    CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

MODULE_PATH = ROOT / "clc" / "runtime" / "context_temporary_metadata_diagnostics.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = ROOT / "scenarios" / "contextmemory_temporary_metadata_diagnostic_wiring_scaffold.json"

FORBIDDEN_METHOD_NAMES = frozenset(
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
    )
)
FORBIDDEN_CALL_NAMES = frozenset(
    (
        "open",
        "mkdir",
        "replace",
        "unlink",
        "dump",
        "dumps",
        "add_event",
        "add_frame",
        "apply_retention",
        "apply_side_list_retention",
        "apply_pending",
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
    )
)
FORBIDDEN_EXECUTABLE_KEYS = frozenset(
    ("commit", "apply", "save", "write", "persist", "mutate", "store", "enqueue", "flush", "sync")
)
FORBIDDEN_INSTRUCTION_FRAGMENTS = frozenset(
    ("behavior_instruction", "scoring_instruction", "guard_instruction")
)
FORBIDDEN_RUNTIME_WIRING_SYMBOLS = (
    "context_temporary_metadata_diagnostics",
    "RuntimeTemporaryMetadataDiagnosticReport",
    "RuntimeTemporaryMetadataDiagnosticView",
    "RuntimeTemporaryMetadataObservationDiagnosticProvider",
    "build_runtime_temporary_metadata_diagnostics",
)
FORBIDDEN_RUNTIME_WIRING_TARGETS = (
    ROOT / "clc" / "runtime" / "clc_runtime.py",
    ROOT / "clc" / "runtime" / "mode_c_advisory.py",
    ROOT / "clc" / "consolidation",
    ROOT / "clc" / "action",
    ROOT / "clc" / "evaluation",
    ROOT / "clc" / "system",
)
CORE_VERIFIERS = (
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_adr.py",
    "tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_runtime_observation_adr.py",
    "tools/verify_contextmemory_temporary_metadata_negative_retention.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    before = _real_hashes()
    inventory_before = _memory_inventory()
    report = _sample_report()
    spec = _fixture_spec()
    results = {
        "diagnostic scaffold module exists": MODULE_PATH.exists(),
        "diagnostic report/view/provider objects exist": _case_objects_exist(report),
        "explicit diagnostic API exists": callable(build_runtime_temporary_metadata_diagnostics),
        "explicit diagnostic authority is required": _case_authority_required(),
        "missing authority rejected": _case_missing_authority_rejected(),
        "unknown authority rejected": _case_unknown_authority_rejected(),
        "placement authority rejected as diagnostic authority": _case_placement_authority_rejected(),
        "observation authority rejected as diagnostic authority": _case_observation_authority_rejected(),
        "diagnostic authority cannot place metadata": _case_diagnostic_authority_cannot_place(),
        "diagnostic authority cannot authorize writes": _case_report_no_write_authority(report),
        "diagnostics use existing temporary metadata observer": _case_uses_existing_observer(),
        "diagnostics are read-only": _case_read_only(report),
        "diagnostics are metadata-only": _case_metadata_only(report),
        "expired metadata ignored as active": _case_expired_ignored_as_active(),
        "expired metadata only appears in optional diagnostics": _case_expired_optional_only(),
        "AKBSM proposal metadata remains metadata-only": _case_akbsm_metadata_only(),
        "accepted_for_observation is not write approval": _case_state_no_write("accepted_for_observation"),
        "deferred is not pending commit": _case_state_no_write("deferred"),
        "rejected/expired do not authorize writes": _case_state_no_write("rejected")
        and _case_state_no_write("expired"),
        "proposal.commit_allowed remains False": _sample_proposal().commit_allowed is False,
        "diagnostic report has no writer command fields": _case_no_writer_command_fields(report),
        "diagnostic report has no behavior/scoring/guard instruction fields": _case_no_instruction_fields(report),
        "scenario fixture exists": SCENARIO_PATH.exists(),
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario fixture metadata complete": _case_fixture_metadata_complete(spec),
        "diagnostic provider is not imported/called by normal runtime": _case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by _run_tick": _case_run_tick_unchanged(),
        "diagnostic provider is not imported/called by DecisionSelector": _case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by ActionScoring": _case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by ActionProposer": _case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by ModeActionGuard": _case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by Mode C": _case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by PolicyPressureReview": _case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by memory writers": _case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by AKBSM writers": _case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by ExpSM writers": _case_no_normal_runtime_wiring(),
        "no ContextMemoryManager import/call": _case_no_contextmemory_manager_reference(),
        "no real ContextMemory reads/writes": _case_no_real_contextmemory_reference(),
        "no permanent proposal files": _case_no_permanent_proposal_files(inventory_before),
        "no permanent proposal queues": _case_no_permanent_queue_text(),
        "no Memory/AKBSM writes": _case_no_memory_file_terms("Memory/AKBSM"),
        "no Memory/ExpSM writes": _case_no_memory_file_terms("Memory/ExpSM"),
        "no semantic_core.json": _case_no_memory_file_terms("semantic_core.json"),
        "no technical_feedback_patterns.json": _case_no_memory_file_terms("technical_feedback_patterns.json"),
        "no normal runtime wiring": _case_no_normal_runtime_wiring(),
        "no _run_tick() wiring": _case_run_tick_unchanged(),
        "no forbidden method names": _case_no_forbidden_methods(),
        "marker 36 absent": _case_marker_36_absent(),
        "core safety still passes": _run_core_verifiers(),
    }
    after = _real_hashes()
    results["Memory inventory unchanged"] = inventory_before == _memory_inventory()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("ContextMemory temporary metadata diagnostic wiring scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print("  no-behavior-influence proof: included in this scaffold verifier")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_objects_exist(report: RuntimeTemporaryMetadataDiagnosticReport) -> bool:
    return (
        RuntimeTemporaryMetadataDiagnosticReport.__name__
        == "RuntimeTemporaryMetadataDiagnosticReport"
        and RuntimeTemporaryMetadataDiagnosticView.__name__
        == "RuntimeTemporaryMetadataDiagnosticView"
        and RuntimeTemporaryMetadataObservationDiagnosticProvider.__name__
        == "RuntimeTemporaryMetadataObservationDiagnosticProvider"
        and isinstance(report, RuntimeTemporaryMetadataDiagnosticReport)
        and isinstance(report.view, RuntimeTemporaryMetadataDiagnosticView)
    )


def _case_authority_required() -> bool:
    authorized = build_runtime_temporary_metadata_diagnostics(
        _placement(),
        authority=CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
        current_tick=4,
    )
    return authorized is not None and _case_missing_authority_rejected()


def _case_missing_authority_rejected() -> bool:
    return RuntimeTemporaryMetadataObservationDiagnosticProvider().build_diagnostics(
        _placement(),
        current_tick=4,
    ) is None


def _case_unknown_authority_rejected() -> bool:
    return build_runtime_temporary_metadata_diagnostics(
        _placement(),
        authority="normal_runtime",
        current_tick=4,
    ) is None


def _case_placement_authority_rejected() -> bool:
    return build_runtime_temporary_metadata_diagnostics(
        _placement(),
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        current_tick=4,
    ) is None


def _case_observation_authority_rejected() -> bool:
    return build_runtime_temporary_metadata_diagnostics(
        _placement(),
        authority=CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
        current_tick=4,
    ) is None


def _case_diagnostic_authority_cannot_place() -> bool:
    result = ContextTemporaryMetadataPlacement().place_temporary_metadata(
        {"payload_id": "runtime_diag_auth_cannot_place"},
        namespace="scenario",
        source="scenario_harness",
        authority=CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
        created_tick=1,
        ttl_ticks=3,
    )
    return not result.accepted and result.entry is None


def _case_report_no_write_authority(report: RuntimeTemporaryMetadataDiagnosticReport) -> bool:
    payload = report.as_payload()
    return (
        payload["write_authorized"] is False
        and payload["pending_commit"] is False
        and payload["akbsm_write_approved"] is False
        and payload["expsm_write_approved"] is False
        and payload["proposal_storage_added"] is False
        and payload["review_record_persistence_added"] is False
    )


def _case_uses_existing_observer() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    return (
        "build_temporary_metadata_observation" in text
        and "CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY" in text
    )


def _case_read_only(report: RuntimeTemporaryMetadataDiagnosticReport) -> bool:
    payload = report.as_payload()
    return (
        payload["read_only"] is True
        and payload["contextmemory_read"] is False
        and payload["contextmemory_written"] is False
        and payload["contextmemory_manager_called"] is False
        and payload["normal_runtime_default"] is False
        and payload["run_tick_default"] is False
    )


def _case_metadata_only(report: RuntimeTemporaryMetadataDiagnosticReport) -> bool:
    payload = report.as_payload()
    view = payload["view"]
    return (
        isinstance(payload, MappingProxyType)
        and payload["metadata_only"] is True
        and payload["diagnostic_only"] is True
        and payload["observation_only"] is True
        and view["metadata_only"] is True
        and view["diagnostic_only"] is True
        and view["active_count"] == 2
        and view["namespaces_present"] == ("akbsm_proposal_review", "scenario")
        and view["payload_kinds_present"] == ("akbsm_proposal_review_metadata", "sensor_note")
        and view["authority_used"] == CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY
        and view["diagnostic_tick"] == 4
    )


def _case_expired_ignored_as_active() -> bool:
    report = build_runtime_temporary_metadata_diagnostics(
        _placement(),
        authority=CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
        current_tick=4,
    )
    if report is None:
        return False
    view = report.as_payload()["view"]
    return view["active_count"] == 2 and view["expired_diagnostics_count"] == 0


def _case_expired_optional_only() -> bool:
    report = build_runtime_temporary_metadata_diagnostics(
        _placement(),
        authority=CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
        current_tick=4,
        include_expired_diagnostics=True,
    )
    if report is None:
        return False
    view = report.as_payload()["view"]
    expired = view["expired_diagnostics"]
    return (
        view["active_count"] == 2
        and view["expired_diagnostics_count"] == 1
        and expired[0]["expired"] is True
        and expired[0]["active"] is False
        and expired[0]["diagnostic_only"] is True
        and expired[0]["write_authorized"] is False
    )


def _case_akbsm_metadata_only() -> bool:
    report = _state_report("accepted_for_observation")
    if report is None:
        return False
    view = report.as_payload()["view"]
    active = view["active_metadata"]
    return (
        len(active) == 1
        and active[0]["lifecycle_state"] == "accepted_for_observation"
        and active[0]["metadata_only"] is True
        and active[0]["observation_only"] is True
        and active[0]["pending_commit"] is False
        and active[0]["write_authorized"] is False
    )


def _case_state_no_write(state: str) -> bool:
    report = _state_report(state)
    if report is None:
        return False
    payload = report.as_payload()
    active = payload["view"]["active_metadata"]
    return (
        len(active) == 1
        and active[0]["lifecycle_state"] == state
        and active[0]["write_authorized"] is False
        and active[0]["pending_commit"] is False
        and payload["write_authorized"] is False
        and payload["pending_commit"] is False
        and payload["akbsm_write_approved"] is False
    )


def _case_no_writer_command_fields(report: RuntimeTemporaryMetadataDiagnosticReport) -> bool:
    keys = _flatten_keys(report.as_payload())
    return not any(key in FORBIDDEN_EXECUTABLE_KEYS for key in keys)


def _case_no_instruction_fields(report: RuntimeTemporaryMetadataDiagnosticReport) -> bool:
    flattened = _flatten(report.as_payload())
    return not any(
        isinstance(item, str)
        and any(fragment in item.lower() for fragment in FORBIDDEN_INSTRUCTION_FRAGMENTS)
        for item in flattened
    )


def _case_fixture_runner_safe() -> bool:
    try:
        fixture = load_scenario(SCENARIO_PATH)
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
    except Exception:
        return False
    return result.passed and result.memory_unchanged and not result.marker_sequence


def _case_fixture_metadata_complete(spec: dict[str, Any]) -> bool:
    cases = spec.get("cases", {})
    return (
        spec.get("test_only") is True
        and spec.get("authority") == CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY
        and spec.get("observation_authority")
        == CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY
        and spec.get("placement_authority") == CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY
        and spec.get("metadata_only") is True
        and spec.get("diagnostic_only") is True
        and spec.get("read_only") is True
        and spec.get("observation_only") is True
        and spec.get("local_only") is True
        and spec.get("normal_runtime_default") is False
        and spec.get("run_tick_default") is False
        and spec.get("contextmemory_manager_called") is False
        and spec.get("contextmemory_read") is False
        and spec.get("contextmemory_written") is False
        and spec.get("proposal_storage_added") is False
        and spec.get("review_record_persistence_added") is False
        and spec.get("permanent_files_created") is False
        and spec.get("permanent_queues_created") is False
        and isinstance(cases, dict)
        and cases.get("diagnostic_report_explicit_authority") is True
        and cases.get("missing_authority_rejected") is True
        and cases.get("unknown_authority_rejected") is True
        and cases.get("placement_authority_rejected") is True
        and cases.get("observation_authority_rejected") is True
        and cases.get("diagnostic_authority_cannot_place_metadata") is True
        and cases.get("diagnostic_authority_cannot_authorize_writes") is True
        and cases.get("uses_existing_temporary_metadata_observer") is True
        and cases.get("active_metadata_diagnostic_only") is True
        and cases.get("expired_metadata_ignored_as_active") is True
        and cases.get("expired_metadata_optional_diagnostics_only") is True
        and cases.get("namespace_payload_kind_count_ttl_metadata_only") is True
        and cases.get("akbsm_proposal_metadata_metadata_only") is True
        and cases.get("accepted_for_observation_observation_only") is True
        and cases.get("deferred_pending_commit") is False
        and cases.get("rejected_authorizes_write") is False
        and cases.get("expired_authorizes_write") is False
        and cases.get("proposal_commit_allowed") is False
        and cases.get("writer_commands_present") is False
        and cases.get("behavior_scoring_guard_instruction_present") is False
        and cases.get("normal_runtime_provider_call") is False
        and cases.get("run_tick_provider_call") is False
        and cases.get("selector_scoring_proposer_guard_mode_policy_writer_calls") is False
        and cases.get("real_contextmemory_read") is False
        and cases.get("real_contextmemory_write") is False
        and cases.get("proposal_storage_files_created") is False
        and cases.get("permanent_proposal_queue_created") is False
        and cases.get("review_record_persistence_added") is False
        and cases.get("akbsm_write_forbidden") is True
        and cases.get("expsm_write_forbidden") is True
        and cases.get("marker_36_absent") is True
    )


def _case_no_contextmemory_manager_reference() -> bool:
    return "ContextMemoryManager" not in MODULE_PATH.read_text(encoding="utf-8")


def _case_no_real_contextmemory_reference() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    return "clc.context.context_memory" not in text and "ContextMemory(" not in text


def _case_no_permanent_proposal_files(before_inventory: tuple[str, ...]) -> bool:
    after_inventory = _memory_inventory()
    return before_inventory == after_inventory and not any(
        "proposal" in path.lower() for path in after_inventory
    )


def _case_no_permanent_queue_text() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8").lower()
    return "permanent proposal queue" not in text and "proposal queue persistence" not in text


def _case_no_memory_file_terms(term: str) -> bool:
    return term not in MODULE_PATH.read_text(encoding="utf-8")


def _case_no_normal_runtime_wiring() -> bool:
    for target in FORBIDDEN_RUNTIME_WIRING_TARGETS:
        paths = target.rglob("*.py") if target.is_dir() else (target,)
        for path in paths:
            if not path.exists() or path == MODULE_PATH:
                continue
            text = path.read_text(encoding="utf-8")
            if any(symbol in text for symbol in FORBIDDEN_RUNTIME_WIRING_SYMBOLS):
                return False
    return True


def _case_run_tick_unchanged() -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", "main...HEAD", "--", str(RUNTIME_PATH.relative_to(ROOT))],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def _case_no_forbidden_methods() -> bool:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.lower() in FORBIDDEN_METHOD_NAMES:
                return False
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in FORBIDDEN_CALL_NAMES:
                return False
            if call_name.endswith(tuple(f".{name}" for name in FORBIDDEN_CALL_NAMES)):
                return False
    return True


def _case_marker_36_absent() -> bool:
    forbidden_marker_name = "MARKER" + "_36"
    forbidden_marker_attr = "OperationMarker." + "36"
    forbidden_marker_ctor = "OperationMarker(" + "36"
    for path in (ROOT / "clc").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if forbidden_marker_name in text or forbidden_marker_attr in text or forbidden_marker_ctor in text:
            return False
    return True


def _run_core_verifiers() -> bool:
    if os.environ.get("RNDEM_VERIFIER_SHALLOW") == "1":
        return True
    env = dict(os.environ)
    env["RNDEM_VERIFIER_SHALLOW"] = "1"
    for relative_path in CORE_VERIFIERS:
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=ROOT,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            return False
    return True


def _sample_report() -> RuntimeTemporaryMetadataDiagnosticReport:
    report = build_runtime_temporary_metadata_diagnostics(
        _placement(),
        authority=CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
        current_tick=4,
    )
    if report is None:
        raise AssertionError("diagnostic report unexpectedly rejected")
    return report


def _placement() -> ContextTemporaryMetadataPlacement:
    placement = ContextTemporaryMetadataPlacement()
    placement.place_temporary_metadata(
        {"payload_id": "active_note", "diagnostic_notes": "temporary metadata"},
        namespace="scenario",
        source="scenario_harness",
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        created_tick=3,
        ttl_ticks=4,
        notes="diagnostic notes",
        payload_kind="sensor_note",
        payload_reference={"payload_id": "active_note"},
    )
    placement.place_temporary_metadata(
        {"payload_id": "expired_note", "diagnostic_notes": "temporary metadata"},
        namespace="scenario",
        source="scenario_harness",
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        created_tick=1,
        ttl_ticks=2,
        notes="expired diagnostic notes",
        payload_kind="sensor_note",
        payload_reference={"payload_id": "expired_note"},
    )
    placement.place_temporary_metadata(
        {
            "proposal_id": "proposal_observation",
            "lifecycle_state": "accepted_for_observation",
            "transition_result_metadata": {
                "from_state": "review_pending",
                "to_state": "accepted_for_observation",
            },
            "diagnostic_notes": "proposal metadata only",
        },
        namespace="akbsm_proposal_review",
        source="akbsm_proposal_lifecycle",
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        created_tick=3,
        ttl_ticks=4,
        notes="proposal observation metadata",
        payload_kind="akbsm_proposal_review_metadata",
        payload_reference={"proposal_id": "proposal_observation"},
    )
    return placement


def _state_report(state: str) -> RuntimeTemporaryMetadataDiagnosticReport | None:
    placement = ContextTemporaryMetadataPlacement()
    metadata = AKBSMProposalContextMemoryMetadataBuilder(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY
    ).build_metadata(_record(state))
    if metadata is None:
        return None
    result = placement.place_temporary_metadata(
        {
            "proposal_id": metadata.proposal_id,
            "lifecycle_state": metadata.lifecycle_state.value,
            "transition_result_metadata": {"state": metadata.lifecycle_state.value},
            "diagnostic_notes": metadata.review_notes,
        },
        namespace="akbsm_proposal_review",
        source="akbsm_proposal_lifecycle",
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        created_tick=metadata.created_tick,
        ttl_ticks=metadata.ttl_ticks,
        expires_at_tick=metadata.expires_at_tick,
        notes=metadata.review_notes,
        payload_kind="akbsm_proposal_review_metadata",
        payload_reference={"proposal_id": metadata.proposal_id},
    )
    if not result.accepted:
        return None
    return build_runtime_temporary_metadata_diagnostics(
        placement,
        authority=CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
        current_tick=2,
    )


def _record(state: str) -> AKBSMProposalReviewRecord:
    return AKBSMProposalReviewRecord(
        proposal=_sample_proposal(),
        state=AKBSMProposalLifecycleState(state),
        created_tick=1,
        updated_tick=2,
        ttl_ticks=5,
        review_reason="scenario metadata",
        review_notes="temporary only",
        transition_history=("created->review_pending@2",),
    )


def _sample_proposal() -> AKBSMAssociationProposal:
    return AKBSMAssociationProposal(
        source=AKBSM_PROBE_PROPOSAL_SOURCE,
        tick=1,
        subject_id="pat_source",
        relation_type="supports",
        object_id="pat_object",
        confidence=0.72,
        evidence=("probe:akbsm_probe_001",),
        reason="metadata only",
    )


def _fixture_spec() -> dict[str, Any]:
    if not SCENARIO_PATH.exists():
        return {}
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    expect = data.get("expect", {})
    if not isinstance(expect, dict):
        return {}
    spec = expect.get("contextmemory_temporary_metadata_diagnostic_wiring_scaffold", {})
    return dict(spec) if isinstance(spec, dict) else {}


def _flatten_keys(value: Any) -> tuple[str, ...]:
    if isinstance(value, MappingProxyType):
        return _flatten_keys(dict(value))
    if isinstance(value, dict):
        keys: list[str] = []
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_flatten_keys(item))
        return tuple(keys)
    if isinstance(value, (tuple, list, set)):
        keys = []
        for item in value:
            keys.extend(_flatten_keys(item))
        return tuple(keys)
    return ()


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


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def _memory_inventory() -> tuple[str, ...]:
    return tuple(
        sorted(str(path.relative_to(ROOT)) for path in (ROOT / "Memory").rglob("*") if path.is_file())
    )


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
