# Policy Pressure Review

`PolicyPressureReview` is a runtime-only Option B review over the latest
`PolicyPressure`.

It is not a policy change, not a decision instruction, not planning, and not a
memory write. It does not emit a cognitive marker, write permanent memory,
modify ExpSM or AKBSM, update value feedback memory, change scoring, change
planning, or feed back into `DecisionSelector`, `ActionProposer`,
`ModeActionGuard`, memory write gates, `FieldUpdater`, or
`NeuromodulationModule`.

## Influence Boundary

Current implementation is review-only. `PolicyPressureReview` may read
`PolicyPressure`, but it must not affect behavior. See
`docs/adr_policy_pressure_influence_boundary.md`.

## Source

The review builder reads only the current `PolicyPressure`. It stores the latest
review and a bounded in-memory recent list.

Bound:

- `MAX_RECENT_POLICY_PRESSURE_REVIEWS = 50`

## Review API

Each `PolicyPressureReview` contains:

- `review_id`
- `tick`
- `review_status`
- `severity`
- `confidence`
- `pressure_type`
- `pressure_active`
- `primary_issue`
- `summary`
- `recommended_future_operation`
- `apply_now`
- `evidence`
- `tags`

`apply_now` is always `False`. `recommended_future_operation` is not executed.

## Review Statuses

- `no_pressure_data`: no pressure object is available yet
- `no_active_pressure`: pressure exists but reports no active pressure
- `evidence_pressure_review`: evidence pressure is active
- `uncertainty_pressure_review`: uncertainty pressure is active
- `guard_pressure_review`: guard pressure is active
- `value_signal_pressure_review`: value signal pressure is active
- `mixed_pressure_review`: mixed pressure is active or the pressure type is not recognized
- `stability_pressure_review`: recent behavior appears stable

## Primary Issue Rules

- no pressure data: `no_pressure_data`
- no active pressure: `none`
- stability pressure: `stable_recent_behavior`
- evidence pressure: copied from `PolicyPressure.source_primary_issue`
- uncertainty pressure: copied from `PolicyPressure.source_primary_issue`
- guard pressure: `guard_policy_tension`
- value signal pressure: `weak_value_influence`
- mixed pressure: `mixed_cycle_history`

## Confidence

Confidence is copied from `PolicyPressure.confidence` and clamped to
`[0.0, 1.0]`. Missing pressure uses `0.0`.

## Evidence

Evidence is compact:

```text
pressure_active
pressure_type
pressure_severity
pressure_confidence
source_review_status
source_primary_issue
pressure_recommended_future_operation
```

No nested full pressure or review payloads are copied into the review.

## Runtime Debug

`CLCRuntime` builds the review after `PolicyPressureBuilder.build(...)` and
before debug output.

Example:

```text
policy pressure review:
  status=evidence_pressure_review severity=medium confidence=1.00 pressure=evidence_pressure active=true
  summary=Evidence pressure is active; recent decision history suggests more evidence should be collected.
  recommended_future_operation=collect_more_evidence apply_now=false
```

Stable example:

```text
policy pressure review:
  status=stability_pressure_review severity=info confidence=1.00 pressure=stability_pressure active=false
```

No-data example:

```text
policy pressure review:
  status=no_pressure_data severity=info confidence=0.00 pressure=no_policy_pressure active=false
```

## Future Path

Any later connection to memory gates, decision gates, scoring, planning,
`FieldUpdater`, or `NeuromodulationModule` requires a separate architecture
decision and verifier coverage.

## Scenario Coverage

Dedicated fixtures live under `scenarios/policy_review_*.json` and are verified
by:

```bash
python tools/verify_policy_pressure_review_scenarios.py
```

Some fixtures use a test-only synthetic pressure input to cover review statuses
that current full-chain dominance does not naturally produce. See
`docs/policy_pressure_review_scenarios.md`.
