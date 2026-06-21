# Policy Pressure

`PolicyPressure` is a runtime-only diagnostic snapshot derived from
`ReflectionReview`.

It is not a policy change, not a decision instruction, and not a memory write.
It does not emit a cognitive marker, write permanent memory, modify ExpSM or
AKBSM, update value feedback memory, change scoring, change planning, or feed
back into `DecisionSelector`, `ActionProposer`, `ModeActionGuard`, memory write
gates, `FieldUpdater`, or neuromodulation.

## Influence Boundary

Current implementation is observational only. `PolicyPressure` does not affect
action selection, memory gates, `FieldUpdater`, or `NeuromodulationModule`.
See `docs/adr_policy_pressure_influence_boundary.md`.

`PolicyPressureReview` is an Option B review-only extension. It may read
`PolicyPressure`, but it must not affect behavior.

## Source

The pressure builder reads only the current `ReflectionReview`. It stores the
latest pressure and a bounded in-memory recent list.

Bound:

- `MAX_RECENT_POLICY_PRESSURES = 50`

## Pressure API

Each `PolicyPressure` contains:

- `pressure_id`
- `tick`
- `active`
- `pressure_type`
- `severity`
- `confidence`
- `source_review_status`
- `source_primary_issue`
- `recommended_future_operation`
- `apply_now`
- `evidence`
- `tags`

`apply_now` is always `False` in this pass. `recommended_future_operation` is
not executed.

## Pressure Types

- `no_policy_pressure`: no usable review or no reflection data
- `evidence_pressure`: active need-more-evidence review
- `uncertainty_pressure`: uncertain recent behavior
- `guard_pressure`: guard policy tension
- `value_signal_pressure`: weak value signal coverage
- `mixed_policy_pressure`: mixed reflection state
- `stability_pressure`: stable recent behavior

## Activation Rules

- `no_reflection_data`: inactive `no_policy_pressure`, `info`
- `needs_more_evidence`: active `evidence_pressure`, review severity
- `uncertain_recent_behavior`: active `uncertainty_pressure`, `medium`
- `guard_policy_tension`: active `guard_pressure`, review severity
- `weak_value_signal`: active `value_signal_pressure`, `low`
- `mixed_reflection_state`: active `mixed_policy_pressure`, `low`
- `stable_recent_behavior`: inactive `stability_pressure`, `info`

## Confidence

Confidence is the source review confidence clamped to `[0.0, 1.0]`.

For missing review or no-data pressure, confidence is `0.0`. For stable
behavior, confidence is still copied from the review.

## Evidence

Evidence is compact:

```text
review_status
primary_issue
review_severity
review_confidence
need_more_evidence_active
source_trend_label
source_reflection_types
```

No nested full review/history payloads are copied into the pressure.

## Runtime Debug

`CLCRuntime` builds policy pressure after `ReflectionReviewBuilder.build(...)`
and before debug output.

Active example:

```text
policy pressure:
  active=true type=evidence_pressure severity=medium confidence=1.00
  source_review=needs_more_evidence primary_issue=repeated_uncertain_selection
  recommended_future_operation=collect_more_evidence apply_now=false
```

Stable example:

```text
policy pressure:
  active=false type=stability_pressure severity=info confidence=1.00
```

No-data example:

```text
policy pressure:
  active=false type=no_policy_pressure severity=info confidence=0.00
```

## Future Path

Possible future layers:

- `NeedMoreEvidenceReview`
- later gate or decision influence only after explicit architecture decision
