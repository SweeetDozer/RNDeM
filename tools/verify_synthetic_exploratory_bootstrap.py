"""RND-022 behavioral verifier. All writable fixtures are temporary/isolated."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import verify_native_heart_b2 as fixtures
from clc.actuation.synthetic_exploration import (
    SyntheticExplorationConfig as Config, SyntheticExplorationAuthorization as Authorization,
    SyntheticExplorationPolicy as Policy,
)
from clc.actuation.remembered_action_execution import NFPRememberedActionExecutionStatus as S
from clc.runtime.native_heart_session import NativeHeartSession
from clc.runtime.native_bounded_delivery import NativeDeliverySession, DeliveryLimits, Control
from clc.runtime.heart import HeartState
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology


class ExplorationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = fixtures.inventory()

    @classmethod
    def tearDownClass(cls):
        if fixtures.inventory() != cls.original:
            raise AssertionError('Production Memory changed')

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='rnd022-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.events = []

    def session(self, *, enabled=True, authorized=True, commands=((0., 1.), (1., 0.)),
                intents=1, actions=1, delivery=False, sample_enabled=None,
                limits=DeliveryLimits(journal_capacity=128), **options):
        base = fixtures.B2Tests.session(self, empty=options.pop('empty', True), **options)
        config = Config('round-robin-v1', commands, intents, actions) if enabled else None
        auth = Authorization('isolated-test-owner', 'permit-022', 'round-robin-v1') if authorized and enabled else None
        kwargs = dict(max_ticks=base.heart.max_ticks, exploration_config=config,
                      exploration_authorization=auth)
        if delivery:
            return NativeDeliverySession(base.components, sample_enabled=sample_enabled, limits=limits, **kwargs)
        return NativeHeartSession(base.components, sensor=base.sensor, **kwargs)

    def test_disabled_and_missing_authorization(self):
        for opts in ({'enabled': False}, {'authorized': False}):
            s = self.session(**opts)
            s.run()
            self.assertEqual(s.components.world.applies, [])
            self.assertTrue(all(r.execution is None for r in s.records))

    def test_empty_store_real_apply_observe_and_bounded_provenance(self):
        s = self.session(delivery=True)
        s.run()
        x = s.records[0].execution
        self.assertEqual(x.status, S.ACTION_EXECUTED_OBSERVATION_PENDING)
        self.assertIsNone(x.source_experience_id)
        self.assertIsNone(x.predicted_effect)
        self.assertIsNone(x.target_core)
        self.assertFalse(hasattr(x.exploratory_intent, 'selection_id'))
        self.assertFalse(hasattr(x.exploratory_intent, 'predicted_effect'))
        self.assertEqual(UUID(x.execution_occurrence_id).version, 4)
        self.assertEqual(UUID(x.action_frame.frame_id).version, 4)
        self.assertEqual(len(s.components.world.applies), 1)
        self.assertEqual(s.records[0].advancement, 'actuator')
        self.assertEqual(s.records[0].observation.end_tick, 0)
        self.assertIsNone(s.records[0].recent)
        t = s.records[1].recent
        self.assertEqual(t.execution_occurrence_id, x.execution_occurrence_id)
        self.assertIs(t.action_frame, x.action_frame)
        self.assertIs(t.before_sensory_window, x.before_context_at_T)
        self.assertNotEqual(t.before_sensory_window.frames[0].values, t.after_sensory_window.frames[0].values)
        self.assertIs(s.components.short_memory.snapshot()[0], t)
        self.assertEqual((t.action_tick, t.observation_tick), (0, 1))
        d, = s.exploration.diagnostics
        self.assertTrue(d.admitted and d.guarded and d.applied)
        self.assertFalse(d.denied or d.uncertain)
        self.assertEqual(d.intent, x.exploratory_intent)
        self.assertEqual(json.loads(next(self.root.rglob('ExpSM.json')).read_text())['experience'], {})

    def test_order_changes_choice_without_world_changes(self):
        outputs = []
        for commands in (((0., 1.), (1., 0.)), ((1., 0.), (0., 1.))):
            s = self.session(commands=commands)
            s.run()
            outputs.append(s.records[0].execution.actuator_signal.values)
        self.assertEqual(outputs, [(0., 1.), (1., 0.)])

    def test_round_robin_budget_and_unique_occurrences(self):
        s = self.session(intents=3, actions=3, ticks=8)
        s.run()
        xs = [r.execution for r in s.records if r.execution is not None]
        self.assertEqual([x.actuator_signal.values for x in xs], [(0., 1.), (1., 0.), (0., 1.)])
        self.assertEqual(len({x.execution_occurrence_id for x in xs}), 3)
        self.assertEqual(len(s.exploration.diagnostics), 3)
        self.assertEqual(s.components.world.current_tick, 8)

    def test_guard_denial_no_apply_and_conservative_admission_budget(self):
        s = self.session(mode='consolidation', intents=4, actions=1)
        s.run()
        self.assertEqual(s.records[0].execution.status, S.GUARD_DENIED)
        self.assertEqual(s.components.world.applies, [])
        d, = s.exploration.diagnostics
        self.assertTrue(d.admitted and d.denied)
        self.assertFalse(d.guarded or d.applied)

    def test_remembered_action_keeps_precedence(self):
        s = self.session(empty=False, ticks=3)
        s.run()
        self.assertIsNotNone(s.records[0].execution.source_experience_id)
        self.assertIsNotNone(s.records[0].execution.predicted_effect)
        self.assertIsNone(s.records[0].execution.exploratory_intent)
        self.assertEqual(s.exploration.diagnostics, ())

    def test_denied_remembered_never_falls_back(self):
        s = self.session(empty=False, mode='consolidation')
        s.run()
        self.assertTrue(all(r.execution.status is S.GUARD_DENIED for r in s.records))
        self.assertEqual(s.exploration.diagnostics, ())

    def test_selection_none_with_candidates_is_conservatively_not_empty(self):
        s = self.session(empty=False, decision=1.)
        s.run()
        self.assertEqual(s.exploration.diagnostics, ())
        self.assertEqual(s.components.world.applies, [])

    def test_retrieval_activation_selection_errors_no_fallback(self):
        for component, method in (('retriever', 'retrieve'), ('activation', 'activate_native'), ('selector', 'select_native')):
            s = self.session()
            with patch.object(getattr(s.components, component), method, side_effect=RuntimeError('fault')):
                with self.assertRaises(RuntimeError):
                    s.run()
            self.assertEqual(s.heart.state, HeartState.STOPPED)
            self.assertEqual(s.exploration.diagnostics, ())
            self.assertEqual(s.components.world.applies, [])

    def test_typed_retrieval_errors_never_authorize_exploration(self):
        from clc.expsm.nfp_operational_retrieval import NFPExpSMRetrievalResult, NFPExpSMRetrievalStatus
        for status in (NFPExpSMRetrievalStatus.STORE_INVALID,
                       NFPExpSMRetrievalStatus.INVALID_QUERY,
                       NFPExpSMRetrievalStatus.UNSUPPORTED_MEMORY_PRESENT):
            s = self.session()
            with patch.object(s.components.retriever, 'retrieve', return_value=NFPExpSMRetrievalResult(status)):
                s.run()
            self.assertEqual(s.exploration.diagnostics, ())
            self.assertEqual(s.components.world.applies, [])
        # Actual malformed store path, not only an injected result.
        s = self.session()
        paths = sorted(self.root.rglob('ExpSM.json'))
        path = paths[-1]
        original = path.read_bytes()
        path.write_text('invalid json')
        try:
            s.run()
            self.assertEqual(s.components.world.applies, [])
        finally:
            path.write_bytes(original)

    def test_missing_or_late_observation_never_reopens_exploration(self):
        for enabled in (lambda t: t != 1, lambda t: t == 0):
            s = self.session(delivery=True, sample_enabled=enabled, intents=4, actions=4)
            s.run()
            self.assertEqual(len(s.components.world.applies), 1)
            self.assertFalse(any(r.recent for r in s.records))
            self.assertEqual(s.components.short_memory.snapshot(), ())

    def test_unknown_apply_outcome_no_retry(self):
        for failure in ('before', 'after', 'double'):
            s = self.session(failure=failure, intents=4, actions=4)
            if failure == 'double':
                with self.assertRaises(RuntimeError):
                    s.run()
            else:
                s.run()
            self.assertEqual(s.heart.state, HeartState.STOPPED)
            s.resume()
            s.run()
            self.assertEqual(len(s.components.world.applies), 1)
            if failure != 'double':
                self.assertTrue(s.exploration.diagnostics[0].uncertain)

    def boundary(self):
        s = self.session(intents=4, actions=4)
        snapshot = s.components.world.snapshot()
        from clc.transduction import VisualFieldTransducer
        frame = VisualFieldTransducer().transduce(snapshot, frame_id='boundary')
        window = NFPWindow('boundary-window', (frame,))
        s.components.context_manager.observe_external_sensory_window(window)
        intent = s.exploration.issue(window, tick=0, pending=None, unresolved=False)
        return s, window, intent

    def execute(self, s, intent):
        c = s.components
        return c.coordinator.execute_exploratory(intent, policy=s.exploration,
            context_manager=c.context_manager, world=c.world, system_state=c.system_state)

    def test_stale_context_and_world_tick_denied(self):
        s, window, intent = self.boundary()
        s.components.world.advance_idle(expected_tick=0)
        self.assertIsNone(self.execute(s, intent).actuator_signal)
        self.assertEqual(s.components.world.applies, [])

    def test_copied_intent_and_reuse_denied(self):
        s, window, intent = self.boundary()
        self.assertIsNone(self.execute(s, replace(intent)).actuator_signal)
        c = s.components
        invalid = c.coordinator.execute_exploratory(intent, policy=object(),
            context_manager=c.context_manager, world=c.world, system_state=c.system_state)
        self.assertEqual(invalid.detail, 'exploration_request_type_invalid')
        first = self.execute(s, intent)
        self.assertIsNotNone(first.actuator_signal)
        self.assertIsNone(self.execute(s, intent).actuator_signal)
        self.assertEqual(len(s.components.world.applies), 1)

    def test_occupied_causal_slot(self):
        s, window, intent = self.boundary()
        frame = NFPFrame('other-action', PatternModality.ACTION, PatternOrigin.ACTION_GENERATED,
                         PatternTopology((2,)), (0., 1.), 0)
        s.components.context_manager.observe_action_frame(frame)
        self.assertEqual(self.execute(s, intent).status, S.CAUSAL_SLOT_OCCUPIED)
        self.assertEqual(s.components.world.applies, [])
        self.assertIsNone(s.exploration.issue(window, tick=0, pending=s.components.context_manager.pending_causal_transition, unresolved=False))

    def test_topology_and_transducer_remain_authoritative(self):
        from clc.actuation.synthetic_exploration import MaterializedExploratoryAction
        from uuid import uuid4
        s, window, intent = self.boundary()
        frame = NFPFrame(str(uuid4()), PatternModality.ACTION, PatternOrigin.ACTION_GENERATED,
                         PatternTopology((1, 2)), (0., 1.), 0)
        materialized = MaterializedExploratoryAction(intent, frame, window, str(uuid4()))
        result = s.components.coordinator._execute_materialized(materialized, common={},
            context_manager=s.components.context_manager, world=s.components.world,
            system_state=s.components.system_state, observe_consequence=False, short_memory=None)
        self.assertEqual(result.status, S.ACTUATOR_INCOMPATIBLE)
        with patch.object(s.components.coordinator.action_transducer, 'transduce', side_effect=ValueError('fault')):
            result = self.execute(s, intent)
        self.assertEqual(result.status, S.TRANSDUCTION_REJECTED)
        self.assertTrue(result.guard_passed)
        self.assertEqual(s.components.world.applies, [])

    def test_invalid_config_and_resource_bounds(self):
        for kw in ({'commands': ()}, {'commands': ((float('nan'), 0.),)},
                   {'commands': ((2., 0.),)}, {'max_intents': 65},
                   {'max_actions': 2}, {'intent_lifetime_ticks': 1},
                   {'configuration_id': 'x'*257}):
            fields = dict(configuration_id='round-robin-v1', commands=((0., 1.),))
            fields.update(kw)
            with self.assertRaises(ValueError):
                Config(**fields)
        s = self.session(actions=0)
        s.run()
        self.assertEqual(s.exploration.diagnostics, ())

    def test_pause_resume_pending_without_duplicate_apply(self):
        s = self.session(intents=2, actions=2)
        s.start()
        s.step()
        s.pause()
        self.assertIsNone(s.step())
        self.assertEqual(len(s.components.world.applies), 1)
        s.resume()
        s.step()
        self.assertIsNotNone(s.records[1].recent)
        self.assertEqual(len(s.components.world.applies), 2)
        self.assertNotEqual(s.records[0].execution.execution_occurrence_id,
                            s.records[1].execution.execution_occurrence_id)

    def test_stop_and_tick_exhaustion_terminal(self):
        for ticks in (1, 5):
            s = self.session(ticks=ticks, intents=4, actions=4)
            s.start()
            s.step()
            s.stop()
            s.start()
            s.resume()
            s.run()
            self.assertEqual(len(s.components.world.applies), 1)
            self.assertIsNotNone(s.components.context_manager.pending_causal_transition)

    def test_control_stop_pause_and_tick_budget(self):
        for control in (Control.STOP, Control.PAUSE):
            s = self.session(delivery=True)
            s.ingress = lambda tick, delivery: delivery.accept(control, source_id='test-owner', stream_id='control')
            s.run()
            self.assertEqual(s.components.world.applies, [])
            self.assertEqual(s.exploration.diagnostics, ())
        s = self.session(ticks=1, intents=4, actions=4)
        s.run()
        self.assertEqual(s.heart.diagnostic, 'tick_budget_exhausted')
        self.assertEqual(len(s.components.world.applies), 1)
        s.run()
        self.assertEqual(len(s.components.world.applies), 1)

    def test_bounded_diagnostics_and_exact_context_world_binding(self):
        s = self.session(mode='consolidation', intents=64, actions=64, ticks=80)
        s.run()
        self.assertEqual(len(s.exploration.diagnostics), 64)
        self.assertEqual(s.components.world.applies, [])
        s, window, intent = self.boundary()
        copied = replace(window)
        self.assertFalse(s.exploration.admit(intent, copied, s.components.world))
        s, window, intent = self.boundary()
        other = fixtures.World([])
        self.assertFalse(s.exploration.admit(intent, window, other))

    def test_delivery_resource_exhaustion_before_intent(self):
        s = self.session(delivery=True, limits=DeliveryLimits(max_values=1))
        s.run()
        self.assertEqual(s.heart.state, HeartState.STOPPED)
        self.assertEqual(s.exploration.diagnostics, ())
        self.assertEqual(s.components.world.applies, [])

    def test_unsupported_world_and_authorization_scope(self):
        base = self.session(enabled=False)
        class Unsupported:
            current_tick = 0
        with self.assertRaises(ValueError):
            NativeHeartSession(replace(base.components, world=Unsupported()), max_ticks=2,
                exploration_config=Config('round-robin-v1', ((0., 1.),)))
        with self.assertRaises(ValueError):
            Policy(Config('a', ((0., 1.),)), Authorization('owner', 'permit', 'b'), 'session')

    def test_sensor_or_tracking_failure_stops_without_retry(self):
        for options in ({'failure': 'sensor'}, {'manager_type': fixtures.TrackingFailure}):
            s = self.session(intents=4, actions=4, **options)
            try:
                s.run()
            except RuntimeError:
                pass
            self.assertEqual(s.heart.state, HeartState.STOPPED)
            self.assertEqual(len(s.components.world.applies), 1)

    def test_no_automatic_create_feedback_or_filesystem_writes(self):
        from clc.experience.expsm_native_create import NFPExpSMCreateWriter
        from clc.expsm.nfp_native_feedback_apply import NFPFeedbackApplyWriter
        s = self.session(delivery=True)
        original_open = Path.open
        def read_only(path, mode='r', *args, **kwargs):
            if any(flag in mode for flag in 'wax+'):
                raise AssertionError('unexpected runtime filesystem write')
            return original_open(path, mode, *args, **kwargs)
        with patch.object(NFPExpSMCreateWriter, 'create', side_effect=AssertionError('automatic CREATE')), \
             patch.object(NFPFeedbackApplyWriter, 'apply', side_effect=AssertionError('automatic Feedback APPLY')), \
             patch.object(Path, 'open', read_only):
            s.run()
        self.assertEqual(len(s.components.world.applies), 1)

    def test_external_exception_diagnostic_is_bounded(self):
        s = self.session()
        with patch.object(s.components.world, 'apply_actuator_signal', side_effect=OSError('x'*100000)):
            s.run()
        self.assertEqual(s.records[0].execution.detail, 'exploratory_execution_diagnostic')
        self.assertTrue(s.exploration.diagnostics[0].uncertain)

    def test_correction_post_apply_interrupt_preserves_uncertain_identity(self):
        for mutate in (False, True):
            s = self.session(intents=4, actions=4)
            world = s.components.world
            original = world.apply_actuator_signal
            interruption = KeyboardInterrupt('controlled interruption')
            def apply(signal):
                if mutate:
                    original(signal)
                raise interruption
            with patch.object(world, 'apply_actuator_signal', side_effect=apply) as apply_call:
                with self.assertRaises(KeyboardInterrupt) as caught:
                    s.run()
                self.assertIs(caught.exception, interruption)
                self.assertEqual(apply_call.call_count, 1)
                d, = s.exploration.diagnostics
                self.assertTrue(d.admitted and d.guarded and d.uncertain)
                self.assertFalse(d.applied or d.denied)
                self.assertEqual(UUID(d.execution_occurrence_id).version, 4)
                self.assertIn(d.execution_occurrence_id, s.stop_report().unresolved_occurrences)
                self.assertIsNone(s.components.context_manager.pending_causal_transition)
                self.assertEqual(world.idles, [])
                self.assertEqual(world.current_tick, int(mutate))
                self.assertTrue(s.stop_report().synchronization_blocked)
                s.pause(); s.resume(); s.start(); s.run(); s.step()
                self.assertEqual(apply_call.call_count, 1)
                self.assertEqual(len(s.exploration.diagnostics), 1)

    def test_correction_pre_apply_interrupt_has_no_physical_uncertainty(self):
        s = self.session()
        interruption = KeyboardInterrupt('guard interrupted')
        with patch.object(s.components.coordinator.mode_action_guard,
                          'is_native_action_allowed', side_effect=interruption):
            with self.assertRaises(KeyboardInterrupt) as caught:
                s.run()
        self.assertIs(caught.exception, interruption)
        d, = s.exploration.diagnostics
        self.assertTrue(d.admitted and d.denied)
        self.assertFalse(d.uncertain or d.applied)
        self.assertIsNotNone(d.execution_occurrence_id)
        self.assertEqual(s.components.world.applies, [])
        self.assertEqual(s.components.world.idles, [])
        self.assertIsNone(s.components.context_manager.pending_causal_transition)
        self.assertEqual(s.stop_report().unresolved_occurrences, ())

    def test_correction_late_diagnostic_failure_preserves_confirmed_pending(self):
        for after_projection in (False, True):
            s = self.session(intents=4, actions=4)
            original = s.exploration.finish
            interruption = KeyboardInterrupt('diagnostic interrupted')
            def finish(intent, result):
                if after_projection:
                    original(intent, result)
                raise interruption
            with patch.object(s.exploration, 'finish', side_effect=finish):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    s.run()
            self.assertIs(caught.exception, interruption)
            d, = s.exploration.diagnostics
            self.assertEqual(d.outcome, S.ACTION_EXECUTED_OBSERVATION_PENDING.value)
            self.assertTrue(d.applied and d.guarded)
            self.assertFalse(d.uncertain or d.denied)
            pending = s.components.context_manager.pending_causal_transition
            self.assertEqual(pending.execution_occurrence_id, d.execution_occurrence_id)
            self.assertEqual(len(s.components.context_manager.pending_log), 1)
            self.assertEqual(len(s.components.world.applies), 1)
            self.assertEqual(s.components.world.idles, [])
            self.assertIn(d.execution_occurrence_id, s.stop_report().unresolved_occurrences)
            s.resume(); s.run()
            self.assertEqual(len(s.components.world.applies), 1)

    def test_correction_after_coordinator_return_preserves_authoritative_outcome(self):
        s = self.session()
        interruption = RuntimeError('session finish diagnostic failed')
        with patch.object(s.time_adapter, 'finish', side_effect=interruption):
            with self.assertRaises(RuntimeError) as caught:
                s.run()
        self.assertIs(caught.exception, interruption)
        d, = s.exploration.diagnostics
        self.assertEqual(d.outcome, S.ACTION_EXECUTED_OBSERVATION_PENDING.value)
        self.assertTrue(d.applied)
        self.assertFalse(d.uncertain)
        self.assertEqual(len(s.components.context_manager.pending_log), 1)
        self.assertIn(d.execution_occurrence_id, s.stop_report().unresolved_occurrences)
        self.assertEqual(len(s.components.world.applies), 1)
        self.assertEqual(s.components.world.idles, [])

    def test_correction_pending_registration_interruption_is_conservative(self):
        s = self.session(intents=4, actions=4)
        manager = s.components.context_manager
        original = manager.observe_action_frame
        interruption = KeyboardInterrupt('tracking interrupted after mutation')
        def observe(*args, **kwargs):
            original(*args, **kwargs)
            raise interruption
        with patch.object(manager, 'observe_action_frame', side_effect=observe):
            with self.assertRaises(KeyboardInterrupt) as caught:
                s.run()
        self.assertIs(caught.exception, interruption)
        d, = s.exploration.diagnostics
        self.assertTrue(d.uncertain)
        self.assertEqual(manager.pending_causal_transition.execution_occurrence_id, d.execution_occurrence_id)
        self.assertEqual(len(manager.pending_log), 1)
        self.assertIn(d.execution_occurrence_id, s.stop_report().unresolved_occurrences)
        s.resume(); s.run()
        self.assertEqual(len(s.components.world.applies), 1)

    def test_correction_coordinator_completed_but_caller_did_not_receive_result(self):
        s = self.session()
        coordinator = s.components.coordinator
        original = coordinator.execute_exploratory
        interruption = KeyboardInterrupt('return delivery interrupted')
        def execute(*args, **kwargs):
            original(*args, **kwargs)
            raise interruption
        with patch.object(coordinator, 'execute_exploratory', side_effect=execute):
            with self.assertRaises(KeyboardInterrupt) as caught:
                s.run()
        self.assertIs(caught.exception, interruption)
        d, = s.exploration.diagnostics
        self.assertEqual(d.outcome, S.ACTION_EXECUTED_OBSERVATION_PENDING.value)
        self.assertTrue(d.applied and not d.uncertain)
        self.assertEqual(len(s.components.world.applies), 1)
        self.assertEqual(len(s.components.context_manager.pending_log), 1)
        self.assertIn(d.execution_occurrence_id, s.stop_report().unresolved_occurrences)

    def test_correction_success_and_tick_exhaustion_keep_single_occurrence(self):
        s = self.session(delivery=True, ticks=2)
        s.run()
        d, = s.exploration.diagnostics
        self.assertTrue(d.applied and not d.uncertain)
        transition, = s.components.short_memory.snapshot()
        self.assertEqual(transition.execution_occurrence_id, d.execution_occurrence_id)
        self.assertEqual((transition.action_tick, transition.observation_tick), (0, 1))
        self.assertEqual(s.stop_report().unresolved_occurrences, ())
        self.assertEqual(s.heart.diagnostic, 'tick_budget_exhausted')
        s.resume(); s.run()
        self.assertEqual(len(s.components.world.applies), 1)

    def test_marker_enter_apply_failure_does_not_claim_physical_uncertainty(self):
        for after_write in (False, True):
            for error_type in (RuntimeError, KeyboardInterrupt):
                s = self.session(intents=4, actions=4)
                original = s.exploration.enter_apply
                primary = error_type('enter_apply failed')
                def marker(intent):
                    if after_write:
                        original(intent)
                    raise primary
                with patch.object(s.exploration, 'enter_apply', side_effect=marker):
                    with self.assertRaises(error_type) as caught:
                        s.run()
                self.assertIs(caught.exception, primary)
                d, = s.exploration.diagnostics
                receipt = s.exploration.execution_receipt
                self.assertTrue(receipt.guard_passed)
                self.assertFalse(receipt.apply_entry or receipt.apply_returned or receipt.pending_registered)
                self.assertFalse(d.uncertain or d.applied)
                self.assertTrue(d.denied)
                self.assertEqual(d.execution_occurrence_id, receipt.execution_occurrence_id)
                self.assertEqual(s.components.world.applies, [])
                self.assertEqual(s.components.world.idles, [])
                self.assertIsNone(s.components.context_manager.pending_causal_transition)
                self.assertEqual(s.stop_report().unresolved_occurrences, ())
                self.assertEqual(s.heart.state, HeartState.STOPPED)
                s.resume(); s.run()
                self.assertEqual(s.components.world.applies, [])

    def test_marker_confirm_pending_failure_preserves_fact_without_fake_result(self):
        for after_write in (False, True):
            for error_type in (RuntimeError, KeyboardInterrupt):
                s = self.session()
                original = s.exploration.confirm_pending
                primary = error_type('confirm_pending failed')
                def marker(intent):
                    if after_write:
                        original(intent)
                    raise primary
                with patch.object(s.exploration, 'confirm_pending', side_effect=marker):
                    with self.assertRaises(error_type) as caught:
                        s.run()
                self.assertIs(caught.exception, primary)
                receipt = s.exploration.execution_receipt
                d, = s.exploration.diagnostics
                self.assertTrue(receipt.apply_entry and receipt.apply_returned and receipt.pending_registered)
                self.assertIsNone(receipt.result_status)  # coordinator did not form a result
                self.assertEqual(d.outcome, 'pending_registered')
                self.assertTrue(d.applied)
                self.assertFalse(d.uncertain or d.denied)
                self.assertEqual(s.components.context_manager.pending_causal_transition.execution_occurrence_id,
                                 receipt.execution_occurrence_id)
                self.assertEqual(len(s.components.context_manager.pending_log), 1)
                self.assertEqual(len(s.components.world.applies), 1)
                self.assertEqual(s.components.world.idles, [])
                self.assertIn(receipt.execution_occurrence_id, s.stop_report().unresolved_occurrences)
                self.assertFalse(s.components.short_memory.snapshot())
                s.resume(); s.run()
                self.assertEqual(len(s.components.world.applies), 1)

    def test_marker_recovery_failure_preserves_primary_world_interruption(self):
        for secondary_type in (RuntimeError, KeyboardInterrupt):
            s = self.session(intents=4, actions=4)
            original = s.components.world.apply_actuator_signal
            primary = KeyboardInterrupt('primary world interruption')
            def apply(signal):
                original(signal)
                raise primary
            with patch.object(s.components.world, 'apply_actuator_signal', side_effect=apply) as calls, \
                 patch.object(s.exploration, 'interrupt', side_effect=secondary_type('secondary diagnostic error')) as recovery:
                with self.assertRaises(KeyboardInterrupt) as caught:
                    s.run()
                self.assertIs(caught.exception, primary)
                self.assertEqual(recovery.call_count, 1)
                self.assertEqual(calls.call_count, 1)
                self.assertTrue(s.exploration.diagnostic_recovery_failed)
                self.assertFalse(s.exploration.diagnostic_projection_failed)
                receipt = s.exploration.execution_receipt
                d, = s.exploration.diagnostics
                self.assertTrue(receipt.apply_entry and not receipt.apply_returned)
                self.assertTrue(d.uncertain and not d.applied)
                self.assertEqual(d.execution_occurrence_id, receipt.execution_occurrence_id)
                self.assertIn(receipt.execution_occurrence_id, s.stop_report().unresolved_occurrences)
                self.assertIsNone(s.components.context_manager.pending_causal_transition)
                self.assertTrue(s.stop_report().synchronization_blocked)
                self.assertEqual(s.components.world.idles, [])
                s.resume(); s.run()
                self.assertEqual(calls.call_count, 1)

    def test_marker_recovery_failure_after_finish_keeps_known_result(self):
        s = self.session()
        primary = RuntimeError('primary finish failure')
        with patch.object(s.exploration, 'finish', side_effect=primary), \
             patch.object(s.exploration, 'interrupt', side_effect=KeyboardInterrupt('secondary recovery failure')):
            with self.assertRaises(RuntimeError) as caught:
                s.run()
        self.assertIs(caught.exception, primary)
        receipt = s.exploration.execution_receipt
        d, = s.exploration.diagnostics
        self.assertEqual(receipt.result_status, S.ACTION_EXECUTED_OBSERVATION_PENDING.value)
        self.assertEqual(d.outcome, receipt.result_status)
        self.assertTrue(d.applied and not d.uncertain)
        self.assertEqual(len(s.components.context_manager.pending_log), 1)
        self.assertEqual(len(s.components.world.applies), 1)
        self.assertIn(receipt.execution_occurrence_id, s.stop_report().unresolved_occurrences)

    def test_marker_receipt_distinguishes_apply_return_from_pending_registration(self):
        s = self.session()
        primary = KeyboardInterrupt('before pending registration')
        with patch.object(s.components.context_manager, 'observe_action_frame', side_effect=primary):
            with self.assertRaises(KeyboardInterrupt) as caught:
                s.run()
        self.assertIs(caught.exception, primary)
        receipt = s.exploration.execution_receipt
        self.assertTrue(receipt.apply_entry and receipt.apply_returned)
        self.assertFalse(receipt.pending_registered)
        self.assertIsNone(receipt.result_status)
        d, = s.exploration.diagnostics
        self.assertTrue(d.uncertain and not d.applied)
        self.assertIsNone(s.components.context_manager.pending_causal_transition)
        self.assertEqual(len(s.components.world.applies), 1)
        self.assertEqual(s.components.world.idles, [])

    def test_marker_failed_secondary_projection_preserves_primary_and_receipt(self):
        s = self.session()
        original = s.components.world.apply_actuator_signal
        primary = KeyboardInterrupt('primary')
        def apply(signal):
            original(signal)
            raise primary
        with patch.object(s.components.world, 'apply_actuator_signal', side_effect=apply), \
             patch.object(s.exploration, 'interrupt', side_effect=RuntimeError('secondary')), \
             patch.object(s.exploration, '_recover_receipt', side_effect=MemoryError('projection unavailable')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                s.run()
        self.assertIs(caught.exception, primary)
        self.assertTrue(s.exploration.diagnostic_recovery_failed and s.exploration.diagnostic_projection_failed)
        receipt = s.exploration.execution_receipt
        self.assertTrue(receipt.apply_entry and not receipt.pending_registered)
        self.assertIn(receipt.execution_occurrence_id, s.stop_report().unresolved_occurrences)
        self.assertFalse(s.exploration.diagnostics[0].applied)
        self.assertEqual(s.heart.state, HeartState.STOPPED)
        self.assertEqual(len(s.components.world.applies), 1)

    def test_marker_bind_and_guard_errors_preserve_coordinator_identity(self):
        for name in ('bind_execution', 'pass_guard'):
            for after_write in (False, True):
                s = self.session()
                original = getattr(s.exploration, name)
                primary = KeyboardInterrupt('pre-apply marker')
                def marker(*args):
                    if after_write:
                        original(*args)
                    raise primary
                with patch.object(s.exploration, name, side_effect=marker):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        s.run()
                self.assertIs(caught.exception, primary)
                d, = s.exploration.diagnostics
                receipt = s.exploration.execution_receipt
                self.assertEqual(d.execution_occurrence_id, receipt.execution_occurrence_id)
                self.assertEqual(d.guarded, name == 'pass_guard')
                self.assertFalse(d.uncertain or receipt.apply_entry)
                self.assertEqual(s.components.world.applies, [])

    def test_rnd021_actual_exploratory_admission_without_prediction_or_write(self):
        from clc.experience.bounded_native_acquisition import BoundedNativeAcquisition
        from clc.experience.expsm_native_create import NFPExpSMCreateWriter
        from clc.runtime.memory_mutation_policy import policy_for_profile
        from clc.experience.evidence import ExperienceEvidenceFactory
        s = self.session(delivery=True)
        path = next(self.root.rglob('ExpSM.json'))
        writer = NFPExpSMCreateWriter(path, policy_for_profile('safe_demo', memory_root=path.parent, memory_is_temporary=True))
        owner = BoundedNativeAcquisition(s, isolated_root=path.parent, writer=writer)
        s.run()
        t = s.records[1].recent
        admission = owner.admit(t)
        self.assertEqual(admission.status, 'admitted')
        self.assertIsNone(admission.envelope.execution.source_experience_id)
        self.assertEqual(admission.envelope.evidence, ExperienceEvidenceFactory.build(t))
        self.assertEqual(json.loads(path.read_text())['experience'], {})
        self.assertFalse(any(p.name.endswith(('.lock', '.pyc')) for p in self.root.rglob('*')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
