from __future__ import annotations

import ast
import hashlib
import inspect
import math
import re
import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.patterns import (  # noqa: E402
    NFPFrame,
    NFPWindow,
    PatternModality,
    PatternOrigin,
    PatternTopology,
)
from clc.patterns.reactivation import NFPReactivation  # noqa: E402
from clc.transduction import NFPWindowAssembler, VisualFieldSnapshot, VisualFieldTransducer  # noqa: E402
from scenarios.support.synthetic_visual_world import SyntheticVisualWorld  # noqa: E402


TRANSDUCTION_ROOT = PROJECT_ROOT / "clc" / "transduction"
RUNTIME_ROOT = PROJECT_ROOT / "clc" / "runtime"
SCENARIO_PATH = PROJECT_ROOT / "scenarios" / "first_natural_pattern_transduction.json"
EXPECTED_MEMORY_HASHES = {
    PROJECT_ROOT / "Memory" / "ExpSM" / "ExpSM_data.json": "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    PROJECT_ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json": "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
}
EXPECTED_SCENARIO_CASES = {
    "default_synthetic_world_is_16x16",
    "world_rejects_invalid_coordinates",
    "world_rejects_invalid_activation_values",
    "snapshot_is_immutable",
    "snapshot_validates_shape_value_length",
    "snapshot_values_are_normalized",
    "snapshot_preserves_active_tick",
    "snapshot_id_generated_independently_of_hidden_debug_meaning",
    "world_mutation_after_snapshot_does_not_mutate_snapshot",
    "visual_field_transducer_creates_nfpframe",
    "frame_modality_visual",
    "frame_origin_external_sensory",
    "frame_topology_matches_snapshot_shape",
    "frame_values_match_row_major_field",
    "frame_tick_matches_snapshot_tick",
    "frame_provenance_is_opaque_sensor_snapshot_style",
    "frame_has_no_semantic_debug_name",
    "world_mutation_after_transduction_does_not_mutate_frame",
    "same_visible_field_different_hidden_debug_descriptions_equal_topology_values",
    "hidden_description_does_not_enter_provenance",
    "same_physical_field_different_ticks_distinct_occurrences_equal_values",
    "changing_one_sensor_cell_changes_only_corresponding_flattened_position",
    "window_size_validation",
    "assembler_returns_none_before_window_full",
    "assembler_creates_nfpwindow_when_full",
    "assembler_uses_sliding_stride_1",
    "assembler_rejects_internal_reactivation",
    "assembler_rejects_mixed_modality",
    "assembler_rejects_topology_mismatch",
    "assembler_rejects_duplicate_frame_ids",
    "assembler_rejects_non_increasing_ticks",
    "generated_window_ids_are_non_semantic",
    "static_field_window_contains_equal_activation_frames",
    "changing_field_window_contains_temporal_activation_variation",
    "window_has_no_semantic_motion_direction_object_metadata",
    "no_akbsm_writes",
    "no_expsm_writes",
    "no_chronicle_writes",
    "no_contextmemory_placement",
    "no_run_tick_integration",
}
FORBIDDEN_PUBLIC_FIELD_NAMES = {
    "label",
    "class_name",
    "object_type",
    "direction",
    "velocity",
    "semantic_name",
    "ground_truth",
    "recognized_object",
    "transcript",
    "motion",
}
FORBIDDEN_IMPORT_PREFIXES = {
    "clc.runtime",
    "clc.action",
    "clc.evaluation",
    "clc.context",
    "clc.akbsm",
    "clc.expsm",
    "clc.consolidation",
    "Memory",
}
FORBIDDEN_RUNTIME_TOKENS = {
    "CLCRuntime",
    "DecisionSelector",
    "ActionProposer",
    "ActionScoring",
    "ModeActionGuard",
    "PolicyPressureReview",
    "ContextMemoryManager",
    "AKBSM",
    "ExpSM",
    "semantic_core.json",
    "technical_feedback_patterns.json",
}


def main() -> int:
    checks = {
        "VisualFieldSnapshot validation": _snapshot_validation,
        "SyntheticVisualWorld behavior": _synthetic_world_behavior,
        "snapshot copy/no-alias boundary": _snapshot_copy_no_alias,
        "deterministic transduction": _deterministic_transduction,
        "VISUAL + EXTERNAL_SENSORY output": _visual_external_output,
        "row-major mapping": _row_major_mapping,
        "opaque provenance": _opaque_provenance,
        "semantic/debug leakage resistance": _label_leakage_resistance,
        "frame immutability/no alias": _frame_immutability,
        "NFPWindowAssembler behavior": _window_assembler_behavior,
        "sliding windows": _sliding_windows,
        "external-sensory-only assembler boundary": _external_sensory_only_boundary,
        "same topology/modality enforcement": _topology_modality_enforcement,
        "strict tick ordering": _strict_tick_ordering,
        "static-field temporal behavior": _static_field_temporal_behavior,
        "changing-field temporal behavior": _changing_field_temporal_behavior,
        "absence of semantic fields": _absence_of_semantic_fields,
        "transduction package isolation": _transduction_package_isolated,
        "normal runtime remains unwired": _normal_runtime_unwired,
        "scenario fixture coverage": _scenario_fixture_coverage,
        "real Memory hashes unchanged": _memory_hashes_unchanged,
    }
    passed = True
    for label, check in checks.items():
        try:
            ok, detail = check()
        except Exception as exc:  # noqa: BLE001 - verifier reports compact failures.
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        print(f"{'PASS' if ok else 'FAIL'}: {label}" + (f" ({detail})" if detail else ""))
        passed = passed and ok
    return 0 if passed else 1


def _snapshot_validation() -> tuple[bool, str]:
    snapshot = VisualFieldSnapshot(shape=(2, 3), values=(0, 0.2, 0.4, 0.6, 0.8, 1), active_tick=7, snapshot_id=3)
    checks = [
        snapshot.shape == (2, 3),
        snapshot.values == (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        snapshot.active_tick == 7,
        snapshot.snapshot_id == 3,
        _raises(lambda: VisualFieldSnapshot(shape=(2,), values=(0.0, 1.0), active_tick=0, snapshot_id=0), ValueError),
        _raises(lambda: VisualFieldSnapshot(shape=(2, 0), values=(), active_tick=0, snapshot_id=0), ValueError),
        _raises(lambda: VisualFieldSnapshot(shape=(2, 2), values=(0.0,), active_tick=0, snapshot_id=0), ValueError),
        _raises(lambda: VisualFieldSnapshot(shape=(1, 1), values=(math.nan,), active_tick=0, snapshot_id=0), ValueError),
        _raises(lambda: VisualFieldSnapshot(shape=(1, 1), values=(-0.1,), active_tick=0, snapshot_id=0), ValueError),
        _raises(lambda: VisualFieldSnapshot(shape=(1, 1), values=(1.1,), active_tick=0, snapshot_id=0), ValueError),
        _raises(lambda: VisualFieldSnapshot(shape=(1, 1), values=(0.5,), active_tick=-1, snapshot_id=0), ValueError),
        _raises(lambda: VisualFieldSnapshot(shape=(1, 1), values=(0.5,), active_tick=0, snapshot_id=-1), ValueError),
        _raises(lambda: setattr(snapshot, "active_tick", 8), FrozenInstanceError),
    ]
    return all(checks), f"shape={snapshot.shape} tick={snapshot.active_tick}"


def _synthetic_world_behavior() -> tuple[bool, str]:
    world = SyntheticVisualWorld()
    world.set_activation(0, 0, 1.0)
    world.set_activation(15, 15, 0.25)
    snapshot = world.snapshot(active_tick=10)
    second = world.snapshot(active_tick=11)
    checks = [
        world.shape == (16, 16),
        snapshot.values[0] == 1.0,
        snapshot.values[-1] == 0.25,
        snapshot.active_tick == 10,
        second.snapshot_id == snapshot.snapshot_id + 1,
        _raises(lambda: SyntheticVisualWorld(shape=(16,)), ValueError),
        _raises(lambda: world.set_activation(-1, 0, 1.0), ValueError),
        _raises(lambda: world.set_activation(0, 16, 1.0), ValueError),
        _raises(lambda: world.set_activation(0, 0, -0.1), ValueError),
        _raises(lambda: world.set_activation(0, 0, 1.1), ValueError),
        _raises(lambda: world.set_field((0.0, 1.0)), ValueError),
    ]
    return all(checks), f"default={world.shape}"


def _snapshot_copy_no_alias() -> tuple[bool, str]:
    world = SyntheticVisualWorld(shape=(2, 2))
    world.set_field((0.0, 0.1, 0.2, 0.3))
    snapshot = world.snapshot(active_tick=1)
    world.clear(1.0)
    checks = [
        snapshot.values == (0.0, 0.1, 0.2, 0.3),
        world.snapshot(active_tick=2).values == (1.0, 1.0, 1.0, 1.0),
    ]
    return all(checks), "snapshot preserved pre-mutation values"


def _deterministic_transduction() -> tuple[bool, str]:
    snapshot = VisualFieldSnapshot((2, 2), (0.0, 0.5, 0.75, 1.0), 4, 12)
    transducer = VisualFieldTransducer()
    frame_a = transducer.transduce(snapshot, frame_id="frame-a")
    frame_b = transducer.transduce(snapshot, frame_id="frame-b")
    checks = [
        frame_a.values == frame_b.values,
        frame_a.topology == frame_b.topology,
        frame_a.modality == frame_b.modality,
        frame_a.active_tick == frame_b.active_tick,
        frame_a.provenance_ref == frame_b.provenance_ref,
        frame_a.frame_id != frame_b.frame_id,
    ]
    return all(checks), "same snapshot maps deterministically"


def _visual_external_output() -> tuple[bool, str]:
    frame = _visual_frame("visual-output", tick=3, values=(0.0, 1.0), shape=(1, 2), snapshot_id=1)
    checks = [
        isinstance(frame, NFPFrame),
        frame.modality == PatternModality.VISUAL,
        frame.origin == PatternOrigin.EXTERNAL_SENSORY,
        frame.topology == PatternTopology((1, 2)),
        frame.active_tick == 3,
        frame.debug_name is None,
    ]
    return all(checks), f"{frame.modality.value}/{frame.origin.value}"


def _row_major_mapping() -> tuple[bool, str]:
    world = SyntheticVisualWorld(shape=(2, 3))
    world.set_activation(0, 0, 0.1)
    world.set_activation(0, 1, 0.2)
    world.set_activation(0, 2, 0.3)
    world.set_activation(1, 0, 0.4)
    world.set_activation(1, 1, 0.5)
    world.set_activation(1, 2, 0.6)
    frame = VisualFieldTransducer().transduce(world.snapshot(active_tick=8), frame_id="row-major")
    return frame.values == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6), str(frame.values)


def _opaque_provenance() -> tuple[bool, str]:
    frame = _visual_frame("opaque", tick=2, values=(0.0,), shape=(1, 1), snapshot_id=123)
    provenance = frame.provenance_ref or ""
    checks = [
        re.fullmatch(r"sensor_snapshot:\d{6}", provenance) is not None,
        "moving" not in provenance,
        "banana" not in provenance,
        "right" not in provenance,
    ]
    return all(checks), provenance


def _label_leakage_resistance() -> tuple[bool, str]:
    values = tuple(1.0 if index == 5 else 0.0 for index in range(16))
    moving = SyntheticVisualWorld(shape=(4, 4), hidden_debug_description="moves right")
    banana = SyntheticVisualWorld(shape=(4, 4), hidden_debug_description="banana")
    moving.set_field(values)
    banana.set_field(values)
    transducer = VisualFieldTransducer()
    frame_moving = transducer.transduce(moving.snapshot(active_tick=10), frame_id="visible-a")
    frame_banana = transducer.transduce(banana.snapshot(active_tick=11), frame_id="visible-b")
    checks = [
        frame_moving.topology == frame_banana.topology,
        frame_moving.values == frame_banana.values,
        frame_moving.modality == frame_banana.modality,
        frame_moving.debug_name is None,
        frame_banana.debug_name is None,
        "moves" not in (frame_moving.provenance_ref or ""),
        "banana" not in (frame_banana.provenance_ref or ""),
    ]
    return all(checks), "hidden descriptions did not affect visible activation"


def _frame_immutability() -> tuple[bool, str]:
    world = SyntheticVisualWorld(shape=(1, 2))
    world.set_field((0.25, 0.75))
    snapshot = world.snapshot(active_tick=5)
    frame = VisualFieldTransducer().transduce(snapshot, frame_id="immutable-frame")
    world.clear(1.0)
    checks = [
        frame.values == (0.25, 0.75),
        _raises(lambda: setattr(frame, "values", (1.0, 1.0)), FrozenInstanceError),
    ]
    return all(checks), "frame preserved pre-mutation values"


def _window_assembler_behavior() -> tuple[bool, str]:
    assembler = NFPWindowAssembler(window_size=3)
    frame1 = _visual_frame("w1", tick=1)
    frame2 = _visual_frame("w2", tick=2)
    frame3 = _visual_frame("w3", tick=3)
    checks = [
        _raises(lambda: NFPWindowAssembler(window_size=0), ValueError),
        assembler.push(frame1) is None,
        assembler.push(frame2) is None,
    ]
    window = assembler.push(frame3)
    checks.extend(
        [
            isinstance(window, NFPWindow),
            window is not None and window.frames == (frame1, frame2, frame3),
            window is not None and window.debug_name is None,
            window is not None and window.window_id == "nfp_window:000001",
        ]
    )
    return all(checks), "window_size=3"


def _sliding_windows() -> tuple[bool, str]:
    assembler = NFPWindowAssembler(window_size=2)
    frame1 = _visual_frame("s1", tick=1)
    frame2 = _visual_frame("s2", tick=2)
    frame3 = _visual_frame("s3", tick=3)
    first = assembler.push(frame1)
    second = assembler.push(frame2)
    third = assembler.push(frame3)
    checks = [
        first is None,
        second is not None and second.frames == (frame1, frame2),
        third is not None and third.frames == (frame2, frame3),
        second is not None and second.window_id == "nfp_window:000001",
        third is not None and third.window_id == "nfp_window:000002",
    ]
    return all(checks), "stride=1"


def _external_sensory_only_boundary() -> tuple[bool, str]:
    original = _visual_frame("external", tick=1)
    replay = NFPReactivation.reactivate_frame(original, new_frame_id="replay", active_tick=2)
    assembler = NFPWindowAssembler(window_size=2)
    checks = [
        _raises(lambda: assembler.push(replay), ValueError),
        replay.origin == PatternOrigin.INTERNAL_REACTIVATION,
    ]
    return all(checks), replay.origin.value


def _topology_modality_enforcement() -> tuple[bool, str]:
    visual = _visual_frame("visual-a", tick=1, shape=(1, 2), values=(0.0, 1.0))
    audio = NFPFrame(
        frame_id="audio-a",
        modality=PatternModality.AUDIO,
        origin=PatternOrigin.EXTERNAL_SENSORY,
        topology=PatternTopology((1, 2)),
        values=(0.0, 1.0),
        active_tick=2,
    )
    larger = _visual_frame("visual-larger", tick=2, shape=(1, 3), values=(0.0, 0.5, 1.0))
    modality_assembler = NFPWindowAssembler(window_size=2)
    topology_assembler = NFPWindowAssembler(window_size=2)
    modality_assembler.push(visual)
    topology_assembler.push(visual)
    checks = [
        _raises(lambda: modality_assembler.push(audio), ValueError),
        _raises(lambda: topology_assembler.push(larger), ValueError),
    ]
    return all(checks), "mixed modality/topology rejected"


def _strict_tick_ordering() -> tuple[bool, str]:
    duplicate_id_assembler = NFPWindowAssembler(window_size=2)
    duplicate_id_assembler.push(_visual_frame("dup", tick=1))
    tick_assembler = NFPWindowAssembler(window_size=2)
    tick_assembler.push(_visual_frame("tick-a", tick=3))
    checks = [
        _raises(lambda: duplicate_id_assembler.push(_visual_frame("dup", tick=2)), ValueError),
        _raises(lambda: tick_assembler.push(_visual_frame("tick-b", tick=3)), ValueError),
        _raises(lambda: tick_assembler.push(_visual_frame("tick-c", tick=2)), ValueError),
    ]
    return all(checks), "duplicate IDs and non-increasing ticks rejected"


def _static_field_temporal_behavior() -> tuple[bool, str]:
    world = SyntheticVisualWorld(shape=(2, 2))
    world.set_field((0.0, 0.5, 0.5, 1.0))
    transducer = VisualFieldTransducer()
    assembler = NFPWindowAssembler(window_size=3)
    frames = tuple(
        transducer.transduce(world.snapshot(active_tick=tick), frame_id=f"static-{tick}") for tick in (10, 11, 12)
    )
    window = None
    for frame in frames:
        window = assembler.push(frame)
    checks = [
        len({frame.frame_id for frame in frames}) == 3,
        len({frame.active_tick for frame in frames}) == 3,
        frames[0].values == frames[1].values == frames[2].values,
        window is not None and window.frames == frames,
    ]
    return all(checks), "equal activation across distinct ticks"


def _changing_field_temporal_behavior() -> tuple[bool, str]:
    world = SyntheticVisualWorld(shape=(2, 3))
    transducer = VisualFieldTransducer()
    assembler = NFPWindowAssembler(window_size=3)
    frames = []
    for index, (tick, coord) in enumerate(((20, (0, 0)), (21, (0, 1)), (22, (0, 2))), start=1):
        world.clear(0.0)
        world.set_activation(coord[0], coord[1], 1.0)
        frames.append(transducer.transduce(world.snapshot(active_tick=tick), frame_id=f"changing-{index}"))
    window = None
    for frame in frames:
        window = assembler.push(frame)
    checks = [
        window is not None,
        frames[0].values != frames[1].values,
        frames[1].values != frames[2].values,
        window is not None and window.frames == tuple(frames),
        not hasattr(window, "motion"),
        not hasattr(window, "direction"),
        not hasattr(window, "object_type"),
    ]
    return all(checks), "temporal variation grouped without interpretation"


def _absence_of_semantic_fields() -> tuple[bool, str]:
    snapshot_fields = {field.name for field in fields(VisualFieldSnapshot)}
    transducer_methods = {name for name, _ in inspect.getmembers(VisualFieldTransducer, inspect.isfunction) if not name.startswith("_")}
    assembler_public = {
        field.name
        for field in fields(NFPWindowAssembler)
        if not field.name.startswith("_")
    }
    public_api_names = snapshot_fields | transducer_methods | assembler_public
    forbidden_present = sorted(public_api_names & FORBIDDEN_PUBLIC_FIELD_NAMES)
    checks = [
        not forbidden_present,
        "hidden_debug_description" not in snapshot_fields,
        "label" not in snapshot_fields,
        "ground_truth" not in snapshot_fields,
    ]
    return all(checks), f"public_api={sorted(public_api_names)}"


def _transduction_package_isolated() -> tuple[bool, str]:
    failures: list[str] = []
    for path in sorted(TRANSDUCTION_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _forbidden_import(alias.name):
                        failures.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _forbidden_import(module):
                    failures.append(f"{path.name}: from {module}")
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNTIME_TOKENS:
            if token in text:
                failures.append(f"{path.name}: token {token}")
    return not failures, "; ".join(failures[:5])


def _normal_runtime_unwired() -> tuple[bool, str]:
    failures: list[str] = []
    for path in sorted(RUNTIME_ROOT.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "clc.transduction" in text or "SyntheticVisualWorld" in text or "VisualFieldTransducer" in text:
            failures.append(str(path.relative_to(PROJECT_ROOT)))
    runtime_text = (RUNTIME_ROOT / "clc_runtime.py").read_text(encoding="utf-8")
    checks = [
        not failures,
        "VisualFieldTransducer" not in runtime_text,
        "NFPWindowAssembler" not in runtime_text,
        "SyntheticVisualWorld" not in runtime_text,
    ]
    return all(checks), "; ".join(failures)


def _scenario_fixture_coverage() -> tuple[bool, str]:
    import json

    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    section = data.get("expect", {}).get("first_natural_pattern_transduction", {})
    cases = section.get("cases", {})
    present = {key for key, value in cases.items() if value is True}
    missing = sorted(EXPECTED_SCENARIO_CASES - present)
    checks = [
        data.get("schema_version") == 1,
        data.get("runtime", {}).get("max_ticks") == 0,
        section.get("isolated") is True,
        section.get("runtime_wiring") is False,
        section.get("akbsm_writes") is False,
        section.get("expsm_writes") is False,
        not missing,
    ]
    return all(checks), f"cases={len(present)} missing={missing[:3]}"


def _memory_hashes_unchanged() -> tuple[bool, str]:
    observed = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in EXPECTED_MEMORY_HASHES}
    mismatches = [
        f"{path.relative_to(PROJECT_ROOT)}={digest}"
        for path, digest in observed.items()
        if digest != EXPECTED_MEMORY_HASHES[path]
    ]
    return not mismatches, "; ".join(mismatches)


def _visual_frame(
    frame_id: str,
    *,
    tick: int,
    values: tuple[float, ...] = (0.0,),
    shape: tuple[int, int] = (1, 1),
    snapshot_id: int = 0,
) -> NFPFrame:
    snapshot = VisualFieldSnapshot(shape=shape, values=values, active_tick=tick, snapshot_id=snapshot_id)
    return VisualFieldTransducer().transduce(snapshot, frame_id=frame_id)


def _forbidden_import(module_name: str) -> bool:
    return any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES)


def _raises(call: Callable[[], object], expected: type[BaseException]) -> bool:
    try:
        call()
    except expected:
        return True
    except Exception:
        return False
    return False


if __name__ == "__main__":
    raise SystemExit(main())
