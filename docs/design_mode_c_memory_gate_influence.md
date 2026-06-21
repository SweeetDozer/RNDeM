# Mode C: Advisory Memory-Gate Influence Design

Status: design-only / not implemented

## Context

`docs/adr_behavior_influence_modes.md` defines Mode C as a possible future
advisory memory-gate influence mode. Mode C is the first recommended
behavior-adjacent step only because it can be bounded at review gates before any
writer or permanent memory mutation.

This document designs what Mode C could mean. It does not approve Mode C and it
does not implement behavior influence.

## Current Policy

Current runtime is still Mode A.

PolicyPressureReview does not influence behavior. Reflection/pressure chain is
observational-only. No memory gate currently reads pressure/review signals. This
document is design-only.

No runtime, scoring, selection, guard, memory gate, memory writer, field,
neuromodulation, planning, ExpSM, or AKBSM behavior changes in this pass.

## Design Goal

Mode C means diagnostic/review systems may provide advisory metadata to memory
review gates under an explicit runtime policy gate.

They must not directly write memory. They must not directly approve memory
writes. They must not bypass existing gates. They must not alter ExpSM semantic
core. They must not alter permanent memory unless existing MemoryMutationPolicy
allows it.

The advisory should be inspectable, explainable, bounded, disabled by default,
and treated as review evidence rather than a command.

## Non-Goals

- Do not implement Mode C.
- Do not connect PolicyPressure or PolicyPressureReview to memory gates.
- Do not connect reflection/pressure signals to scoring, planning, memory
  writers, FieldUpdater, NeuromodulationModule, or ModeActionGuard.
- Do not make writes more permissive by default.
- Do not introduce a new marker, including marker 36.
- Do not modify ExpSM records, ExpSM semantic core, value feedback memory, or
  AKBSM.

## Possible Signal Sources

Potential signal sources, ranked conservatively:

1. `PolicyPressureReview`
   - Recommended first source.
   - It is already summarized, review-only, and built after the runtime
     behavior path.
   - It carries review status, pressure type, active state, primary issue,
     confidence, and recommended future operation.
2. `PolicyPressure`
   - Lower-level than `PolicyPressureReview`.
   - It may be useful as supporting evidence, but should not directly advise
     gates in the first Mode C design.
3. `ReflectionReview`
   - Useful for review status and primary issue.
   - Should remain upstream evidence behind `PolicyPressureReview`.
4. `NeedMoreEvidenceSignal`
   - Useful as evidence of uncertainty or insufficient support.
   - Too low-level to affect gates directly in the first design.
5. `DecisionCycleHistoryView`
   - Useful for audits and scenario expectations.
   - Should not directly affect gates; it should feed review layers.
6. `ValueFeedbackMemoryView`
   - Useful context for value-related evidence.
   - Should not be part of the first Mode C source because it is already close
     to value/memory update semantics.

First Mode C source should be `PolicyPressureReview` only, because it is already
summarized and review-only. Lower-level signals should not directly affect
gates.

## Possible Gate Targets

Potential memory review targets:

1. `MemoryWriteReviewModule` in
   `clc/consolidation/memory_write_review_module.py`
   - Conservative first target candidate.
   - It is already a review layer before draft writing.
   - It can reject or defer material without directly writing permanent memory.
2. `DraftCommitGate` in `clc/consolidation/draft_commit_gate.py`
   - Conservative first target candidate if the project wants advisory metadata
     to affect draft promotion rather than draft creation.
   - It is still a gate, not a writer.
3. `ExpSMUpdateReviewGate` in
   `clc/consolidation/expsm_update_review_gate.py`
   - Later target only.
   - It is closer to permanent ExpSM mutation and needs stronger verifier and
     scenario coverage first.
4. `ValueFeedbackReviewGate` in
   `clc/evaluation/value_feedback_review_gate.py`
   - Later target only.
   - It is close to value feedback updates and should wait until Mode C is
     proven on draft-oriented gates.

First Mode C target should be `MemoryWriteReviewModule` or `DraftCommitGate`,
not `ExpSMUpdateWriter`, not `ValueFeedbackUpdateWriter`, and not any writer.

`docs/adr_mode_c_first_experiment.md` narrows this design for the first future
experiment: use `PolicyPressureReview` as the only source and
`MemoryWriteReviewModule` as the first target. `DraftCommitGate` remains a later
draft-promotion target.

## Advisory Payload Shape

Example future payload only:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryGateAdvisory:
    source: str
    tick: int
    advisory_type: str
    severity: str
    confidence: float
    recommendation: str
    reason: str
    apply_now: bool = False
```

`apply_now` must remain `False` in the first design. Advisory payload must be
inspectable and auditable. Advisory must not be treated as a command.

The payload should be copied into review metadata only when a future policy gate
allows it. It should not become a direct `ContextOperation`, permanent memory
write, draft commit, ExpSM update, value feedback update, AKBSM update, or
DecisionSelector input.

## Runtime Policy Gate

Mode C requires a future feature flag or runtime profile gate.

Example future policy:

```text
mode_c_memory_gate_advisory_enabled = false by default
allowed only outside safe_demo unless explicitly enabled
draft_only may allow advisory for drafts only
mutating_memory may allow advisory to review gates, not writers
```

No such policy is implemented in this pass.

Recommended policy behavior:

- default disabled in all profiles
- `safe_demo` blocks advisory effect unless an explicit test-only override is
  added in a later accepted ADR
- `draft_only` may allow advisory metadata on draft review gates only
- `mutating_memory` may allow advisory metadata to review gates, but writers
  still obey MemoryMutationPolicy
- disabled behavior must match current Mode A snapshots

## Safety Boundaries

Forbidden behavior:

- advisory cannot directly call a writer
- advisory cannot directly commit draft
- advisory cannot directly update ExpSM
- advisory cannot directly update value feedback
- advisory cannot modify AKBSM
- advisory cannot modify ExpSM semantic core
- advisory cannot bypass MemoryMutationPolicy
- advisory cannot influence DecisionSelector or ActionScoring
- advisory cannot change ModeActionGuard
- advisory cannot trigger planning
- advisory cannot create LLM calls or chatbot behavior
- advisory cannot make permanent memory writes more permissive by default

Any implementation that creates an equivalent hidden path is also forbidden.

## Required Verifier Changes

Future Mode C implementation requires verifier updates or new verifiers:

- `tools/verify_mode_c_memory_gate_advisory.py`
- `tools/verify_policy_pressure_influence_boundary.py` update
- `tools/verify_memory_mutation_policy.py` update
- `tools/verify_phase_level_invariants.py` update
- `tools/verify_phase_regression_snapshots.py` update

Required checks:

- Mode C disabled by default
- `safe_demo` behavior unchanged
- advisory never writes memory
- advisory reaches only allowed review gate
- writers remain gated by MemoryMutationPolicy
- ExpSM/AKBSM hashes unchanged in `safe_demo`
- DecisionSelector scoring unchanged
- ActionScoring behavior unchanged
- ModeActionGuard behavior unchanged
- marker 36 remains absent
- disabled Mode C matches current phase regression snapshots

## Required Scenario Coverage

Future scenario coverage should include:

- `scenario_mode_c_disabled_no_effect`
- `scenario_mode_c_draft_advisory_only`
- `scenario_mode_c_memory_gate_rejects_low_confidence`
- `scenario_mode_c_memory_gate_records_advisory_metadata`
- `scenario_mode_c_safe_demo_blocks_advisory_effect`

These are design names only. This pass does not add scenario fixtures or
snapshots.

## Rollback Plan

Rollback must be simple and observable:

1. Disable feature flag or runtime policy gate.
2. Remove advisory input from the memory gate.
3. Rerun phase regression snapshots.
4. Verify real ExpSM/AKBSM hashes.
5. Verify decision snapshots unchanged.
6. Verify `verify_policy_pressure_influence_boundary.py` and
   `verify_memory_mutation_policy.py`.
7. Confirm no marker 36 and no new permanent memory writes.

If disabled Mode C does not match Mode A behavior, the implementation should be
reverted rather than patched around.

## Open Questions

- Which exact advisory metadata keys should MemoryWriteReviewModule expose?
- Should safe_demo always block Mode C?
- Should draft_only allow advisory metadata?
- What confidence threshold is required?
- Should advisory be stored in ContextMemory as MODULE_UPDATE or a future
  marker?
- Should advisory influence only rejection/deferral, not approval?
- Should Mode C ever be allowed to make memory writes more permissive?
