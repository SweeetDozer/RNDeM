from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.akbsm_draft_proposal import (
    AKBSM_PROBE_PROPOSAL_SOURCE,
    AKBSMAssociationProposal,
    AKBSMDraftProposalProvider,
)
from clc.runtime.memory_mutation_policy import MemoryMutationPolicy, RuntimeProfile, policy_for_profile


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

SCAFFOLD_PATHS = (
    ROOT / "clc" / "runtime" / "akbsm_draft_proposal.py",
    ROOT / "clc" / "runtime" / "memory_mutation_policy.py",
)

FORBIDDEN_INTEGRATION_NAMES = (
    "DecisionSelector",
    "ActionScoring",
    "ActionProposer",
    "ModeActionGuard",
    "PolicyPressureReview",
    "ModeCMemoryGateAdvisoryProvider",
    "MemoryWriteReviewModule",
    "ExpSMUpdateWriter",
    "ValueFeedbackUpdateWriter",
    "AKBSMAdapter",
)

FORBIDDEN_CALL_NAMES = (
    "write",
    "save",
    "commit",
    "open",
    "replace",
    "unlink",
    "mkdir",
)


def main() -> int:
    before = _real_hashes()
    results = {
        "default_policy_disabled": _case_default_policy_disabled(),
        "policy_summary_has_flag": _case_policy_summary_has_flag(),
        "payload_is_frozen": _case_payload_is_frozen(),
        "payload_shape": _case_payload_shape(),
        "payload_validation": _case_payload_validation(),
        "provider_noop_by_default": _case_provider_noop_by_default(),
        "provider_noop_when_disabled": _case_provider_noop_when_disabled(),
        "provider_noop_without_probe_evidence": _case_provider_noop_without_probe_evidence(),
        "provider_enabled_probe_metadata_only": _case_provider_enabled_probe_metadata_only(),
        "provider_forbidden_sources_noop": _case_provider_forbidden_sources_noop(),
        "no_forbidden_integrations": _case_no_forbidden_integrations(),
        "no_file_or_writer_calls": _case_no_file_or_writer_calls(),
        "akbsm_write_policy_still_passes": _run_verifier("tools/verify_akbsm_write_policy_adr.py"),
        "akbsm_write_disabled_scenarios_still_pass": _run_verifier(
            "tools/verify_akbsm_write_disabled_scenarios.py"
        ),
        "akbsm_draft_proposal_design_still_passes": _run_verifier(
            "tools/verify_akbsm_draft_proposal_design.py"
        ),
        "memory_mutation_policy_still_passes": _run_verifier("tools/verify_memory_mutation_policy.py"),
        "phase_regression_snapshots_still_pass": _run_verifier("tools/verify_phase_regression_snapshots.py"),
        "marker_36_absent": _case_marker_36_absent(),
    }
    after = _real_hashes()
    results["real_expsm_hash_unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real_akbsm_hash_unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("AKBSM draft proposal scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_default_policy_disabled() -> bool:
    policies = (
        policy_for_profile(RuntimeProfile.SAFE_DEMO),
        policy_for_profile(RuntimeProfile.DRAFT_ONLY),
        policy_for_profile(RuntimeProfile.MUTATING_MEMORY),
    )
    return all(policy.akbsm_draft_proposals_enabled is False and policy.allow_akbsm_write is False for policy in policies)


def _case_policy_summary_has_flag() -> bool:
    summary = policy_for_profile(RuntimeProfile.SAFE_DEMO).summary()
    return (
        summary.get("akbsm_draft_proposals_enabled") is False
        and summary.get("allow_akbsm_write") is False
    )


def _case_payload_is_frozen() -> bool:
    proposal = _sample_proposal()
    try:
        proposal.reason = "changed"
    except FrozenInstanceError:
        return True
    return False


def _case_payload_shape() -> bool:
    field_map = {field.name: field for field in fields(AKBSMAssociationProposal)}
    commit_field = field_map.get("commit_allowed")
    return (
        is_dataclass(AKBSMAssociationProposal)
        and getattr(AKBSMAssociationProposal, "__dataclass_params__").frozen is True
        and tuple(field_map) == (
            "source",
            "tick",
            "subject_id",
            "relation_type",
            "object_id",
            "confidence",
            "evidence",
            "reason",
            "commit_allowed",
        )
        and commit_field is not None
        and commit_field.default is False
        and _sample_proposal().evidence == ("probe:1",)
    )


def _case_payload_validation() -> bool:
    confidence_rejected = False
    commit_rejected = False
    empty_metadata_rejected = False
    empty_evidence_rejected = False
    evidence_tupled = AKBSMAssociationProposal(
        source="verify",
        tick=1,
        subject_id="pat_a",
        relation_type="supports",
        object_id="pat_b",
        confidence=0.4,
        evidence=["probe:1"],
        reason="metadata only",
    ).evidence == ("probe:1",)
    try:
        AKBSMAssociationProposal("verify", 1, "pat_a", "supports", "pat_b", 1.1, (), "bad")
    except ValueError:
        confidence_rejected = True
    try:
        AKBSMAssociationProposal("verify", 1, "pat_a", "supports", "pat_b", 0.5, (), "bad", True)
    except ValueError:
        commit_rejected = True
    try:
        AKBSMAssociationProposal("verify", 1, "", "supports", "pat_b", 0.5, ("probe:1",), "bad")
    except ValueError:
        empty_metadata_rejected = True
    try:
        AKBSMAssociationProposal("verify", 1, "pat_a", "supports", "pat_b", 0.5, (), "bad")
    except ValueError:
        empty_evidence_rejected = True
    return confidence_rejected and commit_rejected and empty_metadata_rejected and empty_evidence_rejected and evidence_tupled


def _case_provider_noop_by_default() -> bool:
    provider = AKBSMDraftProposalProvider(policy_for_profile(RuntimeProfile.DRAFT_ONLY))
    return provider.from_association_evidence(object()) == ()


def _case_provider_noop_when_disabled() -> bool:
    provider = AKBSMDraftProposalProvider(policy_for_profile(RuntimeProfile.DRAFT_ONLY))
    return provider.from_association_evidence(_probe_payload(), source=AKBSM_PROBE_PROPOSAL_SOURCE, tick=7) == ()


def _case_provider_noop_without_probe_evidence() -> bool:
    policy = MemoryMutationPolicy(
        profile=RuntimeProfile.DRAFT_ONLY,
        allow_draft_writes=True,
        allow_expsm_commit=False,
        allow_expsm_update=False,
        allow_value_feedback_update=False,
        allow_akbsm_write=False,
        akbsm_draft_proposals_enabled=True,
    )
    provider = AKBSMDraftProposalProvider(policy)
    return provider.from_association_evidence(object()) == ()


def _case_provider_enabled_probe_metadata_only() -> bool:
    policy = MemoryMutationPolicy(
        profile=RuntimeProfile.DRAFT_ONLY,
        allow_draft_writes=True,
        allow_expsm_commit=False,
        allow_expsm_update=False,
        allow_value_feedback_update=False,
        allow_akbsm_write=False,
        akbsm_draft_proposals_enabled=True,
    )
    provider = AKBSMDraftProposalProvider(policy)
    proposals = provider.from_association_evidence(_probe_payload(), source=AKBSM_PROBE_PROPOSAL_SOURCE, tick=7)
    return (
        len(proposals) == 1
        and proposals[0].source == AKBSM_PROBE_PROPOSAL_SOURCE
        and proposals[0].tick == 7
        and proposals[0].subject_id == "pat_source"
        and proposals[0].relation_type == "supports"
        and proposals[0].object_id == "pat_object"
        and proposals[0].confidence == 0.72
        and proposals[0].evidence
        and proposals[0].commit_allowed is False
    )


def _case_provider_forbidden_sources_noop() -> bool:
    policy = MemoryMutationPolicy(
        profile=RuntimeProfile.DRAFT_ONLY,
        allow_draft_writes=True,
        allow_expsm_commit=False,
        allow_expsm_update=False,
        allow_value_feedback_update=False,
        allow_akbsm_write=False,
        akbsm_draft_proposals_enabled=True,
    )
    provider = AKBSMDraftProposalProvider(policy)
    forbidden_sources = (
        "AKBSMAssociationField",
        "PolicyPressureReview",
        "Mode C",
        "DecisionSelector",
        "ActionScoring",
        "ActionProposer",
        "ModeActionGuard",
        "ValueFeedback",
        "ExpSM",
        "memory writers",
    )
    return all(provider.from_association_evidence(_probe_payload(), source=source, tick=7) == () for source in forbidden_sources)


def _case_no_forbidden_integrations() -> bool:
    scaffold_text = (ROOT / "clc" / "runtime" / "akbsm_draft_proposal.py").read_text(encoding="utf-8")
    return not any(name in scaffold_text for name in FORBIDDEN_INTEGRATION_NAMES)


def _case_no_file_or_writer_calls() -> bool:
    for path in SCAFFOLD_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name in FORBIDDEN_CALL_NAMES or name.endswith(".write") or name.endswith(".save"):
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


def _run_verifier(relative_path: str) -> bool:
    if os.environ.get("RNDEM_VERIFIER_SHALLOW") == "1":
        return True
    env = dict(os.environ)
    env["RNDEM_VERIFIER_SHALLOW"] = "1"
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
        source="verify",
        tick=1,
        subject_id="pat_a",
        relation_type="supports",
        object_id="pat_b",
        confidence=0.5,
        evidence=("probe:1",),
        reason="metadata only",
    )


def _probe_payload() -> dict[str, object]:
    return {
        "probe_id": "akbsm_probe_001",
        "source_target_observation_id": "target_observation_001",
        "source_pattern_id": "pat_source",
        "activation": 0.61,
        "associated_patterns": [
            {
                "pattern_id": "pat_object",
                "relation_type": "supports",
                "score": 0.72,
                "path": ["pat_source", "pat_object"],
            }
        ],
        "memory_modified": False,
        "permanent_memory_modified": False,
        "akbsm_modified": False,
    }


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
