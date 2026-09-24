from __future__ import annotations

import ast
import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.actuation import (
    ActionTransducer,
    NFPRememberedActionExecutionCoordinator,
    NFPRememberedActionExecutionStatus as Status,
    SelectedNFPExecutionRequest,
)
from clc.context.context_memory import ContextMemory
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.context_ops_pool import ContextOpsPool
from clc.context.short_memory import ShortMemory
from clc.core.ids import IdGenerator
from clc.core.pattern_registry import PatternRegistry
from clc.experience.expsm_representation import SerializedNFPActionV1, SerializedObservedEffectV1
from clc.expsm.nfp_operational_retrieval import SelectedNFPExpSMExperience
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState
from clc.transduction import VisualFieldTransducer
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld


MEMORY_FILES = (
    ROOT / "Memory/ExpSM/ExpSM_data.json",
    ROOT / "Memory/AKBSM/AKBSM_ne.json",
)
EXPECTED_HASHES = (
    "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
)


def _hashes() -> tuple[str, ...]:
    return tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in MEMORY_FILES)


class CountingWorld(SyntheticClosedLoopVisualWorld):
    def __init__(self, *args: object, fail: bool = False, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.apply_count = 0
        self.fail = fail

    def apply_actuator_signal(self, signal: object) -> None:
        self.apply_count += 1
        if self.fail:
            raise RuntimeError("injected world rejection")
        super().apply_actuator_signal(signal)


class CountingTransducer(ActionTransducer):
    def __init__(self, reject: bool = False) -> None:
        super().__init__()
        self.calls = 0
        self.reject = reject

    def transduce(self, action_frame: NFPFrame):
        self.calls += 1
        if self.reject:
            raise ValueError("injected transduction rejection")
        return super().transduce(action_frame)


class FailingTrackingManager(ContextMemoryManager):
    def observe_action_frame(self, action_frame: NFPFrame):
        raise RuntimeError("injected post-world tracking failure")


class RememberedActionExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before_hashes = _hashes()
        if cls.before_hashes != EXPECTED_HASHES:
            raise AssertionError(f"unexpected production hashes: {cls.before_hashes}")
        cls.temp = tempfile.TemporaryDirectory()
        cls.registry = PatternRegistry(Path(cls.temp.name) / "manifest.json")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()
        if _hashes() != cls.before_hashes:
            raise AssertionError("production Memory changed")

    def _selected(
        self, source: str = "experience:1", action: tuple[float, ...] = (0.0, 1.0),
        prediction: tuple[float, ...] = (0.0,) * 16,
        topology: tuple[int, ...] = (2,),
    ) -> SelectedNFPExpSMExperience:
        return SelectedNFPExpSMExperience(
            f"selection:{source}", f"activation:{source}", f"candidate:{source}", source,
            1.0, 1.0, SerializedNFPActionV1("action", topology, action),
            SerializedObservedEffectV1("visual", (4, 4), prediction), 0.8, 0.7, 0.9,
        )

    def _episode(self, tick: int = 3, *, manager_type=ContextMemoryManager, world=None):
        world = world or CountingWorld(shape=(4, 4), initial_tick=tick)
        manager = manager_type(ContextMemory(IdGenerator(), self.registry), ContextOpsPool())
        snapshot = world.snapshot()
        frame = VisualFieldTransducer().transduce(snapshot, frame_id=f"before:{tick}")
        before = NFPWindow(f"before-window:{tick}", (frame,))
        manager.observe_external_sensory_window(before)
        return world, manager, before

    def _run(self, selected=None, *, tick=3, state=None, transducer=None,
             manager_type=ContextMemoryManager, world=None, observe=True, short=None):
        world, manager, before = self._episode(tick, manager_type=manager_type, world=world)
        coordinator = NFPRememberedActionExecutionCoordinator(
            IdGenerator(), ModeActionGuard(self.registry), action_transducer=transducer,
        )
        request = SelectedNFPExecutionRequest(selected or self._selected(), tick)
        result = coordinator.execute(
            request, context_manager=manager, world=world,
            system_state=state or SystemState(), observe_consequence=observe,
            short_memory=short,
        )
        return result, world, manager, before

    def test_selected_experience_is_inert_and_runtime_is_not_wired(self) -> None:
        for method in ("execute", "act", "apply"):
            self.assertFalse(hasattr(SelectedNFPExpSMExperience, method))
        runtime = (ROOT / "clc/runtime/clc_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("NFPRememberedActionExecutionCoordinator", runtime)

    def test_stale_selection_stops_before_all_execution_work(self) -> None:
        world, manager, _ = self._episode(3)
        transducer = CountingTransducer()
        result = NFPRememberedActionExecutionCoordinator(
            IdGenerator(), ModeActionGuard(self.registry), transducer,
        ).execute(SelectedNFPExecutionRequest(self._selected(), 2), context_manager=manager,
                  world=world, system_state=SystemState())
        self.assertEqual(result.status, Status.STALE_SELECTION)
        self.assertFalse(result.executed)
        self.assertIsNone(result.action_frame)
        self.assertEqual((transducer.calls, world.apply_count), (0, 0))
        self.assertIsNone(manager.pending_causal_transition)

    def test_pending_collision_preserves_exact_existing_pending(self) -> None:
        world, manager, before = self._episode(3)
        occupied = NFPFrame("occupied", PatternModality.ACTION, PatternOrigin.ACTION_GENERATED,
                            PatternTopology((2,)), (1.0, 0.0), 3)
        pending = manager.observe_action_frame(occupied)
        result = NFPRememberedActionExecutionCoordinator(
            IdGenerator(), ModeActionGuard(self.registry), CountingTransducer(),
        ).execute(SelectedNFPExecutionRequest(self._selected(), 3), context_manager=manager,
                  world=world, system_state=SystemState())
        self.assertEqual(result.status, Status.CAUSAL_SLOT_OCCUPIED)
        self.assertIs(manager.pending_causal_transition, pending)
        self.assertIs(pending.before_sensory_window, before)
        self.assertEqual(world.apply_count, 0)

    def test_invalid_incompatible_guard_transducer_and_world_failures(self) -> None:
        malformed = replace(self._selected(), action=None)
        result, world, manager, _ = self._run(malformed)
        self.assertEqual(result.status, Status.INVALID_SELECTED_EXPERIENCE)
        self.assertEqual(world.apply_count, 0)
        self.assertIsNone(manager.pending_causal_transition)

        incompatible = self._selected(action=(0.1, 0.2, 0.3), topology=(3,))
        transducer = CountingTransducer()
        result, world, _, _ = self._run(incompatible, transducer=transducer)
        self.assertEqual(result.status, Status.ACTUATOR_INCOMPATIBLE)
        self.assertEqual((transducer.calls, world.apply_count), (0, 0))

        transducer = CountingTransducer()
        result, world, manager, _ = self._run(
            state=SystemState(mode="consolidation"), transducer=transducer,
        )
        self.assertEqual(result.status, Status.GUARD_DENIED)
        self.assertEqual((transducer.calls, world.apply_count), (0, 0))
        self.assertIsNone(manager.pending_causal_transition)

        transducer = CountingTransducer(reject=True)
        result, world, manager, _ = self._run(transducer=transducer)
        self.assertEqual(result.status, Status.TRANSDUCTION_REJECTED)
        self.assertEqual((transducer.calls, world.apply_count), (1, 0))
        self.assertIsNone(manager.pending_causal_transition)

        failed_world = CountingWorld(shape=(4, 4), initial_tick=3, fail=True)
        before_position = failed_world.hidden_position
        result, world, manager, _ = self._run(world=failed_world)
        self.assertEqual(result.status, Status.WORLD_EXECUTION_FAILED)
        self.assertFalse(result.executed)
        self.assertEqual(world.apply_count, 1)
        self.assertEqual(world.hidden_position, before_position)
        self.assertIsNone(manager.pending_causal_transition)

    def test_post_world_tracking_failure_is_executed_exactly_once(self) -> None:
        result, world, manager, before = self._run(manager_type=FailingTrackingManager)
        self.assertEqual(result.status, Status.ACTION_EXECUTED_CAUSAL_TRACKING_FAILED)
        self.assertTrue(result.executed)
        self.assertEqual(world.apply_count, 1)
        self.assertEqual(world.current_tick, 4)
        self.assertIs(result.before_context_at_T, before)
        self.assertIsNotNone(result.action_frame)
        self.assertNotEqual(result.source_experience_id, result.action_frame.frame_id)
        self.assertIsNone(manager.pending_causal_transition)
        self.assertIsNone(result.recent_transition)

    def test_observation_pending_and_full_t_plus_one_completion(self) -> None:
        result, world, manager, before = self._run(observe=False)
        self.assertEqual(result.status, Status.ACTION_EXECUTED_OBSERVATION_PENDING)
        self.assertTrue(result.executed)
        self.assertEqual(world.apply_count, 1)
        self.assertIs(result.pending_transition, manager.pending_causal_transition)
        self.assertIs(result.pending_transition.before_sensory_window, before)

        short = ShortMemory(4, 10)
        result, world, manager, before = self._run(short=short)
        self.assertEqual(result.status, Status.EXECUTED_AND_OBSERVED)
        self.assertTrue(result.executed)
        self.assertEqual(world.apply_count, 1)
        self.assertIsNone(manager.pending_causal_transition)
        self.assertIs(result.recent_transition.before_sensory_window, before)
        self.assertEqual(result.recent_transition.action_tick + 1,
                         result.recent_transition.observation_tick)
        self.assertEqual(short.snapshot(), (result.recent_transition,))

    def test_materialization_identity_tick_origin_and_prediction_physics_isolation(self) -> None:
        first, world_a, _, _ = self._run(self._selected("experience:A", prediction=(0.1,) * 16))
        second, world_b, _, _ = self._run(self._selected("experience:B", prediction=(-0.1,) * 16))
        for result in (first, second):
            self.assertEqual(result.action_frame.origin, PatternOrigin.ACTION_GENERATED)
            self.assertEqual(result.action_frame.active_tick, 3)
            self.assertIsNone(result.action_frame.provenance_ref)
            self.assertNotEqual(result.action_frame.frame_id, result.source_experience_id)
        self.assertEqual(first.action_frame.values, second.action_frame.values)
        self.assertEqual(first.actuator_signal.values, second.actuator_signal.values)
        self.assertEqual(world_a.hidden_position, world_b.hidden_position)
        self.assertNotEqual(first.source_experience_id, second.source_experience_id)

        selected = self._selected("experience:repeat")
        coordinator = NFPRememberedActionExecutionCoordinator(
            IdGenerator(), ModeActionGuard(self.registry),
        )
        world_one, manager_one, _ = self._episode(3)
        one = coordinator.execute(
            SelectedNFPExecutionRequest(selected, 3), context_manager=manager_one,
            world=world_one, system_state=SystemState(),
        )
        world_two, manager_two, _ = self._episode(8)
        two = coordinator.execute(
            SelectedNFPExecutionRequest(selected, 8), context_manager=manager_two,
            world=world_two, system_state=SystemState(),
        )
        self.assertEqual(one.source_experience_id, two.source_experience_id)
        self.assertNotEqual(one.action_frame.frame_id, two.action_frame.frame_id)
        self.assertNotEqual(one.action_frame.active_tick, two.action_frame.active_tick)

    def test_fixture_and_authority_boundaries(self) -> None:
        fixture = json.loads((ROOT / "scenarios/nfp_remembered_action_guarded_execution.json").read_text())
        self.assertEqual(fixture["name"], "nfp_remembered_action_guarded_execution")
        source = (ROOT / "clc/actuation/remembered_action_execution.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"MemoryMutationPolicy", "ExpSMCommitWriter", "ExpSMUpdateWriter",
                     "ExpSMStoreTransaction", "NFPExpSMCreateWriter", "Feedback", "CLCRuntime"}
        names = {alias.name.split(".")[-1] for node in ast.walk(tree)
                 if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
        calls = {node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertFalse((names | calls) & forbidden)
        execute = next(node for node in ast.walk(tree)
                       if isinstance(node, ast.FunctionDef) and node.name == "execute")
        world_calls = [node for node in ast.walk(execute) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Attribute)
                       and node.func.attr == "apply_actuator_signal"]
        self.assertEqual(len(world_calls), 1)


def main() -> int:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RememberedActionExecutionTests)
    )
    if not result.wasSuccessful():
        return 1
    print("PASS: guarded remembered-action execution")
    print("PASS: explicit isolation, exactly-once boundary, T+1 causality, and Memory safety")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
