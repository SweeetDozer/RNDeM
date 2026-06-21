from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.scenarios.scenario_loader import load_scenario  # noqa: E402
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture  # noqa: E402


SCENARIO_ROOT = PROJECT_ROOT / "scenarios"


def main() -> int:
    scenario_paths = sorted(SCENARIO_ROOT.glob("reflection_*.json"))
    if not scenario_paths:
        print("FAIL: no reflection pressure scenario fixtures found")
        return 1
    passed = True
    print("Reflection pressure scenario verification:")
    for scenario_path in scenario_paths:
        fixture = load_scenario(scenario_path)
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
        reflection_expect = fixture.expect.get("reflection", {})
        print(f"scenario: {fixture.name}")
        _print_check(
            "history_trend_label",
            reflection_expect.get("history_trend_label"),
            result.decision_cycle_history_snapshot.trend_label if result.decision_cycle_history_snapshot else None,
        )
        candidate_types = [candidate.reflection_type for candidate in result.reflection_candidates]
        _print_candidate_check(reflection_expect.get("candidate_types", []), candidate_types)
        _print_check(
            "need_more_evidence_active",
            reflection_expect.get("need_more_evidence_active"),
            result.need_more_evidence_signal.active if result.need_more_evidence_signal else None,
        )
        if "need_more_evidence_reason" in reflection_expect:
            _print_check(
                "need_more_evidence_reason",
                reflection_expect.get("need_more_evidence_reason"),
                result.need_more_evidence_signal.reason if result.need_more_evidence_signal else None,
            )
        _print_check(
            "reflection_review_status",
            reflection_expect.get("reflection_review_status"),
            result.reflection_review.review_status if result.reflection_review else None,
        )
        _print_check(
            "reflection_review_primary_issue",
            reflection_expect.get("reflection_review_primary_issue"),
            result.reflection_review.primary_issue if result.reflection_review else None,
        )
        _print_check(
            "policy_pressure_type",
            reflection_expect.get("policy_pressure_type"),
            result.policy_pressure.pressure_type if result.policy_pressure else None,
        )
        _print_check(
            "policy_pressure_active",
            reflection_expect.get("policy_pressure_active"),
            result.policy_pressure.active if result.policy_pressure else None,
        )
        if "policy_pressure_recommended_future_operation" in reflection_expect:
            _print_check(
                "policy_pressure_recommended_future_operation",
                reflection_expect.get("policy_pressure_recommended_future_operation"),
                result.policy_pressure.recommended_future_operation if result.policy_pressure else None,
            )
        if "policy_pressure_review_status" in reflection_expect:
            _print_check(
                "policy_pressure_review_status",
                reflection_expect.get("policy_pressure_review_status"),
                result.policy_pressure_review.review_status if result.policy_pressure_review else None,
            )
        if "policy_pressure_review_primary_issue" in reflection_expect:
            _print_check(
                "policy_pressure_review_primary_issue",
                reflection_expect.get("policy_pressure_review_primary_issue"),
                result.policy_pressure_review.primary_issue if result.policy_pressure_review else None,
            )
        if "policy_pressure_review_pressure_type" in reflection_expect:
            _print_check(
                "policy_pressure_review_pressure_type",
                reflection_expect.get("policy_pressure_review_pressure_type"),
                result.policy_pressure_review.pressure_type if result.policy_pressure_review else None,
            )
        if "policy_pressure_review_active" in reflection_expect:
            _print_check(
                "policy_pressure_review_active",
                reflection_expect.get("policy_pressure_review_active"),
                result.policy_pressure_review.pressure_active if result.policy_pressure_review else None,
            )
        if "policy_pressure_review_recommended_future_operation" in reflection_expect:
            _print_check(
                "policy_pressure_review_recommended_future_operation",
                reflection_expect.get("policy_pressure_review_recommended_future_operation"),
                (
                    result.policy_pressure_review.recommended_future_operation
                    if result.policy_pressure_review
                    else None
                ),
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


def _print_candidate_check(expected: object, actual: list[str]) -> None:
    if not expected:
        print(f"  candidate_types: {', '.join(actual) if actual else 'none'}")
        return
    expected_items = [str(item) for item in expected] if isinstance(expected, list) else [str(expected)]
    missing = [item for item in expected_items if item not in actual]
    print(
        "  candidate_types: "
        f"{', '.join(actual) if actual else 'none'} "
        f"{'PASS' if not missing else f'FAIL missing={missing}'}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
