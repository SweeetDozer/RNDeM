# Decision Cycle History View

`DecisionCycleHistoryView` is a runtime-only diagnostic view over recent
marker 35 `DECISION_CYCLE_SUMMARY` payloads.

It does not write permanent memory, emit a new marker, change scoring, change
planning, or feed back into `DecisionSelector`, `ActionProposer`,
`ModeActionGuard`, `FieldUpdater`, or neuromodulation.

## Source

The view reads recent entries from:

```text
ContextMemory.get_recent_decision_cycle_summaries(window_size)
```

The default `window_size` is `20`. If retention or side-list retention prunes
older marker 35 payloads, the view aggregates the summaries that remain.

## Snapshot

`DecisionCycleHistorySnapshot` includes:

- `status_counts`
- `confidence_counts`
- `flag_counts`
- `selected_source_counts`
- `value_influenced_count`
- `guard_constrained_count`
- `uncertain_count`
- `risky_or_constrained_count`
- `clean_count`
- `dominant_status`
- `dominant_confidence`
- `trend_label`
- `warnings`

## Trends

Trend labels are diagnostic only:

- `no_data`: no recent summaries
- `mostly_clean`: at least 60% clean selections
- `guard_constrained_recent_history`: at least 30% guard-constrained cycles
- `uncertain_recent_history`: at least 30% uncertain cycles
- `value_influenced_recent_history`: at least 30% value-influenced cycles
- `mixed_recent_history`: no single diagnostic trend dominates

## Runtime Debug

`CLCRuntime` refreshes the view after marker 35 summaries have been committed
and before debug output. The debug block is compact:

```text
decision cycle history:
  window=20 observed=7 trend=mostly_clean
  statuses={clean_selection: 5, uncertain_selection: 2}
  confidence={high: 4, medium: 3}
  flags={narrow_decision: 2, no_value_influence: 6}
  selected_sources={expsm_activation: 5, expsm_mechanism_search: 2}
```

## Future Path

This view can later become input to a runtime-only
`ReflectionCandidateBuilder`, or to a separate `NeedMoreEvidence` signal, but
that is intentionally out of scope for the current pass.
