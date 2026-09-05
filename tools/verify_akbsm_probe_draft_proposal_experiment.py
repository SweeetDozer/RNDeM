from __future__ import annotations

import ast
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
import subprocess
import sys
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.akbsm_draft_proposal import (
    AKBSM_PROBE_PROPOSAL_SOURCE,
    AKBSMAssociationProposal,
    AKBSMDraftProposalProvider,
)
from clc.runtime.clc_runtime import CLCRuntime
from clc.runtime.memory_mutation_policy import MemoryMutationPolicy, RuntimeProfile, policy_for_profile


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

SCENARIO_ROOT = ROOT / "scenarios"
EXPECTED_FIXTURES = (
    "akbsm_draft_proposal_enabled_probe_creates_temp_metadata.json",
    "akbsm_draft_proposal_enabled_commit_forbidden.json",
    "akbsm_draft_proposal_enabled_probe_no_memory_mutation.json",
    "akbsm_draft_proposal_enabled_forbidden_sources_no_proposal.json",
    "akbsm_draft_proposal_default_still_disabled_after_enabled_test.json",
)

FORBIDDEN_SOURCES = (
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

FORBIDDEN_WIRING_NAMES = (
    "AKBSMDraftProposalProvider",
    "AKBSMAssociationProposal",
)

ALLOWED_CLC_REFERENCES = {
    Path("clc/runtime/akbsm_draft_proposal.py"),
}

FORBIDDEN_PROPOSAL_METHODS = (
    "commit",
    "apply",
    "save",
    "write",
    "persist",
    "mutate",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_akbsm_draft_proposal_disabled_scenarios.py",
    "tools/verify_akbsm_draft_proposal_scaffold.py",
    "tools/verify_akbsm_first_enabled_draft_proposal_adr.py",
    "tools/verify_akbsm_write_disabled_scenarios.py",
    "tools/verify_memory_mutation_policy.py",
    "tools/verify_phase_regression_snapshots.py",
)


def main() -> int:
    before = _real_hashes()
    results = {
        "default remains disabled": _case_default_disabled(),
        "normal runtime creates no proposals": _case_normal_runtime_no_proposals(),
        "enabled probe creates proposal": _case_enabled_probe_creates_proposal(),
        "commit_allowed true rejected": _case_commit_allowed_true_rejected(),
        "forbidden sources no-op": _case_forbidden_sources_noop(),
        "no forbidden wiring": _case_no_forbidden_wiring(),
        "no proposal commit path": _case_no_proposal_commit_path(),
        "no persistence": _case_no_persistence(),
        "enabled fixtures exist": _case_enabled_fixtures_exist(),
        "enabled fixture metadata valid": _case_enabled_fixture_metadata_valid(),
        "marker 36 absent": _case_marker_36_absent(),
        "existing safety still passes": _run_core_safety_verifiers(),
    }
    after = _real_hashes()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("AKBSM probe draft proposal experiment verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_default_disabled() -> bool:
    policy = policy_for_profile(RuntimeProfile.SAFE_DEMO)
    provider = AKBSMDraftProposalProvider(policy)
    return policy.akbsm_draft_proposals_enabled is False and provider.from_association_evidence(_probe_payload()) == ()


def _case_normal_runtime_no_proposals() -> bool:
    runtime = CLCRuntime(ROOT / "Memory")
    with redirect_stdout(io.StringIO()):
        runtime.feed_audio(1, {440: 0.78, 880: 0.2, 1200: 0.1})
    text = repr([event.payload for event in runtime.memory.events])
    return (
        runtime.memory_mutation_policy.akbsm_draft_proposals_enabled is False
        and not hasattr(runtime, "akbsm_draft_proposal_provider")
        and "akbsm_draft_proposal" not in text.lower()
        and all(event.marker.value != 36 for event in runtime.memory.events)
    )


def _case_enabled_probe_creates_proposal() -> bool:
    provider = AKBSMDraftProposalProvider(_enabled_policy())
    proposals = provider.from_association_evidence(_probe_payload(), source=AKBSM_PROBE_PROPOSAL_SOURCE, tick=7)
    if len(proposals) != 1:
        return False
    proposal = proposals[0]
    return (
        isinstance(proposal, AKBSMAssociationProposal)
        and is_dataclass(proposal)
        and proposal.source == AKBSM_PROBE_PROPOSAL_SOURCE
        and proposal.tick == 7
        and proposal.subject_id == "pat_source"
        and proposal.relation_type == "supports"
        and proposal.object_id == "pat_object"
        and 0.0 <= proposal.confidence <= 1.0
        and proposal.evidence
        and proposal.reason
        and proposal.commit_allowed is False
    )


def _case_commit_allowed_true_rejected() -> bool:
    try:
        AKBSMAssociationProposal(
            source=AKBSM_PROBE_PROPOSAL_SOURCE,
            tick=1,
            subject_id="pat_source",
            relation_type="supports",
            object_id="pat_object",
            confidence=0.5,
            evidence=("probe:akbsm_probe_001",),
            reason="verify rejected commit flag",
            commit_allowed=True,
        )
    except ValueError:
        return True
    return False


def _case_forbidden_sources_noop() -> bool:
    provider = AKBSMDraftProposalProvider(_enabled_policy())
    return all(provider.from_association_evidence(_probe_payload(), source=source, tick=7) == () for source in FORBIDDEN_SOURCES)


def _case_no_forbidden_wiring() -> bool:
    findings: list[str] = []
    for path in (ROOT / "clc").rglob("*.py"):
        relative = path.relative_to(ROOT)
        if relative in ALLOWED_CLC_REFERENCES:
            continue
        text = path.read_text(encoding="utf-8")
        for symbol in FORBIDDEN_WIRING_NAMES:
            if symbol in text:
                findings.append(f"{relative}:{symbol}")
    return not findings


def _case_no_proposal_commit_path() -> bool:
    tree = ast.parse((ROOT / "clc" / "runtime" / "akbsm_draft_proposal.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AKBSMAssociationProposal":
            method_names = [item.name.lower() for item in node.body if isinstance(item, ast.FunctionDef)]
            return not any(name in method_names for name in FORBIDDEN_PROPOSAL_METHODS)
    return False


def _case_no_persistence() -> bool:
    text = (ROOT / "clc" / "runtime" / "akbsm_draft_proposal.py").read_text(encoding="utf-8")
    forbidden_terms = (
        "AKBSMAdapter",
        "ExpSMAdapter",
        "semantic_core.json",
        "technical_feedback_patterns.json",
        "permanent proposal",
    )
    return not any(term in text for term in forbidden_terms)


def _case_enabled_fixtures_exist() -> bool:
    return all((SCENARIO_ROOT / filename).exists() for filename in EXPECTED_FIXTURES)


def _case_enabled_fixture_metadata_valid() -> bool:
    for filename in EXPECTED_FIXTURES:
        path = SCENARIO_ROOT / filename
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        expect = data.get("expect", {})
        experiment = expect.get("akbsm_draft_proposal_experiment", {})
        if not isinstance(experiment, dict):
            return False
        if experiment.get("test_only") is not True:
            return False
        if experiment.get("normal_runtime_disabled") is not True:
            return False
        if experiment.get("akbsm_write_forbidden") is not True:
            return False
        if 36 not in expect.get("forbidden_markers", []):
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


def _enabled_policy() -> MemoryMutationPolicy:
    return MemoryMutationPolicy(
        profile=RuntimeProfile.DRAFT_ONLY,
        allow_draft_writes=True,
        allow_expsm_commit=False,
        allow_expsm_update=False,
        allow_value_feedback_update=False,
        allow_akbsm_write=False,
        akbsm_draft_proposals_enabled=True,
    )


def _probe_payload() -> dict[str, Any]:
    return {
        "probe_id": "akbsm_probe_001",
        "source_target_observation_id": "target_observation_001",
        "source_pattern_id": "pat_source",
        "_event_tick": 6,
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


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
