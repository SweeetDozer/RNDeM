from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_mode_c_first_experiment.md"

SOURCE_TARGET_TERMS = (
    "PolicyPressureReview",
    "DraftCommitGate",
    "MemoryWriteReview",
)

FORBIDDEN_TERMS = (
    "direct write",
    "direct commit",
    "direct approval",
    "DecisionSelector",
    "ActionScoring",
    "ModeActionGuard",
    "MemoryMutationPolicy",
    "ExpSM semantic core",
    "AKBSM",
    "marker 36",
)

PROFILE_TERMS = (
    "safe_demo",
    "draft_only",
    "mutating_memory",
)

FUTURE_COVERAGE_TERMS = (
    "mode_c_disabled_no_effect",
    "mode_c_safe_demo_no_effect",
    "mode_c_draft_only_metadata_only",
    "verify_mode_c_advisory_memory_gate",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_mode_c_design_doc.py",
    "tools/verify_behavior_influence_adr.py",
    "tools/verify_policy_pressure_influence_boundary.py",
    "tools/verify_phase_regression_snapshots.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    missing_source_target = _missing_terms(text, SOURCE_TARGET_TERMS)
    missing_forbidden = _missing_terms(text, FORBIDDEN_TERMS)
    missing_profiles = _missing_terms(text, PROFILE_TERMS)
    missing_future_coverage = _missing_terms(text, FUTURE_COVERAGE_TERMS)
    safety_passed = _run_core_safety_verifiers()
    checks = {
        "ADR exists": ADR_PATH.exists(),
        "source/target decision documented": not missing_source_target,
        "forbidden effects documented": not missing_forbidden,
        "profile policy documented": not missing_profiles,
        "future scenarios/verifiers documented": not missing_future_coverage,
        "core safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("Mode C first experiment ADR verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_source_target:
        print(f"  missing source/target terms: {', '.join(missing_source_target)}")
    if missing_forbidden:
        print(f"  missing forbidden terms: {', '.join(missing_forbidden)}")
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
