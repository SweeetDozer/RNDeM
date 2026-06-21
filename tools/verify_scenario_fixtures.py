from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture


SCENARIO_ROOT = PROJECT_ROOT / "scenarios"

EXPECTED_MEMORY_HASHES = {
    "ExpSM/ExpSM_data.json": "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    "AKBSM/AKBSM_ne.json": "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
    "AKBSM/DB/semantic_core.json": None,
    "AKBSM/DB/technical_feedback_patterns.json": None,
}


def main() -> int:
    scenario_paths = sorted(SCENARIO_ROOT.glob("*.json"))
    if not scenario_paths:
        print("FAIL: no scenario fixtures found")
        return 1

    passed = True
    before_hashes = _memory_hashes()
    for expected_path, expected_hash in EXPECTED_MEMORY_HASHES.items():
        if before_hashes.get(expected_path) != expected_hash:
            print(f"FAIL: unexpected starting Memory hash for {expected_path}: {before_hashes.get(expected_path)}")
            passed = False

    for scenario_path in scenario_paths:
        try:
            fixture = load_scenario(scenario_path)
            result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
        except Exception as exc:  # noqa: BLE001 - verifier should report fixture failures compactly.
            print(f"FAIL: {scenario_path.name}: {exc}")
            passed = False
            continue

        print(f"{fixture.name}: {'PASS' if result.passed else 'FAIL'}")
        print(f"  markers: {_compact_sequence(result.marker_sequence)}")
        print(f"  counts: {_compact_counts(result.marker_counts)}")
        if result.required_markers_missing:
            print(f"  missing required: {result.required_markers_missing}")
        if result.forbidden_markers_present:
            print(f"  forbidden present: {result.forbidden_markers_present}")
        if result.order_violations:
            print(f"  order violations: {result.order_violations}")
        if fixture.expect.get("min_event_count") is not None:
            print(
                f"  min event count: {len(result.marker_sequence)} >= {fixture.expect.get('min_event_count')} "
                f"{'yes' if result.min_event_count_met else 'no'}"
            )
        if fixture.expect.get("retention_pruned_events"):
            print(f"  retention pruned events: {result.retention_pruned_events}")
        if fixture.expect.get("side_list_caps_respected"):
            print(f"  side-list caps respected: {result.side_list_caps_respected}")
        print(f"  real Memory unchanged: {result.memory_unchanged}")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        passed = passed and result.passed

    after_hashes = _memory_hashes()
    if before_hashes != after_hashes:
        print("FAIL: real Memory hashes changed after scenario verification")
        for key in sorted(before_hashes):
            if before_hashes[key] != after_hashes.get(key):
                print(f"  {key}: {before_hashes[key]} -> {after_hashes.get(key)}")
        passed = False

    if passed:
        print("PASS: scenario fixtures")
        return 0
    return 1


def _compact_sequence(values: list[int], limit: int = 40) -> str:
    if len(values) <= limit:
        return " ".join(str(value) for value in values)
    head = " ".join(str(value) for value in values[:limit])
    return f"{head} ... (+{len(values) - limit})"


def _compact_counts(counts: dict[int, int]) -> str:
    return ", ".join(f"{marker}:{count}" for marker, count in sorted(counts.items()))


def _memory_hashes() -> dict[str, str | None]:
    import hashlib

    hashes: dict[str, str | None] = {}
    for relative in EXPECTED_MEMORY_HASHES:
        path = REAL_MEMORY_ROOT / relative
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    return hashes


if __name__ == "__main__":
    raise SystemExit(main())
