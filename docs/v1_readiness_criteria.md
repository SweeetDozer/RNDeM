# v1.0.0 Readiness Criteria

## Status

This document defines readiness criteria for `v1.0.0`.

It does not introduce runtime behavior.
It does not authorize `_run_tick()` wiring.
It does not authorize real ContextMemory reads/writes.
It does not authorize proposal storage.
It does not authorize AKBSM/ExpSM writes.
It does not authorize behavior/scoring/guard influence.

## Scope

This document defines the criteria for a stable safety-bounded RNDeM CLC
prototype checkpoint. It is a release-boundary document, not an implementation
plan.

The scope is the current documented architecture, verifier coverage, memory
safety, runtime invariants, and known forbidden paths before tagging `v1.0.0`.

## Meaning of v1.0.0

`v1.0.0` means a stable safety-bounded RNDeM CLC prototype checkpoint.

`v1.0.0` freezes the current safe architecture boundaries for review.

`v1.0.0` is a point to stop, review the full architecture, discuss what was
built, and decide the next direction.

## What v1.0.0 is not

- `v1.0.0` is not AGI.
- `v1.0.0` is not autonomous self-modification.
- `v1.0.0` is not permission for AKBSM writes.
- `v1.0.0` is not permission for ExpSM writes beyond existing memory policy.
- `v1.0.0` is not permission for real ContextMemory placement.
- `v1.0.0` is not permission for permanent proposal storage.
- `v1.0.0` is not permission for proposal queues.
- `v1.0.0` is not permission for direct `_run_tick()` diagnostic hook.
- `v1.0.0` is not permission for default runtime diagnostics.
- `v1.0.0` is not permission for behavior/scoring/guard influence.

## Current baseline

- `main` HEAD after visualization merge: `fbef338 docs: visualize temporary metadata diagnostic architecture`.
- Latest tag: `v0.8.0`.
- `v0.8.0` marks the temporary metadata diagnostic architecture map checkpoint.
- Post-`v0.8.0` visualization document is merged.

## Required architecture state

- `_run_tick()` remains mechanically split and behavior-stable.
- Memory mutation policy remains explicit.
- `safe_demo` remains safe by default.
- `CLCRuntime("Memory")` remains safe by default.
- `DecisionSelector` remains before `ExpSMMechanismSearch`.
- `ExpSMMechanismSearch` candidates remain next-tick material.
- `PolicyPressureReview` remains observational-only and disconnected from behavior.
- Mode C remains disabled/unwired unless explicitly enabled by existing safe scaffold.
- AKBSM writes remain blocked.
- ContextMemory temporary metadata ladder remains local/scaffold-only.
- External tick diagnostic wrapper remains outside `_run_tick()`.
- Direct `_run_tick()` diagnostic hook remains deferred.
- No real ContextMemory reads/writes are added.
- No proposal persistence or queues are added.

## Required safety boundaries

- No runtime default diagnostic activation.
- No direct `_run_tick()` diagnostic hook.
- No tick order changes.
- No `ContextMemoryManager.apply_pending()` timing changes.
- No `ContextMemoryManager` calls from the temporary metadata diagnostic ladder.
- No real ContextMemory reads/writes.
- No permanent proposal storage.
- No permanent proposal queues.
- No review record persistence.
- No Memory/AKBSM writes.
- No Memory/ExpSM writes from this subsystem.
- No `semantic_core.json`.
- No `technical_feedback_patterns.json`.
- No behavior/scoring/guard influence.
- No Mode C influence from this subsystem.
- No `PolicyPressureReview` influence from this subsystem.
- No diagnostics-as-write-authority.
- No marker 36.

## Required verifier coverage

Required verifier families:

- memory mutation policy verifiers
- decay semantics verifiers
- retention policy verifiers
- real-input scenario verifiers
- behavior influence ADR verifiers
- AKBSM write-disabled verifiers
- AKBSM draft proposal verifiers
- AKBSM proposal lifecycle/transition controller verifiers
- ContextMemory metadata boundary verifiers
- temporary metadata placement verifiers
- AKBSM proposal temporary metadata adapter verifiers
- temporary metadata negative/retention verifiers
- read-only observation verifiers
- observation negative/no-behavior verifiers
- diagnostic wiring verifiers
- diagnostic wiring negative/no-behavior verifiers
- tick diagnostic visibility ADR verifier
- external tick diagnostic wrapper verifier
- external tick wrapper negative/no-behavior verifier
- architecture map verifier
- architecture diagram verifier
- debug-name dependency audit verifier
- scenario fixture verifier
- `main.py` smoke run

## Required scenario coverage

Required scenario coverage includes:

- real-input audio/sensor/value/guard regression fixtures
- retention and side-list retention fixtures
- Mode C disabled/no-effect fixtures
- AKBSM write-disabled fixtures
- AKBSM draft proposal disabled/default/no-write fixtures
- AKBSM controlled probe draft proposal fixtures
- AKBSM proposal lifecycle and transition controller fixtures
- AKBSM proposal ContextMemory metadata scaffold fixtures
- AKBSM proposal temporary metadata placement adapter fixtures
- ContextMemory temporary metadata placement scaffold fixtures
- ContextMemory temporary metadata negative/retention fixtures
- read-only observation scaffold fixtures
- observation negative/no-behavior fixtures
- diagnostic wiring scaffold fixtures
- diagnostic wiring negative/no-behavior fixtures
- external tick diagnostic wrapper scaffold fixtures
- external tick wrapper negative/no-behavior fixtures

## Required memory invariants

Expected real memory hashes:

```text
Memory/ExpSM/ExpSM_data.json:
6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e

Memory/AKBSM/AKBSM_ne.json:
0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd
```

`v1.0.0` cannot be tagged if these hashes change unexpectedly.
Any intentional memory hash change before `v1.0.0` requires a separate ADR/pass
and explicit approval.

## Required runtime invariants

- `apply_pending` count remains 62 unless separately approved.
- marker 36 remains absent.
- `legacy_semantic_decision` remains 0.
- `semantic_decision_needs_migration` remains 0.
- `unknown_runtime_logic` remains 0.
- `ambiguous_runtime_logic` remains 1 and remains demo/display-only.
- debug-name high-risk findings remain 0.

## Required documentation

Required documents for `v1.0.0`:

- `README.md`
- `docs/current_architecture_checkpoint.md`
- `docs/post_v0_0_2_safety_architecture_checkpoint.md`
- `docs/project_hygiene_audit.md`
- `docs/contextmemory_temporary_metadata_architecture_map.md`
- `docs/contextmemory_temporary_metadata_architecture_diagram.md`
- `docs/v1_readiness_criteria.md`
- `docs/v1_release_checklist.md`
- behavior influence, Mode C, AKBSM write policy, AKBSM proposal lifecycle,
  ContextMemory temporary metadata, diagnostic wiring, and tick visibility ADRs

## Required release validation

A `v1.0.0` release candidate must run focused validation plus this release
checklist. Required command group:

```bash
python tools/clean_pycache.py
python tools/verify_v1_release_candidate.py
python tools/verify_v1_readiness_criteria.py
python tools/verify_contextmemory_temporary_metadata_architecture_diagram.py
python tools/verify_contextmemory_temporary_metadata_architecture_map.py
python tools/verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py
python tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py
python tools/verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py
python tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.py
python tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py
python tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py
python tools/verify_contextmemory_temporary_metadata_negative_retention.py
python tools/verify_scenario_fixtures.py
python tools/verify_memory_mutation_policy.py
python tools/verify_debug_name_dependency_audit.py
python tools/audit_debug_name_dependencies.py
python -B main.py
```

A final `v1.0.0` release pass may run broader/full validation if available.

The release-candidate checklist in `docs/v1_release_checklist.md` documents the
final blockers, stop-and-review procedure, and future tag command. It does not
tag `v1.0.0`; tagging requires a separate reviewed pass on `main`.

## Allowed pre-v1 work

- docs cleanup
- architecture checklist
- release checklist verifier
- scenario/verifier coverage consolidation
- README release notes
- final safety checkpoint documentation
- optional generated architecture summary

## Forbidden pre-v1 work

Forbidden before `v1.0.0` unless a separate explicit decision is made:

- direct `_run_tick()` hook
- default runtime diagnostic activation
- real ContextMemory placement
- `ContextMemoryManager` calls
- proposal storage
- proposal queues
- review record persistence
- AKBSM writes
- ExpSM writes from this subsystem
- Mode C/`PolicyPressureReview` influence from this subsystem
- behavior/scoring/guard influence
- memory hash changes

## v1.0.0 release checklist

- architecture map exists
- architecture diagram exists
- v1 readiness criteria exists
- current architecture checkpoint is up to date
- post-v0.0.2 safety checkpoint is up to date
- project hygiene audit is up to date
- debug-name audit high-risk findings are 0
- marker 36 absent
- no `semantic_core.json`
- no `technical_feedback_patterns.json`
- no `__pycache__` or `.pyc` files
- memory hashes match expected values
- focused validation passes
- `main.py` smoke run passes
- final git status clean
- v1 tag points at reviewed main

## Post-v1 review plan

After `v1.0.0` is tagged, stop feature work.

Review the full architecture.
Review what was built.
Review what remains forbidden.
Review whether temporary metadata should remain external only.
Review whether real ContextMemory placement is needed.
Review whether any direct `_run_tick()` diagnostic hook is justified.
Review whether AKBSM writes should remain blocked.
Decide next roadmap only after that review.

Post-v1 architecture documents may be added after the review checkpoint without
rewriting v1 history. `docs/natural_pattern_data_contract.md` is one such
post-v1 design contract: it defines natural activation patterns as the future
data substrate and preserves all v1 safety boundaries until a separate approved
implementation pass exists.

## Open questions after v1.0.0

- Should temporary metadata stay permanently external/scaffold-only?
- Is real temporary ContextMemory placement needed, or is local diagnostic scaffolding sufficient?
- Is any direct `_run_tick()` diagnostic hook justified after review?
- Should AKBSM writes remain blocked indefinitely?
- Which scenario families should be consolidated before any post-v1 runtime work?
