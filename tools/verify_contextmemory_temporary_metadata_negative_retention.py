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
    AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY,
    AKBSMProposalContextMemoryMetadata,
    AKBSMProposalContextMemoryMetadataBuilder,
    AKBSMProposalTemporaryMetadataPlacementAdapter,
)
from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewRecord,
)
from clc.runtime.context_temporary_metadata import (
    CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND,
    CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataPlacement,
    ContextTemporaryMetadataPlacementResult,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

CONTEXT_MODULE_PATH = ROOT / "clc" / "runtime" / "context_temporary_metadata.py"
AKBSM_MODULE_PATH = ROOT / "clc" / "runtime" / "akbsm_proposal_contextmemory_metadata.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = ROOT / "scenarios" / "contextmemory_temporary_metadata_negative_retention_coverage.json"
TARGET_MODULES = (CONTEXT_MODULE_PATH, AKBSM_MODULE_PATH)

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
FORBIDDEN_CALL_NAMES = FORBIDDEN_METHOD_NAMES | frozenset(
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
    )
)
FORBIDDEN_RUNTIME_WIRING_SYMBOLS = (
    "ContextTemporaryMetadataPlacement",
    "ContextTemporaryMetadataPlacementResult",
    "place_temporary_metadata",
    "AKBSMProposalTemporaryMetadataPlacementAdapter",
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
    "tools/verify_akbsm_proposal_temporary_metadata_placement_adapter.py",
    "tools/verify_contextmemory_temporary_metadata_placement_scaffold.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    before = _real_hashes()
    inventory_before = _memory_inventory()
    spec = _fixture_spec()
    results = {
        "negative/retention scenario fixture exists": SCENARIO_PATH.exists(),
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario fixture metadata complete": _case_fixture_metadata_complete(spec),
        "generic rejects missing authority": _case_generic_missing_authority_rejected(),
        "generic rejects unknown authority": _case_generic_unknown_authority_rejected(),
        "generic rejects missing TTL/expiration": _case_generic_missing_ttl_rejected(),
        "generic handles invalid TTL/expiration safely": _case_generic_invalid_ttl_rejected(),
        "generic rejects write-like keys": _case_generic_rejects_write_like_keys(),
        "generic rejects write-like values": _case_generic_rejects_write_like_values(),
        "generic rejects nested write-like metadata": _case_generic_rejects_nested_write_like(),
        "generic rejects behavior/scoring/guard/Mode C/PolicyPressure instructions": (
            _case_generic_rejects_instruction_payloads()
        ),
        "local temporary expiration/removal works": _case_expiration_removal(),
        "AKBSM adapter missing authority safe no-op": _case_adapter_missing_authority_noop(),
        "AKBSM adapter unknown authority safe no-op": _case_adapter_unknown_authority_noop(),
        "AKBSM adapter rejects missing TTL/expiration": _case_adapter_missing_ttl_noop(),
        "AKBSM adapter rejects write-like metadata": _case_adapter_write_like_rejected(),
        "accepted_for_observation is not write approval": _case_adapter_state_no_write(
            "accepted_for_observation"
        ),
        "deferred is not pending commit": _case_adapter_deferred_not_pending(),
        "rejected/expired do not authorize writes": _case_adapter_rejected_expired_no_write(),
        "proposal.commit_allowed remains False": _case_proposal_commit_allowed_false(),
        "no ContextMemoryManager import/call": _case_no_contextmemory_manager_import_or_call(),
        "no real ContextMemory writes": _case_no_real_contextmemory_calls(),
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
        "no forbidden method names": _case_no_forbidden_methods(),
        "marker 36 absent": _case_marker_36_absent(),
        "core safety still passes": _run_core_verifiers(),
    }
    after = _real_hashes()
    results["Memory inventory unchanged"] = inventory_before == _memory_inventory()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("ContextMemory temporary metadata negative/retention verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_generic_missing_authority_rejected() -> bool:
    result = _generic_place(authority=None)
    return not result.accepted and result.entry is None and result.reason == "unauthorized"


def _case_generic_unknown_authority_rejected() -> bool:
    result = _generic_place(authority="normal_runtime")
    return not result.accepted and result.entry is None and result.reason == "unauthorized"


def _case_generic_missing_ttl_rejected() -> bool:
    result = _generic_place(ttl_ticks=None, expires_at_tick=None)
    return not result.accepted and result.entry is None and result.reason == "invalid_metadata"


def _case_generic_invalid_ttl_rejected() -> bool:
    cases = (
        {"ttl_ticks": 0, "expires_at_tick": None},
        {"ttl_ticks": -1, "expires_at_tick": None},
        {"ttl_ticks": None, "expires_at_tick": 1},
        {"ttl_ticks": "bad", "expires_at_tick": None},
    )
    for kwargs in cases:
        result = _generic_place(**kwargs)
        if result.accepted or result.entry is not None:
            return False
    return True


def _case_generic_rejects_write_like_keys() -> bool:
    for key in ("commit", "write_authorized", "akbsm_write", "ready_to_write"):
        result = _generic_place(payload={key: "metadata only"})
        if result.accepted:
            return False
    return True


def _case_generic_rejects_write_like_values() -> bool:
    payloads = (
        {"payload_id": "ctx_negative", "notes": "ready_to_write"},
        {"payload_id": "ctx_negative", "status": "approved_for_akbsm"},
        {"payload_id": "ctx_negative", "memo": "commit instruction"},
    )
    return all(not _generic_place(payload=payload).accepted for payload in payloads)


def _case_generic_rejects_nested_write_like() -> bool:
    payload = {
        "payload_id": "ctx_negative_nested",
        "nested": {
            "safe": ("temporary", {"review": "accepted_for_write"}),
        },
    }
    return not _generic_place(payload=payload).accepted


def _case_generic_rejects_instruction_payloads() -> bool:
    fragments = (
        "behavior_instruction",
        "scoring_instruction",
        "guard_instruction",
        "mode_c_instruction",
        "policy_pressure_instruction",
    )
    for fragment in fragments:
        result = _generic_place(payload={"payload_id": "ctx_negative", "instruction": fragment})
        if result.accepted:
            return False
    return True


def _case_expiration_removal() -> bool:
    placement = ContextTemporaryMetadataPlacement()
    result = _generic_place(
        placement=placement,
        payload={"payload_id": "ctx_expiring"},
        created_tick=2,
        ttl_ticks=2,
    )
    if not result.accepted:
        return False
    active_before = placement.list_active_metadata(
        3,
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    )
    active_at_expiry = placement.list_active_metadata(
        4,
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    )
    expired = placement.expire_metadata(
        4,
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    )
    active_after = placement.list_active_metadata(
        4,
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    )
    unauthorized_expire = placement.expire_metadata(4, authority="normal_runtime")
    return (
        len(active_before) == 1
        and active_at_expiry == ()
        and len(expired) == 1
        and active_after == ()
        and unauthorized_expire == ()
    )


def _case_adapter_missing_authority_noop() -> bool:
    result = AKBSMProposalTemporaryMetadataPlacementAdapter().place_metadata(
        _metadata("review_pending"),
        ContextTemporaryMetadataPlacement(),
    )
    return result is None


def _case_adapter_unknown_authority_noop() -> bool:
    result = _adapter().place_metadata(
        _metadata("review_pending"),
        ContextTemporaryMetadataPlacement(),
        authority="normal_runtime",
    )
    return result is None


def _case_adapter_missing_ttl_noop() -> bool:
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


def _case_adapter_write_like_rejected() -> bool:
    metadata = AKBSMProposalContextMemoryMetadata(
        proposal_id="proposal_with_instruction",
        proposal_reference=(("source", AKBSM_PROBE_PROPOSAL_SOURCE),),
        lifecycle_state=AKBSMProposalLifecycleState.REVIEW_PENDING,
        created_tick=1,
        updated_tick=1,
        ttl_ticks=3,
        expires_at_tick=4,
        review_reason="metadata only",
        review_notes="policy_pressure_instruction",
        transition_history=("created->review_pending@1",),
    )
    result = _adapter().place_metadata(metadata, ContextTemporaryMetadataPlacement())
    return isinstance(result, ContextTemporaryMetadataPlacementResult) and not result.accepted


def _case_adapter_state_no_write(state: str) -> bool:
    result = _adapter_result(state)
    if result is None or result.entry is None:
        return False
    payload = result.as_metadata()
    entry = payload["entry"]
    return (
        result.accepted
        and payload["observation_only"] is True
        and payload["pending_commit"] is False
        and payload["write_authorized"] is False
        and payload["akbsm_write_approved"] is False
        and entry["observation_only"] is True
        and entry["pending_commit"] is False
        and entry["write_authorized"] is False
        and entry["akbsm_write_approved"] is False
    )


def _case_adapter_deferred_not_pending() -> bool:
    return _case_adapter_state_no_write("deferred")


def _case_adapter_rejected_expired_no_write() -> bool:
    return _case_adapter_state_no_write("rejected") and _case_adapter_state_no_write("expired")


def _case_proposal_commit_allowed_false() -> bool:
    proposal = _sample_proposal()
    metadata = _metadata("accepted_for_observation")
    try:
        AKBSMAssociationProposal(
            source=AKBSM_PROBE_PROPOSAL_SOURCE,
            tick=1,
            subject_id="pat_source",
            relation_type="supports",
            object_id="pat_object",
            confidence=0.72,
            evidence=("probe:akbsm_probe_001",),
            reason="metadata only",
            commit_allowed=True,
        )
    except ValueError:
        true_rejected = True
    else:
        true_rejected = False
    return proposal.commit_allowed is False and metadata.as_payload()["pending_commit"] is False and true_rejected


def _case_fixture_runner_safe() -> bool:
    try:
        fixture = load_scenario(SCENARIO_PATH)
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
    except Exception:
        return False
    return result.passed and result.memory_unchanged and not result.marker_sequence


def _case_fixture_metadata_complete(spec: dict[str, Any]) -> bool:
    generic = spec.get("generic_cases", {})
    adapter = spec.get("akbsm_adapter_cases", {})
    boundaries = spec.get("boundaries", {})
    return (
        spec.get("test_only") is True
        and spec.get("authority") == CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY
        and spec.get("metadata_only") is True
        and spec.get("temporary") is True
        and spec.get("local_only") is True
        and spec.get("ttl_required") is True
        and spec.get("placement_kind") == CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND
        and spec.get("normal_runtime_wiring") is False
        and spec.get("contextmemory_manager_called") is False
        and spec.get("contextmemory_written") is False
        and spec.get("proposal_storage_added") is False
        and spec.get("review_record_persistence_added") is False
        and spec.get("permanent_files_created") is False
        and spec.get("permanent_queues_created") is False
        and _all_expected_true(
            generic,
            (
                "missing_authority_rejected",
                "unknown_authority_rejected",
                "missing_ttl_or_expiration_rejected",
                "invalid_ttl_or_expiration_rejected",
                "write_like_payload_keys_rejected",
                "write_like_payload_values_rejected",
                "nested_write_like_payload_rejected",
                "behavior_scoring_guard_mode_policy_instructions_rejected",
                "expired_metadata_removed_or_ignored",
            ),
        )
        and _all_expected_true(
            adapter,
            (
                "missing_authority_safe_noop",
                "unknown_authority_safe_noop",
                "missing_ttl_or_expiration_safe_noop",
                "write_like_metadata_rejected",
                "accepted_for_observation_observation_only",
            ),
        )
        and adapter.get("deferred_pending_commit") is False
        and adapter.get("rejected_authorizes_write") is False
        and adapter.get("expired_authorizes_write") is False
        and adapter.get("proposal_commit_allowed") is False
        and boundaries.get("normal_runtime_default_placement") is False
        and boundaries.get("real_contextmemory_write") is False
        and boundaries.get("contextmemory_manager_called") is False
        and boundaries.get("proposal_storage_files_created") is False
        and boundaries.get("permanent_proposal_queue_created") is False
        and boundaries.get("review_record_persistence_added") is False
        and boundaries.get("akbsm_write_forbidden") is True
        and boundaries.get("expsm_write_forbidden") is True
        and boundaries.get("mode_c_disabled") is True
        and boundaries.get("policy_pressure_review_disconnected") is True
        and boundaries.get("marker_36_absent") is True
    )


def _case_no_contextmemory_manager_import_or_call() -> bool:
    return all(
        "ContextMemoryManager" not in path.read_text(encoding="utf-8")
        and "apply_pending" not in path.read_text(encoding="utf-8")
        for path in TARGET_MODULES
    )


def _case_no_real_contextmemory_calls() -> bool:
    for path in TARGET_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
    return all("permanent proposal queue" not in path.read_text(encoding="utf-8").lower() for path in TARGET_MODULES)


def _case_no_memory_file_terms(term: str) -> bool:
    return all(term not in path.read_text(encoding="utf-8") for path in TARGET_MODULES)


def _case_no_normal_runtime_wiring() -> bool:
    return _case_no_wiring_symbols()


def _case_no_behavior_wiring() -> bool:
    return _case_no_wiring_symbols()


def _case_no_wiring_symbols() -> bool:
    for target in FORBIDDEN_RUNTIME_WIRING_TARGETS:
        paths = target.rglob("*.py") if target.is_dir() else (target,)
        for path in paths:
            if not path.exists() or path in TARGET_MODULES:
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
    for path in TARGET_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
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


def _generic_place(
    payload: dict[str, Any] | None = None,
    *,
    placement: ContextTemporaryMetadataPlacement | None = None,
    authority: str | None = CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    created_tick: int = 1,
    ttl_ticks: Any = 3,
    expires_at_tick: Any = None,
) -> ContextTemporaryMetadataPlacementResult:
    target = placement if placement is not None else ContextTemporaryMetadataPlacement()
    return target.place_temporary_metadata(
        payload if payload is not None else {"payload_id": "ctx_negative_001"},
        namespace="scenario",
        source="scenario_harness",
        authority=authority,
        created_tick=created_tick,
        ttl_ticks=ttl_ticks,
        expires_at_tick=expires_at_tick,
    )


def _adapter() -> AKBSMProposalTemporaryMetadataPlacementAdapter:
    return AKBSMProposalTemporaryMetadataPlacementAdapter(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_INTEGRATION_TEST_SCENARIO_AUTHORITY
    )


def _adapter_result(state: str) -> ContextTemporaryMetadataPlacementResult | None:
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


def _fixture_spec() -> dict[str, Any]:
    if not SCENARIO_PATH.exists():
        return {}
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    expect = data.get("expect", {})
    if not isinstance(expect, dict):
        return {}
    spec = expect.get("contextmemory_temporary_metadata_negative_retention", {})
    return dict(spec) if isinstance(spec, dict) else {}


def _all_expected_true(mapping: Any, keys: tuple[str, ...]) -> bool:
    return isinstance(mapping, dict) and all(mapping.get(key) is True for key in keys)


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
