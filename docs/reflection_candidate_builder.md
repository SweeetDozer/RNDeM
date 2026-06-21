# Reflection Candidate Builder

`ReflectionCandidateBuilder` is a runtime-only diagnostic layer over
`DecisionCycleHistoryView`.

It does not emit a cognitive marker, write permanent memory, modify ExpSM or
AKBSM, update value feedback memory, change scoring, change planning, or feed
back into `DecisionSelector`, `ActionProposer`, `ModeActionGuard`,
`FieldUpdater`, or neuromodulation.

## Source

The builder reads a `DecisionCycleHistorySnapshot`, which aggregates recent
marker 35 `DECISION_CYCLE_SUMMARY` payloads. The builder itself stores only a
bounded in-memory list of recent reflection candidates.

Bounds:

- `MAX_REFLECTION_CANDIDATES_PER_TICK = 3`
- `MAX_RECENT_REFLECTION_CANDIDATES = 50`

## Candidate API

Each `ReflectionCandidate` contains:

- `reflection_candidate_id`
- `tick`
- `reflection_type`
- `severity`
- `confidence`
- `source`
- `source_trend_label`
- `evidence`
- `recommended_future_operation`
- `apply_now`
- `tags`

`apply_now` is always `False` in this pass. `recommended_future_operation` is a
string for later layers only.

## Candidate Types

The controlled candidate set is:

- `no_decision_history`
- `insufficient_decision_confidence`
- `repeated_uncertain_selection`
- `guard_policy_tension`
- `weak_value_influence`
- `stable_clean_selection`
- `mixed_cycle_history`

## Severity Rules

- `no_decision_history`: `info`
- `insufficient_decision_confidence`: `low`
- `repeated_uncertain_selection`: `medium`
- `guard_policy_tension`: `medium`, or `high` when risky/constrained cycles are present
- `weak_value_influence`: `low`
- `stable_clean_selection`: `info`
- `mixed_cycle_history`: `low`

When the history trend is `value_influenced_recent_history`, the builder does
not emit `weak_value_influence`.

## Confidence

Confidence is bounded:

```text
min(1.0, observed_count / window_size)
```

Medium and high severities receive a small diagnostic adjustment. The value is
still capped at `1.0`.

## Evidence

Candidate evidence is compact and copied from the snapshot:

```text
observed_count
window_size
trend_label
status_counts
confidence_counts
flag_counts
selected_source_counts
value_influenced_count
guard_constrained_count
uncertain_count
risky_or_constrained_count
clean_count
```

## Runtime Debug

`CLCRuntime` refreshes `DecisionCycleHistoryView` after marker 35 summaries have
been committed, then builds reflection candidates before debug output.

Debug output is compact:

```text
reflection candidates:
  reflection_candidate_001 type=repeated_uncertain_selection severity=medium confidence=1.00
    trend=uncertain_recent_history observed=20
    recommended_future_operation=inspect_candidate_discrimination apply_now=false
```

## Future Path

This layer prepares later runtime-only concepts such as `NeedMoreEvidence`,
`PolicyPressure`, or `ReflectionReview`. This pass intentionally stops at
diagnostic candidate construction and debug visibility.
