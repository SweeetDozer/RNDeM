# ADR: First AKBSM Draft Proposal Transition Controller Experiment

## Status

This ADR is design-only for storage, runtime wiring, and enabled behavior.

A metadata-only transition controller scaffold is implemented by this pass.
No transition execution is implemented by this pass.
No proposal storage is added by this pass.
No AKBSM write path is added by this pass.

## Context

`v0.0.9` marks the AKBSM proposal lifecycle state scaffold checkpoint.
`AKBSMProposalLifecycleState`, `AKBSMProposalReviewRecord`, and
`AKBSMProposalTransitionResult` exist as metadata-only runtime scaffold.
Allowed transitions exist as metadata only. A metadata-only, test/scenario-only
review controller scaffold can classify requested transitions and return
temporary metadata results. Transition execution, review service behavior,
proposal storage, proposal persistence, AKBSM writes, ExpSM writes, behavior
influence, Mode C integration, and PolicyPressureReview integration are not
implemented.

Current proposal creation remains limited to the explicit test/scenario enabled
`AKBSMAssociationProbe` provider path. Normal runtime does not create proposals
by default, and AKBSM writes remain blocked.

## Decision

The first transition controller experiment may only be metadata-only and
test/scenario-only.

The controller may only classify/request allowed lifecycle transitions by
returning new temporary metadata objects. The controller must not mutate
existing records in place. The controller must not persist records. The
controller must not write AKBSM or ExpSM.

Preferred first controller shape:

- input: `AKBSMProposalReviewRecord` + requested target state + explicit
  test/scenario authority
- output: `AKBSMProposalTransitionResult` + new
  `AKBSMProposalReviewRecord` metadata copy if transition is allowed

In verifier terms, the output includes `AKBSMProposalTransitionResult` plus a
new AKBSMProposalReviewRecord metadata copy when the transition is allowed.

Returning a new metadata record is not storage. Returning a transition result is
not commit. `accepted_for_observation` is not AKBSM write approval. `deferred`
is not pending commit. Rejected or expired records cannot be revived into
writes.

## First Experiment Scope

The first experiment is limited to isolated test/scenario calls that receive an
existing temporary `AKBSMProposalReviewRecord`, check requested state movement
against the allowed transition metadata, and return metadata describing the
outcome.

It must not change normal runtime behavior, default behavior, tick order,
retention timing, `ContextMemoryManager.apply_pending()` placement, memory
writer behavior, scoring, selection, guards, Mode C behavior, or
PolicyPressureReview behavior.

## Controller Responsibility

The scaffold controller may:

- require explicit test/scenario harness authority
- check whether requested transition is in the allowed transition table
- reject forbidden transitions
- create transition result metadata
- create a new immutable review record copy for allowed transitions
- append metadata-only transition history
- expire stale records by returning expired metadata

## Controller Non-Goals

A future controller may not:

- write AKBSM
- write ExpSM
- persist proposals
- persist review records
- create relation types
- create concepts
- change behavior
- change scoring
- affect guards
- affect Mode C
- call memory writers
- call AKBSM writers/save paths

## Allowed Authority

Allowed first authority:

- explicit test/scenario harness only

Normal runtime must not call the controller by default. The normal runtime
default path is not an authority.

## Forbidden Authorities

Forbidden authorities:

- PolicyPressureReview
- Mode C
- ModeCMemoryGateAdvisoryProvider
- DecisionSelector
- ActionScoring
- ActionProposer
- ModeActionGuard
- ValueFeedback
- ExpSM writers/update paths
- memory writers
- AKBSM writers/save paths
- normal runtime default path

## Transition Semantics

All transitions are metadata-only. A transition request can only produce a
report and, if allowed, a new immutable metadata record. It cannot commit,
apply, save, write, persist, mutate, store, or authorize memory changes.

## Allowed Transitions

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

## Forbidden Transitions

Forbidden transitions:

- `any state -> AKBSM write`
- `any state -> commit`
- `any state -> apply`
- `any state -> save`
- `any state -> write`
- `any state -> persist`
- `any state -> mutate`
- `expired -> review_pending`
- `expired -> accepted_for_observation`
- `expired -> deferred`
- `expired -> rejected`
- `expired -> created`
- `rejected -> accepted_for_observation`
- `rejected -> review_pending`
- `accepted_for_observation -> review_pending`
- `accepted_for_observation -> deferred`
- `accepted_for_observation -> rejected`

## Record Handling

`AKBSMProposalReviewRecord` remains immutable. An allowed transition returns a
new metadata record copy. The original record is not mutated. Transition history
remains metadata-only. `AKBSMProposalTransitionResult` is report-only. No
transition result can authorize a write. No lifecycle record can set
`proposal.commit_allowed=True`.

## Expiration Handling

TTL-based expiration may be checked only in the test/scenario path. Expiration
produces expired metadata only. Expired proposals cannot be accepted. Expired
proposals cannot be committed. Expired proposals cannot be persisted. Expired
proposals cannot write AKBSM.

## Storage Policy

Allowed first experiment storage:

- test-local controller return values only

Allowed later only with separate approval:

- temporary ContextMemory metadata
- scenario/debug output

Temporary ContextMemory metadata storage now has a separate design-only ADR:
`docs/adr_akbsm_proposal_contextmemory_metadata_integration.md`. That ADR does
not implement ContextMemory integration, proposal storage, review record
persistence, normal runtime wiring, or AKBSM writes.

Forbidden storage:

- `Memory/AKBSM/*`
- `Memory/ExpSM/*`
- `semantic_core.json`
- `technical_feedback_patterns.json`
- permanent proposal files
- permanent proposal queues
- permanent association files

## No-Write Safety Requirements

The controller experiment must preserve:

- no proposal storage/writes/commit path exists
- no proposal commit/apply/save/write/persist/mutate path exists
- no AKBSM mutation
- no ExpSM mutation
- no permanent AKBSM associations
- no relation type creation
- no concept creation
- no behavior, scoring, guard, Mode C, PolicyPressureReview, ExpSM writer,
  AKBSM writer, or memory writer integration
- marker 36 remains absent
- real ExpSM and AKBSM hashes remain unchanged

## Required Future Scenario Coverage

Future scenarios required before or with implementation:

- controller accepts `created -> review_pending`
- controller accepts `review_pending -> accepted_for_observation`
- controller accepts `review_pending -> deferred`
- controller accepts `review_pending -> rejected`
- controller accepts `review_pending -> expired`
- controller accepts `accepted_for_observation -> expired`
- controller accepts `deferred -> review_pending`
- controller accepts `deferred -> expired`
- controller accepts `rejected -> expired`
- controller rejects `expired -> accepted_for_observation`
- controller rejects `rejected -> accepted_for_observation`
- controller rejects any transition to write/commit/apply/save/persist/mutate
- allowed transition returns new immutable metadata record
- original record is not mutated
- transition result is metadata-only
- no proposal storage is created
- no AKBSM mutation occurs
- no ExpSM mutation occurs
- normal runtime does not call controller by default
- disabled proposal scenarios still pass
- controlled probe proposal experiment still passes

Implemented scenario coverage:

- `scenarios/akbsm_transition_controller_metadata_coverage.json`
- `tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py`

The coverage is metadata-only and test/scenario-only. It verifies allowed
transition requests, forbidden transition rejection, write-like target
rejection, immutable record copy behavior, unchanged original records,
unchanged proposal payloads, metadata-only expiration, absent proposal storage,
absent ContextMemory storage, absent normal runtime wiring, unchanged real
ExpSM/AKBSM hashes, and marker 36 absence.

## Required Future Verifier Coverage

Future verifier expectations:

- verify controller exists only after implementation pass
- verify controller is not imported by normal runtime default path
- verify explicit test/scenario authority is required
- verify allowed transitions only
- verify forbidden transitions rejected
- verify expired/rejected cannot be revived into accepted states
- verify allowed transition returns new immutable record
- verify original record remains unchanged
- verify transition result is metadata-only
- verify no commit/apply/save/write/persist/mutate methods
- verify no proposal storage
- verify no AKBSM mutation
- verify no ExpSM mutation
- verify no behavior/scoring/guard/Mode C integration
- verify marker 36 absent
- verify memory hashes unchanged
- verify controller transition scenario coverage
- verify temporary ContextMemory metadata integration remains design-only until
  a later explicit implementation pass

## Rejected Alternatives

Rejected alternatives:

- controller called by normal runtime by default
- controller connected to PolicyPressureReview
- controller connected to Mode C
- controller connected to DecisionSelector
- controller connected to ActionScoring
- controller connected to ValueFeedback
- controller persisting review records
- controller mutating records in place
- controller writing to ContextMemory in first implementation
- controller writing AKBSM
- `accepted_for_observation` acting as write approval
- expired proposal revival
- rejected proposal revival

These alternatives are rejected because they are too close to behavior
influence, hidden persistence, or permanent memory mutation.

## Consequences

This ADR approves only a metadata-only experiment shape. It adds a
test/scenario-only controller scaffold, but does not add transition execution,
storage, proposal persistence, write approval, or runtime wiring. A later
implementation pass must add verifier and scenario coverage before or with any
storage, ContextMemory metadata, runtime wiring, or enabled behavior.

## Next Steps

Review this ADR before any transition controller storage or runtime integration
pass.

Stop before transition execution, proposal storage, writer wiring, behavior
wiring, Mode C wiring, PolicyPressureReview lifecycle integration, or permanent
AKBSM mutation.
