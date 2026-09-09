from __future__ import annotations

import ast
import hashlib
import json
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
    AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY,
    AKBSM_PROPOSAL_CONTEXT_METADATA_PLACEMENT,
    AKBSM_PROPOSAL_CONTEXT_METADATA_STORAGE_KIND,
    AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY,
    AKBSMProposalContextMemoryMetadata,
    AKBSMProposalContextMemoryMetadataBuilder,
    AKBSMProposalContextMemoryMetadataIntegration,
    AKBSMProposalContextMemoryMetadataIntegrationResult,
)
from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewRecord,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

MODULE_PATH = ROOT / "clc" / "runtime" / "akbsm_proposal_contextmemory_metadata.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = ROOT / "scenarios" / "akbsm_proposal_contextmemory_metadata_integration_scaffold.json"

EXPECTED_STATES = (
    "review_pending",
    "accepted_for_observation",
    "deferred",
    "rejected",
    "expired",
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
FORBIDDEN_VALUE_FRAGMENTS = frozenset(
    (
        "commit instruction",
        "apply instruction",
        "save instruction",
        "write instruction",
        "persist instruction",
        "mutate instruction",
        "writer command",
        "behavior instruction",
        "scoring instruction",
        "guard instruction",
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
FORBIDDEN_RUNTIME_WIRING_SYMBOLS = (
    "AKBSMProposalContextMemoryMetadataIntegration",
    "AKBSMProposalContextMemoryMetadataIntegrationResult",
    "AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY",
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
    "tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_adr.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scaffold.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    before = _real_hashes()
    inventory_before = _memory_inventory()
    spec = _fixture_spec()
    results = {
        "integration scaffold exists": _case_integration_scaffold_exists(),
        "explicit scenario/test authority required": _case_authority_required(),
        "missing authority rejected": _case_missing_authority_rejected(),
        "unknown authority rejected": _case_unknown_authority_rejected(),
        "integration output temporary metadata only": _case_output_temporary_metadata_only(),
        "review_pending enters boundary under authority": _case_state_enters("review_pending"),
        "accepted_for_observation observation-only": _case_observation_only(),
        "deferred is not pending commit": _case_deferred_not_pending_commit(),
        "rejected/expired do not authorize writes": _case_rejected_expired_no_write(),
        "payload contains no instructions": _case_payload_contains_no_instructions(),
        "scenario fixture exists": SCENARIO_PATH.exists(),
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario fixture metadata complete": _case_fixture_metadata_complete(spec),
        "no ContextMemoryManager import/call": _case_no_context_memory_manager_import_or_call(),
        "no real ContextMemory placement call": _case_no_real_contextmemory_call(),
        "no permanent proposal files": _case_no_permanent_proposal_files(inventory_before),
        "no permanent proposal queues": _case_no_permanent_queue_text(),
        "no Memory/AKBSM writes": _case_no_memory_file_terms("Memory/AKBSM"),
        "no Memory/ExpSM writes": _case_no_memory_file_terms("Memory/ExpSM"),
        "no semantic_core.json": _case_no_memory_file_terms("semantic_core.json"),
        "no technical_feedback_patterns.json": _case_no_memory_file_terms(
            "technical_feedback_patterns.json"
        ),
        "no normal runtime wiring": _case_no_normal_runtime_wiring(),
        "no _run_tick wiring": _case_run_tick_unchanged(),
        "no forbidden integration method names": _case_no_forbidden_methods(),
        "marker 36 absent": _case_marker_36_absent(),
        "core safety still passes": _run_core_verifiers(),
    }
    after = _real_hashes()
    results["Memory inventory unchanged"] = inventory_before == _memory_inventory()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("AKBSM proposal ContextMemory metadata integration scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_integration_scaffold_exists() -> bool:
    return (
        AKBSMProposalContextMemoryMetadataIntegration.__name__
        == "AKBSMProposalContextMemoryMetadataIntegration"
        and AKBSMProposalContextMemoryMetadataIntegrationResult.__name__
        == "AKBSMProposalContextMemoryMetadataIntegrationResult"
        and AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY
        == AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY
    )


def _case_authority_required() -> bool:
    metadata = _metadata("review_pending")
    integration = AKBSMProposalContextMemoryMetadataIntegration()
    authorized = AKBSMProposalContextMemoryMetadataIntegration(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY
    )
    return (
        integration.integrate_metadata(metadata) is None
        and integration.integrate_metadata(metadata, authority="normal_runtime") is None
        and authorized.integrate_metadata(metadata) is not None
    )


def _case_missing_authority_rejected() -> bool:
    metadata = _metadata("review_pending")
    return AKBSMProposalContextMemoryMetadataIntegration().integrate_metadata(metadata) is None


def _case_unknown_authority_rejected() -> bool:
    metadata = _metadata("review_pending")
    return (
        AKBSMProposalContextMemoryMetadataIntegration()
        .integrate_metadata(metadata, authority="unknown_authority")
        is None
    )


def _case_output_temporary_metadata_only() -> bool:
    result = _result("review_pending")
    if result is None:
        return False
    payload = result.as_context_metadata()
    proposal_metadata = payload.get("proposal_metadata")
    return (
        isinstance(result, AKBSMProposalContextMemoryMetadataIntegrationResult)
        and isinstance(payload, MappingProxyType)
        and isinstance(proposal_metadata, MappingProxyType)
        and payload["temporary"] is True
        and payload["metadata_only"] is True
        and payload["placement"] == AKBSM_PROPOSAL_CONTEXT_METADATA_PLACEMENT
        and proposal_metadata["storage_kind"] == AKBSM_PROPOSAL_CONTEXT_METADATA_STORAGE_KIND
        and payload["contextmemory_written"] is False
        and payload["contextmemory_manager_called"] is False
        and payload["proposal_storage_added"] is False
        and payload["review_record_persistence_added"] is False
    )


def _case_state_enters(state: str) -> bool:
    result = _result(state)
    return result is not None and result.as_payload()["proposal_metadata"]["lifecycle_state"] == state


def _case_observation_only() -> bool:
    result = _result("accepted_for_observation")
    if result is None:
        return False
    payload = result.as_payload()
    metadata = payload["proposal_metadata"]
    return (
        payload["observation_only"] is True
        and metadata["observation_only"] is True
        and payload["akbsm_write_approved"] is False
        and payload["write_authorized"] is False
        and metadata["akbsm_write_approved"] is False
        and metadata["write_authorized"] is False
    )


def _case_deferred_not_pending_commit() -> bool:
    result = _result("deferred")
    if result is None:
        return False
    payload = result.as_payload()
    return (
        payload["pending_commit"] is False
        and payload["proposal_metadata"]["pending_commit"] is False
    )


def _case_rejected_expired_no_write() -> bool:
    for state in ("rejected", "expired"):
        result = _result(state)
        if result is None:
            return False
        payload = result.as_payload()
        metadata = payload["proposal_metadata"]
        if (
            payload["akbsm_write_approved"]
            or payload["write_authorized"]
            or metadata["akbsm_write_approved"]
            or metadata["write_authorized"]
        ):
            return False
    return True


def _case_payload_contains_no_instructions() -> bool:
    for state in EXPECTED_STATES:
        result = _result(state)
        if result is None:
            return False
        for value in _flatten_values(result.as_payload()):
            if isinstance(value, str):
                lowered = value.lower()
                if any(fragment in lowered for fragment in FORBIDDEN_VALUE_FRAGMENTS):
                    return False
    return True


def _case_fixture_runner_safe() -> bool:
    try:
        fixture = load_scenario(SCENARIO_PATH)
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
    except Exception:
        return False
    return result.passed and result.memory_unchanged and not result.marker_sequence


def _case_fixture_metadata_complete(spec: dict[str, Any]) -> bool:
    safety = spec.get("safety", {})
    return (
        spec.get("test_only") is True
        and spec.get("authority")
        == AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY
        and spec.get("metadata_only") is True
        and spec.get("temporary") is True
        and spec.get("integration_shape") == "deferred_boundary_result"
        and spec.get("contextmemory_placement") == "deferred"
        and spec.get("contextmemory_written") is False
        and spec.get("contextmemory_manager_called") is False
        and spec.get("storage_added") is False
        and spec.get("review_record_persistence_added") is False
        and spec.get("normal_runtime_wiring") is False
        and set(EXPECTED_STATES).issubset(set(spec.get("states_covered", ())))
        and isinstance(safety, dict)
        and safety.get("review_pending_under_authority") is True
        and safety.get("accepted_for_observation_observation_only") is True
        and safety.get("deferred_pending_commit") is False
        and safety.get("rejected_authorizes_write") is False
        and safety.get("expired_authorizes_write") is False
        and safety.get("missing_authority_rejected") is True
        and safety.get("unknown_authority_rejected") is True
        and safety.get("normal_runtime_default_integration") is False
        and safety.get("proposal_storage_files_created") is False
        and safety.get("permanent_proposal_queue_created") is False
        and safety.get("akbsm_write_forbidden") is True
        and safety.get("expsm_write_forbidden") is True
        and safety.get("marker_36_absent") is True
    )


def _case_no_context_memory_manager_import_or_call() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    return "ContextMemoryManager" not in text and "apply_pending" not in text


def _case_no_real_contextmemory_call() -> bool:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("clc.context"):
                    return False
            for alias in node.names:
                if alias.name in {"ContextMemory", "ContextMemoryManager"}:
                    return False
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in FORBIDDEN_CALL_NAMES:
                return False
            if call_name.endswith(tuple(f".{name}" for name in FORBIDDEN_CALL_NAMES)):
                return False
    return True


def _case_no_permanent_proposal_files(before_inventory: tuple[str, ...]) -> bool:
    after_inventory = _memory_inventory()
    return before_inventory == after_inventory and not any(
        "proposal" in path.lower() for path in after_inventory
    )


def _case_no_permanent_queue_text() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8").lower()
    return "permanent proposal queue" not in text and "proposal queue" not in text


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
    for relative_path in CORE_VERIFIERS:
        result = subprocess.run([sys.executable, "-B", relative_path], cwd=ROOT, check=False)
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
    spec = expect.get("akbsm_contextmemory_metadata_integration_scaffold", {})
    return dict(spec) if isinstance(spec, dict) else {}


def _result(state: str) -> AKBSMProposalContextMemoryMetadataIntegrationResult | None:
    return AKBSMProposalContextMemoryMetadataIntegration(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY
    ).integrate_metadata(_metadata(state))


def _metadata(state: str) -> AKBSMProposalContextMemoryMetadata:
    metadata = AKBSMProposalContextMemoryMetadataBuilder(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY
    ).build_metadata(_record(state))
    if metadata is None:
        raise RuntimeError("expected metadata under scenario/test authority")
    return metadata


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


def _flatten_values(value: Any) -> tuple[Any, ...]:
    if isinstance(value, MappingProxyType):
        flattened: list[Any] = []
        for item in value.values():
            flattened.extend(_flatten_values(item))
        return tuple(flattened)
    if isinstance(value, dict):
        flattened = []
        for item in value.values():
            flattened.extend(_flatten_values(item))
        return tuple(flattened)
    if isinstance(value, (tuple, list)):
        flattened = []
        for item in value:
            flattened.extend(_flatten_values(item))
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
    return tuple(sorted(str(path.relative_to(ROOT)) for path in (ROOT / "Memory").rglob("*") if path.is_file()))


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
