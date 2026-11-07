"""RND-023 behavioral verification, using real production APIs and /tmp stores."""
from __future__ import annotations
from dataclasses import FrozenInstanceError, asdict, replace
import gc
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import weakref
from unittest.mock import PropertyMock, patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenarios.first_native_acquired_experience_loop import make_session, training, admit_all, prepare, EMPTY
from clc.experience.expsm_native_create import ExpSMCreateStatus as CS, ExpSMRecoveryStatus as RS
from clc.actuation.remembered_action_execution import NFPRememberedActionExecutionStatus as XS
from clc.experience.bounded_native_acquisition import _digest


def inventory():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'Memory').rglob('*') if p.is_file()}


class NestedIdentity(str):
    """Negative input: short visible text with an arbitrary retained graph."""
    def __new__(cls, text, payload=None):
        obj = super().__new__(cls, text)
        obj.payload = payload
        return obj


class LoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = inventory()

    @classmethod
    def tearDownClass(cls):
        if inventory() != cls.original:
            raise AssertionError('Production Memory changed')

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='rnd023-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def train(self, **options):
        return training(self.root / str(len(list(self.root.iterdir()))), **options)

    def ready(self, **options):
        s, a, w, p = self.train(**options)
        results = admit_all(s, a)
        self.assertEqual([r.status for r in results], ['admitted'] * 3)
        self.assertIsNotNone(prepare(a))
        return s, a, w, p

    def control(self, name, store):
        s, w, path = make_session(self.root / name, store=store)
        c = s.components
        traces = {}
        # Spies observe real calls; return objects are never fabricated.
        with patch.object(c.retriever, 'retrieve', wraps=c.retriever.retrieve) as r, \
             patch.object(c.activation, 'activate_native', wraps=c.activation.activate_native) as a, \
             patch.object(c.selector, 'select_native', wraps=c.selector.select_native) as d, \
             patch.object(c.coordinator, 'execute', wraps=c.coordinator.execute) as execute:
            s.run()
            traces['execution_request'] = execute.call_args.args[0] if execute.call_args else None
            traces['retrieved'] = r.call_count
            traces['activated'] = a.call_args.args[0] if a.call_args else ()
            traces['selected'] = d.call_args.args[0] if d.call_args else ()
        self.assertIsNone(s.exploration)
        self.assertEqual(json.loads(path.read_text()), store)
        return s, traces

    def test_empty_training_create_controls_and_ablation(self):
        s, a, w, p = self.train()
        self.assertEqual(json.loads(p.read_text()), EMPTY)
        xs = [r.execution for r in s.records if r.execution]
        self.assertEqual([x.actuator_signal.values for x in xs], [(0., 1.), (1., 0.), (0., 1.)])
        self.assertTrue(all(x.source_experience_id is None and x.target_core is None and x.predicted_effect is None for x in xs))
        transitions = s.components.short_memory.snapshot()
        self.assertEqual(len(transitions), 3)
        before = tuple(_digest(t) for t in transitions)
        admitted = admit_all(s, a)
        self.assertEqual([r.status for r in admitted], ['admitted'] * 3)
        self.assertEqual(sorted(c.support_count for c in a.candidates), [1, 2])
        self.assertEqual(len({t.execution_occurrence_id for t in transitions}), 3)
        for e in a.envelopes:
            audit = e.exploratory_provenance
            x = s.records[e.action_tick].execution
            self.assertEqual(audit.intent_id, x.exploratory_intent.intent_id)
            self.assertEqual(audit.authorization_id, s.exploration.authorization.authorization_id)
            self.assertEqual(audit.test_owner_id, s.exploration.authorization.test_owner_id)
            self.assertEqual(audit.configuration_id, s.exploration.config.configuration_id)
            self.assertEqual((audit.execution_occurrence_id, audit.transition_id, audit.session_id, audit.source_id),
                             (e.execution_occurrence_id, e.transition_id, e.session_id, e.source_id))
        self.assertIsNotNone(prepare(a))
        self.assertIsNone(a.create())
        self.assertEqual(json.loads(p.read_text()), EMPTY)
        result = a.create(test_owner_authorized=True)
        self.assertEqual(result.status, CS.CREATED)
        self.assertEqual(a.readback.status, RS.CONFIRMED_PERSISTED)
        self.assertEqual(a.readback.record, result.record)
        learned = json.loads(p.read_text())
        self.assertEqual(set(learned['experience']), {result.record_id})
        self.assertEqual(tuple(_digest(t) for t in transitions), before)
        c0, t0 = self.control('c0', EMPTY)
        c1, t1 = self.control('c1', learned)
        ablated = json.loads(json.dumps(learned))
        del ablated['experience'][result.record_id]
        ca, ta = self.control('ablation', ablated)
        for c in (c0, c1, ca):
            self.assertEqual(c.records[0].observation.frames[0].values, s.records[0].observation.frames[0].values)
            self.assertEqual(c.records[0].observation.frames[0].active_tick, 0)
            self.assertEqual(c.components.selector.decision_threshold, .35)
            self.assertEqual(c.components.retrieval_config.context_similarity_threshold, 1.)
        for c, trace in ((c0, t0), (ca, ta)):
            self.assertTrue(all(r.execution is None for r in c.records))
            self.assertEqual(c.components.world.hidden_position, (0, 0))
            self.assertEqual(trace['activated'], ())
        self.assertEqual([v.source_experience_id for v in t1['activated']], [result.record_id])
        self.assertEqual([v.source_experience_id for v in t1['selected']], [result.record_id])
        x = c1.records[0].execution
        self.assertIsNotNone(x, 'INTEGRATION GAP: acquired source not selected')
        selected = t1['execution_request'].selected
        activated, = t1['selected']
        retrieved, = t1['activated']
        self.assertEqual(selected.source_experience_id, result.record_id)
        self.assertEqual(selected.activation_id, activated.activation_id)
        self.assertEqual(selected.retrieval_candidate_id, retrieved.candidate_id)
        self.assertEqual(selected.target_core.source_proposal_id, result.record.creation_metadata.source_proposal_id)
        self.assertEqual(x.target_core, selected.target_core)
        self.assertEqual(x.source_experience_id, result.record_id)
        self.assertEqual(x.status, XS.ACTION_EXECUTED_OBSERVATION_PENDING)
        self.assertTrue(x.guard_passed)
        self.assertIsNone(x.exploratory_intent)
        self.assertEqual(sum(r.execution is not None for r in c1.records), 1)
        self.assertEqual(c1.components.world.hidden_position, (0, 1))
        self.assertEqual(c1.records[1].recent.execution_occurrence_id, x.execution_occurrence_id)
        self.assertNotEqual(c1.records[1].recent.before_sensory_window.frames[0].values,
                            c1.records[1].recent.after_sensory_window.frames[0].values)
        self.assertIsNone(a.create(test_owner_authorized=True))
        print('RND023 proof:', json.dumps(dict(record_id=result.record_id, training_actions=len(xs),
            evidence=len(a.envelopes), support=len(a.proposal.supporting_evidence_ids),
            c0_actions=sum(r.execution is not None for r in c0.records),
            c1_actions=sum(r.execution is not None for r in c1.records),
            ablation_actions=sum(r.execution is not None for r in ca.records), selected_source=x.source_experience_id)))

    def test_support_and_duplicate(self):
        s, a, w, p = self.train()
        t = s.components.short_memory.snapshot()[0]
        r = a.admit(t)
        self.assertEqual(a.admit(t).status, 'duplicate')
        self.assertEqual(a.candidates[0].support_count, 1)
        a.seal()
        self.assertIsNone(a.prepare(r.candidate_id))
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(json.loads(p.read_text()), EMPTY)

    def test_missing_or_mismatched_authorization(self):
        for field in ('missing', 'authorization_id', 'test_owner_id', 'configuration_id'):
            with self.subTest(field=field):
                s, a, w, p = self.train()
                if field == 'missing':
                    s.exploration.authorization = None
                else:
                    s.exploration.authorization = replace(s.exploration.authorization, **{field: 'forged'})
                self.assertTrue(a.admit(s.components.short_memory.snapshot()[0]).status.startswith('exploratory_authorization_'))
                self.assertEqual(a.envelopes, ())

    def test_intent_occurrence_transition_tampering(self):
        for field in ('intent_id', 'execution_occurrence_id', 'transition_id', 'missing_intent', 'execution_occurrence'):
            with self.subTest(field=field):
                s, a, w, p = self.train()
                t = s.components.short_memory.snapshot()[0]
                if field in ('intent_id', 'missing_intent', 'execution_occurrence'):
                    r = s.records[0]
                    if field == 'intent_id':
                        x = replace(r.execution, exploratory_intent=replace(r.execution.exploratory_intent, intent_id='forged'))
                    elif field == 'missing_intent':
                        x = replace(r.execution, exploratory_intent=None)
                    else:
                        x = replace(r.execution, execution_occurrence_id=str(uuid4()))
                    s.records[0] = replace(r, execution=x)
                else:
                    t = replace(t, **{field: str(uuid4()) if field == 'execution_occurrence_id' else 'forged'})
                self.assertNotEqual(a.admit(t).status, 'admitted')
                self.assertEqual(a.envelopes, ())

    def test_session_loss_before_and_after_admission(self):
        s, a, w, p = self.train()
        t = s.components.short_memory.snapshot()[0]
        ref = weakref.ref(s)
        del s
        gc.collect()
        self.assertIsNone(ref())
        self.assertEqual(a.admit(t).status, 'stopped_session_unavailable')
        s, a, w, p = self.ready()
        audit = tuple(asdict(e.exploratory_provenance) for e in a.envelopes)
        ref = weakref.ref(s)
        del s
        gc.collect()
        self.assertIsNone(ref())
        self.assertEqual(tuple(asdict(e.exploratory_provenance) for e in a.envelopes), audit)
        self.assertEqual(a.create(test_owner_authorized=True).status, CS.CREATED)

    def test_missing_actual_and_guard_denial(self):
        for options in ({'sample_enabled': lambda tick: tick != 1}, {'mode': 'consolidation'}):
            s, a, w, p = self.train(**options)
            self.assertEqual(s.components.short_memory.snapshot(), ())
            self.assertEqual(admit_all(s, a), ())
            self.assertIsNone(prepare(a))
            self.assertIsNone(a.create(test_owner_authorized=True))
            self.assertEqual(json.loads(p.read_text()), EMPTY)

    def test_uncertain_apply_no_evidence_no_retry(self):
        s, w, p = make_session(self.root / 'uncertain', training=True)
        from clc.experience.bounded_native_acquisition import BoundedNativeAcquisition
        a = BoundedNativeAcquisition(s, isolated_root=p.parent, writer=w)
        original = s.components.world.apply_actuator_signal
        def uncertain(signal):
            original(signal)
            raise OSError('unknown apply outcome')
        with patch.object(s.components.world, 'apply_actuator_signal', side_effect=uncertain) as apply:
            s.run()
            s.resume()
            s.run()
            self.assertEqual(apply.call_count, 1)
        self.assertEqual(admit_all(s, a), ())
        self.assertIsNone(prepare(a))
        self.assertIsNone(a.create(test_owner_authorized=True))

    def test_full_set_conflict(self):
        s, w, p = make_session(self.root / 'conflict', training=True, training_actions=5)
        from clc.experience.bounded_native_acquisition import BoundedNativeAcquisition
        a = BoundedNativeAcquisition(s, isolated_root=p.parent, writer=w)
        original = s.components.world.snapshot
        def sensor_fault():
            snap = original()
            return replace(snap, values=(1., 0.)) if snap.active_tick == 5 else snap
        with patch.object(s.components.world, 'snapshot', side_effect=sensor_fault):
            s.run()
        self.assertEqual([r.status for r in admit_all(s, a)], ['admitted'] * 5)
        self.assertTrue(any(c.support_count >= 2 for c in a.candidates))
        a.seal()
        self.assertIsNone(a.prepare(a.candidates[0].candidate_id))
        self.assertEqual(a.state, 'stopped_effect_conflict')
        self.assertIsNone(a.create(test_owner_authorized=True))

    def test_policy_denial(self):
        s, a, w, p = self.ready(profile='safe_demo')
        self.assertEqual(a.create(test_owner_authorized=True).status, CS.DENIED_BY_POLICY)
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(json.loads(p.read_text()), EMPTY)

    def test_readback_recovery_no_retry(self):
        for outcome in ('persisted', 'unresolved'):
            s, a, w, p = self.ready()
            def fault(stage):
                if stage == 'post_replace_readback':
                    if outcome == 'unresolved':
                        p.write_text('malformed')
                    raise OSError('readback failed')
            w.failure_hook = fault
            self.assertEqual(a.create(test_owner_authorized=True).status, CS.READBACK_FAILED)
            self.assertEqual(a.readback.status, RS.CONFIRMED_PERSISTED if outcome == 'persisted' else RS.UNRESOLVED_OR_STORE_INVALID)
            self.assertIsNone(a.create(test_owner_authorized=True))
            if outcome == 'unresolved':
                self.assertEqual(a.state, 'stopped_unresolved')

    def assert_unadmitted(self, owner, before=((), (), ())):
        self.assertEqual((owner.reservations, owner.envelopes, owner.candidates), before)

    def test_reclassification_original_reproduction_is_rejected(self):
        s, a, w, p = self.train()
        for index in (0, 2):
            r = s.records[index]
            s.records[index] = replace(r, execution=replace(r.execution,
                exploratory_intent=None, source_experience_id='fabricated-remembered-source'))
        s.exploration.authorization = None
        self.assertTrue(all(r.status != 'admitted' for r in admit_all(s, a)))
        self.assert_unadmitted(a)
        self.assertIsNone(prepare(a))
        self.assertIsNone(a.create(test_owner_authorized=True))
        self.assertEqual(json.loads(p.read_text()), EMPTY)

    def test_reclassification_with_missing_policy_history_is_rejected(self):
        from clc.actuation.synthetic_exploration import SyntheticExplorationPolicy
        for missing in ('entries', 'policy'):
            s, a, w, p = self.train()
            r = s.records[0]
            s.records[0] = replace(r, execution=replace(r.execution,
                exploratory_intent=None, source_experience_id='fabricated-source'))
            if missing == 'policy':
                s.exploration = None
            with patch.object(SyntheticExplorationPolicy, 'diagnostics', new_callable=PropertyMock,
                              return_value=()):
                self.assertNotEqual(a.admit(s.components.short_memory.snapshot()[0]).status, 'admitted')
            self.assert_unadmitted(a)
            self.assertIsNone(prepare(a))
            self.assertIsNone(a.create(test_owner_authorized=True))

    def test_transition_metadata_budget_preserves_terminal_stop(self):
        s, a, w, p = self.train()
        t = replace(s.components.short_memory.snapshot()[0], transition_id='x' * 257)
        self.assertEqual(a.admit(t).status, 'stopped_payload_budget')
        self.assert_unadmitted(a)
        self.assertEqual(a.admit(t).status, 'stopped_payload_budget')

    def test_one_forged_source_preserves_previous_admission(self):
        s, a, w, p = self.train()
        ts = s.components.short_memory.snapshot()
        self.assertEqual(a.admit(ts[0]).status, 'admitted')
        before = (a.reservations, a.envelopes, a.candidates)
        r = s.records[2]
        s.records[2] = replace(r, execution=replace(r.execution, source_experience_id='forged'))
        self.assertNotEqual(a.admit(ts[2]).status, 'admitted')
        self.assert_unadmitted(a, before)
        self.assertEqual(a.candidates[0].support_count, 1)
        self.assertIsNone(prepare(a))
        self.assertIsNone(a.create(test_owner_authorized=True))

    def test_unavailable_or_mismatched_diagnostics_fail_before_reservation(self):
        from clc.actuation.synthetic_exploration import SyntheticExplorationPolicy
        for field in ('missing', 'unavailable', 'session', 'occurrence', 'intent_session'):
            with self.subTest(field=field):
                s, a, w, p = self.train()
                policy = s.exploration
                if field == 'session':
                    policy.session_id = 'other-session'
                elif field in ('occurrence', 'intent_session'):
                    entry = policy.diagnostics[0]
                    changed = replace(entry, execution_occurrence_id=str(uuid4())) if field == 'occurrence' else replace(
                        entry, intent=replace(entry.intent, session_id='other-session'))
                    policy._entries[0] = changed  # negative fault injection only
                diagnostics = () if field == 'missing' else None if field == 'unavailable' else policy.diagnostics
                with patch.object(SyntheticExplorationPolicy, 'diagnostics', new_callable=PropertyMock,
                                  return_value=diagnostics):
                    self.assertNotEqual(a.admit(s.components.short_memory.snapshot()[0]).status, 'admitted')
                self.assert_unadmitted(a)
                self.assertIsNone(prepare(a))

    def test_remembered_admission_ignores_unrelated_historical_occurrence(self):
        from tools.verify_bounded_native_acquisition import AcquisitionTests
        from clc.actuation.synthetic_exploration import (
            SyntheticExplorationConfig, SyntheticExplorationAuthorization, SyntheticExplorationPolicy,
            ExploratoryIntent, ExplorationDiagnostic,
        )
        # Existing RND-021 genuine remembered producer, not a fabricated selection.
        fixture = AcquisitionTests('test_single_and_replay_never_gain_support')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        s, a, p, original = fixture.fixture()
        t = fixture.targets(s)[0]
        config = SyntheticExplorationConfig('history-config', ((0., 1.),))
        policy = SyntheticExplorationPolicy(config,
            SyntheticExplorationAuthorization('history-owner', 'history-auth', config.configuration_id),
            s.session_id, s.components.world)
        foreign = ExploratoryIntent('foreign-intent', 'history-auth', 'history-owner',
            config.configuration_id, 'unrelated-session', 'foreign-window', 0, 0, (0., 1.))
        policy._entries.append(ExplorationDiagnostic(foreign,
            execution_occurrence_id=t.execution_occurrence_id))
        s.exploration = policy
        result = a.admit(t)
        self.assertEqual(result.status, 'admitted')
        self.assertIsNone(result.envelope.exploratory_provenance)
        self.assertEqual(result.envelope.execution.source_experience_id, s.records[0].execution.source_experience_id)
        self.assertEqual(p.read_bytes(), original)

    def test_all_projection_identity_fields_require_exact_bounded_strings(self):
        from clc.experience.bounded_native_acquisition import ExploratoryAcquisitionProvenance
        names = tuple(ExploratoryAcquisitionProvenance.__dataclass_fields__)
        values = {name: name for name in names}
        for name in names:
            with self.subTest(field=name):
                boundary = {**values, name: 'x' * 256}
                projection = ExploratoryAcquisitionProvenance(**boundary)
                self.assertEqual(getattr(projection, name), boundary[name])
                self.assertIs(type(getattr(projection, name)), str)
                with self.assertRaises(FrozenInstanceError):
                    setattr(projection, name, 'changed')
                for bad in ('', 'x' * 257, NestedIdentity('short', bytearray(1_000_000))):
                    with self.assertRaises(ValueError):
                        ExploratoryAcquisitionProvenance(**{**values, name: bad})

    def identity_training(self, field, value):
        from clc.actuation.synthetic_exploration import SyntheticExplorationConfig, SyntheticExplorationAuthorization
        from clc.runtime.native_bounded_delivery import NativeDeliverySession, DeliveryLimits, Control
        from clc.experience.bounded_native_acquisition import BoundedNativeAcquisition
        root = self.root / str(len(list(self.root.iterdir())))
        base, writer, path = make_session(root)
        c = base.components
        del base
        identity = value(c.world) if callable(value) else value
        config_id = identity if field == 'configuration_id' else 'bounded-config'
        config = SyntheticExplorationConfig(config_id, ((0., 1.), (1., 0.)), 3, 3)
        auth = SyntheticExplorationAuthorization(
            identity if field == 'test_owner_id' else 'bounded-owner',
            identity if field == 'authorization_id' else 'bounded-auth', config_id)
        def ingress(tick, delivery):
            if tick == 3:
                delivery.accept(Control.PAUSE, source_id='test-owner', stream_id='control')
        session = NativeDeliverySession(c, max_ticks=4, ingress=ingress,
            limits=DeliveryLimits(journal_capacity=128), exploration_config=config,
            exploration_authorization=auth)
        owner = BoundedNativeAcquisition(session, isolated_root=root, writer=writer)
        session.run()
        return session, owner, writer, path

    def test_public_authorization_identity_boundary_is_preserved(self):
        for field in ('authorization_id', 'test_owner_id', 'configuration_id'):
            s, a, w, p = self.identity_training(field, 'x' * 256)
            self.assertEqual([r.status for r in admit_all(s, a)], ['admitted'] * 3)
            self.assertTrue(all(getattr(e.exploratory_provenance, field) == 'x' * 256 for e in a.envelopes))

    def test_public_subclass_refusal_releases_payload_and_world(self):
        for field in ('authorization_id', 'test_owner_id', 'configuration_id'):
            for world_reference in (False, True):
                with self.subTest(field=field, world_reference=world_reference):
                    s, a, w, p = self.identity_training(field,
                        lambda world: NestedIdentity('review-owner', (world, bytearray(1_000_000)) if world_reference else bytearray(1_000_000)))
                    identity = getattr(s.exploration.authorization, field)
                    identity_ref, world_ref = weakref.ref(identity), weakref.ref(s.components.world)
                    self.assertTrue(all(r.status != 'admitted' for r in admit_all(s, a)))
                    self.assert_unadmitted(a)
                    del identity, s
                    gc.collect()
                    self.assertIsNone(identity_ref())
                    self.assertIsNone(world_ref())
                    self.assert_unadmitted(a)
                    self.assertEqual(json.loads(p.read_text()), EMPTY)

    def test_successful_plain_projection_releases_session_and_world(self):
        s, a, w, p = self.identity_training('test_owner_id', 'ordinary-owner')
        self.assertEqual([r.status for r in admit_all(s, a)], ['admitted'] * 3)
        audit = tuple(asdict(e.exploratory_provenance) for e in a.envelopes)
        session_ref, world_ref = weakref.ref(s), weakref.ref(s.components.world)
        del s
        gc.collect()
        self.assertIsNone(session_ref())
        self.assertIsNone(world_ref())
        self.assertEqual(tuple(asdict(e.exploratory_provenance) for e in a.envelopes), audit)
        self.assertIsNotNone(prepare(a))
        self.assertEqual(a.create(test_owner_authorized=True).status, CS.CREATED)
        self.assertEqual(a.readback.status, RS.CONFIRMED_PERSISTED)

    def test_related_scope_and_transition_subclasses_are_not_retained(self):
        from clc.experience.bounded_native_acquisition import BoundedNativeAcquisition
        for field in ('session_id', 'source_id'):
            s, w, p = make_session(self.root / field, training=True)
            identity = NestedIdentity(s.session_id if field == 'session_id' else s.delivery.VISUAL_SOURCE,
                                      s.components.world)
            if field == 'session_id':
                s.session_id = identity
            else:
                s.delivery.VISUAL_SOURCE = identity
            with self.assertRaises(ValueError):
                BoundedNativeAcquisition(s, isolated_root=p.parent, writer=w)
        for field in ('execution_occurrence_id', 'transition_id'):
            s, a, w, p = self.train()
            t = s.components.short_memory.snapshot()[0]
            altered = replace(t, **{field: NestedIdentity(getattr(t, field), s.components.world)})
            self.assertNotEqual(a.admit(altered).status, 'admitted')
            self.assert_unadmitted(a)

    def test_provenance_exceptions_stop_without_partial_admission(self):
        from clc.actuation.synthetic_exploration import SyntheticExplorationPolicy
        for target in ('constructor', 'diagnostics'):
            s, a, w, p = self.train()
            t = s.components.short_memory.snapshot()[0]
            context = patch('clc.experience.bounded_native_acquisition.ExploratoryAcquisitionProvenance',
                            side_effect=MemoryError('injected')) if target == 'constructor' else patch.object(
                                SyntheticExplorationPolicy, 'diagnostics', new_callable=PropertyMock,
                                side_effect=RuntimeError('injected'))
            with context:
                with self.assertRaises((MemoryError, RuntimeError)):
                    a.admit(t)
            self.assert_unadmitted(a)
            diagnostic = a.stop_diagnostic
            self.assertEqual(a.state, 'stopped_provenance_error')
            self.assertEqual(a.admit(t).status, 'stopped_provenance_error')
            self.assertIs(a.stop_diagnostic, diagnostic)
            self.assertIsNone(prepare(a))
            self.assertIsNone(a.create(test_owner_authorized=True))
            self.assertEqual(json.loads(p.read_text()), EMPTY)


if __name__ == '__main__':
    unittest.main(verbosity=2)
