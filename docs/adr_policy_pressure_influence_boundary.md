# PolicyPressure Influence Boundary

Status: accepted / current

## Context

The runtime currently builds a diagnostic-only reflection chain:

```text
DECISION_CYCLE_SUMMARY marker 35
DecisionCycleHistoryView
ReflectionCandidateBuilder
NeedMoreEvidenceSignal
ReflectionReview
PolicyPressure
PolicyPressureReview
```

Scenario fixtures and verifiers inspect this chain so current reflective state
can be observed and audited. The chain is not a control path.

## Decision

`PolicyPressure` is runtime-only observational state.

It may be displayed in debug output. It may be read by verifiers and scenario
runners. It may be used by future review modules only after an explicit
architecture decision.

Current: Option B review-only extension implemented as `PolicyPressureReview`.

Recommended next safe extension: additional Option B review-only modules only.

## Allowed Now

- Build `PolicyPressure` from `ReflectionReview`.
- Keep the latest pressure and bounded recent pressure list in runtime memory.
- Print pressure in runtime debug output.
- Read pressure from verifiers and scenario runners.
- Build `PolicyPressureReview` from `PolicyPressure` as a review-only
  diagnostic layer.
- Print pressure review in runtime debug output.
- Document pressure states and scenario expectations.

## Forbidden Now

`PolicyPressure`, `PolicyPressureReview`, `ReflectionReview`, and
`NeedMoreEvidenceSignal` must not affect:

- `DecisionSelector`
- `ActionProposer`
- `ModeActionGuard`
- `MemoryDraftWriter`
- `DraftCommitGate`
- `ExpSMCommitWriter`
- `ExpSMUpdateWriter`
- `ValueFeedbackUpdateWriter`
- `FieldUpdater`
- `NeuromodulationModule`
- permanent memory

They must not be connected to scoring, planning, memory gates, field updates,
neuromodulation, or permanent memory writes.

## Future Options

Option A: Observation only

`PolicyPressure` remains debug/diagnostic only.

Option B: Review-only influence

`PolicyPressure` may feed future `PolicyPressureReview` or
`NeedMoreEvidenceReview`, but those reviews still do not affect behavior.

Implemented review-only layer: `PolicyPressureReview`.

Option C: Memory-gate advisory influence

`PolicyPressure` may advise draft, commit, or update gates, but only after an
explicit architecture decision and verifier coverage.

Option D: Decision scoring influence

`PolicyPressure` may affect `DecisionSelector` or `ActionProposer`, but this is
high risk and must require an explicit architecture decision, scenario coverage,
and rollback-safe policy flags.

## Verification

Run:

```bash
python tools/verify_policy_pressure_influence_boundary.py
```

The verifier scans behavior-changing modules for forbidden imports or direct
references to `PolicyPressure`, `ReflectionReview`, `NeedMoreEvidenceSignal`,
`PolicyPressureReview`, and their runtime object names.

Allowed references remain in runtime construction/debug output, scenario
runners, verifiers, documentation, and the diagnostic evaluation modules
themselves.

## Consequences

The reflection/pressure chain can be inspected without silently changing runtime
control behavior. Any later behavior influence must be introduced as a separate
architecture decision with targeted verifier coverage and rollback-safe policy
boundaries.
