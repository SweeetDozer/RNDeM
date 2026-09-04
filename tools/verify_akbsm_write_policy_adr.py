from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_akbsm_write_policy.md"

CURRENT_POLICY_TERMS = (
    "AKBSM writes are blocked",
    "safe_demo",
    "draft_only",
    "mutating_memory",
)

CANDIDATE_MODE_TERMS = (
    "Mode 0",
    "Mode 1",
    "Mode 2",
    "Mode 3",
    "Mode 4",
)

FIRST_STEP_TERMS = (
    "draft-only AKBSM proposal",
    "AKBSMAssociationProposal",
    "commit_allowed",
    "False",
)

FORBIDDEN_WRITE_TERMS = (
    "direct AKBSM graph mutation",
    "autonomous relation creation",
    "autonomous relation deletion",
    "relation type creation",
    "low confidence",
    "without evidence",
    "marker 36",
)

FUTURE_COVERAGE_TERMS = (
    "verify_akbsm_write_draft_policy",
    "akbsm_write_disabled_no_effect",
    "akbsm_safe_demo_no_write",
    "akbsm_draft_only_proposal_no_commit",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_memory_mutation_policy.py",
    "tools/verify_akbsm_association_probe.py",
    "tools/verify_akbsm_association_field.py",
    "tools/verify_phase_regression_snapshots.py",
)


def main() -> int:
    text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    missing_current_policy = _missing_terms(text, CURRENT_POLICY_TERMS)
    missing_candidate_modes = _missing_terms(text, CANDIDATE_MODE_TERMS)
    missing_first_step = _missing_terms(text, FIRST_STEP_TERMS)
    missing_forbidden_writes = _missing_terms(text, FORBIDDEN_WRITE_TERMS)
    missing_future_coverage = _missing_terms(text, FUTURE_COVERAGE_TERMS)
    safety_passed = _run_core_safety_verifiers()
    checks = {
        "ADR exists": ADR_PATH.exists(),
        "current policy documented": not missing_current_policy,
        "candidate modes documented": not missing_candidate_modes,
        "recommended first step documented": not missing_first_step,
        "forbidden writes documented": not missing_forbidden_writes,
        "future verifiers/scenarios documented": not missing_future_coverage,
        "core safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("AKBSM write policy ADR verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_current_policy:
        print(f"  missing current policy terms: {', '.join(missing_current_policy)}")
    if missing_candidate_modes:
        print(f"  missing candidate modes: {', '.join(missing_candidate_modes)}")
    if missing_first_step:
        print(f"  missing first-step terms: {', '.join(missing_first_step)}")
    if missing_forbidden_writes:
        print(f"  missing forbidden write terms: {', '.join(missing_forbidden_writes)}")
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
