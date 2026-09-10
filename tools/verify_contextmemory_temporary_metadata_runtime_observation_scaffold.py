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
from clc.runtime.context_temporary_metadata_observation import (
    CONTEXT_TEMPORARY_METADATA_OBSERVATION_KIND,
    CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataObservation,
    ContextTemporaryMetadataObservationReport,
    ContextTemporaryMetadataObservationView,
    ContextTemporaryMetadataObserver,
    build_temporary_metadata_observation,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

MODULE_PATH = ROOT / "clc" / "runtime" / "context_temporary_metadata_observation.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = (
    ROOT / "scenarios" / "contextmemory_temporary_metadata_runtime_observation_scaffold.json"
)

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
FORBIDDEN_OUTPUT_FRAGMENTS = frozenset(
    (
        "behavior_instruction",
        "scoring_instruction",
        "guard_instruction",
        "mode_c_instruction",
        "policy_pressure_instruction",
    )
)
FORBIDDEN_RUNTIME_WIRING_SYMBOLS = (
    "context_temporary_metadata_observation",
    "ContextTemporaryMetadataObservation",
    "ContextTemporaryMetadataObservationView",
    "ContextTemporaryMetadataObservationReport",
    "ContextTemporaryMetadataObserver",
    "build_temporary_metadata_observation",
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
    "tools/verify_contextmemory_temporary_metadata_runtime_observation_adr.py",
    "tools/verify_contextmemory_temporary_metadata_negative_retention.py",
    "tools/verify_akbsm_proposal_temporary_metadata_placement_adapter.py",
    "tools/verify_contextmemory_temporary_metadata_placement_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_placement_api_adr.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    before = _real_hashes()
    inventory_before = _memory_inventory()
    spec = _fixture_spec()
    report = _sample_report()
    results = {
        "observation scaffold module exists": MODULE_PATH.exists(),
        "observation report/view objects exist": _case_objects_exist(report),
        "observation API exists": callable(build_temporary_metadata_observation),
        "explicit observation authority is required": _case_authority_required(),
        "missing authority rejected": _case_missing_authority_rejected(),
        "unknown authority rejected": _case_unknown_authority_rejected(),
        "active metadata is visible only as diagnostic material": _case_active_diagnostic(report),
        "expired metadata is ignored as active metadata": _case_expired_ignored_as_active(),
        "optional expired diagnostics do not become active metadata": _case_expired_diagnostics(),
        "observation output is metadata-only": _case_report_metadata_only(report),
        "observation output contains no writer commands": _case_no_writer_commands(report),
        "observation output contains no behavior/scoring/guard instructions": _case_no_instruction_text(
            report
        ),
        "accepted_for_observation is not write approval": _case_state_no_write(
            "accepted_for_observation"
        ),
        "deferred is not pending commit": _case_state_no_write("deferred"),
        "rejected/expired do not authorize writes": _case_rejected_expired_no_write(),
        "proposal.commit_allowed remains False": _case_proposal_commit_allowed_false(),
        "scenario fixture exists": SCENARIO_PATH.exists(),
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario fixture metadata complete": _case_fixture_metadata_complete(spec),
        "no ContextMemoryManager import/call": _case_no_contextmemory_manager_reference(),
        "no real ContextMemory reads/writes": _case_no_real_contextmemory_reference(),
        "no permanent proposal files": _case_no_permanent_proposal_files(inventory_before),
        "no permanent proposal queues": _case_no_permanent_queue_text(),
        "no Memory/AKBSM writes": _case_no_memory_file_terms("Memory/AKBSM"),
        "no Memory/ExpSM writes": _case_no_memory_file_terms("Memory/ExpSM"),
        "no semantic_core.json": _case_no_memory_file_terms("semantic_core.json"),
        "no technical_feedback_patterns.json": _case_no_memory_file_terms(
            "technical_feedback_patterns.json"
        ),
        "no normal runtime wiring": _case_no_normal_runtime_wiring(),
        "no _run_tick() wiring": _case_run_tick_unchanged(),
        "no DecisionSelector influence": _case_no_normal_runtime_wiring(),
        "no ActionScoring influence": _case_no_normal_runtime_wiring(),
        "no ActionProposer influence": _case_no_normal_runtime_wiring(),
        "no ModeActionGuard influence": _case_no_normal_runtime_wiring(),
        "no Mode C influence": _case_no_normal_runtime_wiring(),
        "no PolicyPressureReview influence": _case_no_normal_runtime_wiring(),
        "no memory writer influence": _case_no_normal_runtime_wiring(),
        "no AKBSM writer influence": _case_no_normal_runtime_wiring(),
        "no forbidden method names": _case_no_forbidden_methods(),
        "marker 36 absent": _case_marker_36_absent(),
        "core safety still passes": _run_core_verifiers(),
    }
    after = _real_hashes()
    results["Memory inventory unchanged"] = inventory_before == _memory_inventory()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("ContextMemory temporary metadata runtime observation scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print("  no-behavior-influence proof: included in this scaffold verifier")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_objects_exist(report: ContextTemporaryMetadataObservationReport) -> bool:
    return (
        ContextTemporaryMetadataObservationView.__name__
        == "ContextTemporaryMetadataObservationView"
        and ContextTemporaryMetadataObservation.__name__ == "ContextTemporaryMetadataObservation"
        and ContextTemporaryMetadataObservationReport.__name__
        == "ContextTemporaryMetadataObservationReport"
        and ContextTemporaryMetadataObserver.__name__ == "ContextTemporaryMetadataObserver"
        and isinstance(report, ContextTemporaryMetadataObservationReport)
        and isinstance(report.observation, ContextTemporaryMetadataObservation)
        and all(
            isinstance(view, ContextTemporaryMetadataObservationView)
            for view in report.observation.active_entries
        )
    )


def _case_authority_required() -> bool:
    placement = _sample_placement()
    authorized = build_temporary_metadata_observation(
        placement,
        authority=CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
        current_tick=4,
    )
    placement_authority = build_temporary_metadata_observation(
        placement,
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        current_tick=4,
    )
    return (
        authorized is not None
        and placement_authority is None
        and CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY
        != CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY
    )


def _case_missing_authority_rejected() -> bool:
    return ContextTemporaryMetadataObserver().observe(
        _sample_placement(),
        current_tick=4,
    ) is None


def _case_unknown_authority_rejected() -> bool:
    return build_temporary_metadata_observation(
        _sample_placement(),
        authority="normal_runtime",
        current_tick=4,
    ) is None


def _case_active_diagnostic(report: ContextTemporaryMetadataObservationReport) -> bool:
    payload = report.as_payload()
    observation = payload["observation"]
    return (
        payload["diagnostic_only"] is True
        and payload["observation_only"] is True
        and payload["behavior_influence"] is False
        and payload["scoring_influence"] is False
        and payload["guard_influence"] is False
        and observation["active_count"] == 2
        and observation["namespaces_present"] == (
            "akbsm_proposal_review",
            "scenario",
        )
        and observation["payload_kinds_present"] == (
            "akbsm_proposal_review_metadata",
            "sensor_note",
        )
    )


def _case_expired_ignored_as_active() -> bool:
    report = build_temporary_metadata_observation(
        _sample_placement(),
        authority=CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
        current_tick=4,
    )
    if report is None:
        return False
    observation = report.as_payload()["observation"]
    return (
        observation["active_count"] == 2
        and len(observation["expired_diagnostics"]) == 0
        and all(not entry["expired"] for entry in observation["active_entries"])
    )


def _case_expired_diagnostics() -> bool:
    report = build_temporary_metadata_observation(
        _sample_placement(),
        authority=CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
        current_tick=4,
        include_expired_diagnostics=True,
    )
    if report is None:
        return False
    observation = report.as_payload()["observation"]
    return (
        observation["active_count"] == 2
        and len(observation["expired_diagnostics"]) == 1
        and observation["expired_diagnostics"][0]["expired"] is True
        and observation["expired_diagnostics"][0]["active"] is False
    )


def _case_report_metadata_only(report: ContextTemporaryMetadataObservationReport) -> bool:
    payload = report.as_payload()
    observation = payload["observation"]
    return (
        isinstance(payload, MappingProxyType)
        and payload["metadata_only"] is True
        and payload["diagnostic_only"] is True
        and payload["observation_only"] is True
        and payload["local_only"] is True
        and payload["contextmemory_written"] is False
        and payload["contextmemory_manager_called"] is False
        and payload["normal_runtime_wiring"] is False
        and payload["write_authorized"] is False
        and payload["pending_commit"] is False
        and payload["akbsm_write_approved"] is False
        and payload["expsm_write_approved"] is False
        and observation["observation_kind"] == CONTEXT_TEMPORARY_METADATA_OBSERVATION_KIND
    )


def _case_no_writer_commands(report: ContextTemporaryMetadataObservationReport) -> bool:
    payload = report.as_payload()
    return (
        payload["write_authorized"] is False
        and payload["pending_commit"] is False
        and payload["akbsm_write_approved"] is False
        and payload["expsm_write_approved"] is False
        and payload["proposal_storage_added"] is False
        and payload["review_record_persistence_added"] is False
        and payload["permanent_files_created"] is False
        and payload["permanent_queues_created"] is False
    )


def _case_no_instruction_text(report: ContextTemporaryMetadataObservationReport) -> bool:
    flattened = _flatten(report.as_payload())
    return not any(
        isinstance(item, str)
        and any(fragment in item.lower() for fragment in FORBIDDEN_OUTPUT_FRAGMENTS)
        for item in flattened
    )


def _case_state_no_write(state: str) -> bool:
    report = _akbsm_state_report(state)
    if report is None:
        return False
    payload = report.as_payload()
    active_entries = payload["observation"]["active_entries"]
    return (
        len(active_entries) == 1
        and active_entries[0]["lifecycle_state"] == state
        and active_entries[0]["write_authorized"] is False
        and payload["write_authorized"] is False
        and payload["pending_commit"] is False
        and payload["akbsm_write_approved"] is False
    )


def _case_rejected_expired_no_write() -> bool:
    return _case_state_no_write("rejected") and _case_state_no_write("expired")


def _case_proposal_commit_allowed_false() -> bool:
    return _sample_proposal().commit_allowed is False


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
        and spec.get("authority") == CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY
        and spec.get("placement_authority") == CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY
        and spec.get("metadata_only") is True
        and spec.get("diagnostic_only") is True
        and spec.get("observation_only") is True
        and spec.get("local_only") is True
        and spec.get("observation_kind") == CONTEXT_TEMPORARY_METADATA_OBSERVATION_KIND
        and spec.get("normal_runtime_wiring") is False
        and spec.get("run_tick_wiring") is False
        and spec.get("contextmemory_manager_called") is False
        and spec.get("contextmemory_written") is False
        and spec.get("proposal_storage_added") is False
        and spec.get("review_record_persistence_added") is False
        and spec.get("permanent_files_created") is False
        and spec.get("permanent_queues_created") is False
        and isinstance(cases, dict)
        and cases.get("active_metadata_visible_as_diagnostic") is True
        and cases.get("namespace_payload_kind_count_reported") is True
        and cases.get("expired_metadata_ignored_as_active") is True
        and cases.get("expired_metadata_optional_diagnostics_only") is True
        and cases.get("missing_authority_rejected") is True
        and cases.get("unknown_authority_rejected") is True
        and cases.get("observation_authority_not_placement_authority") is True
        and cases.get("placement_authority_not_write_authority") is True
        and cases.get("akbsm_proposal_metadata_observation_metadata_only") is True
        and cases.get("accepted_for_observation_observation_only") is True
        and cases.get("deferred_pending_commit") is False
        and cases.get("rejected_authorizes_write") is False
        and cases.get("expired_authorizes_write") is False
        and cases.get("behavior_instruction_present") is False
        and cases.get("scoring_instruction_present") is False
        and cases.get("guard_instruction_present") is False
        and cases.get("writer_commands_present") is False
        and cases.get("normal_runtime_observer_call") is False
        and cases.get("contextmemory_manager_called") is False
        and cases.get("real_contextmemory_write") is False
        and cases.get("proposal_storage_files_created") is False
        and cases.get("permanent_proposal_queue_created") is False
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


def _sample_report() -> ContextTemporaryMetadataObservationReport:
    report = build_temporary_metadata_observation(
        _sample_placement(),
        authority=CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
        current_tick=4,
    )
    if report is None:
        raise AssertionError("sample observation report unexpectedly rejected")
    return report


def _sample_placement() -> ContextTemporaryMetadataPlacement:
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
            "transition_result_metadata": {"from_state": "review_pending", "to_state": "accepted_for_observation"},
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


def _akbsm_state_report(state: str) -> ContextTemporaryMetadataObservationReport | None:
    placement = ContextTemporaryMetadataPlacement()
    metadata = AKBSMProposalContextMemoryMetadataBuilder(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY
    ).build_metadata(_record(state))
    if metadata is None:
        return None
    placement.place_temporary_metadata(
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
    return build_temporary_metadata_observation(
        placement,
        authority=CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
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
    spec = expect.get("contextmemory_temporary_metadata_runtime_observation_scaffold", {})
    return dict(spec) if isinstance(spec, dict) else {}


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


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
