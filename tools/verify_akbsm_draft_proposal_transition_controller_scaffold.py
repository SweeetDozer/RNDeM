from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.akbsm_draft_proposal import AKBSM_PROBE_PROPOSAL_SOURCE, AKBSMAssociationProposal
from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewController,
    AKBSMProposalReviewRecord,
    AKBSMProposalTransitionResult,
)


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

LIFECYCLE_PATH = ROOT / "clc" / "runtime" / "akbsm_proposal_lifecycle.py"
ALLOWED_TRANSITIONS = (
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
FORBIDDEN_TRANSITIONS = (
    ("created", "accepted_for_observation"),
    ("created", "deferred"),
    ("created", "rejected"),
    ("created", "expired"),
    ("expired", "review_pending"),
    ("expired", "accepted_for_observation"),
    ("expired", "deferred"),
    ("expired", "rejected"),
    ("expired", "created"),
    ("rejected", "accepted_for_observation"),
    ("rejected", "review_pending"),
    ("accepted_for_observation", "review_pending"),
    ("accepted_for_observation", "deferred"),
    ("accepted_for_observation", "rejected"),
)
FORBIDDEN_TARGET_STATES = (
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
FORBIDDEN_CALL_NAMES = (
    "open",
    "mkdir",
    "replace",
    "unlink",
    "dump",
    "dumps",
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
CORE_SAFETY_VERIFIERS = (
    "tools/verify_akbsm_draft_proposal_transition_controller_adr.py",
    "tools/verify_akbsm_draft_proposal_lifecycle_state_scaffold.py",
    "tools/verify_akbsm_draft_proposal_lifecycle_implementation_plan.py",
    "tools/verify_akbsm_draft_proposal_review_lifecycle_adr.py",
    "tools/verify_akbsm_probe_draft_proposal_experiment.py",
    "tools/verify_akbsm_draft_proposal_disabled_scenarios.py",
    "tools/verify_akbsm_draft_proposal_scaffold.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    before = _real_hashes()
    results = {
        "controller exists": _case_controller_exists(),
        "test scenario authority required": _case_authority_required(),
        "allowed transitions accepted": _case_allowed_transitions(),
        "forbidden transitions rejected": _case_forbidden_transitions(),
        "write-like targets rejected": _case_forbidden_target_states(),
        "expiration metadata only": _case_expiration_metadata_only(),
        "allowed request returns immutable copy": _case_allowed_copy_behavior(),
        "transition result metadata only": _case_transition_result_metadata_only(),
        "no forbidden transition methods": _case_no_forbidden_transition_methods(),
        "no proposal storage": _case_no_storage_calls(),
        "no normal runtime wiring": _case_no_normal_runtime_wiring(),
        "marker 36 absent": _case_marker_36_absent(),
        "existing safety still passes": _run_core_safety_verifiers(),
    }
    after = _real_hashes()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("AKBSM draft proposal transition controller scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_controller_exists() -> bool:
    controller = AKBSMProposalReviewController()
    return (
        AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY == "explicit_test_scenario_harness"
        and controller.is_transition_allowed("created", "review_pending")
        and not controller.is_transition_allowed("created", "expired")
    )


def _case_authority_required() -> bool:
    controller = AKBSMProposalReviewController()
    record = _record("created")
    accepted_result, accepted_record = controller.request_transition(
        record,
        "review_pending",
        authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
        tick=2,
    )
    rejected_result, rejected_record = controller.request_transition(
        record,
        "review_pending",
        authority="PolicyPressureReview",
        tick=2,
    )
    blank_result, blank_record = controller.request_transition(
        record,
        "review_pending",
        authority="",
        tick=2,
    )
    return (
        accepted_result.allowed is True
        and accepted_record is not None
        and rejected_result.allowed is False
        and rejected_result.reason == "unauthorized_transition"
        and rejected_record is None
        and blank_result.allowed is False
        and blank_record is None
    )


def _case_allowed_transitions() -> bool:
    controller = AKBSMProposalReviewController()
    for source, target in ALLOWED_TRANSITIONS:
        record = _record(source)
        result, next_record = controller.request_transition(
            record,
            target,
            authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
            tick=3,
            reason="scenario review",
            notes="temporary metadata",
        )
        if not (
            result.allowed is True
            and result.from_state == AKBSMProposalLifecycleState(source)
            and result.to_state == AKBSMProposalLifecycleState(target)
            and isinstance(next_record, AKBSMProposalReviewRecord)
            and next_record is not record
            and next_record.state == AKBSMProposalLifecycleState(target)
            and next_record.proposal is record.proposal
            and next_record.updated_tick == 3
            and record.state == AKBSMProposalLifecycleState(source)
        ):
            return False
    return True


def _case_forbidden_transitions() -> bool:
    controller = AKBSMProposalReviewController()
    for source, target in FORBIDDEN_TRANSITIONS:
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


def _case_forbidden_target_states() -> bool:
    controller = AKBSMProposalReviewController()
    record = _record("review_pending")
    for target in FORBIDDEN_TARGET_STATES:
        result, next_record = controller.request_transition(
            record,
            target,
            authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
            tick=5,
        )
        if result.allowed or next_record is not None:
            return False
    return True


def _case_expiration_metadata_only() -> bool:
    controller = AKBSMProposalReviewController()
    record = _record("accepted_for_observation", ttl_ticks=8)
    result, next_record = controller.request_expiration(
        record,
        authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
        tick=9,
        reason="ttl elapsed",
    )
    return (
        result.allowed is True
        and result.to_state == AKBSMProposalLifecycleState.EXPIRED
        and isinstance(next_record, AKBSMProposalReviewRecord)
        and next_record.state == AKBSMProposalLifecycleState.EXPIRED
        and next_record.ttl_ticks == 8
        and record.state == AKBSMProposalLifecycleState.ACCEPTED_FOR_OBSERVATION
        and next_record.proposal.commit_allowed is False
    )


def _case_allowed_copy_behavior() -> bool:
    controller = AKBSMProposalReviewController()
    record = _record("created", transition_history=("seed",))
    result, next_record = controller.request_transition(
        record,
        "review_pending",
        authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
        tick=2,
    )
    if not result.allowed or next_record is None:
        return False
    immutable = _frozen_rejects(next_record, "review_notes", "changed")
    return (
        next_record is not record
        and next_record.proposal is record.proposal
        and record.transition_history == ("seed",)
        and next_record.transition_history == ("seed", "created->review_pending@2")
        and immutable
    )


def _case_transition_result_metadata_only() -> bool:
    controller = AKBSMProposalReviewController()
    record = _record("created")
    result, next_record = controller.request_transition(
        record,
        "review_pending",
        authority=AKBSM_PROPOSAL_REVIEW_TEST_SCENARIO_AUTHORITY,
        tick=2,
    )
    immutable = _frozen_rejects(result, "allowed", False)
    return (
        isinstance(result, AKBSMProposalTransitionResult)
        and result.proposal is record.proposal
        and result.allowed is True
        and next_record is not None
        and result.proposal.commit_allowed is False
        and immutable
    )


def _case_no_forbidden_transition_methods() -> bool:
    tree = ast.parse(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.lower() in FORBIDDEN_METHOD_NAMES:
                return False
    return True


def _case_no_storage_calls() -> bool:
    tree = ast.parse(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if (
                call_name in FORBIDDEN_CALL_NAMES
                or call_name.endswith(".open")
                or call_name.endswith(".write")
                or call_name.endswith(".save")
                or call_name.endswith(".dump")
            ):
                return False
    return True


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


def _case_marker_36_absent() -> bool:
    forbidden_marker_name = "MARKER" + "_36"
    forbidden_marker_attr = "OperationMarker." + "36"
    forbidden_marker_ctor = "OperationMarker(" + "36"
    for path in (ROOT / "clc").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if forbidden_marker_name in text or forbidden_marker_attr in text or forbidden_marker_ctor in text:
            return False
    return True


def _frozen_rejects(instance: object, field_name: str, value: object) -> bool:
    try:
        setattr(instance, field_name, value)
    except FrozenInstanceError:
        return True
    return False


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


def _run_core_safety_verifiers() -> bool:
    if os.environ.get("RNDEM_VERIFIER_SHALLOW") == "1":
        return True
    env = dict(os.environ)
    env["RNDEM_VERIFIER_SHALLOW"] = "1"
    for relative_path in CORE_SAFETY_VERIFIERS:
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=ROOT,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            return False
    return True


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
