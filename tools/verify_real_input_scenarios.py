from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


SCENARIO_ROOT = PROJECT_ROOT / "scenarios"

REAL_INPUT_SCENARIOS = [
    "real_input_repeated_audio_signal.json",
    "real_input_conflicting_sensor_signal.json",
    "real_input_low_confidence_action_loop.json",
    "real_input_integrity_preservation_loop.json",
    "real_input_value_target_repetition.json",
    "real_input_retention_with_observation_views.json",
    "real_input_mixed_audio_sensor_sequence.json",
    "real_input_stable_repetition_no_pressure.json",
    "real_input_conflict_then_stabilize.json",
    "real_input_value_target_conflict.json",
    "real_input_long_audio_retention_probe.json",
    "real_input_guard_audit_probe.json",
]


def main() -> int:
    passed = True
    for filename in REAL_INPUT_SCENARIOS:
        fixture = load_scenario(SCENARIO_ROOT / filename)
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
        required_ok = not result.required_markers_missing
        marker_36_absent = 36 not in result.marker_counts
        expected_decision_summary = bool(fixture.expect.get("decision_cycle_summary_observed", True))
        decision_cycle_summary_observed = (35 in result.marker_counts) == expected_decision_summary
        reflection_ok = not result.reflection_expectation_violations
        retention_ok = (
            result.retention_pruned_events if fixture.expect.get("retention_pruned_events") else True
        )
        side_lists_ok = result.side_list_caps_respected

        print(f"scenario: {fixture.name}")
        _print_check("required markers", required_ok)
        _print_check("marker 36 absent", marker_36_absent)
        _print_check(
            f"decision cycle summary observed == {expected_decision_summary}",
            decision_cycle_summary_observed,
        )
        _print_check("min event count", result.min_event_count_met)
        _print_check("reflection expectations", reflection_ok)
        if fixture.expect.get("retention_pruned_events"):
            _print_check("retention pruned", retention_ok)
        if fixture.expect.get("side_list_caps_respected"):
            _print_check("side-list caps respected", side_lists_ok)
        _print_check("memory unchanged", result.memory_unchanged)
        for warning in result.warnings:
            print(f"  warning: {warning}")

        scenario_passed = (
            result.passed
            and required_ok
            and marker_36_absent
            and decision_cycle_summary_observed
            and reflection_ok
            and retention_ok
            and side_lists_ok
        )
        passed = passed and scenario_passed

    if passed:
        print("PASS: real-input scenarios")
        return 0
    print("FAIL: real-input scenarios")
    return 1


def _print_check(label: str, ok: bool) -> None:
    print(f"  {label} {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    raise SystemExit(main())
