from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "current_architecture_checkpoint.md"

CRITICAL_TERMS = (
    "runtime tick pipeline",
    "ContextMemory",
    "ContextOpsPool",
    "ContextMemoryManager",
    "ExpSM",
    "AKBSM",
    "ActionProposer",
    "DecisionSelector",
    "ExpSMMechanismSearch",
    "DecisionCycleSummaryObserver",
    "PolicyPressureReview",
    "apply_pending",
    "marker 36",
    "debug-name",
    "real-input scenarios",
    "phase-level invariants",
)

SAFETY_TERMS = (
    "reflection/pressure observational-only",
    "PolicyPressureReview does not influence behavior",
    "DecisionSelector before ExpSMMechanismSearch",
    "apply_pending count = 62",
    "high-risk debug-name findings = 0",
    "legacy_semantic_decision = 0",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_phase_level_invariants.py",
    "tools/verify_run_tick_phase_split_boundaries.py",
    "tools/verify_policy_pressure_influence_boundary.py",
    "tools/verify_legacy_semantic_decision_migration.py",
    "tools/verify_real_input_scenarios.py",
)


def main() -> int:
    doc_text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    missing_critical = _missing_terms(doc_text, CRITICAL_TERMS)
    missing_safety = _missing_terms(doc_text, SAFETY_TERMS)
    verifiers_pass = _run_core_safety_verifiers()
    checks = {
        "checkpoint doc exists": DOC_PATH.exists(),
        "critical sections present": not missing_critical,
        "safety boundaries documented": not missing_safety,
        "core safety verifiers pass": verifiers_pass,
    }
    passed = all(checks.values())

    print("Architecture checkpoint verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_critical:
        print(f"  missing critical terms: {', '.join(missing_critical)}")
    if missing_safety:
        print(f"  missing safety terms: {', '.join(missing_safety)}")
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
