# ADR: ContextMemory Temporary Metadata Placement API

## Status

This ADR is design-only.

No ContextMemory placement API is implemented by this pass.
No ContextMemory runtime code is changed by this pass.
No proposal metadata is written into ContextMemory by this pass.
No proposal storage is added by this pass.
No AKBSM write path is added by this pass.

## Context

`v0.2.0` marks the AKBSM proposal ContextMemory metadata boundary scaffold
checkpoint. At that checkpoint, the proposal lifecycle test/scenario subsystem
exists, the ContextMemory metadata payload scaffold exists, and the
ContextMemory metadata integration boundary scaffold exists.

The current AKBSM proposal ContextMemory integration remains Shape B/deferred
boundary: existing ContextMemory has no dedicated safe temporary metadata
placement API, so the scaffold returns temporary metadata-only integration
result objects and does not place review records into ContextMemory.

No real ContextMemory placement exists. No `ContextMemoryManager` calls exist.
No proposal storage exists. No review record persistence exists. No permanent
proposal queues exist. No normal runtime wiring exists. AKBSM writes remain
blocked.

## Decision

A future ContextMemory temporary metadata placement API may exist only for
temporary, TTL-bounded, metadata-only entries.

The first implementation must be scenario/test-only.
The API must not create permanent memory.
The API must not create proposal storage.
The API must not persist review records.
The API must not write AKBSM or ExpSM.
The API must not influence behavior/scoring/guards/Mode C.

If existing ContextMemory conventions cannot safely support temporary
metadata/side-list placement without changing runtime behavior, the future
implementation must remain deferred.

Future implementation must remain deferred unless ContextMemory conventions can
safely support temporary metadata/side-list placement.

## First API Scope

Tentative future names only:

- `ContextTemporaryMetadataEntry`
- `ContextTemporaryMetadataPlacementResult`
- `ContextTemporaryMetadataPlacementPolicy`
- `place_temporary_metadata(...)`

Preferred future behavior:

- input: metadata payload plus namespace/source, `ttl_ticks` or
  `expires_at_tick`, and explicit scenario/test authority
- output: placement result metadata
- storage: temporary ContextMemory metadata/side-list only if existing
  ContextMemory conventions safely support it

The first API scope is not normal runtime behavior, proposal storage, review
record persistence, permanent memory, AKBSM write approval, or behavior
influence.

## Allowed Metadata Placement

Allowed metadata categories:

- source
- namespace
- `temporary = true`
- `ttl_ticks` or `expires_at_tick`
- `created_tick`
- `updated_tick`
- payload kind
- payload reference/id metadata
- diagnostic notes

For AKBSM proposal metadata specifically:

- proposal reference metadata
- lifecycle state
- transition result metadata
- review notes/reason
- temporary metadata marker

## Forbidden Data and Operations

Forbidden content:

- full AKBSM association writes
- new relation types
- new concepts
- ExpSM records
- writer commands
- commit/apply/save/write/persist/mutate instructions
- behavior instructions
- scoring instructions
- guard instructions
- Mode C instructions
- PolicyPressureReview instructions

Forbidden operations:

- permanent file write
- proposal queue persistence
- review record persistence
- AKBSM mutation
- ExpSM mutation
- normal runtime behavior influence
- DecisionSelector reads for behavior
- ActionScoring reads for scoring
- ModeActionGuard reads for guarding
- Mode C memory-gate influence

## Authority Model

Allowed first authority:

- explicit scenario/test harness only

Forbidden authorities:

- normal runtime default path
- `_run_tick()`
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

## Retention and Cleanup

Temporary metadata must have TTL or `expires_at_tick`.

Expired metadata must be removable by temporary retention cleanup.
Expired metadata must not trigger writes.
Expired metadata must not trigger controller transitions.
Expired metadata must not become permanent memory.
Cleanup must not move metadata into AKBSM/ExpSM.

Retention cleanup may remove or ignore temporary metadata. Removal, ignoring,
or expiration is not AKBSM write approval and is not a lifecycle transition
unless a later explicit scenario/test-only implementation defines a
metadata-only transition with allowed authority.

## Runtime Boundaries

The future API must not be called by normal runtime default paths.

It must not be wired into `_run_tick()`.
It must not change tick order.
It must not move `ContextMemoryManager.apply_pending()` calls.
It must not change retention timing.
It must not connect proposal metadata to DecisionSelector, ActionScoring,
ActionProposer, ModeActionGuard, Mode C, PolicyPressureReview, memory writers,
or AKBSM writers.

## AKBSM Proposal Integration Boundaries

ContextMemory metadata presence is not AKBSM write approval.
`accepted_for_observation` remains observation-only.
`deferred` is not pending commit.
Rejected/expired metadata cannot authorize writes.

The integration boundary scaffold remains Shape B until a safe placement API
exists. The current boundary returns temporary metadata-only deferred results
and does not place review records into ContextMemory.

## No-Write Safety Requirements

Any future implementation and verifier coverage must prove:

- scenario/test-only authority required
- metadata is temporary
- TTL/expiration required
- no permanent proposal files
- no permanent proposal queues
- no Memory/AKBSM writes
- no Memory/ExpSM writes
- no `semantic_core.json`
- no `technical_feedback_patterns.json`
- no normal runtime wiring
- no `_run_tick()` wiring
- no behavior/scoring/guard/Mode C/PolicyPressureReview influence
- no commit/apply/save/write/persist/mutate path
- marker 36 absent
- memory hashes unchanged

## Required Future Scenarios

Future scenarios:

- scenario/test-only placement accepts temporary metadata with TTL
- missing authority is rejected
- unknown authority is rejected
- metadata without TTL is rejected
- write-like metadata is rejected
- AKBSM proposal metadata can be represented without write approval
- expired metadata is removable/ignored
- normal runtime does not place metadata by default
- no proposal storage files are created
- no permanent proposal queues are created
- AKBSM/ExpSM hashes remain unchanged

## Required Future Verifiers

Future verifiers:

- `verify_contextmemory_temporary_metadata_placement_api_adr.py`
- `verify_contextmemory_temporary_metadata_placement_scaffold.py`
- `verify_contextmemory_temporary_metadata_retention.py`
- `verify_akbsm_proposal_contextmemory_metadata_real_integration_scenarios.py`

They must verify:

- scenario/test-only authority required
- metadata is temporary
- TTL/expiration required
- no permanent proposal files
- no permanent proposal queues
- no Memory/AKBSM writes
- no Memory/ExpSM writes
- no semantic_core.json
- no technical_feedback_patterns.json
- no normal runtime wiring
- no `_run_tick()` wiring
- no behavior/scoring/guard/Mode C/PolicyPressureReview influence
- no commit/apply/save/write/persist/mutate path
- marker 36 absent
- memory hashes unchanged

## Rejected Alternatives

Rejected alternatives:

- using existing ContextMemory primary data as proposal storage
- permanent proposal queue
- proposal metadata created by normal runtime by default
- proposal metadata read by DecisionSelector for behavior
- proposal metadata read by ActionScoring for scoring
- proposal metadata controlled by PolicyPressureReview
- proposal metadata controlled by Mode C
- `accepted_for_observation` treated as write approval
- `deferred` treated as pending commit
- storing full AKBSM associations as ContextMemory metadata
- adding storage before retention rules

These alternatives are rejected because they introduce persistence, write
authority, normal-runtime behavior influence, or permanent memory mutation
before temporary retention and no-write safety are proven.

## Consequences

This ADR narrows the next possible ContextMemory step to a temporary,
TTL-bounded, metadata-only, scenario/test-only placement API.

It does not implement the API. It keeps current AKBSM proposal ContextMemory
integration as Shape B/deferred boundary. Real ContextMemory placement is still
deferred. No proposal storage exists. No normal runtime wiring exists. AKBSM
writes remain blocked.

A later implementation scaffold adds
`clc/runtime/context_temporary_metadata.py` as a scenario/test-only local
temporary metadata placement object. ContextMemory temporary metadata placement
scaffold exists, scaffold is scenario/test-only, scaffold requires explicit
authority, scaffold requires TTL/expiration, scaffold accepts metadata-only
temporary entries, scaffold rejects write-like metadata, scaffold is not wired
into normal runtime, scaffold does not create permanent storage/queues, AKBSM
proposal metadata remains non-authoritative for writes, and AKBSM writes remain
blocked.

A scenario/test-only AKBSM proposal adapter now targets that generic scaffold.
It converts proposal review metadata to local temporary metadata only when
explicit authority and TTL/expiration are present. It does not call
`ContextMemoryManager`, does not write into real ContextMemory, does not create
proposal storage or review record persistence, and does not add normal runtime
wiring.

`docs/adr_contextmemory_temporary_metadata_runtime_observation.md` now records
the next possible runtime observation boundary. That runtime observation ADR
exists as design-only guidance: no runtime observation is implemented, any
future observation must be read-only diagnostic material, no normal runtime
wiring exists, no behavior influence is approved, and AKBSM writes remain
blocked.

## Next Steps

Review this ADR before any implementation pass.

A later explicit implementation pass may add only a disabled
scenario/test-only temporary ContextMemory metadata placement scaffold with
matching scenarios and verifiers. Stop before proposal storage, review record
persistence, permanent queues, normal runtime wiring, behavior influence, or
AKBSM writes.
