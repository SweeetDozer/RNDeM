"""RND-018 behavioral verification through real session APIs, temp fixtures."""
from pathlib import Path
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_native_heart_b2 as b2
from tools.verify_echo_expectations import window
from clc.internal.admission import AdmissionLimits, AdmissionRejected
from clc.internal.multitick import WorkLimits
from clc.runtime.native_heart_session import NativeHeartSession
from clc.runtime.heart import HeartState
from clc.patterns import NFPWindow, PatternOrigin
from clc.patterns.similarity import NFPWindowSimilarity


class AdmissionTests(b2.B2Tests):
    def make(self, ticks=16, limits=None, sensing=False, actions=False):
        base = self.session(empty=not actions, ticks=ticks, sensing=sensing or actions)
        return NativeHeartSession(base.components, max_ticks=ticks, sensor=base.sensor,
                                  internal_work_limits=WorkLimits(1, 8),
                                  admission_limits=limits or AdmissionLimits())

    def submit(self, s, value=0.):
        return s.submit_comparison_request(window(0, (1., .5, 0., 1.)),
                                           window(0, (value, .5, 1., value)))

    def test_three_real_comparisons_fifo_provenance(self):
        s = self.make(sensing=True)
        ids = [self.submit(s, x).request_id for x in (0., .25, .5)]
        self.assertEqual(sum(r.retained_cells for r in s.comparison_requests()), 24)
        s.start()
        processes = []
        for index in range(3):
            for cell in range(1, 5):
                s.step()
                rs = s.comparison_requests()
                self.assertEqual(rs[index].work.processed_cells, cell)
                self.assertTrue(all(r.work is None and r.state == 'queued' for r in rs[index+1:]))
            r = rs[index]
            self.assertEqual(r.request_id, ids[index])
            self.assertEqual(r.state, 'completed')
            result = r.work.result
            processes.append(result.process_id)
            self.assertEqual(result.origin, PatternOrigin.INTERNAL_STATE)
            self.assertEqual(result.source_descriptors, r.work.source_descriptors)
            self.assertAlmostEqual(result.score, NFPWindowSimilarity.compare(
                window(0, (1., .5, 0., 1.)), window(0, ((0., .25, .5)[index], .5, 1., (0., .25, .5)[index]))).score)
            self.assertIsNone(s.internal_work_snapshot())
        self.assertEqual(len(set(processes)), 3)
        self.assertEqual((s.heart.tick, s.components.world.current_tick), (12, 12))
        self.assertEqual(len(s.components.retriever.calls), 12)
        self.assertEqual(len(s.components.world.idles), 12)
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(s.components.short_memory.snapshot(), ())
        before = s.comparison_requests(); s.step()
        self.assertEqual(before, s.comparison_requests())

    def test_queue_overflow(self):
        s = self.make(limits=AdmissionLimits(max_pending=2))
        self.submit(s); self.submit(s)
        with self.assertRaisesRegex(AdmissionRejected, 'pending'): self.submit(s)
        s.start(); s.step(); self.submit(s)
        self.assertEqual(len(s.comparison_requests()), 3)

    def test_aggregate_budget(self):
        s = self.make(limits=AdmissionLimits(max_retained_cells=15))
        self.submit(s)
        with self.assertRaisesRegex(AdmissionRejected, 'coordinate'): self.submit(s)
        s.start(); s.step()
        with self.assertRaises(AdmissionRejected): self.submit(s)
        s.cancel_comparison_request(s.comparison_requests()[0].request_id)
        self.submit(s)

    def test_outcomes_backpressure_release(self):
        s = self.make(limits=AdmissionLimits(max_requests=2))
        a = self.submit(s); b = self.submit(s)
        s.start()
        for _ in range(8): s.step()
        before = s.comparison_requests()
        with self.assertRaisesRegex(AdmissionRejected, 'outcome'): self.submit(s)
        self.assertEqual(before, s.comparison_requests())
        s.cancel_comparison_request(a.request_id)
        self.assertEqual(before, s.comparison_requests())
        s.release_comparison_request(a.request_id)
        with self.assertRaises(KeyError): s.release_comparison_request(a.request_id)
        self.submit(s)
        self.assertEqual(s.comparison_requests()[0].request_id, b.request_id)

    def test_invalid_inputs_and_limits(self):
        for n in (True, 0, -1, 1.5):
            for name in ('max_pending', 'max_requests', 'max_retained_cells'):
                with self.assertRaises(ValueError): AdmissionLimits(**{name:n})
        s = self.make()
        for a,b in [('bad',window(0)), (window(0),window(1)),
                    (window(0),window(0,(1.,))), (window(0,(0.,)*9),window(0,(0.,)*9))]:
            with self.assertRaises((TypeError, ValueError)): s.submit_comparison_request(a,b)
        self.assertEqual(s.comparison_requests(), ())

    def test_cancel_queued_active_no_reexecution(self):
        s = self.make(); a = self.submit(s); b = self.submit(s); c = self.submit(s)
        with self.assertRaises(ValueError): s.release_comparison_request(a.request_id)
        s.cancel_comparison_request(b.request_id)
        s.start(); s.step()
        self.assertEqual(s.cancel_comparison_request(a.request_id).work.processed_cells, 1)
        s.cancel_comparison_request(a.request_id)
        s.step()
        self.assertEqual([r.state for r in s.comparison_requests()], ['cancelled','cancelled','running'])
        self.assertEqual(s.comparison_requests()[2].work.processed_cells, 1)
        self.assertIsNone(s.comparison_requests()[1].work)

    def test_pause_resume(self):
        s = self.make(); self.submit(s); self.submit(s)
        s.start(); s.step(); s.pause(); before=s.comparison_requests()
        s.step(); self.assertEqual(s.comparison_requests(), before)
        self.submit(s); s.resume(); s.step()
        self.assertEqual(s.comparison_requests()[0].work.processed_cells, 2)
        s.run(); self.assertTrue(all(r.state=='completed' for r in s.comparison_requests()))

    def test_stop_and_tick_exhaustion(self):
        for mode in ('ready','active','budget','callback'):
            s=self.make(ticks=2); self.submit(s); self.submit(s)
            if mode=='active': s.start(); s.step(); s.stop()
            elif mode=='ready': s.stop()
            elif mode=='callback': s.sensor=lambda tick: s.stop() and None; s.run()
            else: s.run()
            self.assertEqual(s.heart.state, HeartState.STOPPED)
            self.assertTrue(all(r.state=='cancelled' and r.retained_cells==0 for r in s.comparison_requests()))
            self.assertIsNone(s.internal_work_snapshot())
            with self.assertRaises(ValueError): self.submit(s)

    def test_failure_isolated_next_executes(self):
        s=self.make(); self.submit(s); self.submit(s); s.start(); s.step()
        s._internal_work._inputs=None  # controlled computation fault
        s.step(); self.assertEqual(s.comparison_requests()[0].state,'failed')
        self.assertEqual(s.comparison_requests()[0].work.diagnostic,'TypeError')
        s.run(); self.assertEqual(s.comparison_requests()[1].state,'completed')
        self.assertEqual(s.components.world.current_tick,16)
        self.assertFalse(s.time_adapter.blocked)

    def test_session_failure_cleanup(self):
        s=self.make(); self.submit(s); self.submit(s)
        def fail(tick): raise RuntimeError('sensor fault')
        s.sensor=fail
        with self.assertRaises(RuntimeError): s.run()
        self.assertTrue(all(r.state=='cancelled' for r in s.comparison_requests()))

    def test_guards_inside_pulse_and_slot_ownership(self):
        s=self.make(); a=self.submit(s)
        def sensor(tick):
            for op in (lambda:self.submit(s), lambda:s.cancel_comparison_request(a.request_id),
                       lambda:s.release_comparison_request(a.request_id),
                       lambda:s.submit_internal_comparison(window(0),window(0))):
                with self.assertRaises(ValueError): op()
        s.sensor=sensor
        for op in (s.cancel_internal_work,s.release_internal_work):
            with self.assertRaises(ValueError): op()
        s.run(); self.assertEqual(s.comparison_requests()[0].state,'completed')

    def test_mixed_origin_descriptors_survive_release(self):
        s=self.make()
        left=window(0)
        right=NFPWindow('internal', (replace(left.frames[0],frame_id='reactivated',
                        origin=PatternOrigin.INTERNAL_REACTIVATION,provenance_ref='source'),))
        request=s.submit_comparison_request(left,right); s.run()
        outcome=s.comparison_requests()[0]; result=outcome.work.result
        self.assertEqual(result.source_descriptors[1].frames[0].origin,PatternOrigin.INTERNAL_REACTIVATION)
        self.assertEqual(result.source_descriptors[1].frames[0].provenance_ref,'source')
        s.release_comparison_request(request.request_id)
        self.assertEqual(result.origin,PatternOrigin.INTERNAL_STATE)
        self.assertEqual(s.comparison_requests(),())

    def test_native_actions_short_memory_echo_differential(self):
        from clc.echo.expectations import EchoExpectations
        traces=[]
        for enabled in (False,True):
            base=self.session(ticks=8)
            s=NativeHeartSession(base.components,max_ticks=8,sensor=base.sensor,echo=EchoExpectations(),
                internal_work_limits=WorkLimits(1,8) if enabled else None,
                admission_limits=AdmissionLimits() if enabled else None)
            if enabled:
                for x in (0.,.25,.5): self.submit(s,x)
            records=s.run()
            traces.append(([(r.tick,r.advancement,r.execution.status if r.execution else None,
                             r.recent is not None,r.echo_matches) for r in records],
                           len(s.components.world.applies),len(s.components.short_memory.snapshot())))
        self.assertEqual(*traces)

    def test_pacing_boundary_pause(self):
        s=self.make(); self.submit(s); self.submit(s)
        now=[0.]
        def sleep(delay):
            now[0]+=delay; s.pause()
        s.run(paced=True,clock=lambda:now[0],sleep=sleep)
        self.assertEqual(s.heart.state,HeartState.PAUSED)
        self.assertEqual(s.comparison_requests()[0].work.processed_cells,1)
        s.resume(); s.run(); self.assertTrue(all(r.state=='completed' for r in s.comparison_requests()))

    def test_nonempty_echo_differential(self):
        from clc.echo.expectations import EchoExpectations
        traces = []
        for enabled in (False, True):
            base = self.session(ticks=6)
            echo = EchoExpectations()
            s = NativeHeartSession(base.components, max_ticks=6, sensor=base.sensor, echo=echo,
                                   internal_work_limits=WorkLimits(1, 8) if enabled else None,
                                   admission_limits=AdmissionLimits() if enabled else None)
            s.start(); first = s.step()
            echo.expect(first.observation, expected_coordinates=(1,), ttl=3)
            if enabled:
                for _ in range(3): s.submit_comparison_request(first.observation, first.observation)
            # Three ticks with both an unfinished process and a retained expectation.
            for _ in range(3):
                s.step()
                if enabled:
                    self.assertEqual(s.internal_work_snapshot().state, 'running')
                    self.assertIsNone(s.internal_work_snapshot().result)
            s.run()
            if enabled: self.assertEqual([r.state for r in s.comparison_requests()],
                                         ['completed', 'cancelled', 'cancelled'])
            c = s.components
            traces.append((
                [(r.tick, r.advancement, r.execution.status if r.execution else None,
                  r.recent is not None, tuple(replace(m, source_window_id='source',
                      observation_id='observation' if m.observation_id is not None else None)
                      for m in r.echo_matches)) for r in s.records],
                [(before, signal.values) for before, signal in c.world.applies],
                c.world.idles, (s.heart.tick, c.world.current_tick, c.world.hidden_position),
                [(r.before_sensory_window.frames[0].values, r.after_sensory_window.frames[0].values)
                 for r in c.short_memory.snapshot()],
                echo.snapshot(),
            ))
            self.assertTrue(any(r.echo_matches for r in s.records))
            for record in s.records:
                for match in record.echo_matches:
                    self.assertEqual(match.source_window_id, first.observation.window_id)
                    if match.observation_id is not None:
                        self.assertEqual(match.observation_id, record.observation.window_id)
            self.assertEqual(len(c.short_memory.snapshot()), 3)
        self.assertEqual(*traces)


if __name__=='__main__':
    suite=unittest.TestSuite(AdmissionTests(n) for n in AdmissionTests.__dict__ if n.startswith('test_'))
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
