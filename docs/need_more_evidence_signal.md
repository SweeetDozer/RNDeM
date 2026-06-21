# Need More Evidence Signal

`NeedMoreEvidenceSignal` is a runtime-only diagnostic signal derived from recent
`ReflectionCandidateBuilder` output.

It does not emit a cognitive marker, write permanent memory, modify ExpSM or
AKBSM, update value feedback memory, change scoring, change planning, or feed
back into `DecisionSelector`, `ActionProposer`, `ModeActionGuard`, memory write
gates, `FieldUpdater`, or neuromodulation.

## Influence Boundary

Current implementation is observational only. `NeedMoreEvidenceSignal` does not
affect action selection, memory gates, `FieldUpdater`, or
`NeuromodulationModule`. See
`docs/adr_policy_pressure_influence_boundary.md`.

## Source

The signal builder reads the reflection candidates produced in the current tick.
It stores the latest signal and a bounded in-memory recent list only.

Bound:

- `MAX_RECENT_NEED_MORE_EVIDENCE_SIGNALS = 50`

## Signal API

Each `NeedMoreEvidenceSignal` contains:

- `signal_id`
- `tick`
- `active`
- `severity`
- `confidence`
- `reason`
- `source_reflection_types`
- `recommended_future_operation`
- `evidence`
- `apply_now`
- `tags`

`apply_now` is always `False` in this pass. `recommended_future_operation` is
not executed.

## Activation Rules

The signal is active for:

- `repeated_uncertain_selection`: reason `repeated_uncertain_selection`,
  severity `medium`, future operation `collect_more_evidence`
- `insufficient_decision_confidence`: reason
  `insufficient_decision_confidence`, severity `low`, future operation
  `collect_more_evidence`
- `mixed_cycle_history`: reason `mixed_cycle_history`, severity `low`, future
  operation `inspect_recent_decision_context`
- `guard_policy_tension`: active only when the reflection candidate severity is
  `medium` or `high`, future operation `inspect_guard_policy_tension`

`weak_value_influence` is inactive by default, but appears as warning evidence.

If there are no candidates, or only `stable_clean_selection`, the signal is:

```text
active=false
severity=info
reason=no_evidence_gap_detected
recommended_future_operation=maintain_current_policy
```

## Priority

When multiple active candidates exist, severity wins:

```text
high > medium > low > info
```

For equal severity, reason priority is:

```text
repeated_uncertain_selection
insufficient_decision_confidence
guard_policy_tension
mixed_cycle_history
weak_value_influence
stable_clean_selection
no_decision_history
```

## Confidence

For active signals, confidence is the max confidence among candidates with the
chosen reason, clamped to `[0.0, 1.0]`.

For inactive signals, confidence is `0.0`.

## Evidence

Evidence is compact:

```text
reflection_count
active_reflection_types
all_reflection_types
max_reflection_confidence
source_trend_labels
reasons_seen
warning_reflection_types
min_confidence
```

No nested decision history payloads are copied into the signal.

## Runtime Debug

`CLCRuntime` builds the signal after `ReflectionCandidateBuilder.build(...)` and
before debug output.

Active example:

```text
need more evidence signal:
  active=true severity=medium confidence=1.00 reason=repeated_uncertain_selection
  recommended_future_operation=collect_more_evidence apply_now=false
```

Inactive example:

```text
need more evidence signal:
  active=false reason=no_evidence_gap_detected
```

## Future Path

Possible future layers:

- `NeedMoreEvidenceReview`
- `PolicyPressure`
- `ReflectionReview`

Any later connection to memory gates, decision gates, or planning should require
an explicit architecture decision.
