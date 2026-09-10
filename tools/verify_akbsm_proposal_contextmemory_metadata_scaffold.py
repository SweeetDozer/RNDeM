from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.akbsm_draft_proposal import AKBSM_PROBE_PROPOSAL_SOURCE, AKBSMAssociationProposal
from clc.runtime.akbsm_proposal_contextmemory_metadata import (
    AKBSM_PROPOSAL_CONTEXT_METADATA_SOURCE,
    AKBSM_PROPOSAL_CONTEXT_METADATA_STORAGE_KIND,
    AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY,
    AKBSMProposalContextMemoryMetadata,
    AKBSMProposalContextMemoryMetadataBuilder,
)
from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewController,
    AKBSMProposalReviewRecord,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

MODULE_PATH = ROOT / "clc" / "runtime" / "akbsm_proposal_contextmemory_metadata.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = ROOT / "scenarios" / "akbsm_proposal_contextmemory_metadata_scaffold.json"

EXPECTED_STATES = (
    "review_pending",
    "accepted_for_observation",
    "deferred",
    "rejected",
    "expired",
)
EXPECTED_METADATA_FIELDS = (
    "proposal_id",
    "proposal_reference",
    "lifecycle_state",
    "created_tick",
    "updated_tick",
    "ttl_ticks",
    "expires_at_tick",
    "review_reason",
    "review_notes",
    "transition_history",
    "controller_result",
    "source",
    "temporary",
    "storage_kind",
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
FORBIDDEN_MODULE_IMPORTS = frozenset(
    (
        "ContextMemoryManager",
        "ContextMemory",
        "MemoryWriteReviewModule",
        "MemoryDraftWriter",
        "ExpSMCommitWriter",
        "ExpSMUpdateWriter",
        "AKBSMWriter",
        "AKBSMSave",
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
    "AKBSMProposalContextMemoryMetadata",
    "AKBSMProposalContextMemoryMetadataBuilder",
    "AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY",
)
FORBIDDEN_RUNTIME_WIRING_TARGETS = (
    ROOT / "clc" / "runtime" / "clc_runtime.py",
    ROOT / "clc" / "runtime" / "mode_c_advisory.py",
    ROOT / "clc" / "consolidation",
    ROOT / "clc" / "action",
    ROOT / "clc" / "evaluation",
)
CORE_VERIFIERS = (
    "tools/verify_akbsm_proposal_contextmemory_metadata_adr.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scaffold.py",
    "tools/verify_akbsm_draft_proposal_lifecycle_state_scaffold.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    before = _real_hashes()
    inventory_before = _memory_inventory()
    fixture_spec = _fixture_spec()
    results = {
        "metadata scaffold module exists": MODULE_PATH.exists(),
        "metadata object/builder exists": _case_object_and_builder_exist(),
        "explicit scenario/test authority required": _case_authority_required(),
        "allowed lifecycle states produce temporary metadata": _case_allowed_states(),
        "payload temporary true": _case_payload_flag("temporary", True),
        "payload storage_kind metadata_only": _case_payload_flag(
            "storage_kind", AKBSM_PROPOSAL_CONTEXT_METADATA_STORAGE_KIND
        ),
        "payload source identifies lifecycle": _case_payload_flag(
            "source", AKBSM_PROPOSAL_CONTEXT_METADATA_SOURCE
        ),
        "accepted_for_observation observation-only": _case_observation_only(),
        "deferred is not pending commit": _case_deferred_not_pending_commit(),
        "rejected/expired do not authorize writes": _case_rejected_expired_no_write(),
        "transition result metadata included safely": _case_transition_result_metadata(),
        "scenario fixture exists": SCENARIO_PATH.exists(),
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario fixture metadata complete": _case_fixture_metadata_complete(fixture_spec),
        "no ContextMemoryManager import/call": _case_no_context_memory_manager_import_or_call(),
        "no real ContextMemory write path": _case_no_context_memory_call(),
        "no proposal storage files": _case_no_proposal_storage_files(inventory_before),
        "no permanent proposal queues": _case_no_permanent_queue_text(),
        "no Memory/AKBSM writes": _case_no_memory_file_terms("Memory/AKBSM"),
        "no Memory/ExpSM writes": _case_no_memory_file_terms("Memory/ExpSM"),
        "no semantic_core.json": _case_no_memory_file_terms("semantic_core.json"),
        "no technical_feedback_patterns.json": _case_no_memory_file_terms(
            "technical_feedback_patterns.json"
        ),
        "no normal runtime wiring": _case_no_normal_runtime_wiring(),
        "_run_tick unchanged": _case_run_tick_unchanged(),
        "no forbidden scaffold method names": _case_no_forbidden_methods(),
        "marker 36 absent": _case_marker_36_absent(),
        "core safety still passes": _run_core_verifiers(),
    }
    after = _real_hashes()
    results["Memory inventory unchanged"] = inventory_before == _memory_inventory()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("AKBSM proposal ContextMemory metadata scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_object_and_builder_exist() -> bool:
    return (
        AKBSMProposalContextMemoryMetadata.__name__
        == "AKBSMProposalContextMemoryMetadata"
        and AKBSMProposalContextMemoryMetadataBuilder.__name__
        == "AKBSMProposalContextMemoryMetadataBuilder"
        and AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY
        == AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY
    )


def _case_authority_required() -> bool:
    builder = AKBSMProposalContextMemoryMetadataBuilder()
    record = _record("review_pending")
    return (
        builder.build_metadata(record) is None
        and builder.build_metadata(record, authority="normal_runtime") is None
        and builder.build_metadata(
            record,
            authority=AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY,
        )
        is not None
    )


def _case_allowed_states() -> bool:
    builder = _builder()
    for state in EXPECTED_STATES:
        record = _record(state, ttl_ticks=5)
        metadata = builder.build_metadata(record)
        if metadata is None:
            return False
        payload = metadata.as_payload()
        if not (
            payload["lifecycle_state"] == state
            and payload["temporary"] is True
            and payload["storage_kind"] == "metadata_only"
            and payload["source"] == "akbsm_proposal_lifecycle"
            and payload["expires_at_tick"] == record.created_tick + record.ttl_ticks
        ):
            return False
        try:
            metadata.review_notes = "changed"
        except FrozenInstanceError:
            pass
        else:
            return False
        if not isinstance(payload, MappingProxyType):
            return False
    return True


def _case_payload_flag(key: str, expected: object) -> bool:
    metadata = _builder().build_metadata(_record("review_pending"))
    if metadata is None:
        return False
    return metadata.as_payload().get(key) == expected


def _case_observation_only() -> bool:
    metadata = _builder().build_metadata(_record("accepted_for_observation"))
    if metadata is None:
        return False
    payload = metadata.as_payload()
    return (
        payload["observation_only"] is True
        and payload["akbsm_write_approved"] is False
        and payload["write_authorized"] is False
        and payload["pending_commit"] is False
    )


def _case_deferred_not_pending_commit() -> bool:
    metadata = _builder().build_metadata(_record("deferred"))
    return metadata is not None and metadata.as_payload()["pending_commit"] is False


def _case_rejected_expired_no_write() -> bool:
    builder = _builder()
    for state in ("rejected", "expired"):
        metadata = builder.build_metadata(_record(state))
        if metadata is None:
            return False
        payload = metadata.as_payload()
        if payload["akbsm_write_approved"] or payload["write_authorized"]:
            return False
    return True


def _case_transition_result_metadata() -> bool:
    controller = AKBSMProposalReviewController()
    record = _record("created", ttl_ticks=3)
    result, next_record = controller.request_transition(
        record,
        "review_pending",
        authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
        tick=4,
        reason="metadata coverage",
    )
    if not result.allowed or next_record is None:
        return False
    metadata = _builder().build_metadata(next_record, result)
    if metadata is None:
        return False
    payload = metadata.as_payload()
    return (
        payload["controller_result"]
        == (
            ("from_state", "created"),
            ("to_state", "review_pending"),
            ("allowed", True),
            ("reason", "metadata coverage"),
            ("tick", 4),
        )
        and payload["storage_kind"] == "metadata_only"
        and payload["akbsm_write_approved"] is False
    )


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
        and spec.get("authority") == AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY
        and spec.get("metadata_only") is True
        and spec.get("contextmemory_compatible") is True
        and spec.get("contextmemory_written") is False
        and spec.get("contextmemory_manager_called") is False
        and spec.get("storage_added") is False
        and spec.get("normal_runtime_wiring") is False
        and set(EXPECTED_STATES).issubset(set(spec.get("states_covered", ())))
        and set(EXPECTED_METADATA_FIELDS).issubset(set(spec.get("allowed_metadata_fields", ())))
        and isinstance(safety, dict)
        and safety.get("temporary") is True
        and safety.get("storage_kind") == "metadata_only"
        and safety.get("source") == "akbsm_proposal_lifecycle"
        and safety.get("accepted_for_observation_observation_only") is True
        and safety.get("deferred_pending_commit") is False
        and safety.get("rejected_authorizes_write") is False
        and safety.get("expired_authorizes_write") is False
        and safety.get("transition_result_metadata_allowed") is True
        and safety.get("missing_authority_rejected") is True
        and safety.get("unknown_authority_rejected") is True
        and safety.get("normal_runtime_default_metadata") is False
        and safety.get("storage_files_created") is False
        and safety.get("akbsm_write_forbidden") is True
        and safety.get("expsm_write_forbidden") is True
        and safety.get("marker_36_absent") is True
    )


def _case_no_context_memory_manager_import_or_call() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    return "ContextMemoryManager" not in text and "apply_pending" not in text


def _case_no_context_memory_call() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported_names = tuple(alias.name for alias in node.names)
            if any(name in FORBIDDEN_MODULE_IMPORTS for name in imported_names):
                return False
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.endswith(("context_memory", "context_memory_manager")):
                    return False
        if isinstance(node, ast.Call) and _call_name(node.func) in FORBIDDEN_CALL_NAMES:
            return False
        if isinstance(node, ast.Call) and _call_name(node.func).endswith(
            tuple(f".{name}" for name in FORBIDDEN_CALL_NAMES)
        ):
            return False
    return True


def _case_no_proposal_storage_files(before_inventory: tuple[str, ...]) -> bool:
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
            if not path.exists():
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


def _fixture_spec() -> dict[str, Any]:
    if not SCENARIO_PATH.exists():
        return {}
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    expect = data.get("expect", {})
    if not isinstance(expect, dict):
        return {}
    spec = expect.get("akbsm_contextmemory_metadata_scaffold", {})
    return dict(spec) if isinstance(spec, dict) else {}


def _builder() -> AKBSMProposalContextMemoryMetadataBuilder:
    return AKBSMProposalContextMemoryMetadataBuilder(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY
    )


def _record(state: str, *, ttl_ticks: int | None = None) -> AKBSMProposalReviewRecord:
    return AKBSMProposalReviewRecord(
        proposal=_sample_proposal(),
        state=AKBSMProposalLifecycleState(state),
        created_tick=1,
        updated_tick=2,
        ttl_ticks=ttl_ticks,
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
