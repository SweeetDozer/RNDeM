# Real-input scenarios

## Purpose

Real-input scenarios exercise the current runtime pipeline from ordinary inputs
instead of pre-seeded decision-cycle summaries or synthetic policy-pressure
reviews. They are scenario/testing fixtures only: they do not change runtime
behavior, tick order, scoring, action proposal, memory mutation policy, or
retention semantics.

The focused verifier is:

```bash
python tools/verify_real_input_scenarios.py
```

The broader scenario verifier also includes them:

```bash
python tools/verify_scenario_fixtures.py
```

Several real-input fixtures also have compact phase regression snapshots in
`scenarios/regression_snapshots/`. Verify those baselines with:

```bash
python tools/verify_phase_regression_snapshots.py
```

## Difference from synthetic fixtures

Synthetic reflection and policy-review fixtures seed
`synthetic_decision_cycle_summaries` or, for one focused review case,
`synthetic_policy_pressure_review`. Those fixtures are useful for precise
coverage of reflection states that are hard to reach under current dominance
rules.

Real-input fixtures avoid those synthetic hooks. They call the existing scenario
input kinds, usually `audio` or `sensor`, and let `_run_tick()` naturally produce
decision audits, action-guard audits, decision-cycle summaries, reflection
candidates, need-more-evidence signals, policy pressure, and policy-pressure
reviews.

## Fixture list

- `scenarios/real_input_repeated_audio_signal.json`
  - Alternating ordinary audio intensity over six ticks.
  - Expects markers 33, 34, and 35, evidence pressure, marker 36 absence, and
    unchanged real Memory.

- `scenarios/real_input_conflicting_sensor_signal.json`
  - Alternates risky and quiet sensor readings.
  - Expects risk labels, decision/audit summaries, repeated uncertainty,
    weak-value-influence reflection, evidence pressure review, and unchanged
    real Memory.

- `scenarios/real_input_low_confidence_action_loop.json`
  - Runs a longer ambiguous audio loop.
  - Expects naturally accumulated uncertain decision-cycle summaries and
    evidence pressure without synthetic summaries.

- `scenarios/real_input_integrity_preservation_loop.json`
  - Repeats high-risk integrity sensor input.
  - Expects risk labels, ExpSM feedback, decision/audit summaries, and evidence
    pressure without writing ExpSM or AKBSM.

- `scenarios/real_input_value_target_repetition.json`
  - Runs a longer ordinary audio loop that reaches target satisfaction and value
    feedback review observations.
  - Expects markers 29, 30, and 31 while forbidding marker 32, ExpSM writes, and
    AKBSM writes.

- `scenarios/real_input_retention_with_observation_views.json`
  - Runs real audio input under a small context cap.
  - Expects retention pruning, side-list caps, decision-cycle summaries, runtime
    observation views, marker 36 absence, and unchanged real Memory.

## Expected observations

The real-input fixtures prefer partial, stable assertions:

- required marker presence, especially 33, 34, and 35
- marker 36 absence
- minimum event count rather than exact marker totals
- runtime-only reflection/pressure status when naturally produced
- retention pruning and side-list caps only in the retention fixture
- real `Memory/ExpSM` and `Memory/AKBSM` hashes unchanged

They intentionally avoid exact counts for most markers because the runtime can
produce additional observation-only events as upstream modules evolve.

## Known limitations

These fixtures describe the current safe-demo pipeline. They do not prove that
reflection or policy pressure influences behavior; those objects remain
runtime-only views. They also do not cover planning, chatbot behavior, LLM calls,
or new cognitive markers.
