# ContextMemory Temporary Metadata Architecture Map

## Status

This document is an architecture map/checkpoint.

It does not introduce new runtime behavior.
It does not authorize `_run_tick()` wiring.
It does not authorize real ContextMemory reads/writes.
It does not authorize proposal storage.
It does not authorize AKBSM/ExpSM writes.
It does not authorize behavior/scoring/guard influence.

Current `main` checkpoint: `eb7fd21 test: harden temporary metadata tick wrapper coverage`.
Latest tag in this ladder: `v0.7.0` = temporary metadata external tick diagnostic wrapper checkpoint.

Companion visualization:
`docs/contextmemory_temporary_metadata_architecture_diagram.md`.

v1 readiness criteria:
`docs/v1_readiness_criteria.md`.

## Scope

This map covers the temporary metadata and AKBSM proposal diagnostic ladder from
`v0.1.0` through `v0.7.0`, plus the post-`v0.7.0` negative/no-behavior
hardening commit `eb7fd21`.

The ladder is local/scaffold-only, explicit-authority-only, metadata-only, and
diagnostic-only after placement. It is not normal runtime default behavior.

## Version timeline

- `v0.1.0` - AKBSM proposal lifecycle test-scenario subsystem checkpoint.
- `v0.2.0` - AKBSM proposal ContextMemory metadata boundary scaffold checkpoint.
- `v0.3.0` - ContextMemory temporary metadata placement scaffold checkpoint.
- `v0.4.0` - AKBSM proposal temporary metadata placement adapter checkpoint.
- `v0.5.0` - temporary metadata read-only observation scaffold checkpoint.
- `v0.6.0` - temporary metadata diagnostic wiring scaffold checkpoint.
- `v0.7.0` - temporary metadata external tick diagnostic wrapper checkpoint.

Post-tag hardening:

- `0924d08` after `v0.4.0` adds negative/retention coverage for temporary metadata placement.
- `14390b7` after `v0.5.0` hardens temporary metadata observation coverage.
- `c418e6d` after `v0.6.0` hardens temporary metadata diagnostic wiring coverage.
- `eb7fd21` after `v0.7.0` hardens external tick wrapper negative/no-behavior coverage.

## Component ladder

1. AKBSM proposal creation / lifecycle / transition controller

- Purpose: represent draft proposal lifecycle state and metadata-only transition results.
- Files: `clc/runtime/akbsm_draft_proposal.py`, `clc/runtime/akbsm_proposal_lifecycle.py`, `docs/adr_akbsm_draft_proposal_review_lifecycle.md`, `docs/adr_akbsm_draft_proposal_transition_controller_experiment.md`, `tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py`.
- Authority required: proposal lifecycle test/scenario authority.
- May do: create immutable proposal/lifecycle metadata for scenario/test paths.
- Must not do: commit, apply, save, write, persist, mutate, store, enqueue, or authorize AKBSM writes.
- Verifier coverage: lifecycle, transition controller, and scenario verifiers.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

2. AKBSM proposal ContextMemory metadata payload scaffold

- Purpose: convert proposal review/lifecycle metadata into temporary metadata payload shape.
- Files: `clc/runtime/akbsm_proposal_contextmemory_metadata.py`, `tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py`.
- Authority required: explicit scenario/test authority.
- May do: return immutable metadata payloads.
- Must not do: call ContextMemory, store review records, or persist proposals.
- Verifier coverage: proposal ContextMemory metadata scaffold verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

3. AKBSM proposal ContextMemory metadata integration boundary, Shape B/deferred boundary

- Purpose: document and encode the deferred boundary before real ContextMemory placement exists.
- Files: `docs/adr_akbsm_proposal_contextmemory_metadata_integration.md`, `clc/runtime/akbsm_proposal_contextmemory_metadata.py`, `tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py`.
- Authority required: explicit scenario/test authority.
- May do: return temporary metadata-only deferred boundary results.
- Must not do: place into real ContextMemory, create proposal storage, or persist review records.
- Verifier coverage: integration scaffold verifier and ADR verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

4. Generic ContextMemory temporary metadata placement scaffold

- Purpose: provide local temporary metadata placement with TTL/expiration.
- Files: `clc/runtime/context_temporary_metadata.py`, `docs/adr_contextmemory_temporary_metadata_placement_api.md`, `tools/verify_contextmemory_temporary_metadata_placement_scaffold.py`.
- Authority required: temporary metadata placement authority `explicit_test_scenario_harness`.
- May do: place metadata-only temporary entries in a local scaffold object.
- Must not do: write real ContextMemory, create permanent storage, or authorize writes.
- Verifier coverage: placement scaffold verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

5. AKBSM proposal temporary metadata placement adapter

- Purpose: adapt AKBSM proposal metadata into the generic local placement scaffold.
- Files: `clc/runtime/akbsm_proposal_contextmemory_metadata.py`, `tools/verify_akbsm_proposal_temporary_metadata_placement_adapter.py`.
- Authority required: adapter scenario/test authority plus valid TTL/expiration.
- May do: place safe metadata into local `ContextTemporaryMetadataPlacement`.
- Must not do: call `ContextMemoryManager`, write real ContextMemory, or approve AKBSM writes.
- Verifier coverage: adapter verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

6. Negative/retention coverage for temporary metadata placement

- Purpose: prove authority rejection, TTL rejection, write-like metadata rejection, and local expiration.
- Files: `scenarios/contextmemory_temporary_metadata_negative_retention_coverage.json`, `tools/verify_contextmemory_temporary_metadata_negative_retention.py`.
- Authority required: verifier-controlled explicit authorities.
- May do: test local scaffold behavior.
- Must not do: mutate real Memory or wire runtime paths.
- Verifier coverage: negative/retention verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

7. Read-only temporary metadata observer

- Purpose: observe active local temporary metadata as diagnostic material.
- Files: `clc/runtime/context_temporary_metadata_observation.py`, `docs/adr_contextmemory_temporary_metadata_runtime_observation.md`, `tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py`.
- Authority required: observation authority `explicit_observation_diagnostic_harness`.
- May do: return read-only observation reports.
- Must not do: treat expired metadata as active or influence behavior.
- Verifier coverage: runtime observation scaffold verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

8. Observer negative/no-behavior coverage

- Purpose: prove observer authority separation and no behavior influence.
- Files: `scenarios/contextmemory_temporary_metadata_runtime_observation_negative_no_behavior.json`, `tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py`.
- Authority required: verifier-controlled observation authority.
- May do: validate diagnostic-only observer reports.
- Must not do: introduce writer commands or instruction fields.
- Verifier coverage: observer negative/no-behavior verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

9. Explicit runtime-facing diagnostic scaffold

- Purpose: wrap the local observer in a runtime-facing diagnostic report under explicit authority.
- Files: `clc/runtime/context_temporary_metadata_diagnostics.py`, `docs/adr_contextmemory_temporary_metadata_diagnostic_wiring.md`, `tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py`.
- Authority required: runtime diagnostic authority `explicit_runtime_diagnostic_harness`.
- May do: build read-only metadata-only diagnostic reports from local placement.
- Must not do: become normal runtime default or call real ContextMemory.
- Verifier coverage: diagnostic wiring scaffold verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

10. Diagnostic wiring negative/no-behavior coverage

- Purpose: prove diagnostic authority separation and no behavior/scoring/guard/Mode C/PolicyPressureReview influence.
- Files: `scenarios/contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.json`, `tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.py`.
- Authority required: verifier-controlled diagnostic authority.
- May do: validate reports and boundaries.
- Must not do: create writer command fields or instruction fields.
- Verifier coverage: diagnostic wiring negative/no-behavior verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

11. Tick diagnostic visibility ADR

- Purpose: decide that tick-facing visibility should start as an external wrapper/harness.
- Files: `docs/adr_contextmemory_temporary_metadata_tick_diagnostic_visibility.md`, `tools/verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py`.
- Authority required: design-only; no runtime authority granted.
- May do: document future constraints.
- Must not do: authorize direct `_run_tick()` hooks.
- Verifier coverage: tick diagnostic visibility ADR verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

12. External tick diagnostic wrapper scaffold

- Purpose: run a provided callable and return behavior output plus a separate diagnostic snapshot.
- Files: `clc/runtime/context_temporary_metadata_tick_diagnostics.py`, `scenarios/contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.json`, `tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py`.
- Authority required: tick diagnostic authority `explicit_tick_diagnostic_harness`.
- May do: call the provided callable with unchanged args/kwargs and separately build diagnostics.
- Must not do: import or call `CLCRuntime._run_tick()` directly, pass diagnostic data into the callable, or change behavior output.
- Verifier coverage: tick diagnostic wrapper scaffold verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

13. External tick wrapper negative/no-behavior coverage

- Purpose: harden the wrapper against authority confusion and behavior influence.
- Files: `scenarios/contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.json`, `tools/verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py`.
- Authority required: verifier-controlled tick diagnostic authority.
- May do: prove direct/wrapped behavior equality and separated diagnostics.
- Must not do: allow placement authority, observation authority, or runtime diagnostic authority to act as tick authority.
- Verifier coverage: tick wrapper negative/no-behavior verifier.
- Normal runtime wiring: no.
- `_run_tick()` touch: no.
- Write authority: no.

## Data flow map

Current allowed flow:

```text
AKBSM proposal lifecycle metadata
-> AKBSM proposal ContextMemory metadata payload
-> AKBSM proposal temporary metadata placement adapter
-> generic local ContextTemporaryMetadataPlacement
-> read-only observer
-> explicit runtime diagnostic provider
-> external tick diagnostic wrapper snapshot
```

This flow is local/scaffold-only, explicit-authority-only, metadata-only,
read-only after placement, not normal runtime default, not `_run_tick()` wiring,
not behavior input, not scoring input, not guard input, not write authority, and
not permanent storage.

## Authority ladder

- Proposal lifecycle test/scenario authority.
- Temporary metadata placement authority: `explicit_test_scenario_harness`.
- AKBSM proposal temporary metadata adapter authority.
- Temporary metadata observation authority: `explicit_observation_diagnostic_harness`.
- Runtime diagnostic authority: `explicit_runtime_diagnostic_harness`.
- Tick diagnostic authority: `explicit_tick_diagnostic_harness`.

Separation rules:

- Placement authority is not observation authority.
- Observation authority is not runtime diagnostic authority unless explicitly documented.
- Runtime diagnostic authority is not tick diagnostic authority unless explicitly documented.
- Tick diagnostic authority is not placement authority.
- No authority in this ladder is AKBSM write authority.
- No authority in this ladder is ExpSM write authority.
- No authority in this ladder is behavior influence authority.

## TTL / expiration model

Temporary placement requires `ttl_ticks` or `expires_at_tick`. Expired metadata
is ignored as active metadata. Optional expired diagnostics may report expired
metadata only as diagnostic material. Expiration never grants pending commit,
write authorization, AKBSM write approval, ExpSM write approval, behavior
influence, scoring influence, guard influence, Mode C influence, or
PolicyPressureReview influence.

## No-write boundaries

- ContextMemory metadata presence is not AKBSM write approval.
- Temporary placement result is not storage approval.
- Observation result is not write approval.
- Runtime diagnostic report is not write approval.
- Tick diagnostic snapshot is not write approval.
- `accepted_for_observation` remains observation-only.
- `deferred` is not pending commit.
- Rejected metadata cannot authorize writes.
- Expired metadata cannot authorize writes.
- `proposal.commit_allowed` remains `False`.
- AKBSM writes remain blocked.
- ExpSM writes remain blocked outside existing allowed policy.

## No-behavior-influence boundaries

None of these are influenced by this ladder:

- `DecisionSelector`
- `ActionScoring`
- `ActionProposer`
- `ModeActionGuard`
- Mode C
- `ModeCMemoryGateAdvisoryProvider`
- `PolicyPressureReview`
- `ValueFeedback`
- memory writers
- AKBSM writers
- ExpSM writers
- normal behavior output path

## Runtime and _run_tick boundaries

No component in this ladder is wired into normal runtime by default.
No component in this ladder modifies `_run_tick()`.
No component in this ladder changes tick order.
No component in this ladder moves `ContextMemoryManager.apply_pending()`.
The external tick diagnostic wrapper accepts a provided callable and does not
import/call `CLCRuntime._run_tick()` directly.
Direct `_run_tick()` diagnostic hook remains deferred.
Any future direct `_run_tick()` hook requires a separate ADR/pass.

## AKBSM proposal lifecycle boundaries

AKBSM proposal lifecycle data is metadata-only. Lifecycle states and transition
results do not create proposal storage, review record persistence, permanent
queues, AKBSM writes, or normal runtime behavior changes.
`accepted_for_observation` is still observation-only. `deferred` is not pending
commit. Rejected and expired metadata remain non-authoritative.

## What exists now

- Lifecycle state/transition controller scaffold.
- Scenario/test-only proposal metadata payloads.
- Shape B deferred ContextMemory metadata boundary.
- Generic local temporary metadata placement scaffold.
- AKBSM proposal adapter into local temporary placement.
- Read-only observer.
- Explicit runtime-facing diagnostic provider.
- External tick diagnostic wrapper.
- Negative/retention/no-behavior coverage for these layers.

## What explicitly does not exist

- No real ContextMemory placement.
- No `ContextMemoryManager` calls.
- No real ContextMemory reads/writes.
- No permanent proposal storage.
- No permanent proposal queue.
- No review record persistence.
- No normal runtime default diagnostics.
- No `_run_tick()` diagnostic hook.
- No behavior/scoring/guard influence.
- No Mode C influence.
- No `PolicyPressureReview` influence.
- No AKBSM write path.
- No ExpSM write path from this subsystem.

## Verifier coverage map

- `verify_akbsm_draft_proposal_transition_controller_scenarios.py`: transition controller scenario coverage and no storage/write paths.
- `verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py`: Shape B deferred boundary, no ContextMemory placement, no persistence.
- `verify_contextmemory_temporary_metadata_placement_scaffold.py`: generic local placement authority, TTL/expiration, no writes.
- `verify_akbsm_proposal_temporary_metadata_placement_adapter.py`: AKBSM proposal adapter into local temporary placement only.
- `verify_contextmemory_temporary_metadata_negative_retention.py`: negative authority/TTL/write-like/expiration coverage.
- `verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py`: read-only observer scaffold and no behavior influence.
- `verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py`: observer negative/no-behavior hardening.
- `verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py`: runtime-facing diagnostic scaffold and no `_run_tick()` wiring.
- `verify_contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.py`: diagnostic authority separation and no behavior influence.
- `verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py`: design-only tick visibility ADR and deferred direct hook.
- `verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py`: external tick wrapper scaffold and behavior output preservation.
- `verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py`: external tick wrapper negative/no-behavior hardening.
- `verify_memory_mutation_policy.py`: real Memory mutation boundaries and unchanged hashes.
- `verify_debug_name_dependency_audit.py`: debug-name audit schema and high-risk finding boundary.

## Scenario coverage map

- `akbsm_transition_controller_metadata_coverage.json`: metadata-only transition controller scenario coverage.
- `akbsm_proposal_contextmemory_metadata_scaffold.json`: proposal ContextMemory metadata payload scaffold coverage.
- `akbsm_proposal_contextmemory_metadata_integration_scaffold.json`: deferred integration boundary coverage.
- `akbsm_proposal_temporary_metadata_placement_adapter.json`: adapter-to-local-placement coverage.
- `contextmemory_temporary_metadata_placement_scaffold.json`: generic local placement scaffold coverage.
- `contextmemory_temporary_metadata_negative_retention_coverage.json`: authority, TTL, write-like, nested instruction, and expiration coverage.
- `contextmemory_temporary_metadata_runtime_observation_scaffold.json`: read-only observer scaffold coverage.
- `contextmemory_temporary_metadata_runtime_observation_negative_no_behavior.json`: observer negative/no-behavior coverage.
- `contextmemory_temporary_metadata_diagnostic_wiring_scaffold.json`: explicit runtime diagnostic scaffold coverage.
- `contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.json`: diagnostic wiring negative/no-behavior coverage.
- `contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.json`: external tick diagnostic wrapper scaffold coverage.
- `contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.json`: external tick wrapper negative/no-behavior coverage.

## Tag/checkpoint map

- `v0.1.0`: AKBSM proposal lifecycle test-scenario subsystem checkpoint.
- `v0.2.0`: AKBSM proposal ContextMemory metadata boundary scaffold checkpoint.
- `v0.3.0`: ContextMemory temporary metadata placement scaffold checkpoint.
- `v0.4.0`: AKBSM proposal temporary metadata placement adapter checkpoint.
- `v0.5.0`: temporary metadata read-only observation scaffold checkpoint.
- `v0.6.0`: temporary metadata diagnostic wiring scaffold checkpoint.
- `v0.7.0`: temporary metadata external tick diagnostic wrapper checkpoint.

## Current safe stopping point

The current safe stopping point is explicit/local/scaffold-only diagnostics up
to an external tick wrapper. The system can produce diagnostic snapshots around
a provided callable, but this is not normal runtime behavior and not
`_run_tick()` wiring. Stopping here preserves maximum safety before any direct
runtime/tick integration.

## Next possible branches

A. Stop here and keep diagnostics external.
B. Add more docs/scenario hardening only.
C. Build a visualization/diagram of the architecture map.
D. Draft a separate ADR for direct `_run_tick()` diagnostic hook, but do not implement it.
E. Draft a separate ADR for real temporary ContextMemory placement, but do not implement it.

## Forbidden next steps

- No direct `_run_tick()` hook without separate ADR and verifier plan.
- No default runtime diagnostic activation.
- No real ContextMemory reads/writes without separate ADR.
- No proposal storage or queues without separate ADR.
- No AKBSM writes without separate ADR, gates, rollback, scenarios, and memory mutation policy update.
- No behavior/scoring/guard influence without separate behavior influence ADR and no-behavior regression plan.
- No Mode C/PolicyPressureReview connection from this subsystem.

## Open questions

- Should future architecture visualization be a static diagram or generated from verifier metadata?
- Should a future direct `_run_tick()` diagnostic hook be rejected permanently or kept as a deferred ADR topic?
- Should real temporary ContextMemory placement be introduced before any runtime-facing hook, or should diagnostics remain external indefinitely?
