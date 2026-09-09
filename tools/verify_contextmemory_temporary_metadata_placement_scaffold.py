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
    AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY,
    AKBSMProposalContextMemoryMetadataBuilder,
)
from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewRecord,
)
from clc.runtime.context_temporary_metadata import (
    CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND,
    CONTEXT_TEMPORARY_METADATA_STORAGE_KIND,
    CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataEntry,
    ContextTemporaryMetadataPlacement,
    ContextTemporaryMetadataPlacementPolicy,
    ContextTemporaryMetadataPlacementResult,
    place_temporary_metadata,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

MODULE_PATH = ROOT / "clc" / "runtime" / "context_temporary_metadata.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = ROOT / "scenarios" / "contextmemory_temporary_metadata_placement_scaffold.json"

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
    "ContextTemporaryMetadataEntry",
    "ContextTemporaryMetadataPlacement",
    "ContextTemporaryMetadataPlacementResult",
    "place_temporary_metadata",
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
    "tools/verify_contextmemory_temporary_metadata_placement_api_adr.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    before = _real_hashes()
    inventory_before = _memory_inventory()
    spec = _fixture_spec()
    results = {
        "scaffold module exists": MODULE_PATH.exists(),
        "placement entry/result/policy/API exists": _case_api_exists(),
        "explicit scenario/test authority required": _case_authority_required(),
        "missing/unknown authority rejected": _case_missing_unknown_authority_rejected(),
        "TTL or expires_at_tick required": _case_ttl_required(),
        "valid temporary metadata accepted": _case_valid_metadata_accepted(),
        "payload temporary=true": _case_payload_temporary_true(),
        "placement result is metadata-only": _case_result_metadata_only(),
        "write-like metadata rejected": _case_write_like_metadata_rejected(),
        "AKBSM proposal metadata does not authorize writes": _case_akbsm_metadata_no_write(),
        "accepted_for_observation is not write approval": _case_state_no_write(
            "accepted_for_observation"
        ),
        "deferred is not pending commit": _case_deferred_not_pending_commit(),
        "rejected/expired do not authorize writes": _case_rejected_expired_no_write(),
        "expired metadata can be removed/ignored": _case_expiration(),
        "scenario fixture exists": SCENARIO_PATH.exists(),
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario fixture metadata complete": _case_fixture_metadata_complete(spec),
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

    print("ContextMemory temporary metadata placement scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_api_exists() -> bool:
    return (
        ContextTemporaryMetadataEntry.__name__ == "ContextTemporaryMetadataEntry"
        and ContextTemporaryMetadataPlacementResult.__name__
        == "ContextTemporaryMetadataPlacementResult"
        and ContextTemporaryMetadataPlacementPolicy.__name__
        == "ContextTemporaryMetadataPlacementPolicy"
        and ContextTemporaryMetadataPlacement.__name__ == "ContextTemporaryMetadataPlacement"
        and callable(place_temporary_metadata)
    )


def _case_authority_required() -> bool:
    placement = ContextTemporaryMetadataPlacement()
    default_result = placement.place_temporary_metadata(
        {"payload_id": "ctx_tmp_001"},
        namespace="scenario",
        source="scenario_harness",
        authority=None,
        created_tick=1,
        ttl_ticks=3,
    )
    authorized = placement.place_temporary_metadata(
        {"payload_id": "ctx_tmp_002"},
        namespace="scenario",
        source="scenario_harness",
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        created_tick=1,
        ttl_ticks=3,
    )
    return not default_result.accepted and authorized.accepted


def _case_missing_unknown_authority_rejected() -> bool:
    missing = _placement_result(authority=None)
    unknown = _placement_result(authority="normal_runtime")
    return not missing.accepted and not unknown.accepted


def _case_ttl_required() -> bool:
    result = ContextTemporaryMetadataPlacement().place_temporary_metadata(
        {"payload_id": "ctx_tmp_no_ttl"},
        namespace="scenario",
        source="scenario_harness",
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        created_tick=1,
    )
    return not result.accepted and result.entry is None


def _case_valid_metadata_accepted() -> bool:
    result = _placement_result()
    return (
        result.accepted
        and isinstance(result.entry, ContextTemporaryMetadataEntry)
        and result.entry.expires_at_tick == 4
    )


def _case_payload_temporary_true() -> bool:
    result = _placement_result()
    if result.entry is None:
        return False
    payload = result.entry.as_payload()
    return payload["temporary"] is True and payload["storage_kind"] == CONTEXT_TEMPORARY_METADATA_STORAGE_KIND


def _case_result_metadata_only() -> bool:
    result = _placement_result()
    payload = result.as_payload()
    return (
        isinstance(payload, MappingProxyType)
        and payload["metadata_only"] is True
        and payload["temporary"] is True
        and payload["local_only"] is True
        and payload["contextmemory_written"] is False
        and payload["contextmemory_manager_called"] is False
        and payload["normal_runtime_wiring"] is False
        and payload["behavior_influence"] is False
        and payload["permanent_files_created"] is False
        and payload["permanent_queues_created"] is False
    )


def _case_write_like_metadata_rejected() -> bool:
    bad_payloads = (
        {"commit": "now"},
        {"payload_id": "ok", "nested": {"behavior_instruction": "do something"}},
        {"payload_id": "ok", "notes": ["ready_to_write"]},
        {"payload_id": "ok", "proposal": "approved_for_akbsm"},
    )
    placement = ContextTemporaryMetadataPlacement()
    for payload in bad_payloads:
        result = placement.place_temporary_metadata(
            payload,
            namespace="scenario",
            source="scenario_harness",
            authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
            created_tick=1,
            ttl_ticks=3,
        )
        if result.accepted:
            return False
    return True


def _case_akbsm_metadata_no_write() -> bool:
    metadata = _akbsm_proposal_context_metadata("review_pending")
    if metadata is None:
        return False
    payload = metadata.as_payload()
    safe_payload = {
        "proposal_id": payload["proposal_id"],
        "proposal_reference": payload["proposal_reference"],
        "lifecycle_state": payload["lifecycle_state"],
        "transition_result_metadata": payload["controller_result"],
        "review_reason": payload["review_reason"],
        "review_notes": payload["review_notes"],
        "temporary_metadata_marker": "akbsm_proposal_review_metadata",
    }
    result = ContextTemporaryMetadataPlacement().place_temporary_metadata(
        safe_payload,
        namespace="akbsm_proposal_review",
        source="akbsm_proposal_lifecycle",
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        created_tick=1,
        ttl_ticks=5,
        payload_kind="akbsm_proposal_review_metadata",
        payload_reference={"proposal_id": payload["proposal_id"]},
    )
    result_payload = result.as_payload()
    return (
        result.accepted
        and result_payload["observation_only"] is True
        and result_payload["pending_commit"] is False
        and result_payload["write_authorized"] is False
        and result_payload["akbsm_write_approved"] is False
    )


def _case_state_no_write(state: str) -> bool:
    result = _akbsm_placement_for_state(state)
    payload = result.as_payload()
    return (
        result.accepted
        and payload["observation_only"] is True
        and payload["write_authorized"] is False
        and payload["akbsm_write_approved"] is False
    )


def _case_deferred_not_pending_commit() -> bool:
    result = _akbsm_placement_for_state("deferred")
    return result.accepted and result.as_payload()["pending_commit"] is False


def _case_rejected_expired_no_write() -> bool:
    for state in ("rejected", "expired"):
        result = _akbsm_placement_for_state(state)
        payload = result.as_payload()
        if (
            not result.accepted
            or payload["pending_commit"]
            or payload["write_authorized"]
            or payload["akbsm_write_approved"]
        ):
            return False
    return True


def _case_expiration() -> bool:
    placement = ContextTemporaryMetadataPlacement()
    result = placement.place_temporary_metadata(
        {"payload_id": "ctx_tmp_expiring"},
        namespace="scenario",
        source="scenario_harness",
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        created_tick=2,
        ttl_ticks=2,
    )
    if not result.accepted:
        return False
    before = placement.list_active_metadata(
        3,
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    )
    expired = placement.expire_metadata(
        4,
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    )
    after = placement.list_active_metadata(
        4,
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    )
    unauthorized = placement.expire_metadata(4, authority="normal_runtime")
    return len(before) == 1 and len(expired) == 1 and not after and not unauthorized


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
        and spec.get("authority") == CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY
        and spec.get("metadata_only") is True
        and spec.get("temporary") is True
        and spec.get("local_only") is True
        and spec.get("ttl_required") is True
        and spec.get("storage_kind") == CONTEXT_TEMPORARY_METADATA_STORAGE_KIND
        and spec.get("placement_kind") == CONTEXT_TEMPORARY_METADATA_PLACEMENT_KIND
        and spec.get("normal_runtime_wiring") is False
        and spec.get("contextmemory_manager_called") is False
        and spec.get("contextmemory_written") is False
        and spec.get("proposal_storage_added") is False
        and spec.get("review_record_persistence_added") is False
        and spec.get("permanent_files_created") is False
        and spec.get("permanent_queues_created") is False
        and isinstance(cases, dict)
        and cases.get("valid_ttl_metadata_accepted") is True
        and cases.get("missing_authority_rejected") is True
        and cases.get("unknown_authority_rejected") is True
        and cases.get("metadata_without_ttl_rejected") is True
        and cases.get("write_like_metadata_rejected") is True
        and cases.get("akbsm_proposal_metadata_without_write_approval") is True
        and cases.get("accepted_for_observation_observation_only") is True
        and cases.get("deferred_pending_commit") is False
        and cases.get("rejected_authorizes_write") is False
        and cases.get("expired_authorizes_write") is False
        and cases.get("expired_metadata_removable_or_ignored") is True
        and cases.get("normal_runtime_default_placement") is False
        and cases.get("proposal_storage_files_created") is False
        and cases.get("permanent_proposal_queue_created") is False
        and cases.get("akbsm_write_forbidden") is True
        and cases.get("expsm_write_forbidden") is True
        and cases.get("marker_36_absent") is True
    )


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
    return _case_no_wiring_symbols()


def _case_no_behavior_wiring() -> bool:
    return _case_no_wiring_symbols()


def _case_no_wiring_symbols() -> bool:
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
    if _shallow_enabled():
        return True
    env = dict(__import__("os").environ)
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
    spec = expect.get("contextmemory_temporary_metadata_placement_scaffold", {})
    return dict(spec) if isinstance(spec, dict) else {}


def _placement_result(
    *,
    authority: str | None = CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
) -> ContextTemporaryMetadataPlacementResult:
    return ContextTemporaryMetadataPlacement().place_temporary_metadata(
        {"payload_id": "ctx_tmp_001", "diagnostic_notes": "temporary metadata"},
        namespace="scenario",
        source="scenario_harness",
        authority=authority,
        created_tick=1,
        ttl_ticks=3,
        payload_reference={"payload_id": "ctx_tmp_001"},
    )


def _akbsm_placement_for_state(state: str) -> ContextTemporaryMetadataPlacementResult:
    return ContextTemporaryMetadataPlacement().place_temporary_metadata(
        {
            "proposal_id": f"proposal_{state}",
            "lifecycle_state": state,
            "review_reason": "observation_only",
            "review_notes": "temporary metadata",
            "temporary_metadata_marker": "akbsm_proposal_review_metadata",
        },
        namespace="akbsm_proposal_review",
        source="akbsm_proposal_lifecycle",
        authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
        created_tick=2,
        ttl_ticks=4,
        payload_kind="akbsm_proposal_review_metadata",
        payload_reference={"proposal_id": f"proposal_{state}"},
    )


def _akbsm_proposal_context_metadata(state: str):
    return AKBSMProposalContextMemoryMetadataBuilder(
        authority=AKBSM_PROPOSAL_CONTEXT_METADATA_TEST_SCENARIO_AUTHORITY
    ).build_metadata(_record(state))


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


def _shallow_enabled() -> bool:
    return __import__("os").environ.get("RNDEM_VERIFIER_SHALLOW") == "1"


if __name__ == "__main__":
    raise SystemExit(main())
