from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "scenarios"
SNAPSHOT_ROOT = SCENARIO_ROOT / "regression_snapshots"

SELECTED_SCENARIOS = (
    "real_input_repeated_audio_signal",
    "real_input_conflicting_sensor_signal",
    "real_input_low_confidence_action_loop",
    "real_input_integrity_preservation_loop",
    "real_input_value_target_repetition",
    "real_input_retention_with_observation_views",
    "decision_audit_cycle",
    "retention_pressure",
)


def snapshot_path(scenario_name: str) -> Path:
    return SNAPSHOT_ROOT / f"{scenario_name}.snapshot.json"


def scenario_path(scenario_name: str) -> Path:
    return SCENARIO_ROOT / f"{scenario_name}.json"


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(snapshot), encoding="utf-8")


def read_snapshot(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: snapshot must be a JSON object")
    return data


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"
