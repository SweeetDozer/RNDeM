"""RND-015 differential behavior on exclusively temporary Memory roots."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

from legacy_native_joint_checkpoint import (
    LegacyAdapter, NativeAdapter, JointLifecycle, inventory, plain,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import run_scenario_fixture
from clc.runtime.runtime_phase_map import RUNTIME_PHASE_MAP
from clc.runtime.heart import HeartState
from clc.patterns import PatternOrigin
from phase_regression_snapshots import read_snapshot, snapshot_path

FIXTURES = ('real_input_repeated_audio_signal', 'real_input_conflicting_sensor_signal')


def fixture(name=FIXTURES[0]):
    return load_scenario(ROOT / 'scenarios' / (name + '.json'))


def native_trace(adapter):
    """Alpha-rename only generated identities; preserve equality and all refs.

    Map session scope, actual materialized occurrence UUIDs and delivery UUIDs.
    Values, source IDs, provenance, origin, ticks, counters and diagnostics stay.
    Generated UUID literals are random, their linkage and distinctness are semantic.
    """
    s = adapter.session
    names = {s.session_id: '<session>'}
    for r in s.records:
        if r.execution and r.execution.execution_occurrence_id:
            key = r.execution.execution_occurrence_id
            names.setdefault(key, f'<occurrence:{len(names)}>')
    for item in s.delivery.journal:
        if item.event:
            key = item.event.delivery_event_id
            names.setdefault(key, f'<delivery:{len(names)}>')
    def rename(v):
        if isinstance(v, str):
            for identity, alias in names.items():
                v = v.replace(identity, alias)
            return v
        if isinstance(v, dict):
            return {k: rename(x) for k, x in v.items()}
        if isinstance(v, list):
            return [rename(x) for x in v]
        return v
    c = s.components
    return rename(plain({'records': s.records, 'stop': s.stop_report(),
        'journal': list(s.delivery.journal), 'counts': s.delivery.counts,
        'events': adapter.events, 'queries': c.retriever.calls,
        'pending_log': c.context_manager.pending_log, 'short': c.short_memory.snapshot(),
        'samples': c.world.samples, 'applies': c.world.applies, 'idles': c.world.idles,
        'position': c.world.hidden_position, 'depths': s.delivery.depths}))


class JointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = inventory()

    @classmethod
    def tearDownClass(cls):
        if inventory() != cls.original:
            raise AssertionError('full original Memory file inventory/bytes changed')

    def pair(self, f=None, **opts):
        legacy = LegacyAdapter(f or fixture())
        self.addCleanup(legacy.close)
        native = NativeAdapter(**opts)
        self.addCleanup(native.close)
        return legacy, native, JointLifecycle(legacy, native)

    def command(self, target, method, arg=None):
        return target, method, arg

    def test_differential_matrix(self):
        # Ten joint scenarios vs independent adapter execution AND public runner.
        for name in FIXTURES:
            f = fixture(name)
            baseline = run_scenario_fixture(f)
            self.assertTrue(baseline.passed, baseline.warnings)
            expected = read_snapshot(snapshot_path(name))
            self.assertEqual(baseline.regression_summary, expected)
            for opts in ({'sensing': False}, {}, {'empty': True}, {'flood': True}, {'mode': 'consolidation'}):
                with self.subTest(fixture=name, options=opts):
                    left, native_left, _ = self.pair(f, **opts)
                    right, native_right, h = self.pair(f, **opts)
                    left.start()
                    for item in f.inputs:
                        left.feed(item)
                    native_left.start()
                    for _ in range(5):
                        native_left.step()
                    plan = [self.command('legacy', 'start'), self.command('native', 'start')]
                    for i, item in enumerate(f.inputs):
                        plan.append(self.command('legacy', 'feed', item))
                        if i < 5:
                            plan.append(self.command('native', 'step'))
                    report = h.run(plan)
                    self.assertFalse(report['errors'])
                    self.assertEqual(left.phases, right.phases)
                    self.assertEqual(left.drains, right.drains)
                    self.assertEqual(left.summary(), right.summary())
                    summary = right.summary()
                    summary['memory_safety'] = baseline.regression_summary['memory_safety']
                    self.assertEqual(summary, baseline.regression_summary)
                    self.assertEqual(native_trace(native_left), native_trace(native_right))
                    self.assert_native(native_right)
                    self.assert_legacy(right)
                    self.assertEqual(inventory(left.root), inventory(right.root))
                    # Release large phase traces and temp copies per matrix cell.
                    for a in (left, right, native_left, native_right):
                        a.close()

    def assert_legacy(self, a):
        phases = a.phases
        expected = [p.phase_id for p in RUNTIME_PHASE_MAP]
        self.assertEqual([p['phase'] for p in phases], expected * len(a.feeds))
        self.assertEqual([p['tick'] for p in phases], [t for _, t in a.feeds for _ in expected])
        # Manager consumes precisely the FIFO returned by the original pool drain.
        drained = [op for _, _, ops in a.drains for op in ops]
        # ContextMemory.add_event adds exactly this metadata on commit.
        for op in drained:
            op['payload']['_event_tick'] = op['tick']
        self.assertEqual(drained, plain(a.runtime.memory.events))
        witnessed_late = False
        witnessed_next_candidate = False
        for offset in range(0, len(phases), 12):
            cycle = phases[offset:offset + 12]
            raw = [e for e in cycle[0]['after']['events'] if e['marker'] == 1 and e['tick'] == cycle[0]['tick']]
            self.assertTrue(raw)
            self.assertTrue(all(e in cycle[3]['before']['events'] for e in raw))
            early = {e['op_id'] for e in cycle[3]['before']['events']}
            before = {e['op_id'] for e in cycle[6]['before']['events']}
            late = [e for e in cycle[6]['after']['events'] if e['op_id'] not in before]
            if late:
                witnessed_late = True
                self.assertFalse(early.intersection(e['op_id'] for e in late))
                if offset + 12 < len(phases):
                    following = phases[offset + 15]['before']['events']
                    self.assertTrue(all(e in following for e in late))
            # Phase 06 emits search events; the next ActionProposer (03)
            # materializes their candidates. It does not emit candidates in 06.
            search_ids = {e['payload']['mechanism_search_id'] for e in late
                          if 'mechanism_search_id' in e['payload']}
            early_refs = {c['source_metadata'].get('source_mechanism_search_id')
                          for c in cycle[3]['after']['candidates']}
            self.assertFalse(search_ids.intersection(early_refs))
            if search_ids and offset + 12 < len(phases):
                next_refs = {c['source_metadata'].get('source_mechanism_search_id')
                             for c in phases[offset + 15]['after']['candidates']}
                witnessed_next_candidate |= bool(search_ids.intersection(next_refs))
        self.assertTrue(witnessed_late)
        # This audio fixture actually produces a match; the sensor fixture
        # emits search diagnostics without a matching mechanism candidate.
        if a.fixture.name == FIXTURES[0]:
            self.assertTrue(witnessed_next_candidate)

    def assert_native(self, a):
        s = a.session
        c = s.components
        self.assertEqual([r.tick for r in s.records], list(range(len(s.records))))
        self.assertEqual(s.heart.tick, c.world.current_tick)
        self.assertEqual(len(c.world.applies) + len(c.world.idles), len(s.records))
        occurrences = []
        for i, r in enumerate(s.records):
            if r.observation:
                frame = r.observation.frames[0]
                self.assertEqual(frame.origin, PatternOrigin.EXTERNAL_SENSORY)
                self.assertEqual(frame.active_tick, r.tick)
                self.assertEqual(frame.provenance_ref, f'sensor_snapshot:{c.world.samples[i].snapshot_id:06d}')
            else:
                self.assertIsNone(r.execution)
            if r.execution:
                e = r.execution
                occurrence = e.execution_occurrence_id
                self.assertEqual(str(UUID(occurrence, version=4)), occurrence)
                occurrences.append(occurrence)
                self.assertEqual(e.action_frame.origin, PatternOrigin.ACTION_GENERATED)
                self.assertIsNone(e.action_frame.provenance_ref)
                self.assertIsNone(e.recent_transition)
            if r.recent:
                previous = s.records[i - 1]
                self.assertEqual((r.recent.action_tick, r.recent.observation_tick), (i - 1, i))
                self.assertEqual(r.recent.execution_occurrence_id, previous.execution.execution_occurrence_id)
                self.assertIs(r.recent.before_sensory_window, previous.observation)
                self.assertIs(r.recent.after_sensory_window, r.observation)
                if r.execution and r.execution.actuator_signal is not None:
                    self.assertLess(a.events.index(('remember', i)), a.events.index(('apply', i)))
        self.assertEqual(len(occurrences), len(set(occurrences)))

    def test_native_idle_never_invokes_legacy_feed(self):
        l, n, h = self.pair(sensing=False)
        h.run([self.command('legacy', 'start'), self.command('native', 'start')])
        l.feed(l.fixture.inputs[0])
        before = (plain(l.phases), plain(l.drains), l.snapshot())
        h.run([self.command('native', 'step')] * 5)
        self.assertEqual(before, (plain(l.phases), plain(l.drains), l.snapshot()))
        self.assertEqual(len(n.session.components.world.idles), 5)
        self.assertEqual(n.session.components.retriever.calls, [])
        self.assertTrue(all(r.observation is None and r.execution is None for r in n.session.records))

    def test_feed_between_native_ticks_and_no_cross_delivery(self):
        l, n, h = self.pair(ticks=3)
        h.run([self.command('legacy', 'start'), self.command('native', 'start'), self.command('native', 'step')])
        s = n.session
        before = native_trace(n)
        l.feed(l.fixture.inputs[0])
        self.assertEqual(before, native_trace(n))
        self.assertIsNone(l.runtime.manager.current_external_sensory_window)
        context = l.snapshot()
        h.run([self.command('native', 'step')])
        self.assertEqual(context, l.snapshot())
        self.assertEqual(s.records[1].recent.observation_tick, 1)
        self.assertEqual(len(s.components.world.applies), 2)
        self.assertEqual(len(s.components.retriever.calls), 2)
        self.assertEqual(s.records[1].observation.frames[0].values, (0., 1., 0., 0.))

    def test_flood_preserves_protected_observation(self):
        l, n, h = self.pair(ticks=3, flood=True)
        h.run([self.command('legacy', 'start'), self.command('native', 'start')] +
              [cmd for i in range(3) for cmd in (self.command('native', 'step'),
                self.command('legacy', 'feed', l.fixture.inputs[i]))])
        self.assert_native(n)
        s = n.session
        causal = [x.event for x in s.delivery.journal if x.stage == 'causal_observed']
        self.assertEqual(len(causal), 2)
        self.assertEqual(causal[0].execution_occurrence_id, s.records[0].execution.execution_occurrence_id)
        self.assertGreater(s.delivery.counts['rejected'], 290)
        self.assertEqual(len(s.components.world.applies), 3)

    def test_legacy_pause_stop_are_admission_gates_without_backlog(self):
        l, n, h = self.pair(ticks=3)
        h.run([self.command('legacy', 'start'), self.command('native', 'start'),
               self.command('native', 'step'), self.command('legacy', 'pause'),
               self.command('legacy', 'feed', l.fixture.inputs[0]), self.command('legacy', 'resume'),
               self.command('legacy', 'stop'), self.command('legacy', 'start'),
               self.command('legacy', 'feed', l.fixture.inputs[1]), self.command('native', 'step')])
        self.assertEqual(l.feeds, [])
        self.assertEqual(len(n.session.components.world.applies), 2)
        self.assertEqual(n.session.records[1].recent.observation_tick, 1)

    def test_native_pause_stop_never_retries_and_legacy_continues(self):
        l, n, h = self.pair(ticks=4)
        h.run([self.command('legacy', 'start'), self.command('native', 'start'), self.command('native', 'step'),
               self.command('native', 'pause'), self.command('native', 'step'),
               self.command('legacy', 'feed', l.fixture.inputs[0])])
        pending = n.session.components.context_manager.pending_causal_transition
        self.assertEqual(n.session.heart.tick, 1)
        h.run([self.command('native', 'stop'), self.command('native', 'resume'),
               self.command('native', 'start'), self.command('native', 'step'),
               self.command('legacy', 'feed', l.fixture.inputs[1])])
        self.assertEqual(len(n.session.components.world.applies), 1)
        self.assertEqual(n.session.stop_report().unresolved_occurrences, (pending.execution_occurrence_id,))
        self.assertEqual(len(l.feeds), 2)

    def test_native_resume_and_missing_T1_with_legacy_interleaving(self):
        l, n, h = self.pair(ticks=4)
        s = n.session
        s.sample_enabled = lambda t: t == 0
        h.run([self.command('legacy', 'start'), self.command('native', 'start'),
            self.command('native', 'step'), self.command('native', 'pause'),
            self.command('legacy', 'feed', l.fixture.inputs[0]), self.command('native', 'step')])
        pending = s.components.context_manager.pending_causal_transition
        self.assertEqual((s.heart.tick, s.components.world.current_tick), (1, 1))
        h.run([self.command('native', 'resume'), self.command('native', 'step')])
        self.assertIs(s.components.context_manager.pending_causal_transition, pending)
        self.assertIsNone(s.records[1].observation)
        self.assertIsNone(s.records[1].execution)
        h.run([self.command('legacy', 'feed', l.fixture.inputs[1]), self.command('native', 'step')])
        self.assertIs(s.records[2].expired, pending)
        self.assertIsNone(s.components.context_manager.pending_causal_transition)
        self.assertEqual((len(s.components.world.applies), len(s.components.world.idles)), (1, 2))
        self.assertEqual(len(s.components.short_memory), 0)
        self.assertIn(pending.execution_occurrence_id, s.stop_report().unresolved_occurrences)

    def test_native_exception_reports_partial_result_without_retry(self):
        l, n, h = self.pair(failure='sensor')
        report = h.run([self.command('legacy', 'start'), self.command('native', 'start'),
            self.command('native', 'step'), self.command('native', 'step'),
            self.command('legacy', 'feed', l.fixture.inputs[0]), self.command('native', 'step')])
        self.assertEqual(report['errors']['native']['type'], 'RuntimeError')
        self.assertEqual(len(l.feeds), 1)
        self.assertTrue(report['native_stop'].unresolved_occurrences)
        self.assertTrue(report['native_stop'].synchronization_blocked)
        self.assertEqual(len(n.session.components.world.applies), 1)

    def test_uncertain_world_result_is_not_hidden_or_retried(self):
        l, n, h = self.pair(failure='after')
        report = h.run([self.command('native', 'start'), self.command('native', 'step'),
            self.command('legacy', 'start'), self.command('legacy', 'feed', l.fixture.inputs[0]),
            self.command('native', 'step'), self.command('native', 'resume'), self.command('native', 'step')])
        stop = report['native_stop']
        self.assertTrue(stop.synchronization_blocked)
        self.assertTrue(stop.unresolved_occurrences)
        self.assertIn('physical_result_may_be_uncertain', stop.diagnostic)
        self.assertEqual(len(n.session.components.world.applies), 1)
        self.assertEqual(n.session.components.world.hidden_position, (0, 1))
        self.assertEqual(len(l.feeds), 1)
        self.assertEqual(n.session.components.world.idles, [])

    def test_legacy_exception_stops_only_legacy_no_replay(self):
        l, n, h = self.pair(ticks=2)
        bad = replace(l.fixture.inputs[0], payload={'frequencies': {'invalid': .5}})
        report = h.run([self.command('legacy', 'start'), self.command('native', 'start'),
            self.command('legacy', 'feed', bad), self.command('native', 'step'),
            self.command('legacy', 'feed', l.fixture.inputs[0]), self.command('native', 'step')])
        self.assertEqual(report['errors']['legacy']['type'], 'ValueError')
        self.assertEqual(l.feeds, [])
        self.assertEqual(len(n.session.components.world.applies), 2)
        self.assertEqual(n.session.records[1].recent.observation_tick, 1)

    def test_separate_mutable_roots_and_registries(self):
        l, n, h = self.pair()
        self.assertNotEqual(l.root, n.root)
        self.assertNotEqual(l.root.resolve(), (ROOT / 'Memory').resolve())
        c = n.session.components
        self.assertIsNot(l.runtime.memory, c.context_manager.memory)
        self.assertIsNot(l.runtime.ops_pool, c.context_manager.ops_pool)
        self.assertIsNot(l.runtime.pattern_registry, n.registry)
        self.assertIsNot(l.runtime.expsm, c.retriever)
        self.assertFalse(hasattr(l.runtime, 'short_memory'))
        before = inventory(n.root)
        l.runtime.pattern_registry.id('rnd015_legacy_only')
        self.assertEqual(inventory(n.root), before)
        before = inventory(l.root)
        n.registry.id('rnd015_native_only')
        self.assertEqual(inventory(l.root), before)
        self.assertEqual(inventory(), self.original)

    def test_same_caller_tick_remains_two_cycles(self):
        f = fixture()
        f = replace(f, inputs=[f.inputs[0], replace(f.inputs[1], tick=f.inputs[0].tick)])
        l, n, h = self.pair(f, ticks=1, sensing=False)
        h.run([self.command('legacy', 'start'), self.command('native', 'start'),
            self.command('legacy', 'feed', f.inputs[0]), self.command('native', 'step'),
            self.command('legacy', 'feed', f.inputs[1])])
        self.assertEqual(len(l.phases), 24)
        self.assertEqual([p['phase'] for p in l.phases], [p.phase_id for p in RUNTIME_PHASE_MAP] * 2)
        self.assertEqual({p['tick'] for p in l.phases}, {1})
        self.assertEqual(n.session.heart.tick, 1)

    def test_plan_budget_and_ports_reject_before_execution(self):
        l, n, h = self.pair()
        with self.assertRaises(ValueError):
            h.run([self.command('native', 'step')] * 129)
        with self.assertRaises(ValueError):
            h.run([self.command('native', 'start'), self.command('native', 'feed', l.fixture.inputs[0])])
        self.assertEqual(n.session.heart.state, HeartState.READY)
        self.assertEqual(h.used, 0)
        with self.assertRaises(ValueError):
            LegacyAdapter(replace(fixture(), inputs=[replace(fixture().inputs[0], kind='tick')]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
