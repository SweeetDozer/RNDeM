from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.actuation import ActionTransducer
from clc.context.causal_transition import (
    PendingCausalTransition, RecentCausalTransition, validate_external_sensory_window,
)
from clc.context.context_memory import ContextMemory
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.context_ops_pool import ContextOpsPool
from clc.context.context_retention_policy import ContextRetentionPolicy
from clc.context.short_memory import ShortMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.nfp import NFPFrame as LegacyFrame
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.field.field_updater import FieldUpdater
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology
from clc.patterns.reactivation import NFPReactivation
from clc.transduction import NFPWindowAssembler, VisualFieldTransducer
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld


def action(tick: int) -> NFPFrame:
    return NFPFrame(f"action:{tick}", PatternModality.ACTION, PatternOrigin.ACTION_GENERATED,
                    PatternTopology((2,)), (0.0, 1.0), tick)


def sensory(tick: int) -> NFPWindow:
    frame = NFPFrame(f"visual:{tick}", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY,
                     PatternTopology((2,)), (0.0, 1.0), tick)
    return NFPWindow(f"window:{tick}", (frame,))


def recent(tick: int, transition_id: str | None = None) -> RecentCausalTransition:
    return RecentCausalTransition(transition_id or f"occurrence:{tick}", sensory(tick - 1),
                                  action(tick - 1), sensory(tick), tick - 1, tick)


def memory_inventory() -> dict[str, str]:
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / "Memory").rglob("*") if path.is_file()}


class ContextShortMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.registry = PatternRegistry(Path(self.directory.name) / "manifest.json")
        self.context = self.new_context()
        self.short = ShortMemory(max_entries=2, max_age_ticks=5)

    def new_context(self) -> ContextMemoryManager:
        return ContextMemoryManager(ContextMemory(IdGenerator(), self.registry), ContextOpsPool())

    def open_pending(self, tick: int = 10) -> PendingCausalTransition:
        self.assertIsNone(self.context.observe_external_sensory_window(sensory(tick)))
        return self.context.observe_action_frame(action(tick))

    def test_legacy_constructor_queue_apply_pending_and_active_field(self) -> None:
        manager = self.context
        self.assertIsNone(manager.current_external_sensory_window)
        self.assertIsNone(manager.current_action_frame)
        self.assertIsNone(manager.pending_causal_transition)
        pattern_id = self.registry.id("input_sensor_pressure")
        raw = LegacyFrame("raw", 1, "external", "sensor", {pattern_id: 0.5})
        thought = LegacyFrame("thought", 1, "self_generated", "internal", {pattern_id: 0.8})
        operations = [
            ContextOperation("raw_op", OperationMarker.RAW_INPUT_WRITE, 1, "test", None, {"frame": raw}),
            ContextOperation("thought_op", OperationMarker.SELF_GENERATED_THOUGHT, 1, "test", None, {"frame": thought}),
        ]
        manager.ops_pool.extend(operations)
        self.assertEqual(len(manager.ops_pool), 2)
        self.assertEqual(manager.memory.events, [])
        manager.apply_pending()
        self.assertEqual(len(manager.ops_pool), 0)
        self.assertEqual(manager.memory.raw_frames, [raw])
        self.assertEqual(manager.memory.thought_frames, [thought])
        self.assertEqual([event.op_id for event in manager.memory.events], ["raw_op", "thought_op"])
        field = ActiveContextField()
        updater = FieldUpdater(self.registry)
        updater.update_from_memory(1, manager.memory, field)
        self.assertTrue(any(item.pattern_id == pattern_id for item in field.get_top_patterns()))
        before = field.debug_snapshot()
        updater.update_from_memory(1, manager.memory, field)
        self.assertEqual(before, field.debug_snapshot())
        retention = manager.last_retention_result
        manager.apply_pending()
        self.assertIs(manager.last_retention_result, retention)
        manager.retention_policy = ContextRetentionPolicy(max_events=1, protected_recent_events=0)
        manager.ops_pool.push(ContextOperation("module_op", OperationMarker.MODULE_UPDATE, 2, "test", None, {}))
        manager.apply_pending()
        self.assertEqual([event.op_id for event in manager.memory.events], ["module_op"])
        self.assertIsNone(manager.pending_causal_transition)

    def test_pending_validation_and_immutability(self) -> None:
        pending = self.open_pending()
        self.assertEqual(pending.expected_observation_tick, 11)
        self.assertIs(pending.action_frame, self.context.current_action_frame)
        self.assertIs(pending.before_sensory_window, self.context.current_external_sensory_window)
        with self.assertRaises(FrozenInstanceError):
            pending.action_tick = 9
        for changes in ({"transition_id": " "}, {"action_tick": 9},
                        {"expected_observation_tick": 12}, {"before_sensory_window": sensory(11)},
                        {"action_tick": True}, {"expected_observation_tick": 11.0},
                        {"action_frame": sensory(10).frames[0]}, {"transition_id": None}):
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                replace(pending, **changes)

    def test_recent_validation_and_immutability(self) -> None:
        item = recent(11)
        with self.assertRaises(FrozenInstanceError):
            item.observation_tick = 12
        for changes in ({"transition_id": ""}, {"action_tick": 9}, {"observation_tick": 12},
                        {"after_sensory_window": sensory(12)}, {"before_sensory_window": sensory(11)},
                        {"after_sensory_window": None}, {"action_frame": "action"}):
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                replace(item, **changes)
        replay = NFPWindow("replay", (NFPReactivation.reactivate_frame(
            sensory(11).frames[0], new_frame_id="replay:11", active_tick=11),))
        for changes in ({"after_sensory_window": replay}, {"before_sensory_window": replay},
                        {"action_frame": replace(action(10), origin=PatternOrigin.INTERNAL_REACTIVATION)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(item, **changes)

    def test_external_qualification_and_mixed_origin(self) -> None:
        self.open_pending()
        before = vars(self.context).copy()
        frame = sensory(11).frames[0]
        replay = replace(frame, origin=PatternOrigin.INTERNAL_REACTIVATION)
        windows = (None, "window", NFPWindow("audio", (replace(frame, modality=PatternModality.AUDIO),)),
                   NFPWindow("mixed", (replace(sensory(10).frames[0], origin=PatternOrigin.INTERNAL_REACTIVATION), frame)),
                   NFPWindow("replay", (replay,)))
        for window in windows:
            with self.subTest(window=window), self.assertRaises((TypeError, ValueError)):
                self.context.observe_external_sensory_window(window)
            self.assertEqual(vars(self.context), before)
        validate_external_sensory_window(sensory(11))

    def test_visual_replay_cannot_complete_then_external_can(self) -> None:
        pending = self.open_pending()
        replay_frame = NFPReactivation.reactivate_frame(
            sensory(10).frames[0], new_frame_id="replay:11", active_tick=11)
        with self.assertRaises(ValueError):
            self.context.observe_external_sensory_window(NFPWindow("replayed", (replay_frame,)))
        self.assertIs(self.context.pending_causal_transition, pending)
        self.assertEqual(self.short.snapshot(), ())
        completed = self.context.observe_external_sensory_window(sensory(11))
        self.short.remember(completed, current_tick=11)
        self.assertEqual(len(self.short), 1)
        self.assertIsNone(self.context.pending_causal_transition)

    def test_action_replay_and_non_action_rejected(self) -> None:
        self.context.observe_external_sensory_window(sensory(10))
        for frame in (None, sensory(10).frames[0],
                      replace(action(10), origin=PatternOrigin.INTERNAL_REACTIVATION),
                      replace(action(10), origin=PatternOrigin.INTERNAL_STATE),
                      replace(action(10), origin=PatternOrigin.EXTERNAL_SENSORY)):
            with self.subTest(frame=frame), self.assertRaises((TypeError, ValueError)):
                self.context.observe_action_frame(frame)
            self.assertIsNone(self.context.pending_causal_transition)
            self.assertIsNone(self.context.current_action_frame)
        with self.assertRaises(ValueError):
            ActionTransducer().transduce(replace(action(10), origin=PatternOrigin.INTERNAL_REACTIVATION))

    def test_action_requires_current_sensory_tick(self) -> None:
        with self.assertRaises(ValueError):
            self.context.observe_action_frame(action(10))
        self.context.observe_external_sensory_window(sensory(10))
        for tick in (9, 11):
            with self.assertRaises(ValueError):
                self.context.observe_action_frame(action(tick))
        self.assertIsNone(self.context.pending_causal_transition)

    def test_second_action_does_not_overwrite(self) -> None:
        pending = self.open_pending()
        for tick in (10, 11, 12):
            with self.assertRaises(ValueError):
                self.context.observe_action_frame(action(tick))
            self.assertIs(self.context.pending_causal_transition, pending)
            self.assertIs(self.context.current_action_frame, pending.action_frame)

    def test_early_and_late_observation(self) -> None:
        pending = self.open_pending()
        self.assertIsNone(self.context.observe_external_sensory_window(sensory(10)))
        self.assertIs(self.context.pending_causal_transition, pending)
        self.assertIsNone(self.context.observe_external_sensory_window(sensory(12)))
        self.assertIsNone(self.context.pending_causal_transition)
        self.assertIsNone(self.context.current_action_frame)
        self.assertEqual(self.context.current_external_sensory_window.end_tick, 12)
        with self.assertRaises(ValueError):
            self.context.observe_external_sensory_window(sensory(11))
        self.assertEqual(len(self.short), 0)

    def test_expiration_active_time_boundary(self) -> None:
        pending = self.open_pending()
        self.assertIsNone(self.context.expire_pending_if_overdue(11))
        self.assertIs(self.context.pending_causal_transition, pending)
        self.assertIs(self.context.expire_pending_if_overdue(12), pending)
        self.assertIsNone(self.context.pending_causal_transition)
        self.assertIsNone(self.context.current_action_frame)
        self.assertEqual(len(self.short), 0)
        self.assertIsNone(self.context.expire_pending_if_overdue(12))
        for tick in (11, -1, True, 12.5):
            with self.assertRaises((TypeError, ValueError)):
                self.context.expire_pending_if_overdue(tick)

    def test_completion_and_layer_distinction(self) -> None:
        pending = self.open_pending()
        self.assertEqual(self.short.snapshot(), ())
        after = sensory(11)
        completed = self.context.observe_external_sensory_window(after)
        self.assertIsInstance(completed, RecentCausalTransition)
        self.assertIsNone(self.context.pending_causal_transition)
        self.assertIsNone(self.context.current_action_frame)
        self.assertIs(self.context.current_external_sensory_window, after)
        self.assertIs(completed.before_sensory_window, pending.before_sensory_window)
        self.assertIs(completed.action_frame, pending.action_frame)
        self.assertEqual(self.short.snapshot(), ())
        self.short.remember(completed, current_tick=11)
        self.assertEqual(self.short.snapshot(), (completed,))
        self.assertIsNone(self.context.observe_external_sensory_window(after))
        self.assertEqual(self.context.memory.events, [])
        self.assertEqual(len(self.context.ops_pool), 0)

    def test_invalid_completion_preserves_pending(self) -> None:
        pending = self.open_pending()
        after = NFPWindow("other", (replace(sensory(11).frames[0], topology=PatternTopology((1, 2))),))
        with self.assertRaises(ValueError):
            self.context.observe_external_sensory_window(after)
        self.assertIs(self.context.pending_causal_transition, pending)
        self.assertIsNotNone(self.context.observe_external_sensory_window(sensory(11)))

    def run_world(self, column: int) -> RecentCausalTransition:
        world = SyntheticClosedLoopVisualWorld(shape=(1, 4), initial_row=0, initial_column=column,
                                               hidden_debug_description="hidden-world-only")
        visual = VisualFieldTransducer()
        assembler = NFPWindowAssembler(2)
        self.assertIsNone(assembler.push(visual.transduce(world.snapshot(), frame_id="v:0")))
        world.apply_actuator_signal(ActionTransducer().transduce(replace(action(0), values=(0.5, 0.5))))
        before = assembler.push(visual.transduce(world.snapshot(), frame_id="v:1"))
        self.context.observe_external_sensory_window(before)
        pending = self.context.observe_action_frame(action(1))
        self.assertEqual(len(self.short), 0)
        self.assertIs(self.context.pending_causal_transition, pending)
        world.apply_actuator_signal(ActionTransducer().transduce(action(1)))
        after = assembler.push(visual.transduce(world.snapshot(), frame_id="v:2"))
        self.assertIs(before.frames[-1], after.frames[0])
        completed = self.context.observe_external_sensory_window(after)
        self.short.remember(completed, current_tick=2)
        self.assertIsNone(self.context.pending_causal_transition)
        self.assertIs(self.context.current_external_sensory_window, after)
        self.assertEqual(self.short.snapshot(), (completed,))
        self.assertNotIn("hidden-world-only", repr(completed))
        return completed

    def test_full_v13_flow_with_overlapping_windows(self) -> None:
        completed = self.run_world(1)
        self.assertNotEqual(completed.before_sensory_window.frames[-1].values,
                            completed.after_sensory_window.frames[-1].values)

    def test_same_values_at_world_boundary_are_valid(self) -> None:
        completed = self.run_world(3)
        self.assertEqual(completed.before_sensory_window.frames[-1].values,
                         completed.after_sensory_window.frames[-1].values)
        self.assertNotEqual(completed.before_sensory_window.end_tick,
                            completed.after_sensory_window.end_tick)

    def test_short_memory_order_and_capacity(self) -> None:
        records = [recent(tick) for tick in (10, 11, 12)]
        for record in records:
            self.short.remember(record, current_tick=record.observation_tick)
        self.assertEqual(self.short.snapshot(), tuple(records[1:]))
        self.assertEqual(len(self.short), 2)
        snapshot = self.short.snapshot()
        with self.assertRaises(TypeError):
            snapshot[0] = records[0]
        with self.assertRaises(AttributeError):
            self.short.max_entries = 100

    def test_short_memory_age_boundary_and_explicit_prune(self) -> None:
        record = recent(10)
        self.short.remember(record, current_tick=10)
        self.short.prune(15)
        self.assertEqual(self.short.snapshot(), (record,))
        self.short.prune(16)
        self.assertEqual(self.short.snapshot(), ())
        zero = ShortMemory(1, 0)
        zero.remember(record, current_tick=10)
        self.assertEqual(len(zero), 1)
        zero.prune(11)
        self.assertEqual(len(zero), 0)
        self.short.remember(recent(12), current_tick=20)
        self.assertEqual(len(self.short), 0)

    def test_short_memory_invalid_inputs_are_atomic(self) -> None:
        for entries, age in ((0, 1), (-1, 1), (1, -1), (True, 1), (1, False), (1.5, 1)):
            with self.assertRaises((TypeError, ValueError)):
                ShortMemory(entries, age)
        record = recent(10)
        self.short.remember(record, current_tick=10)
        for item, tick in ((record, 10), (recent(11), 10), (recent(9), 10), (record, 9),
                           (None, 10), (self.open_pending(), 10), (recent(11), True)):
            with self.subTest(item=item, tick=tick), self.assertRaises((TypeError, ValueError)):
                self.short.remember(item, current_tick=tick)
            self.assertEqual(self.short.snapshot(), (record,))
        with self.assertRaises(ValueError):
            self.short.prune(9)

    def test_equal_activation_occurrences_remain_distinct(self) -> None:
        first, second = recent(10, "opaque:1"), recent(10, "opaque:2")
        self.short.remember(first, current_tick=10)
        self.short.remember(second, current_tick=10)
        self.assertEqual(self.short.snapshot(), (first, second))

    def test_debug_names_do_not_define_identity_or_retention(self) -> None:
        for name in ("move_right_success", "hit_wall"):
            manager = self.new_context()
            window = sensory(10)
            manager.observe_external_sensory_window(replace(window, debug_name=name))
            pending = manager.observe_action_frame(replace(action(10), debug_name=name))
            self.assertEqual(pending.transition_id, "causal_transition:000001")
            completed = manager.observe_external_sensory_window(sensory(11))
            short = ShortMemory(1, 0)
            short.remember(completed, current_tick=11)
            short.prune(12)
            self.assertEqual(len(short), 0)

    def test_public_fields_have_no_semantic_or_hidden_world_data(self) -> None:
        common = {"transition_id", "before_sensory_window", "action_frame", "action_tick"}
        self.assertEqual({field.name for field in fields(PendingCausalTransition)},
                         common | {"expected_observation_tick"})
        self.assertEqual({field.name for field in fields(RecentCausalTransition)},
                         common | {"after_sensory_window", "observation_tick"})
        self.assertEqual(vars(self.short).keys(),
                         {"_max_entries", "_max_age_ticks", "_entries", "_current_tick", "_last_observation_tick"})

    def test_old_temporary_metadata_is_non_authoritative(self) -> None:
        from clc.runtime.context_temporary_metadata import (
            CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY, ContextTemporaryMetadataPlacement,
        )
        from clc.runtime.context_temporary_metadata_observation import (
            CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY, ContextTemporaryMetadataObserver,
        )
        pending = self.open_pending()
        placement = ContextTemporaryMetadataPlacement()
        kwargs = dict(namespace="test", source="test", created_tick=10, ttl_ticks=2)
        self.assertFalse(placement.place_temporary_metadata({}, authority=None, **kwargs).accepted)
        result = placement.place_temporary_metadata(
            {}, authority=CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY, **kwargs)
        self.assertTrue(result.accepted)
        observer = ContextTemporaryMetadataObserver()
        self.assertIsNone(observer.observe(placement, current_tick=11))
        report = observer.observe(placement, current_tick=11,
                                  authority=CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY)
        self.assertIsNotNone(report)
        with self.assertRaises(TypeError):
            self.context.observe_external_sensory_window(result.entry)
        self.assertIs(self.context.pending_causal_transition, pending)
        self.assertFalse(result.entry.write_authorized)

    def test_no_permanent_writes_or_consolidation_on_eviction(self) -> None:
        before = memory_inventory()
        self.run_world(1)
        self.short.prune(100)
        self.assertEqual(len(self.short), 0)
        self.assertEqual(memory_inventory(), before)
        for filename in ("causal_transition.py", "short_memory.py"):
            tree = ast.parse((ROOT / "clc/context" / filename).read_text())
            allowed = {"__future__", "dataclasses", "clc.patterns", "clc.context.causal_transition"}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, allowed)
                self.assertNotIsInstance(node, ast.Import)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"open", "eval", "exec", "__import__"})

    def test_canonical_manager_and_no_runtime_invocation_or_eager_import(self) -> None:
        forbidden_classes = {"NFPContextMemoryManager", "ExperienceCaptureManager",
                             "TransitionMemoryManager", "EpisodeMemoryManager", "ExperienceCaptureMemory",
                             "ExperienceCaptureStore", "TransitionMemory", "EpisodeMemory"}
        managers = []
        for path in (ROOT / "clc").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.assertNotIn(node.name, forbidden_classes)
                    if node.name == "ContextMemoryManager":
                        managers.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(managers, ["clc/context/context_memory_manager.py"])
        script = '''
import contextlib, io, runpy, sys
from clc.context.context_memory_manager import ContextMemoryManager
def forbidden(*args, **kwargs):
    raise AssertionError("normal runtime invoked NFP memory")
for name in ("observe_external_sensory_window", "observe_action_frame", "expire_pending_if_overdue"):
    setattr(ContextMemoryManager, name, forbidden)
with contextlib.redirect_stdout(io.StringIO()):
    runpy.run_path("main.py", run_name="__main__")
for module in ("clc.patterns", "clc.transduction", "clc.actuation", "clc.context.short_memory", "clc.context.causal_transition"):
    assert module not in sys.modules, module
'''
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_scenario_fixture_maps_to_executed_tests(self) -> None:
        data = json.loads((ROOT / "scenarios/nfp_context_short_memory.json").read_text())
        section = data["expect"]["nfp_context_short_memory"]
        expected = {name.removeprefix("test_") for name in unittest.defaultTestLoader.getTestCaseNames(type(self))
                    if name != "test_scenario_fixture_maps_to_executed_tests"}
        self.assertEqual(set(section["cases"]), expected)
        self.assertTrue(all(value is True for value in section["cases"].values()))
        self.assertEqual(data["runtime"]["max_ticks"], 0)
        self.assertEqual(data["inputs"], [])
        for key in ("runtime_wiring", "permanent_writes", "automatic_consolidation"):
            self.assertIs(section[key], False)


def main() -> int:
    before = memory_inventory()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContextShortMemoryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    expected = {
        "Memory/ExpSM/ExpSM_data.json": "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
        "Memory/AKBSM/AKBSM_ne.json": "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
    }
    memory_ok = before == memory_inventory() and all(before.get(key) == value for key, value in expected.items())
    forbidden = {"semantic_core.json", "technical_feedback_patterns.json"}
    memory_ok = memory_ok and not any(Path(path).name in forbidden for path in before)
    print(f"{'PASS' if memory_ok else 'FAIL'}: entire root Memory inventory and hashes unchanged")
    return 0 if result.wasSuccessful() and memory_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
