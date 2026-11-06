"""RND-017 production session behavior, temporary writable fixtures only."""
from pathlib import Path
import sys
import unittest
from dataclasses import replace, FrozenInstanceError, fields

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_native_heart_b2 as b2
from tools.verify_echo_expectations import window
from clc.internal.multitick import MultiTickComparison, WorkLimits
from clc.patterns import NFPWindow, PatternOrigin
from clc.patterns.similarity import NFPWindowSimilarity
from clc.runtime.native_heart_session import NativeHeartSession


class WorkTests(b2.B2Tests):
    # Reuse fixture construction, not inherited B2 test cases (loaded below).
    def make(self, ticks=8, cells=1, sensing=False):
        base = self.session(empty=True, ticks=ticks, sensing=sensing)
        return NativeHeartSession(base.components, max_ticks=ticks, sensor=base.sensor,
                                  internal_work_limits=WorkLimits(cells, 8))

    def submit(self, s):
        return s.submit_internal_comparison(window(0, (1., .5, 0., 1.)),
                                            window(0, (0., .5, 1., 0.)))

    def test_multitick_actual_computation(self):
        s = self.make()
        entry = self.submit(s)
        s.start()
        for expected in (1., 1., 2.):
            s.step()
            snap = s.internal_work_snapshot()
            self.assertEqual(snap.state, 'running')
            self.assertEqual(snap.distance, expected)
            self.assertIsNone(snap.result)
        s.step()
        result = s.internal_work_snapshot().result
        self.assertEqual(result.process_id, entry.process_id)
        self.assertEqual(result.origin.value, 'internal_state')
        self.assertEqual(result.source_window_ids, entry.source_window_ids)
        self.assertEqual(result.score, NFPWindowSimilarity.compare(
            window(0, (1., .5, 0., 1.)), window(0, (0., .5, 1., 0.))).score)
        self.assertEqual((s.heart.tick, s.components.world.current_tick), (4, 4))
        self.assertEqual(len(s.components.world.idles), 4)
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(s.components.retriever.calls, [])
        s.step()
        self.assertIs(s.internal_work_snapshot().result, result)

    def test_pause_resume(self):
        s = self.make(); self.submit(s); s.start(); s.step(); s.pause()
        before = s.internal_work_snapshot()
        self.assertIsNone(s.step())
        self.assertIs(s.internal_work_snapshot(), before)
        s.resume(); s.step()
        self.assertEqual(s.internal_work_snapshot().processed_cells, 2)
        s.run()
        self.assertEqual(s.internal_work_snapshot().state, 'completed')

    def test_stop_and_budget_release_inputs(self):
        for run in (False, True):
            s = self.make(ticks=2); self.submit(s)
            if run:
                s.run()
            else:
                s.start(); s.step(); s.stop()
            self.assertEqual(s.internal_work_snapshot().state, 'cancelled')
            self.assertIsNone(s._internal_work._inputs)
            before = s.internal_work_snapshot()
            s.run(); s.step(); s.resume()
            self.assertIs(s.internal_work_snapshot(), before)
            with self.assertRaises(ValueError): self.submit(s)

    def test_cancel_capacity_and_release(self):
        s = self.make(); self.submit(s)
        with self.assertRaises(ValueError): self.submit(s)
        with self.assertRaises(ValueError): s.release_internal_work()
        s.cancel_internal_work(); s.cancel_internal_work()
        self.assertEqual(s.internal_work_snapshot().state, 'cancelled')
        with self.assertRaises(ValueError): self.submit(s)
        s.release_internal_work(); self.submit(s); s.run()
        self.assertEqual(s.internal_work_snapshot().state, 'completed')

    def test_limits_invalid_input_and_replay(self):
        for n in (0, -1, True, 1.5):
            with self.assertRaises(ValueError): WorkLimits(n, 8)
        s = self.make()
        for right in (window(1), window(0, (1.,)), 'legacy'):
            with self.assertRaises((ValueError, TypeError)):
                s.submit_internal_comparison(window(0), right)
        with self.assertRaises(ValueError):
            s.submit_internal_comparison(window(0, (0.,)*9), window(0, (0.,)*9))
        self.assertIsNone(s.internal_work_snapshot())
        self.submit(s); s.start(); s.step()
        before = s.internal_work_snapshot()
        with self.assertRaises(ValueError): s._internal_work.advance(0)
        self.assertIs(s.internal_work_snapshot(), before)
        s.step(); self.assertEqual(s.internal_work_snapshot().processed_cells, 2)

    def test_failure_isolated_and_no_result(self):
        s = self.make(); self.submit(s); s.start(); s.step()
        s._internal_work._inputs = None  # computation failure injection
        s.step()
        self.assertEqual(s.internal_work_snapshot().state, 'failed')
        self.assertIsNone(s.internal_work_snapshot().result)
        self.assertIsNone(s._internal_work._inputs)
        s.run()
        self.assertEqual((s.heart.tick, s.components.world.current_tick), (8, 8))
        self.assertFalse(s.time_adapter.blocked)

    def test_opt_in_and_in_pulse_submission(self):
        s = self.session(empty=True)
        with self.assertRaises(ValueError): self.submit(s)
        s = self.make(sensing=True)
        original = s.sensor
        def sample(tick):
            with self.assertRaises(ValueError): self.submit(s)
            return original(tick)
        s.sensor = sample
        self.submit(s); s.run()
        self.assertEqual(s.internal_work_snapshot().state, 'completed')
        self.assertEqual(len(s.components.retriever.calls), 8)

    def test_session_failure_cancels(self):
        s = self.make(); self.submit(s)
        def fail(tick): raise RuntimeError('sensor failure')
        s.sensor = fail
        with self.assertRaises(RuntimeError): s.run()
        self.assertEqual(s.internal_work_snapshot().state, 'cancelled')
        self.assertIsNone(s._internal_work._inputs)

    def test_native_actions_and_echo_unchanged(self):
        from clc.echo.expectations import EchoExpectations
        traces = []
        for enabled in (False, True):
            base = self.session(ticks=5)
            echo = EchoExpectations()
            s = NativeHeartSession(base.components, max_ticks=5, sensor=base.sensor,
                                   echo=echo, internal_work_limits=WorkLimits(1, 8) if enabled else None)
            if enabled: self.submit(s)
            records = s.run()
            traces.append([(r.tick, r.advancement, r.execution.status if r.execution else None,
                            r.recent is not None, r.echo_matches) for r in records])
            self.assertEqual(len(s.components.world.applies), 3)
            self.assertEqual(len(s.components.short_memory.snapshot()), 3)
        self.assertEqual(*traces)

    def test_callback_stop_cancels_without_step(self):
        s = self.make()
        self.submit(s)
        def sample(tick):
            s.stop()
            return None
        s.sensor = sample
        s.run()
        self.assertEqual(s.internal_work_snapshot().state, 'cancelled')
        self.assertEqual(s.internal_work_snapshot().processed_cells, 0)
        self.assertEqual((s.heart.tick, s.components.world.current_tick), (1, 1))

    def test_mixed_provenance_survives_completion(self):
        s = self.make()
        # Establish a real session boundary admitting historical frames 0 and 1.
        s.start(); s.step()
        def source(name, origin):
            return NFPWindow(name, tuple(
                replace(window(tick).frames[0], frame_id=f'{name}:frame:{tick}',
                        origin=origin, provenance_ref=f'{name}:provenance:{tick}')
                for tick in (0, 1)
            ), provenance_ref=f'{name}:window-provenance')
        left = source('external', PatternOrigin.EXTERNAL_SENSORY)
        right = source('reactivated', PatternOrigin.INTERNAL_REACTIVATION)
        entry = s.submit_internal_comparison(left, right)
        captured = entry.source_descriptors
        for _ in range(4): s.step()
        terminal = s.internal_work_snapshot()
        self.assertEqual(terminal.state, 'completed')
        self.assertIsNone(s._internal_work._inputs)  # resource release assertion only
        self.assertIs(terminal.source_descriptors, captured)
        self.assertIs(terminal.result.source_descriptors, captured)
        self.assertEqual(terminal.result.source_window_ids, ('external', 'reactivated'))
        self.assertEqual(terminal.result.origin, PatternOrigin.INTERNAL_STATE)
        self.assertIsInstance(captured, tuple)
        for descriptor, original in zip(captured, (left, right)):
            self.assertEqual((descriptor.window_id, descriptor.provenance_ref),
                             (original.window_id, original.provenance_ref))
            self.assertIsInstance(descriptor.frames, tuple)
            self.assertEqual(len(descriptor.frames), original.length)
            self.assertLessEqual(len(descriptor.frames), 8)  # max_cells, topology.size >= 1
            for frame, expected in zip(descriptor.frames, original.frames):
                self.assertEqual((frame.frame_id, frame.origin, frame.active_tick, frame.provenance_ref),
                                 (expected.frame_id, expected.origin, expected.active_tick, expected.provenance_ref))
                self.assertEqual({f.name for f in fields(frame)},
                                 {'frame_id', 'origin', 'active_tick', 'provenance_ref'})
                with self.assertRaises(FrozenInstanceError): frame.origin = PatternOrigin.EXTERNAL_SENSORY
            with self.assertRaises(FrozenInstanceError): descriptor.provenance_ref = 'changed'
            with self.assertRaises(TypeError): descriptor.frames[0] = descriptor.frames[-1]
        with self.assertRaises(FrozenInstanceError): terminal.result.origin = PatternOrigin.EXTERNAL_SENSORY
        s.release_internal_work()
        self.assertIsNone(s.internal_work_snapshot())
        self.assertEqual(captured[1].frames[1].provenance_ref, 'reactivated:provenance:1')
        self.assertTrue(all(r.observation is None and r.execution is None and r.echo_matches == ()
                            for r in s.records))
        self.assertEqual(s.components.retriever.calls, [])
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(s.components.short_memory.snapshot(), ())
        self.assertIsNone(s.components.context_manager.pending_causal_transition)

    def test_fractional_multiframe_partial_final_chunk(self):
        s = self.make(cells=4)
        left = NFPWindow('left', (window(0, (.1, .2, .3)).frames[0],
                                 window(1, (.4, .5, .6)).frames[0]))
        right = NFPWindow('right', (window(0, (.9, .1, .7)).frames[0],
                                   window(1, (.2, .8, .3)).frames[0]))
        s.start(); s.step(); s.submit_internal_comparison(left, right)
        distances = [abs(a-b) for lf, rf in zip(left.frames, right.frames)
                     for a, b in zip(lf.values, rf.values)]
        s.step()
        partial = s.internal_work_snapshot()
        self.assertEqual(partial.processed_cells, 4)
        self.assertAlmostEqual(partial.distance, sum(distances[:4]), delta=1e-12)
        self.assertEqual(partial.state, 'running')
        self.assertIsNone(partial.result)
        s.step()
        terminal = s.internal_work_snapshot()
        self.assertEqual(terminal.processed_cells, 6)
        self.assertAlmostEqual(terminal.distance, sum(distances), delta=1e-12)
        self.assertAlmostEqual(terminal.result.score, NFPWindowSimilarity.compare(left, right).score,
                               delta=1e-12)
        s.step()
        self.assertIs(s.internal_work_snapshot(), terminal)

    def test_nonempty_echo_differential(self):
        from clc.echo.expectations import EchoExpectations
        traces = []
        for enabled in (False, True):
            base = self.session(ticks=6)
            echo = EchoExpectations()
            s = NativeHeartSession(base.components, max_ticks=6, sensor=base.sensor, echo=echo,
                                   internal_work_limits=WorkLimits(1, 8) if enabled else None)
            s.start(); first = s.step()
            echo.expect(first.observation, expected_coordinates=(1,), ttl=3)
            if enabled: s.submit_internal_comparison(first.observation, first.observation)
            # Three ticks with both an unfinished process and a retained expectation.
            for _ in range(3):
                s.step()
                if enabled:
                    self.assertEqual(s.internal_work_snapshot().state, 'running')
                    self.assertIsNone(s.internal_work_snapshot().result)
            s.run()
            if enabled: self.assertEqual(s.internal_work_snapshot().state, 'completed')
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

    def test_multiframe_input(self):
        from clc.patterns import NFPWindow
        s = self.make()
        a = NFPWindow('a', (window(0).frames[0], window(1).frames[0]))
        b = NFPWindow('b', (window(0, (0., 1.)).frames[0], window(1, (.5, .5)).frames[0]))
        s.start(); s.step(); s.submit_internal_comparison(a, b)
        for _ in range(4): s.step()
        self.assertEqual(s.internal_work_snapshot().result.score, NFPWindowSimilarity.compare(a, b).score)


if __name__ == '__main__':
    names = [name for name in WorkTests.__dict__ if name.startswith('test_')]
    suite = unittest.TestSuite(WorkTests(name) for name in names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
