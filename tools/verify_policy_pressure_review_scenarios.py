from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.scenarios.scenario_loader import load_scenario  # noqa: E402
from clc.scenarios.scenario_runner import run_scenario_fixture  # noqa: E402


SCENARIO_ROOT = ROOT / "scenarios"


def main() -> int:
    scenario_paths = sorted(SCENARIO_ROOT.glob("policy_review_*.json"))
    if not scenario_paths:
        print("FAIL: no policy pressure review scenario fixtures found")
        return 1
    passed = True
    print("Policy pressure review scenario verification:")
    for path in scenario_paths:
        fixture = load_scenario(path)
        result = run_scenario_fixture(fixture)
        reflection_expect = fixture.expect.get("reflection", {})
        print(f"scenario: {fixture.name}")
        _print_check(
            "pressure_type",
            reflection_expect.get("policy_pressure_type"),
            result.policy_pressure.pressure_type if result.policy_pressure else None,
        )
        _print_check(
            "pressure_active",
            reflection_expect.get("policy_pressure_active"),
            result.policy_pressure.active if result.policy_pressure else None,
        )
        _print_check(
            "review_status",
            reflection_expect.get("policy_pressure_review_status"),
            result.policy_pressure_review.review_status if result.policy_pressure_review else None,
        )
        _print_check(
            "primary_issue",
            reflection_expect.get("policy_pressure_review_primary_issue"),
            result.policy_pressure_review.primary_issue if result.policy_pressure_review else None,
        )
        _print_check(
            "review_pressure_type",
            reflection_expect.get("policy_pressure_review_pressure_type"),
            result.policy_pressure_review.pressure_type if result.policy_pressure_review else None,
        )
        _print_check(
            "review_active",
            reflection_expect.get("policy_pressure_review_active"),
            result.policy_pressure_review.pressure_active if result.policy_pressure_review else None,
        )
        _print_check(
            "recommended_future_operation",
            reflection_expect.get("policy_pressure_review_recommended_future_operation"),
            result.policy_pressure_review.recommended_future_operation if result.policy_pressure_review else None,
        )
        print(f"  real Memory unchanged: {result.memory_unchanged}")
        if result.reflection_expectation_violations:
            for violation in result.reflection_expectation_violations:
                print(f"  violation: {violation}")
        if not result.passed:
            passed = False
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _print_check(label: str, expected: object, actual: object) -> None:
    if expected is None:
        print(f"  {label}: {actual}")
        return
    print(f"  {label}: {actual} {'PASS' if actual == expected else f'FAIL expected={expected}'}")


if __name__ == "__main__":
    raise SystemExit(main())
