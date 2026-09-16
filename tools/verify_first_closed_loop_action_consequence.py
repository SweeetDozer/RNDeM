from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.actuation import ActionTransducer, ActuatorSignal  # noqa: E402
from clc.patterns import NFPFrame, PatternModality, PatternOrigin, PatternTopology  # noqa: E402
from clc.transduction import VisualFieldTransducer  # noqa: E402
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld  # noqa: E402


ACTUATION_ROOT = PROJECT_ROOT / "clc" / "actuation"
RUNTIME_ROOT = PROJECT_ROOT / "clc" / "runtime"
SCENARIO_PATH = PROJECT_ROOT / "scenarios" / "first_closed_loop_action_consequence.json"
EXPECTED_MEMORY_HASHES = {
    PROJECT_ROOT / "Memory" / "ExpSM" / "ExpSM_data.json": "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    PROJECT_ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json": "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
}
EXPECTED_SCENARIO_CASES = {
    "action_generated_accepted",
    "action_internal_reactivation_rejected",
    "non_action_modality_rejected",
    "wrong_topology_rejected",
    "actuator_signal_immutable",
    "actuator_signal_values_copied_correctly",
    "signal_active_tick_preserved",
    "signal_occurrence_identity_opaque",
    "source_provenance_opaque_non_semantic",
    "debug_name_does_not_leak",
    "closed_loop_world_defaults_to_16x16",
    "initial_hidden_position_validated",
    "snapshot_tick_equals_world_current_tick",
    "visible_field_contains_only_numeric_sensory_state",
    "signal_tick_must_equal_current_world_tick",
    "world_transition_advances_exactly_one_tick",
    "apply_actuator_signal_returns_none",
    "positive_drive_changes_interior_hidden_position",
    "negative_drive_changes_interior_hidden_position",
    "balanced_drive_leaves_position_unchanged",
    "boundary_clamp_leaves_position_unchanged",
    "same_action_at_interior_vs_boundary_has_different_sensory_consequence",
    "same_action_values_produce_equivalent_numeric_actuator_signal_values",
    "no_blocked_success_collision_callback_exists",
    "action_at_t_produces_next_snapshot_at_t_plus_1",
    "next_snapshot_transduces_to_visual_external_sensory_nfpframe",
    "hidden_world_position_does_not_enter_sensory_provenance",
    "hidden_action_meaning_does_not_enter_actuator_signal",
    "no_direct_action_visual_shortcut",
    "same_action_values_at_different_ticks_remain_distinct_occurrences",
    "no_akbsm_writes",
    "no_expsm_writes",
    "no_chronicle_writes",
    "no_contextmemory_placement",
    "no_run_tick_integration",
}
FORBIDDEN_SIGNAL_FIELDS = {
    "command",
    "direction",
    "movement",
    "target",
    "expected_result",
    "success",
    "failure",
    "collision",
    "blocked",
    "reward",
    "consequence",
    "world_position",
}
FORBIDDEN_ACTUATION_IMPORTS = {
    "clc.runtime",
    "clc.transduction",
    "scenarios.support.synthetic_closed_loop_visual_world",
    "clc.action",
    "clc.evaluation",
    "clc.context",
    "clc.akbsm",
    "clc.expsm",
    "clc.consolidation",
    "Memory",
}
FORBIDDEN_RUNTIME_TOKENS = {
    "clc.actuation",
    "synthetic_closed_loop_visual_world",
    "ActionTransducer",
    "ActuatorSignal",
    "SyntheticClosedLoopVisualWorld",
}


def main() -> int:
    checks = {
        "ActuatorSignal validation and immutability": _actuator_signal_validation,
        "ActionTransducer validation": _action_transducer_validation,
        "opaque provenance": _opaque_provenance,
        "semantic debug-name non-leakage": _debug_name_non_leakage,
        "replay rejection": _replay_rejection,
        "world physical dynamics": _world_physical_dynamics,
        "strict T->T+1 causal timing": _strict_temporal_causality,
        "None return from world transition": _none_return,
        "same-action/different-context behavior": _same_action_different_context,
        "full sensory return path": _full_sensory_return_path,
        "no semantic consequence object": _no_semantic_result_fields,
        "actuation package isolation": _actuation_package_isolated,
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


def _actuator_signal_validation() -> tuple[bool, str]:
    signal = ActuatorSignal(values=(0, 1), active_tick=3, signal_id=1, source_frame_ref="action_frame_ref:abc")
    checks = [
        signal.values == (0.0, 1.0),
        signal.active_tick == 3,
        signal.signal_id == 1,
        _raises(lambda: ActuatorSignal(values=(0.0,), active_tick=0, signal_id=0, source_frame_ref="x"), ValueError),
        _raises(lambda: ActuatorSignal(values=(0.0, 0.5, 1.0), active_tick=0, signal_id=0, source_frame_ref="x"), ValueError),
        _raises(lambda: ActuatorSignal(values=(-0.1, 0.0), active_tick=0, signal_id=0, source_frame_ref="x"), ValueError),
        _raises(lambda: ActuatorSignal(values=(0.0, 1.1), active_tick=0, signal_id=0, source_frame_ref="x"), ValueError),
        _raises(lambda: ActuatorSignal(values=(0.0, 1.0), active_tick=-1, signal_id=0, source_frame_ref="x"), ValueError),
        _raises(lambda: ActuatorSignal(values=(0.0, 1.0), active_tick=0, signal_id=-1, source_frame_ref="x"), ValueError),
        _raises(lambda: ActuatorSignal(values=(0.0, 1.0), active_tick=0, signal_id=0, source_frame_ref=""), ValueError),
        _raises(lambda: setattr(signal, "values", (1.0, 0.0)), FrozenInstanceError),
    ]
    return all(checks), f"signal_id={signal.signal_id} tick={signal.active_tick}"


def _action_transducer_validation() -> tuple[bool, str]:
    transducer = ActionTransducer()
    frame = _action_frame("action_frame:000001", tick=5, values=(0.25, 0.75))
    signal = transducer.transduce(frame)
    next_signal = transducer.transduce(_action_frame("action_frame:000002", tick=6, values=(0.25, 0.75)))
    checks = [
        signal.values == frame.values,
        signal.active_tick == frame.active_tick,
        signal.signal_id == 1,
        next_signal.signal_id == 2,
        signal is not frame,
        _raises(lambda: transducer.transduce("not-a-frame"), TypeError),
        _raises(lambda: transducer.transduce(_frame(PatternModality.VISUAL, PatternOrigin.ACTION_GENERATED, (2,), (0.0, 1.0), 5)), ValueError),
        _raises(lambda: transducer.transduce(_frame(PatternModality.INTERNAL, PatternOrigin.ACTION_GENERATED, (2,), (0.0, 1.0), 5)), ValueError),
        _raises(lambda: transducer.transduce(_frame(PatternModality.AUDIO, PatternOrigin.ACTION_GENERATED, (2,), (0.0, 1.0), 5)), ValueError),
        _raises(lambda: transducer.transduce(_frame(PatternModality.ACTION, PatternOrigin.EXTERNAL_SENSORY, (2,), (0.0, 1.0), 5)), ValueError),
        _raises(lambda: transducer.transduce(_frame(PatternModality.ACTION, PatternOrigin.INTERNAL_STATE, (2,), (0.0, 1.0), 5)), ValueError),
        _raises(lambda: transducer.transduce(_frame(PatternModality.ACTION, PatternOrigin.INTERNAL_REACTIVATION, (2,), (0.0, 1.0), 5)), ValueError),
        _raises(lambda: transducer.transduce(_frame(PatternModality.ACTION, PatternOrigin.ACTION_GENERATED, (1,), (1.0,), 5)), ValueError),
        _raises(lambda: transducer.transduce(_frame(PatternModality.ACTION, PatternOrigin.ACTION_GENERATED, (3,), (0.0, 0.5, 1.0), 5)), ValueError),
        _raises(lambda: transducer.transduce(_frame(PatternModality.ACTION, PatternOrigin.ACTION_GENERATED, (2, 2), (0.0, 0.0, 1.0, 1.0), 5)), ValueError),
    ]
    return all(checks), f"values={signal.values} next_signal_id={next_signal.signal_id}"


def _opaque_provenance() -> tuple[bool, str]:
    frame = _action_frame("move_right_debug_fixture", tick=1, values=(0.0, 1.0), debug_name="move right")
    signal = ActionTransducer().transduce(frame)
    expected = "action_frame_ref:" + hashlib.sha256(frame.frame_id.encode("utf-8")).hexdigest()[:16]
    checks = [
        signal.source_frame_ref == expected,
        re.fullmatch(r"action_frame_ref:[0-9a-f]{16}", signal.source_frame_ref) is not None,
        "move" not in signal.source_frame_ref,
        "right" not in signal.source_frame_ref,
        frame.frame_id not in signal.source_frame_ref,
    ]
    return all(checks), signal.source_frame_ref


def _debug_name_non_leakage() -> tuple[bool, str]:
    frame = _action_frame("action_frame:000003", tick=2, values=(1.0, 0.0), debug_name="left command success")
    signal = ActionTransducer().transduce(frame)
    text = repr(signal)
    checks = [
        "left" not in text,
        "command" not in text,
        "success" not in text,
        signal.values == (1.0, 0.0),
    ]
    return all(checks), "debug_name absent from signal repr"


def _replay_rejection() -> tuple[bool, str]:
    world = SyntheticClosedLoopVisualWorld(shape=(1, 3), initial_row=0, initial_column=1, initial_tick=10)
    before = (world.current_tick, world.hidden_position, world.snapshot().values)
    replay = _frame(PatternModality.ACTION, PatternOrigin.INTERNAL_REACTIVATION, (2,), (0.0, 1.0), 10)
    rejected = _raises(lambda: ActionTransducer().transduce(replay), ValueError)
    after = (world.current_tick, world.hidden_position, world.snapshot().values)
    return rejected and before == after, f"tick={world.current_tick} position={world.hidden_position}"


def _world_physical_dynamics() -> tuple[bool, str]:
    positive = SyntheticClosedLoopVisualWorld(shape=(1, 4), initial_row=0, initial_column=1, initial_tick=7)
    negative = SyntheticClosedLoopVisualWorld(shape=(1, 4), initial_row=0, initial_column=2, initial_tick=7)
    balanced = SyntheticClosedLoopVisualWorld(shape=(1, 4), initial_row=0, initial_column=2, initial_tick=7)
    boundary = SyntheticClosedLoopVisualWorld(shape=(1, 4), initial_row=0, initial_column=3, initial_tick=7)

    positive.apply_actuator_signal(_signal((0.0, 1.0), tick=7))
    negative.apply_actuator_signal(_signal((1.0, 0.0), tick=7))
    balanced.apply_actuator_signal(_signal((0.5, 0.5), tick=7))
    boundary.apply_actuator_signal(_signal((0.0, 1.0), tick=7))

    checks = [
        positive.hidden_position == (0, 2),
        negative.hidden_position == (0, 1),
        balanced.hidden_position == (0, 2),
        boundary.hidden_position == (0, 3),
        positive.current_tick == 8,
        negative.current_tick == 8,
        balanced.current_tick == 8,
        boundary.current_tick == 8,
        _raises(lambda: SyntheticClosedLoopVisualWorld(shape=(1, 4), initial_row=1, initial_column=0), ValueError),
        _raises(lambda: SyntheticClosedLoopVisualWorld(shape=(1, 4), initial_row=0, initial_column=4), ValueError),
    ]
    return all(checks), "positive/negative/balanced/boundary dynamics"


def _strict_temporal_causality() -> tuple[bool, str]:
    world = SyntheticClosedLoopVisualWorld(shape=(1, 4), initial_row=0, initial_column=1, initial_tick=10)
    before_snapshot = world.snapshot()
    before_frame = VisualFieldTransducer().transduce(before_snapshot, frame_id="visual_frame:before")
    action = _action_frame("action_frame:strict", tick=10, values=(0.0, 1.0))
    signal = ActionTransducer().transduce(action)
    result = world.apply_actuator_signal(signal)
    after_snapshot = world.snapshot()
    after_frame = VisualFieldTransducer().transduce(after_snapshot, frame_id="visual_frame:after")
    checks = [
        before_snapshot.active_tick == 10,
        before_frame.active_tick == 10,
        action.active_tick == 10,
        signal.active_tick == 10,
        result is None,
        world.current_tick == 11,
        after_snapshot.active_tick == 11,
        after_frame.active_tick == 11,
        after_frame.active_tick != action.active_tick,
        _raises(lambda: world.apply_actuator_signal(signal), ValueError),
        _raises(lambda: SyntheticClosedLoopVisualWorld(initial_tick=10).apply_actuator_signal(_signal((0.0, 1.0), tick=9)), ValueError),
        _raises(lambda: SyntheticClosedLoopVisualWorld(initial_tick=10).apply_actuator_signal(_signal((0.0, 1.0), tick=11)), ValueError),
    ]
    return all(checks), "ACTION(10) -> VISUAL(11)"


def _none_return() -> tuple[bool, str]:
    world = SyntheticClosedLoopVisualWorld(shape=(1, 3), initial_row=0, initial_column=1, initial_tick=4)
    result = world.apply_actuator_signal(_signal((0.0, 1.0), tick=4))
    return result is None, repr(result)


def _same_action_different_context() -> tuple[bool, str]:
    transducer = ActionTransducer()
    interior_world = SyntheticClosedLoopVisualWorld(shape=(1, 3), initial_row=0, initial_column=0, initial_tick=20)
    boundary_world = SyntheticClosedLoopVisualWorld(shape=(1, 3), initial_row=0, initial_column=2, initial_tick=20)
    action_a = _action_frame("action_frame:interior", tick=20, values=(0.0, 1.0))
    action_b = _action_frame("action_frame:boundary", tick=20, values=(0.0, 1.0))
    signal_a = transducer.transduce(action_a)
    signal_b = transducer.transduce(action_b)
    result_a = interior_world.apply_actuator_signal(signal_a)
    result_b = boundary_world.apply_actuator_signal(signal_b)
    sensory_a = interior_world.snapshot().values
    sensory_b = boundary_world.snapshot().values
    checks = [
        action_a.values == action_b.values,
        signal_a.values == signal_b.values,
        signal_a.signal_id != signal_b.signal_id,
        result_a is None,
        result_b is None,
        interior_world.hidden_position == (0, 1),
        boundary_world.hidden_position == (0, 2),
        sensory_a != sensory_b,
    ]
    return all(checks), f"signals_equal={signal_a.values == signal_b.values} sensory_diff={sensory_a != sensory_b}"


def _full_sensory_return_path() -> tuple[bool, str]:
    world = SyntheticClosedLoopVisualWorld(
        shape=(1, 4),
        initial_row=0,
        initial_column=1,
        initial_tick=30,
        hidden_debug_description="test-only hidden body state",
    )
    visual = VisualFieldTransducer()
    before_snapshot = world.snapshot()
    before_visual = visual.transduce(before_snapshot, frame_id="visual_frame:before")
    action = _action_frame("action_frame:causal", tick=30, values=(0.0, 1.0), debug_name="rightward test label")
    signal = ActionTransducer().transduce(action)
    result = world.apply_actuator_signal(signal)
    after_snapshot = world.snapshot()
    after_visual = visual.transduce(after_snapshot, frame_id="visual_frame:after")
    checks = [
        before_visual.modality == PatternModality.VISUAL,
        before_visual.origin == PatternOrigin.EXTERNAL_SENSORY,
        before_visual.active_tick == 30,
        signal.values == action.values,
        signal.active_tick == action.active_tick,
        result is None,
        after_visual.modality == PatternModality.VISUAL,
        after_visual.origin == PatternOrigin.EXTERNAL_SENSORY,
        after_visual.active_tick == 31,
        after_visual.values != before_visual.values,
        "hidden" not in (after_visual.provenance_ref or ""),
        "body" not in (after_visual.provenance_ref or ""),
        "rightward" not in signal.source_frame_ref,
    ]
    return all(checks), "world->sensor->VISUAL after action"


def _no_semantic_result_fields() -> tuple[bool, str]:
    signal_fields = {field.name for field in fields(ActuatorSignal)}
    world_apply_signature = inspect.signature(SyntheticClosedLoopVisualWorld.apply_actuator_signal)
    checks = [
        signal_fields == {"values", "active_tick", "signal_id", "source_frame_ref"},
        signal_fields.isdisjoint(FORBIDDEN_SIGNAL_FIELDS),
        world_apply_signature.return_annotation in {None, "None"},
    ]
    return all(checks), str(sorted(signal_fields))


def _actuation_package_isolated() -> tuple[bool, str]:
    violations: list[str] = []
    for path in ACTUATION_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _forbidden_import(alias.name, FORBIDDEN_ACTUATION_IMPORTS):
                        violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _forbidden_import(module, FORBIDDEN_ACTUATION_IMPORTS):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")
    return not violations, "; ".join(violations[:5])


def _normal_runtime_unwired() -> tuple[bool, str]:
    violations: list[str] = []
    for path in RUNTIME_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNTIME_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")
    clc_runtime = PROJECT_ROOT / "clc" / "runtime" / "clc_runtime.py"
    if "clc.actuation" in clc_runtime.read_text(encoding="utf-8"):
        violations.append("clc_runtime.py imports clc.actuation")
    return not violations, "; ".join(violations[:5])


def _scenario_fixture_coverage() -> tuple[bool, str]:
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    section = data["expect"]["first_closed_loop_action_consequence"]
    cases = section["cases"]
    present = {key for key, value in cases.items() if value is True}
    checks = [
        section["isolated"] is True,
        section["runtime_wiring"] is False,
        section["run_tick_integration"] is False,
        section["semantic_result_callback"] is False,
        section["akbsm_writes"] is False,
        section["expsm_writes"] is False,
        section["chronicle_writes"] is False,
        section["contextmemory_placement"] is False,
        EXPECTED_SCENARIO_CASES.issubset(present),
    ]
    missing = sorted(EXPECTED_SCENARIO_CASES - present)
    return all(checks), f"cases={len(present)} missing={missing}"


def _memory_hashes_unchanged() -> tuple[bool, str]:
    mismatches = []
    for path, expected in EXPECTED_MEMORY_HASHES.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append(f"{path.relative_to(PROJECT_ROOT)}={actual}")
    return not mismatches, "; ".join(mismatches)


def _action_frame(frame_id: str, tick: int, values: tuple[float, float], debug_name: str | None = None) -> NFPFrame:
    return NFPFrame(
        frame_id=frame_id,
        modality=PatternModality.ACTION,
        origin=PatternOrigin.ACTION_GENERATED,
        topology=PatternTopology((2,)),
        values=values,
        active_tick=tick,
        provenance_ref=None,
        debug_name=debug_name,
    )


def _frame(
    modality: PatternModality,
    origin: PatternOrigin,
    shape: tuple[int, ...],
    values: tuple[float, ...],
    tick: int,
) -> NFPFrame:
    return NFPFrame(
        frame_id=f"frame:{modality.value}:{origin.value}:{shape}:{tick}",
        modality=modality,
        origin=origin,
        topology=PatternTopology(shape),
        values=values,
        active_tick=tick,
        provenance_ref=None,
        debug_name=None,
    )


def _signal(values: tuple[float, float], tick: int) -> ActuatorSignal:
    return ActuatorSignal(values=values, active_tick=tick, signal_id=1, source_frame_ref="action_frame_ref:test")


def _forbidden_import(module: str, forbidden: set[str]) -> bool:
    return any(module == item or module.startswith(f"{item}.") for item in forbidden)


def _raises(call: Callable[[], object], exc_type: type[BaseException]) -> bool:
    try:
        call()
    except exc_type:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
