# Policy Pressure Review Scenarios

Policy pressure review fixtures cover the runtime-only diagnostic/review chain:

```text
DECISION_CYCLE_SUMMARY marker 35
DecisionCycleHistoryView
ReflectionCandidateBuilder
NeedMoreEvidenceSignal
ReflectionReview
PolicyPressure
PolicyPressureReview
```

They verify diagnostic outputs only. `PolicyPressureReview` remains review-only
and must not affect scoring, planning, memory gates, `FieldUpdater`, or
`NeuromodulationModule`.

## Covered States

- `policy_review_no_pressure_data`: direct test-only no-pressure input,
  `no_pressure_data`
- `policy_review_no_active_pressure`: full runtime chain with no history,
  `no_active_pressure`
- `policy_review_stability`: full runtime chain, `stability_pressure_review`
- `policy_review_evidence_pressure`: full runtime chain,
  `evidence_pressure_review`
- `policy_review_guard_pressure`: full runtime chain, current-rule
  `evidence_pressure_review`
- `policy_review_value_signal_pressure`: full runtime chain,
  `value_signal_pressure_review`
- `policy_review_uncertainty_pressure`: direct test-only synthetic pressure,
  `uncertainty_pressure_review`
- `policy_review_mixed_pressure`: direct test-only synthetic pressure,
  `mixed_pressure_review`

## Expectation Fields

Fixtures use `expect.reflection` fields:

- `policy_pressure_type`
- `policy_pressure_active`
- `policy_pressure_review_status`
- `policy_pressure_review_primary_issue`
- `policy_pressure_review_pressure_type`
- `policy_pressure_review_active`
- `policy_pressure_review_recommended_future_operation`

The standard reflection fields can also be used when a fixture runs the full
upstream chain.

## Synthetic Inputs

Full-chain fixtures use existing synthetic marker 35 decision-cycle summaries.
They are inserted into temporary runtime `ContextMemory` only.

Some review statuses cannot be produced naturally by the current full chain
because upstream rules dominate. For those cases, fixtures use the test-only
`synthetic_policy_pressure_review` input kind. It builds a runtime-only
`PolicyPressureReview` from a synthetic `PolicyPressure` or from no pressure at
all. It does not write `ContextMemory` or permanent memory.

## Dominance Nuance

Guard-constrained and mixed histories can activate `NeedMoreEvidenceSignal`.
When that happens, `ReflectionReview` becomes `needs_more_evidence`,
`PolicyPressure` becomes `evidence_pressure`, and `PolicyPressureReview` becomes
`evidence_pressure_review`. The pure `guard_pressure_review` and
`mixed_pressure_review` rules remain directly covered by
`tools/verify_policy_pressure_review.py`; the scenario fixtures document current
full-chain dominance instead of forcing the runtime to lie.

## Verifier

Run:

```bash
python tools/verify_policy_pressure_review_scenarios.py
```

The normal scenario verifier also honors these optional expectations:

```bash
python tools/verify_scenario_fixtures.py
```

Both verifiers run fixtures against a temporary copy of `Memory` and check real
memory immutability.
