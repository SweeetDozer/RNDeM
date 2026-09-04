from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "design_mode_c_memory_gate_influence.md"

STATUS_TERMS = (
    "design-only",
    "not implemented",
    "Current runtime is still Mode A",
)

SECTION_TERMS = (
    "Possible signal sources",
    "Possible gate targets",
    "Advisory payload",
    "Runtime policy gate",
    "Safety boundaries",
    "Required verifier changes",
    "Required scenario coverage",
    "Rollback plan",
    "Open questions",
)

FORBIDDEN_TERMS = (
    "DecisionSelector",
    "ActionScoring",
    "MemoryMutationPolicy",
    "ExpSM semantic core",
    "AKBSM",
    "permanent memory",
    "planning",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_behavior_influence_adr.py",
    "tools/verify_policy_pressure_influence_boundary.py",
    "tools/verify_phase_regression_snapshots.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    missing_status = _missing_terms(text, STATUS_TERMS)
    missing_sections = _missing_terms(text, SECTION_TERMS)
    missing_forbidden = _missing_terms(text, FORBIDDEN_TERMS)
    safety_passed = _run_core_safety_verifiers()
    checks = {
        "design doc exists": DOC_PATH.exists(),
        "design-only status documented": not missing_status,
        "required sections documented": not missing_sections,
        "forbidden behavior documented": not missing_forbidden,
        "core safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("Mode C design doc verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_status:
        print(f"  missing status terms: {', '.join(missing_status)}")
    if missing_sections:
        print(f"  missing section terms: {', '.join(missing_sections)}")
    if missing_forbidden:
        print(f"  missing forbidden terms: {', '.join(missing_forbidden)}")
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
