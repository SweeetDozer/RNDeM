from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.clc_runtime import CLCRuntime  # noqa: E402

ADR_PATH = ROOT / "docs" / "adr_run_tick_phase_split_boundaries.md"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
DOCUMENTED_APPLY_PENDING_COUNT = 62

REQUIRED_ADR_TEXT = (
    "ContextMemoryManager.apply_pending",
    "retention timing",
    "DecisionSelector",
    "ExpSMMechanismSearch",
    "reflection/pressure observational-only",
    "PolicyPressureReview",
    "marker 36",
    "scenario fixtures",
    "ExpSM/AKBSM hashes",
)

STRICT_MARKER_36_PATTERNS = (
    "MARKER_36",
    "OperationMarker.36",
    "OperationMarker(36",
    "OperationMarker\\..*36",
)

KEY_VERIFIERS = (
    "tools/verify_runtime_tick_phase_map.py",
    "tools/verify_policy_pressure_influence_boundary.py",
    "tools/verify_scenario_fixtures.py",
    "tools/verify_reflection_pressure_scenarios.py",
    "tools/verify_policy_pressure_review_scenarios.py",
)

REQUIRED_HELPERS = (
    "_phase_00_input_commit",
    "_phase_03_action_proposal_and_selection",
    "_phase_06_outcome_evaluation_akbsm_mechanism",
    "_phase_10_runtime_observation_views",
)


def main() -> int:
    apply_pending_count = _apply_pending_count()
    checks = {
        "ADR exists": ADR_PATH.exists(),
        "critical invariants documented": _adr_contains_required_text(),
        "critical helper methods exist": _helpers_exist(),
        "apply_pending boundaries present": apply_pending_count > 0,
        "marker 36 absent from implementation": _marker_36_absent_from_implementation(),
        "key safety verifiers pass": _run_key_verifiers(),
    }
    passed = all(checks.values())
    print("Run tick phase split boundary verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  apply_pending count: {apply_pending_count}")
    if apply_pending_count != DOCUMENTED_APPLY_PENDING_COUNT:
        print(f"  warning: documented apply_pending count is {DOCUMENTED_APPLY_PENDING_COUNT}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _apply_pending_count() -> int:
    if not RUNTIME_PATH.exists():
        return 0
    return RUNTIME_PATH.read_text(encoding="utf-8").count("apply_pending(")


def _adr_contains_required_text() -> bool:
    if not ADR_PATH.exists():
        return False
    text = ADR_PATH.read_text(encoding="utf-8")
    return all(item in text for item in REQUIRED_ADR_TEXT)


def _helpers_exist() -> bool:
    return all(hasattr(CLCRuntime, name) for name in REQUIRED_HELPERS)


def _marker_36_absent_from_implementation() -> bool:
    paths = [
        path
        for base in ("clc", "scenarios", "tools")
        for path in (ROOT / base).rglob("*")
        if path.is_file() and path.suffix in {".py", ".json"}
    ]
    for path in paths:
        if path.name == "verify_run_tick_phase_split_boundaries.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "MARKER_36" in text or "OperationMarker.36" in text or "OperationMarker(36" in text:
            print(f"  marker 36 implementation reference: {path.relative_to(ROOT)}")
            return False
    return True


def _run_key_verifiers() -> bool:
    for relative_path in KEY_VERIFIERS:
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
