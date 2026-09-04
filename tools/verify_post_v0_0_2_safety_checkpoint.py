from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md"

BASELINE_TERMS = (
    "v0.0.1",
    "v0.0.2",
    "v0.0.3",
    "post-v0.0.2",
    "not a new runtime release",
)

MODE_C_TERMS = (
    "Mode C disabled by default",
    "ModeCMemoryGateAdvisoryProvider",
    "no-op",
    "PolicyPressureReview",
    "disconnected",
    "no gate integration",
    "no scoring",
)

AKBSM_TERMS = (
    "AKBSM writes blocked",
    "draft proposal scaffold exists",
    "disabled by default",
    "provider is no-op",
    "draft proposal design",
    "no permanent AKBSM mutation",
)

FORBIDDEN_TERMS = (
    "DecisionSelector",
    "ActionScoring",
    "ActionProposer",
    "ModeActionGuard",
    "marker 36",
    "ExpSM/AKBSM memory files",
)

COVERAGE_TERMS = (
    "verify_mode_c_disabled_scenarios.py",
    "verify_akbsm_write_disabled_scenarios.py",
    "verify_akbsm_draft_proposal_design.py",
    "verify_akbsm_draft_proposal_scaffold.py",
    "phase regression snapshots",
    "scenario-only coverage",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_mode_c_disabled_scenarios.py",
    "tools/verify_akbsm_write_disabled_scenarios.py",
    "tools/verify_akbsm_draft_proposal_scaffold.py",
    "tools/verify_memory_mutation_policy.py",
    "tools/verify_phase_regression_snapshots.py",
)


def main() -> int:
    text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    missing_baseline = _missing_terms(text, BASELINE_TERMS)
    missing_mode_c = _missing_terms(text, MODE_C_TERMS)
    missing_akbsm = _missing_terms(text, AKBSM_TERMS)
    missing_forbidden = _missing_terms(text, FORBIDDEN_TERMS)
    missing_coverage = _missing_terms(text, COVERAGE_TERMS)
    safety_passed = _run_core_safety_verifiers()
    checks = {
        "checkpoint exists": DOC_PATH.exists(),
        "baseline documented": not missing_baseline,
        "Mode C state documented": not missing_mode_c,
        "AKBSM state documented": not missing_akbsm,
        "forbidden changes documented": not missing_forbidden,
        "verifier/scenario coverage documented": not missing_coverage,
        "core safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("Post-v0.0.2 safety checkpoint verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_baseline:
        print(f"  missing baseline terms: {', '.join(missing_baseline)}")
    if missing_mode_c:
        print(f"  missing Mode C terms: {', '.join(missing_mode_c)}")
    if missing_akbsm:
        print(f"  missing AKBSM terms: {', '.join(missing_akbsm)}")
    if missing_forbidden:
        print(f"  missing forbidden terms: {', '.join(missing_forbidden)}")
    if missing_coverage:
        print(f"  missing coverage terms: {', '.join(missing_coverage)}")
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
