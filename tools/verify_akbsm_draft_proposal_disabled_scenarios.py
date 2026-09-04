from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.pattern_registry import PatternRegistry
from clc.runtime.akbsm_draft_proposal import AKBSMDraftProposalProvider
from clc.runtime.memory_mutation_policy import MemoryMutationPolicy, RuntimeProfile, policy_for_profile
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


SCENARIO_ROOT = ROOT / "scenarios"
EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

EXPECTED_FIXTURES = (
    "akbsm_draft_proposal_disabled_no_effect.json",
    "akbsm_draft_proposal_safe_demo_no_proposal.json",
    "akbsm_draft_proposal_draft_only_no_proposal.json",
    "akbsm_draft_proposal_mutating_memory_no_proposal.json",
    "akbsm_draft_proposal_repeated_signal_no_proposal.json",
    "akbsm_draft_proposal_pressure_review_no_proposal.json",
)

ALLOWED_CLC_REFERENCES = {
    Path("clc/runtime/akbsm_draft_proposal.py"),
    Path("clc/runtime/memory_mutation_policy.py"),
}

FORBIDDEN_WIRING_NAMES = (
    "AKBSMDraftProposalProvider",
    "AKBSMAssociationProposal",
)


def main() -> int:
    before = _real_hashes()
    scenario_results = _run_fixtures()
    results = {
        "fixtures exist": _fixtures_exist(),
        "scenario runner passes": all(scenario_results.values()),
        "scaffold verifier passes": _run_verifier("tools/verify_akbsm_draft_proposal_scaffold.py"),
        "provider no-op by default": _provider_noop_by_default(),
        "provider no-op when enabled": _provider_noop_when_enabled(),
        "provider does not write ContextMemory": _provider_does_not_write_context_memory(),
        "no forbidden wiring": _no_forbidden_wiring(),
        "AKBSM writes blocked by policy": _akbsm_writes_blocked_by_policy(),
        "marker 36 absent": _marker_36_absent(),
    }
    after = _real_hashes()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("AKBSM draft proposal disabled scenario verification:")
    for fixture, ok in scenario_results.items():
        print(f"  fixture {fixture}: {'PASS' if ok else 'FAIL'}")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _fixtures_exist() -> bool:
    return all((SCENARIO_ROOT / filename).exists() for filename in EXPECTED_FIXTURES)


def _run_fixtures() -> dict[str, bool]:
    results: dict[str, bool] = {}
    for filename in EXPECTED_FIXTURES:
        path = SCENARIO_ROOT / filename
        if not path.exists():
            results[filename] = False
            continue
        fixture = load_scenario(path)
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
        proposal_absent = _proposal_markers_absent(result.marker_counts) and _proposal_summary_absent(result.regression_summary)
        pressure_review_ok = True
        if fixture.name == "akbsm_draft_proposal_pressure_review_no_proposal":
            pressure_review_ok = result.policy_pressure_review is not None
        probe_ok = True
        if fixture.name in {
            "akbsm_draft_proposal_safe_demo_no_proposal",
            "akbsm_draft_proposal_repeated_signal_no_proposal",
        }:
            probe_ok = 27 in result.marker_counts
        results[filename] = result.passed and result.memory_unchanged and proposal_absent and pressure_review_ok and probe_ok
    return results


def _provider_noop_by_default() -> bool:
    provider = AKBSMDraftProposalProvider(policy_for_profile(RuntimeProfile.SAFE_DEMO))
    return provider.from_association_evidence(object()) == ()


def _provider_noop_when_enabled() -> bool:
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


def _provider_does_not_write_context_memory() -> bool:
    id_gen = IdGenerator()
    registry = PatternRegistry(ROOT / "Memory" / "pattern_manifest.json")
    memory = ContextMemory(id_gen, registry)
    before_events = len(memory.events)
    before_modules = len(memory.module_updates)
    before_hashes = _real_hashes()
    provider = AKBSMDraftProposalProvider(policy_for_profile(RuntimeProfile.SAFE_DEMO))
    proposals = provider.from_association_evidence(memory)
    after_hashes = _real_hashes()
    return (
        proposals == ()
        and len(memory.events) == before_events
        and len(memory.module_updates) == before_modules
        and before_hashes == after_hashes
    )


def _no_forbidden_wiring() -> bool:
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


def _akbsm_writes_blocked_by_policy() -> bool:
    profiles = (
        RuntimeProfile.SAFE_DEMO,
        RuntimeProfile.DRAFT_ONLY,
        RuntimeProfile.MUTATING_MEMORY,
    )
    return all(
        policy_for_profile(profile).allow_akbsm_write is False
        and policy_for_profile(profile).akbsm_draft_proposals_enabled is False
        for profile in profiles
    )


def _marker_36_absent() -> bool:
    forbidden_marker_name = "MARKER" + "_36"
    forbidden_marker_attr = "OperationMarker." + "36"
    forbidden_marker_ctor = "OperationMarker(" + "36"
    for path in (ROOT / "clc").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if forbidden_marker_name in text or forbidden_marker_attr in text or forbidden_marker_ctor in text:
            return False
    return True


def _proposal_markers_absent(marker_counts: dict[int, int]) -> bool:
    return 36 not in marker_counts


def _proposal_summary_absent(value: object, *, parent_key: str | None = None) -> bool:
    if parent_key == "scenario":
        return True
    if isinstance(value, dict):
        for key, item in value.items():
            if "akbsm_draft_proposal" in str(key).lower():
                return False
            if not _proposal_summary_absent(item, parent_key=str(key)):
                return False
    elif isinstance(value, (list, tuple)):
        return all(_proposal_summary_absent(item, parent_key=parent_key) for item in value)
    elif isinstance(value, str):
        return "akbsm_draft_proposal" not in value.lower()
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


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
