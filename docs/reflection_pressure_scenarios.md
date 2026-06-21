# Reflection Pressure Scenarios

Reflection pressure fixtures cover the runtime-only diagnostic chain:

```text
DECISION_CYCLE_SUMMARY marker 35
DecisionCycleHistoryView
ReflectionCandidateBuilder
NeedMoreEvidenceSignal
ReflectionReview
PolicyPressure
PolicyPressureReview
```

They are scenario tests only. They do not write permanent memory, add markers,
change scoring, change planning, or connect pressure/review/signal output to
runtime behavior.

Scenarios verify diagnostic outputs only. They do not verify behavioral
influence because no influence is currently allowed. See
`docs/adr_policy_pressure_influence_boundary.md`.

`PolicyPressureReview` is an Option B review-only extension. It may read
`PolicyPressure`, but it must not affect behavior.

## Synthetic Marker 35

Fixtures may include test-only synthetic decision-cycle summaries:

```json
{
  "synthetic_decision_cycle_summaries": [
    {
      "tick": 0,
      "cycle_status": "uncertain_selection",
      "cycle_confidence": "medium",
      "flags": ["narrow_decision", "no_value_influence"],
      "selected": {"source": "expsm_activation"},
      "decision_summary": {"value_influence": "none_or_tiny"},
      "guard_summary": {"guard_effect": "no_blocked_candidates", "severity": "none"}
    }
  ]
}
```

The runner inserts these as marker 35 events into the temporary runtime
`ContextMemory` before fixture inputs run. Real memory is not touched. Unknown
synthetic status names do not register new pattern ids.

## Reflection Expectations

Fixtures can add optional expectations under `expect.reflection`:

```json
{
  "expect": {
    "reflection": {
      "history_trend_label": "uncertain_recent_history",
      "candidate_types": ["repeated_uncertain_selection"],
      "need_more_evidence_active": true,
      "need_more_evidence_reason": "repeated_uncertain_selection",
      "reflection_review_status": "needs_more_evidence",
      "reflection_review_primary_issue": "repeated_uncertain_selection",
      "policy_pressure_type": "evidence_pressure",
      "policy_pressure_active": true,
      "policy_pressure_recommended_future_operation": "collect_more_evidence",
      "policy_pressure_review_status": "evidence_pressure_review",
      "policy_pressure_review_primary_issue": "repeated_uncertain_selection",
      "policy_pressure_review_pressure_type": "evidence_pressure",
      "policy_pressure_review_active": true,
      "policy_pressure_review_recommended_future_operation": "collect_more_evidence"
    }
  }
}
```

All reflection expectation fields are optional. `candidate_types` is checked as a
required subset of runtime candidates. Policy pressure review expectations are
also optional and check diagnostic review output only.

For dedicated `PolicyPressureReview` fixtures, see
`docs/policy_pressure_review_scenarios.md`.

## Covered Fixtures

- `reflection_no_data`
- `reflection_stable_clean`
- `reflection_uncertain`
- `reflection_guard_pressure`
- `reflection_weak_value_signal`
- `reflection_mixed_history`

`reflection_mixed_history` documents the current implemented rules: a
`mixed_cycle_history` candidate activates `NeedMoreEvidenceSignal`, so the final
pressure is currently `evidence_pressure`.

## Verifier

Run the focused verifier:

```bash
python tools/verify_reflection_pressure_scenarios.py
```

The normal scenario verifier also honors optional reflection expectations:

```bash
python tools/verify_scenario_fixtures.py
```

Both verifiers run fixtures against a temporary copy of `Memory` and check real
memory immutability.
