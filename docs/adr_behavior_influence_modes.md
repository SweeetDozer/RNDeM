# Behavior Influence Modes

Status: proposed / discussion-only

## Context

The current prototype has a runtime-only diagnostic and review chain:

```text
DecisionCycleHistoryView
ReflectionCandidateBuilder
NeedMoreEvidenceSignal
ReflectionReview
PolicyPressure
PolicyPressureReview
```

This chain helps inspect recent decision history, uncertainty, weak value
signals, guard tension, and policy pressure. It is deliberately not a control
path. It may be observed by debug output, scenario fixtures, and verifiers, but
it does not change action proposal, scoring, selection, guard behavior, memory
writes, field projection, neuromodulation, planning, or external behavior.

The architecture question is whether these diagnostic systems should ever
influence behavior in a future version. This ADR records possible influence
modes without approving or implementing any behavior influence.

## Current Policy

Current policy:

- reflection/pressure chain is observational-only
- PolicyPressureReview does not influence behavior
- NeedMoreEvidenceSignal does not influence behavior
- ReflectionReview does not influence behavior
- PolicyPressure does not influence behavior
- no planning
- no LLM calls
- no chatbot behavior

The current runtime remains Mode A. This ADR does not change runtime behavior.

## Decision Not Yet Made

No behavior influence mode is accepted by this ADR. The document only names
candidate modes, risk boundaries, required safety gates, and open questions.

Any future move beyond observation-only behavior requires a separate explicit
ADR, implementation plan, verifier updates, rollback path, and user approval.

## Candidate Influence Modes

### Mode A: Observation Only

Current mode.

Diagnostic systems may produce summaries, runtime objects, debug output, and
scenario/verifier observations. They cannot affect behavior.

### Mode B: Review-Only Influence

Diagnostic systems may feed other review-only modules. Review-only modules may
produce additional summaries, classifications, or recommended future operations.

They still have no behavior effect. They cannot change scoring, selection,
guards, memory gates, fields, neuromodulation, planning, or memory writes.

### Mode C: Advisory Memory-Gate Influence

Diagnostic systems may advise memory write review gates under an explicit
runtime policy.

They cannot directly write memory. They may only influence review
recommendations, and only when enabled by a feature flag or runtime policy gate.
Permanent writes remain controlled by existing memory mutation policy and review
modules.

This is the first plausible behavior-adjacent mode because it can be bounded at
review gates and audited before any permanent memory mutation.

### Mode D: Advisory Candidate-Priority Influence

Diagnostic systems may produce advisory metadata for candidate prioritization.

They cannot directly select actions. They cannot inject candidates. They cannot
bypass ModeActionGuard. They cannot override DecisionSelector. Any effect must
be explicit, bounded, explainable, and disabled by default.

### Mode E: DecisionSelector Scoring Influence

Diagnostic, value, or pressure systems may influence scoring.

This is high-risk. It changes behavior directly and requires a separate
accepted ADR, new scenario fixtures, regression snapshots, phase-level invariant
updates, influence-boundary verifier changes, and a rollback path.

### Mode F: Planning/Task Influence

Diagnostic systems may create future tasks or plans.

This is not allowed yet. It requires a separate planning architecture before any
reflection/pressure signal can produce tasks, plans, chatbot behavior, or LLM
calls.

## Forbidden Direct Connections

The following direct connections remain forbidden unless explicitly approved by
a later ADR:

- PolicyPressureReview -> DecisionSelector direct scoring
- PolicyPressure -> ActionScoring direct scoring
- NeedMoreEvidenceSignal -> ActionProposer direct candidate injection
- ReflectionReview -> Memory writer direct write
- ReflectionCandidate -> FieldUpdater direct modulation
- PolicyPressure -> Neuromodulation direct modulation
- Reflection chain -> ModeActionGuard bypass
- Any reflection/pressure module -> permanent memory write

These restrictions also prohibit hidden indirect equivalents that create the
same behavior effect through a renamed adapter or convenience helper.

## Required Safety Gates

Any future behavior influence requires:

- explicit ADR
- feature flag / runtime policy gate
- safe default disabled
- scenario fixtures
- regression snapshots
- phase-level invariant update
- influence boundary verifier update
- memory safety hash checks
- rollback instructions

The implementation must also document which profiles may enable the influence,
which modules may read the influence signal, and how the effect is surfaced in
audits or summaries.

## Required Verifiers

At minimum, a future behavior influence pass must update or add verifiers for:

- influence boundary scanning
- phase-level invariants
- scenario fixtures
- phase regression snapshots
- memory safety hash checks
- DecisionAudit explainability when candidate scoring or selection is affected
- memory mutation policy when memory gates are affected
- rollback or feature-flag disabled behavior

Until those verifiers exist and pass, Mode A remains the only accepted behavior
mode.

## Future Migration Path

Recommended gradual path:

1. Stay in Mode A for v0.0.x.
2. Mode B review-only may continue.
3. First possible behavior influence should be Mode C, advisory memory-gate
   influence, not DecisionSelector scoring.
4. DecisionSelector scoring influence should wait until stronger scenario
   coverage exists.
5. Planning/task influence is later architecture work.

`docs/design_mode_c_memory_gate_influence.md` expands the Mode C option as a
design-only, not implemented proposal. It recommends `PolicyPressureReview` as
the first possible advisory source and `MemoryWriteReviewModule` or
`DraftCommitGate` as the first possible review-gate target, with all behavior
disabled by default until a later accepted ADR and verifier updates exist.

## Consequences

The project can discuss behavior influence without weakening the current safety
boundary. Current behavior remains unchanged, and the existing
PolicyPressureReview influence boundary continues to be the active guardrail.

Future work gets a named ladder of risk: review-only before advisory memory
gates, advisory memory gates before candidate priority, candidate priority
before DecisionSelector scoring, and planning only after a separate planning
architecture exists.

## Open Questions

- Should diagnostic pressure ever influence behavior?
- Should influence first touch memory gates or candidate scoring?
- Should influence be per-profile, e.g. safe_demo/draft_only/mutating_memory?
- Should influence require confidence thresholds?
- Should influence be reversible/explainable through DecisionAudit?
- Should AKBSM associations participate in behavior influence?
