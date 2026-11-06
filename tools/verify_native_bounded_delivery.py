"""RND-014 effect-based verifier. All writable fixtures use TemporaryDirectory."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

from verify_native_heart_b2 import B2Tests, inventory
from clc.patterns import PatternOrigin
from clc.runtime.heart import HeartState
from clc.runtime.native_bounded_delivery import (
    BoundedNativeDelivery, Control, DeliveryLimits, NativeDeliverySession, Port,
)
from clc.transduction import VisualFieldSnapshot, VisualFieldTransducer


class DeliveryTests(unittest.TestCase):
    setUp = B2Tests.setUp

    @classmethod
    def setUpClass(cls):
        cls.original = inventory()

    @classmethod
    def tearDownClass(cls):
        if inventory() != cls.original:
            raise AssertionError('production Memory inventory/SHA-256 changed')

    def session(self, *, limits=DeliveryLimits(), ingress=None, sample_enabled=None, **opts):
        base = B2Tests.session(self, **opts)
        return NativeDeliverySession(base.components, max_ticks=base.heart.max_ticks,
                                     limits=limits, ingress=ingress, sample_enabled=sample_enabled)

    def snapshot(self, identity=0, tick=0):
        return VisualFieldSnapshot((1, 4), (1., 0., 0., 0.), tick, identity)

    def test_same_tick_fifo_independent_sources_and_equal_values(self):
        accepted = []
        def ingress(tick, port):
            for source, stream in [('A', 'x'), ('A', 'x'), ('B', 'x'), ('A', 'y')]:
                accepted.append(port.accept(self.snapshot(), source_id=source, stream_id=stream,
                                            source_sequence=7, source_timestamp=2.5).event)
        s = self.session(empty=True, ticks=1, ingress=ingress)
        s.run()
        delivered = [x.event for x in s.delivery.journal if x.stage == 'delivered']
        optional = [e for e in delivered if e.source_id != s.delivery.VISUAL_SOURCE]
        self.assertEqual(optional, accepted)
        self.assertEqual(len({e.delivery_event_id for e in delivered}), 5)
        self.assertEqual({e.admission_tick for e in delivered}, {0})
        self.assertEqual([e.admission_order for e in accepted], [1, 2, 3, 4])
        self.assertEqual(len({e.payload.values for e in accepted}), 1)
        self.assertEqual(len(s.components.retriever.calls), 1)
        self.assertEqual(len(s.components.world.idles), 1)
        self.assertEqual(s.components.world.applies, [])

    def test_nfp_provenance_origin_topology_and_identity_unchanged(self):
        original = VisualFieldTransducer().transduce(self.snapshot(17), frame_id='source-frame')
        internal = replace(original, frame_id='internal', origin=PatternOrigin.INTERNAL_REACTIVATION)
        accepted = []
        def ingress(tick, d):
            for payload in (original, internal):
                accepted.append(d.accept(payload, source_id='other', stream_id='frames').event)
        s = self.session(empty=True, ticks=1, ingress=ingress)
        s.run()
        for event, frame in zip(accepted, (original, internal)):
            self.assertIs(event.payload, frame)
            self.assertEqual(event.native_refs, (frame.frame_id, frame.provenance_ref))
            self.assertEqual(frame.active_tick, 0)
        self.assertEqual(internal.origin, PatternOrigin.INTERNAL_REACTIVATION)
        present = s.components.context_manager.current_external_sensory_window.frames[0]
        self.assertIsNot(present, original)
        self.assertIsNot(present, internal)
        self.assertEqual(present.origin, PatternOrigin.EXTERNAL_SENSORY)
        self.assertEqual(original.provenance_ref, 'sensor_snapshot:000017')
        self.assertEqual(len(s.components.retriever.calls), 1)

    def test_queue_capacity_dispatch_budget_and_explicit_overflow(self):
        results = []
        def ingress(tick, d):
            if tick == 0:
                results.extend(d.accept(self.snapshot(i), source_id='noise', stream_id='x')
                               for i in range(10))
        limits = DeliveryLimits(sensory_capacity=3, dispatch_budget=2, journal_capacity=100)
        s = self.session(empty=True, ticks=3, limits=limits, ingress=ingress)
        s.start()
        s.step()
        self.assertEqual([r.status for r in results], ['accepted'] * 3 + ['overflow'] * 7)
        self.assertEqual(s.delivery.depths, (2, 0, 0))
        self.assertEqual(sum(x.stage == 'delivered' for x in s.delivery.journal), 2)
        s.run()
        self.assertEqual(s.delivery.depths, (0, 0, 0))
        self.assertEqual(s.delivery.counts['rejected'], 7)
        self.assertEqual([x.event for x in s.delivery.journal if x.detail == 'observer_only'],
                         [r.event for r in results[:3]])
        self.assertEqual(len(s.components.world.idles), 3)
        self.assertEqual(len(s.components.retriever.calls), 3)

    def test_noise_flood_cannot_starve_pending_or_perform_second_apply(self):
        def ingress(tick, d):
            for i in range(100):
                d.accept(self.snapshot(i, tick), source_id='noise', stream_id='x')
        s = self.session(ticks=3, ingress=ingress,
                         limits=DeliveryLimits(sensory_capacity=2, dispatch_budget=2, journal_capacity=400))
        s.run()
        c = s.components
        self.assertEqual(len(c.world.applies), 3)
        self.assertEqual(c.world.idles, [])
        self.assertEqual((s.heart.tick, c.world.current_tick, c.world.hidden_position), (3, 3, (0, 3)))
        for index in (1, 2):
            previous, record = s.records[index - 1:index + 1]
            self.assertEqual(record.recent.execution_occurrence_id, previous.execution.execution_occurrence_id)
            self.assertLess(self.events.index(('remember', index)), self.events.index(('apply', index)))
        causal = [x.event for x in s.delivery.journal if x.stage == 'causal_observed']
        self.assertEqual(len(causal), 2)
        self.assertTrue(all(e.port is Port.CONSEQUENCE for e in causal))
        self.assertEqual(causal[-1].execution_occurrence_id, s.records[1].execution.execution_occurrence_id)
        self.assertGreater(s.delivery.counts['rejected'], 290)

    def test_foreign_T1_and_forged_source_cannot_complete_pending(self):
        results = []
        def ingress(tick, d):
            if tick == 1:
                results.append(d.accept(self.snapshot(99, 1), source_id='foreign', stream_id='visual'))
                results.append(d.accept(self.snapshot(98, 1), source_id=d.VISUAL_SOURCE, stream_id=d.VISUAL_STREAM))
        s = self.session(ticks=3, ingress=ingress, sample_enabled=lambda t: t == 0)
        s.start()
        first = s.step()
        pending = s.components.context_manager.pending_causal_transition
        s.step()
        self.assertEqual([r.status for r in results], ['accepted', 'reserved_source'])
        self.assertIs(s.components.context_manager.pending_causal_transition, pending)
        self.assertIs(s.components.context_manager.current_external_sensory_window, first.observation)
        self.assertEqual(len(s.components.short_memory), 0)
        self.assertEqual(len(s.components.retriever.calls), 1)
        self.assertEqual(len(s.components.world.applies), 1)
        s.step()
        self.assertIs(s.records[2].expired, pending)
        self.assertEqual((s.components.world.current_tick, len(s.components.world.idles)), (3, 2))

    def test_stale_late_optional_snapshot_never_relabelled_or_retrieved(self):
        old = self.snapshot(91, 0)
        def ingress(tick, d):
            if tick:
                d.accept(old, source_id='late', stream_id='x')
        s = self.session(empty=True, ticks=3, ingress=ingress, sample_enabled=lambda t: t == 0)
        s.run()
        self.assertEqual(old.active_tick, 0)
        self.assertEqual(s.components.context_manager.current_external_sensory_window.end_tick, 0)
        self.assertEqual(len(s.components.retriever.calls), 1)
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(len(s.components.world.idles), 3)

    def test_missing_authoritative_T1_expires_then_future_sample_is_new_present(self):
        s = self.session(ticks=4, sample_enabled=lambda t: t != 1)
        s.run()
        self.assertIsNone(s.records[1].observation)
        self.assertIsNone(s.records[2].observation)
        self.assertIsNotNone(s.records[2].expired)
        self.assertEqual(s.records[3].observation.end_tick, 3)
        self.assertIsNone(s.records[3].recent)
        self.assertEqual(len(s.components.short_memory), 0)
        self.assertEqual(len(s.components.world.applies), 2)
        self.assertEqual(len(s.components.world.idles), 2)

    def test_required_slot_failure_blocks_new_action_without_retry(self):
        s = self.session(ticks=4)
        s.start()
        s.step()
        original_pending = s.components.context_manager.pending_causal_transition
        reserve = s.delivery._reserve_visual
        def fail(snapshot, pending):
            # A real undelivered sample occupies the protected slot. No invented
            # occurrence/source is used; the second enqueue must fail closed.
            reserve(snapshot, pending)
            return reserve(snapshot, pending)
        s.delivery._reserve_visual = fail
        second = s.step()
        self.assertIsNone(second.observation)
        self.assertIs(s.components.context_manager.pending_causal_transition, original_pending)
        self.assertEqual(s.heart.state, HeartState.STOPPED)
        self.assertEqual(s.delivery.counts['required_failure'], 1)
        self.assertIn('required_delivery_failed', s.heart.diagnostic)
        self.assertEqual((len(s.components.world.applies), len(s.components.world.idles)), (1, 1))
        self.assertEqual(s.components.world.current_tick, 2)
        self.assertEqual(s.delivery.depths, (0, 0, 0))
        s.run()
        self.assertIsNone(s.step())
        self.assertEqual(len(s.components.world.applies), 1)

    def test_pause_control_and_resume_do_not_execute_queued_payloads(self):
        def ingress(tick, d):
            for i in range(5):
                d.accept(self.snapshot(i, tick), source_id='noise', stream_id='x')
            if tick == 0:
                d.accept(Control.PAUSE, source_id='operator', stream_id='lifecycle')
        s = self.session(ticks=3, ingress=ingress, limits=DeliveryLimits(dispatch_budget=2))
        s.run()
        self.assertEqual(s.heart.state, HeartState.PAUSED)
        self.assertEqual((s.heart.tick, s.components.world.current_tick), (1, 1))
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(s.components.retriever.calls, [])
        self.assertEqual(s.delivery.depths, (5, 0, 0))
        s.stop()
        self.assertEqual(s.delivery.depths, (0, 0, 0))
        s.resume()
        s.run()
        self.assertIsNone(s.step())
        self.assertEqual(s.components.world.applies, [])

    def test_stop_control_and_diagnostic_markers_confer_no_action_authority(self):
        def ingress(tick, d):
            for marker in (Control.TICK, Control.OVERLOAD, Control.DELIVERY_FAILURE, Control.STOP):
                d.accept(marker, source_id='operator', stream_id='lifecycle')
        s = self.session(ticks=5, empty=True, ingress=ingress)
        s.run()
        self.assertEqual(s.heart.tick, 4)
        self.assertEqual(s.components.world.current_tick, 4)
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(len(s.components.short_memory), 0)
        self.assertEqual(s.delivery.depths, (0, 0, 0))
        self.assertGreater(s.delivery.counts['rejected'], 0)  # control backlog overflow
        self.assertGreater(s.delivery.counts['cancelled'], 0)
        self.assertEqual(s.delivery.accept(self.snapshot(), source_id='x', stream_id='x').status, 'port_not_open')
        s.run()
        self.assertEqual(s.components.world.current_tick, 4)

    def test_real_pending_serviced_before_pause_blocks_next_action(self):
        def ingress(tick, d):
            if tick == 1:
                d.accept(Control.PAUSE, source_id='operator', stream_id='life')
        s = self.session(ticks=3, ingress=ingress)
        s.run()
        self.assertEqual(s.heart.state, HeartState.PAUSED)
        self.assertEqual(len(s.components.short_memory), 1)
        self.assertIsNone(s.components.context_manager.pending_causal_transition)
        self.assertEqual((len(s.components.world.applies), len(s.components.world.idles)), (1, 1))
        self.assertEqual(len(s.components.retriever.calls), 1)
        s.resume()
        s.run()
        self.assertEqual(len(s.components.world.applies), 2)
        self.assertEqual(s.components.world.current_tick, 3)

    def test_bounded_long_run_journal_queues_and_bookkeeping(self):
        def ingress(tick, d):
            for i in range(20):
                d.accept(self.snapshot(i, tick), source_id=f'noise-{tick}', stream_id='x')
        s = self.session(empty=True, ticks=600, ingress=ingress,
                         limits=DeliveryLimits(sensory_capacity=3, dispatch_budget=2, journal_capacity=7))
        s.start()
        for _ in range(600):
            s.step()
            self.assertLessEqual(s.delivery.depths[0], 3)
            self.assertLessEqual(len(s.delivery.journal), 7)
            self.assertLessEqual(len(s.delivery.counts), 10)
            self.assertLessEqual(len(s._seen_snapshots), s.heart.max_ticks)
        self.assertEqual((s.heart.tick, s.components.world.current_tick), (600, 600))
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(len(s.records), 600)  # existing B2 finite session budget
        self.assertEqual(s.delivery.depths, (0, 0, 0))
        self.assertGreater(s.delivery.counts['rejected'], 11000)
        self.assertFalse(hasattr(s.delivery, 'seen_ids'))

    def test_limits_validation_payload_cap_and_closed_admission(self):
        for kwargs in ({'dispatch_budget': 1}, {'sensory_capacity': 0}, {'journal_capacity': True}):
            with self.assertRaises(ValueError):
                DeliveryLimits(**kwargs)
        d = BoundedNativeDelivery('test', DeliveryLimits(max_values=1))
        self.assertEqual(d.accept(self.snapshot(), source_id='x', stream_id='x').status, 'port_not_open')
        d._begin(0)
        self.assertEqual(d.accept(self.snapshot(), source_id='x', stream_id='x').status, 'payload_limit')
        d._end()
        self.assertEqual(d.depths, (0, 0, 0))
        s = self.session(limits=DeliveryLimits(max_values=1), ticks=3)
        s.run()
        self.assertEqual(s.heart.state, HeartState.STOPPED)
        self.assertEqual(len(s.components.world.applies), 0)
        self.assertEqual(len(s.components.world.idles), 1)
        self.assertEqual(s.components.retriever.calls, [])

    def test_queued_action_frame_is_observer_data_and_never_reexecuted(self):
        s = self.session(ticks=4, limits=DeliveryLimits(dispatch_budget=2))
        s.start()
        first = s.step()
        action = first.execution.action_frame
        def ingress(tick, d):
            for _ in range(3):
                d.accept(action, source_id='action-telemetry', stream_id='frames')
            d.accept(Control.STOP, source_id='operator', stream_id='life')
        s.ingress = ingress
        second = s.step()
        self.assertIsNotNone(second.recent)
        self.assertIsNone(second.execution)
        self.assertEqual(action.active_tick, 0)
        self.assertEqual(len(s.components.world.applies), 1)
        self.assertEqual(s.delivery.counts['cancelled'], 3)
        self.assertEqual(s.delivery.depths, (0, 0, 0))
        s.resume()
        s.run()
        self.assertEqual(len(s.components.world.applies), 1)
        self.assertEqual(s.components.world.current_tick, 2)

    def test_pending_from_another_session_cannot_acquire_source_binding(self):
        base = B2Tests.session(self)
        base.start()
        base.step()
        pending = base.components.context_manager.pending_causal_transition
        with self.assertRaises(ValueError):
            NativeDeliverySession(base.components, max_ticks=2, initial_tick=1)
        self.assertIs(base.components.context_manager.pending_causal_transition, pending)
        self.assertEqual(len(base.components.world.applies), 1)

    def test_stream_cannot_overtake_itself_by_changing_port(self):
        results = []
        def ingress(tick, d):
            results.append(d.accept(self.snapshot(), source_id='x', stream_id='same'))
            results.append(d.accept(Control.STOP, source_id='x', stream_id='same'))
        s = self.session(empty=True, ticks=1, ingress=ingress)
        s.run()
        self.assertEqual([r.status for r in results], ['accepted', 'stream_port_conflict'])
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(len(s.components.world.idles), 1)

    def test_manual_sensor_exception_cancels_backlog_and_never_retries(self):
        def ingress(tick, d):
            d.accept(self.snapshot(), source_id='x', stream_id='same')
            raise RuntimeError('producer failed')
        s = self.session(ingress=ingress)
        s.start()
        with self.assertRaises(RuntimeError):
            s.step()
        self.assertEqual(s.heart.state, HeartState.STOPPED)
        self.assertEqual(s.delivery.depths, (0, 0, 0))
        self.assertEqual(s.delivery.counts['cancelled'], 1)
        self.assertEqual(s.delivery.counts['delivery_failure'], 1)
        self.assertIsNone(s.step())
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(s.components.world.idles, [])

    def test_world_failure_not_retried_and_direct_source_bad_tick_not_relabelled(self):
        s = self.session(failure='after')
        s.run()
        self.assertTrue(s.stop_report().synchronization_blocked)
        self.assertEqual(len(s.components.world.applies), 1)
        self.assertEqual(s.components.world.idles, [])
        s.run()
        self.assertEqual(len(s.components.world.applies), 1)
        s = self.session()
        s.components.world.snapshot = lambda: self.snapshot(10, 9)
        s.run()
        self.assertEqual(s.heart.state, HeartState.STOPPED)
        self.assertEqual(s.delivery.counts['required_failure'], 1)
        self.assertEqual(s.components.retriever.calls, [])
        self.assertIsNone(s.components.context_manager.current_external_sensory_window)
        self.assertEqual(s.components.world.applies, [])


if __name__ == '__main__':
    # Imported fixtures are reused, but this entry point runs only RND-014 tests.
    unittest.main(defaultTest='DeliveryTests', verbosity=2)
