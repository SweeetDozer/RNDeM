"""RND-026 diagnostic math only: no stores, writers, world or runtime hooks.

Predictions are prequential. Full-information is an information upper control;
partial-feedback reveals only the selected candidate's outcome after selection.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import tempfile

from clc.action.decision_selector import DecisionSelector
from clc.core.ids import IdGenerator
from clc.experience.expsm_representation import ExpSMOperationalMetadataV1
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.nfp_native_feedback import NFPFeedbackEvaluationStatus
from clc.expsm.nfp_native_feedback_apply import _updated_record
from clc.expsm.nfp_operational_retrieval import NFPExpSMRetrievalCandidate

SEEDS = tuple(range(32))
MAX_HORIZON = 1000
MODELS = ('M0', 'M1', 'M2', 'M3', 'M3_alpha20')
POLICIES = MODELS + ('M0_native',)
STATIONARY = (0., .1, .5, .9, 1.)
STREAM_CASES = tuple((f'p={p:g}', p, p) for p in STATIONARY) + (
    ('change=.9-.1', .9, .1), ('change=.1-.9', .1, .9))
PAIR_CASES = (
    ('pair=.9-.1', (.9, .1), (.9, .1)),
    ('pair=.7-.6', (.7, .6), (.7, .6)),
    ('pair=.5-.5', (.5, .5), (.5, .5)),
    ('pair=1-0', (1., 0.), (1., 0.)),
    ('pair=change', (.9, .1), (.1, .9)),
)
WINDOW = 200
SUSTAIN = 20
TOLERANCE = .1
NA = None  # JSON null means N/A, never a substituted zero.


def budget(horizon: int, seeds=SEEDS):
    if type(horizon) is not int or not 1 <= horizon <= MAX_HORIZON:
        raise ValueError('horizon must be an integer in 1..1000')
    seeds = tuple(seeds)
    if not seeds or len(seeds) > 32 or len(set(seeds)) != len(seeds):
        raise ValueError('one to 32 unique seeds required')
    if any(type(s) is not int or s not in SEEDS for s in seeds):
        raise ValueError('seeds must belong to 0..31')
    return seeds


def probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('finite probability required')
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('finite probability in [0,1] required')
    return float(value)


@dataclass(frozen=True)
class FormulaRecord:
    """Transient duck-typed envelope for the production pure update helper."""
    operational: ExpSMOperationalMetadataV1
    updated_at_world: str = 'rnd026-diagnostic-only'


class Oracle:
    def __init__(self):
        # activate_native needs only id_gen; do not construct a registry or path.
        self.activation = object.__new__(ExpSMActivationModule)
        self.activation.id_gen = IdGenerator()
        self.selector = DecisionSelector(IdGenerator(), decision_threshold=.35)

    def activate(self, models, similarities=None):
        similarities = (1.,) * len(models) if similarities is None else tuple(similarities)
        if len(similarities) != len(models):
            raise ValueError('one similarity per candidate required')
        candidates = []
        for i, (model, similarity) in enumerate(zip(models, similarities)):
            similarity = probability(similarity)
            # The native fixtures retrieve at >=1/3, before activation/top-3.
            if similarity < 1 / 3:
                continue
            o = model.record.operational
            candidates.append(NFPExpSMRetrievalCandidate(
                f'diagnostic:{i}', str(i), similarity, None, None,
                o.hits, o.misses, o.confidence, o.repeatability))
        return self.activation.activate_native(candidates)

    def score(self, model):
        return self.activate((model,))[0].activation

    def choose(self, models, similarities=None):
        selected = self.selector.select_native(self.activate(models, similarities))
        return None if selected is None else int(selected.source_experience_id)


class Model:
    def __init__(self, name, oracle=None):
        if name not in POLICIES:
            raise ValueError('unknown diagnostic model')
        self.name = name
        self.oracle = oracle if oracle is not None else Oracle()
        self.record = FormulaRecord(ExpSMOperationalMetadataV1())
        self.h = self.m = 0
        self.z = .5
        self.last_event = -1
        self.alpha = .2 if name == 'M3_alpha20' else .05
        self._score = self.oracle.score(self) if name in ('M0', 'M0_native') else .5

    def predict(self):
        return self._score

    def update(self, event: int, outcome: int):
        if type(event) is not int or event <= self.last_event:
            raise ValueError('events must be strictly increasing per candidate')
        if type(outcome) is not int or outcome not in (0, 1):
            raise ValueError('outcome must be integer 0 or 1')
        if event >= MAX_HORIZON:
            raise ValueError('event outside diagnostic horizon')
        if self.name in ('M0', 'M0_native'):
            classification = NFPFeedbackEvaluationStatus.HIT if outcome else NFPFeedbackEvaluationStatus.MISS
            self.record = _updated_record(self.record, classification, 'rnd026-diagnostic-only')
        self.h += outcome
        self.m += 1 - outcome
        self.last_event = event
        if self.name in ('M0', 'M0_native'):
            self._score = self.oracle.score(self)
        elif self.name == 'M1':
            self._score = (self.h + 1) / (self.h + self.m + 2)
        elif self.name == 'M2':
            self._score = (self.h + 2) / (self.h + self.m + 4)
        else:
            self.z = (1 - self.alpha) * self.z + self.alpha * outcome
            self._score = self.z

    def snapshot(self):
        n = self.h + self.m
        result = dict(hits=self.h, misses=self.m, score=self.predict(),
                      delta_score=self.predict() - (.775 if self.name in ('M0', 'M0_native') else .5))
        if self.name in ('M0', 'M0_native'):
            o = self.record.operational
            result.update(confidence=o.confidence, repeatability=o.repeatability,
                          viability=(self.h + 1) / (n + 2),
                          delta_confidence=o.confidence - .5,
                          delta_repeatability=o.repeatability - .5,
                          delta_viability=(self.h + 1) / (n + 2) - .5)
        result.update(posterior_std=self.std(), credible_interval_95=NA)
        return result

    def std(self):
        if self.name != 'M2':
            return NA
        a, b = self.h + 2, self.m + 2
        return math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))


def prescribed_sequences():
    result = {s: s for s in ('H', 'M', 'HH', 'MM', 'HM', 'MH', 'HHHMM', 'MMHHH')}
    for n in (5, 10, 50, 100, 1000):
        for symbol in 'HM':
            result[f'{symbol}x{n}'] = symbol * n
    for n in (25, 500):
        for pair in ('HM', 'MH'):
            result[f'({pair})x{n}'] = pair * n
    result.update(H90M10='H' * 90 + 'M' * 10, M10H90='M' * 10 + 'H' * 90,
                  H10M90='H' * 10 + 'M' * 90, M90H10='M' * 90 + 'H' * 10,
                  H9M='H' * 9 + 'M', H9Mx10=('H' * 9 + 'M') * 10)
    return result


PARITY = {'': .775, 'H': .7568166666666667, 'M': .7220833333333333,
          'HH': .73935, 'HM': .71215, 'MH': .71115,
          'H' * 10: .7680166666666668, 'H' * 50: .8903769230769232,
          'M' * 50: .6864230769230769}


def parity_gate():
    for sequence, expected in PARITY.items():
        model = Model('M0')
        for t, symbol in enumerate(sequence):
            model.update(t, int(symbol == 'H'))
        if not math.isclose(model.predict(), expected, rel_tol=0, abs_tol=1e-12):
            raise RuntimeError('STOP: production parity differs from RND-026/A')
    return 'PASS'


def prescribed():
    result = {}
    checkpoints = {1, 2, 3, 4, 5, 7, 8, 10, 11, 20, 50, 100, 500, 1000}
    for label, sequence in prescribed_sequences().items():
        models = [Model(name) for name in MODELS]
        rows = {'0': {m.name: m.snapshot() for m in models}}
        for t, symbol in enumerate(sequence):
            for model in models:
                model.update(t, int(symbol == 'H'))
            if t + 1 in checkpoints or t + 1 == len(sequence):
                rows[str(t + 1)] = {m.name: m.snapshot() for m in models}
        result[label] = rows
    return result


def outcomes(label, seed, candidate, before, after, horizon=MAX_HORIZON):
    budget(horizon, (seed,))
    before, after = probability(before), probability(after)
    identity = f'rnd026-v1:{label}:{seed}:{candidate}'.encode('ascii')
    rng = random.Random(int.from_bytes(hashlib.sha256(identity).digest(), 'big'))
    ps = tuple(before if t < 500 else after for t in range(horizon))
    return ps, tuple(int(rng.random() < p) for p in ps)


class ForecastMetrics:
    def __init__(self, probabilistic):
        self.probabilistic = probabilistic
        self.n = 0
        self.score_sum = self.square_error = self.std_sum = 0.
        self.std_n = 0
        self.bins = [[0, 0., 0.] for _ in range(10)]

    def add(self, prediction, outcome, std=NA):
        prediction = probability(prediction)
        if type(outcome) is not int or outcome not in (0, 1):
            raise ValueError('invalid metric outcome')
        self.n += 1
        self.score_sum += prediction
        if self.probabilistic:
            self.square_error += (prediction - outcome) ** 2
            row = self.bins[min(9, int(prediction * 10))]
            row[0] += 1
            row[1] += prediction
            row[2] += outcome
        if std is not None:
            self.std_sum += std
            self.std_n += 1

    def summary(self):
        bins = {str(i): dict(count=n, mean_prediction=s / n if n else NA,
                            hit_frequency=y / n if n else NA)
                for i, (n, s, y) in enumerate(self.bins)} if self.probabilistic else NA
        return dict(observations=self.n, mean_score=self.score_sum / self.n if self.n else NA,
                    brier=self.square_error / self.n if self.probabilistic and self.n else NA,
                    ece=sum(abs(s - y) for n, s, y in self.bins) / self.n
                    if self.probabilistic and self.n else NA,
                    bins=bins, posterior_std_mean=self.std_sum / self.std_n if self.std_n else NA)


class Sustained:
    """First beginning of a SUSTAIN-long valid run, relative to change point."""
    def __init__(self):
        self.run = 0
        self.delay = None

    def observe(self, offset, valid):
        if self.delay is not None:
            return
        self.run = self.run + 1 if valid else 0
        if self.run == SUSTAIN:
            self.delay = offset - SUSTAIN + 1


def window_names(t, horizon):
    result = ['all']
    if t < WINDOW:
        result.append('initial200')
    if t >= max(0, horizon - WINDOW):
        result.append('last200')
    return result


def run_stream(ps, ys, name):
    horizon = len(ys)
    budget(horizon)
    if len(ps) != horizon:
        raise ValueError('latent/outcome lengths differ')
    model = Model(name)
    initial = model.snapshot()
    probabilistic = name not in ('M0', 'M0_native')
    metrics = {w: ForecastMetrics(probabilistic) for w in ('all', 'initial200', 'last200')}
    adaptation = Sustained()
    changed = horizon > 500 and ps[499] != ps[500]
    for t in range(horizon):
        prediction, std = model.predict(), model.std()
        # The decision/prediction boundary precedes access to this event.
        y = ys[t]
        for w in window_names(t, horizon):
            metrics[w].add(prediction, y, std)
        if changed and probabilistic and t >= 500:
            adaptation.observe(t - 500, abs(prediction - ps[t]) <= TOLERANCE)
        model.update(t, y)
    return dict(windows={w: m.summary() for w, m in metrics.items()}, initial=initial,
                final=model.snapshot(), adaptation_delay=adaptation.delay if changed and probabilistic else NA,
                adaptation_censored=int(adaptation.delay is None) if changed and probabilistic else NA,
                credible_interval_coverage=NA)


class ChoiceMetrics:
    def __init__(self):
        self.n = self.rank_n = self.correct = self.switches = self.edges = 0
        self.regret = 0.
        self.previous = None
        self.have_previous = False
        self.gaps = [0, 0]
        self.max_gaps = [0, 0]
        self.choices = [0, 0]
        self.none = 0

    def add(self, selected, ps, eligible=(True, True)):
        self.n += 1
        if ps[0] != ps[1]:
            self.rank_n += 1
            self.correct += int(selected is not None and ps[selected] == max(ps))
        # None is counted as zero obtained reliability, explicitly diagnostic.
        self.regret += max(ps) - (ps[selected] if selected is not None else 0.)
        if self.have_previous:
            self.edges += 1
            self.switches += int(selected != self.previous)
        self.have_previous, self.previous = True, selected
        if selected is None:
            self.none += 1
        else:
            self.choices[selected] += 1
        for i in range(2):
            self.gaps[i] = self.gaps[i] + 1 if eligible[i] and selected != i else 0
            self.max_gaps[i] = max(self.max_gaps[i], self.gaps[i])

    def summary(self):
        return dict(steps=self.n, ranking_accuracy=self.correct / self.rank_n if self.rank_n else NA,
                    ranking_comparisons=self.rank_n,
                    switch_frequency=self.switches / self.edges if self.edges else NA,
                    switches=self.switches, selection_regret=self.regret / self.n if self.n else NA,
                    starvation_A=self.max_gaps[0], starvation_B=self.max_gaps[1],
                    choices_A=self.choices[0], choices_B=self.choices[1], no_selection=self.none)


def choose(models, policy, oracle):
    if policy == 'M0_native':
        return oracle.choose(models)
    return max(range(2), key=lambda i: models[i].predict())  # A first on ties.


def run_pair(probabilities, table, policy, mode):
    if mode not in ('full', 'partial') or policy not in POLICIES:
        raise ValueError('unknown competition configuration')
    if len(table) != 2 or len(probabilities) != 2:
        raise ValueError('two candidate series required')
    horizon = len(table[0])
    budget(horizon)
    if any(len(a) != horizon for a in (*table, *probabilities)):
        raise ValueError('two equal bounded candidate series required')
    oracle = Oracle()
    models = [Model(policy, oracle) for _ in range(2)]
    metrics = {w: ChoiceMetrics() for w in ('all', 'initial200', 'last200')}
    forecasts = {w: ForecastMetrics(policy not in ('M0', 'M0_native'))
                 for w in ('all', 'initial200', 'last200')}
    adaptation = Sustained()
    changed = horizon > 500 and any(p[499] != p[500] for p in probabilities)
    for t in range(horizon):
        # No probability or outcome table is passed to the selection algorithm.
        selected = choose(models, policy, oracle)
        predictions = tuple((model.predict(), model.std()) for model in models)
        ps = tuple(p[t] for p in probabilities)
        for w in window_names(t, horizon):
            metrics[w].add(selected, ps)
        if changed and t >= 500:
            adaptation.observe(t - 500, selected is not None and ps[selected] == max(ps))
        for i in range(2):
            if mode == 'full' or selected == i:
                outcome = table[i][t]
                for w in window_names(t, horizon):
                    forecasts[w].add(predictions[i][0], outcome, predictions[i][1])
                models[i].update(t, outcome)
    return dict(windows={w: dict(**m.summary(), forecast=forecasts[w].summary())
                         for w, m in metrics.items()},
                final_A=models[0].snapshot(), final_B=models[1].snapshot(),
                adaptation_delay=adaptation.delay if changed else NA,
                adaptation_censored=int(adaptation.delay is None) if changed else NA)


def aggregate(rows):
    """Per-seed statistics, not a pooled ECE; N/A excluded and counted."""
    if isinstance(rows[0], dict):
        return {key: aggregate([row[key] for row in rows]) for key in rows[0]}
    values = [value for value in rows if value is not None]
    if values and not all(isinstance(value, (int, float)) for value in values):
        raise ValueError('only bounded numeric summaries can be aggregated')
    return dict(mean=statistics.fmean(values) if values else NA,
                std=statistics.pstdev(values) if values else NA,
                minimum=min(values) if values else NA, maximum=max(values) if values else NA,
                valid_seeds=len(values), na_seeds=len(rows) - len(values))


def experiment(horizon=MAX_HORIZON, seeds=SEEDS):
    seeds = budget(horizon, seeds)
    parity = parity_gate()  # STOP before any benchmark if this fails.
    streams, pairs = {}, {}
    for label, before, after in STREAM_CASES:
        rows = {name: [] for name in MODELS}
        for seed in seeds:
            ps, ys = outcomes(label, seed, 0, before, after, horizon)
            for name in MODELS:
                rows[name].append(dict(seed=seed, metrics=run_stream(ps, ys, name)))
        streams[label] = {name: dict(per_seed=data, aggregate=aggregate([r['metrics'] for r in data]))
                          for name, data in rows.items()}
    for label, before, after in PAIR_CASES:
        rows = {f'{mode}/{policy}': [] for mode in ('full', 'partial') for policy in POLICIES}
        for seed in seeds:
            generated = [outcomes(label, seed, i, before[i], after[i], horizon) for i in range(2)]
            ps, table = tuple(g[0] for g in generated), tuple(g[1] for g in generated)
            for mode in ('full', 'partial'):
                for policy in POLICIES:
                    rows[f'{mode}/{policy}'].append(dict(seed=seed, metrics=run_pair(ps, table, policy, mode)))
        pairs[label] = {key: dict(per_seed=data, aggregate=aggregate([r['metrics'] for r in data]))
                        for key, data in rows.items()}
    return dict(configuration=dict(version=1, seeds=list(seeds), horizon=horizon, change_point=500,
                                   initial_window=WINDOW, final_window=WINDOW, sustain=SUSTAIN,
                                   probability_tolerance=TOLERANCE, ewma_alphas=[.05, .2],
                                   intervals='N/A: no installed numerical interval library; no normal approximation',
                                   outcome_rng='SHA256(rnd026-v1:series:seed:candidate), random.Random',
                                   exact_context_similarity=1., native_retrieval_threshold=1/3,
                                   native_selector_threshold=.35),
                production_parity=parity, prescribed=prescribed(), streams=streams, competition=pairs)


def compact(result):
    rows = []
    for case, data in result['competition'].items():
        for key, run in data.items():
            a = run['aggregate']
            w = a['windows']['last200']
            rows.append(dict(case=case, policy=key, ranking=w['ranking_accuracy']['mean'],
                             regret=w['selection_regret']['mean'],
                             switches=a['windows']['all']['switches']['mean'],
                             starvation_A=a['windows']['all']['starvation_A']['mean'],
                             starvation_B=a['windows']['all']['starvation_B']['mean'],
                             adaptation=a['adaptation_delay']['mean'],
                             censored=a['adaptation_censored']['mean']))
    return dict(production_parity=result['production_parity'], configuration=result['configuration'],
                competition=rows)


def write_results(root, result):
    root = Path(root)
    resolved = root.resolve()
    temporary = Path(tempfile.gettempdir()).resolve()
    checkout = Path(__file__).resolve().parents[1]
    if (root.is_symlink() or resolved == temporary or not resolved.is_relative_to(temporary)
            or resolved.is_relative_to(checkout)):
        raise ValueError('new dedicated directory below /tmp required')
    # Exclusive creation: never overwrite or follow existing result directories.
    resolved.mkdir(exist_ok=False)
    payload = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n'
    (resolved / 'results.json').write_text(payload, encoding='utf-8')
    (resolved / 'summary.json').write_text(json.dumps(compact(result), sort_keys=True, indent=2,
                                                    allow_nan=False) + '\n', encoding='utf-8')
    return resolved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--output-dir')
    args = parser.parse_args(argv)
    try:
        result = experiment() if args.preset == 'full' else experiment(32, (0,))
        if args.output_dir:
            write_results(args.output_dir, result)
        print(json.dumps(compact(result), sort_keys=True, allow_nan=False))
    except (ValueError, RuntimeError, OSError) as exc:
        # Never retain exception objects or arbitrary caller diagnostics.
        parser.exit(2, f'diagnostic bench stopped: {type(exc).__name__}\n')


if __name__ == '__main__':
    main()
