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
    AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY,
    AKBSM_PROPOSAL_CONTEXT_METADATA_SOURCE,
    AKBSM_PROPOSAL_CONTEXT_METADATA_STORAGE_KIND,
    AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY,
    AKBSM_PROPOSAL_TEMPORARY_METADATA_KIND,
    AKBSM_PROPOSAL_TEMPORARY_METADATA_NAMESPACE,
    AKBSMProposalContextMemoryMetadata,
    AKBSMProposalContextMemoryMetadataBuilder,
    AKBSMProposalTemporaryMetadataPlacementAdapter,
    place_akbsm_proposal_temporary_metadata,
)
from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewRecord,
)
from clc.runtime.context_temporary_metadata import (
    CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND,
    ContextTemporaryMetadataPlacement,
    ContextTemporaryMetadataPlacementResult,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

MODULE_PATH = ROOT / "clc" / "runtime" / "akbsm_proposal_contextmemory_metadata.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = ROOT / "scenarios" / "akbsm_proposal_temporary_metadata_placement_adapter.json"
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
    "AKBSMProposalTemporaryMetadataPlacementAdapter",
    "place_akbsm_proposal_temporary_metadata",
    "AKBSM_PROPOSAL_TEMPORARY_METADATA_NAMESPACE",
    "AKBSM_PROPOSAL_TEMPORARY_METADATA_KIND",
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
    "tools/verify_contextmemory_temporary_metadata_placement_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_placement_api_adr.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_adr.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scaffold.py",
    "tools/verify_akbsm_draft_proposal_lifecycle_state_scaffold.py",
    "tools/verify_akbsm_probe_draft_proposal_experiment.py",
    "tools/verify_scenario_fixtures.py",
    "tools/verify_memory_mutation_policy.py",
    "tools/verify_debug_name_dependency_audit.py",
    "tools/audit_debug_name_dependencies.py",
)


def main() -> int:
    before = _real_hashes()
    inventory_before = _memory_inventory()
    spec = _fixture_spec()
    results = {
        "adapter exists": _case_adapter_exists(),
        "generic scaffold is the only placement target": _case_generic_scaffold_import_only(),
        "explicit scenario/test authority required": _case_authority_required(),
        "missing authority rejected": _case_missing_authority_rejected(),
        "unknown authority rejected": _case_unknown_authority_rejected(),
        "TTL or expires_at_tick required": _case_ttl_required(),
        "valid metadata accepted into local placement": _case_valid_metadata_accepted(),
        "placement result metadata-only/local-only": _case_result_metadata_only(),
        "proposal metadata converted safely": _case_payload_converted_safely(),
        "write-like metadata rejected": _case_write_like_metadata_rejected(),
        "accepted_for_observation is not write approval": _case_state_no_write(
            "accepted_for_observation"
        ),
        "deferred is not pending commit": _case_deferred_not_pending_commit(),
        "rejected/expired do not authorize writes": _case_rejected_expired_no_write(),
        "adapter helper returns placement result": _case_helper_returns_result(),
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
        "no behavior/scoring/guard/Mode C/PolicyPressureReview wiring": _case_no_behavior_wiring(),
        "no forbidden adapter method names": _case_no_forbidden_methods(),
        "marker 36 absent": _case_marker_36_absent(),
        "core safety still passes": _run_core_verifiers(),
    }
    after = _real_hashes()
    results["Memory inventory unchanged"] = inventory_before == _memory_inventory()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("AKBSM proposal temporary metadata placement adapter verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_adapter_exists() -> bool:
    return (
        AKBSMProposalTemporaryMetadataPlacementAdapter.__name__
        == "AKBSMProposalTemporaryMetadataPlacementAdapter"
        and callable(place_akbsm_proposal_temporary_metadata)
        and AKBSM_PROPOSAL_TEMPORARY_METADATA_NAMESPACE == "akbsm_proposal_review"
        and AKBSM_PROPOSAL_TEMPORARY_METADATA_KIND == "akbsm_proposal_review_metadata"
    )


def _case_generic_scaffold_import_only() -> bool:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports_generic = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "clc.runtime.context_temporary_metadata":
                imported = {alias.name for alias in node.names}
                imports_generic = {
                    "CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY",
                    "ContextTemporaryMetadataPlacement",
                    "ContextTemporaryMetadataPlacementResult",
                }.issubset(imported)
            if node.module and node.module.startswith("clc.context"):
                return False
    return imports_generic


def _case_authority_required() -> bool:
    metadata = _metadata("review_pending")
    placement = ContextTemporaryMetadataPlacement()
    adapter = AKBSMProposalTemporaryMetadataPlacementAdapter()
    authorized = AKBSMProposalTemporaryMetadataPlacementAdapter(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY
    )
    return (
        adapter.place_metadata(metadata, placement) is None
        and adapter.place_metadata(metadata, placement, authority="normal_runtime") is None
        and _is_accepted(authorized.place_metadata(metadata, placement))
    )


def _case_missing_authority_rejected() -> bool:
    return AKBSMProposalTemporaryMetadataPlacementAdapter().place_metadata(
        _metadata("review_pending"), ContextTemporaryMetadataPlacement()
    ) is None


def _case_unknown_authority_rejected() -> bool:
    return AKBSMProposalTemporaryMetadataPlacementAdapter().place_metadata(
        _metadata("review_pending"),
        ContextTemporaryMetadataPlacement(),
        authority="unknown_authority",
    ) is None


def _case_ttl_required() -> bool:
    metadata = AKBSMProposalContextMemoryMetadata(
        proposal_id="proposal_without_expiration",
        proposal_reference=(("source", AKBSM_PROBE_PROPOSAL_SOURCE),),
        lifecycle_state=AKBSMProposalLifecycleState.REVIEW_PENDING,
        created_tick=1,
        updated_tick=1,
        ttl_ticks=None,
        expires_at_tick=None,
        review_reason="metadata only",
        review_notes="temporary only",
        transition_history=("created->review_pending@1",),
    )
    result = _adapter().place_metadata(metadata, ContextTemporaryMetadataPlacement())
    return result is None


def _case_valid_metadata_accepted() -> bool:
    placement = ContextTemporaryMetadataPlacement()
    result = _adapter().place_metadata(_metadata("review_pending"), placement)
    active = placement.list_active_metadata(
        2,
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY,
    )
    return (
        _is_accepted(result)
        and len(active) == 1
        and active[0].namespace == AKBSM_PROPOSAL_TEMPORARY_METADATA_NAMESPACE
        and active[0].source == AKBSM_PROPOSAL_CONTEXT_METADATA_SOURCE
        and active[0].payload_kind == AKBSM_PROPOSAL_TEMPORARY_METADATA_KIND
    )


def _case_result_metadata_only() -> bool:
    result = _placement_result("review_pending")
    if result is None:
        return False
    payload = result.as_metadata()
    entry = payload["entry"]
    return (
        result.accepted is True
        and payload["metadata_only"] is True
        and payload["temporary"] is True
        and payload["local_only"] is True
        and payload["contextmemory_written"] is False
        and payload["contextmemory_manager_called"] is False
        and payload["normal_runtime_wiring"] is False
        and isinstance(entry, MappingProxyType)
        and entry["storage_kind"] == AKBSM_PROPOSAL_CONTEXT_METADATA_STORAGE_KIND
        and entry["placement_kind"] == CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND
        and entry["observation_only"] is True
        and entry["pending_commit"] is False
        and entry["write_authorized"] is False
        and entry["akbsm_write_approved"] is False
    )


def _case_payload_converted_safely() -> bool:
    result = _placement_result("accepted_for_observation")
    if result is None or result.entry is None:
        return False
    payload = dict(result.entry.payload)
    return (
        payload["proposal_id"] == _metadata("accepted_for_observation").proposal_id
        and payload["lifecycle_state"] == "accepted_for_observation"
        and payload["temporary"] is True
        and payload["observation_only"] is True
        and payload["placement_adapter"] == AKBSM_PROPOSAL_TEMPORARY_METADATA_KIND
        and "write_authorized" not in payload
        and "akbsm_write_approved" not in payload
        and "pending_commit" not in payload
    )


def _case_write_like_metadata_rejected() -> bool:
    metadata = AKBSMProposalContextMemoryMetadata(
        proposal_id="proposal_with_instruction",
        proposal_reference=(("source", AKBSM_PROBE_PROPOSAL_SOURCE),),
        lifecycle_state=AKBSMProposalLifecycleState.REVIEW_PENDING,
        created_tick=1,
        updated_tick=1,
        ttl_ticks=3,
        expires_at_tick=4,
        review_reason="metadata only",
        review_notes="ready_to_write",
        transition_history=("created->review_pending@1",),
    )
    result = _adapter().place_metadata(metadata, ContextTemporaryMetadataPlacement())
    return isinstance(result, ContextTemporaryMetadataPlacementResult) and not result.accepted


def _case_state_no_write(state: str) -> bool:
    result = _placement_result(state)
    if result is None:
        return False
    payload = result.as_metadata()
    entry = payload["entry"]
    return (
        payload["write_authorized"] is False
        and payload["akbsm_write_approved"] is False
        and entry["write_authorized"] is False
        and entry["akbsm_write_approved"] is False
    )


def _case_deferred_not_pending_commit() -> bool:
    result = _placement_result("deferred")
    return result is not None and result.as_metadata()["pending_commit"] is False


def _case_rejected_expired_no_write() -> bool:
    return _case_state_no_write("rejected") and _case_state_no_write("expired")


def _case_helper_returns_result() -> bool:
    result = place_akbsm_proposal_temporary_metadata(
        _metadata("review_pending"),
        ContextTemporaryMetadataPlacement(),
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY,
    )
    return _is_accepted(result)


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
        and spec.get("local_only") is True
        and spec.get("placement_kind") == CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND
        and spec.get("contextmemory_manager_called") is False
        and spec.get("contextmemory_written") is False
        and spec.get("normal_runtime_wiring") is False
        and spec.get("proposal_storage_added") is False
        and spec.get("review_record_persistence_added") is False
        and spec.get("permanent_proposal_queue_created") is False
        and set(EXPECTED_STATES).issubset(set(spec.get("states_covered", ())))
        and isinstance(safety, dict)
        and safety.get("missing_authority_rejected") is True
        and safety.get("unknown_authority_rejected") is True
        and safety.get("ttl_or_expiration_required") is True
        and safety.get("write_like_metadata_rejected") is True
        and safety.get("accepted_for_observation_observation_only") is True
        and safety.get("deferred_pending_commit") is False
        and safety.get("rejected_authorizes_write") is False
        and safety.get("expired_authorizes_write") is False
        and safety.get("normal_runtime_default_integration") is False
        and safety.get("akbsm_write_forbidden") is True
        and safety.get("expsm_write_forbidden") is True
        and safety.get("mode_c_disabled") is True
        and safety.get("policy_pressure_review_disconnected") is True
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


def _case_no_behavior_wiring() -> bool:
    for relative_path in (
        "clc/action",
        "clc/evaluation",
        "clc/runtime/mode_c_advisory.py",
        "clc/runtime/policy_pressure.py",
    ):
        path = ROOT / relative_path
        paths = path.rglob("*.py") if path.is_dir() else (path,)
        for item in paths:
            if not item.exists():
                continue
            text = item.read_text(encoding="utf-8")
            if any(symbol in text for symbol in FORBIDDEN_RUNTIME_WIRING_SYMBOLS):
                return False
    return True


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
    if os.environ.get("RNDEM_VERIFIER_SHALLOW") == "1":
        return True
    env = os.environ.copy()
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


def _adapter() -> AKBSMProposalTemporaryMetadataPlacementAdapter:
    return AKBSMProposalTemporaryMetadataPlacementAdapter(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY
    )


def _placement_result(state: str) -> ContextTemporaryMetadataPlacementResult | None:
    return _adapter().place_metadata(_metadata(state), ContextTemporaryMetadataPlacement())


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


def _is_accepted(result: Any) -> bool:
    return isinstance(result, ContextTemporaryMetadataPlacementResult) and result.accepted


def _fixture_spec() -> dict[str, Any]:
    if not SCENARIO_PATH.exists():
        return {}
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    expect = data.get("expect", {})
    if not isinstance(expect, dict):
        return {}
    spec = expect.get("akbsm_proposal_temporary_metadata_placement_adapter", {})
    return dict(spec) if isinstance(spec, dict) else {}


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
