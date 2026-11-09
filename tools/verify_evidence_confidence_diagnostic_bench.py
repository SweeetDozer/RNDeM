"""Bounded RND-026 math diagnostics; all writable test artifacts are temporary."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenarios import evidence_confidence_diagnostic_bench as b


def inventory():
    files = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.relative_to(ROOT).parts}
    dirs = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob('*')
                  if p.is_dir() and '.git' not in p.relative_to(ROOT).parts)
    return files, dirs


def replay(name, sequence):
    model = b.Model(name)
    for t, symbol in enumerate(sequence):
        model.update(t, int(symbol == 'H'))
    return model


class DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = inventory()

    @classmethod
    def tearDownClass(cls):
        if cls.before != inventory():
            raise AssertionError('checkout inventory changed during diagnostic verifier')

    def test_known_production_parity(self):
        self.assertEqual(b.parity_gate(), 'PASS')
        self.assertEqual(replay('M0', 'H').snapshot()['confidence'], .382)
        self.assertEqual(replay('M0', 'M').snapshot()['repeatability'], .425)

    def test_oracle_calls_real_helpers(self):
        with patch.object(b, '_updated_record', wraps=b._updated_record) as update:
            with patch.object(b.ExpSMActivationModule, 'activate_native',
                              autospec=True, side_effect=b.ExpSMActivationModule.activate_native) as activation:
                model = replay('M0', 'HM')
                self.assertEqual(update.call_count, 2)
                self.assertGreaterEqual(activation.call_count, 3)
                self.assertAlmostEqual(model.predict(), .71215)

    def test_caps(self):
        model = b.Model('M0')
        model.record = replace(model.record, operational=b.ExpSMOperationalMetadataV1(0, 0, 1., 1.))
        model.update(0, 1)
        self.assertEqual(model.record.operational.repeatability, .85)
        self.assertEqual(model.record.operational.confidence, .57)
        model.record = replace(model.record, operational=b.ExpSMOperationalMetadataV1(1000, 0, 1., 1.))
        model.h, model.m = 1000, 0
        model.update(1, 1)
        self.assertEqual(model.record.operational.repeatability, .9)
        self.assertLessEqual(model.record.operational.confidence, .75)
        self.assertLessEqual(model.predict(), 1.)

    def test_rounding_fixed_points(self):
        self.assertEqual(replay('M0', 'M' * 1000).record.operational.confidence, .002)
        self.assertEqual(replay('M0', 'H' * 1000).record.operational.confidence, .599)

    def test_equal_counts_order(self):
        hm, mh = replay('M0', 'HM'), replay('M0', 'MH')
        self.assertEqual((hm.h, hm.m), (mh.h, mh.m))
        self.assertNotEqual(hm.predict(), mh.predict())
        self.assertEqual(hm.record.operational.repeatability, mh.record.operational.repeatability)
        for name in ('M1', 'M2'):
            self.assertEqual(replay(name, 'HM').predict(), replay(name, 'MH').predict())
        self.assertNotEqual(replay('M3', 'HM').predict(), replay('M3', 'MH').predict())

    def test_repeatability_counts_misses(self):
        h, m = replay('M0', 'H' * 50), replay('M0', 'M' * 50)
        self.assertEqual(h.record.operational.repeatability, m.record.operational.repeatability)
        self.assertEqual(m.record.operational.repeatability, .894)

    def test_first_hit_switch_and_recovery(self):
        oracle = b.Oracle()
        models = [b.Model('M0', oracle), b.Model('M0', oracle)]
        self.assertEqual(oracle.choose(models), 0)
        models[0].update(0, 1)
        self.assertEqual(oracle.choose(models), 1)
        self.assertLess(replay('M0', 'H' * 10).predict(), .775)
        self.assertGreater(replay('M0', 'H' * 11).predict(), .775)

    def test_native_eligibility_and_top_three(self):
        oracle = b.Oracle()
        models = [b.Model('M0', oracle) for _ in range(4)]
        self.assertEqual(oracle.choose(models, (0., 0., 0., 0.)), None)
        self.assertEqual(len(oracle.activate(models)), 3)
        self.assertEqual(oracle.choose(models), 0)
        for model in models:
            model.record = replace(model.record, operational=b.ExpSMOperationalMetadataV1(0, 1000, 0., 0.))
        self.assertEqual(oracle.choose(models, (1/3,) * 4), None)

    def test_deterministic_ties_without_probability_threshold(self):
        models = [b.Model('M1'), b.Model('M1')]
        for model in models:
            for t in range(20):
                model.update(t, 0)
        self.assertLess(models[0].predict(), .35)
        self.assertEqual(b.choose(models, 'M1', b.Oracle()), 0)

    def test_native_and_diagnostic_baseline_agree_at_exact_context(self):
        generated = [b.outcomes('native-parity', 7, i, .9-i*.8, .9-i*.8, 100)
                     for i in range(2)]
        ps, table = tuple(x[0] for x in generated), tuple(x[1] for x in generated)
        for mode in ('full', 'partial'):
            self.assertEqual(b.run_pair(ps, table, 'M0', mode),
                             b.run_pair(ps, table, 'M0_native', mode))

    def test_beta_mean_std_support(self):
        model = replay('M2', 'HHM')
        self.assertEqual(model.predict(), 4/7)
        self.assertAlmostEqual(model.std() ** 2, 4*3/(7**2*8))
        self.assertLess(replay('M2', 'HM' * 100).std(), replay('M2', 'HM').std())
        self.assertEqual(replay('M1', 'HHM').predict(), 3/5)

    def test_ewma_fixed_prespecified_sensitivity(self):
        self.assertAlmostEqual(replay('M3', 'H').predict(), .525)
        self.assertAlmostEqual(replay('M3_alpha20', 'H').predict(), .6)

    def test_brier_ece_and_bin_boundaries(self):
        metrics = b.ForecastMetrics(True)
        for prediction, outcome in ((0., 0), (.1, 1), (.9, 0), (1., 1)):
            metrics.add(prediction, outcome)
        result = metrics.summary()
        self.assertAlmostEqual(result['brier'], .405)
        self.assertAlmostEqual(result['ece'], .45)
        self.assertEqual([result['bins'][str(i)]['count'] for i in range(10)],
                         [1, 1, 0, 0, 0, 0, 0, 0, 0, 2])
        self.assertIsNone(result['bins']['2']['hit_frequency'])

    def test_na_not_zero(self):
        metrics = b.ForecastMetrics(False)
        metrics.add(.775, 1)
        self.assertIsNone(metrics.summary()['brier'])
        self.assertIsNone(metrics.summary()['ece'])
        result = b.run_pair(((.5,)*3, (.5,)*3), ((1,)*3, (0,)*3), 'M1', 'partial')
        self.assertIsNone(result['windows']['all']['ranking_accuracy'])
        self.assertIsNone(result['adaptation_delay'])

    def test_prediction_before_event(self):
        result = b.run_stream((1.,), (1,), 'M1')
        self.assertEqual(result['windows']['all']['brier'], .25)
        self.assertEqual(result['initial']['score'], .5)
        self.assertEqual(result['final']['score'], 2/3)

    def test_no_hidden_outcome_access_before_selection(self):
        events = []
        class Guarded:
            def __len__(self):
                return 4
            def __getitem__(self, tick):
                self_outer.assertEqual(events[-1], ('choice', tick))
                events.append(('read', tick))
                return 1
        self_outer = self
        def selected(models, policy, oracle):
            tick = len([e for e in events if e[0] == 'choice'])
            events.append(('choice', tick))
            return 0
        with patch.object(b, 'choose', side_effect=selected):
            b.run_pair(((.9,)*4, (.1,)*4), (Guarded(), Guarded()), 'M1', 'partial')
        self.assertEqual(len(events), 8)

    def test_unselected_not_updated_or_read(self):
        class Forbidden:
            def __len__(self):
                return 10
            def __getitem__(self, tick):
                raise AssertionError('unselected outcome read')
        result = b.run_pair(((1.,)*10, (0.,)*10), ((1,)*10, Forbidden()), 'M1', 'partial')
        self.assertEqual(result['final_A']['hits'], 10)
        self.assertEqual(result['final_B']['hits'] + result['final_B']['misses'], 0)
        self.assertEqual(result['windows']['all']['starvation_B'], 10)

    def test_full_information_identical_conditions(self):
        a = b.outcomes('common', 3, 0, .7, .7, 20)
        c = b.outcomes('common', 3, 1, .6, .6, 20)
        for policy in b.POLICIES:
            result = b.run_pair((a[0], c[0]), (a[1], c[1]), policy, 'full')
            self.assertEqual(result['final_A']['hits'], sum(a[1]))
            self.assertEqual(result['final_B']['hits'], sum(c[1]))
            self.assertEqual(result['windows']['all']['forecast']['observations'], 40)

    def test_event_exactly_once_and_errors_atomic(self):
        model = b.Model('M1')
        model.update(0, 1)
        before = model.snapshot()
        for event, outcome in ((0, 1), (-1, 0), (1, 2), (1000, 1), (True, 1)):
            with self.assertRaises(ValueError):
                model.update(event, outcome)
            self.assertEqual(before, model.snapshot())

    def test_seeds_and_candidate_rng_are_reproducible(self):
        first = b.outcomes('stream', 1, 0, .5, .9)
        self.assertEqual(first, b.outcomes('stream', 1, 0, .5, .9))
        self.assertNotEqual(first[1], b.outcomes('stream', 1, 1, .5, .9)[1])
        self.assertNotEqual(first[1], b.outcomes('stream', 2, 0, .5, .9)[1])
        self.assertEqual(first[0][499], .5)
        self.assertEqual(first[0][500], .9)

    def test_byte_reproducible_smoke(self):
        first = json.dumps(b.experiment(8, (0,)), sort_keys=True, allow_nan=False)
        second = json.dumps(b.experiment(8, (0,)), sort_keys=True, allow_nan=False)
        self.assertEqual(first, second)

    def test_bounds(self):
        for horizon in (0, 1001, True, 1.5):
            with self.assertRaises(ValueError):
                b.budget(horizon)
        for seeds in ((), (0, 0), (32,), (True,)):
            with self.assertRaises(ValueError):
                b.budget(1, seeds)
        for value in (float('nan'), float('inf'), -.1, 1.1, True):
            with self.assertRaises(ValueError):
                b.probability(value)
        self.assertLessEqual(max(map(len, b.prescribed_sequences().values())), 1000)
        metrics = b.ForecastMetrics(True)
        for _ in range(1000):
            metrics.add(.5, 1)
        self.assertEqual(len(metrics.bins), 10)
        self.assertEqual(set(vars(metrics)), {'probabilistic', 'n', 'score_sum', 'square_error',
                                              'std_sum', 'std_n', 'bins'})

    def test_adaptation_and_censoring_definition(self):
        detector = b.Sustained()
        for offset in range(25):
            detector.observe(offset, offset >= 5)
        self.assertEqual(detector.delay, 5)
        ps = (.9,)*500 + (.1,)*30
        result = b.run_stream(ps, (1,)*530, 'M1')
        self.assertEqual(result['adaptation_censored'], 1)
        self.assertIsNone(result['adaptation_delay'])

    def test_choice_metrics(self):
        metrics = b.ChoiceMetrics()
        for selected in (0, 1, 1, 0):
            metrics.add(selected, (.9, .1))
        result = metrics.summary()
        self.assertEqual(result['ranking_accuracy'], .5)
        self.assertAlmostEqual(result['selection_regret'], .4)
        self.assertAlmostEqual(result['switch_frequency'], 2/3)
        self.assertEqual(result['starvation_A'], 2)
        self.assertEqual(result['starvation_B'], 1)

    def test_windows(self):
        self.assertEqual(b.window_names(0, 1000), ['all', 'initial200'])
        self.assertEqual(b.window_names(800, 1000), ['all', 'last200'])
        self.assertEqual(b.window_names(500, 1000), ['all'])

    def test_aggregate_na_and_dispersion(self):
        result = b.aggregate([dict(x=1., na=None), dict(x=3., na=None)])
        self.assertEqual(result['x']['mean'], 2.)
        self.assertEqual(result['x']['std'], 1.)
        self.assertIsNone(result['na']['mean'])
        self.assertEqual(result['na']['na_seeds'], 2)

    def test_output_confined_exclusive_and_deterministic(self):
        result = b.experiment(2, (0,))
        with tempfile.TemporaryDirectory(prefix='rnd026-verifier-') as temporary:
            a, c = Path(temporary)/'a', Path(temporary)/'b'
            b.write_results(a, result)
            b.write_results(c, result)
            self.assertEqual((a/'results.json').read_bytes(), (c/'results.json').read_bytes())
            with self.assertRaises(FileExistsError):
                b.write_results(a, result)
            link = Path(temporary)/'link'
            link.symlink_to(a, target_is_directory=True)
            with self.assertRaises(ValueError):
                b.write_results(link, result)
        for path in (ROOT/'forbidden-output', Path('/tmp')):
            with self.assertRaises(ValueError):
                b.write_results(path, result)

    def test_errors_and_sanitized_diagnostics(self):
        with self.assertRaises(ValueError):
            b.Model('unknown')
        with self.assertRaises(ValueError):
            b.run_pair((), (), 'M1', 'partial')
        with patch.object(b, 'experiment', side_effect=RuntimeError('private unbounded detail')):
            with patch('sys.stderr', new_callable=io.StringIO) as output:
                with self.assertRaises(SystemExit) as exit_info:
                    b.main(['--preset', 'smoke'])
                self.assertEqual(exit_info.exception.code, 2)
                self.assertEqual(output.getvalue(), 'diagnostic bench stopped: RuntimeError\n')

    def test_parity_failure_stops_before_benchmark(self):
        with patch.object(b, 'PARITY', {'': .1}):
            with patch.object(b, 'outcomes', side_effect=AssertionError('must not start')):
                with self.assertRaisesRegex(RuntimeError, 'STOP'):
                    b.experiment(1, (0,))


if __name__ == '__main__':
    unittest.main(verbosity=2)
