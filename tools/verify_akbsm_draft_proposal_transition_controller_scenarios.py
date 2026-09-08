from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture
from clc.runtime.akbsm_draft_proposal import AKBSM_PROBE_PROPOSAL_SOURCE, AKBSMAssociationProposal
from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewController,
    AKBSMProposalReviewRecord,
)


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

SCENARIO_PATH = ROOT / "scenarios" / "akbsm_transition_controller_metadata_coverage.json"
LIFECYCLE_PATH = ROOT / "clc" / "runtime" / "akbsm_proposal_lifecycle.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
EXPECTED_ALLOWED_TRANSITIONS = (
    ("created", "review_pending"),
    ("review_pending", "accepted_for_observation"),
    ("review_pending", "deferred"),
    ("review_pending", "rejected"),
    ("review_pending", "expired"),
    ("accepted_for_observation", "expired"),
    ("deferred", "review_pending"),
    ("deferred", "expired"),
    ("rejected", "expired"),
)
EXPECTED_FORBIDDEN_TRANSITIONS = (
    ("expired", "accepted_for_observation"),
    ("expired", "review_pending"),
    ("rejected", "accepted_for_observation"),
    ("rejected", "review_pending"),
    ("accepted_for_observation", "review_pending"),
    ("accepted_for_observation", "deferred"),
    ("created", "accepted_for_observation"),
)
EXPECTED_WRITE_LIKE_TARGETS = (
    "committed",
    "applied",
    "persisted",
    "written",
    "saved",
    "accepted_for_write",
    "ready_to_write",
    "approved_for_akbsm",
    "commit",
    "apply",
    "save",
    "write",
    "persist",
    "mutate",
)
FORBIDDEN_METHOD_NAMES = (
    "commit",
    "apply",
    "save",
    "write",
    "persist",
    "mutate",
    "execute_transition",
    "apply_transition",
    "commit_transition",
    "persist_transition",
    "save_transition",
    "write_transition",
)
FORBIDDEN_STORAGE_TERMS = (
    "ContextMemoryManager",
    "ContextMemory",
    "Memory/AKBSM",
    "Memory/ExpSM",
    "semantic_core.json",
    "technical_feedback_patterns.json",
    "permanent proposal",
    "permanent association",
)
FORBIDDEN_RUNTIME_WIRING_SYMBOLS = (
    "AKBSMProposalReviewController",
    "AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY",
)
FORBIDDEN_RUNTIME_WIRING_TARGETS = (
    ROOT / "clc" / "runtime" / "clc_runtime.py",
    ROOT / "clc" / "runtime" / "mode_c_advisory.py",
    ROOT / "clc" / "consolidation",
    ROOT / "clc" / "action",
    ROOT / "clc" / "evaluation",
)
CORE_VERIFIERS = (
    "tools/verify_akbsm_draft_proposal_transition_controller_scaffold.py",
    "tools/verify_akbsm_draft_proposal_lifecycle_state_scaffold.py",
    "tools/verify_akbsm_draft_proposal_scaffold.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    before = _real_hashes()
    fixture_spec = _fixture_spec()
    memory_inventory_before = _memory_inventory()
    results = {
        "scenario fixture exists": SCENARIO_PATH.exists(),
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario metadata complete": _case_scenario_metadata_complete(fixture_spec),
        "allowed transitions covered": _case_allowed_transitions_covered(fixture_spec),
        "forbidden transitions covered": _case_forbidden_transitions_covered(fixture_spec),
        "write-like targets covered": _case_write_like_targets_covered(fixture_spec),
        "allowed transitions accepted": _case_allowed_transitions_accepted(fixture_spec),
        "forbidden transitions rejected": _case_forbidden_transitions_rejected(fixture_spec),
        "write-like targets rejected": _case_write_like_targets_rejected(fixture_spec),
        "immutable copy behavior": _case_immutable_copy_behavior(),
        "proposal unchanged": _case_proposal_unchanged(),
        "expiration metadata-only": _case_expiration_metadata_only(),
        "no proposal storage": _case_no_proposal_storage(),
        "no ContextMemory storage integration": _case_no_context_memory_storage(),
        "normal runtime does not call controller": _case_no_normal_runtime_wiring(),
        "_run_tick unchanged": _case_run_tick_unchanged(),
        "no forbidden transition methods": _case_no_forbidden_transition_methods(),
        "marker 36 absent": _case_marker_36_absent(),
        "core safety still passes": _run_core_verifiers(),
    }
    memory_inventory_after = _memory_inventory()
    after = _real_hashes()
    results["Memory inventory unchanged"] = memory_inventory_before == memory_inventory_after
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("AKBSM draft proposal transition controller scenario verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _fixture_spec() -> dict[str, Any]:
    if not SCENARIO_PATH.exists():
        return {}
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    expect = data.get("expect", {})
    if not isinstance(expect, dict):
        return {}
    spec = expect.get("akbsm_transition_controller", {})
    return dict(spec) if isinstance(spec, dict) else {}


def _case_fixture_runner_safe() -> bool:
    try:
        fixture = load_scenario(SCENARIO_PATH)
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
    except Exception:
        return False
    return result.passed and result.memory_unchanged and not result.marker_sequence


def _case_scenario_metadata_complete(spec: dict[str, Any]) -> bool:
    copy_behavior = spec.get("copy_behavior", {})
    expiration = spec.get("expiration", {})
    safety = spec.get("safety", {})
    return (
        spec.get("test_only") is True
        and spec.get("authority") == AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY
        and spec.get("metadata_only") is True
        and spec.get("storage_added") is False
        and spec.get("context_memory_storage_added") is False
        and spec.get("normal_runtime_wiring") is False
        and isinstance(copy_behavior, dict)
        and copy_behavior.get("original_record_unchanged") is True
        and copy_behavior.get("proposal_unchanged") is True
        and copy_behavior.get("commit_allowed") is False
        and isinstance(expiration, dict)
        and expiration.get("metadata_only") is True
        and expiration.get("target_state") == "expired"
        and isinstance(safety, dict)
        and safety.get("akbsm_write_forbidden") is True
        and safety.get("expsm_write_forbidden") is True
        and safety.get("marker_36_absent") is True
    )


def _case_allowed_transitions_covered(spec: dict[str, Any]) -> bool:
    return _transition_set(spec.get("allowed_transitions")) == set(EXPECTED_ALLOWED_TRANSITIONS)


def _case_forbidden_transitions_covered(spec: dict[str, Any]) -> bool:
    return set(EXPECTED_FORBIDDEN_TRANSITIONS).issubset(
        _transition_set(spec.get("forbidden_transitions"))
    )


def _case_write_like_targets_covered(spec: dict[str, Any]) -> bool:
    values = spec.get("write_like_targets", [])
    return isinstance(values, list) and set(EXPECTED_WRITE_LIKE_TARGETS).issubset(
        {str(item) for item in values}
    )


def _case_allowed_transitions_accepted(spec: dict[str, Any]) -> bool:
    controller = AKBSMProposalReviewController()
    for source, target in _transition_set(spec.get("allowed_transitions")):
        record = _record(source)
        result, next_record = controller.request_transition(
            record,
            target,
            authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
            tick=3,
            reason="scenario coverage",
            notes="metadata only",
        )
        if not (
            result.allowed is True
            and result.from_state == AKBSMProposalLifecycleState(source)
            and result.to_state == AKBSMProposalLifecycleState(target)
            and next_record is not None
            and next_record is not record
            and next_record.proposal is record.proposal
            and next_record.state == AKBSMProposalLifecycleState(target)
            and next_record.updated_tick == 3
            and record.state == AKBSMProposalLifecycleState(source)
            and record.proposal.commit_allowed is False
        ):
            return False
    return True


def _case_forbidden_transitions_rejected(spec: dict[str, Any]) -> bool:
    controller = AKBSMProposalReviewController()
    for source, target in _transition_set(spec.get("forbidden_transitions")):
        record = _record(source)
        result, next_record = controller.request_transition(
            record,
            target,
            authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
            tick=4,
        )
        if result.allowed or next_record is not None or record.state != AKBSMProposalLifecycleState(source):
            return False
    return True


def _case_write_like_targets_rejected(spec: dict[str, Any]) -> bool:
    controller = AKBSMProposalReviewController()
    record = _record("review_pending")
    values = spec.get("write_like_targets", [])
    if not isinstance(values, list):
        return False
    for target in values:
        result, next_record = controller.request_transition(
            record,
            str(target),
            authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
            tick=5,
        )
        if result.allowed or next_record is not None:
            return False
    return record.state == AKBSMProposalLifecycleState.REVIEW_PENDING


def _case_immutable_copy_behavior() -> bool:
    controller = AKBSMProposalReviewController()
    record = _record("created", transition_history=("seed",))
    result, next_record = controller.request_transition(
        record,
        "review_pending",
        authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
        tick=6,
    )
    if not result.allowed or next_record is None:
        return False
    try:
        next_record.review_notes = "changed"
    except FrozenInstanceError:
        immutable = True
    else:
        immutable = False
    return (
        immutable
        and next_record is not record
        and next_record.transition_history == ("seed", "created->review_pending@6")
        and record.transition_history == ("seed",)
        and record.state == AKBSMProposalLifecycleState.CREATED
        and next_record.state == AKBSMProposalLifecycleState.REVIEW_PENDING
    )


def _case_proposal_unchanged() -> bool:
    controller = AKBSMProposalReviewController()
    proposal = _sample_proposal()
    record = AKBSMProposalReviewRecord(
        proposal=proposal,
        state="created",
        created_tick=1,
        updated_tick=1,
    )
    proposal_before = proposal
    result, next_record = controller.request_transition(
        record,
        "review_pending",
        authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
        tick=7,
    )
    return (
        result.allowed is True
        and next_record is not None
        and proposal == proposal_before
        and record.proposal is proposal
        and next_record.proposal is proposal
        and proposal.commit_allowed is False
    )


def _case_expiration_metadata_only() -> bool:
    controller = AKBSMProposalReviewController()
    record = _record("accepted_for_observation", ttl_ticks=4)
    result, next_record = controller.request_expiration(
        record,
        authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
        tick=8,
        reason="ttl_expired",
    )
    return (
        result.allowed is True
        and result.to_state == AKBSMProposalLifecycleState.EXPIRED
        and next_record is not None
        and next_record.state == AKBSMProposalLifecycleState.EXPIRED
        and next_record.ttl_ticks == 4
        and record.state == AKBSMProposalLifecycleState.ACCEPTED_FOR_OBSERVATION
        and next_record.proposal.commit_allowed is False
    )


def _case_no_proposal_storage() -> bool:
    text = LIFECYCLE_PATH.read_text(encoding="utf-8")
    if any(term in text for term in FORBIDDEN_STORAGE_TERMS):
        return False
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if (
                call_name in {"open", "mkdir", "replace", "unlink", "dump", "dumps"}
                or call_name.endswith(".open")
                or call_name.endswith(".write")
                or call_name.endswith(".save")
                or call_name.endswith(".dump")
            ):
                return False
    return True


def _case_no_context_memory_storage() -> bool:
    text = LIFECYCLE_PATH.read_text(encoding="utf-8")
    return "ContextMemory" not in text and "ContextMemoryManager" not in text


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


def _case_no_forbidden_transition_methods() -> bool:
    tree = ast.parse(LIFECYCLE_PATH.read_text(encoding="utf-8"))
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


def _transition_set(value: object) -> set[tuple[str, str]]:
    if not isinstance(value, list):
        return set()
    transitions: set[tuple[str, str]] = set()
    for item in value:
        if isinstance(item, list) and len(item) == 2:
            transitions.add((str(item[0]), str(item[1])))
    return transitions


def _record(
    state: str,
    *,
    ttl_ticks: int | None = None,
    transition_history: tuple[str, ...] = (),
) -> AKBSMProposalReviewRecord:
    return AKBSMProposalReviewRecord(
        proposal=_sample_proposal(),
        state=state,
        created_tick=1,
        updated_tick=1,
        ttl_ticks=ttl_ticks,
        transition_history=transition_history,
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
