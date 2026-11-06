"""Targeted B2 behavior; writable fixtures live exclusively in temporary roots."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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
from clc.runtime.heart import Heart, HeartState
from clc.runtime.native_heart_session import NativeHeartComponents, NativeHeartSession
from clc.runtime.synthetic_time_adapter import SyntheticTimeAdapter
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld


def inventory():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'Memory').rglob('*') if p.is_file()}


class World(SyntheticClosedLoopVisualWorld):
    def __init__(self, events, failure=None):
        super().__init__(shape=(1, 4), initial_column=0)
        self.events = events
        self.failure = failure
        self.applies = []
        self.idles = []
        self.samples = []

    def snapshot(self):
        if self.failure == 'sensor' and self.current_tick:
            raise RuntimeError('sensor unavailable')
        result = super().snapshot()
        self.samples.append(result)
        self.events.append(('sample', result.active_tick, result.snapshot_id))
        return result

    def apply_actuator_signal(self, signal):
        before = (self.current_tick, self.hidden_position)
        self.events.append(('apply', signal.active_tick))
        self.applies.append((before, signal))
        if self.failure == 'before':
            raise RuntimeError('uncertain rejection')
        super().apply_actuator_signal(signal)
        if self.failure == 'after':
            raise RuntimeError('failed after physical effect')
        if self.failure == 'double':
            self.current_tick += 1  # fault injection, never a normal time adapter

    def advance_idle(self, *, expected_tick):
        self.idles.append((expected_tick, self.hidden_position))
        self.events.append(('idle', expected_tick))
        super().advance_idle(expected_tick=expected_tick)
        if self.failure == 'idle':
            raise RuntimeError('failure after idle time advancement')


class Manager(ContextMemoryManager):
    def observe_external_sensory_window(self, window):
        self.events.append(('observe', window.end_tick))
        return super().observe_external_sensory_window(window)

    def observe_action_frame(self, frame, execution_occurrence_id=None):
        pending = super().observe_action_frame(frame, execution_occurrence_id)
        self.pending_log.append(pending)
        return pending


class Retriever(NFPExpSMRetriever):
    def retrieve(self, query, config):
        self.calls.append(query)
        return super().retrieve(query, config)


class Short(ShortMemory):
    def remember(self, transition, *, current_tick):
        self.events.append(('remember', current_tick))
        if self.fail:
            raise RuntimeError('retention unavailable')
        return super().remember(transition, current_tick=current_tick)


class TrackingFailure(Manager):
    def observe_action_frame(self, frame, execution_occurrence_id=None):
        raise RuntimeError('tracking failed after apply')


class StaleCoordinator(NFPRememberedActionExecutionCoordinator):
    def execute(self, request, **kwargs):
        # Delivery fault: actual production stale check must reject before materialization.
        return super().execute(replace(request, selection_context_end_tick=request.selection_context_end_tick + 1),
                               **kwargs)


class B2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = inventory()

    @classmethod
    def tearDownClass(cls):
        if inventory() != cls.original:
            raise AssertionError('original Memory inventory/SHA-256 changed')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rnd013-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.events = []

    def session(self, *, empty=False, decision=.35, mode='active', ticks=5,
                sensing=True, failure=None, age=10, manager_type=Manager,
                coordinator_type=NFPRememberedActionExecutionCoordinator):
        root = self.root / str(len(list(self.root.iterdir())))
        root.mkdir()
        path = root / 'ExpSM.json'
        records = {}
        for col in range(3):
            values = tuple(float(i == col) for i in range(4))
            record = NFPExpSMRecordV1(
                str(col), SerializedNFPContextV1('visual', (1, 4), (values,)),
                SerializedNFPActionV1('action', (2,), (0., 1.)),
                SerializedObservedEffectV1('visual', (1, 4),
                    tuple(float(i == col + 1) - values[i] for i in range(4))),
                ExpSMOperationalMetadataV1(5, 0, .8, .9),
                NFPExpSMCreationMetadataV1(2, f'fixture:{col}', 0),
            )
            records[str(col)] = record.to_json_data()
        path.write_text(json.dumps({'experience': {} if empty else records, 'reflexes': {}}))
        original = path.read_bytes()
        self.addCleanup(lambda: self.assertEqual(path.read_bytes(), original))
        registry = PatternRegistry(root / 'manifest.json')
        ids = IdGenerator()
        manager = manager_type(ContextMemory(ids, registry), ContextOpsPool())
        manager.events = self.events
        manager.pending_log = []
        retriever = Retriever(path)
        retriever.calls = []
        short = Short(8, age)
        short.events = self.events
        short.fail = False
        world = World(self.events, failure)
        c = NativeHeartComponents(
            world, manager, retriever, NFPExpSMRetrievalConfig(.99),
            ExpSMActivationModule(ids, registry, path),
            DecisionSelector(ids, decision_threshold=decision),
            coordinator_type(ids, ModeActionGuard(registry)), short, SystemState(mode=mode),
        )
        return NativeHeartSession(c, max_ticks=ticks,
                                  sensor=(lambda tick: world.snapshot()) if sensing else None)

    def test_idle_no_match_and_selection_none(self):
        for opts, diagnostic in [({'empty': True}, 'no_native_match'),
                                  ({'decision': 1.}, 'selection_none')]:
            with self.subTest(opts=opts):
                s = self.session(**opts)
                records = s.run()
                c = s.components
                self.assertEqual([r.tick for r in records], list(range(5)))
                self.assertTrue(all(r.diagnostic == diagnostic and r.execution is None for r in records))
                self.assertEqual((s.heart.tick, c.world.current_tick, c.world.hidden_position), (5, 5, (0, 0)))
                self.assertEqual(len(c.world.idles), 5)
                self.assertEqual(c.world.applies, [])
                self.assertEqual(len(c.retriever.calls), 5)
                self.assertIsNone(c.context_manager.pending_causal_transition)
                self.assertEqual(c.context_manager.pending_log, [])

    def test_equal_values_new_identity_and_provenance(self):
        s = self.session(empty=True)
        records = s.run()
        frames = [r.observation.frames[0] for r in records]
        self.assertEqual(len({f.values for f in frames}), 1)
        self.assertEqual(len({f.frame_id for f in frames}), 5)
        self.assertEqual(len({f.provenance_ref for f in frames}), 5)
        self.assertEqual([f.active_tick for f in frames], list(range(5)))
        self.assertEqual([x.snapshot_id for x in s.components.world.samples], list(range(5)))
        for query, record in zip(s.components.retriever.calls, records):
            self.assertIs(query.current_context, record.observation)

    def test_no_input_ticks_do_not_query_or_create_evidence(self):
        s = self.session(sensing=False)
        s.run()
        c = s.components
        self.assertEqual((s.heart.tick, c.world.current_tick), (5, 5))
        self.assertEqual(len(c.world.idles), 5)
        self.assertEqual(c.world.samples, [])
        self.assertEqual(c.retriever.calls, [])
        self.assertIsNone(c.context_manager.current_external_sensory_window)
        self.assertTrue(all(r.observation is None and r.execution is None for r in s.records))

    def test_real_action_then_observation_before_next_admission(self):
        s = self.session(ticks=3)
        c = s.components
        s.start()
        first = s.step()
        self.assertEqual(first.execution.status.value, 'action_executed_observation_pending')
        self.assertIsNone(first.execution.recent_transition)
        self.assertIsNone(first.recent)
        self.assertEqual(len(c.world.samples), 1)  # no same-T consequence observation
        self.assertEqual((s.heart.tick, c.world.current_tick), (1, 1))
        second = s.step()
        self.assertEqual((second.recent.action_tick, second.recent.observation_tick), (0, 1))
        self.assertIs(second.recent.before_sensory_window, first.observation)
        self.assertIs(second.recent.after_sensory_window, second.observation)
        self.assertEqual(second.recent.execution_occurrence_id, first.execution.execution_occurrence_id)
        self.assertEqual(c.context_manager.pending_log[0].execution_occurrence_id,
                         first.execution.execution_occurrence_id)
        self.assertIs(c.short_memory.snapshot()[0], second.recent)
        self.assertLess(self.events.index(('observe', 1)), self.events.index(('remember', 1)))
        self.assertLess(self.events.index(('remember', 1)), self.events.index(('apply', 1)))
        third = s.step()
        self.assertEqual((third.recent.action_tick, third.recent.observation_tick), (1, 2))
        self.assertEqual((c.world.current_tick, c.world.hidden_position), (3, (0, 3)))
        self.assertEqual(len(c.world.applies), 3)
        self.assertEqual(c.world.idles, [])
        self.assertEqual(len({r.execution.execution_occurrence_id for r in s.records}), 3)
        for tick, ((before, signal), record) in enumerate(zip(c.world.applies, s.records)):
            self.assertEqual(before, (tick, (0, tick)))
            self.assertIs(signal, record.execution.actuator_signal)
            self.assertEqual(signal.active_tick, tick)

    def test_pending_missing_T1_expires_only_overdue(self):
        s = self.session(ticks=4)
        c = s.components
        s.sensor = lambda tick: c.world.snapshot() if tick == 0 else None
        s.start()
        first = s.step()
        pending = c.context_manager.pending_causal_transition
        s.step()
        self.assertIs(c.context_manager.pending_causal_transition, pending)
        self.assertIsNone(s.records[1].expired)
        s.step()
        self.assertIs(s.records[2].expired, pending)
        self.assertIsNone(c.context_manager.pending_causal_transition)
        self.assertIs(c.context_manager.current_external_sensory_window, first.observation)
        self.assertEqual(first.observation.end_tick, 0)
        s.run()
        self.assertEqual((len(c.world.applies), len(c.world.idles), c.world.current_tick), (1, 3, 4))
        self.assertEqual(len(c.retriever.calls), 1)
        self.assertEqual(len(c.short_memory), 0)
        self.assertIn(first.execution.execution_occurrence_id, s.stop_report().unresolved_occurrences)

    def test_short_memory_retention_and_idle_pruning(self):
        s = self.session(ticks=5, age=1)
        c = s.components
        s.sensor = lambda tick: c.world.snapshot() if tick <= 1 else None
        s.start()
        s.step()
        c.system_state.mode = 'consolidation'
        s.step()
        recent = s.records[1].recent
        self.assertIs(c.short_memory.snapshot()[0], recent)
        s.step()
        self.assertIs(c.short_memory.snapshot()[0], recent)
        s.step()
        self.assertEqual(len(c.short_memory), 0)
        self.assertEqual((len(c.world.applies), len(c.world.idles)), (1, 3))
        self.assertEqual(len(c.retriever.calls), 2)
        self.assertEqual(s.records[1].execution.status.value, 'guard_denied')

    def test_late_real_sample_does_not_complete_expired_T1_relation(self):
        s = self.session(ticks=3)
        c = s.components
        s.sensor = lambda tick: c.world.snapshot() if tick != 1 else None
        s.run()
        self.assertIsNone(s.records[2].recent)
        self.assertEqual(len(c.short_memory), 0)
        self.assertEqual((s.records[0].observation.end_tick, s.records[2].observation.end_tick), (0, 2))
        first, last = s.records[0].execution, s.records[2].execution
        self.assertNotEqual(first.execution_occurrence_id, last.execution_occurrence_id)
        self.assertEqual(last.action_frame.active_tick, 2)
        self.assertEqual((len(c.world.applies), len(c.world.idles), c.world.current_tick), (2, 1, 3))
        self.assertEqual(len(c.retriever.calls), 2)
        self.assertIn(first.execution_occurrence_id, s.stop_report().unresolved_occurrences)

    def test_guard_denial_has_no_physical_apply(self):
        s = self.session(mode='consolidation', ticks=3)
        s.run()
        self.assertEqual(len(s.components.world.idles), 3)
        self.assertEqual(s.components.world.applies, [])
        for r in s.records:
            self.assertEqual(r.execution.status.value, 'guard_denied')
            self.assertIsNone(r.execution.actuator_signal)
            # Guard's existing materialization/occurrence semantics remain intact.
            self.assertIsNotNone(r.execution.execution_occurrence_id)
        self.assertEqual(s.stop_report().unresolved_occurrences, ())

    def test_stale_selection_no_occurrence_or_automatic_recreation(self):
        s = self.session(coordinator_type=StaleCoordinator, ticks=3)
        c = s.components
        s.sensor = lambda tick: c.world.snapshot() if tick == 0 else None
        s.run()
        execution = s.records[0].execution
        self.assertEqual(execution.status.value, 'stale_selection')
        self.assertIsNone(execution.execution_occurrence_id)
        self.assertIsNone(execution.action_frame)
        self.assertEqual(c.world.applies, [])
        self.assertEqual(len(c.world.idles), 3)
        self.assertEqual(len(c.retriever.calls), 1)
        self.assertTrue(all(r.execution is None for r in s.records[1:]))

    def test_pause_resume_freezes_world_and_preserves_pending(self):
        s = self.session(ticks=3)
        s.start()
        s.step()
        c = s.components
        pending = c.context_manager.pending_causal_transition
        s.pause()
        self.assertIsNone(s.step())
        self.assertEqual(len(s.run()), 1)  # run does not implicitly resume
        self.assertEqual((s.heart.tick, c.world.current_tick, len(c.world.applies)), (1, 1, 1))
        self.assertIs(c.context_manager.pending_causal_transition, pending)
        s.resume()
        s.step()
        self.assertEqual((s.records[1].tick, s.records[1].recent.observation_tick), (1, 1))
        self.assertEqual((s.heart.tick, c.world.current_tick), (2, 2))

    def test_stop_pending_and_repeated_completed_run(self):
        for budget_stop in (False, True):
            s = self.session(ticks=1 if budget_stop else 3)
            s.start()
            s.step()
            report = s.stop_report() if budget_stop else s.stop()
            self.assertIsNotNone(report.pending)
            self.assertFalse(report.in_flight)
            self.assertEqual(report.unresolved_occurrences, (report.pending.execution_occurrence_id,))
            records = tuple(s.records)
            s.start()
            s.resume()
            self.assertEqual(s.run(), records)
            self.assertIsNone(s.step())
            self.assertEqual((len(s.components.world.applies), len(s.components.world.idles)), (1, 0))

    def test_post_world_failures_never_idle_or_retry(self):
        for opts, world_tick, position in [({'failure': 'before'}, 0, (0, 0)),
                                           ({'failure': 'after'}, 1, (0, 1)),
                                           ({'manager_type': TrackingFailure}, 1, (0, 1))]:
            with self.subTest(opts=opts):
                s = self.session(**opts)
                s.run()
                c = s.components
                self.assertEqual((c.world.current_tick, c.world.hidden_position), (world_tick, position))
                self.assertEqual((len(c.world.applies), len(c.world.idles)), (1, 0))
                self.assertTrue(s.stop_report().synchronization_blocked)
                self.assertTrue(s.stop_report().unresolved_occurrences)
                self.assertIn('physical_result_may_be_uncertain', s.diagnostic)
                s.run()
                self.assertEqual(len(c.world.applies), 1)

    def test_sensor_and_retention_failure_stop_without_further_action(self):
        for failure in ('sensor', 'retention'):
            s = self.session(failure='sensor' if failure == 'sensor' else None)
            s.start()
            s.step()
            if failure == 'retention':
                s.components.short_memory.fail = True
            with self.assertRaises(RuntimeError):
                s.step()
            self.assertEqual(s.heart.state, HeartState.STOPPED)
            self.assertTrue(s.stop_report().unresolved_occurrences)
            self.assertEqual((s.components.world.current_tick, len(s.components.world.applies),
                              len(s.components.world.idles)), (1, 1, 0))
            s.run()
            self.assertEqual(len(s.components.world.applies), 1)

    def test_boundary_divergence_and_double_advance_fail_closed(self):
        s = self.session()
        s.components.world.current_tick = 1  # external time divergence fault
        with self.assertRaises(RuntimeError):
            s.run()
        self.assertEqual(s.components.world.samples, [])
        self.assertEqual(s.components.world.idles, [])
        s = self.session(failure='double')
        with self.assertRaises(RuntimeError):
            s.run()
        self.assertEqual((s.components.world.current_tick, len(s.components.world.applies)), (2, 1))
        self.assertEqual(s.components.world.idles, [])
        s.run()
        self.assertEqual(len(s.components.world.applies), 1)

    def test_adapter_rejects_second_finish_and_unclaimed_advance(self):
        world = World(self.events)
        adapter = SyntheticTimeAdapter(world)
        adapter.open(0)
        adapter.finish(actuator_advanced=False)
        with self.assertRaises(RuntimeError):
            adapter.finish(actuator_advanced=False)
        self.assertEqual(len(world.idles), 1)
        adapter.open(1)
        world.advance_idle(expected_tick=1)  # unexpected external mutation
        with self.assertRaises(RuntimeError):
            adapter.finish(actuator_advanced=False)
        self.assertEqual((world.current_tick, len(world.idles)), (2, 2))
        self.assertTrue(adapter.blocked)

    def test_idle_failure_after_advance_is_not_retried(self):
        s = self.session(sensing=False, failure='idle')
        with self.assertRaises(RuntimeError):
            s.run()
        self.assertEqual((s.heart.tick, s.components.world.current_tick), (0, 1))
        self.assertEqual(len(s.components.world.idles), 1)
        self.assertEqual(s.components.world.applies, [])
        self.assertTrue(s.stop_report().synchronization_blocked)
        s.run()
        self.assertEqual(len(s.components.world.idles), 1)

    def test_world_idle_boundary_validation_preserves_physical_state(self):
        world = World(self.events)
        position = world.hidden_position
        world.advance_idle(expected_tick=0)
        self.assertEqual((world.current_tick, world.hidden_position), (1, position))
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises((TypeError, ValueError)):
                world.advance_idle(expected_tick=invalid)
        self.assertEqual((world.current_tick, world.hidden_position), (1, position))

    def test_sensor_identity_replay_and_wrong_tick_rejected(self):
        for case in ('identity', 'tick'):
            s = self.session(empty=True)
            s.start()
            first = s.step()
            snapshot = s.components.world.samples[0]
            s.sensor = lambda tick: replace(snapshot,
                active_tick=tick if case == 'identity' else tick + 1)
            with self.assertRaises(ValueError):
                s.step()
            self.assertIs(s.components.context_manager.current_external_sensory_window, first.observation)
            self.assertEqual(first.observation.end_tick, 0)
            self.assertEqual(len(s.components.world.idles), 1)
            self.assertEqual(len(s.components.retriever.calls), 1)

    def test_stop_inflight_diagnostic_and_uncaught_coordinator_failure(self):
        s = self.session()
        base = s.components.coordinator.execute
        reports = []
        def interrupted(request, **kwargs):
            reports.append(s.stop())
            raise RuntimeError('unknown execution boundary')
        s.components.coordinator.execute = interrupted
        with self.assertRaises(RuntimeError):
            s.run()
        self.assertTrue(reports[0].in_flight)
        self.assertTrue(s.stop_report().in_flight)
        self.assertTrue(s.stop_report().synchronization_blocked)
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(s.components.world.idles, [])
        s.components.coordinator.execute = base
        s.run()
        self.assertEqual(s.components.world.applies, [])

    def test_pause_during_sample_closes_admission_at_safe_boundary(self):
        s = self.session(ticks=3)
        def sensor(tick):
            result = s.components.world.snapshot()
            s.pause()
            return result
        s.sensor = sensor
        s.run()
        self.assertEqual(s.heart.state, HeartState.PAUSED)
        self.assertEqual((s.heart.tick, s.components.world.current_tick), (1, 1))
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(s.components.retriever.calls, [])
        self.assertIsNone(s.step())

    def test_heart_manual_pacing_budget_and_terminal_lifecycle(self):
        class Clock:
            now = 0.
            def clock(self):
                return self.now
            def sleep(self, duration):
                self.now += duration
        clock = Clock()
        heart = Heart(max_ticks=3, initial_tick=7)
        seen = []
        heart.run(seen.append, paced=True, interval=.02, clock=clock.clock, sleep=clock.sleep)
        self.assertEqual(seen, [7, 8, 9])
        self.assertAlmostEqual(clock.now, .04)
        self.assertEqual((heart.tick, heart.state), (10, HeartState.STOPPED))
        heart.run(seen.append)
        self.assertEqual(seen, [7, 8, 9])
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                Heart(max_ticks=invalid)
        heart = Heart(max_ticks=1)
        heart.run(lambda tick: heart.pause())
        self.assertEqual(heart.state, HeartState.STOPPED)
        heart.resume()
        self.assertFalse(heart.step(seen.append))

    def test_paced_pause_resume_has_no_catchup_or_extra_tick(self):
        now = [0.]
        heart = Heart(max_ticks=3)
        seen = []
        def sleep(duration):
            now[0] += duration
            heart.pause()
        heart.run(seen.append, paced=True, interval=.02, clock=lambda: now[0], sleep=sleep)
        self.assertEqual(seen, [0])
        self.assertEqual(heart.state, HeartState.PAUSED)
        now[0] = 1000.
        heart.resume()
        def advance(duration):
            now[0] += duration
        heart.run(seen.append, paced=True, interval=.02, clock=lambda: now[0], sleep=advance)
        self.assertEqual(seen, [0, 1, 2])
        self.assertAlmostEqual(now[0], 1000.02)

    def test_manual_and_paced_sessions_have_same_model_trace(self):
        manual = self.session(ticks=4)
        paced = self.session(ticks=4)
        manual.start()
        while manual.step() is not None:
            pass
        now = [0.]
        def sleep(duration):
            now[0] += duration
        paced.run(paced=True, interval=.03, clock=lambda: now[0], sleep=sleep)
        def trace(s):
            return [(r.tick, r.observation.end_tick, r.observation.frames[0].values,
                     r.execution.status if r.execution else None, r.advancement,
                     r.recent.observation_tick if r.recent else None) for r in s.records]
        self.assertEqual(trace(manual), trace(paced))
        for s in (manual, paced):
            self.assertEqual((s.heart.tick, s.components.world.current_tick), (4, 4))
            self.assertEqual((len(s.components.world.applies), len(s.components.world.idles)), (3, 1))
            self.assertIsNone(s.stop_report().pending)
            self.assertEqual(s.stop_report().unresolved_occurrences, ())
            self.assertEqual(len(s.components.short_memory), 3)
            s.run()
            self.assertEqual(len(s.components.world.applies), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
