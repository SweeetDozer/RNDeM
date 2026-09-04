from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.core.markers import OperationMarker
from clc.runtime.memory_mutation_policy import RuntimeProfile, policy_for_profile
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


SCENARIO_ROOT = ROOT / "scenarios"
EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

EXPECTED_FIXTURES = (
    "akbsm_write_disabled_no_effect.json",
    "akbsm_safe_demo_no_write.json",
    "akbsm_draft_only_no_commit.json",
    "akbsm_mutating_memory_still_blocked.json",
    "akbsm_pressure_review_no_graph_write.json",
    "akbsm_repeated_signal_no_association_write.json",
)


def main() -> int:
    before = _real_hashes()
    scenario_results = _run_akbsm_write_disabled_fixtures()
    after = _real_hashes()
    results = {
        "fixtures exist": _fixtures_exist(),
        "scenario runner passes": all(scenario_results.values()),
        "AKBSM write policy ADR verifier passes": _run_verifier("tools/verify_akbsm_write_policy_adr.py"),
        "memory mutation policy blocks AKBSM": _akbsm_write_blocked_by_policy()
        and _run_verifier("tools/verify_memory_mutation_policy.py"),
        "AKBSM association probe verifier passes": _run_verifier("tools/verify_akbsm_association_probe.py"),
        "AKBSM association field verifier passes": _run_verifier("tools/verify_akbsm_association_field.py"),
        "real ExpSM unchanged": before["expsm"] == after["expsm"] == EXP_HASH,
        "real AKBSM unchanged": before["akbsm"] == after["akbsm"] == AKB_HASH,
        "marker 36 absent": _marker_36_absent(),
    }
    passed = all(results.values())

    print("AKBSM write-disabled scenario verification:")
    for fixture, ok in scenario_results.items():
        print(f"  fixture {fixture}: {'PASS' if ok else 'FAIL'}")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _fixtures_exist() -> bool:
    return all((SCENARIO_ROOT / filename).exists() for filename in EXPECTED_FIXTURES)


def _run_akbsm_write_disabled_fixtures() -> dict[str, bool]:
    results: dict[str, bool] = {}
    for filename in EXPECTED_FIXTURES:
        path = SCENARIO_ROOT / filename
        if not path.exists():
            results[filename] = False
            continue
        fixture = load_scenario(path)
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
        marker_36_absent = 36 not in result.marker_counts
        pressure_review_ok = True
        if fixture.name == "akbsm_pressure_review_no_graph_write":
            pressure_review_ok = result.policy_pressure_review is not None
        probe_ok = True
        if fixture.name in {"akbsm_safe_demo_no_write", "akbsm_repeated_signal_no_association_write"}:
            probe_ok = OperationMarker.AKBSM_ASSOCIATION_PROBE.value in result.marker_counts
        results[filename] = result.passed and marker_36_absent and pressure_review_ok and probe_ok and result.memory_unchanged
    return results


def _akbsm_write_blocked_by_policy() -> bool:
    profiles = (
        RuntimeProfile.SAFE_DEMO,
        RuntimeProfile.DRAFT_ONLY,
        RuntimeProfile.MUTATING_MEMORY,
    )
    return all(policy_for_profile(profile).allow_akbsm_write is False for profile in profiles)


def _run_verifier(relative_path: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-B", relative_path],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        return False
    return True


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _marker_36_absent() -> bool:
    forbidden_marker_name = "MARKER" + "_36"
    forbidden_marker_attr = "OperationMarker." + "36"
    forbidden_marker_ctor = "OperationMarker(" + "36"
    for path in (ROOT / "clc").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if forbidden_marker_name in text or forbidden_marker_attr in text or forbidden_marker_ctor in text:
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
