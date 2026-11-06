from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clc.runtime.native_session import NativeSession
from clc.action.decision_selector import DecisionSelector
from clc.actuation.remembered_action_execution import NFPRememberedActionExecutionCoordinator
from clc.context.context_memory import ContextMemory
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.context_ops_pool import ContextOpsPool
from clc.context.short_memory import ShortMemory
from clc.core.ids import IdGenerator
from clc.core.pattern_registry import PatternRegistry
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.nfp_operational_retrieval import NFPExpSMRetriever, NFPExpSMRetrievalConfig
from clc.experience.expsm_representation import (
    NFPExpSMRecordV1, SerializedNFPContextV1, SerializedNFPActionV1,
    SerializedObservedEffectV1, ExpSMOperationalMetadataV1, NFPExpSMCreationMetadataV1,
)
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState
from clc.transduction import VisualFieldTransducer
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld


def inventory():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'Memory').rglob('*') if p.is_file()}


class World(SyntheticClosedLoopVisualWorld):
    def __init__(self, failure=None):
        super().__init__(shape=(1, 4), initial_column=0)
        self.calls = 0
        self.failure = failure
        self.applied = []

    def apply_actuator_signal(self, signal):
        self.calls += 1
        before = (self.current_tick, self.hidden_position)
        super().apply_actuator_signal(signal)
        self.applied.append((before, (self.current_tick, self.hidden_position), signal))
        if self.failure == 'world':
            raise RuntimeError('after real apply')

    def snapshot(self):
        if self.calls and self.failure == 'observation':
            raise RuntimeError('sensor unavailable')
        result = super().snapshot()
        if self.calls and self.failure == 'late':
            from dataclasses import replace
            # Fault injection only: inconsistent late sensor delivery, not a B1 time adapter.
            return replace(result, active_tick=result.active_tick + 1)
        return result


class RecordingManager(ContextMemoryManager):
    def __init__(self, *args):
        super().__init__(*args)
        self.observed_pending = []

    def observe_action_frame(self, frame, execution_occurrence_id=None):
        pending = super().observe_action_frame(frame, execution_occurrence_id)
        self.observed_pending.append(pending)
        return pending


class TrackingFailure(ContextMemoryManager):
    def observe_action_frame(self, frame, execution_occurrence_id=None):
        raise RuntimeError('tracking unavailable after apply')


class RetentionFailure(ShortMemory):
    def remember(self, transition, *, current_tick):
        raise RuntimeError('retention unavailable')


class NativeSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = inventory()

    @classmethod
    def tearDownClass(cls):
        if inventory() != cls.original:
            raise AssertionError('production Memory inventory changed')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rnd012-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def session(self, *, failure=None, empty=False, threshold=.99,
                decision=.35, mode='active', manager_type=RecordingManager,
                short_type=ShortMemory):
        path = self.root / 'ExpSM.json'
        records = {}
        # Prepared data, not a session policy: three contexts with a rightward action.
        for col in range(3):
            values = tuple(float(i == col) for i in range(4))
            effect = tuple(float(i == col + 1) - values[i] for i in range(4))
            record_id = str(col)
            records[record_id] = NFPExpSMRecordV1(
                record_id, SerializedNFPContextV1('visual', (1, 4), (values,)),
                SerializedNFPActionV1('action', (2,), (0., 1.)),
                SerializedObservedEffectV1('visual', (1, 4), effect),
                ExpSMOperationalMetadataV1(5, 0, .8, .9),
                NFPExpSMCreationMetadataV1(2, f'fixture:{col}', 0),
            ).to_json_data()
        path.write_text(json.dumps({'experience': {} if empty else records, 'reflexes': {}}))
        registry = PatternRegistry(self.root / 'manifest.json')
        ids = IdGenerator()
        manager = manager_type(ContextMemory(ids, registry), ContextOpsPool())
        session = NativeSession(
            world=World(failure), context_manager=manager,
            retriever=NFPExpSMRetriever(path), retrieval_config=NFPExpSMRetrievalConfig(threshold),
            activation=ExpSMActivationModule(ids, registry, path),
            selector=DecisionSelector(ids, decision_threshold=decision),
            coordinator=NFPRememberedActionExecutionCoordinator(ids, ModeActionGuard(registry)),
            short_memory=short_type(8, 10), system_state=SystemState(mode=mode), max_episodes=3,
        )
        self.store_bytes = path.read_bytes()
        self.store_path = path
        return session

    def test_three_linked_production_episodes(self):
        s = self.session()
        result = s.run()
        self.assertEqual(len(result), 3)
        occurrences = set()
        observation_ids = set()
        provenance_refs = set()
        for tick, episode in enumerate(result):
            self.assertEqual(episode.retrieval.status.value, 'ok')
            self.assertEqual(len(episode.retrieval.candidates), 1)
            self.assertEqual(episode.retrieval.candidates[0].context_similarity, 1.)
            self.assertEqual(episode.selected.activation_id, episode.activated[0].activation_id)
            self.assertEqual(episode.selected.retrieval_candidate_id, episode.retrieval.candidates[0].candidate_id)
            self.assertEqual(episode.selected.source_experience_id, str(tick))
            self.assertEqual(episode.diagnostic, 'completed')
            self.assertTrue(episode.retained)
            execution = episode.execution
            recent = execution.recent_transition
            self.assertIs(execution.before_context_at_T, episode.before)
            self.assertEqual((recent.action_tick, recent.observation_tick), (tick, tick + 1))
            self.assertEqual(execution.execution_occurrence_id, recent.execution_occurrence_id)
            pending = s.context_manager.observed_pending[tick]
            self.assertEqual(pending.execution_occurrence_id, recent.execution_occurrence_id)
            self.assertIs(pending.action_frame, recent.action_frame)
            self.assertEqual(UUID(execution.execution_occurrence_id).version, 4)
            occurrences.add(execution.execution_occurrence_id)
            self.assertIs(recent.action_frame, execution.action_frame)
            self.assertEqual(execution.action_frame.origin, PatternOrigin.ACTION_GENERATED)
            self.assertEqual(execution.action_frame.topology.shape, (2,))
            self.assertEqual(execution.action_frame.active_tick, tick)
            self.assertNotIn(execution.action_frame.frame_id, {
                episode.selected.selection_id, episode.selected.activation_id,
                episode.selected.source_experience_id,
            })
            before_state, after_state, signal = s.world.applied[tick]
            self.assertEqual(before_state, (tick, (0, tick)))
            self.assertEqual(after_state, (tick + 1, (0, tick + 1)))
            self.assertIs(signal, execution.actuator_signal)
            after = recent.after_sensory_window.frames[0]
            self.assertEqual(after.topology.shape, (1, 4))
            self.assertEqual(after.values, tuple(float(i == tick + 1) for i in range(4)))
            self.assertIs(s.short_memory.snapshot()[tick], recent)
            observation_ids.add(after.frame_id)
            provenance_refs.add(after.provenance_ref)
            self.assertEqual(recent.after_sensory_window.frames[0].origin, PatternOrigin.EXTERNAL_SENSORY)
            self.assertTrue(recent.after_sensory_window.frames[0].provenance_ref)
            if tick:
                self.assertIs(episode.before, result[tick-1].execution.recent_transition.after_sensory_window)
        self.assertEqual(len(occurrences), 3)
        self.assertEqual(len(observation_ids), 3)
        self.assertEqual(len(provenance_refs), 3)
        self.assertIsNone(s.context_manager.pending_causal_transition)
        self.assertEqual((s.world.calls, s.world.current_tick, s.world.hidden_position), (3, 3, (0, 3)))
        self.assertEqual(len(s.short_memory), 3)
        self.assertEqual(s.run(), result)
        self.assertEqual(s.world.calls, 3)
        self.assertEqual(self.store_path.read_bytes(), self.store_bytes)

    def test_no_match_and_selection_none(self):
        for opts, diagnostic in [({'empty': True}, 'no_native_match'),
                                  ({'decision': 1.}, 'selection_none')]:
            s = self.session(**opts)
            episodes = s.run()
            self.assertEqual(episodes[0].diagnostic, diagnostic)
            self.assertEqual((s.world.calls, s.world.current_tick, s.world.hidden_position), (0, 0, (0, 0)))
            self.assertEqual(len(s.short_memory), 0)

    def test_threshold_no_match(self):
        s = self.session()
        s.world._column = 3  # actual unmatched world state before first observation
        result = s.run()[0]
        self.assertEqual(result.retrieval.reason, 'below_native_threshold')
        self.assertIsNone(result.execution)
        self.assertEqual((s.world.calls, s.world.current_tick, s.world.hidden_position), (0, 0, (0, 3)))

    def test_guard_stale_and_pending(self):
        for case in ('guard', 'stale', 'pending'):
            s = self.session(mode='consolidation' if case == 'guard' else 'active')
            if case != 'guard':
                frame = VisualFieldTransducer().transduce(s.world.snapshot(), frame_id='external')
                s.context_manager.observe_external_sensory_window(NFPWindow('before', (frame,)))
                if case == 'stale':
                    s.world.current_tick = 1  # separate-world change, no relabelled evidence
                else:
                    s.context_manager.observe_action_frame(NFPFrame(
                        'occupied', PatternModality.ACTION, PatternOrigin.ACTION_GENERATED,
                        PatternTopology((2,)), (0., 1.), 0))
            result = s.run()[0]
            expected = {'guard': 'guard_denied', 'stale': 'stale_selection', 'pending': 'causal_slot_occupied'}[case]
            self.assertEqual(result.execution.status.value, expected)
            self.assertIsNone(result.execution.actuator_signal)
            if case == 'guard':
                self.assertIsNotNone(result.execution.execution_occurrence_id)
                self.assertIsNotNone(result.execution.action_frame)
            else:
                self.assertIsNone(result.execution.execution_occurrence_id)
            self.assertEqual((s.world.calls, s.world.hidden_position), (0, (0, 0)))
            self.assertEqual(len(s.short_memory), 0)

    def test_post_apply_failures_stop_without_retry(self):
        cases = [({'failure': 'world'}, 'world_execution_failed', False),
                 ({'failure': 'observation'}, 'action_executed_observation_pending', False),
                 ({'failure': 'late'}, 'action_executed_observation_pending', False),
                 ({'manager_type': TrackingFailure}, 'action_executed_causal_tracking_failed', False),
                 ({'short_type': RetentionFailure}, 'executed_and_observed', True)]
        for options, status, observed in cases:
            with self.subTest(options=options):
                s = self.session(**options)
                result = s.run()
                self.assertEqual(len(result), 1)
                episode = result[0]
                self.assertEqual(episode.execution.status.value, status)
                self.assertEqual(episode.execution.recent_transition is not None, observed)
                self.assertFalse(episode.retained)
                self.assertIn('physical_result_may_be_uncertain', s.diagnostic)
                occurrence = episode.execution.execution_occurrence_id
                self.assertIsNotNone(occurrence)
                self.assertEqual((s.world.calls, s.world.current_tick, s.world.hidden_position), (1, 1, (0, 1)))
                self.assertEqual(s.run(), result)
                self.assertEqual(s.world.calls, 1)
                pending = s.context_manager.pending_causal_transition
                if pending:
                    self.assertEqual(pending.execution_occurrence_id, occurrence)
                self.assertEqual(len(s.short_memory), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
