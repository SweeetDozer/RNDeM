# ADR: ContextMemory Temporary Metadata Runtime Observation

## Status

This ADR is design-only.

No runtime observation is implemented by this pass.
No runtime source code is changed by this pass.
No `_run_tick()` wiring is added by this pass.
No `ContextMemoryManager` call is added by this pass.
No real ContextMemory write is added by this pass.
No proposal storage is added by this pass.
No behavior influence is added by this pass.
No AKBSM write path is added by this pass.

## Context

The temporary metadata placement scaffold is scenario/test-only. It can create
local temporary metadata under explicit authority and TTL/expiration, but it is
not real ContextMemory placement and is not wired into normal runtime.

AKBSM proposal metadata remains non-authoritative. Metadata presence, lifecycle
state, transition result metadata, and observation eligibility do not approve
AKBSM writes.

The next possible design question is whether normal runtime may observe that
temporary metadata exists. This ADR defines that future observation boundary
without implementing it.

## Decision

Future normal-runtime observation of temporary metadata may only expose
temporary metadata as read-only diagnostic/observational material.

The first implementation must not affect decisions, scoring, action proposal,
guards, Mode C, `PolicyPressureReview`, memory writers, AKBSM writers, ExpSM
writers, or feedback.

Observation must not create or imply write approval, permanent memory, persisted
review records, proposal storage, or permanent proposal queues.

## Observation-only principle

Observation means runtime can see/report temporary metadata exists.

Observation does not mean runtime can decide differently, score actions, propose
actions, guard/block actions, commit, apply, save, write, persist, mutate
anything, or become AKBSM/ExpSM memory.

## Allowed future observation surface

The allowed future observation surface is limited to:

- `ContextTemporaryMetadataObservation`
- `ContextTemporaryMetadataObservationView`
- `ContextTemporaryMetadataObservationReport`
- `build_temporary_metadata_observation(...)`

Allowed future content:

- count active entries
- namespaces present
- payload kinds present
- active/expired status
- `ttl_ticks` metadata
- `expires_at_tick` metadata
- diagnostic notes
- proposal lifecycle state metadata only
- transition result metadata only

Forbidden future content:

- full AKBSM association writes
- new relation definitions
- new concepts to insert
- ExpSM records
- writer commands
- behavior instructions
- scoring instructions
- guard instructions
- Mode C instructions
- PolicyPressureReview instructions

## Forbidden runtime influence

Temporary metadata observation must not influence:

- `DecisionSelector`
- `ActionScoring`
- `ActionProposer`
- `ModeActionGuard`
- Mode C
- `ModeCMemoryGateAdvisoryProvider`
- `PolicyPressureReview`
- `ValueFeedback`
- ExpSM writers/update paths
- memory writers
- AKBSM writers/save paths

Observation must not create any commit/apply/save/write/persist/mutate path.

## Authority and activation model

The first future implementation must be explicit scenario/test-only or diagnostic-only.

The normal runtime default path must not automatically observe temporary
metadata until a separate implementation pass approves that surface.

Observation requires explicit observation authority or a diagnostic flag.
Observation authority is not placement authority. Placement authority is not
write authority. Runtime observation authority is not AKBSM write authority.
Placement authority is not write authority.

Forbidden authorities:

- `DecisionSelector`
- `ActionScoring`
- `ActionProposer`
- `ModeActionGuard`
- Mode C
- `ModeCMemoryGateAdvisoryProvider`
- `PolicyPressureReview`
- `ValueFeedback`
- ExpSM writers/update paths
- memory writers
- AKBSM writers/save paths

## TTL/expiration requirements

Runtime observation must ignore expired metadata.

Runtime observation must not revive expired metadata, transition expired metadata,
promote expired metadata to permanent memory, or convert expired metadata into write approval.

Temporary metadata must keep TTL/expiration requirements from the placement
scaffold. Missing TTL, invalid TTL, missing expiration, and invalid expiration
must remain rejected before observation.

## AKBSM proposal metadata boundaries

ContextMemory metadata presence is not AKBSM write approval.

A temporary placement result is not storage approval.

A runtime observation result is not write approval.

`accepted_for_observation` remains observation-only.

`deferred` is not pending commit.

`rejected` cannot authorize writes.

`expired` cannot authorize writes.

`proposal.commit_allowed` remains `False`.

## Runtime wiring boundaries

The first runtime observation implementation, if later approved, must be
read-only and diagnostic-only.

It must not change tick order.

It must not move `ContextMemoryManager.apply_pending()` calls.

It must not feed `DecisionSelector`, `ActionScoring`, `ActionProposer`,
`ModeActionGuard`, Mode C, `PolicyPressureReview`, memory writers, AKBSM
writers, ExpSM writers, or feedback.

It must not alter behavior output.

It must include a verifier proving behavior output is unchanged when
observation is enabled.

## Required future scenarios

Future scenarios must prove:

- observation sees active temporary metadata diagnostically
- observation ignores expired metadata
- missing authority is rejected
- unknown authority is rejected
- observation does not alter behavior output
- observation does not alter `DecisionSelector` inputs
- observation does not alter `ActionScoring` inputs
- observation does not alter `ModeActionGuard` inputs
- observation does not alter Mode C inputs
- observation does not call `PolicyPressureReview`
- observation does not create proposal storage
- observation does not create permanent proposal queues
- observation does not write Memory/AKBSM
- observation does not write Memory/ExpSM
- memory hashes remain unchanged

## Required future verifiers

Future verifier coverage must include:

- `verify_contextmemory_temporary_metadata_runtime_observation_adr.py`
- `verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py`
- `verify_contextmemory_temporary_metadata_runtime_observation_no_behavior_influence.py`
- `verify_akbsm_proposal_temporary_metadata_runtime_observation_scenarios.py`

Those verifiers must prove read-only observation, authority-gated observation,
expired metadata ignored, no default behavior change, no influence on
`DecisionSelector`, `ActionScoring`, `ActionProposer`, `ModeActionGuard`, Mode
C, `PolicyPressureReview`, memory writers, AKBSM writers, ExpSM writers, no
storage, no permanent queues, no Memory/AKBSM writes, no Memory/ExpSM writes,
no `semantic_core.json`, no `technical_feedback_patterns.json`, no
commit/apply/save/write/persist/mutate path, marker 36 absent, and hashes unchanged.

## Rejected alternatives

Rejected alternatives:

- runtime observation directly inside `DecisionSelector`
- runtime observation directly inside `ActionScoring`
- runtime observation directly inside `ActionProposer`
- runtime observation directly inside `ModeActionGuard`
- observation controlled by Mode C
- observation controlled by `PolicyPressureReview`
- observation treated as memory write approval
- `accepted_for_observation` treated as AKBSM write approval
- `deferred` treated as pending commit
- expired metadata revived by observation
- observation creating proposal storage
- observation creating permanent queues
- observation writing AKBSM
- observation writing ExpSM
- observation before no-behavior-influence scenarios

## Consequences

This ADR permits only a future read-only diagnostic observation design. It does
not implement runtime observation, does not implement ContextMemory placement,
does not add normal runtime wiring, does not add storage, and does not add an
AKBSM write path.

AKBSM writes remain blocked. Mode C remains disabled. `PolicyPressureReview`
remains disconnected. Marker 36 remains absent.

A later implementation scaffold adds
`clc/runtime/context_temporary_metadata_observation.py` as an isolated
read-only diagnostic observation object for local temporary metadata placement
state. It requires explicit observation authority, ignores expired metadata as
active metadata, may include expired entries only as diagnostics, returns
metadata-only reports, is not wired into normal runtime or `_run_tick()`, does
not call `ContextMemoryManager`, performs no real ContextMemory writes, and
does not influence behavior/scoring/guards/Mode C/PolicyPressureReview.

Negative/no-behavior coverage now exists for the observer in
`scenarios/contextmemory_temporary_metadata_runtime_observation_negative_no_behavior.json`
and `tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py`.
It covers authority separation, expired metadata active-ignore behavior,
no-writer-command reports, no behavior/scoring/guard/Mode C/PolicyPressureReview
instruction reports, AKBSM proposal metadata remaining non-authoritative for
writes, and no normal runtime or `_run_tick()` observer calls.

`docs/adr_contextmemory_temporary_metadata_diagnostic_wiring.md` now records the
next possible diagnostic runtime wiring boundary. The diagnostic runtime wiring
ADR exists as design-only guidance: diagnostic runtime wiring is not
implemented yet, no `_run_tick()` wiring exists, the observer remains unwired
from behavior paths, no real ContextMemory reads/writes exist, and AKBSM writes
remain blocked.

## Next steps

Review the read-only scenario/test-only ContextMemory temporary metadata
runtime observation scaffold before any normal-runtime wiring is considered.

Any future normal-runtime pass must stay read-only, authority-gated, TTL-aware,
diagnostic-only, and covered by no-behavior-influence scenarios before any
broader runtime observation is considered.
