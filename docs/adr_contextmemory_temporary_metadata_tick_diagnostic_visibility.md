# ADR: ContextMemory Temporary Metadata Tick Diagnostic Visibility

## Status

This ADR is design-only.

No tick diagnostic visibility is implemented by this pass.
No runtime source code is changed by this pass.
No `_run_tick()` wiring is added by this pass.
No `ContextMemoryManager` call is added by this pass.
No real ContextMemory read/write is added by this pass.
No proposal storage is added by this pass.
No behavior influence is added by this pass.
No AKBSM write path is added by this pass.

## Context

The generic temporary metadata placement scaffold exists. The AKBSM proposal
temporary metadata placement adapter exists. Temporary metadata negative/
retention coverage exists. A read-only diagnostic temporary metadata observer
exists, observer negative/no-behavior coverage exists, and an explicit
runtime-facing diagnostic scaffold exists.

The diagnostic scaffold requires `explicit_runtime_diagnostic_harness`, uses
the existing local temporary metadata observer, is read-only, is metadata-only,
is local/scaffold-only, is not normal runtime default, and is not wired into
`_run_tick()`. It does not call `ContextMemoryManager`, does not create real
ContextMemory reads/writes, does not influence behavior/scoring/guards/Mode C/
`PolicyPressureReview`, and cannot authorize writes.

Diagnostic wiring negative/no-behavior coverage exists and proves the current
scaffold remains explicit-only and unwired. The next design question is whether
temporary metadata diagnostics may ever become visible near a tick execution
without becoming part of the tick decision path.

## Decision

The first future tick-facing diagnostic visibility should not modify
`_run_tick()`.

The preferred first implementation is an explicit external diagnostic wrapper or diagnostic harness.

The preferred first implementation should be an explicit external diagnostic
wrapper or diagnostic harness that can run before/after a tick call without
becoming part of the tick decision path.

Any direct `_run_tick()` diagnostic hook is deferred and requires a separate
implementation ADR/pass.

If direct `_run_tick()` visibility is ever allowed, it must be
post-behavior-output, diagnostic-only, disabled by default, authority-gated, and
proven no-behavior-influence.

## Preferred design

Preferred future surface names only:

- `TemporaryMetadataTickDiagnosticWrapper`
- `TemporaryMetadataTickDiagnosticSnapshot`
- `build_tick_diagnostic_snapshot(...)`
- `run_tick_with_diagnostics(...)`

Preferred future behavior:

- explicit diagnostic harness only
- not normal runtime default
- does not modify `_run_tick()`
- collects diagnostics outside the tick decision path
- calls existing diagnostic scaffold only under explicit diagnostic authority
- returns runtime behavior output unchanged
- returns diagnostic snapshot separately
- does not feed diagnostics into any runtime decision/scoring/guard/writer path

The wrapper/harness may surround a tick call only as an external caller. It may
observe the behavior result after it is produced, but the diagnostic snapshot
must remain separate from the behavior output.

## Deferred design

Direct `_run_tick()` diagnostic hook is deferred.

If documented as a future possibility, a direct `_run_tick()` hook must be:

- optional
- disabled by default
- explicit diagnostic authority only
- post-behavior-output only
- after all `DecisionSelector`/`ActionScoring`/`ActionProposer`/
  `ModeActionGuard` behavior inputs are finalized
- not before or between behavior phases
- not allowed to change tick result
- not allowed to change memory writes
- not allowed to change `apply_pending` timing
- not allowed to feed Mode C or `PolicyPressureReview`

Any direct hook requires a separate ADR/pass before implementation.

## Diagnostic-only tick visibility principle

Tick diagnostic visibility means: the system can produce a separate diagnostic
snapshot about temporary metadata near a tick execution.

Tick diagnostic visibility means: separate diagnostic snapshot about temporary metadata near a tick execution.

It does not mean: the tick can decide differently.

It does not mean: selector/scoring/proposer/guards can read diagnostics.

It does not mean: memory writers can read diagnostics.

It does not mean: `apply_pending` timing can change.

It does not mean: AKBSM/ExpSM can be updated.

It does not mean: temporary metadata becomes permanent memory.

It does not mean: diagnostics authorize writes.

## Allowed future visibility surfaces

Allowed first future surfaces:

- explicit external diagnostic wrapper
- explicit diagnostic harness
- manually requested tick diagnostic snapshot
- scenario/test-only diagnostic tick run

Allowed future diagnostic content:

- tick number or diagnostic tick
- diagnostics enabled/disabled flag
- active temporary metadata count
- namespaces present
- payload kinds present
- TTL/expiration diagnostics
- expired metadata count as diagnostics only
- AKBSM proposal lifecycle state as metadata only
- transition result metadata as metadata only
- diagnostic authority used

## Forbidden tick/runtime paths

Forbidden integration points:

- `DecisionSelector`
- `ActionScoring`
- `ActionProposer`
- `ModeActionGuard`
- Mode C
- `ModeCMemoryGateAdvisoryProvider`
- `PolicyPressureReview`
- `ValueFeedback`
- ExpSM commit/update paths
- `MemoryDraftWriter`
- `ExpSMCommitWriter`
- `ExpSMUpdateWriter`
- `ValueFeedbackUpdateWriter`
- AKBSM writers/save paths
- `ContextMemoryManager.apply_pending()`
- normal behavior output path
- default `_run_tick` path

Direct `_run_tick()` calls to diagnostics are forbidden until a separate
implementation pass explicitly changes this.

## Activation and authority model

Diagnostic authority is required.

Missing authority must be rejected.

Unknown authority must be rejected.

Placement authority is not tick diagnostic authority.

Observation authority is not tick diagnostic authority unless a future ADR
explicitly shares them.

Runtime diagnostic authority is not tick diagnostic authority unless a future
ADR explicitly shares them.

Tick diagnostic authority is not placement authority.

Tick diagnostic authority is not observation authority.

Tick diagnostic authority is not write authority.

Tick diagnostic authority is not AKBSM write authority.

Normal runtime default must not activate tick diagnostics automatically.

Suggested future authority constant only:

`CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY = "explicit_tick_diagnostic_harness"`

## No-behavior-influence requirements

Future implementation must prove:

- same input produces the same behavior output with tick diagnostics disabled
  and enabled
- `DecisionSelector` inputs unchanged
- `ActionScoring` inputs unchanged
- `ActionProposer` inputs unchanged
- `ModeActionGuard` inputs unchanged
- Mode C inputs unchanged
- `PolicyPressureReview` inputs unchanged
- memory writer inputs unchanged
- AKBSM writer inputs unchanged
- ExpSM writer inputs unchanged
- `ContextMemoryManager.apply_pending()` timing unchanged
- tick phase order unchanged
- no additional Memory/AKBSM writes
- no additional Memory/ExpSM writes
- real memory hashes unchanged

## Tick-order requirements

Future external wrapper must not modify tick order.

Future external wrapper must not move `apply_pending`.

Future external wrapper must not add diagnostics before selector/scoring/guard
phases.

Future external wrapper must not add diagnostics before selector/scoring/guard phases.

Future external wrapper must keep diagnostics separate from behavior output.

Direct `_run_tick()` diagnostic hook is deferred and cannot be implemented
without separate ADR/pass.

## TTL and expiration requirements

Tick diagnostics must ignore expired metadata as active.

Expired metadata may appear only in explicit expired diagnostics.

Expired metadata must not be revived.

Expired metadata must not trigger transitions.

Expired metadata must not become permanent memory.

Expired metadata must not become write approval.

## AKBSM proposal metadata boundaries

ContextMemory metadata presence is not AKBSM write approval.

A temporary placement result is not storage approval.

An observation result is not write approval.

A diagnostic runtime report is not write approval.

A tick diagnostic snapshot is not write approval.

`accepted_for_observation` remains observation-only.

`deferred` is not pending commit.

Rejected metadata cannot authorize writes.

Expired metadata cannot authorize writes.

`proposal.commit_allowed` remains `False`.

AKBSM writes remain blocked.

## Required future scenarios

Future scenarios must prove:

- external diagnostic wrapper can produce separate tick diagnostic snapshot
- missing tick diagnostic authority is rejected
- unknown tick diagnostic authority is rejected
- placement authority cannot request tick diagnostics
- observation authority cannot request tick diagnostics unless explicitly
  shared by future ADR
- runtime diagnostic authority cannot request tick diagnostics unless
  explicitly shared by future ADR
- tick diagnostic authority cannot place metadata
- tick diagnostic authority cannot authorize writes
- tick diagnostic snapshot sees active metadata only as diagnostic material
- tick diagnostic snapshot ignores expired metadata as active
- tick diagnostic snapshot is returned separately from behavior output
- behavior output is identical with diagnostics disabled and enabled
- `DecisionSelector` inputs unchanged
- `ActionScoring` inputs unchanged
- `ActionProposer` inputs unchanged
- `ModeActionGuard` inputs unchanged
- Mode C inputs unchanged
- `PolicyPressureReview` inputs unchanged
- `ContextMemoryManager.apply_pending` timing unchanged
- no proposal storage
- no permanent queues
- no Memory/AKBSM writes
- no Memory/ExpSM writes
- AKBSM/ExpSM hashes remain unchanged

## Required future verifiers

Future verifier coverage must include:

- `verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py`
- `verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py`
- `verify_contextmemory_temporary_metadata_tick_diagnostic_no_behavior_influence.py`
- `verify_contextmemory_temporary_metadata_tick_order_unchanged.py`
- `verify_akbsm_proposal_temporary_metadata_tick_diagnostic_scenarios.py`

Those verifiers must verify:

- tick diagnostic visibility is explicit
- tick diagnostic visibility is authority-gated
- default `_run_tick` path is unchanged
- tick phase order is unchanged
- `ContextMemoryManager.apply_pending` timing unchanged
- diagnostic snapshot is separate from behavior output
- behavior output unchanged with diagnostics disabled/enabled
- no `DecisionSelector` influence
- no `ActionScoring` influence
- no `ActionProposer` influence
- no `ModeActionGuard` influence
- no Mode C influence
- no `PolicyPressureReview` influence
- no memory writer influence
- no AKBSM writer influence
- no ExpSM writer influence
- no proposal storage
- no permanent queues
- no Memory/AKBSM writes
- no Memory/ExpSM writes
- no `semantic_core.json`
- no `technical_feedback_patterns.json`
- no commit/apply/save/write/persist/mutate path
- marker 36 absent
- memory hashes unchanged

## Rejected alternatives

Rejected alternatives:

- wiring diagnostics directly into `_run_tick()` by default
- diagnostics before `DecisionSelector`
- diagnostics before `ActionScoring`
- diagnostics before `ActionProposer`
- diagnostics before `ModeActionGuard`
- diagnostics inside Mode C
- diagnostics inside `PolicyPressureReview`
- diagnostics inside memory writers
- diagnostics inside AKBSM writers
- diagnostics changing tick result
- diagnostics changing behavior output
- diagnostics moving `ContextMemoryManager.apply_pending()`
- diagnostics treated as write approval
- `accepted_for_observation` treated as AKBSM write approval
- `deferred` treated as pending commit
- expired metadata revived by tick diagnostics
- diagnostics creating proposal storage
- diagnostics creating permanent queues
- diagnostics writing AKBSM or ExpSM
- direct `_run_tick()` hook implemented before wrapper/no-behavior-influence checks

## Consequences

Tick diagnostic visibility ADR exists as design-only guidance.

The preferred future shape is an external diagnostic wrapper/harness. Direct
`_run_tick()` diagnostic hook is deferred. No runtime source code changed. No
`_run_tick()` wiring exists. Diagnostics remain unwired from behavior paths. No
real ContextMemory reads/writes exist. No behavior/scoring/guard influence
exists. AKBSM proposal metadata remains non-authoritative for writes. AKBSM
writes remain blocked.

A later implementation scaffold adds
`clc/runtime/context_temporary_metadata_tick_diagnostics.py` as the external
tick diagnostic wrapper surface. It stays outside `_run_tick()`, does not
modify `_run_tick()`, requires `explicit_tick_diagnostic_harness`, runs a
provided tick callable without diagnostic inputs, returns behavior output
unchanged, and returns a diagnostic snapshot separately. The scaffold is
read-only, metadata-only, not normal runtime default, calls no
`ContextMemoryManager`, creates no real ContextMemory reads/writes, cannot
influence behavior/scoring/guards/Mode C/`PolicyPressureReview`, cannot
authorize writes, keeps AKBSM proposal metadata non-authoritative for writes,
and leaves AKBSM writes blocked.

`tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py`
contains the no-behavior-influence proof for this scaffold: direct tick
callable output equals wrapped behavior output, tick callable args/kwargs stay
unchanged, diagnostics are separate from behavior output, diagnostics disabled
or enabled both preserve behavior output, and diagnostic data is not passed
into the tick callable. No separate no-behavior verifier is required for this
scaffold.

## Next steps

Review this ADR before any tick-facing diagnostic visibility implementation
pass.

The next implementation, if explicitly approved later, should add only an
external diagnostic wrapper/harness scaffold with no behavior influence, no
default `_run_tick()` path, no tick-order changes, no
`ContextMemoryManager.apply_pending()` timing changes, no real ContextMemory
reads/writes, no storage, no queues, and no AKBSM/ExpSM writes.
