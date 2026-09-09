# ADR: AKBSM Proposal Temporary ContextMemory Metadata Integration

## Status

This ADR is design-only.

The scenario/test-only ContextMemory-compatible metadata payload scaffold is
implemented. It is not actual ContextMemory integration.

The scenario/test-only integration boundary scaffold is implemented as a
temporary metadata-only deferred result. It is not actual ContextMemory
placement and it does not write review records into ContextMemory.
No ContextMemory integration is implemented by this pass.
No proposal storage is added by this pass.
No review record persistence is added by this pass.
No AKBSM write path is added by this pass.

## Context

`v0.1.0` marks the AKBSM proposal lifecycle test-scenario subsystem checkpoint.
At that checkpoint, proposal creation remains test/scenario-only, lifecycle
state/record/result scaffold exists, the transition controller scaffold exists,
transition controller scenario coverage exists, expiration is metadata-only,
and no proposal storage, ContextMemory storage, normal runtime wiring, or AKBSM
writes exist.

The current transition controller returns test-local metadata objects only. A
future pass may need temporary ContextMemory metadata so scenario/debug tooling
can inspect proposal review records through existing runtime observation
patterns. That future integration needs a narrow ADR before any implementation.

## Decision

The first future ContextMemory integration may only store temporary metadata copies of AKBSM proposal review records.

It must remain scenario/test-only at first.
It must not run in normal runtime by default.
It must not persist proposals.
It must not persist review records.
It must not create permanent proposal queues.
It must not write AKBSM or ExpSM.

ContextMemory presence is not approval to write AKBSM.
`accepted_for_observation` remains observation-only.
`deferred` is not pending commit.
`expired` and `rejected` cannot be revived into writes.

## First Integration Scope

The first integration scope is limited to scenario/test harnesses that already
create temporary proposal review records and transition controller results.
Those harnesses may copy review metadata into temporary ContextMemory metadata
only after a later explicit implementation pass.

The current scaffold creates immutable temporary metadata payload objects only.
It does not write into ContextMemory, does not call `ContextMemoryManager`, and
does not create proposal storage or review record persistence.

Because current `ContextMemory` conventions do not expose a dedicated safe
temporary metadata placement API for proposal review records, the first
integration scaffold is a scenario/test-only boundary object that returns a
temporary metadata-only deferred-placement result. It requires explicit
scenario/test authority, treats `accepted_for_observation` as observation-only,
keeps `deferred` out of pending-commit semantics, and rejects missing or
unknown authority. Real ContextMemory placement remains deferred.

The integration must not change normal runtime behavior, tick order, retention
timing, `ContextMemoryManager.apply_pending()` placement, scoring, selection,
guards, Mode C behavior, PolicyPressureReview behavior, ExpSM writers, memory
writers, or AKBSM writers/save paths.

## Allowed Data Shape

Future ContextMemory metadata may contain only:

- proposal id/reference metadata
- lifecycle state
- `created_tick`
- `updated_tick`
- `ttl_ticks` or `expires_at_tick`
- `review_reason`
- `review_notes`
- transition_history metadata
- controller result metadata
- `source = akbsm_proposal_lifecycle`
- `temporary = true`

Forbidden data:

- full permanent AKBSM association writes
- new relation types
- new concepts
- ExpSM records
- writer commands
- commit/apply/save/write/persist/mutate instructions
- behavior/scoring/guard instructions
- Mode C instructions
- PolicyPressureReview instructions

## ContextMemory Placement Strategy

Preferred first design:

- ContextMemory metadata only, not primary memory data
- temporary side-list or metadata bucket if existing ContextMemory conventions
  support it
- no permanent files
- no Memory/AKBSM writes
- no Memory/ExpSM writes
- no `semantic_core.json`
- no `technical_feedback_patterns.json`

This ADR does not choose an exact `ContextMemory` field or side-list name. A
later implementation pass must inspect current `ContextMemory` conventions and
add the smallest temporary metadata placement that preserves existing retention
and scenario safety checks.

## Lifecycle/Controller Boundaries

The lifecycle state model and transition controller remain metadata-only.

Allowed future ContextMemory metadata must be a copy of lifecycle/controller
review metadata. It must not become the primary proposal object, a proposal
queue, a review service, a write journal, a commit request, or a behavior
signal.

The controller must not read ContextMemory metadata as authority to transition,
commit, apply, save, write, persist, mutate, or approve AKBSM changes.

## Retention and Expiration

Temporary ContextMemory proposal metadata must have TTL/expiration semantics.

Expired metadata must be removable by normal temporary retention cleanup.
Expired metadata must not trigger AKBSM writes.
Expired metadata must not trigger controller transitions.
Expired metadata must not become permanent memory.

Retention cleanup may remove or ignore stale proposal metadata. Removal,
ignoring, or expiration is not a lifecycle transition unless a future
scenario/test harness explicitly requests a metadata-only controller transition
with allowed authority.

## Authority Model

Allowed future first authority:

- explicit scenario/test harness only

Forbidden authorities:

- normal runtime default path
- `_run_tick()`
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

## Non-Goals

This ADR does not approve:

- implementation in this pass
- enabled normal runtime behavior
- proposal storage
- review record persistence
- permanent proposal queues
- proposal commit behavior
- AKBSM writes
- ExpSM writes
- behavior influence
- scoring influence
- guard influence
- Mode C influence
- PolicyPressureReview influence

## Forbidden Integrations

Forbidden integrations:

- controller normal-runtime wiring
- `_run_tick()` wiring
- DecisionSelector reads proposal metadata
- ActionScoring reads proposal metadata
- ActionProposer reads proposal metadata
- ModeActionGuard reads proposal metadata
- Mode C reads proposal metadata
- PolicyPressureReview creates or controls proposal metadata
- memory writers create proposal metadata by default
- AKBSM writers/save paths consume proposal metadata
- ExpSM writers/update paths consume proposal metadata
- commit/apply/save/write/persist/mutate path

## No-Write Safety Requirements

Any future implementation must verify:

- integration is scenario/test-only
- metadata is temporary
- no permanent proposal files
- no Memory/AKBSM writes
- no Memory/ExpSM writes
- no `semantic_core.json`
- no `technical_feedback_patterns.json`
- no controller normal-runtime wiring
- no `_run_tick()` wiring
- no commit/apply/save/write/persist/mutate path
- marker 36 absent
- memory hashes unchanged

## Required Future Scenario Coverage

Future scenario coverage must include:

- scenario-only proposal review record can be represented as temporary
  ContextMemory metadata
- metadata contains lifecycle state and TTL
- metadata does not contain write/commit/persist instructions
- `accepted_for_observation` metadata does not authorize AKBSM write
- expired metadata is removed or ignored by retention
- normal runtime does not create ContextMemory proposal metadata by default
- controller scenarios still pass
- memory mutation policy still blocks AKBSM writes

## Required Future Verifier Coverage

Future verifiers:

- `verify_akbsm_proposal_contextmemory_metadata_adr.py`
- `verify_akbsm_proposal_contextmemory_metadata_scaffold.py`
- `verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py`
- `verify_akbsm_proposal_contextmemory_metadata_scenarios.py`

They must verify:

- integration is scenario/test-only
- metadata is temporary
- no permanent proposal files
- no Memory/AKBSM writes
- no Memory/ExpSM writes
- no `semantic_core.json`
- no `technical_feedback_patterns.json`
- no controller normal-runtime wiring
- no `_run_tick()` wiring
- no commit/apply/save/write/persist/mutate path
- marker 36 absent
- memory hashes unchanged

## Rejected Alternatives

Rejected alternatives:

- permanent proposal queue
- ContextMemory metadata created by normal runtime by default
- ContextMemory metadata treated as write approval
- `accepted_for_observation` triggering AKBSM writes
- `deferred` treated as pending commit
- PolicyPressureReview-controlled ContextMemory metadata
- Mode C-controlled ContextMemory metadata
- DecisionSelector/ActionScoring reading proposal metadata for behavior
- storing full AKBSM associations in ContextMemory

These alternatives are rejected because they would add hidden persistence,
normal-runtime behavior, write authority, behavior influence, or permanent
memory mutation before the proposal lifecycle has an explicit storage design and
dedicated no-write scenario coverage.

## Consequences

This ADR narrows the next possible storage step to temporary ContextMemory
metadata copies only. It keeps current proposal creation test/scenario-only and
keeps lifecycle/controller output metadata-only.

A later implementation pass must add the temporary metadata scaffold and
scenario coverage together. It must keep normal runtime disabled by default,
preserve memory hashes, and prove that ContextMemory metadata cannot approve or
trigger AKBSM writes.

## Next Steps

Review this ADR before any ContextMemory proposal metadata implementation pass.

The next implementation, if explicitly approved later, should add only a
scenario/test-only temporary ContextMemory metadata scaffold and matching
scenario/verifier coverage. Stop before permanent proposal queues, review record
persistence, normal runtime wiring, behavior influence, or AKBSM writes.

Before real placement, review
`docs/adr_contextmemory_temporary_metadata_placement_api.md`. That temporary
ContextMemory metadata placement API ADR exists as design-only guidance: the
API is not implemented yet, current AKBSM proposal ContextMemory integration
remains Shape B/deferred boundary, real ContextMemory placement is still
deferred, no proposal storage exists, no normal runtime wiring exists, and
AKBSM writes remain blocked.

`clc/runtime/context_temporary_metadata.py` now provides a scenario/test-only
ContextMemory temporary metadata placement scaffold. It requires explicit
authority and TTL/expiration, accepts metadata-only temporary entries, rejects
write-like metadata, remains local-only, is not wired into normal runtime, does
not create permanent storage/queues, and does not make AKBSM proposal metadata
authoritative for writes.
