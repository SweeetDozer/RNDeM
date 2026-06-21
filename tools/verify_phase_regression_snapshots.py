from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, regression_summary_for_result, run_scenario_fixture
from tools.phase_regression_snapshots import SELECTED_SCENARIOS, read_snapshot, scenario_path, snapshot_path


def main() -> int:
    print("Phase regression snapshot verification:")
    passed = True
    for scenario_name in SELECTED_SCENARIOS:
        path = snapshot_path(scenario_name)
        if not path.exists():
            print(f"scenario: {scenario_name}")
            print(f"  snapshot missing: {path.relative_to(ROOT)}")
            passed = False
            continue
        expected = read_snapshot(path)
        fixture = load_scenario(scenario_path(scenario_name))
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
        current = regression_summary_for_result(result)
        diffs = _diff(expected, current)
        memory_ok = bool(current.get("memory_safety", {}).get("exp_sm_unchanged")) and bool(
            current.get("memory_safety", {}).get("akbsm_unchanged")
        )
        scenario_passed = not diffs and memory_ok
        passed = passed and scenario_passed
        print(f"scenario: {scenario_name}")
        print(f"  snapshot match {'PASS' if not diffs else 'FAIL'}")
        print(f"  memory safety {'PASS' if memory_ok else 'FAIL'}")
        for diff in diffs[:12]:
            print(f"  diff: {diff}")
        if len(diffs) > 12:
            print(f"  diff: ... +{len(diffs) - 12} more")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _diff(expected: dict[str, Any], current: dict[str, Any]) -> list[str]:
    diffs: list[str] = []
    _walk_diff("", expected, current, diffs)
    return diffs


def _walk_diff(path: str, expected: Any, current: Any, diffs: list[str]) -> None:
    if type(expected) is not type(current):
        diffs.append(f"{path or '<root>'}: type {type(expected).__name__} != {type(current).__name__}")
        return
    if isinstance(expected, dict):
        expected_keys = set(expected)
        current_keys = set(current)
        for key in sorted(expected_keys - current_keys):
            diffs.append(f"{_join(path, key)}: missing current key")
        for key in sorted(current_keys - expected_keys):
            diffs.append(f"{_join(path, key)}: unexpected current key")
        for key in sorted(expected_keys & current_keys):
            _walk_diff(_join(path, key), expected[key], current[key], diffs)
        return
    if isinstance(expected, list):
        if len(expected) != len(current):
            diffs.append(f"{path}: length {len(expected)} != {len(current)}")
            return
        for index, (left, right) in enumerate(zip(expected, current)):
            _walk_diff(f"{path}[{index}]", left, right, diffs)
        return
    if expected != current:
        diffs.append(f"{path}: {json.dumps(expected, sort_keys=True)} != {json.dumps(current, sort_keys=True)}")


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


if __name__ == "__main__":
    raise SystemExit(main())
