"""RND-016 targeted checks; all writable runtime fixtures use temporary roots."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clc.echo.expectations import EchoExpectations
from clc.context.short_memory import ShortMemory
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology
from tools.verify_nfp_context_short_memory import recent, memory_inventory
from tools import verify_native_heart_b2 as b2


def window(tick, values=(1., 0.), **changes):
    frame = NFPFrame(f'f:{tick}', PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY,
                     PatternTopology((len(values),)), values, tick, provenance_ref=f'sensor:{tick}')
    return NFPWindow(f'w:{tick}', (replace(frame, **changes),))


class EchoTests(unittest.TestCase):
    def setUp(self):
        original = memory_inventory()
        self.addCleanup(lambda: self.assertEqual(memory_inventory(), original))
        self.echo = EchoExpectations()
        self.entry = self.echo.expect(window(0), expected_coordinates=(0,),
                                      opposing_coordinates=(1,), ttl=4)

    def match(self, tick, observation):
        return self.echo.advance(tick, observation)[0]

    def test_gap_continuation_and_provenance(self):
        self.assertEqual(self.match(1, None).outcome, 'no_data')
        self.assertEqual(self.match(2, None).outcome, 'no_data')
        result = self.match(3, window(3))
        self.assertEqual(result.outcome, 'support')
        self.assertTrue(result.possible_continuation)
        self.assertFalse(result.identity_confirmed)
        self.assertEqual((result.source_window_id, result.observation_id), ('w:0', 'w:3'))
        self.assertEqual(self.echo.snapshot()[0].expectation_id, self.entry.expectation_id)
        self.assertEqual(self.echo.snapshot()[0].expires_at, 4)

    def test_missing_absence_contradiction_are_distinct(self):
        self.assertEqual(self.match(1, None).outcome, 'no_data')
        self.assertEqual(self.match(2, window(2, (0., 0.))).outcome, 'observed_absence')
        self.assertEqual(self.match(3, window(3, (0., 1.))).outcome, 'contradiction')
        self.assertEqual(self.echo.snapshot()[0].state, 'contradicted')
        self.assertEqual(self.echo.advance(4, window(4)), ())

    def test_uncertainty_and_incompatible_topology(self):
        self.assertEqual(self.match(1, window(1, (.2, 0.))).outcome, 'inconclusive')
        self.assertEqual(self.match(2, window(2, (1., 0., 0.))).outcome, 'incomparable')
        self.assertEqual(self.echo.snapshot()[0].state, 'open')

    def test_support_does_not_require_similarity_or_assert_identity(self):
        echo = EchoExpectations(continuation_threshold=.9)
        echo.expect(window(0), expected_coordinates=(1,), ttl=4)
        result = echo.advance(1, window(1, (0., 1.)))[0]
        self.assertEqual(result.outcome, 'support')
        self.assertFalse(result.possible_continuation)
        self.assertFalse(result.identity_confirmed)

    def test_observed_absence_keeps_expectation_open(self):
        self.assertEqual(self.match(1, window(1, (0., 0.))).outcome, 'observed_absence')
        self.assertEqual(self.echo.snapshot()[0].state, 'open')
        self.assertEqual(self.match(2, window(2)).outcome, 'support')

    def test_deadline_is_inclusive_and_not_failure(self):
        self.assertEqual(self.match(4, window(4)).outcome, 'support')
        result = self.match(5, window(5))
        self.assertEqual(result.outcome, 'expired')
        self.assertFalse(result.possible_continuation)
        self.assertEqual(self.echo.snapshot(), ())

    def test_no_self_evaluation_replay_or_stale_input(self):
        self.assertEqual(self.echo.advance(0, window(0)), ())
        for tick, observation in [(0, window(0)), (1, window(0)), (1, window(1, origin=PatternOrigin.INTERNAL_REACTIVATION))]:
            with self.assertRaises(ValueError):
                self.echo.advance(tick, observation)
        self.assertEqual(self.match(1, window(1)).outcome, 'support')

    def test_determinism_ignores_debug_names(self):
        other = EchoExpectations()
        other.expect(window(0, debug_name='unrelated'), expected_coordinates=(0,),
                     opposing_coordinates=(1,), ttl=4)
        for tick, observation in [(1, None), (2, window(2)), (5, None)]:
            self.assertEqual(self.echo.advance(tick, observation), other.advance(tick, observation))

    def test_bounded_capacity_and_validation(self):
        echo = EchoExpectations(max_entries=1)
        for spec in [dict(expected_coordinates=(), ttl=1), dict(expected_coordinates=(2,), ttl=1),
                     dict(expected_coordinates=(0,), opposing_coordinates=(0,), ttl=1),
                     dict(expected_coordinates=(0,), ttl=0)]:
            with self.assertRaises(ValueError):
                echo.expect(window(0), **spec)
        echo.expect(window(0), expected_coordinates=(0,), ttl=1)
        with self.assertRaises(ValueError):
            echo.expect(window(0), expected_coordinates=(0,), ttl=1)
        echo.advance(2, None)
        echo.expect(window(2), expected_coordinates=(0,), ttl=1)
        self.assertEqual(len(echo.snapshot()), 1)

    def test_short_memory_retained_transition_only(self):
        memory = ShortMemory(2, 2)
        transition = recent(1)
        memory.remember(transition, current_tick=1)
        echo = EchoExpectations()
        entry = echo.expect_transition(memory, transition.transition_id,
                                       expected_coordinates=(1,), ttl=4)
        self.assertIs(entry.source, transition.after_sensory_window)
        memory.prune(4)
        with self.assertRaises(ValueError):
            echo.expect_transition(memory, transition.transition_id, expected_coordinates=(1,), ttl=4)
        result = echo.advance(4, window(4, (0., 1.)))[0]
        self.assertEqual(result.history_transition_id, transition.transition_id)
        self.assertTrue(result.possible_continuation)
        self.assertEqual(len(memory), 0)

    def test_partial_multi_coordinate_match_is_inconclusive(self):
        echo = EchoExpectations()
        echo.expect(window(0, (1., 1., 0.)), expected_coordinates=(0, 1), ttl=3)
        result = echo.advance(1, window(1, (1., 0., 0.)))[0]
        self.assertEqual(result.outcome, 'inconclusive')
        self.assertFalse(result.possible_continuation)
        self.assertEqual(echo.snapshot()[0].state, 'open')
        self.assertEqual(echo.advance(2, window(2, (1., 1., 0.)))[0].outcome, 'support')

    def test_similar_candidates_remain_separate_hypotheses(self):
        echo = EchoExpectations()
        first = echo.expect(window(0), expected_coordinates=(0,), ttl=4)
        alternative = replace(window(0, (.95, 0.)), window_id='alternative',
                              frames=(replace(window(0, (.95, 0.)).frames[0],
                                              frame_id='alternative-frame',
                                              provenance_ref='alternative-sensor'),))
        second = echo.expect(alternative, expected_coordinates=(0,), ttl=4)
        echo.advance(1, None)
        echo.advance(2, None)
        results = echo.advance(3, window(3))
        self.assertEqual({r.expectation_id for r in results},
                         {first.expectation_id, second.expectation_id})
        self.assertEqual({r.source_window_id for r in results}, {'w:0', 'alternative'})
        self.assertTrue(all(r.outcome == 'support' and r.possible_continuation for r in results))
        self.assertTrue(all(not r.identity_confirmed for r in results))
        self.assertEqual(len(echo.snapshot()), 2)

    def test_echo_does_not_change_native_execution_or_short_memory(self):
        fixture = b2.B2Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        sessions = []
        for enabled in (False, True):
            base = fixture.session(ticks=4)
            echo = EchoExpectations() if enabled else None
            session = b2.NativeHeartSession(base.components, max_ticks=4,
                                           sensor=base.sensor, echo=echo)
            session.start()
            first = session.step()
            if enabled:
                echo.expect(first.observation, expected_coordinates=(0,), ttl=3)
            for _ in range(3):
                session.step()
            sessions.append(session)
        def behavior(session):
            return (
                [(r.tick, r.observation.frames[-1].values, r.execution.status if r.execution else None,
                  r.advancement, r.diagnostic) for r in session.records],
                [(t.action_tick, t.observation_tick, t.before_sensory_window.frames[-1].values,
                  t.after_sensory_window.frames[-1].values)
                 for t in session.components.short_memory.snapshot()],
                session.components.world.hidden_position,
                len(session.components.world.applies),
                session.components.world.current_tick,
            )
        self.assertEqual(behavior(sessions[0]), behavior(sessions[1]))
        self.assertGreater(len(sessions[1].components.world.applies), 0)
        self.assertTrue(any(r.echo_matches for r in sessions[1].records))
        self.assertTrue(all(not r.echo_matches for r in sessions[0].records))

    def test_late_support_does_not_close_old_causal_transition(self):
        fixture = b2.B2Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        base = fixture.session(ticks=4)
        echo = EchoExpectations(continuation_threshold=.5)
        session = b2.NativeHeartSession(base.components, max_ticks=4, echo=echo)
        c = session.components
        session.sensor = lambda tick: c.world.snapshot() if tick in (0, 3) else None
        session.start()
        first = session.step()
        pending = c.context_manager.pending_causal_transition
        self.assertIsNotNone(pending)
        echo.expect(first.observation, expected_coordinates=(1,), ttl=4)
        for _ in range(3):
            session.step()
            self.assertEqual(session.heart.tick, c.world.current_tick)
        late = session.records[3]
        self.assertEqual([r.echo_matches[0].outcome for r in session.records[1:]],
                         ['no_data', 'no_data', 'support'])
        self.assertTrue(late.echo_matches[0].possible_continuation)
        self.assertFalse(late.echo_matches[0].identity_confirmed)
        self.assertIs(session.records[2].expired, pending)
        self.assertIsNone(late.recent)
        self.assertEqual(c.short_memory.snapshot(), ())
        self.assertIn(pending.execution_occurrence_id,
                      session.stop_report().unresolved_occurrences)
        if c.context_manager.pending_causal_transition is not None:
            self.assertNotEqual(c.context_manager.pending_causal_transition.execution_occurrence_id,
                                pending.execution_occurrence_id)

    def test_pause_resume_preserves_echo_time_and_expectation(self):
        fixture = b2.B2Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        base = fixture.session(empty=True, ticks=3)
        echo = EchoExpectations()
        session = b2.NativeHeartSession(base.components, max_ticks=3,
                                       sensor=base.sensor, echo=echo)
        session.start()
        first = session.step()
        entry = echo.expect(first.observation, expected_coordinates=(0,), ttl=1)
        session.pause()
        retained = echo.snapshot()
        for _ in range(2):
            self.assertIsNone(session.step())
            self.assertEqual(session.heart.tick, 1)
            self.assertEqual(session.components.world.current_tick, 1)
            self.assertEqual(echo.snapshot(), retained)
        self.assertIsNone(retained[0].last_match)
        session.resume()
        supported = session.step()
        self.assertEqual(supported.tick, 1)
        self.assertEqual(supported.echo_matches[0].outcome, 'support')
        self.assertEqual(echo.snapshot()[0].expires_at, entry.expires_at)
        self.assertEqual(session.heart.tick, session.components.world.current_tick)
        expired = session.step()
        self.assertEqual(expired.echo_matches[0].outcome, 'expired')
        self.assertEqual(echo.snapshot(), ())
        self.assertEqual(session.heart.tick, session.components.world.current_tick)

    def test_two_similar_observations_do_not_confirm_original_identity(self):
        results = [self.match(tick, window(tick, values))
                   for tick, values in [(1, (1., 0.)), (2, (.95, 0.))]]
        self.assertTrue(all(r.outcome == 'support' and r.possible_continuation for r in results))
        self.assertTrue(all(not r.identity_confirmed for r in results))
        self.assertNotEqual(results[0].observation_id, results[1].observation_id)
        self.assertTrue(all(r.expectation_id == self.entry.expectation_id for r in results))
        self.assertTrue(all(r.source_window_id == self.entry.source.window_id for r in results))
        self.assertEqual(len(self.echo.snapshot()), 1)
        self.assertEqual(self.echo.snapshot()[0].expires_at, self.entry.expires_at)

    def test_native_heart_integration_gap_and_expiry(self):
        fixture = b2.B2Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        session = fixture.session(empty=True, ticks=7)
        echo = EchoExpectations()
        session = b2.NativeHeartSession(session.components, max_ticks=7, echo=echo)
        world = session.components.world
        session.sensor = lambda tick: world.snapshot() if tick in (0, 3, 6) else None
        session.start()
        first = session.step()
        entry = echo.expect(first.observation, expected_coordinates=(0,), ttl=4)
        for _ in range(6):
            session.step()
        outcomes = [m.outcome for r in session.records for m in r.echo_matches]
        self.assertEqual(outcomes, ['no_data', 'no_data', 'support', 'no_data', 'expired'])
        self.assertTrue(session.records[3].echo_matches[0].possible_continuation)
        self.assertEqual(len(session.components.retriever.calls), 3)
        self.assertEqual(world.applies, [])
        self.assertEqual(entry.expires_at, 4)
        self.assertEqual(echo.snapshot(), ())


if __name__ == '__main__':
    unittest.main()
