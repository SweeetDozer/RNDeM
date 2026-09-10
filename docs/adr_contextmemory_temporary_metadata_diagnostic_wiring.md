# ADR: ContextMemory Temporary Metadata Diagnostic Runtime Wiring

## Status

This ADR is design-only.

No diagnostic runtime wiring is implemented by this pass.
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
exists, and observer negative/no-behavior coverage exists.

The observer is authority-gated, local/scaffold-only, ignores expired metadata
as active metadata, and returns metadata-only reports. It remains unwired from
normal runtime and `_run_tick()`. No `ContextMemoryManager` calls, real
ContextMemory reads/writes, or AKBSM/ExpSM writes exist.

This ADR defines the first possible future runtime-facing diagnostic wiring
boundary without implementing that wiring.

## Decision

The first future runtime-facing observation wiring must be diagnostic-only.

It must expose observer output only through an explicit diagnostic surface.

It must not run automatically in the normal tick path by default.

It must not feed `DecisionSelector`, `ActionScoring`, `ActionProposer`,
`ModeActionGuard`, Mode C, `PolicyPressureReview`, feedback, memory writers,
AKBSM writers, or ExpSM writers.

It must not change behavior output.

It must not create or imply write approval.

It must not create persistent storage or queues.

## Diagnostic-only wiring principle

Diagnostic wiring means: the runtime can produce a report that temporary metadata exists.

Diagnostic wiring does not mean: decisions can change.

Diagnostic wiring does not mean: scores can change.

Diagnostic wiring does not mean: guards can change.

Diagnostic wiring does not mean: actions can change.

Diagnostic wiring does not mean: memory writes can occur.

Diagnostic wiring does not mean: AKBSM/ExpSM can be updated.

Diagnostic wiring does not mean: temporary metadata becomes permanent memory.

## Allowed future wiring surface

Tentative future surface names only:

- `RuntimeTemporaryMetadataDiagnosticReport`
- `RuntimeTemporaryMetadataDiagnosticView`
- `RuntimeTemporaryMetadataObservationDiagnosticProvider`
- `build_runtime_temporary_metadata_diagnostics(...)`

Allowed first future surface:

- explicit diagnostic command/harness
- explicit runtime diagnostic method
- scenario/test-only diagnostic run
- manually requested diagnostic report

Preferred first future integration shape:

- explicit diagnostic method or diagnostic harness
- called manually by scenario/test/diagnostic authority
- outside `_run_tick()`
- outside `DecisionSelector`/`ActionScoring`/`ActionProposer`/`ModeActionGuard`
- reads only local `ContextTemporaryMetadataPlacement` scaffold through the
  existing observer
- returns immutable diagnostic report
- report is not consumed by behavior code

If a later implementation needs `_run_tick()` visibility, it must require a
separate ADR and a no-behavior-influence verifier before code changes.

Allowed future report content:

- active temporary metadata count
- namespaces present
- payload kinds present
- TTL/expiration diagnostics
- expired metadata count as diagnostics only
- AKBSM proposal lifecycle state as metadata only
- transition result metadata as metadata only
- observer authority used
- diagnostic timestamp/tick if available

## Forbidden runtime paths

Forbidden integration points:

- `_run_tick()`
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

## Authority and activation model

Diagnostic observation authority is required.

Missing authority must be rejected.

Unknown authority must be rejected.

Placement authority is not observation authority.

Observation authority is not placement authority.

Diagnostic observation authority is not write authority.

Diagnostic observation authority is not AKBSM write authority.

Normal runtime default path must not activate diagnostics automatically.

Suggested future authority constant only:

`CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY = "explicit_runtime_diagnostic_harness"`

## No-behavior-influence requirements

Future implementation must prove:

- same scenario input produces same behavior output with diagnostic observation
  disabled and enabled
- `DecisionSelector` inputs unchanged
- `ActionScoring` inputs unchanged
- `ActionProposer` inputs unchanged
- `ModeActionGuard` inputs unchanged
- Mode C inputs unchanged
- `PolicyPressureReview` inputs unchanged
- memory writer inputs unchanged
- AKBSM writer inputs unchanged
- ExpSM writer inputs unchanged
- no additional Memory/AKBSM writes
- no additional Memory/ExpSM writes

## TTL and expiration requirements

Diagnostic wiring must ignore expired metadata as active.

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

`accepted_for_observation` remains observation-only.

`deferred` is not pending commit.

Rejected metadata cannot authorize writes.

Expired metadata cannot authorize writes.

`proposal.commit_allowed` remains `False`.

AKBSM writes remain blocked.

## Required future scenarios

Future scenarios must prove:

- diagnostic report can be requested explicitly under diagnostic authority
- missing diagnostic authority is rejected
- unknown diagnostic authority is rejected
- placement authority cannot request runtime diagnostics
- diagnostic authority cannot place metadata
- diagnostic authority cannot authorize writes
- diagnostic report sees active metadata only as diagnostic material
- diagnostic report ignores expired metadata as active
- diagnostic report does not alter behavior output
- diagnostic report does not alter `DecisionSelector` inputs
- diagnostic report does not alter `ActionScoring` inputs
- diagnostic report does not alter `ActionProposer` inputs
- diagnostic report does not alter `ModeActionGuard` inputs
- diagnostic report does not alter Mode C inputs
- diagnostic report does not alter `PolicyPressureReview` inputs
- diagnostic report does not create proposal storage
- diagnostic report does not create permanent queues
- diagnostic report does not write Memory/AKBSM
- diagnostic report does not write Memory/ExpSM
- AKBSM/ExpSM hashes remain unchanged

## Required future verifiers

Future verifier coverage must include:

- `verify_contextmemory_temporary_metadata_diagnostic_wiring_adr.py`
- `verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py`
- `verify_contextmemory_temporary_metadata_diagnostic_wiring_no_behavior_influence.py`
- `verify_akbsm_proposal_temporary_metadata_diagnostic_wiring_scenarios.py`

Those verifiers must prove:

- diagnostic wiring is explicit
- diagnostic wiring is authority-gated
- diagnostic wiring is not normal runtime default
- diagnostic wiring is not `_run_tick()` default
- diagnostic wiring is read-only
- diagnostic report is metadata-only
- expired metadata is ignored as active
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

- wiring observer directly into `_run_tick()` by default
- wiring observer into `DecisionSelector`
- wiring observer into `ActionScoring`
- wiring observer into `ActionProposer`
- wiring observer into `ModeActionGuard`
- wiring observer into Mode C
- wiring observer into `PolicyPressureReview`
- wiring observer into memory writers
- wiring observer into AKBSM writers
- diagnostic report treated as write approval
- `accepted_for_observation` treated as AKBSM write approval
- `deferred` treated as pending commit
- expired metadata revived by diagnostics
- diagnostics creating proposal storage
- diagnostics creating permanent queues
- diagnostics writing AKBSM or ExpSM
- diagnostics implemented before no-behavior-influence checks

## Consequences

Diagnostic runtime wiring ADR exists as design-only guidance.

Diagnostic runtime wiring is not implemented yet. No runtime source code is
changed. No `_run_tick()` wiring exists. The observer remains unwired from
behavior paths. No real ContextMemory reads/writes exist. No behavior/scoring/
guard influence exists. AKBSM proposal metadata remains non-authoritative for
writes. AKBSM writes remain blocked.

## Next steps

Review this ADR before any controlled diagnostic runtime observation wiring
implementation pass.

The next implementation, if explicitly approved later, should add only an
explicit diagnostic surface with no behavior influence, no `_run_tick()`
default path, no real ContextMemory reads/writes, no storage, no queues, and no
AKBSM/ExpSM writes.
