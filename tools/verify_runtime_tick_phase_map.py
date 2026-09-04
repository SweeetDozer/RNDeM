from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.runtime_phase_map import RUNTIME_PHASE_MAP  # noqa: E402
from clc.runtime.clc_runtime import CLCRuntime  # noqa: E402


DOC_PATH = ROOT / "docs" / "runtime_tick_phase_map.md"
MAP_PATH = ROOT / "clc" / "runtime" / "runtime_phase_map.py"

CRITICAL_NAMES = (
    "ActionProposer",
    "DecisionSelector",
    "ModeActionGuard",
    "DecisionAuditObserver",
    "ActionGuardAuditObserver",
    "DecisionCycleSummaryObserver",
    "DecisionCycleHistoryView",
    "ReflectionCandidateBuilder",
    "NeedMoreEvidenceSignalBuilder",
    "ReflectionReviewBuilder",
    "PolicyPressureBuilder",
    "PolicyPressureReviewBuilder",
    "ContextMemoryManager",
    "ContextRetentionPolicy",
    "SideListRetentionPolicy",
)

CAVEATS = (
    "ExpSMMechanismSearch",
    "next-tick material",
    "reflection/pressure chain is observational only",
    "PolicyPressureReview does not influence behavior",
)

KEY_VERIFIERS = (
    "tools/verify_scenario_fixtures.py",
    "tools/verify_reflection_pressure_scenarios.py",
    "tools/verify_policy_pressure_review_scenarios.py",
    "tools/verify_policy_pressure_influence_boundary.py",
)

REQUIRED_HELPERS = (
    "_phase_00_input_commit",
    "_phase_03_action_proposal_and_selection",
    "_phase_06_outcome_evaluation_akbsm_mechanism",
    "_phase_10_runtime_observation_views",
)


def main() -> int:
    checks = {
        "doc exists": DOC_PATH.exists(),
        "phase map module exists": MAP_PATH.exists(),
        "phase entries present": len(RUNTIME_PHASE_MAP) >= 10,
        "phase ids unique": _phase_ids_unique(),
        "critical names documented": _contains_all(CRITICAL_NAMES),
        "timing caveats documented": _contains_all(CAVEATS),
        "critical helper methods exist": _helpers_exist(),
        "key behavior verifiers pass": _run_key_verifiers(),
    }
    passed = all(checks.values())
    print("Runtime tick phase map verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  phases: {len(RUNTIME_PHASE_MAP)}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _phase_ids_unique() -> bool:
    phase_ids = [entry.phase_id for entry in RUNTIME_PHASE_MAP]
    return len(phase_ids) == len(set(phase_ids))


def _contains_all(needles: tuple[str, ...]) -> bool:
    if not DOC_PATH.exists():
        return False
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    map_text = MAP_PATH.read_text(encoding="utf-8") if MAP_PATH.exists() else ""
    combined = f"{doc_text}\n{map_text}"
    return all(needle in combined for needle in needles)


def _helpers_exist() -> bool:
    return all(hasattr(CLCRuntime, name) for name in REQUIRED_HELPERS)


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
