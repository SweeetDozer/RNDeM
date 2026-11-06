"""RND-019 behavioral experiments; observations enter real production session."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_native_heart_b2 as b2
from clc.echo.expectations import EchoExpectations
from clc.echo.candidate_comparison import EchoCandidateComparison
from clc.internal.admission import AdmissionLimits, AdmissionRejected
from clc.internal.multitick import WorkLimits
from clc.patterns import PatternOrigin
from clc.patterns.similarity import NFPWindowSimilarity
from clc.runtime.native_heart_session import NativeHeartSession
from clc.transduction import VisualFieldSnapshot


class IntegrationTests(unittest.TestCase):
    setUpClass = classmethod(b2.B2Tests.setUpClass.__func__)
    tearDownClass = classmethod(b2.B2Tests.tearDownClass.__func__)
    setUp = b2.B2Tests.setUp
    session = b2.B2Tests.session

    def make(self, b=(1., .8, 0., 0.), c=(1., 0., 1., 0.), *, limits=None,
             enabled=True, actions=False, a=(1.,1.,0.,0.)):
        base = self.session(empty=not actions, ticks=24)
        observations = {0:a, 3:b, 4:c}
        s = NativeHeartSession(base.components, max_ticks=24, echo=EchoExpectations(),
            sensor=lambda tick: VisualFieldSnapshot((1,4), observations[tick], tick, tick)
                if tick in observations else None,
            internal_work_limits=WorkLimits(1,8) if enabled else None,
            admission_limits=(limits or AdmissionLimits()) if enabled else None)
        s.start()
        first = s.step()
        entry = s.echo.expect(first.observation, expected_coordinates=(0,), ttl=23)
        s.step(); s.step()
        self.assertEqual([r.echo_matches[0].outcome for r in s.records[1:]], ['no_data']*2)
        s.step(); s.step()
        return s, entry, EchoCandidateComparison(s)

    def finish(self, s, bridge):
        for _ in range(8):
            s.step()
        return bridge.snapshot()

    def test_real_multitick_influence_and_provenance(self):
        for b,c,preferred in [((1.,.8,0.,0.),(1.,0.,1.,0.),0),
                              ((1.,0.,1.,0.),(1.,.8,0.,0.),1)]:
            with self.subTest(preferred=preferred):
                s,e,bridge = self.make(b,c)
                before = s.echo.snapshot()
                initial = bridge.submit(e.expectation_id, (3,4))
                self.assertEqual(initial.state, 'pending')
                self.assertTrue(all(r.state=='queued' and r.work is None for r in initial.requests))
                for cell in range(1,5):
                    s.step(); pending=bridge.snapshot()
                    self.assertEqual(pending.requests[0].work.processed_cells, cell)
                    self.assertEqual(pending.state,'pending')
                    self.assertIsNone(pending.preferred_observation_id)
                    self.assertIsNone(pending.score_delta)
                result = self.finish_half(s,bridge)
                self.assertEqual(result.state,'relative_similarity')
                self.assertEqual(result.preferred_observation_id,result.candidates[preferred].window_id)
                self.assertFalse(result.identity_confirmed)
                self.assertEqual(result.origin,PatternOrigin.INTERNAL_STATE)
                for index, request in enumerate(result.requests):
                    work=request.work; measurement=work.result
                    self.assertEqual(work.process_id,measurement.process_id)
                    self.assertTrue(request.request_id and measurement.result_id)
                    self.assertEqual(measurement.source_descriptors,(result.source,result.candidates[index]))
                    expected=NFPWindowSimilarity.compare(s.records[0].observation,s.records[3+index].observation).score
                    self.assertAlmostEqual(measurement.score,expected)
                    self.assertEqual(measurement.origin,PatternOrigin.INTERNAL_STATE)
                self.assertAlmostEqual(result.score_delta,
                    result.requests[0].work.result.score-result.requests[1].work.result.score)
                self.assertEqual(s.records[0].observation.end_tick,0)
                self.assertEqual((s.heart.tick,s.components.world.current_tick),(13,13))
                self.assertEqual(len(s.components.world.idles),13)
                self.assertEqual(s.components.short_memory.snapshot(),())
                self.assertEqual(s.components.world.applies,[])
                self.assertEqual(s.echo.snapshot()[0].source,before[0].source)
                bridge.release()
                self.assertIsNone(bridge.snapshot())
                self.assertEqual(s.comparison_requests(),())
                self.assertTrue(result.requests[0].work.result.source_descriptors)

    def finish_half(self,s,bridge):
        for _ in range(4): s.step()
        return bridge.snapshot()

    def test_equal_and_numerical_tie(self):
        for difference in (0.,1e-13):
            s,e,bridge=self.make((1.,.8,0.,0.),(1.,.8+difference,0.,0.))
            bridge.submit(e.expectation_id,(3,4)); result=self.finish(s,bridge)
            self.assertEqual(result.state,'indistinguishable')
            self.assertIsNone(result.preferred_observation_id)
            self.assertFalse(result.identity_confirmed)

    def test_perfect_similarity_never_confirms_identity(self):
        s,e,bridge=self.make((1.,1.,0.,0.),(1.,1.,0.,0.))
        bridge.submit(e.expectation_id,(3,4)); result=self.finish(s,bridge)
        self.assertEqual([r.work.result.score for r in result.requests],[1.,1.])
        self.assertTrue(all(m.possible_continuation for m in result.matches))
        self.assertTrue(all(not m.identity_confirmed for m in result.matches))
        self.assertFalse(result.identity_confirmed)
        self.assertEqual(result.state,'indistinguishable')
        self.assertIsNone(result.preferred_observation_id)

    def test_inconclusive_and_observed_absence_remain_uncertain(self):
        for value,outcome in ((.2,'inconclusive'),(0.,'observed_absence')):
            s,e,bridge=self.make(c=(value,0.,1.,0.))
            bridge.submit(e.expectation_id,(3,4)); result=self.finish(s,bridge)
            self.assertEqual(result.matches[1].outcome,outcome)
            self.assertEqual(result.state,'insufficient_data')
            self.assertIsNotNone(result.score_delta)
            self.assertIsNone(result.preferred_observation_id)

    def test_cancel_queued_and_active(self):
        for index in (0,1):
            s,e,bridge=self.make(); bridge.submit(e.expectation_id,(3,4))
            s.step(); req=bridge.snapshot().requests[index]
            s.cancel_comparison_request(req.request_id)
            result=self.finish(s,bridge)
            self.assertEqual(result.state,'insufficient_data')
            self.assertIsNone(result.preferred_observation_id)
            self.assertEqual(result.requests[index].state,'cancelled')
            bridge.release(); self.assertEqual(s.comparison_requests(),())

    def test_failed_measurement_no_retry(self):
        s,e,bridge=self.make(); bridge.submit(e.expectation_id,(3,4))
        s.step(); s._internal_work._inputs=None  # controlled computation fault
        result=self.finish(s,bridge)
        self.assertEqual([r.state for r in result.requests],['failed','completed'])
        self.assertEqual(result.state,'insufficient_data')
        self.assertEqual(result.requests[0].work.processed_cells,1)
        self.assertIsNone(result.preferred_observation_id)
        before=s.comparison_requests(); s.step()
        self.assertEqual(before,s.comparison_requests())

    def test_released_measurement_is_insufficient(self):
        s,e,bridge=self.make(); bridge.submit(e.expectation_id,(3,4))
        result=self.finish(s,bridge)
        s.release_comparison_request(result.requests[0].request_id)
        self.assertEqual(bridge.snapshot().state,'insufficient_data')
        bridge.release(); self.assertEqual(s.comparison_requests(),())

    def test_explicit_release_cancels_and_capacity_is_reusable(self):
        s,e,bridge=self.make(); bridge.submit(e.expectation_id,(3,4))
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        s.step(); bridge.release(); bridge.release()
        self.assertEqual(s.comparison_requests(),())
        self.assertIsNone(s.internal_work_snapshot())
        bridge.submit(e.expectation_id,(3,4))
        self.assertEqual(self.finish(s,bridge).state,'relative_similarity')

    def test_second_admission_rejection_rolls_back_only_owned_request(self):
        s,e,bridge=self.make(limits=AdmissionLimits(max_pending=1))
        with self.assertRaises(AdmissionRejected): bridge.submit(e.expectation_id,(3,4))
        self.assertEqual(s.comparison_requests(),())
        self.assertIsNone(bridge.snapshot())
        other=s.submit_comparison_request(s.records[0].observation,s.records[3].observation)
        with self.assertRaises(AdmissionRejected): bridge.submit(e.expectation_id,(3,4))
        self.assertEqual(s.comparison_requests(),(other,))

    def test_invalid_or_missing_observations_no_fabrication(self):
        s,e,bridge=self.make()
        for ticks in ((1,4),(3,3),(3,99),(True,4),(3,)):
            with self.assertRaises(ValueError): bridge.submit(e.expectation_id,ticks)
        with self.assertRaises(ValueError): bridge.submit('unknown',(3,4))
        self.assertEqual(s.comparison_requests(),())

    def test_unobserved_source_and_expired_expectation_rejected(self):
        from tools.verify_echo_expectations import window
        s,e,bridge=self.make()
        # A registry-legal external window is not automatically session evidence.
        fake=s.echo.expect(window(s.heart.tick),expected_coordinates=(0,),ttl=5)
        with self.assertRaisesRegex(ValueError,'source'):
            bridge.submit(fake.expectation_id,(3,4))
        s.run()
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        self.assertEqual(s.comparison_requests(),())

    def test_contradictory_expectation_and_incompatible_candidate_rejected(self):
        s,e,bridge=self.make()
        s.sensor=lambda tick: VisualFieldSnapshot((1,2),(1.,0.),tick,tick)
        s.step()
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,5))
        # Explicit opposing coordinates are ECHO's authority, not score differences.
        s,e,bridge=self.make()
        s.echo.expect(s.records[4].observation,expected_coordinates=(0,),
                      opposing_coordinates=(1,),ttl=10)
        key=s.echo.snapshot()[-1].expectation_id
        s.sensor=lambda tick: VisualFieldSnapshot((1,4),(0.,1.,0.,0.),tick,tick)
        s.step()
        with self.assertRaises(ValueError): bridge.submit(key,(4,5))
        self.assertEqual(s.comparison_requests(),())

    def test_default_disabled_and_pulse_guard(self):
        s,e,bridge=self.make(enabled=False)
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        self.assertEqual(s.comparison_requests(),())
        s,e,bridge=self.make()
        def sensor(tick):
            with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        s.sensor=sensor; s.step()
        self.assertIsNone(bridge.snapshot())
        self.assertEqual(s.comparison_requests(),())

    def test_pause_stop_and_frozen_snapshot(self):
        s,e,bridge=self.make(); old=bridge.submit(e.expectation_id,(3,4))
        s.step(); s.pause(); before=bridge.snapshot()
        s.step(); self.assertEqual(bridge.snapshot(),before)
        s.resume(); s.step(); s.stop()
        self.assertEqual(bridge.snapshot().state,'insufficient_data')
        self.assertTrue(all(r.state=='queued' for r in old.requests))
        bridge.release()

    def test_existing_short_memory_expectation_contract(self):
        base=self.session(ticks=24)
        samples={0:(1.,0.,0.,0.),1:(0.,1.,0.,0.),
                 4:(0.,.9,0.,0.),5:(0.,.6,0.,0.)}
        s=NativeHeartSession(base.components,max_ticks=24,echo=EchoExpectations(),
            sensor=lambda t: VisualFieldSnapshot((1,4),samples[t],t,t) if t in samples else None,
            internal_work_limits=WorkLimits(1,8),admission_limits=AdmissionLimits())
        s.start(); s.step(); s.step()
        transition=s.components.short_memory.snapshot()[0]
        entry=s.echo.expect_transition(s.components.short_memory,transition.transition_id,
                                      expected_coordinates=(1,),ttl=20)
        for _ in range(4): s.step()
        bridge=EchoCandidateComparison(s)
        bridge.submit(entry.expectation_id,(4,5))
        result=self.finish(s,bridge)
        self.assertEqual(result.state,'relative_similarity')
        self.assertTrue(all(m.history_transition_id==transition.transition_id for m in result.matches))
        self.assertEqual(result.source.window_id,transition.after_sensory_window.window_id)
        self.assertFalse(result.identity_confirmed)
        self.assertFalse(any(t.action_tick==1 for t in s.components.short_memory.snapshot()))

    def test_differential_native_actions_memory_and_echo(self):
        traces=[]
        for enabled in (False,True):
            s,e,bridge=self.make((.9,0.,0.,0.),(.6,0.,0.,0.),actions=True,a=(1.,0.,0.,0.))
            if enabled: bridge.submit(e.expectation_id,(3,4))
            for _ in range(8): s.step()
            traces.append(([(r.tick,r.advancement,r.execution.status if r.execution else None,
                            r.recent is not None,tuple((m.outcome,m.identity_confirmed) for m in r.echo_matches))
                            for r in s.records],
                           len(s.components.world.applies),len(s.components.short_memory.snapshot()),
                           s.components.context_manager.pending_causal_transition is not None,
                           s.components.world.current_tick,
                           len(s.components.context_manager.memory.events),
                           len(s.components.context_manager.memory.memory_updates),
                           len(s.components.context_manager.memory.value_feedback_updates),
                           tuple(t.observation_tick for t in s.components.short_memory.snapshot())))
        self.assertGreater(traces[0][1],0)
        self.assertEqual(*traces)

    def test_uuid_failure_precedes_admission(self):
        s,e,bridge=self.make()
        # The same production path can accept and release both requests normally.
        bridge.submit(e.expectation_id,(3,4)); bridge.release()
        before=s.comparison_requests()
        with patch('clc.echo.candidate_comparison.uuid4',side_effect=OSError('entropy unavailable')):
            with patch.object(s,'submit_comparison_request',wraps=s.submit_comparison_request) as submit:
                with self.assertRaises(OSError): bridge.submit(e.expectation_id,(3,4))
                submit.assert_not_called()
        self.assertEqual(s.comparison_requests(),before)
        self.assertIsNone(bridge.snapshot())
        bridge.release()
        bridge.submit(e.expectation_id,(3,4))
        self.assertEqual(self.finish(s,bridge).state,'relative_similarity')
        bridge.release()

    def test_descriptor_failure_precedes_admission_preserves_foreign_request(self):
        s,e,bridge=self.make()
        foreign=s.submit_comparison_request(s.records[0].observation,s.records[3].observation)
        with patch('clc.echo.candidate_comparison.WindowSourceDescriptor.capture',
                   side_effect=RuntimeError('descriptor fault')):
            with patch.object(s,'submit_comparison_request',wraps=s.submit_comparison_request) as submit:
                with self.assertRaises(RuntimeError): bridge.submit(e.expectation_id,(3,4))
                submit.assert_not_called()
        self.assertEqual(s.comparison_requests(),(foreign,))
        self.assertIsNone(bridge.snapshot())
        bridge.release(); self.assertEqual(s.comparison_requests(),(foreign,))

    def test_rollback_cleanup_failure_retains_ownership_for_manual_release(self):
        s,e,bridge=self.make(limits=AdmissionLimits(max_pending=1))
        with patch.object(s,'release_comparison_request',side_effect=RuntimeError('cleanup fault')) as release:
            with self.assertRaises(RuntimeError) as error:
                bridge.submit(e.expectation_id,(3,4))
            self.assertIsInstance(error.exception.__context__,AdmissionRejected)
            self.assertEqual(release.call_count,1)  # no hidden retry
        held=s.comparison_requests()
        self.assertEqual(len(held),1)
        self.assertEqual((held[0].state,held[0].retained_cells,held[0].work),('cancelled',0,None))
        self.assertIsNone(bridge.snapshot())
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        bridge.release(); bridge.release()
        self.assertEqual(s.comparison_requests(),())
        # The one-request capacity is usable again, without replay of cancelled work.
        fresh=s.submit_comparison_request(s.records[0].observation,s.records[3].observation)
        s.step()
        self.assertEqual(s.comparison_requests()[0].request_id,fresh.request_id)
        self.assertEqual(s.comparison_requests()[0].work.processed_cells,1)
        self.assertEqual(s.components.world.current_tick,6)

    def test_partial_cleanup_retains_only_remaining_owned_request(self):
        s,e,bridge=self.make()
        foreign=s.submit_comparison_request(s.records[0].observation,s.records[3].observation)
        owned=bridge.submit(e.expectation_id,(3,4)).requests
        following=s.submit_comparison_request(s.records[0].observation,s.records[4].observation)
        original=s.release_comparison_request
        def fail_second(key):
            if key==owned[1].request_id: raise RuntimeError('second cleanup fault')
            return original(key)
        with patch.object(s,'release_comparison_request',side_effect=fail_second) as release:
            with self.assertRaises(RuntimeError): bridge.release()
            self.assertEqual(release.call_count,2)
        self.assertEqual([r.request_id for r in s.comparison_requests()],
                         [foreign.request_id,owned[1].request_id,following.request_id])
        self.assertEqual(bridge.snapshot().state,'insufficient_data')
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        with patch.object(s,'release_comparison_request',wraps=original) as release:
            bridge.release()
            release.assert_called_once_with(owned[1].request_id)
        self.assertEqual(s.comparison_requests(),(foreign,following))
        for _ in range(8): s.step()
        requests=s.comparison_requests()
        self.assertTrue(all(r.state=='completed' for r in requests))
        self.assertLess(requests[0].work.result.completed_tick,requests[1].work.result.completed_tick)
        self.assertIsNone(bridge.snapshot())

    def test_cancel_failure_before_effect_preserves_ownership(self):
        s,e,bridge=self.make(); old=bridge.submit(e.expectation_id,(3,4))
        with patch.object(s,'cancel_comparison_request',side_effect=RuntimeError('cancel fault')) as cancel:
            with patch.object(s,'release_comparison_request',wraps=s.release_comparison_request) as release:
                with self.assertRaises(RuntimeError): bridge.release()
                cancel.assert_called_once_with(old.requests[0].request_id)
                release.assert_not_called()
        self.assertEqual(bridge.snapshot(),old)
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        bridge.release(); self.assertEqual(s.comparison_requests(),())

    def test_cancel_failure_after_effect_preserves_terminal_ownership(self):
        s,e,bridge=self.make(); old=bridge.submit(e.expectation_id,(3,4))
        cancel=s.cancel_comparison_request
        def fail_after_cancel(key):
            cancel(key)
            raise RuntimeError('cancel response fault')
        with patch.object(s,'cancel_comparison_request',side_effect=fail_after_cancel):
            with self.assertRaises(RuntimeError): bridge.release()
        self.assertEqual([r.state for r in s.comparison_requests()],['cancelled','queued'])
        bridge.release(); self.assertEqual(s.comparison_requests(),())

    def test_release_effect_then_keyerror_reconciles_absence(self):
        s,e,bridge=self.make(); owned=bridge.submit(e.expectation_id,(3,4)).requests
        original=s.release_comparison_request
        def delete_then_fail(key):
            original(key)
            raise KeyError('response fault after actual release')
        with patch.object(s,'release_comparison_request',side_effect=delete_then_fail):
            with self.assertRaises(KeyError): bridge.release()
        self.assertEqual([r.request_id for r in s.comparison_requests()],[owned[1].request_id])
        with patch.object(s,'release_comparison_request',wraps=original) as release:
            bridge.release()
            release.assert_called_once_with(owned[1].request_id)
        self.assertEqual(s.comparison_requests(),())

    def test_keyerror_without_release_does_not_clear_ownership(self):
        s,e,bridge=self.make(); old=bridge.submit(e.expectation_id,(3,4))
        with patch.object(s,'release_comparison_request',side_effect=KeyError('still present')):
            with self.assertRaises(KeyError): bridge.release()
        self.assertEqual(len(s.comparison_requests()),2)
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        bridge.release(); self.assertEqual(s.comparison_requests(),())

    def test_failed_reconciliation_retains_conservative_ownership(self):
        s,e,bridge=self.make(); owned=bridge.submit(e.expectation_id,(3,4)).requests
        original=s.release_comparison_request; read=s.comparison_requests
        def delete_then_fail(key):
            original(key)
            raise RuntimeError('release response fault')
        with patch.object(s,'release_comparison_request',side_effect=delete_then_fail):
            with patch.object(s,'comparison_requests',side_effect=[read(),RuntimeError('read fault')]):
                with self.assertRaisesRegex(RuntimeError,'read fault'): bridge.release()
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        # The subsequent explicit read confirms the first ID is absent.
        with patch.object(s,'release_comparison_request',wraps=original) as release:
            bridge.release()
            release.assert_called_once_with(owned[1].request_id)
        self.assertEqual(s.comparison_requests(),())

    def test_initial_snapshot_failure_publishes_no_evaluation_keeps_cleanup_ids(self):
        s,e,bridge=self.make()
        with patch.object(s,'comparison_requests',side_effect=RuntimeError('snapshot fault')):
            with self.assertRaises(RuntimeError): bridge.submit(e.expectation_id,(3,4))
        self.assertIsNone(bridge.snapshot())
        self.assertEqual(len(s.comparison_requests()),2)
        with self.assertRaises(ValueError): bridge.submit(e.expectation_id,(3,4))
        bridge.release(); self.assertEqual(s.comparison_requests(),())
        bridge.submit(e.expectation_id,(3,4))
        self.assertEqual(self.finish(s,bridge).state,'relative_similarity')

    def test_interrupted_second_admission_rolls_back_first(self):
        s,e,bridge=self.make(); original=s.submit_comparison_request; calls=[]
        def interrupted(left,right):
            calls.append(right.window_id)
            if len(calls)==2: raise KeyboardInterrupt('interrupted admission')
            return original(left,right)
        with patch.object(s,'submit_comparison_request',side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): bridge.submit(e.expectation_id,(3,4))
        self.assertEqual(s.comparison_requests(),())
        self.assertIsNone(bridge.snapshot())
        bridge.release()

    def test_cleanup_initial_read_failure_is_recoverable(self):
        s,e,bridge=self.make(); old=bridge.submit(e.expectation_id,(3,4))
        with patch.object(s,'comparison_requests',side_effect=RuntimeError('read fault')):
            with self.assertRaises(RuntimeError): bridge.release()
        self.assertEqual(bridge.snapshot(),old)
        bridge.release(); bridge.release()
        self.assertEqual(s.comparison_requests(),())


if __name__=='__main__':
    unittest.main()
