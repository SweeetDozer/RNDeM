"""RND-025 behavioral verifier: genuine acquisition/C0-C3 and negative arms.

Fault injections are negative-only. Positive records and evaluator evidence are
never constructed by fixtures. All writable artifacts live under temporary roots.
"""
from __future__ import annotations
from dataclasses import replace
import gc
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import TracebackType
import unittest
from unittest.mock import patch
from uuid import uuid4
import weakref

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenarios.native_competing_experience_selection import (
    acquire_pair, make_session, CompetingEpisode, authoritative_record,
    NFPFeedbackApplyWriter, NFPRememberedActionExecutionCoordinator,
    ExpSMStoreTransaction, DEFAULT_SELECTOR, NFPFeedbackEvaluator,
    NativeDeliverySession, SyntheticClosedLoopVisualWorld, ShortMemory,
    BoundedNativeAcquisition, NFPExpSMCreateWriter, policy_for_profile, EMPTY,
    RIGHT, LEFT, DecisionSelector, _bounded_reason, _exception_reason,
    reconcile_nfp_feedback_readback_failure,
)
from tools.verify_native_outcome_feedback_loop import (
    BrokenDiagnosticFailure, MaliciousDiagnosticFailure, MaliciousDiagnosticText,
    MaliciousDiagnosticOSError,
)


def inventory():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'Memory').rglob('*') if p.is_file()}


class CompetingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memory = inventory()

    @classmethod
    def tearDownClass(cls):
        if inventory() != cls.memory:
            raise AssertionError('Production Memory changed')

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='rnd025-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fixture = acquire_pair(self.root / 'acquired')
        self.count = 0

    def episode(self, *, store_bytes=None, enabled=True, profile='mutating_memory', **options):
        self.count += 1
        root = self.root / str(self.count)
        session, path = make_session(root, store_bytes=(self.fixture.store_bytes
            if store_bytes is None else store_bytes), **options)
        records = tuple(authoritative_record(path, r.record_id)[0] for r in self.fixture.records)
        owner = CompetingEpisode(session, root=root, acquired_records=records,
            feedback_enabled=enabled, profile=profile)
        return session, owner

    def observed(self, **options):
        session, owner = self.episode(**options)
        owner.observe()
        return session, owner

    def assert_no_retry(self, owner):
        state, reason, result = owner.state, owner.reason, owner.result
        with patch.object(owner._writer, 'apply', side_effect=AssertionError('retry')):
            self.assertIs(owner.apply(), result)
            owner.observe()
        self.assertEqual((owner.state, owner.reason), (state, reason))


    def assert_primary_traceback(self, operation, primary, marker):
        # assertRaises clears traceback; inspect it inside the actual handler.
        try:
            operation()
        except BaseException as caught:
            self.assertIs(caught, primary)
            names = []
            tb = caught.__traceback__
            while tb is not None:
                names.append(tb.tb_frame.f_code.co_name)
                tb = tb.tb_next
            self.assertIn(marker, names)
            self.assertNotIn('__str__', names)
        else:
            self.fail('primary exception did not escape')


    def assert_terminal_diagnostics(self, owner, state):
        self.assertEqual(owner.state, state)
        self.assertIs(type(owner.reason), str)
        self.assertTrue(owner.reason)
        self.assertLessEqual(len(owner.reason), 256)
        self.assertFalse(any(isinstance(v, (BaseException, TracebackType))
                             for v in vars(owner).values()))
        with patch.object(NativeDeliverySession, 'run', side_effect=AssertionError('repeat session')), \
             patch.object(SyntheticClosedLoopVisualWorld, 'apply_actuator_signal',
                          side_effect=AssertionError('repeat action')):
            self.assert_no_retry(owner)


    def test_missing_actual_t_plus_1(self):
        session, owner = self.observed(sample_enabled=lambda tick: tick == 0)
        self.assertEqual(owner.state, 'stopped')
        self.assertEqual(owner.reason, 'missing_retained_actual_t_plus_1')
        self.assertEqual(owner.physical_calls, 1)
        self.assertEqual(len(session.components.short_memory), 0)
        self.assertIsNone(owner.apply())


    def test_wrong_source_occurrence_prediction_and_core_are_rejected(self):
        real = NFPRememberedActionExecutionCoordinator.execute
        for field in ('source', 'occurrence', 'prediction', 'core'):
            with self.subTest(field=field):
                session, owner = self.episode()
                def corrupt(coordinator, *args, **kwargs):
                    x = real(coordinator, *args, **kwargs)
                    if field == 'source':
                        return replace(x, source_experience_id='wrong')
                    if field == 'occurrence':
                        return replace(x, execution_occurrence_id=str(uuid4()))
                    if field == 'prediction':
                        return replace(x, predicted_effect=replace(x.predicted_effect,
                            delta_values=(0., 0., 0.)))
                    return replace(x, target_core=replace(x.target_core, source_proposal_id='wrong'))
                with patch.object(NFPRememberedActionExecutionCoordinator, 'execute', corrupt):
                    with self.assertRaises(ValueError):
                        owner.observe()
                self.assertEqual(owner.state, 'stopped')
                self.assertIsNone(owner.apply())
                self.assertFalse(owner.attempted)


    def test_feedback_for_unselected_action_is_rejected(self):
        # Corrupt selector/activation continuity in a negative arm only.
        real_select = DecisionSelector.select_native
        def corrupt(selector, candidates):
            return replace(real_select(selector, candidates), activation_id='unselected')
        session, owner = self.episode()
        with patch.object(DecisionSelector, 'select_native', corrupt):
            with self.assertRaisesRegex(ValueError, 'selection_chain'):
                owner.observe()
        self.assertIsNone(owner.apply())


    def test_conflicting_actual_provenance_and_unretained_copy(self):
        real = ShortMemory.snapshot
        for fault in ('copy', 'actual'):
            session, owner = self.episode()
            def corrupt(memory):
                ts = real(memory)
                if not ts:
                    return ts
                t = ts[0]
                if fault == 'copy':
                    return (replace(t),)
                frame = replace(t.after_sensory_window.frames[0], values=(1., 0., 0.))
                return (replace(t, after_sensory_window=replace(
                    t.after_sensory_window, frames=(frame,))),)
            with patch.object(ShortMemory, 'snapshot', corrupt):
                with self.assertRaisesRegex(ValueError, 'execution_not_confirmed'):
                    owner.observe()
            self.assertIsNone(owner.apply())


    def test_guard_denial(self):
        session, owner = self.observed(mode='recovery')
        self.assertIn('guard_denied', owner.reason)
        self.assertEqual(owner.physical_calls, 0)
        self.assertIsNone(owner.apply())
        self.assertEqual(len(session.components.short_memory), 0)


    def test_uncertain_world_apply_no_feedback_or_retry(self):
        real = SyntheticClosedLoopVisualWorld.apply_actuator_signal
        def uncertain(world, signal):
            real(world, signal)
            raise OSError('lost physical acknowledgement')
        session, owner = self.episode()
        with patch.object(SyntheticClosedLoopVisualWorld, 'apply_actuator_signal', uncertain):
            owner.observe()
        self.assertEqual(owner.physical_calls, 1)
        self.assertEqual(session.components.world.hidden_position, (0, 2))
        self.assertEqual(owner.state, 'stopped')
        self.assertIsNone(owner.apply())
        self.assert_no_retry(owner)


    def test_policy_denial_is_terminal(self):
        session, owner = self.observed(profile='safe_demo')
        old = owner.path.read_bytes()
        owner.apply()
        self.assertEqual(owner.result.status.value, 'denied_by_policy')
        self.assertEqual(owner.path.read_bytes(), old)
        self.assert_no_retry(owner)


    def test_duplicate_and_altered_event_source_conflicts_without_mutation(self):
        session, owner = self.observed()
        owner.apply()
        old = owner.path.read_bytes()
        writer = NFPFeedbackApplyWriter(owner.path, owner._writer.memory_mutation_policy)
        evidence = owner.evaluation.evidence
        # Explicit negative replay probe outside owner's single-attempt API.
        self.assertEqual(writer.apply(evidence).status.value, 'already_applied')
        for altered in (replace(evidence, agreement_threshold=.9),
                        replace(evidence, source_experience_id='wrong')):
            self.assertEqual(writer.apply(altered).status.value, 'event_conflict')
        self.assertEqual(owner.path.read_bytes(), old)
        self.assert_no_retry(owner)


    def test_stale_target_is_rejected_by_existing_writer(self):
        session, owner = self.observed()
        evidence = owner.evaluation.evidence
        bad = replace(evidence, target_core=replace(evidence.target_core,
                                                  source_proposal_id='stale'))
        old = owner.path.read_bytes()
        result = owner._writer.apply(bad)  # negative writer-boundary probe only
        self.assertEqual(result.status.value, 'stale_or_changed_target')
        self.assertEqual(owner.path.read_bytes(), old)


    def test_lost_readback_ack_reconciles_without_retry(self):
        session, owner = self.observed()
        def fail(stage):
            if stage == 'post_replace_readback':
                raise OSError('lost readback')
        owner._writer.failure_hook = fail
        owner.apply()
        self.assertEqual(owner.result.status.value, 'readback_failed')
        self.assertEqual(owner.state, 'reconciled_applied')
        self.assertEqual(owner.recovery.record, owner.result.intended_record)
        self.assertEqual(authoritative_record(owner.path, self.fixture.records[0].record_id)[0], owner.recovery.record)
        self.assert_no_retry(owner)


    def test_unresolved_readback_is_terminal(self):
        session, owner = self.observed()
        def fail(stage):
            if stage == 'post_replace_readback':
                # Negative storage corruption, never a positive world outcome.
                owner.path.write_text('{invalid')
                raise OSError('lost readback with corrupted store')
        owner._writer.failure_hook = fail
        owner.apply()
        self.assertEqual(owner.state, 'reconciliation_conflict')
        self.assertIsNone(owner.recovery.record)
        self.assert_no_retry(owner)


    def test_write_failed_after_replace_stops_despite_retry_safe(self):
        session, owner = self.observed()
        with patch.object(ExpSMStoreTransaction, '_fsync_parent_if_supported',
                          side_effect=OSError('directory fsync failed')):
            owner.apply()
        self.assertEqual(owner.result.status.value, 'write_failed')
        self.assertTrue(owner.result.retry_safe)  # existing API caveat reproduced
        self.assertEqual(owner.state, 'persistence_uncertain')
        self.assertIsNone(owner.recovery)
        record, state = authoritative_record(owner.path, self.fixture.records[0].record_id)
        self.assertEqual(record, owner.result.intended_record)
        self.assertEqual(len(state.native_feedback_receipts['by_event_key']), 1)
        with self.assertRaises(ValueError):
            reconcile_nfp_feedback_readback_failure(owner.path, owner.result)
        self.assert_no_retry(owner)


    def test_pre_replace_write_failure_also_never_retries(self):
        session, owner = self.observed()
        old = owner.path.read_bytes()
        def fail(stage):
            if stage == 'pre_replace':
                raise OSError('before replace')
        owner._writer.failure_hook = fail
        owner.apply()
        self.assertEqual(owner.result.status.value, 'write_failed')
        self.assertEqual(owner.path.read_bytes(), old)
        self.assertEqual(owner.state, 'persistence_uncertain')
        self.assert_no_retry(owner)


    def test_primary_apply_and_recovery_errors_preserved(self):
        for boundary in ('apply', 'recovery'):
            session, owner = self.observed()
            error = MemoryError('primary ' + boundary)
            if boundary == 'apply':
                context = patch.object(owner._writer, 'apply', side_effect=error)
            else:
                def fail(stage):
                    if stage == 'post_replace_readback':
                        raise OSError('lost ack')
                owner._writer.failure_hook = fail
                context = patch('scenarios.native_competing_experience_selection.reconcile_nfp_feedback_readback_failure',
                                side_effect=error)
            with context:
                with self.assertRaises(MemoryError) as caught:
                    owner.apply()
            self.assertIs(caught.exception, error)
            self.assertEqual(owner.state, 'persistence_uncertain')
            self.assert_no_retry(owner)


    def test_session_release_after_binding_allows_apply_without_world_retention(self):
        session, owner = self.observed()
        sr, wr = weakref.ref(session), weakref.ref(session.components.world)
        del session
        gc.collect()
        self.assertIsNone(sr())
        self.assertIsNone(wr())
        owner.apply()
        self.assertEqual(owner.state, 'confirmed_applied')


    def test_release_before_binding_fails_closed(self):
        session, owner = self.episode()
        ref = weakref.ref(session)
        del session
        gc.collect()
        self.assertIsNone(ref())
        self.assertIsNone(owner.observe())
        self.assertEqual(owner.reason, 'session_released_before_binding')
        self.assertIsNone(owner.apply())


    def test_retention_loss_and_expiry_fail_closed(self):
        real = NativeDeliverySession.run
        for tick in (12, 100):
            session, owner = self.episode()
            def expire(s, **options):
                result = real(s, **options)
                s.components.short_memory.prune(tick)
                return result
            with patch.object(NativeDeliverySession, 'run', expire):
                owner.observe()
            self.assertEqual(owner.reason, 'missing_retained_actual_t_plus_1')
            self.assertIsNone(owner.apply())


    def test_single_observe_evaluation_apply_budgets(self):
        session, owner = self.episode()
        with patch.object(NFPFeedbackEvaluator, 'evaluate', wraps=NFPFeedbackEvaluator.evaluate) as evaluate:
            owner.observe()
            owner.observe()
            owner.apply()
            owner.apply()
            self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(len(session.records), 2)
        self.assertEqual(len(session.components.short_memory), 1)
        self.assertEqual(session.delivery.journal.maxlen, 128)
        self.assert_no_retry(owner)


    def test_missing_delivery_provenance_is_rejected(self):
        real = NativeDeliverySession.run
        session, owner = self.episode()
        def lose_journal(s, **options):
            result = real(s, **options)
            s.delivery.journal.clear()
            return result
        with patch.object(NativeDeliverySession, 'run', lose_journal):
            with self.assertRaisesRegex(ValueError, 'missing_sensor_provenance'):
                owner.observe()
        self.assertIsNone(owner.apply())


    def test_observation_exception_keeps_original_error_and_terminal_stop(self):
        session, owner = self.episode()
        error = MemoryError('observation interrupted')
        with patch.object(SyntheticClosedLoopVisualWorld, 'snapshot', side_effect=error):
            with self.assertRaises(MemoryError) as caught:
                owner.observe()
        self.assertIs(caught.exception, error)
        self.assertEqual(owner.state, 'stopped')
        self.assertIn('MemoryError: observation interrupted', owner.reason)
        self.assertIsNone(owner.apply())
        self.assert_no_retry(owner)


    def test_broken_str_observation_preserves_identity_traceback_and_stop(self):
        for boundary in ('sensor', 'evaluator'):
            session, owner = self.episode()
            states = []
            primary = BrokenDiagnosticFailure(lambda: states.append((owner.state, owner.reason)))
            def primary_observation_failure(*args, **kwargs):
                raise primary
            target, name = ((SyntheticClosedLoopVisualWorld, 'snapshot') if boundary == 'sensor'
                            else (NFPFeedbackEvaluator, 'evaluate'))
            with patch.object(target, name, primary_observation_failure):
                self.assert_primary_traceback(owner.observe, primary, 'primary_observation_failure')
            self.assertEqual(states, [('stopped', 'observation_exception')])
            self.assertEqual(owner.physical_calls, int(boundary == 'evaluator'))
            self.assertIsNone(owner.apply())
            self.assert_terminal_diagnostics(owner, 'stopped')


    def test_broken_str_post_replace_preserves_primary_and_uncertainty(self):
        session, owner = self.observed()
        states = []
        primary = BrokenDiagnosticFailure(lambda: states.append((owner.state, owner.reason)))
        def primary_post_replace_failure(stage):
            if stage == 'post_replace_readback':
                raise primary
        owner._writer.failure_hook = primary_post_replace_failure
        with patch.object(owner._writer, 'apply', wraps=owner._writer.apply) as apply:
            self.assert_primary_traceback(owner.apply, primary, 'primary_post_replace_failure')
            owner.apply()
            self.assertEqual(apply.call_count, 1)
        self.assertEqual(states, [('persistence_uncertain', 'persistence_exception')])
        self.assertTrue(owner.attempted)
        self.assertIsNone(owner.result)
        self.assertIsNone(owner.readback)
        self.assertIsNone(owner.recovery)
        # Diagnostic authoritative read proves this injected case's persisted
        # bytes; it does not change the owner's unknown outcome or authorize retry.
        record, state = authoritative_record(owner.path, self.fixture.records[0].record_id)
        self.assertEqual(record.operational.hits, 1)
        self.assertEqual(len(state.native_feedback_receipts['by_event_key']), 1)
        owner._writer.failure_hook = None
        self.assert_terminal_diagnostics(owner, 'persistence_uncertain')


    def test_broken_str_reconciliation_preserves_primary_and_first_reason(self):
        for first_reason in ('', 'first reconciliation STOP'):
            session, owner = self.observed()
            states = []
            primary = BrokenDiagnosticFailure(lambda: states.append((owner.state, owner.reason)))
            def lost_ack(stage):
                if stage == 'post_replace_readback':
                    raise OSError('lost readback acknowledgement')
            def primary_reconciliation_failure(*args):
                if first_reason:
                    owner.reason = first_reason
                raise primary
            owner._writer.failure_hook = lost_ack
            with patch('scenarios.native_competing_experience_selection.reconcile_nfp_feedback_readback_failure',
                       primary_reconciliation_failure):
                self.assert_primary_traceback(owner.apply, primary, 'primary_reconciliation_failure')
            self.assertEqual(owner.result.status.value, 'readback_failed')
            self.assertIsNone(owner.recovery)
            self.assertEqual(owner.reason, first_reason or 'persistence_exception')
            self.assertEqual(states, [] if first_reason else
                             [('persistence_uncertain', 'persistence_exception')])
            owner._writer.failure_hook = None
            self.assert_terminal_diagnostics(owner, 'persistence_uncertain')


    def test_diagnostic_helper_failure_cannot_mask_primary_or_unset_stop(self):
        for boundary in ('observe', 'apply', 'reconciliation'):
            session, owner = self.episode()
            primary = MemoryError('primary operation failure')
            if boundary != 'observe':
                owner.observe()
            def primary_boundary_failure(*args, **kwargs):
                raise primary
            states = []
            def secondary_helper_failure(*args):
                states.append((owner.state, owner.reason))
                raise KeyboardInterrupt('diagnostic helper interrupted')
            if boundary == 'observe':
                context = patch.object(NFPFeedbackEvaluator, 'evaluate', primary_boundary_failure)
            elif boundary == 'apply':
                context = patch.object(owner._writer, 'apply', primary_boundary_failure)
            else:
                def lost_ack(stage):
                    if stage == 'post_replace_readback':
                        raise OSError('lost acknowledgement')
                owner._writer.failure_hook = lost_ack
                context = patch('scenarios.native_competing_experience_selection.reconcile_nfp_feedback_readback_failure',
                                primary_boundary_failure)
            with context, patch('scenarios.native_competing_experience_selection._exception_reason',
                                side_effect=secondary_helper_failure) as helper:
                self.assert_primary_traceback(owner.observe if boundary == 'observe' else owner.apply,
                                              primary, 'primary_boundary_failure')
                self.assertEqual(helper.call_count, 1)
            self.assertEqual(states, [('stopped', 'observation_exception')]
                             if boundary == 'observe' else
                             [('persistence_uncertain', 'persistence_exception')])
            owner._writer.failure_hook = None
            self.assert_terminal_diagnostics(owner, 'stopped' if boundary == 'observe'
                                             else 'persistence_uncertain')


    def test_malicious_diagnostic_text_reproduction_observation_apply(self):
        for boundary in ('observe', 'apply'):
            session, owner = self.episode()
            primary = MaliciousDiagnosticFailure()
            reason = _exception_reason(primary, 'safe fallback')
            self.assertIs(type(reason), str)
            self.assertEqual(reason, 'safe fallback')
            self.assertIsNot(reason, primary)
            if boundary == 'observe':
                def primary_malicious_observation(*args):
                    raise primary
                with patch.object(NFPFeedbackEvaluator, 'evaluate', primary_malicious_observation):
                    self.assert_primary_traceback(owner.observe, primary, 'primary_malicious_observation')
            else:
                owner.observe()
                def primary_malicious_post_replace(stage):
                    if stage == 'post_replace_readback':
                        raise primary
                owner._writer.failure_hook = primary_malicious_post_replace
                with patch.object(owner._writer, 'apply', wraps=owner._writer.apply) as apply:
                    self.assert_primary_traceback(owner.apply, primary, 'primary_malicious_post_replace')
                    owner.apply()
                    self.assertEqual(apply.call_count, 1)
                record, state = authoritative_record(owner.path, self.fixture.records[0].record_id)
                self.assertEqual(record.operational.hits, 1)
                self.assertEqual(len(state.native_feedback_receipts['by_event_key']), 1)
                self.assertIsNone(owner.result)
                self.assertIsNone(owner.readback)
                owner._writer.failure_hook = None
            self.assertEqual(owner.physical_calls, 1)
            self.assertEqual(primary.operations, [])
            self.assert_terminal_diagnostics(owner, 'stopped' if boundary == 'observe'
                                             else 'persistence_uncertain')


    def test_malicious_diagnostics_release_session_world_and_payload(self):
        def error_scope(boundary):
            session, owner = self.episode()
            primary = MaliciousDiagnosticFailure()
            refs = tuple(weakref.ref(value) for value in
                         (session, session.components.world, primary, primary.payload))
            def primary_retention_failure(*args):
                raise primary
            if boundary == 'observe':
                context = patch.object(NFPFeedbackEvaluator, 'evaluate', primary_retention_failure)
            else:
                owner.observe()
                def post_replace(stage):
                    if stage == 'post_replace_readback':
                        if boundary == 'apply':
                            raise primary
                        raise OSError('lost acknowledgement')
                owner._writer.failure_hook = post_replace
                if boundary == 'apply':
                    from contextlib import nullcontext
                    context = nullcontext()
                else:
                    context = patch('scenarios.native_competing_experience_selection.reconcile_nfp_feedback_readback_failure',
                                    primary_retention_failure)
            with context:
                self.assert_primary_traceback(owner.observe if boundary == 'observe' else owner.apply,
                    primary, 'post_replace' if boundary == 'apply' else 'primary_retention_failure')
            owner._writer.failure_hook = None  # release the negative injector's closure
            self.assertEqual(primary.operations, [])
            self.assert_terminal_diagnostics(owner, 'stopped' if boundary == 'observe'
                                             else 'persistence_uncertain')
            # Do not return primary/traceback/patch objects; only weak refs and owner.
            return owner, refs

        for boundary in ('observe', 'apply', 'reconciliation'):
            owner, refs = error_scope(boundary)
            gc.collect()
            self.assertTrue(all(ref() is None for ref in refs), boundary)
            self.assertIs(type(owner.reason), str)
            self.assertTrue(1 <= len(owner.reason) <= 256)
            self.assert_no_retry(owner)


    def test_diagnostic_components_require_exact_bounded_strings(self):
        primary = MaliciousDiagnosticFailure()
        evil = MaliciousDiagnosticText(primary)
        for value in (evil, primary, primary.payload, None, '', 'x' * 4096, 'plain text'):
            for fallback in (evil, primary, '', 'x' * 4096, 'safe fallback'):
                result = _bounded_reason(value, fallback)
                self.assertIs(type(result), str)
                self.assertTrue(1 <= len(result) <= 256)
        self.assertEqual(_bounded_reason('plain text'), 'plain text')
        self.assertEqual(_bounded_reason('x' * 4096), 'x' * 256)
        self.assertEqual(_bounded_reason('', 'safe fallback'), 'safe fallback')
        for error in (ValueError('plain text'), ValueError(''), ValueError('x' * 4096), primary):
            result = _exception_reason(error, evil)
            self.assertIs(type(result), str)
            self.assertTrue(1 <= len(result) <= 256)
        calls = []
        class UntrustedName(type):
            def __getattribute__(cls, key):
                if key == '__name__':
                    return evil
                return super().__getattribute__(key)
        class OddFailure(BaseException, metaclass=UntrustedName):
            def __str__(self):
                calls.append('str')
                return 'should not format after invalid label'
        self.assertEqual(_exception_reason(OddFailure(), 'safe fallback'), 'safe fallback')
        self.assertEqual(calls, [])
        self.assertEqual(primary.operations, [])


    def test_invalid_helper_results_fail_closed_at_owner_boundary(self):
        for boundary in ('observe', 'apply', 'reconciliation'):
            primary = MaliciousDiagnosticFailure()
            for diagnostic in (primary, MaliciousDiagnosticText(primary), '', 'x' * 4096, 'safe text'):
                session, owner = self.episode()
                def primary_invalid_diagnostic(*args):
                    raise primary
                if boundary == 'observe':
                    context = patch.object(NFPFeedbackEvaluator, 'evaluate', primary_invalid_diagnostic)
                else:
                    owner.observe()
                    if boundary == 'apply':
                        context = patch.object(owner._writer, 'apply', primary_invalid_diagnostic)
                    else:
                        def lost_ack(stage):
                            if stage == 'post_replace_readback':
                                raise OSError('lost acknowledgement')
                        owner._writer.failure_hook = lost_ack
                        context = patch('scenarios.native_competing_experience_selection.reconcile_nfp_feedback_readback_failure',
                                        primary_invalid_diagnostic)
                with context, patch('scenarios.native_competing_experience_selection._exception_reason',
                                    return_value=diagnostic):
                    self.assert_primary_traceback(owner.observe if boundary == 'observe' else owner.apply,
                                                  primary, 'primary_invalid_diagnostic')
                owner._writer.failure_hook = None
                self.assert_terminal_diagnostics(owner, 'stopped' if boundary == 'observe'
                                                 else 'persistence_uncertain')
                self.assertEqual(primary.operations, [])


    def test_stop_reason_boundary_and_first_reason(self):
        primary = MaliciousDiagnosticFailure()
        for value in (MaliciousDiagnosticText(primary), primary, '', 'x' * 4096, 'first stop'):
            session, owner = self.episode()
            owner._stop(value)
            first = owner.reason
            owner._stop('later diagnostic')
            self.assertEqual(owner.reason, first)
            self.assert_terminal_diagnostics(owner, 'stopped')
        self.assertEqual(primary.operations, [])


    def test_writer_and_reconciliation_diagnostic_snapshots_release_payload(self):
        def error_scope(boundary):
            session, owner = self.observed()
            primary = MaliciousDiagnosticOSError()
            refs = tuple(weakref.ref(value) for value in
                         (session, session.components.world, primary, primary.payload))
            def fail(stage):
                if boundary == 'writer' and stage == 'pre_replace':
                    raise primary
                if boundary == 'reconciliation' and stage == 'post_replace_readback':
                    raise OSError('lost acknowledgement')
            owner._writer.failure_hook = fail
            def failing_read(*args):
                raise primary
            real_reconcile = reconcile_nfp_feedback_readback_failure
            def reconcile_with_failed_read(*args):
                with patch.object(ExpSMStoreTransaction, 'load_state_strict', failing_read):
                    return real_reconcile(*args)
            if boundary == 'writer':
                from contextlib import nullcontext
                context = nullcontext()
            else:
                context = patch('scenarios.native_competing_experience_selection.reconcile_nfp_feedback_readback_failure',
                                reconcile_with_failed_read)
            with context:
                owner.apply()
            owner._writer.failure_hook = None
            self.assertIs(type(owner.result.reason), str)
            self.assertTrue(1 <= len(owner.result.reason) <= 256)
            if boundary == 'writer':
                self.assertEqual(owner.result.status.value, 'write_failed')
                self.assert_terminal_diagnostics(owner, 'persistence_uncertain')
            else:
                self.assertEqual(owner.result.status.value, 'readback_failed')
                self.assertIs(type(owner.recovery.reason), str)
                self.assertTrue(1 <= len(owner.recovery.reason) <= 256)
                self.assert_terminal_diagnostics(owner, 'reconciliation_conflict')
            self.assertEqual(primary.operations, [])
            return owner, refs
        for boundary in ('writer', 'reconciliation'):
            owner, refs = error_scope(boundary)
            gc.collect()
            self.assertTrue(all(ref() is None for ref in refs), boundary)
            self.assert_no_retry(owner)


    def test_two_independent_acquisitions_and_local_proposal_ids(self):
        a, b = self.fixture.records
        ta, tb = self.fixture.traces
        self.assertNotEqual(a.record_id, b.record_id)
        self.assertEqual(a.context, b.context)
        self.assertEqual(a.context.frames, ((0., 1., 0.),))
        self.assertEqual((a.action.values, b.action.values), (RIGHT, LEFT))
        self.assertEqual((a.effect.delta_values, b.effect.delta_values),
                         ((0., -1., 1.), (1., -1., 0.)))
        # Equal local proposal IDs must neither merge nor suppress either CREATE.
        self.assertEqual(a.creation_metadata.source_proposal_id,
                         b.creation_metadata.source_proposal_id)
        for trace in (ta, tb):
            self.assertEqual(sorted(trace.support_counts), [1, 2])
            self.assertEqual(len(set(trace.occurrences)), 3)
            self.assertEqual(len(set(trace.evidence_ids)), 3)
            self.assertEqual((trace.create_status, trace.readback_status),
                             ('created', 'confirmed_persisted'))
            for provenance in trace.exploratory_provenance:
                self.assertEqual(provenance.session_id, trace.session_id)
                self.assertIn(provenance.execution_occurrence_id, trace.occurrences)
        self.assertNotEqual(ta.session_id, tb.session_id)
        self.assertNotEqual(ta.request_id, tb.request_id)
        self.assertTrue(set(ta.occurrences).isdisjoint(tb.occurrences))
        self.assertTrue(set(ta.evidence_ids).isdisjoint(tb.evidence_ids))
        self.assertEqual(len(json.loads(self.fixture.store_bytes)['experience']), 2)
        for name in ('A', 'B'):
            self.assertEqual((self.root / 'acquired' / ('training-' + name)
                              / 'ExpSM.json').read_bytes(), EMPTY)

    def test_c0_c1_c2_c3_feedback_propagation_and_physical_alternative(self):
        a, b = self.fixture.records
        initial_order = (a.record_id, b.record_id)
        baseline = self.fixture.store_bytes
        # C0 is an independent ordinary session, including real execution but no APPLY.
        c0_session, c0 = self.observed(enabled=False)
        self.assertEqual(c0.retrieval_order, initial_order)
        self.assertEqual(c0.activation_order, initial_order)
        self.assertEqual(c0.scores, ((a.record_id, .775), (b.record_id, .775)))
        self.assertEqual(c0.selected_source, a.record_id)
        self.assertEqual(c0.path.read_bytes(), baseline)
        # C1: the genuine chain selects A; only its evaluator evidence reaches writer.
        c1_session, c1 = self.observed()
        self.assertEqual(c1.selected_source, a.record_id)
        self.assertEqual(c1.evaluation.status.value, 'hit')
        self.assertEqual(c1.evaluation.effect_similarity, 1.)
        self.assertEqual(c1.evaluation.evidence.actual_effect.delta_values, (0., -1., 1.))
        self.assertEqual(c1.executed_action, RIGHT)
        self.assertEqual(c1.actual_values, (0., 0., 1.))
        with patch.object(c1._writer, 'apply', wraps=c1._writer.apply) as writer:
            c1.apply()
            c1.apply()
            self.assertEqual(writer.call_count, 1)
            self.assertIs(writer.call_args.args[0], c1.evaluation.evidence)
        self.assertEqual(c1.state, 'confirmed_applied')
        updated_a, state = authoritative_record(c1.path, a.record_id)
        self.assertEqual(authoritative_record(c1.path, b.record_id)[0], b)
        self.assertEqual((updated_a.operational.hits, updated_a.operational.misses,
                          updated_a.operational.confidence, updated_a.operational.repeatability),
                         (1, 0, .382, .425))
        self.assertEqual(updated_a.context, a.context)
        self.assertEqual(updated_a.action, a.action)
        self.assertEqual(updated_a.effect, a.effect)
        self.assertEqual(set(state.experience), set(initial_order))
        receipt = state.native_feedback_receipts['by_event_key'][c1.result.event_key_digest]
        self.assertEqual(receipt['source_experience_id'], a.record_id)
        self.assertEqual(receipt['event_key']['source_experience_id'], a.record_id)
        self.assertEqual(receipt['evidence_digest'], c1.result.evidence_digest)
        self.assertEqual(state.native_feedback_receipts['execution_occurrence_index'],
                         {c1.execution_occurrence_id: c1.result.event_key_digest})
        # Fresh center comparison after persisted feedback, unchanged native parameters.
        post_session, post = self.observed(store_bytes=c1.path.read_bytes(), enabled=False)
        self.assertEqual(post.retrieval_order, initial_order)
        self.assertEqual(post.activation_order, (b.record_id, a.record_id))
        self.assertEqual(post.selected_source, b.record_id)
        self.assertEqual(dict(post.scores)[b.record_id], .775)
        self.assertAlmostEqual(dict(post.scores)[a.record_id], .7568166666666667)
        self.assertGreater(min(dict(post.scores).values()), DEFAULT_SELECTOR)
        # C2: same baseline bytes, actual action/consequence and evaluator, no writer call.
        c2_session, c2 = self.episode(store_bytes=baseline, enabled=False)
        with patch.object(c2._writer, 'apply', side_effect=AssertionError('C2 APPLY')) as writer:
            c2.observe()
            self.assertIsNone(c2.apply())
            writer.assert_not_called()
        self.assertEqual(c2.evaluation.status.value, 'hit')
        self.assertEqual(c2.path.read_bytes(), baseline)
        self.assertEqual(c2.executed_action, c1.executed_action)
        self.assertEqual(c2.actual_values, c1.actual_values)
        self.assertEqual(ExpSMStoreTransaction(c2.path).load_state_strict().native_feedback_receipts,
                         ExpSMStoreTransaction(c0.path).load_state_strict().native_feedback_receipts)
        again_session, again = self.observed(store_bytes=c2.path.read_bytes(), enabled=False)
        self.assertEqual(again.selected_source, a.record_id)
        self.assertEqual(again.scores, c0.scores)
        # C3: separate fresh session, ordinary B selection through real physical T+1.
        c3_session, c3 = self.observed(store_bytes=c1.path.read_bytes(), enabled=False)
        self.assertEqual(c3.selected_source, b.record_id)
        self.assertEqual(c3.executed_action, LEFT)
        self.assertEqual(c3.actual_values, (1., 0., 0.))
        self.assertEqual(c3.physical_calls, 1)
        self.assertEqual(c3_session.components.world.hidden_position, (0, 0))
        execution = c3_session.records[0].execution
        recent = c3_session.components.short_memory.snapshot()[0]
        self.assertEqual(execution.source_experience_id, b.record_id)
        self.assertEqual(execution.execution_occurrence_id, recent.execution_occurrence_id)
        self.assertIs(c3_session.records[1].recent, recent)
        self.assertEqual((recent.action_tick, recent.observation_tick), (0, 1))
        self.assertTrue(execution.guard_passed)
        self.assertIsNone(execution.exploratory_intent)
        self.assertEqual(c3.path.read_bytes(), c1.path.read_bytes())
        sessions = (c0_session, c1_session, post_session, c2_session, again_session, c3_session)
        self.assertEqual(len({s.session_id for s in sessions}), len(sessions))
        for s, owner in zip(sessions, (c0, c1, post, c2, again, c3)):
            self.assertIsNone(s.exploration)
            self.assertEqual(owner.context_values, (0., 1., 0.))
            self.assertEqual(s.components.selector.decision_threshold, .35)
            self.assertEqual(s.components.system_state.mode, 'active')
        print(json.dumps({'C0': c0.scores, 'C1': post.scores, 'C2': again.scores,
                          'C3_source': c3.selected_source, 'C3_action': c3.executed_action,
                          'C3_actual': c3.actual_values, 'receipt_source': receipt['source_experience_id']}))

    def training(self, *, actions=3, authorized=True, profile='mutating_memory'):
        self.count += 1
        root = self.root / ('negative-training-' + str(self.count))
        root.mkdir()
        destination = root / 'competition.json'
        destination.write_bytes(EMPTY)
        s, path = make_session(root / 'reader', training='A', actions=actions,
                               authorized=authorized)
        w = NFPExpSMCreateWriter(destination, policy_for_profile(
            profile, memory_root=root, memory_is_temporary=True))
        o = BoundedNativeAcquisition(s, isolated_root=root, writer=w)
        return s, o, w, destination

    def test_insufficient_support_and_duplicate_occurrence(self):
        s, o, writer, path = self.training(actions=1)
        s.run()
        t, = s.components.short_memory.snapshot()
        admitted = o.admit(t)
        self.assertEqual(admitted.status, 'admitted')
        self.assertEqual(o.admit(t).status, 'duplicate')
        self.assertEqual(o.candidates[0].support_count, 1)
        o.seal()
        self.assertIsNone(o.prepare(admitted.candidate_id))
        self.assertIsNone(o.create(test_owner_authorized=True))
        self.assertEqual(path.read_bytes(), EMPTY)

    def test_acquisition_occurrence_conflict_and_no_retry(self):
        s, o, writer, path = self.training()
        s.run()
        t = s.components.short_memory.snapshot()[0]
        self.assertEqual(o.admit(t).status, 'admitted')
        altered = replace(t, after_sensory_window=replace(t.after_sensory_window,
            frames=(replace(t.after_sensory_window.frames[0], values=(0., 1., 0.)),)))
        self.assertEqual(o.admit(altered).status, 'stopped_occurrence_conflict')
        self.assertIsNone(o.create(test_owner_authorized=True))
        self.assertEqual(path.read_bytes(), EMPTY)

    def test_full_set_conflict_from_owned_sensor_fault_is_terminal(self):
        # Negative-only sensor fault; transitions/evidence still pass the real
        # delivery, ShortMemory, factory and admission path. No fabricated evidence.
        s, o, writer, path = self.training()
        real = SyntheticClosedLoopVisualWorld.snapshot
        def contradictory(world):
            snapshot = real(world)
            return replace(snapshot, values=(0., 1., 0.)) if world.current_tick == 3 else snapshot
        with patch.object(SyntheticClosedLoopVisualWorld, 'snapshot', contradictory):
            s.run()
        results = [o.admit(t) for t in s.components.short_memory.snapshot()]
        self.assertEqual([r.status for r in results], ['admitted'] * 3)
        o.seal()
        self.assertIsNone(o.prepare(results[0].candidate_id))
        self.assertEqual(o.state, 'stopped_effect_conflict')
        self.assertEqual(path.read_bytes(), EMPTY)

    def test_missing_exploratory_authorization_produces_no_evidence(self):
        s, o, writer, path = self.training(authorized=False)
        s.run()
        self.assertEqual(len(s.components.short_memory), 0)
        self.assertEqual(s.components.world.hidden_position, (0, 1))
        o.seal()
        self.assertIsNone(o.create(test_owner_authorized=True))
        self.assertEqual(path.read_bytes(), EMPTY)

    def test_create_requires_separate_owner_authority_and_writer_policy(self):
        s, o, writer, path = self.training(profile='safe_demo')
        s.run()
        for t in s.components.short_memory.snapshot():
            self.assertEqual(o.admit(t).status, 'admitted')
        o.seal()
        supported = next(c for c in o.candidates if c.support_count == 2)
        self.assertIsNotNone(o.prepare(supported.candidate_id))
        self.assertIsNone(o.create())
        self.assertFalse(o.attempted)
        with patch.object(writer, 'create', wraps=writer.create) as create:
            result = o.create(test_owner_authorized=True)
            o.create(test_owner_authorized=True)
            self.assertEqual(create.call_count, 1)
        self.assertEqual(result.status.value, 'denied_by_policy')
        self.assertEqual(path.read_bytes(), EMPTY)

    def test_absent_b_does_not_fabricate_switch(self):
        # Ablation comes from a genuine single CREATE, never deleting JSON records.
        s, o, writer, path = self.training()
        s.run()
        for t in s.components.short_memory.snapshot():
            o.admit(t)
        o.seal()
        o.prepare(next(c for c in o.candidates if c.support_count == 2).candidate_id)
        created = o.create(test_owner_authorized=True)
        s1, p1 = make_session(self.root / 'ablated', store_bytes=path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'two distinct'):
            CompetingEpisode(s1, root=self.root, acquired_records=(created.record,))
        # Existing one-record owner is used within its actual invariant for this
        # ablation, not to implement the two-record experiment.
        from scenarios.native_outcome_feedback_loop import FeedbackEpisode
        single = FeedbackEpisode(s1, root=self.root, acquired_record=created.record)
        single.observe()
        single.apply()
        self.assertEqual(single.state, 'confirmed_applied')
        s2, p2 = make_session(self.root / 'ablated-after', store_bytes=p1.read_bytes())
        s2.run()
        self.assertEqual(s2.records[0].execution.source_experience_id, created.record_id)
        self.assertEqual(s2.records[0].execution.action_frame.values, RIGHT)
        self.assertEqual(len(json.loads(p2.read_bytes())['experience']), 1)

    def test_feedback_cannot_be_attributed_to_eligible_unselected_b(self):
        real = NFPRememberedActionExecutionCoordinator.execute
        session, owner = self.episode()
        b = self.fixture.records[1]
        def wrong_source(coordinator, *args, **options):
            executed = real(coordinator, *args, **options)
            return replace(executed, source_experience_id=b.record_id)
        with patch.object(NFPRememberedActionExecutionCoordinator, 'execute', wrong_source):
            with self.assertRaisesRegex(ValueError, 'source_mismatch'):
                owner.observe()
        self.assertIsNone(owner.apply())
        self.assertEqual(owner.path.read_bytes(), self.fixture.store_bytes)

    def test_isolation_and_fixed_parameters(self):
        temporary = Path(tempfile.gettempdir()).resolve()
        for root in (temporary, temporary.parent):
            with patch.object(Path, 'mkdir', side_effect=AssertionError('write')):
                with self.assertRaises(ValueError):
                    make_session(root)
        with self.assertRaises(ValueError):
            make_session(self.root / 'badtraining', training='C')
        session, owner = self.episode()
        session.components.selector.decision_threshold = .4
        with self.assertRaises(ValueError):
            CompetingEpisode(session, root=self.root, acquired_records=self.fixture.records)
        session.components.selector.decision_threshold = .35
        session.components.retriever.store_path = ROOT / 'Memory/ExpSM/ExpSM_data.json'
        with self.assertRaisesRegex(ValueError, 'isolated'):
            CompetingEpisode(session, root=self.root, acquired_records=self.fixture.records)


if __name__ == '__main__':
    unittest.main(verbosity=2)
