"""RND-021 isolated integration driver; no claim of automatic native learning."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import gc
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import weakref
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clc.action.decision_selector import DecisionSelector
from clc.actuation.remembered_action_execution import NFPRememberedActionExecutionCoordinator, NFPRememberedActionExecutionStatus as XS
from clc.context.context_memory import ContextMemory
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.context_ops_pool import ContextOpsPool
from clc.context.short_memory import ShortMemory
from clc.core.ids import IdGenerator
from clc.core.pattern_registry import PatternRegistry
from clc.experience.bounded_native_acquisition import (
    AcquisitionLimits, BoundedNativeAcquisition, ExecutionProvenance, METADATA_CHARS, _digest,
)
from clc.experience.expsm_representation import ExpSMRecordCreationRequestBuilder
from clc.experience.evidence import ExperienceEvidenceFactory
from clc.experience.expsm_native_create import NFPExpSMCreateWriter, ExpSMCreateStatus, ExpSMRecoveryStatus
from clc.experience.expsm_representation import (
    NFPExpSMRecordV1, SerializedNFPContextV1, SerializedNFPActionV1,
    SerializedObservedEffectV1, ExpSMOperationalMetadataV1, NFPExpSMCreationMetadataV1,
)
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.nfp_operational_retrieval import NFPExpSMRetriever, NFPExpSMRetrievalConfig
from clc.patterns import PatternOrigin
from clc.runtime.memory_mutation_policy import policy_for_profile
from clc.runtime.native_bounded_delivery import NativeDeliverySession, DeliveryLimits, Control
from clc.runtime.native_heart_session import NativeHeartComponents
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld


def inventory():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'Memory').rglob('*') if p.is_file()}


class World(SyntheticClosedLoopVisualWorld):
    """Positive calls use super unchanged; optional faults are negative arms only."""
    def __init__(self, fault=None):
        super().__init__(shape=(1, 2), initial_row=0, initial_column=0)
        self.applies = []
        self.samples = []
        self.fault = fault

    def apply_actuator_signal(self, signal):
        super().apply_actuator_signal(signal)
        self.applies.append(signal)
        if self.fault == 'unknown':
            raise OSError('unknown outcome after apply')

    def snapshot(self):
        actual = super().snapshot()
        if self.fault in ('conflict', 'late_conflict') and self.current_tick == (5 if self.fault == 'late_conflict' else 3):
            actual = replace(actual, values=(1., 0.))
        self.samples.append(actual)
        return actual


class AcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = inventory()

    @classmethod
    def tearDownClass(cls):
        if inventory() != cls.original:
            raise AssertionError('whole Production Memory inventory/SHA-256 changed')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rnd021-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Test owner, not acquisition, owns writer lifetime until CREATE.
        self.writers = []

    def fixture(self, *, mode='active', fault=None, sample_enabled=None, limits=AcquisitionLimits(), profile='mutating_memory', hook=None, ticks=4, source_proposal_id='motor-prior', source_created_at_world=None):
        path = self.root / 'ExpSM.json'
        # Explicit non-target remembered motor priors. Zero effect is deliberately
        # unrelated to target observed delta; no fabricated Selected object.
        priors = {}
        for index, (context, action) in enumerate((((1., 0.), (0., 1.)), ((0., 1.), (1., 0.)))):
            record = NFPExpSMRecordV1(
                str(index), SerializedNFPContextV1('visual', (1, 2), (context,)),
                SerializedNFPActionV1('action', (2,), action),
                SerializedObservedEffectV1('visual', (1, 2), (0., 0.)),
                ExpSMOperationalMetadataV1(), NFPExpSMCreationMetadataV1(1, source_proposal_id, 0), created_at_world=source_created_at_world,
            )
            priors[str(index)] = record.to_json_data()
        path.write_text(json.dumps({'experience': priors, 'reflexes': {}}))
        ids = IdGenerator()
        registry = PatternRegistry(self.root / 'manifest.json')
        manager = ContextMemoryManager(ContextMemory(ids, registry), ContextOpsPool())
        world = World(fault)
        components = NativeHeartComponents(
            world, manager, NFPExpSMRetriever(path), NFPExpSMRetrievalConfig(1.),
            ExpSMActivationModule(ids, registry, path), DecisionSelector(ids, decision_threshold=.35),
            NFPRememberedActionExecutionCoordinator(ids, ModeActionGuard(registry)),
            ShortMemory(8, 10), SystemState(mode=mode),
        )
        def ingress(tick, delivery):
            if tick == ticks - 1:
                delivery.accept(Control.PAUSE, source_id='test-owner', stream_id='control')
        session = NativeDeliverySession(components, max_ticks=ticks, ingress=ingress,
                                       limits=DeliveryLimits(journal_capacity=128), sample_enabled=sample_enabled)
        writer = NFPExpSMCreateWriter(path, policy_for_profile(profile, memory_root=self.root, memory_is_temporary=True), failure_hook=hook)
        self.writers.append(writer)
        owner = BoundedNativeAcquisition(session, isolated_root=self.root, writer=writer, limits=limits)
        original = path.read_bytes()
        session.run()
        return session, owner, path, original

    def targets(self, session):
        return tuple(r.recent for r in session.records if r.recent is not None and r.recent.action_tick in (0, 2, 4))

    def prepared(self, **options):
        s, a, path, original = self.fixture(**options)
        admitted = [a.admit(t) for t in self.targets(s)]
        self.assertEqual([r.status for r in admitted], ['admitted', 'admitted'])
        a.seal()
        self.assertIsNotNone(a.prepare(admitted[0].candidate_id))
        return s, a, path, original

    def test_real_two_occurrences_to_create_fresh_readback_and_no_runtime_side_effects(self):
        s, a, path, original = self.fixture()
        c = s.components
        before = (tuple(s.records), c.short_memory.snapshot(), s.stop_report(), tuple(c.world.applies),
                  c.context_manager.current_external_sensory_window, s.comparison_requests())
        targets = self.targets(s)
        self.assertEqual(len(targets), 2)
        self.assertNotEqual(targets[0].execution_occurrence_id, targets[1].execution_occurrence_id)
        self.assertNotEqual(targets[0].transition_id, targets[1].transition_id)
        digests = tuple(_digest(t) for t in targets)
        admitted = [a.admit(t) for t in targets]
        for t, result in zip(targets, admitted):
            self.assertEqual(result.status, 'admitted')
            self.assertEqual(result.envelope.evidence, ExperienceEvidenceFactory.build(t))
            self.assertEqual(result.envelope.evidence.observed_effect.delta_values, (-1., 1.))
            self.assertEqual(result.envelope.execution_occurrence_id, t.execution_occurrence_id)
            self.assertEqual(result.envelope.session_id, s.session_id)
            self.assertEqual(len(result.envelope.sensor_event_ids), 2)
        self.assertEqual(a.candidates[0].support_count, 2)
        a.seal()
        request = a.prepare(admitted[0].candidate_id)
        self.assertEqual(request.requested_operational, ExpSMOperationalMetadataV1())
        initial = json.loads(original)['experience']
        self.assertTrue(all(v['effect_pattern'] != request.to_json_data()['effect_pattern'] for v in initial.values()))
        self.assertIsNone(a.create())  # separate test-owner authority required
        self.assertEqual(path.read_bytes(), original)
        result = a.create(test_owner_authorized=True)
        self.assertEqual(result.status, ExpSMCreateStatus.CREATED)
        self.assertEqual(a.readback.status, ExpSMRecoveryStatus.CONFIRMED_PERSISTED)
        self.assertEqual(a.readback.record, result.record)
        fresh = NFPExpSMRetriever(path)
        from clc.expsm.nfp_operational_retrieval import NFPExpSMRetrievalQuery
        found = fresh.retrieve(NFPExpSMRetrievalQuery(targets[0].before_sensory_window), c.retrieval_config)
        self.assertIn(result.record_id, [r.source_experience_id for r in found.candidates])
        self.assertEqual(tuple(_digest(t) for t in targets), digests)
        after = (tuple(s.records), c.short_memory.snapshot(), s.stop_report(), tuple(c.world.applies),
                 c.context_manager.current_external_sensory_window, s.comparison_requests())
        self.assertEqual(before, after)
        self.assertIsNone(s.echo)
        self.assertIsNone(s.internal_work_snapshot())
        self.assertEqual(len(c.world.applies), 3)
        self.assertIsNone(a.prepare(admitted[0].candidate_id))
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(len(json.loads(path.read_text())['experience']), 3)

    def test_single_and_replay_never_gain_support(self):
        s, a, path, original = self.fixture()
        t = self.targets(s)[0]
        r = a.admit(t)
        self.assertEqual(a.admit(t).status, 'duplicate')
        self.assertEqual(a.candidates[0].support_count, 1)
        a.seal()
        self.assertIsNone(a.prepare(r.candidate_id))
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(path.read_bytes(), original)

    def test_occurrence_digest_conflict_is_terminal(self):
        s, a, path, original = self.fixture()
        t = self.targets(s)[0]
        a.admit(t)
        changed = replace(t, after_sensory_window=replace(t.after_sensory_window, frames=(replace(t.after_sensory_window.frames[0], values=(1., 0.)),)))
        self.assertEqual(a.admit(changed).status, 'stopped_occurrence_conflict')
        self.assertEqual(a.admit(self.targets(s)[1]).status, 'stopped_occurrence_conflict')
        self.assertEqual(len(a.envelopes), 1)
        self.assertEqual(path.read_bytes(), original)

    def test_all_evidence_conflict_blocks_otherwise_sufficient_group(self):
        s, a, path, original = self.fixture(fault='conflict')
        results = [a.admit(t) for t in self.targets(s)]
        self.assertEqual([x.status for x in results], ['admitted', 'admitted'])
        self.assertEqual(len(a.candidates), 2)
        a.seal()
        self.assertIsNone(a.prepare(results[0].candidate_id))
        self.assertEqual(a.state, 'stopped_effect_conflict')
        self.assertEqual(path.read_bytes(), original)

    def test_conflict_outside_selected_supported_group_blocks_create(self):
        s, a, path, original = self.fixture(fault='late_conflict', ticks=6)
        results = [a.admit(t) for t in self.targets(s)]
        self.assertEqual([c.support_count for c in a.candidates], [2, 1])
        a.seal()
        self.assertIsNone(a.prepare(results[0].candidate_id))
        self.assertEqual(a.state, 'stopped_effect_conflict')
        self.assertEqual(path.read_bytes(), original)

    def test_guard_denial_and_missing_late_actual_produce_no_evidence(self):
        for opts in ({'mode': 'consolidation'}, {'sample_enabled': lambda t: t != 1}, {'fault': 'unknown'}):
            with self.subTest(opts=opts):
                s, a, path, original = self.fixture(**opts)
                self.assertEqual(self.targets(s), ())
                self.assertEqual(a.envelopes, ())
                self.assertIsNone(a.create(test_owner_authorized=True))
                self.assertEqual(path.read_bytes(), original)

    def test_missing_retention(self):
        s, a, _, _ = self.fixture()
        c = s.components
        c.short_memory.prune(100)
        self.assertEqual(a.admit(self.targets(s)[0]).status, 'transition_not_retained')

    def test_missing_world_apply_confirmation_and_mismatched_occurrence(self):
        for status in (XS.GUARD_DENIED, XS.WORLD_EXECUTION_FAILED, XS.ACTION_EXECUTED_CAUSAL_TRACKING_FAILED):
            s, a, _, _ = self.fixture()
            r = s.records[0]
            s.records[0] = replace(r, execution=replace(r.execution, status=status))
            self.assertEqual(a.admit(self.targets(s)[0]).status, 'world_apply_not_confirmed')
        s, a, _, _ = self.fixture()
        s.records[0] = replace(s.records[0], execution=replace(s.records[0].execution, execution_occurrence_id='foreign'))
        self.assertEqual(a.admit(self.targets(s)[0]).status, 'execution_transition_mismatch')

    def test_internal_or_predicted_and_unretained_copy_are_rejected(self):
        s, a, _, _ = self.fixture()
        t = self.targets(s)[0]
        self.assertEqual(a.admit(replace(t)).status, 'transition_not_retained')
        with self.assertRaises(ValueError):
            replace(t, after_sensory_window=replace(t.after_sensory_window, frames=(replace(t.after_sensory_window.frames[0], origin=PatternOrigin.INTERNAL_REACTIVATION),)))
        self.assertEqual(a.admit(s.records[0].execution.predicted_effect).status, 'invalid_transition')

    def test_journal_loss_rejects_without_inventing_binding(self):
        s, a, _, _ = self.fixture()
        s.delivery.journal.clear()
        self.assertEqual(a.admit(self.targets(s)[0]).status, 'sensor_provenance_unavailable')

    def test_denied_create_is_terminal_no_fallback(self):
        _, a, path, original = self.prepared(profile='safe_demo')
        self.assertEqual(a.create(test_owner_authorized=True).status, ExpSMCreateStatus.DENIED_BY_POLICY)
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(path.read_bytes(), original)

    def test_readback_failure_reconciles_without_retry(self):
        def hook(stage):
            if stage == 'post_replace_readback':
                raise OSError('injected readback failure')
        _, a, path, _ = self.prepared(hook=hook)
        self.assertEqual(a.create(test_owner_authorized=True).status, ExpSMCreateStatus.READBACK_FAILED)
        self.assertEqual(a.readback.status, ExpSMRecoveryStatus.CONFIRMED_PERSISTED)
        saved = path.read_bytes()
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(path.read_bytes(), saved)

    def test_reconciliation_absent_and_unresolved_are_terminal(self):
        for fault in ('absent', 'invalid'):
            s, a, path, original = self.prepared()
            def hook(stage):
                if stage == 'post_replace_readback':
                    path.write_bytes(original if fault == 'absent' else b'invalid')
                    raise OSError('negative recovery injection')
            a._writer.failure_hook = hook
            a.create(test_owner_authorized=True)
            self.assertEqual(a.readback.status, ExpSMRecoveryStatus.CONFIRMED_ABSENT if fault == 'absent' else ExpSMRecoveryStatus.UNRESOLVED_OR_STORE_INVALID)
            self.assertIsNone(a.create(test_owner_authorized=True))

    def test_write_failed_and_invalid_store_finish_attempt(self):
        def hook(stage):
            if stage == 'pre_replace':
                raise OSError('negative write injection')
        _, a, path, original = self.prepared(hook=hook)
        self.assertEqual(a.create(test_owner_authorized=True).status, ExpSMCreateStatus.WRITE_FAILED)
        self.assertEqual(path.read_bytes(), original)
        self.assertIsNone(a.create(test_owner_authorized=True))
        _, a, path, _ = self.prepared()
        path.write_text('invalid')
        self.assertEqual(a.create(test_owner_authorized=True).status, ExpSMCreateStatus.STORE_INVALID)
        self.assertIsNone(a.create(test_owner_authorized=True))

    def test_input_evidence_and_lifetime_budgets_stop_without_evicting_keys(self):
        for limits, expected in ((AcquisitionLimits(inputs=1), 'stopped_input_budget'),
                                 (AcquisitionLimits(evidence=1), 'stopped_evidence_budget')):
            s, a, path, original = self.fixture(limits=limits)
            first, second = self.targets(s)
            a.admit(first)
            self.assertEqual(a.admit(second).status, expected)
            self.assertEqual(len(a.envelopes), 1)
            self.assertEqual(a.admit(first).status, expected)
            self.assertEqual(path.read_bytes(), original)
        s, a, path, original = self.fixture()
        with patch('clc.experience.bounded_native_acquisition.time.monotonic', return_value=a._deadline + 1):
            self.assertEqual(a.admit(self.targets(s)[0]).status, 'stopped_lifetime')
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_request_is_terminal_and_no_blind_retry_on_exception(self):
        _, a, path, original = self.prepared()
        # Negative injection after preparation exercises existing typed validator.
        a.request = replace(a.request, requested_operational=ExpSMOperationalMetadataV1(1, 0, .5, .5))
        self.assertEqual(a.create(test_owner_authorized=True).status, ExpSMCreateStatus.INVALID_REQUEST)
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(path.read_bytes(), original)
        _, a, path, original = self.prepared()
        with patch.object(a._writer, 'create', side_effect=OSError('unexpected failure')) as call:
            with self.assertRaises(OSError):
                a.create(test_owner_authorized=True)
            self.assertIsNone(a.create(test_owner_authorized=True))
            self.assertEqual(call.call_count, 1)
        self.assertEqual(path.read_bytes(), original)

    def test_payload_budget_and_sealing_stop_admission(self):
        s, a, path, original = self.fixture(limits=AcquisitionLimits(max_values=1))
        self.assertEqual(a.admit(self.targets(s)[0]).status, 'stopped_payload_budget')
        self.assertEqual(a.envelopes, ())
        self.assertEqual(path.read_bytes(), original)
        s, a, _, _ = self.fixture()
        a.seal()
        self.assertEqual(a.admit(self.targets(s)[0]).status, 'sealed')

    def assert_terminal(self, owner, transition, reason):
        diagnostic = owner.stop_diagnostic
        with patch.object(owner._writer, 'create') as create:
            self.assertEqual(owner.admit(transition).status, reason)
            self.assertEqual(owner.seal(), reason)
            self.assertIsNone(owner.prepare('candidate:000001'))
            self.assertIsNone(owner.create(test_owner_authorized=True))
            create.assert_not_called()
        with patch('clc.experience.bounded_native_acquisition.time.monotonic', return_value=owner._deadline + 1):
            self.assertEqual(owner.admit(transition).status, reason)
            self.assertEqual(owner.seal(), reason)
            self.assertIsNone(owner.prepare('candidate:000001'))
            self.assertIsNone(owner.create(test_owner_authorized=True))
        self.assertIs(owner.stop_diagnostic, diagnostic)
        self.assertEqual(owner.stop_reason, reason)
        self.assertEqual(owner.state, reason)

    def test_grouper_failure_before_mutation_latches_reservation_without_admission(self):
        s, a, path, original = self.fixture()
        t = self.targets(s)[0]
        with patch.object(a._grouper, 'observe', side_effect=RuntimeError('before mutation')) as observe:
            with self.assertRaises(RuntimeError):
                a.admit(t)
            self.assert_terminal(a, t, 'stopped_grouper_error')
            self.assertEqual(observe.call_count, 1)
        self.assertEqual(a.envelopes, ())
        self.assertEqual(a.candidates, ())
        self.assertEqual(len(a.reservations), 1)
        self.assertEqual(a.reservations[0].execution_occurrence_id, t.execution_occurrence_id)
        self.assertEqual(a.reservations[0].evidence_digest, _digest(t))
        self.assertEqual(a.stop_diagnostic.error_category, 'RuntimeError')
        self.assertEqual(path.read_bytes(), original)

    def test_grouper_failure_after_mutation_is_uncertain_never_replayed_or_promoted(self):
        s, a, path, original = self.fixture()
        first, second = self.targets(s)
        observe = a._grouper.observe
        def partial(evidence):
            observe(evidence)
            raise RuntimeError('after mutation')
        with patch.object(a._grouper, 'observe', side_effect=partial) as call:
            with self.assertRaises(RuntimeError):
                a.admit(first)
            self.assert_terminal(a, first, 'stopped_grouper_error')
            self.assertEqual(a.admit(second).status, 'stopped_grouper_error')
            self.assertEqual(call.call_count, 1)
        self.assertEqual(a.envelopes, ())  # grouper's tentative state is not admitted support
        self.assertEqual(a.candidates[0].support_count, 1)
        self.assertEqual(len(a.reservations), 1)
        self.assertEqual(a.stop_diagnostic.execution_occurrence_id, first.execution_occurrence_id)
        self.assertEqual(a.stop_diagnostic.evidence_digest, _digest(first))
        self.assertEqual(path.read_bytes(), original)

    def test_factory_failure_retains_only_reservation_and_bounded_diagnostic(self):
        s, a, path, original = self.fixture()
        t = self.targets(s)[0]
        with patch.object(ExperienceEvidenceFactory, 'build', side_effect=ValueError('x' * 1000000)) as factory:
            with self.assertRaises(ValueError):
                a.admit(t)
            self.assert_terminal(a, t, 'stopped_factory_error')
            self.assertEqual(factory.call_count, 1)
        self.assertEqual(a.envelopes, ())
        self.assertEqual(a.candidates, ())
        self.assertEqual(len(a.reservations), 1)
        self.assertEqual(a.stop_diagnostic.error_category, 'ValueError')
        self.assertEqual(path.read_bytes(), original)

    def test_builder_failure_fixes_proposal_and_support_without_another_prepare(self):
        s, a, path, original = self.fixture()
        results = [a.admit(t) for t in self.targets(s)]
        before = a.envelopes
        a.seal()
        make_proposal = a._grouper.make_proposal
        with patch.object(a._grouper, 'make_proposal', wraps=make_proposal) as propose:
            with patch.object(ExpSMRecordCreationRequestBuilder, 'build', side_effect=ValueError('builder fault')) as builder:
                with self.assertRaises(ValueError):
                    a.prepare(results[0].candidate_id)
                fixed = a.proposal
                self.assertIsNotNone(fixed)
                self.assertEqual(fixed.proposal_id, 'proposal:000001')
                self.assertEqual(fixed.supporting_evidence_ids, tuple(e.evidence_id for e in before))
                self.assertIsNone(a.request)
                self.assert_terminal(a, self.targets(s)[0], 'stopped_builder_error')
                self.assertIs(a.proposal, fixed)
                self.assertEqual(propose.call_count, 1)
                self.assertEqual(builder.call_count, 1)
        self.assertEqual(a.envelopes, before)
        self.assertEqual(a.candidates[0].support_count, 2)
        with self.assertRaises(FrozenInstanceError):
            fixed.proposal_id = 'replacement'
        self.assertEqual(path.read_bytes(), original)

    def test_proposal_exception_after_possible_mutation_is_terminal(self):
        s, a, path, original = self.fixture()
        results = [a.admit(t) for t in self.targets(s)]
        a.seal()
        propose = a._grouper.make_proposal
        def partial(*args, **kwargs):
            propose(*args, **kwargs)
            raise RuntimeError('proposal result unavailable')
        with patch.object(a._grouper, 'make_proposal', side_effect=partial) as call:
            with self.assertRaises(RuntimeError):
                a.prepare(results[0].candidate_id)
            self.assert_terminal(a, self.targets(s)[0], 'stopped_proposal_error')
            self.assertEqual(call.call_count, 1)
        self.assertIsNone(a.proposal)
        self.assertIsNone(a.request)
        self.assertEqual(path.read_bytes(), original)

    def test_execution_projection_accepts_metadata_boundary_without_raw_record_reference(self):
        s, a, _, _ = self.fixture(source_proposal_id='p' * METADATA_CHARS,
                                   source_created_at_world='t' * METADATA_CHARS)
        t = self.targets(s)[0]
        raw = s.records[0].execution
        r = a.admit(t)
        self.assertEqual(r.status, 'admitted')
        projection = r.envelope.execution
        self.assertIsInstance(projection, ExecutionProvenance)
        self.assertIsNot(projection, raw)
        self.assertFalse(hasattr(projection, 'target_core'))
        self.assertFalse(hasattr(projection, 'predicted_effect'))
        self.assertEqual(projection.source_proposal_id, raw.target_core.source_proposal_id)
        self.assertEqual(projection.source_created_at_world, raw.target_core.created_at_world)
        self.assertEqual(projection.execution_occurrence_id, t.execution_occurrence_id)
        self.assertEqual(projection.pending_transition_id, t.transition_id)
        with self.assertRaises(FrozenInstanceError):
            projection.source_proposal_id = 'changed'

    def test_original_oversized_nested_proposal_reproduction_is_rejected(self):
        s, a, path, original = self.fixture(source_proposal_id='x' * 1000000)
        t = self.targets(s)[0]
        self.assertEqual(a.admit(t).status, 'stopped_metadata_budget')
        self.assertEqual(a.envelopes, ())
        self.assertEqual(a.reservations, ())
        self.assertEqual(a.candidates, ())
        self.assert_terminal(a, t, 'stopped_metadata_budget')
        self.assertEqual(path.read_bytes(), original)

    def test_execution_detail_and_alternate_source_fields_cannot_bypass_metadata_budget(self):
        for field in ('detail', 'source_experience_id'):
            for length in (METADATA_CHARS + 1, 1000000):
                with self.subTest(field=field, length=length):
                    s, a, path, original = self.fixture()
                    s.records[0] = replace(s.records[0], execution=replace(s.records[0].execution, **{field: 'x' * length}))
                    self.assertEqual(a.admit(self.targets(s)[0]).status, 'stopped_metadata_budget')
                    self.assertEqual(a.envelopes, ())
                    self.assertEqual(a.reservations, ())
                    self.assertEqual(a.candidates, ())
                    self.assertEqual(path.read_bytes(), original)

    def test_nested_alternate_metadata_field_cannot_bypass_budget(self):
        s, a, path, original = self.fixture(source_created_at_world='t' * (METADATA_CHARS + 1))
        self.assertEqual(a.admit(self.targets(s)[0]).status, 'stopped_metadata_budget')
        self.assertEqual(a.envelopes, ())
        self.assertEqual(a.reservations, ())
        self.assertEqual(path.read_bytes(), original)

    def test_retained_event_and_window_metadata_have_explicit_limits(self):
        s, a, _, _ = self.fixture()
        t = self.targets(s)[0]
        for i, trace in enumerate(s.delivery.journal):
            if trace.stage == 'native_admitted' and trace.detail == t.after_sensory_window.window_id:
                s.delivery.journal[i] = replace(trace, event=replace(trace.event, native_refs=('x' * 257,)))
                break
        self.assertEqual(a.admit(t).status, 'stopped_metadata_budget')
        self.assertEqual(a.envelopes, ())
        self.assertEqual(a.reservations, ())
        s, a, _, _ = self.fixture()
        t = self.targets(s)[0]
        oversized = replace(t, before_sensory_window=replace(t.before_sensory_window, debug_name='x' * 257))
        self.assertEqual(a.admit(oversized).status, 'stopped_payload_budget')
        self.assertEqual(a.envelopes, ())
        self.assertEqual(a.reservations, ())

    def test_first_stop_cause_survives_timeout_and_all_public_calls(self):
        for cause in ('conflict', 'input', 'evidence', 'timeout'):
            with self.subTest(cause=cause):
                limits = AcquisitionLimits(inputs=1) if cause == 'input' else AcquisitionLimits(evidence=1) if cause == 'evidence' else AcquisitionLimits()
                s, a, _, _ = self.fixture(limits=limits)
                first, second = self.targets(s)
                if cause != 'timeout':
                    a.admit(first)
                if cause == 'conflict':
                    altered = replace(first, after_sensory_window=replace(first.after_sensory_window, frames=(replace(first.after_sensory_window.frames[0], values=(1., 0.)),)))
                    reason = a.admit(altered).status
                elif cause in ('input', 'evidence'):
                    reason = a.admit(second).status
                else:
                    with patch('clc.experience.bounded_native_acquisition.time.monotonic', return_value=a._deadline + 1):
                        reason = a.admit(first).status
                self.assertEqual(reason, {'conflict': 'stopped_occurrence_conflict', 'input': 'stopped_input_budget', 'evidence': 'stopped_evidence_budget', 'timeout': 'stopped_lifetime'}[cause])
                self.assert_terminal(a, first, reason)

    def test_reconciliation_exception_preserves_uncertainty_and_blocks_retry(self):
        def hook(stage):
            if stage == 'post_replace_readback':
                raise OSError('readback fault')
        s, a, path, _ = self.prepared(hook=hook)
        with patch('clc.experience.bounded_native_acquisition.reconcile_expsm_readback_failure', side_effect=RuntimeError('reconcile fault')) as reconcile:
            with self.assertRaises(RuntimeError):
                a.create(test_owner_authorized=True)
            self.assert_terminal(a, self.targets(s)[0], 'stopped_reconciliation_error')
            self.assertEqual(reconcile.call_count, 1)
        self.assertEqual(a.create_result.status, ExpSMCreateStatus.READBACK_FAILED)
        self.assertIsNone(a.readback)
        self.assertTrue(a.attempted)
        self.assertEqual(len(json.loads(path.read_text())['experience']), 3)

    def test_oversized_writer_diagnostic_is_not_retained_or_retried(self):
        def hook(stage):
            if stage == 'pre_replace':
                raise OSError('x' * 1000000)
        s, a, path, original = self.prepared(hook=hook)
        result = a.create(test_owner_authorized=True)
        self.assertEqual(result.status, ExpSMCreateStatus.WRITE_FAILED)
        self.assertIsNone(a.create_result)
        self.assertTrue(a.attempted)
        self.assert_terminal(a, self.targets(s)[0], 'stopped_result_metadata_budget')
        self.assertEqual(path.read_bytes(), original)

    def test_oversized_reconciliation_diagnostic_is_not_retained(self):
        from clc.experience.expsm_native_create import reconcile_expsm_readback_failure
        s, a, path, _ = self.prepared()
        def oversized(*args):
            return replace(reconcile_expsm_readback_failure(*args), reason='x' * 257)
        with patch('clc.experience.bounded_native_acquisition.reconcile_expsm_readback_failure', side_effect=oversized):
            result = a.create(test_owner_authorized=True)
        self.assertEqual(result.status, ExpSMCreateStatus.CREATED)
        self.assertIsNone(a.readback)
        self.assert_terminal(a, self.targets(s)[0], 'stopped_result_metadata_budget')
        self.assertEqual(len(json.loads(path.read_text())['experience']), 3)

    def test_successful_admission_does_not_keep_session_or_raw_execution_alive(self):
        s, a, path, original = self.fixture()
        t = self.targets(s)[0]
        refs = (weakref.ref(s), *(weakref.ref(r.execution) for r in s.records if r.execution is not None))
        result = a.admit(t)
        self.assertEqual(result.status, 'admitted')
        envelope = result.envelope
        self.assertEqual(envelope.execution.execution_occurrence_id, t.execution_occurrence_id)
        self.assertEqual(envelope.evidence_digest, _digest(t))
        self.assertIs(envelope.transition, t)
        self.assertEqual(len(envelope.sensor_events), 2)
        self.assertFalse(hasattr(a, '_session'))
        del s
        gc.collect()  # Test-only lifetime probe; production never invokes GC.
        self.assertTrue(all(ref() is None for ref in refs))
        self.assertIs(a.envelopes[0], envelope)
        self.assertEqual(envelope.evidence, ExperienceEvidenceFactory.build(t))
        self.assertEqual(path.read_bytes(), original)

    def test_oversized_refusal_does_not_keep_session_or_raw_execution_alive(self):
        s, a, path, original = self.fixture(source_proposal_id='x' * 1000000)
        t = self.targets(s)[0]
        refs = (weakref.ref(s), weakref.ref(s.records[0].execution))
        self.assertEqual(a.admit(t).status, 'stopped_metadata_budget')
        diagnostic = a.stop_diagnostic
        del s
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))
        self.assertEqual(a.envelopes, ())
        self.assertEqual(a.reservations, ())
        self.assertIs(a.stop_diagnostic, diagnostic)
        self.assert_terminal(a, t, 'stopped_metadata_budget')
        self.assertEqual(path.read_bytes(), original)

    def test_session_disappearing_before_admission_fails_closed_without_reconstruction(self):
        s, a, path, original = self.fixture()
        t = self.targets(s)[0]
        session_ref = weakref.ref(s)
        del s
        gc.collect()
        self.assertIsNone(session_ref())
        with patch.object(ExperienceEvidenceFactory, 'build') as factory:
            self.assertEqual(a.admit(t).status, 'stopped_session_unavailable')
            self.assert_terminal(a, t, 'stopped_session_unavailable')
            factory.assert_not_called()
        self.assertEqual(a.envelopes, ())
        self.assertEqual(a.reservations, ())
        self.assertEqual(path.read_bytes(), original)

    def test_retained_evidence_can_prepare_and_create_after_session_disappears(self):
        s, a, path, original = self.fixture()
        results = [a.admit(t) for t in self.targets(s)]
        self.assertEqual([r.status for r in results], ['admitted', 'admitted'])
        envelopes = a.envelopes
        admission_tick = s.heart.tick
        refs = (weakref.ref(s), *(weakref.ref(r.execution) for r in s.records if r.execution is not None))
        del s
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))
        # seal/prepare/create must not even dereference a lost session.
        with patch.object(a, '_session_ref', side_effect=AssertionError('unexpected session access')) as source:
            self.assertEqual(a.seal(), 'sealed')
            request = a.prepare(results[0].candidate_id)
            self.assertIsNotNone(request)
            self.assertEqual(a.proposal.created_active_tick, admission_tick)
            self.assertEqual(a.proposal.supporting_evidence_ids, tuple(e.evidence_id for e in envelopes))
            result = a.create(test_owner_authorized=True)
            source.assert_not_called()
        self.assertEqual(result.status, ExpSMCreateStatus.CREATED)
        self.assertEqual(a.readback.status, ExpSMRecoveryStatus.CONFIRMED_PERSISTED)
        self.assertEqual(a.readback.record, result.record)
        self.assertEqual(a.envelopes, envelopes)
        from clc.expsm.nfp_operational_retrieval import NFPExpSMRetrievalQuery
        fresh = NFPExpSMRetriever(path).retrieve(NFPExpSMRetrievalQuery(envelopes[0].transition.before_sensory_window), NFPExpSMRetrievalConfig(1.))
        self.assertIn(result.record_id, [c.source_experience_id for c in fresh.candidates])
        self.assertNotEqual(path.read_bytes(), original)
        self.assertEqual(len(json.loads(path.read_text())['experience']), 3)
        self.assertIsNone(a.create(test_owner_authorized=True))

    def test_prepared_request_survives_source_lifetime_without_changing_authority(self):
        s, a, path, original = self.prepared(profile='safe_demo')
        request, proposal, envelopes = a.request, a.proposal, a.envelopes
        refs = (weakref.ref(s), weakref.ref(s.records[0].execution))
        del s
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))
        self.assertIs(a.request, request)
        self.assertIs(a.proposal, proposal)
        self.assertEqual(a.envelopes, envelopes)
        self.assertIsNone(a.create())
        self.assertEqual(a.create(test_owner_authorized=True).status, ExpSMCreateStatus.DENIED_BY_POLICY)
        self.assertEqual(path.read_bytes(), original)

    def test_lost_source_on_new_admission_preserves_previous_evidence_and_first_stop(self):
        s, a, path, original = self.fixture()
        first, second = self.targets(s)
        a.admit(first)
        envelopes = a.envelopes
        source = weakref.ref(s)
        del s
        gc.collect()
        self.assertIsNone(source())
        self.assertEqual(a.admit(second).status, 'stopped_session_unavailable')
        self.assertEqual(a.envelopes, envelopes)
        self.assertEqual(len(a.reservations), 1)
        self.assert_terminal(a, first, 'stopped_session_unavailable')
        self.assertEqual(path.read_bytes(), original)

    def test_original_stop_is_not_replaced_when_source_is_collected(self):
        s, a, path, original = self.fixture()
        first = self.targets(s)[0]
        a.admit(first)
        altered = replace(first, after_sensory_window=replace(first.after_sensory_window, frames=(replace(first.after_sensory_window.frames[0], values=(1., 0.)),)))
        self.assertEqual(a.admit(altered).status, 'stopped_occurrence_conflict')
        refs = (weakref.ref(s), weakref.ref(s.records[0].execution))
        del s
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))
        self.assert_terminal(a, first, 'stopped_occurrence_conflict')
        self.assertEqual(path.read_bytes(), original)

    def test_writer_callback_cannot_indirectly_keep_source_session_alive_via_owner(self):
        s, a, path, original = self.prepared()
        writer = a._writer
        # A legitimate diagnostic hook can incidentally close over the source.
        writer.failure_hook = lambda stage, source=s: None
        refs = (weakref.ref(s), weakref.ref(s.records[0].execution), weakref.ref(writer))
        del s, writer
        self.writers.clear()  # Release the independent test-owner's writer too.
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))
        self.assertEqual(len(a.envelopes), 2)
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(a.stop_reason, 'stopped_writer_unavailable')
        self.assertFalse(a.attempted)
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(path.read_bytes(), original)

    def test_nonisolated_paths_rejected(self):
        s, a, _, _ = self.fixture()
        with self.assertRaises(ValueError):
            BoundedNativeAcquisition(s, isolated_root=ROOT, writer=a._writer)
        a._writer.transaction.store_path = ROOT / 'Memory/ExpSM/ExpSM_data.json'
        with self.assertRaises(ValueError):
            BoundedNativeAcquisition(s, isolated_root=self.root, writer=a._writer)


if __name__ == '__main__':
    unittest.main(verbosity=2)
