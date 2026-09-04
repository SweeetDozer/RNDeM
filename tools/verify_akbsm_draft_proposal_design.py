from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "design_akbsm_draft_association_proposal.md"

STATUS_TERMS = (
    "design accepted",
    "disabled scaffold implemented",
    "AKBSM writes not implemented",
    "AKBSM writes remain blocked",
)

PROPOSAL_SHAPE_TERMS = (
    "AKBSMAssociationProposal",
    "source",
    "tick",
    "subject_id",
    "relation_type",
    "object_id",
    "confidence",
    "evidence",
    "reason",
    "commit_allowed",
    "False",
)

FORBIDDEN_BEHAVIOR_TERMS = (
    "cannot mutate AKBSM",
    "cannot call writers",
    "cannot create relation types",
    "cannot create concepts",
    "permanent AKBSM write",
    "No proposal storage is implemented",
    "marker 36",
)

PROFILE_TERMS = (
    "safe_demo",
    "draft_only",
    "mutating_memory",
)

FUTURE_COVERAGE_TERMS = (
    "akbsm_proposal_disabled_no_effect",
    "akbsm_draft_only_proposal_no_commit",
    "verify_akbsm_draft_proposal_scaffold",
    "verify_akbsm_draft_proposal_no_commit",
    "verify_akbsm_proposal_validation",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_akbsm_write_policy_adr.py",
    "tools/verify_akbsm_write_disabled_scenarios.py",
    "tools/verify_memory_mutation_policy.py",
    "tools/verify_phase_regression_snapshots.py",
)


def main() -> int:
    text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    missing_status = _missing_terms(text, STATUS_TERMS)
    missing_shape = _missing_terms(text, PROPOSAL_SHAPE_TERMS)
    missing_forbidden = _missing_terms(text, FORBIDDEN_BEHAVIOR_TERMS)
    missing_profiles = _missing_terms(text, PROFILE_TERMS)
    missing_future_coverage = _missing_terms(text, FUTURE_COVERAGE_TERMS)
    safety_passed = _run_core_safety_verifiers()
    checks = {
        "design doc exists": DOC_PATH.exists(),
        "design-only status documented": not missing_status,
        "proposal shape documented": not missing_shape,
        "forbidden behavior documented": not missing_forbidden,
        "profile policy documented": not missing_profiles,
        "future scenarios/verifiers documented": not missing_future_coverage,
        "core safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("AKBSM draft proposal design verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_status:
        print(f"  missing status terms: {', '.join(missing_status)}")
    if missing_shape:
        print(f"  missing proposal shape terms: {', '.join(missing_shape)}")
    if missing_forbidden:
        print(f"  missing forbidden behavior terms: {', '.join(missing_forbidden)}")
    if missing_profiles:
        print(f"  missing profile terms: {', '.join(missing_profiles)}")
    if missing_future_coverage:
        print(f"  missing future coverage terms: {', '.join(missing_future_coverage)}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _missing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = text.lower()
    return [term for term in terms if term.lower() not in normalized]


def _run_core_safety_verifiers() -> bool:
    for relative_path in CORE_SAFETY_VERIFIERS:
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
