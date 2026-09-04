from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_akbsm_first_enabled_draft_proposal_experiment.md"
DOC_REFERENCE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "design_akbsm_draft_association_proposal.md",
    ROOT / "docs" / "adr_akbsm_write_policy.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md",
)

DECISION_TERMS = (
    "AKBSMAssociationProbe",
    "only proposal source",
    "AKBSMAssociationField is deferred",
)

FORBIDDEN_SOURCE_TERMS = (
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

NO_WRITE_TERMS = (
    "commit_allowed=False",
    "commit_allowed=True rejected",
    "cannot write AKBSM",
    "cannot write ExpSM",
    "cannot create relation types",
    "cannot create concepts",
    "cannot persist proposals",
)

TEMPORARY_STORAGE_TERMS = (
    "temporary ContextMemory metadata",
    "scenario/debug output",
    "Memory/AKBSM",
    "Memory/ExpSM",
    "semantic_core.json",
    "technical_feedback_patterns.json",
)

FUTURE_SCENARIO_TERMS = (
    "enabled probe creates temporary draft proposal metadata",
    "normal default runtime still creates no proposals",
    "disabled fixtures still pass",
    "PolicyPressureReview cannot create proposal",
)

FUTURE_VERIFIER_TERMS = (
    "verify enabled experiment flag is explicit",
    "verify default remains disabled",
    "verify proposal source is `AKBSMAssociationProbe` only",
    "verify forbidden sources are not referenced by implementation",
    "verify proposal payload is metadata-only",
    "verify commit_allowed=False",
    "verify commit_allowed=True rejected",
    "verify no AKBSM mutation",
    "verify no ExpSM mutation",
    "verify no permanent proposal persistence",
    "verify no behavior/scoring/guard/Mode C integration",
    "verify marker 36 absent",
    "verify memory hashes unchanged",
)

DOC_REFERENCE_TERMS = (
    "adr_akbsm_first_enabled_draft_proposal_experiment.md",
    "AKBSMAssociationProbe",
    "AKBSMAssociationField is deferred",
    "AKBSM writes remain blocked",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_akbsm_draft_proposal_disabled_scenarios.py",
    "tools/verify_akbsm_draft_proposal_scaffold.py",
    "tools/verify_akbsm_write_disabled_scenarios.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    adr_text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    doc_text = "\n".join(
        path.read_text(encoding="utf-8") for path in DOC_REFERENCE_PATHS if path.exists()
    )
    missing_decision = _missing_terms(adr_text, DECISION_TERMS)
    missing_forbidden = _missing_terms(adr_text, FORBIDDEN_SOURCE_TERMS)
    missing_no_write = _missing_terms(adr_text, NO_WRITE_TERMS)
    missing_storage = _missing_terms(adr_text, TEMPORARY_STORAGE_TERMS)
    missing_scenarios = _missing_terms(adr_text, FUTURE_SCENARIO_TERMS)
    missing_verifiers = _missing_terms(adr_text, FUTURE_VERIFIER_TERMS)
    missing_refs = _missing_terms(doc_text, DOC_REFERENCE_TERMS)
    safety_passed = _run_core_safety_verifiers()

    checks = {
        "ADR exists": ADR_PATH.exists(),
        "decision documented": not missing_decision,
        "forbidden sources documented": not missing_forbidden,
        "no-write semantics documented": not missing_no_write,
        "temporary storage documented": not missing_storage,
        "future scenarios documented": not missing_scenarios,
        "future verifiers documented": not missing_verifiers,
        "doc references present": not missing_refs,
        "existing safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("AKBSM first enabled draft proposal ADR verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_decision:
        print(f"  missing decision terms: {', '.join(missing_decision)}")
    if missing_forbidden:
        print(f"  missing forbidden source terms: {', '.join(missing_forbidden)}")
    if missing_no_write:
        print(f"  missing no-write terms: {', '.join(missing_no_write)}")
    if missing_storage:
        print(f"  missing storage terms: {', '.join(missing_storage)}")
    if missing_scenarios:
        print(f"  missing future scenario terms: {', '.join(missing_scenarios)}")
    if missing_verifiers:
        print(f"  missing future verifier terms: {', '.join(missing_verifiers)}")
    if missing_refs:
        print(f"  missing doc reference terms: {', '.join(missing_refs)}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _missing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = text.lower()
    return [term for term in terms if term.lower() not in normalized]


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


if __name__ == "__main__":
    raise SystemExit(main())
