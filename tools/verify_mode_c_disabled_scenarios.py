from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.memory_mutation_policy import RuntimeProfile, policy_for_profile
from clc.runtime.mode_c_advisory import ModeCMemoryGateAdvisoryProvider
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


SCENARIO_ROOT = ROOT / "scenarios"
EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

EXPECTED_FIXTURES = (
    "mode_c_disabled_no_effect.json",
    "mode_c_safe_demo_no_effect.json",
    "mode_c_draft_only_metadata_absent.json",
    "mode_c_policy_flag_default_no_advisory.json",
    "mode_c_pressure_review_still_observational.json",
)


def main() -> int:
    before = _real_hashes()
    scenario_results = _run_mode_c_disabled_fixtures()
    after = _real_hashes()
    results = {
        "fixtures exist": _fixtures_exist(),
        "scenario runner passes": all(scenario_results.values()),
        "scaffold remains disabled": _scaffold_disabled(),
        "provider no-op by default": _provider_noop_by_default(),
        "disabled scaffold verifier passes": _run_verifier("tools/verify_mode_c_disabled_scaffold.py"),
        "influence boundary verifier passes": _run_verifier("tools/verify_policy_pressure_influence_boundary.py"),
        "real ExpSM unchanged": before["expsm"] == after["expsm"] == EXP_HASH,
        "real AKBSM unchanged": before["akbsm"] == after["akbsm"] == AKB_HASH,
        "marker 36 absent": _marker_36_absent(),
    }
    passed = all(results.values())
    print("Mode C disabled scenario verification:")
    for fixture, ok in scenario_results.items():
        print(f"  fixture {fixture}: {'PASS' if ok else 'FAIL'}")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _fixtures_exist() -> bool:
    return all((SCENARIO_ROOT / filename).exists() for filename in EXPECTED_FIXTURES)


def _run_mode_c_disabled_fixtures() -> dict[str, bool]:
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
        if fixture.name in {
            "mode_c_policy_flag_default_no_advisory",
            "mode_c_pressure_review_still_observational",
        }:
            pressure_review_ok = result.policy_pressure_review is not None
        results[filename] = result.passed and marker_36_absent and pressure_review_ok and result.memory_unchanged
    return results


def _scaffold_disabled() -> bool:
    policies = (
        policy_for_profile(RuntimeProfile.SAFE_DEMO),
        policy_for_profile(RuntimeProfile.DRAFT_ONLY),
        policy_for_profile(RuntimeProfile.MUTATING_MEMORY),
    )
    return all(policy.mode_c_memory_gate_advisory_enabled is False for policy in policies)


def _provider_noop_by_default() -> bool:
    provider = ModeCMemoryGateAdvisoryProvider(policy_for_profile(RuntimeProfile.SAFE_DEMO))
    return provider.from_policy_pressure_review(object()) == ()


def _run_verifier(relative_path: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-B", relative_path],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stdout)
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
