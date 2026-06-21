from __future__ import annotations

import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, regression_summary_for_result, run_scenario_fixture
from tools.phase_regression_snapshots import SELECTED_SCENARIOS, scenario_path, snapshot_path, write_snapshot


def main() -> int:
    print("Generating phase regression snapshots:")
    passed = True
    for scenario_name in SELECTED_SCENARIOS:
        fixture = load_scenario(scenario_path(scenario_name))
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
        if not result.memory_unchanged:
            print(f"  {scenario_name}: FAIL real Memory changed")
            passed = False
            continue
        snapshot = regression_summary_for_result(result)
        write_snapshot(snapshot_path(scenario_name), snapshot)
        print(
            f"  {scenario_name}: wrote {snapshot_path(scenario_name).relative_to(ROOT)} "
            f"events={snapshot.get('event_count')} markers={len(snapshot.get('marker_sequence', []))}"
        )
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
