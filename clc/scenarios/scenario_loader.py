from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScenarioInput:
    tick: int
    source: str
    kind: str
    patterns: list[str]
    activation: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class ScenarioFixture:
    schema_version: int
    name: str
    description: str
    runtime: dict[str, Any]
    inputs: list[ScenarioInput]
    synthetic_decision_cycle_summaries: list[dict[str, Any]]
    expect: dict[str, Any]


def load_scenario(path: str | Path) -> ScenarioFixture:
    scenario_path = Path(path)
    with scenario_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{scenario_path} must contain a JSON object")
    schema_version = _required_int(data, "schema_version", scenario_path)
    if schema_version != 1:
        raise ValueError(f"{scenario_path}: schema_version must be 1")
    name = _required_str(data, "name", scenario_path)
    description = _optional_str(data, "description")
    runtime = data.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError(f"{scenario_path}: runtime must be an object")
    raw_inputs = data.get("inputs")
    if not isinstance(raw_inputs, list):
        raise ValueError(f"{scenario_path}: inputs must be a list")
    inputs = [_parse_input(item, scenario_path, index) for index, item in enumerate(raw_inputs)]
    synthetic_decision_cycle_summaries = _parse_synthetic_decision_cycle_summaries(data, scenario_path)
    expect = data.get("expect", {})
    if not isinstance(expect, dict):
        raise ValueError(f"{scenario_path}: expect must be an object")
    if "required_markers" not in expect:
        raise ValueError(f"{scenario_path}: expect.required_markers is required")
    _validate_marker_list(expect, "required_markers", scenario_path)
    _validate_marker_list(expect, "optional_markers", scenario_path)
    _validate_marker_list(expect, "forbidden_markers", scenario_path)
    _validate_marker_order(expect, scenario_path)
    _validate_optional_non_negative_int(expect, "min_event_count", scenario_path)
    return ScenarioFixture(
        schema_version=schema_version,
        name=name,
        description=description,
        runtime=dict(runtime),
        inputs=inputs,
        synthetic_decision_cycle_summaries=synthetic_decision_cycle_summaries,
        expect=dict(expect),
    )


def _parse_input(data: object, scenario_path: Path, index: int) -> ScenarioInput:
    if not isinstance(data, dict):
        raise ValueError(f"{scenario_path}: inputs[{index}] must be an object")
    tick = _required_int(data, "tick", scenario_path, index=index)
    if tick < 0:
        raise ValueError(f"{scenario_path}: inputs[{index}].tick must be >= 0")
    patterns = data.get("patterns", [])
    if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
        raise ValueError(f"{scenario_path}: inputs[{index}].patterns must be a list[str]")
    activation = data.get("activation", 1.0)
    if not isinstance(activation, (int, float)):
        raise ValueError(f"{scenario_path}: inputs[{index}].activation must be numeric")
    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError(f"{scenario_path}: inputs[{index}].payload must be an object")
    return ScenarioInput(
        tick=tick,
        source=str(data.get("source", "")),
        kind=_required_str(data, "kind", scenario_path),
        patterns=list(patterns),
        activation=float(activation),
        payload=dict(payload),
    )


def _parse_synthetic_decision_cycle_summaries(data: dict[str, Any], scenario_path: Path) -> list[dict[str, Any]]:
    values = data.get("synthetic_decision_cycle_summaries", [])
    if not isinstance(values, list):
        raise ValueError(f"{scenario_path}: synthetic_decision_cycle_summaries must be a list")
    summaries: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError(f"{scenario_path}: synthetic_decision_cycle_summaries[{index}] must be an object")
        tick = item.get("tick", 0)
        if not isinstance(tick, int) or tick < 0:
            raise ValueError(f"{scenario_path}: synthetic_decision_cycle_summaries[{index}].tick must be an int >= 0")
        summaries.append(dict(item))
    return summaries


def _required_int(data: dict[str, Any], key: str, scenario_path: Path, *, index: int | None = None) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        prefix = f"inputs[{index}]." if index is not None else ""
        raise ValueError(f"{scenario_path}: {prefix}{key} must be an int")
    return value


def _required_str(data: dict[str, Any], key: str, scenario_path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{scenario_path}: {key} must be a non-empty string")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    return value if isinstance(value, str) else ""


def _validate_marker_list(expect: dict[str, Any], key: str, scenario_path: Path) -> None:
    values = expect.get(key, [])
    if not isinstance(values, list) or not all(isinstance(item, int) for item in values):
        raise ValueError(f"{scenario_path}: expect.{key} must be a list[int]")


def _validate_marker_order(expect: dict[str, Any], scenario_path: Path) -> None:
    values = expect.get("marker_order", [])
    if not isinstance(values, list):
        raise ValueError(f"{scenario_path}: expect.marker_order must be a list")
    for index, pair in enumerate(values):
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(item, int) for item in pair):
            raise ValueError(f"{scenario_path}: expect.marker_order[{index}] must be [int, int]")


def _validate_optional_non_negative_int(expect: dict[str, Any], key: str, scenario_path: Path) -> None:
    if key not in expect:
        return
    value = expect.get(key)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{scenario_path}: expect.{key} must be an int >= 0")
