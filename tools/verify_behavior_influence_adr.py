from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_behavior_influence_modes.md"

MODE_TERMS = (
    "Mode A",
    "Mode B",
    "Mode C",
    "Mode D",
    "Mode E",
    "Mode F",
)

CURRENT_POLICY_TERMS = (
    "observation-only",
    "PolicyPressureReview does not influence behavior",
    "reflection/pressure chain is observational-only",
)

FORBIDDEN_CONNECTION_TERMS = (
    "DecisionSelector",
    "ActionScoring",
    "ActionProposer",
    "ModeActionGuard",
    "Memory writer",
    "FieldUpdater",
    "Neuromodulation",
    "permanent memory write",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_policy_pressure_influence_boundary.py",
    "tools/verify_phase_level_invariants.py",
    "tools/verify_phase_regression_snapshots.py",
    "tools/verify_legacy_semantic_decision_migration.py",
)


def main() -> int:
    text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    missing_modes = _missing_terms(text, MODE_TERMS)
    missing_policy = _missing_terms(text, CURRENT_POLICY_TERMS)
    missing_forbidden = _missing_terms(text, FORBIDDEN_CONNECTION_TERMS)
    safety_passed = _run_core_safety_verifiers()
    checks = {
        "ADR exists": ADR_PATH.exists(),
        "modes documented": not missing_modes,
        "current policy documented": not missing_policy,
        "forbidden direct connections documented": not missing_forbidden,
        "core safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("Behavior influence ADR verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_modes:
        print(f"  missing modes: {', '.join(missing_modes)}")
    if missing_policy:
        print(f"  missing current policy terms: {', '.join(missing_policy)}")
    if missing_forbidden:
        print(f"  missing forbidden connection terms: {', '.join(missing_forbidden)}")
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
