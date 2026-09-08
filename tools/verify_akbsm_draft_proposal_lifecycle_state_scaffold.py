from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.akbsm_draft_proposal import AKBSM_PROBE_PROPOSAL_SOURCE, AKBSMAssociationProposal
from clc.runtime.akbsm_proposal_lifecycle import (
    AKBSM_PROPOSAL_ALLOWED_TRANSITIONS,
    AKBSM_PROPOSAL_FORBIDDEN_WRITE_LIKE_STATE_NAMES,
    AKBSMProposalLifecycleState,
    AKBSMProposalReviewRecord,
    AKBSMProposalTransitionResult,
)


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

LIFECYCLE_PATH = ROOT / "clc" / "runtime" / "akbsm_proposal_lifecycle.py"
EXPECTED_STATES = (
    "created",
    "review_pending",
    "accepted_for_observation",
    "deferred",
    "rejected",
    "expired",
)
FORBIDDEN_WRITE_LIKE_STATES = (
    "committed",
    "applied",
    "persisted",
    "written",
    "saved",
    "accepted_for_write",
    "ready_to_write",
    "approved_for_akbsm",
)
EXPECTED_TRANSITIONS = {
    ("created", "review_pending"),
    ("review_pending", "accepted_for_observation"),
    ("review_pending", "deferred"),
    ("review_pending", "rejected"),
    ("review_pending", "expired"),
    ("accepted_for_observation", "expired"),
    ("deferred", "review_pending"),
    ("deferred", "expired"),
    ("rejected", "expired"),
}
FORBIDDEN_RUNTIME_NAMES = (
    "AKBSMProposalReviewService",
    "execute_transition",
    "apply_transition",
    "commit_transition",
    "persist_transition",
    "save_transition",
    "write_transition",
)
FORBIDDEN_METHOD_NAMES = (
    "commit",
    "apply",
    "save",
    "write",
    "persist",
    "mutate",
)
FORBIDDEN_CALL_NAMES = (
    "open",
    "mkdir",
    "replace",
    "unlink",
)
FORBIDDEN_WIRING_SYMBOLS = (
    "AKBSMProposalLifecycleState",
    "AKBSMProposalReviewRecord",
    "AKBSMProposalTransitionResult",
)
FORBIDDEN_WIRING_TARGETS = (
    ROOT / "clc" / "runtime" / "clc_runtime.py",
    ROOT / "clc" / "runtime" / "mode_c_advisory.py",
    ROOT / "clc" / "consolidation",
    ROOT / "clc" / "action",
    ROOT / "clc" / "evaluation",
)
CORE_SAFETY_VERIFIERS = (
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
        "module/classes exist": _case_module_classes_exist(),
        "allowed states only": _case_allowed_states_only(),
        "forbidden write-like states invalid": _case_forbidden_states_invalid(),
        "allowed transitions metadata exact": _case_allowed_transitions_exact(),
        "no transition execution": _case_no_transition_execution(),
        "metadata-only review record": _case_review_record_metadata_only(),
        "metadata-only transition result": _case_transition_result_metadata_only(),
        "no forbidden wiring": _case_no_forbidden_wiring(),
        "no persistence or memory mutation": _case_no_persistence_or_memory_mutation(),
        "marker 36 absent": _case_marker_36_absent(),
        "existing safety still passes": _run_core_safety_verifiers(),
    }
    after = _real_hashes()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("AKBSM draft proposal lifecycle state scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_module_classes_exist() -> bool:
    return (
        LIFECYCLE_PATH.exists()
        and isinstance(AKBSMProposalLifecycleState.CREATED, AKBSMProposalLifecycleState)
        and is_dataclass(AKBSMProposalReviewRecord)
        and is_dataclass(AKBSMProposalTransitionResult)
    )


def _case_allowed_states_only() -> bool:
    return tuple(state.value for state in AKBSMProposalLifecycleState) == EXPECTED_STATES


def _case_forbidden_states_invalid() -> bool:
    valid = {state.value for state in AKBSMProposalLifecycleState}
    try:
        invalid_rejected = all(_state_rejected(value) for value in FORBIDDEN_WRITE_LIKE_STATES)
    except ValueError:
        invalid_rejected = False
    return (
        not valid.intersection(FORBIDDEN_WRITE_LIKE_STATES)
        and set(AKBSM_PROPOSAL_FORBIDDEN_WRITE_LIKE_STATE_NAMES) == set(FORBIDDEN_WRITE_LIKE_STATES)
        and invalid_rejected
    )


def _case_allowed_transitions_exact() -> bool:
    if not isinstance(AKBSM_PROPOSAL_ALLOWED_TRANSITIONS, MappingProxyType):
        return False
    observed = {
        (from_state.value, to_state.value)
        for from_state, to_states in AKBSM_PROPOSAL_ALLOWED_TRANSITIONS.items()
        for to_state in to_states
    }
    keys = tuple(state.value for state in AKBSM_PROPOSAL_ALLOWED_TRANSITIONS.keys())
    return observed == EXPECTED_TRANSITIONS and keys == EXPECTED_STATES


def _case_no_transition_execution() -> bool:
    text = LIFECYCLE_PATH.read_text(encoding="utf-8")
    return not any(name in text for name in FORBIDDEN_RUNTIME_NAMES)


def _case_review_record_metadata_only() -> bool:
    proposal = _sample_proposal()
    record = AKBSMProposalReviewRecord(
        proposal=proposal,
        state="accepted_for_observation",
        created_tick=1,
        updated_tick=2,
        ttl_ticks=5,
        review_reason="observed_only",
        review_notes="temporary metadata",
        transition_history=["created -> review_pending"],
    )
    field_names = tuple(field.name for field in fields(AKBSMProposalReviewRecord))
    immutable = _frozen_rejects(record, "review_notes", "changed")
    invalid_tick_rejected = _record_rejects(created_tick=3, updated_tick=2)
    invalid_state_rejected = _record_rejects(state="committed")
    return (
        getattr(AKBSMProposalReviewRecord, "__dataclass_params__").frozen is True
        and field_names == (
            "proposal",
            "state",
            "created_tick",
            "updated_tick",
            "ttl_ticks",
            "review_reason",
            "review_notes",
            "transition_history",
        )
        and record.proposal is proposal
        and record.state == AKBSMProposalLifecycleState.ACCEPTED_FOR_OBSERVATION
        and record.transition_history == ("created -> review_pending",)
        and record.proposal.commit_allowed is False
        and immutable
        and invalid_tick_rejected
        and invalid_state_rejected
        and not _class_has_forbidden_methods(AKBSMProposalReviewRecord)
    )


def _case_transition_result_metadata_only() -> bool:
    proposal = _sample_proposal()
    result = AKBSMProposalTransitionResult(
        proposal=proposal,
        from_state="created",
        to_state="review_pending",
        allowed=True,
        reason="metadata report",
        tick=3,
    )
    field_names = tuple(field.name for field in fields(AKBSMProposalTransitionResult))
    immutable = _frozen_rejects(result, "reason", "changed")
    invalid_state_rejected = _transition_rejects(to_state="persisted")
    invalid_tick_rejected = _transition_rejects(tick=-1)
    return (
        getattr(AKBSMProposalTransitionResult, "__dataclass_params__").frozen is True
        and field_names == ("proposal", "from_state", "to_state", "allowed", "reason", "tick")
        and result.proposal is proposal
        and result.from_state == AKBSMProposalLifecycleState.CREATED
        and result.to_state == AKBSMProposalLifecycleState.REVIEW_PENDING
        and result.allowed is True
        and result.proposal.commit_allowed is False
        and immutable
        and invalid_state_rejected
        and invalid_tick_rejected
        and not _class_has_forbidden_methods(AKBSMProposalTransitionResult)
    )


def _case_no_forbidden_wiring() -> bool:
    for target in FORBIDDEN_WIRING_TARGETS:
        paths = target.rglob("*.py") if target.is_dir() else (target,)
        for path in paths:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            if any(symbol in text for symbol in FORBIDDEN_WIRING_SYMBOLS):
                return False
    return True


def _case_no_persistence_or_memory_mutation() -> bool:
    tree = ast.parse(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if (
                call_name in FORBIDDEN_CALL_NAMES
                or call_name.endswith(".open")
                or call_name.endswith(".write")
                or call_name.endswith(".save")
            ):
                return False
    text = LIFECYCLE_PATH.read_text(encoding="utf-8")
    forbidden_terms = (
        "AKBSMAdapter",
        "ExpSMAdapter",
        "Memory/AKBSM",
        "Memory/ExpSM",
        "semantic_core.json",
        "technical_feedback_patterns.json",
        "permanent proposal",
        "permanent association",
    )
    return not any(term in text for term in forbidden_terms)


def _case_marker_36_absent() -> bool:
    forbidden_marker_name = "MARKER" + "_36"
    forbidden_marker_attr = "OperationMarker." + "36"
    forbidden_marker_ctor = "OperationMarker(" + "36"
    for path in (ROOT / "clc").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if forbidden_marker_name in text or forbidden_marker_attr in text or forbidden_marker_ctor in text:
            return False
    return True


def _state_rejected(value: str) -> bool:
    try:
        AKBSMProposalLifecycleState(value)
    except ValueError:
        return True
    return False


def _record_rejects(**overrides: object) -> bool:
    kwargs = {
        "proposal": _sample_proposal(),
        "state": "created",
        "created_tick": 1,
        "updated_tick": 1,
    }
    kwargs.update(overrides)
    try:
        AKBSMProposalReviewRecord(**kwargs)
    except (TypeError, ValueError):
        return True
    return False


def _transition_rejects(**overrides: object) -> bool:
    kwargs = {
        "proposal": _sample_proposal(),
        "from_state": "created",
        "to_state": "review_pending",
        "allowed": False,
        "reason": "metadata report",
        "tick": 1,
    }
    kwargs.update(overrides)
    try:
        AKBSMProposalTransitionResult(**kwargs)
    except (TypeError, ValueError):
        return True
    return False


def _frozen_rejects(instance: object, field_name: str, value: object) -> bool:
    try:
        setattr(instance, field_name, value)
    except FrozenInstanceError:
        return True
    return False


def _class_has_forbidden_methods(class_object: type[object]) -> bool:
    tree = ast.parse(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_object.__name__:
            method_names = {
                item.name.lower()
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            return bool(method_names.intersection(FORBIDDEN_METHOD_NAMES))
    return True


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


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
