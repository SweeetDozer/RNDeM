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

from clc.runtime.context_temporary_metadata import (
    CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataPlacement,
)
from clc.runtime.context_temporary_metadata_diagnostics import (
    CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
    RuntimeTemporaryMetadataObservationDiagnosticProvider,
    build_runtime_temporary_metadata_diagnostics,
)
from clc.runtime.context_temporary_metadata_observation import (
    CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture
from tools import verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold as scaffold


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

MODULE_PATH = ROOT / "clc" / "runtime" / "context_temporary_metadata_diagnostics.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = (
    ROOT
    / "scenarios"
    / "contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.json"
)
DEBUG_AUDIT_PATH = ROOT / "docs" / "debug_name_dependency_audit.json"

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
FORBIDDEN_EXECUTABLE_KEYS = frozenset(
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
FORBIDDEN_INSTRUCTION_FRAGMENTS = frozenset(
    (
        "behavior_instruction",
        "scoring_instruction",
        "guard_instruction",
        "mode_c_instruction",
        "policy_pressure_instruction",
    )
)
CORE_VERIFIERS = (
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py",
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
    report = scaffold._sample_report()
    spec = _fixture_spec()
    results = {
        "negative/no-behavior diagnostic wiring fixture exists": SCENARIO_PATH.exists(),
        "diagnostic scaffold module exists": MODULE_PATH.exists(),
        "missing diagnostic authority rejected": scaffold._case_missing_authority_rejected(),
        "unknown diagnostic authority rejected": scaffold._case_unknown_authority_rejected(),
        "placement authority rejected as diagnostic authority": scaffold._case_placement_authority_rejected(),
        "observation authority rejected as diagnostic authority": scaffold._case_observation_authority_rejected(),
        "diagnostic authority cannot place metadata": scaffold._case_diagnostic_authority_cannot_place(),
        "diagnostic authority cannot authorize writes": scaffold._case_report_no_write_authority(report),
        "diagnostics use existing local temporary metadata observer only": _case_uses_local_observer_only(),
        "diagnostics are read-only": scaffold._case_read_only(report),
        "diagnostics are metadata-only": scaffold._case_metadata_only(report),
        "expired metadata ignored as active": scaffold._case_expired_ignored_as_active(),
        "optional expired diagnostics remain diagnostic-only": scaffold._case_expired_optional_only(),
        "diagnostic report has no writer command fields": scaffold._case_no_writer_command_fields(report),
        "diagnostic report has no behavior/scoring/guard instruction fields": _case_no_instruction_fields(report),
        "diagnostic report has no Mode C/PolicyPressureReview instruction fields": _case_no_mode_policy_instruction_fields(report),
        "AKBSM proposal metadata remains metadata-only": scaffold._case_akbsm_metadata_only(),
        "accepted_for_observation is not write approval": scaffold._case_state_no_write("accepted_for_observation"),
        "deferred is not pending commit": scaffold._case_state_no_write("deferred"),
        "rejected/expired do not authorize writes": scaffold._case_state_no_write("rejected")
        and scaffold._case_state_no_write("expired"),
        "proposal.commit_allowed remains False": scaffold._sample_proposal().commit_allowed is False,
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario fixture metadata complete": _case_fixture_metadata_complete(spec),
        "diagnostic provider is not imported/called by normal runtime": scaffold._case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by _run_tick": scaffold._case_run_tick_unchanged(),
        "diagnostic provider is not imported/called by DecisionSelector": scaffold._case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by ActionScoring": scaffold._case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by ActionProposer": scaffold._case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by ModeActionGuard": scaffold._case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by Mode C": scaffold._case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by PolicyPressureReview": scaffold._case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by memory writers": scaffold._case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by AKBSM writers": scaffold._case_no_normal_runtime_wiring(),
        "diagnostic provider is not imported/called by ExpSM writers": scaffold._case_no_normal_runtime_wiring(),
        "no ContextMemoryManager import/call": scaffold._case_no_contextmemory_manager_reference(),
        "no real ContextMemory reads/writes": scaffold._case_no_real_contextmemory_reference(),
        "no permanent proposal files": scaffold._case_no_permanent_proposal_files(inventory_before),
        "no permanent proposal queues": scaffold._case_no_permanent_queue_text(),
        "no Memory/AKBSM writes": scaffold._case_no_memory_file_terms("Memory/AKBSM"),
        "no Memory/ExpSM writes": scaffold._case_no_memory_file_terms("Memory/ExpSM"),
        "no semantic_core.json": scaffold._case_no_memory_file_terms("semantic_core.json"),
        "no technical_feedback_patterns.json": scaffold._case_no_memory_file_terms(
            "technical_feedback_patterns.json"
        ),
        "no normal runtime wiring": scaffold._case_no_normal_runtime_wiring(),
        "no _run_tick() wiring": scaffold._case_run_tick_unchanged(),
        "no forbidden method names": _case_no_forbidden_methods(),
        "marker 36 absent": scaffold._case_marker_36_absent(),
        "debug-name high-risk findings remain 0": _case_debug_high_risk_zero(),
        "core safety still passes": _run_core_verifiers(),
    }
    after = _real_hashes()
    results["Memory inventory unchanged"] = inventory_before == _memory_inventory()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("ContextMemory temporary metadata diagnostic wiring negative/no-behavior verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_uses_local_observer_only() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    report = build_runtime_temporary_metadata_diagnostics(
        scaffold._placement(),
        authority=CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
        current_tick=4,
    )
    return (
        report is not None
        and "build_temporary_metadata_observation" in text
        and "CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY" in text
        and "clc.context.context_memory" not in text
        and "ContextMemory(" not in text
        and "ContextMemoryManager" not in text
    )


def _case_no_instruction_fields(report: Any) -> bool:
    flattened = _flatten(report.as_payload())
    return not any(
        isinstance(item, str)
        and any(fragment in item.lower() for fragment in FORBIDDEN_INSTRUCTION_FRAGMENTS)
        for item in flattened
    )


def _case_no_mode_policy_instruction_fields(report: Any) -> bool:
    flattened = _flatten(report.as_payload())
    return not any(
        isinstance(item, str)
        and ("mode_c_instruction" in item.lower() or "policy_pressure_instruction" in item.lower())
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
        and cases.get("missing_authority_rejected") is True
        and cases.get("unknown_authority_rejected") is True
        and cases.get("placement_authority_rejected_as_diagnostic_authority") is True
        and cases.get("observation_authority_rejected_as_diagnostic_authority") is True
        and cases.get("diagnostic_authority_cannot_place_metadata") is True
        and cases.get("diagnostic_authority_cannot_authorize_writes") is True
        and cases.get("uses_existing_local_temporary_metadata_observer_only") is True
        and cases.get("active_metadata_diagnostic_count_namespace_payload_kind_ttl_only") is True
        and cases.get("expired_metadata_ignored_as_active") is True
        and cases.get("expired_metadata_optional_diagnostics_only") is True
        and cases.get("writer_commands_present") is False
        and cases.get("behavior_instruction_present") is False
        and cases.get("scoring_instruction_present") is False
        and cases.get("guard_instruction_present") is False
        and cases.get("mode_c_instruction_present") is False
        and cases.get("policy_pressure_instruction_present") is False
        and cases.get("akbsm_proposal_accepted_for_observation_metadata_only") is True
        and cases.get("akbsm_proposal_deferred_non_commit") is True
        and cases.get("akbsm_proposal_rejected_expired_non_authoritative") is True
        and cases.get("accepted_for_observation_observation_only") is True
        and cases.get("deferred_pending_commit") is False
        and cases.get("rejected_authorizes_write") is False
        and cases.get("expired_authorizes_write") is False
        and cases.get("proposal_commit_allowed") is False
        and cases.get("normal_runtime_diagnostic_call") is False
        and cases.get("run_tick_diagnostic_call") is False
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


def _case_no_forbidden_methods() -> bool:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.lower() in FORBIDDEN_METHOD_NAMES:
                return False
    return scaffold._case_no_forbidden_methods()


def _case_debug_high_risk_zero() -> bool:
    if not DEBUG_AUDIT_PATH.exists():
        return False
    data = json.loads(DEBUG_AUDIT_PATH.read_text(encoding="utf-8"))
    return int(data.get("by_risk", {}).get("high", 0)) == 0


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


def _fixture_spec() -> dict[str, Any]:
    if not SCENARIO_PATH.exists():
        return {}
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    expect = data.get("expect", {})
    if not isinstance(expect, dict):
        return {}
    spec = expect.get("contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior", {})
    return dict(spec) if isinstance(spec, dict) else {}


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
