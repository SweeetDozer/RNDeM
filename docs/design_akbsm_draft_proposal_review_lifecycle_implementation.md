# Design: AKBSM Draft Proposal Review Lifecycle Implementation Plan

## Status

Implementation plan only.

Runtime lifecycle implementation is limited to a metadata-only
state/record/result scaffold plus a metadata-only transition controller
scaffold.
No proposal storage is added by this pass.
No AKBSM write path is added by this pass.

This document plans a future temporary metadata-only review lifecycle for AKBSM
draft proposals. The first state/record/result scaffold and test/scenario-only
transition controller scaffold exist in `clc/runtime/akbsm_proposal_lifecycle.py`,
but this document does not add review service behavior, transition execution,
proposal storage, proposal persistence, AKBSM writes, ExpSM writes, behavior
influence, Mode C integration, PolicyPressureReview integration, or marker 36.

## Context

`v0.0.7` marks the AKBSM draft proposal review lifecycle ADR checkpoint.
Current `main` has a controlled AKBSM probe draft proposal experiment:
`AKBSMAssociationProbe` can create temporary metadata-only proposals only
through an explicit test/scenario enabled provider path. Normal runtime remains
disabled/no-op, proposal review lifecycle is design-only, no proposal storage
exists, no proposal commit path exists, and AKBSM writes remain blocked.

The lifecycle ADR defines the allowed state vocabulary. This plan defines a
future implementation shape without approving implementation.

## Design goals

- Keep lifecycle records metadata-only.
- Keep proposal review temporary.
- Keep proposal creation scenario/test-only at first.
- Keep `AKBSMAssociationProposal` as the proposal payload.
- Keep `commit_allowed=False`.
- Reject write-like states, transitions, methods, and authorities.
- Preserve normal runtime behavior, tick order, retention timing, and memory
  writer behavior.
- Preserve real ExpSM and AKBSM memory hashes in safety checks.

## Non-goals

- Implement proposal review service behavior.
- Implement lifecycle transition execution.
- Implement proposal storage or persistence.
- Implement or enable AKBSM writes.
- Modify AKBSM or ExpSM.
- Commit AKBSM proposals.
- Create permanent AKBSM associations.
- Create relation types or concepts.
- Connect proposals to behavior, scoring, guards, Mode C, writers, or storage.
- Connect PolicyPressureReview to AKBSM proposals or memory gates.
- Add marker 36.

## Proposed future components

Implemented metadata-only scaffold:

- `AKBSMProposalLifecycleState`
- `AKBSMProposalReviewRecord`
- `AKBSMProposalTransitionResult`
- `AKBSMProposalReviewController`

The controller is test/scenario-only, requires explicit harness authority, and
returns transition result metadata plus a new immutable review record copy only
for allowed transitions.

Required properties:

- metadata-only
- temporary
- no commit/write/persist/apply/mutate methods
- no AKBSM write access
- no ExpSM write access
- no behavior/scoring/guard/Mode C integration

## Proposal lifecycle record

`AKBSMProposalReviewRecord` is metadata-only.

Suggested fields:

- `proposal`
- `state`
- `created_tick`
- `updated_tick`
- `expires_at_tick` or `ttl_ticks`
- `review_reason`
- `review_notes`
- `transition_history`

Rules:

- `proposal` remains `AKBSMAssociationProposal`.
- `state` is metadata-only.
- `transition_history` is metadata-only.
- `accepted_for_observation` is not approval to write.
- expired/rejected proposals cannot be committed.
- `commit_allowed` remains `False`.
- no proposal storage, transition execution, service behavior, or normal
  runtime wiring is added by this scaffold.

## Review controller/service

`AKBSMProposalReviewController`:

- accepts an existing temporary `AKBSMProposalReviewRecord`
- requests allowed metadata-only transitions
- reject forbidden transitions
- returns transition metadata to test/scenario callers
- returns a new immutable record copy only when allowed
- leaves the original record unchanged

A future service layer remains unimplemented.

Forbidden behavior:

- no AKBSM writes
- no ExpSM writes
- no permanent persistence
- no relation type creation
- no concept creation
- no behavior/scoring/guard influence
- no Mode C integration
- no PolicyPressureReview integration

## Allowed state transitions

Allowed transitions:

- `created -> review_pending`
- `review_pending -> accepted_for_observation`
- `review_pending -> deferred`
- `review_pending -> rejected`
- `review_pending -> expired`
- `accepted_for_observation -> expired`
- `deferred -> review_pending`
- `deferred -> expired`
- `rejected -> expired`

All transitions are metadata-only.

## Forbidden state transitions

Forbidden transitions:

- `any state -> AKBSM write`
- `any state -> commit`
- `any state -> apply`
- `any state -> save`
- `any state -> write`
- `any state -> persist`
- `any state -> mutate`
- `accepted_for_observation -> AKBSM write`
- `deferred -> AKBSM write`
- `rejected -> AKBSM write`
- `expired -> AKBSM write`

## Review authority

Allowed first implementation authority:

- explicit test/scenario harness only

Forbidden authorities:

- PolicyPressureReview
- Mode C
- DecisionSelector
- ActionScoring
- ActionProposer
- ModeActionGuard
- ValueFeedback
- ExpSM writers/update paths
- memory writers
- AKBSM writers/save paths
- normal runtime default path

## Temporary storage strategy

Preferred first implementation storage:

- test-local provider/controller return values first

Allowed later temporary storage only if separately approved:

- temporary ContextMemory metadata
- scenario/debug output

Forbidden storage:

- `Memory/AKBSM/*`
- `Memory/ExpSM/*`
- `semantic_core.json`
- `technical_feedback_patterns.json`
- permanent proposal files
- permanent proposal queues
- permanent association files

## Expiration strategy

Future implementation must include bounded lifetime.

Preferred first strategy:

- `ttl_ticks` in review record

Required behavior:

- expired proposals cannot transition to `accepted_for_observation`
- expired proposals cannot be revived into writes
- expired proposals cannot be persisted
- expired proposals may only remain in temporary debug/test output

## Scenario-only enablement strategy

The first lifecycle implementation must remain scenario/test-only:

- normal runtime disabled
- safe_demo default disabled
- draft_only default disabled
- mutating_memory default disabled
- explicit scenario/test flag required

Transition controller scenario coverage exists as metadata-only fixture data in
`scenarios/akbsm_transition_controller_metadata_coverage.json`, verified by
`tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py`. The
coverage proves allowed and forbidden transition behavior while adding no
proposal storage, no ContextMemory storage, no normal runtime wiring, and no
proposal commit/apply/save/write/persist/mutate path.

Temporary ContextMemory metadata integration is covered by the design-only ADR
`docs/adr_akbsm_proposal_contextmemory_metadata_integration.md`. That ADR
allows only a future scenario/test-only temporary metadata copy of proposal
review records; it does not implement ContextMemory integration, proposal
storage, review record persistence, normal runtime wiring, or AKBSM writes.

The current ContextMemory-compatible metadata scaffold lives in
`clc/runtime/akbsm_proposal_contextmemory_metadata.py`. It creates immutable
temporary metadata payloads from review records and optional transition results
for scenario/test use only. It does not write into ContextMemory, call
`ContextMemoryManager`, persist review records, add proposal storage, or wire
the lifecycle into normal runtime.

The same module now includes a scenario/test-only ContextMemory metadata
integration boundary scaffold. It returns a temporary metadata-only deferred
result because no dedicated safe temporary ContextMemory placement API exists
yet. It does not write review records into ContextMemory, does not create
permanent proposal storage or permanent review record persistence, and does not
wire the lifecycle into normal runtime.

The temporary ContextMemory metadata placement API ADR exists in
`docs/adr_contextmemory_temporary_metadata_placement_api.md`. The API is not
implemented yet, current AKBSM proposal ContextMemory integration remains Shape
B/deferred boundary, real ContextMemory placement is still deferred, no
proposal storage exists, no normal runtime wiring exists, and AKBSM writes
remain blocked.

The ContextMemory temporary metadata placement scaffold now exists in
`clc/runtime/context_temporary_metadata.py` for scenario/test use only. It
requires explicit authority, requires TTL/expiration, accepts metadata-only
temporary entries, rejects write-like metadata, remains local-only and unwired,
does not create permanent storage/queues, and keeps AKBSM proposal metadata
non-authoritative for writes.

The AKBSM proposal temporary metadata placement adapter now exists in
`clc/runtime/akbsm_proposal_contextmemory_metadata.py` for scenario/test use
only. It converts proposal review metadata into the generic local temporary
metadata scaffold only under explicit authority with TTL/expiration, rejects
write-like metadata, does not call `ContextMemoryManager`, does not add
proposal storage, and does not wire the lifecycle into normal runtime.

## No-write safety model

The lifecycle should classify temporary proposal metadata only. It must not be
used as a memory write gate, behavior pressure source, scoring input, guard
input, Mode C advisory input, PolicyPressureReview input, ExpSM update source,
or AKBSM writer input.

No lifecycle state should imply approval to write. No transition should call,
prepare, or authorize commit/apply/save/write/persist/mutate behavior.

## Verifier plan

Current verifier:

- `verify_akbsm_draft_proposal_lifecycle_state_scaffold.py`
- `verify_akbsm_draft_proposal_transition_controller_adr.py`
- `verify_akbsm_draft_proposal_transition_controller_scenarios.py`
- `verify_akbsm_proposal_contextmemory_metadata_adr.py`
- `verify_akbsm_proposal_contextmemory_metadata_scaffold.py`
- `verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py`
- `verify_contextmemory_temporary_metadata_placement_api_adr.py`
- `verify_contextmemory_temporary_metadata_placement_scaffold.py`
- `verify_akbsm_proposal_temporary_metadata_placement_adapter.py`

Future verifiers:

- `verify_akbsm_draft_proposal_lifecycle_state_model.py`
- `verify_akbsm_draft_proposal_lifecycle_transitions.py`
- `verify_akbsm_draft_proposal_lifecycle_no_write.py`
- `verify_akbsm_draft_proposal_lifecycle_scenarios.py`
- `verify_akbsm_proposal_contextmemory_metadata_scaffold.py`
- `verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py`
- `verify_akbsm_proposal_contextmemory_metadata_scenarios.py`

They must verify:

- allowed states only
- forbidden write-like states absent
- allowed transitions only
- forbidden transitions rejected
- `accepted_for_observation` is not write approval
- no commit/apply/save/write/persist/mutate methods
- no permanent proposal persistence
- no AKBSM mutation
- no ExpSM mutation
- no behavior/scoring/guard/Mode C integration
- no ContextMemory metadata outside explicit scenario/test-only authority
- marker 36 absent
- memory hashes unchanged

## Scenario plan

Future scenarios:

- proposal enters `review_pending`
- `review_pending -> accepted_for_observation`
- `review_pending -> deferred`
- `review_pending -> rejected`
- `review_pending -> expired`
- `accepted_for_observation -> expired`
- `deferred -> review_pending`
- `deferred -> expired`
- `rejected -> expired`
- forbidden transition to write is rejected
- expired proposal cannot be accepted
- rejected proposal cannot be accepted
- normal runtime still creates no lifecycle records
- disabled proposal fixtures still pass
- controlled probe proposal experiment still passes

## Implementation sequence

Future implementation order:

1. Add metadata-only lifecycle state/record objects. Done as isolated scaffold.
2. Add controller/service with allowed transition table.
3. Add verifier for state model and forbidden states.
4. Add verifier for transition table and forbidden transitions.
5. Add scenario fixtures for created/review_pending/accepted_for_observation/deferred/rejected/expired.
6. Add expiration verifier.
7. Add docs/checkpoint.
8. Only after merge decide whether to tag.

This sequence does not include permanent AKBSM write implementation.

## Rollback/cleanup strategy

The first implementation should be easy to remove:

- keep lifecycle code isolated from runtime wiring
- keep scenario/test enablement explicit
- keep review records as return values before any ContextMemory metadata
- keep no permanent files for proposals
- delete temporary records at scenario/session end
- keep memory hashes unchanged after safety checks

## Rejected implementation shapes

- persistent proposal queue
- automatic lifecycle records in normal runtime
- `accepted_for_observation` enabling writes
- review controller calling AKBSM writer
- review controller calling ExpSM writer
- PolicyPressureReview-controlled lifecycle
- Mode C-controlled lifecycle
- DecisionSelector/ActionScoring-controlled lifecycle
- using marker 36

These shapes are rejected because they introduce persistence, normal-runtime
behavior, write authority, behavior pressure, or marker semantics before the
lifecycle has isolated scenario/test coverage.

## Open questions

- Should the first lifecycle implementation use an enum-like state object or
  string constants?
- Should `ttl_ticks` be mandatory, or should `expires_at_tick` be derived from
  proposal tick plus TTL?
- Should review notes be free-form strings only, or structured reason codes?
- Should temporary ContextMemory metadata remain a later phase after
  test-local provider/controller return values?
- What minimal scenario set should become part of phase regression snapshots,
  if any?

## Transition Controller Experiment ADR

`docs/adr_akbsm_draft_proposal_transition_controller_experiment.md` defines the
first metadata-only transition controller experiment. It is design-only for
storage and runtime wiring: the metadata-only controller scaffold is
implemented, transition execution is not implemented, the controller remains
test/scenario-only, allowed first storage is test-local controller return
values only, no proposal storage/writes/commit path exists, and AKBSM writes
remain blocked.
