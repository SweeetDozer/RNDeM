# Reflection Review

`ReflectionReview` is a runtime-only diagnostic review over the current
reflection chain.

Source chain:

- `DecisionCycleHistoryView`
- `ReflectionCandidateBuilder`
- `NeedMoreEvidenceSignal`

The review does not emit a cognitive marker, write permanent memory, modify
ExpSM or AKBSM, update value feedback memory, change scoring, change planning,
or feed back into `DecisionSelector`, `ActionProposer`, `ModeActionGuard`,
memory write gates, `FieldUpdater`, or neuromodulation.

## Influence Boundary

Current implementation is observational only. `ReflectionReview` and downstream
`PolicyPressure` do not affect action selection, memory gates, `FieldUpdater`,
or `NeuromodulationModule`. See
`docs/adr_policy_pressure_influence_boundary.md`.

## Review API

Each `ReflectionReview` contains:

- `review_id`
- `tick`
- `review_status`
- `severity`
- `confidence`
- `primary_issue`
- `summary`
- `source_trend_label`
- `need_more_evidence_active`
- `source_reflection_types`
- `recommended_future_operation`
- `apply_now`
- `evidence`
- `tags`

`apply_now` is always `False` in this pass. `recommended_future_operation` is
not executed.

## Status Rules

- `no_reflection_data`: no history snapshot or zero observed cycles
- `needs_more_evidence`: active `NeedMoreEvidenceSignal`
- `guard_policy_tension`: guard tension candidate without active need-more-evidence
- `weak_value_signal`: weak value influence candidate without active need-more-evidence
- `stable_recent_behavior`: history trend is `mostly_clean`
- `uncertain_recent_behavior`: history trend is `uncertain_recent_history`
- `mixed_reflection_state`: fallback for mixed or otherwise non-dominant reflection state

## Primary Issues

The controlled primary issue set is:

- `none`
- `no_decision_history`
- `insufficient_decision_confidence`
- `repeated_uncertain_selection`
- `guard_policy_tension`
- `weak_value_influence`
- `mixed_cycle_history`
- `stable_clean_selection`

Need-more-evidence reason dominates when its signal is active. Otherwise the
review chooses guard tension, weak value signal, stable clean selection,
uncertain recent selection, or mixed cycle history in that order.

## Confidence

Confidence is bounded to `[0.0, 1.0]`:

- active need-more-evidence signal confidence, if present
- otherwise max reflection candidate confidence
- otherwise `observed_count / window_size` from history
- otherwise `0.0`

## Evidence

Evidence is compact:

```text
history_observed_count
history_trend_label
reflection_candidate_count
reflection_types
need_more_evidence_active
need_more_evidence_reason
status_counts
flag_counts
```

No nested full history payloads are copied into the review.

## Runtime Debug

`CLCRuntime` builds the review after `NeedMoreEvidenceSignalBuilder.build(...)`
and before debug output.

Example:

```text
reflection review:
  status=needs_more_evidence severity=medium confidence=1.00 primary_issue=repeated_uncertain_selection
  summary=Recent decisions are often uncertain; more evidence should be collected before stronger future conclusions.
  recommended_future_operation=collect_more_evidence apply_now=false
```

No-data example:

```text
reflection review:
  status=no_reflection_data severity=info confidence=0.00
```

## Future Path

Possible future layers:

- `ReflectionReview -> PolicyPressure`
- `ReflectionReview -> NeedMoreEvidenceReview`
- `ReflectionReview -> later gates only after explicit architecture decision`
