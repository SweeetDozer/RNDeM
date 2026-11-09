"""RND-024 behavioral verification; positive arms use unmodified owned worlds."""
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

from scenarios.native_outcome_feedback_loop import (
    acquire, make_session, FeedbackEpisode, authoritative_record,
    NFPFeedbackApplyWriter, NFPRememberedActionExecutionCoordinator,
    ExpSMStoreTransaction, DEFAULT_SELECTOR, SENSITIVITY_SELECTOR,
    _bounded_reason, _exception_reason,
)
from clc.context.short_memory import ShortMemory
from clc.runtime.native_bounded_delivery import NativeDeliverySession
from clc.action.decision_selector import DecisionSelector
from clc.expsm.nfp_native_feedback import NFPFeedbackEvaluator
from clc.expsm.nfp_native_feedback_apply import reconcile_nfp_feedback_readback_failure
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld


def inventory():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'Memory').rglob('*') if p.is_file()}


class BrokenDiagnosticFailure(BaseException):
    """Negative-only interrupt escaping production OSError/ValueError catches."""

    def __init__(self, observe_format):
        self.observe_format = observe_format

    def __str__(self):
        self.observe_format()
        raise RuntimeError('secondary diagnostic failure')


class DiagnosticPayload:
    def __init__(self):
        self.data = bytearray(65536)


class MaliciousDiagnosticText(str):
    """Original review reproduction plus traps for other scalar operations."""
    def __new__(cls, primary):
        value = super().__new__(cls, 'malicious diagnostic')
        value.primary = primary
        return value

    def __radd__(self, other):
        self.primary.operations.append('radd')
        return self

    def __add__(self, other):
        self.primary.operations.append('add')
        return self

    def __getitem__(self, key):
        self.primary.operations.append('getitem')
        return self.primary

    def __len__(self):
        self.primary.operations.append('len')
        return 4096

    def __bool__(self):
        self.primary.operations.append('bool')
        return True


class MaliciousDiagnosticFailure(BaseException):
    def __init__(self):
        self.payload = DiagnosticPayload()
        self.operations = []

    def __str__(self):
        return MaliciousDiagnosticText(self)


class MaliciousDiagnosticOSError(OSError):
    def __init__(self):
        self.payload = DiagnosticPayload()
        self.operations = []

    def __str__(self):
        return MaliciousDiagnosticText(self)


class FeedbackLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memory = inventory()

    @classmethod
    def tearDownClass(cls):
        if inventory() != cls.memory:
            raise AssertionError('Production Memory changed')

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='rnd024-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fixture = acquire(self.root / 'training')
        self.count = 0

    def episode(self, *, store=None, column=1, threshold=DEFAULT_SELECTOR,
                enabled=True, profile='mutating_memory', **options):
        self.count += 1
        root = self.root / str(self.count)
        store = json.loads(self.fixture.store_json) if store is None else store
        session, path = make_session(root, store=store, column=column,
            selector_threshold=threshold, **options)
        record, _ = authoritative_record(path, self.fixture.record.record_id)
        owner = FeedbackEpisode(session, root=root, acquired_record=record,
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

    def test_training_feasibility_and_default_f0_f1_f2_post_selection(self):
        f = self.fixture
        self.assertEqual(sorted(f.support_counts), [1, 2])
        self.assertEqual((f.create_status, f.readback_status), ('created', 'confirmed_persisted'))
        self.assertEqual(f.record.creation_metadata.source_support_count, 2)
        self.assertEqual((f.record.operational.hits, f.record.operational.misses,
                          f.record.operational.confidence, f.record.operational.repeatability),
                         (0, 0, .5, .5))
        self.assertEqual(len(f.provenance), 3)
        self.assertEqual(len({p.execution_occurrence_id for p in f.provenance}), 3)
        rows = []
        # Independent copies; explicit F0 at both world conditions.
        for label, col, enabled in (('F0-column0', 0, False), ('F0-column1', 1, False),
                                    ('F1', 0, True), ('F2', 1, True)):
            session, owner = self.episode(column=col, enabled=enabled)
            before_bytes = owner.path.read_bytes()
            owner.observe()
            self.assertIsNone(session.exploration)
            e = owner.evaluation.evidence
            x = session.records[0].execution
            t = session.components.short_memory.snapshot()[0]
            self.assertEqual(e.source_experience_id, f.record.record_id)
            self.assertEqual(e.execution_occurrence_id, x.execution_occurrence_id)
            self.assertEqual(e.execution_occurrence_id, t.execution_occurrence_id)
            self.assertNotIn(e.execution_occurrence_id,
                             {p.execution_occurrence_id for p in f.provenance})
            self.assertEqual(e.target_core, x.target_core)
            self.assertEqual(e.predicted_effect, f.record.effect)
            self.assertEqual(e.actual_effect.source_transition_id, t.transition_id)
            self.assertEqual(e.actual_effect.delta_values,
                             (-1., 1., 0.) if col == 0 else (0., -1., 1.))
            self.assertEqual(owner.evaluation.status.value, 'hit' if col == 0 else 'miss')
            self.assertAlmostEqual(owner.evaluation.effect_similarity, 1. if col == 0 else 1/3)
            self.assertAlmostEqual(owner.activation, .775 if col == 0 else .4083333333333333)
            self.assertEqual(owner.physical_calls, 1)
            with patch.object(owner._writer, 'apply', wraps=owner._writer.apply) as writer:
                owner.apply()
                self.assertEqual(writer.call_count, int(enabled))
            record, state = authoritative_record(owner.path, f.record.record_id)
            if enabled:
                self.assertEqual(owner.result.status.value, 'updated')
                self.assertEqual(owner.state, 'confirmed_applied')
                self.assertEqual(record, owner.readback)
                self.assertEqual(record, owner.result.intended_record)
                self.assertEqual(len(state.native_feedback_receipts['by_event_key']), 1)
                self.assertEqual((record.operational.hits, record.operational.misses),
                                 (1, 0) if col == 0 else (0, 1))
                self.assertEqual(record.operational.confidence, .382 if col == 0 else .375)
                self.assertEqual(record.operational.repeatability, .425)
                # Feedback changes metrics/timestamp, never the learned structure
                # or acquisition provenance. Receipt is outside cognitive records.
                changed = {k for k in set(record.to_json_data()) | set(f.record.to_json_data())
                           if record.to_json_data().get(k) != f.record.to_json_data().get(k)}
                self.assertEqual(changed, {'hits' if col == 0 else 'misses',
                                           'confidence', 'repeatability', 'updated_at_world'})
            else:
                self.assertEqual(owner.path.read_bytes(), before_bytes)
                self.assertEqual(record, f.record)
                self.assertIsNone(state.native_feedback_receipts)
            post, po = self.observed(store=json.loads(owner.path.read_text()),
                                     column=col, enabled=False)
            self.assertEqual(po.selected_source, owner.selected_source)
            self.assertEqual(po.physical_calls, 1)
            self.assertEqual(post.records[0].execution.actuator_signal.values,
                             x.actuator_signal.values)
            if enabled:
                self.assertLess(po.activation, owner.activation)
            else:
                self.assertEqual(po.activation, owner.activation)
            rows.append(dict(episode=label, similarity=e.effect_similarity,
                classification=e.classification.value, before=owner.activation,
                after=po.activation, selected=po.selected_source,
                operational=record.to_json_data(), state=owner.state))
            self.assert_no_retry(owner)
        print('RND024 defaults:', json.dumps(rows))

    def test_predeclared_point4_sensitivity_and_no_feedback_control(self):
        # .4 declared in scenario before either action; never adjusted afterward.
        for enabled in (False, True):
            session, owner = self.observed(threshold=SENSITIVITY_SELECTOR, enabled=enabled)
            self.assertEqual(session.components.selector.decision_threshold, .4)
            self.assertEqual(owner.selected_source, self.fixture.record.record_id)
            owner.apply()
            post, po = self.observed(store=json.loads(owner.path.read_text()),
                threshold=SENSITIVITY_SELECTOR, enabled=False)
            self.assertEqual(post.components.selector.decision_threshold, .4)
            self.assertEqual(post.records[0].observation.frames[0].values,
                             session.records[0].observation.frames[0].values)
            if enabled:
                self.assertAlmostEqual(po.activation, .3554166666666667)
                self.assertIsNone(po.selected_source)
                self.assertEqual(po.physical_calls, 0)
                self.assertIsNone(post.records[0].execution)
            else:
                self.assertEqual(po.activation, owner.activation)
                self.assertEqual(po.selected_source, owner.selected_source)
                self.assertEqual(po.physical_calls, 1)
        print('RND024 sensitivity: fixed .4; MISS .408333333 -> .355416667; selection 1 -> None; actions 1 -> 0')

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
        self.assertEqual(authoritative_record(owner.path, '1')[0], owner.recovery.record)
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
        record, state = authoritative_record(owner.path, '1')
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
                context = patch('scenarios.native_outcome_feedback_loop.reconcile_nfp_feedback_readback_failure',
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

    def test_nonisolated_paths_and_undeclared_parameters_rejected(self):
        # The root itself and its parent violate the dedicated-subdirectory
        # invariant regardless of whether the checkout also lives under /tmp.
        temporary = Path(tempfile.gettempdir()).resolve()
        for forbidden in (temporary, temporary.parent):
            with patch.object(Path, 'mkdir', side_effect=AssertionError('unexpected mkdir')) as mkdir, \
                 patch.object(Path, 'write_text', side_effect=AssertionError('unexpected write')) as write:
                with self.assertRaises(ValueError):
                    make_session(forbidden)
                mkdir.assert_not_called()
                write.assert_not_called()
        with self.assertRaises(ValueError):
            make_session(self.root / 'bad-threshold', selector_threshold=.399)
        session, owner = self.episode()
        session.components.retriever.store_path = ROOT / 'Memory/ExpSM/ExpSM_data.json'
        with self.assertRaises(ValueError):
            FeedbackEpisode(session, root=self.root, acquired_record=self.fixture.record)
        # An actual valid temporary descendant still permits the genuine path.
        valid, owner = self.observed(enabled=False)
        self.assertTrue(owner.path.resolve().is_relative_to(self.root))
        self.assertEqual(owner.physical_calls, 1)
        self.assertEqual(owner.state, 'evaluated')
        self.assertIsNone(valid.exploration)

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
        record, state = authoritative_record(owner.path, '1')
        self.assertEqual(record.operational.misses, 1)
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
            with patch('scenarios.native_outcome_feedback_loop.reconcile_nfp_feedback_readback_failure',
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
                context = patch('scenarios.native_outcome_feedback_loop.reconcile_nfp_feedback_readback_failure',
                                primary_boundary_failure)
            with context, patch('scenarios.native_outcome_feedback_loop._exception_reason',
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
                record, state = authoritative_record(owner.path, '1')
                self.assertEqual(record.operational.misses, 1)
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
                    context = patch('scenarios.native_outcome_feedback_loop.reconcile_nfp_feedback_readback_failure',
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
                        context = patch('scenarios.native_outcome_feedback_loop.reconcile_nfp_feedback_readback_failure',
                                        primary_invalid_diagnostic)
                with context, patch('scenarios.native_outcome_feedback_loop._exception_reason',
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
                context = patch('scenarios.native_outcome_feedback_loop.reconcile_nfp_feedback_readback_failure',
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
