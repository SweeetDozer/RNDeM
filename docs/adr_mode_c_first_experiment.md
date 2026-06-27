# Mode C First Experiment

Status: accepted design / disabled scaffold implemented

## Context

`docs/adr_behavior_influence_modes.md` defines Mode C as advisory memory-gate
influence. `docs/design_mode_c_memory_gate_influence.md` narrows Mode C as a
future design space, but current runtime policy remains Mode A: observation
only.

This ADR decides the first safe Mode C experiment in advance. A disabled
scaffold now exists for the future experiment, but it does not enable Mode C,
connect pressure/review signals to memory gates, or change runtime behavior.

## Decision

The first Mode C experiment, if implemented later, should use
`PolicyPressureReview` as the only advisory source.

The first target should be `MemoryWriteReviewModule` in
`clc/consolidation/memory_write_review_module.py`, because it is the earliest
review-only memory gate in the current code before draft writing. `DraftCommitGate`
in `clc/consolidation/draft_commit_gate.py` remains a conservative later target
for draft promotion, not the first experiment target.

The advisory may only add inspectable metadata to review decisions. The advisory
must not directly approve, commit, reject, or write memory. The advisory must
not make memory writes more permissive in the first experiment.

The first experiment may only make gates more cautious or more explicit, never
more permissive.

## First Source

Allowed first source:

- `PolicyPressureReview`

Not allowed as direct first sources:

- `NeedMoreEvidenceSignal`
- `ReflectionCandidate`
- `ReflectionReview`
- `PolicyPressure`
- `DecisionCycleHistoryView`

Reason: `PolicyPressureReview` is the highest-level summarized review-only
layer. Lower-level signals should remain source material, not direct gate
influence.

## First Target

Recommended first target:

- `MemoryWriteReviewModule` in
  `clc/consolidation/memory_write_review_module.py`

Allowed later target after separate approval:

- `DraftCommitGate` in `clc/consolidation/draft_commit_gate.py`

Forbidden first targets:

- `ExpSMUpdateWriter`
- `ExpSMCommitWriter`
- `ValueFeedbackUpdateWriter`
- AKBSM writers or any direct AKBSM write path

The first experiment should prefer the earliest review-only gate that can record
advisory metadata without reaching a writer.

## Allowed Advisory Effect

Allowed:

- attach advisory metadata to a review result
- add human/debug-visible reason
- recommend `defer`, `review_more`, or `check_evidence`
- make review stricter only if explicitly enabled by future runtime policy

Not allowed:

- direct write
- direct commit
- direct approval
- direct rejection as a command
- direct scoring
- direct action injection
- guard bypass
- DecisionSelector influence
- ActionScoring influence
- ModeActionGuard change

## Forbidden Effects

Mode C first experiment must not:

- bypass `MemoryMutationPolicy`
- modify ExpSM semantic core
- modify AKBSM
- modify permanent memory directly
- make memory writes more permissive
- create marker 36
- trigger planning
- call an LLM
- implement chatbot behavior

No confidence, severity, or review status may force approval.

## Runtime Profile Policy

`safe_demo`:

- Mode C effect disabled.
- Advisory may be computed only if a future verifier allows it, but must have no
  effect.

`draft_only`:

- Advisory metadata may be attached to draft review only.
- No permanent memory writes.

`mutating_memory`:

- Advisory metadata may reach review gates.
- Writers still obey `MemoryMutationPolicy`.

Mode C must be disabled by default in all profiles until a later implementation
ADR explicitly changes that.

Current scaffold:

- `MemoryMutationPolicy.mode_c_memory_gate_advisory_enabled` defaults to
  `False` for `safe_demo`, `draft_only`, and `mutating_memory`.
- `MemoryGateAdvisory` and `ModeCMemoryGateAdvisoryProvider` live in
  `clc/runtime/mode_c_advisory.py`.
- The provider returns no advisory while disabled and is not wired into
  `MemoryWriteReviewModule`.
- `PolicyPressureReview` remains disconnected from behavior and memory gates by
  default.

## Confidence/Severity Policy

Low confidence advisory must not affect a gate.

Medium/high confidence may only recommend caution or defer.

No confidence level may force approval. No confidence level may bypass existing
gates.

The first experiment should treat severity as an audit/review hint, not as a
command.

## Auditability

Future implementation must expose advisory metadata in:

- review result evidence
- debug output or `ContextMemory` `MODULE_UPDATE`
- scenario summaries
- regression snapshots if stable

Do not add a new marker in the first experiment. No marker 36 for first Mode C
experiment.

## Scenario Requirements

Future scenario names:

- `mode_c_disabled_no_effect`
- `mode_c_safe_demo_no_effect`
- `mode_c_draft_only_metadata_only`
- `mode_c_low_confidence_ignored`
- `mode_c_medium_confidence_defer_recommendation`
- `mode_c_mutating_memory_writer_still_gated`

These are future scenario names only. This ADR does not add scenario files or
snapshots.

## Verifier Requirements

Future required verifiers and updates:

- `tools/verify_mode_c_first_experiment_adr.py`
- `tools/verify_mode_c_disabled_scaffold.py`
- future `tools/verify_mode_c_advisory_memory_gate.py`
- `tools/verify_policy_pressure_influence_boundary.py` update
- `tools/verify_memory_mutation_policy.py` update
- `tools/verify_phase_regression_snapshots.py` update
- `tools/verify_phase_level_invariants.py` update

Required checks:

- Mode C disabled by default
- `safe_demo` has no effect
- `draft_only` metadata remains draft-only
- low confidence ignored
- medium/high confidence can only recommend caution/defer
- writers still obey `MemoryMutationPolicy`
- ExpSM/AKBSM hashes unchanged in safe checks
- DecisionSelector and ActionScoring unchanged
- marker 36 absent

## Rollback

Rollback for a future implementation must:

1. Disable the Mode C feature/runtime policy flag.
2. Remove advisory input from `MemoryWriteReviewModule`.
3. Verify Mode A snapshots still match.
4. Verify real ExpSM and AKBSM hashes.
5. Verify writers still obey `MemoryMutationPolicy`.
6. Verify no marker 36 and no new permanent memory write path.

If disabling Mode C does not restore Mode A behavior, the implementation should
be reverted.

## Consequences

This ADR answers the first Mode C path while keeping current runtime behavior
unchanged. It chooses the highest-level review source and earliest review-only
memory gate, and it forbids permissive write behavior in the first experiment.

The first implementation, if approved later, should be small, disabled by
default, and mostly observable as review metadata.

## Open Questions Remaining

- What exact advisory metadata keys should `MemoryWriteReviewModule` expose?
- Should advisory metadata use `ContextMemory` `MODULE_UPDATE` or stay only in
  review result evidence?
- What confidence threshold separates ignored low confidence from defer
  recommendations?
- Should `DraftCommitGate` receive the second experiment after the first
  draft-review result is proven safe?
- Should stable advisory metadata be added to phase regression snapshots?
