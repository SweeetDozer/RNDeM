# v1.0.0 Release Checklist

## Status

This document is the final v1.0.0 release checklist.

It does not introduce runtime behavior.
It does not authorize _run_tick wiring.
It does not authorize real ContextMemory reads/writes.
It does not authorize proposal storage.
It does not authorize AKBSM/ExpSM writes.
It does not authorize behavior/scoring/guard influence.

This checklist is a pre-v1 release-candidate artifact. It is not the v1.0.0
tag itself.

## Scope

This checklist covers the release-candidate state for a stable safety-bounded
RNDeM CLC prototype checkpoint. It records required documents, architecture
boundaries, runtime boundaries, memory boundaries, diagnostic boundaries,
verifier coverage, validation commands, tag preconditions, release blockers,
and the stop-and-review procedure.

## Release meaning

v1.0.0 means a stable safety-bounded RNDeM CLC prototype checkpoint.
v1.0.0 is a stop-and-review point.
v1.0.0 freezes the current safety boundaries for architectural review.

## Release exclusions

- v1.0.0 is not AGI.
- v1.0.0 is not autonomous self-modification.
- v1.0.0 is not permission for AKBSM writes.
- v1.0.0 is not permission for ExpSM writes beyond existing policy.
- v1.0.0 is not permission for real ContextMemory placement.
- v1.0.0 is not permission for permanent proposal storage.
- v1.0.0 is not permission for proposal queues.
- v1.0.0 is not permission for direct _run_tick diagnostic hook.
- v1.0.0 is not permission for default runtime diagnostics.
- v1.0.0 is not permission for behavior/scoring/guard influence.

## Current expected baseline

- main HEAD before this branch: `aabeb65 docs: define v1 readiness criteria`.
- Latest architecture checkpoint tag: `v0.8.0`.
- `v0.8.0` marks the temporary metadata diagnostic architecture map checkpoint.
- Post-`v0.8.0` commits include architecture visualization and v1 readiness
  criteria.
- This release checklist commit is a pre-v1 release-candidate artifact and not
  the v1 tag itself.

## Required tags and history

- `v0.8.0` remains the latest architecture checkpoint before the v1
  release-candidate checklist.
- `v1.0.0` must not already exist before the final tag pass.
- `v1.0.0` may only point at reviewed `main` after this release checklist
  branch is reviewed, merged, and validated.

## Required documents

These documents must exist before v1.0.0:

- `README.md`
- `docs/v1_readiness_criteria.md`
- `docs/v1_release_checklist.md`
- `docs/contextmemory_temporary_metadata_architecture_map.md`
- `docs/contextmemory_temporary_metadata_architecture_diagram.md`
- `docs/current_architecture_checkpoint.md`
- `docs/post_v0_0_2_safety_architecture_checkpoint.md`
- `docs/project_hygiene_audit.md`
- `docs/adr_behavior_influence_modes.md`
- `docs/adr_akbsm_write_policy.md`
- `docs/adr_contextmemory_temporary_metadata_tick_diagnostic_visibility.md`

## Required architecture boundaries

- `_run_tick` remains mechanically split and behavior-stable.
- `DecisionSelector` remains before `ExpSMMechanismSearch`.
- `ExpSMMechanismSearch` candidates remain next-tick material.
- `PolicyPressureReview` remains observational-only and disconnected from
  behavior.
- Mode C remains disabled/unwired unless explicitly enabled by existing safe
  scaffold.
- AKBSM writes remain blocked.
- ContextMemory temporary metadata ladder remains local/scaffold-only.
- External tick diagnostic wrapper remains outside `_run_tick`.
- Direct `_run_tick` diagnostic hook remains deferred.
- No real ContextMemory reads/writes are added.
- No proposal persistence or queues are added.

## Required runtime boundaries

- No runtime default diagnostic activation.
- No direct `_run_tick` diagnostic hook.
- No tick order changes.
- No `ContextMemoryManager.apply_pending` timing changes.
- No `ContextMemoryManager` calls from the temporary metadata diagnostic ladder.
- No diagnostics-as-behavior-input.
- No diagnostics-as-scoring-input.
- No diagnostics-as-guard-input.
- No diagnostics-as-write-authority.
- No marker 36.

## Required memory boundaries

- No Memory/AKBSM writes.
- No Memory/ExpSM writes from this subsystem.
- No `semantic_core.json`.
- No `technical_feedback_patterns.json`.
- No permanent proposal storage.
- No permanent proposal queues.
- No review record persistence.

Expected real memory hashes:

```text
Memory/ExpSM/ExpSM_data.json:
6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e

Memory/AKBSM/AKBSM_ne.json:
0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd
```

## Required diagnostic boundaries

- temporary metadata placement is local/scaffold-only
- temporary metadata observation is read-only
- runtime diagnostics are explicit-only
- external tick diagnostic wrapper accepts a provided callable only
- external tick diagnostic wrapper does not import/call `CLCRuntime._run_tick`
  directly
- external tick diagnostic wrapper returns `behavior_output` unchanged
- external tick diagnostic wrapper returns `diagnostic_snapshot` separately
- `diagnostic_snapshot` is not write approval
- `accepted_for_observation` remains observation-only
- `deferred` is not pending commit
- rejected/expired do not authorize writes
- `proposal.commit_allowed` remains False

## Required verifier families

These important verifier families must exist:

- `tools/verify_v1_readiness_criteria.py`
- `tools/verify_v1_release_candidate.py`
- `tools/verify_contextmemory_temporary_metadata_architecture_diagram.py`
- `tools/verify_contextmemory_temporary_metadata_architecture_map.py`
- `tools/verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py`
- `tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py`
- `tools/verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py`
- `tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.py`
- `tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py`
- `tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_adr.py`
- `tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py`
- `tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py`
- `tools/verify_contextmemory_temporary_metadata_runtime_observation_adr.py`
- `tools/verify_contextmemory_temporary_metadata_negative_retention.py`
- `tools/verify_akbsm_proposal_temporary_metadata_placement_adapter.py`
- `tools/verify_contextmemory_temporary_metadata_placement_scaffold.py`
- `tools/verify_contextmemory_temporary_metadata_placement_api_adr.py`
- `tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py`
- `tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py`
- `tools/verify_scenario_fixtures.py`
- `tools/verify_memory_mutation_policy.py`
- `tools/verify_debug_name_dependency_audit.py`
- `tools/audit_debug_name_dependencies.py`

## Required scenario families

These scenario families must remain covered:

- real-input audio/sensor/value/guard scenarios
- retention and observation-view scenarios
- Mode C disabled/no-effect scenarios
- AKBSM write-disabled/no-write scenarios
- AKBSM draft proposal disabled/default/no-write scenarios
- controlled AKBSM probe draft proposal scenarios
- AKBSM proposal lifecycle and transition controller scenarios
- AKBSM proposal ContextMemory metadata scaffold scenarios
- AKBSM proposal temporary metadata placement adapter scenarios
- ContextMemory temporary metadata placement scaffold scenarios
- ContextMemory temporary metadata negative/retention scenarios
- temporary metadata observation negative/no-behavior scenarios
- temporary metadata diagnostic wiring scenarios
- external tick diagnostic wrapper scenarios

## Required release-candidate validation

Required command group:

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
python tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_adr.py
python tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py
python tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py
python tools/verify_contextmemory_temporary_metadata_runtime_observation_adr.py
python tools/verify_contextmemory_temporary_metadata_negative_retention.py
python tools/verify_akbsm_proposal_temporary_metadata_placement_adapter.py
python tools/verify_contextmemory_temporary_metadata_placement_scaffold.py
python tools/verify_contextmemory_temporary_metadata_placement_api_adr.py
python tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py
python tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py
python tools/verify_scenario_fixtures.py
python tools/verify_memory_mutation_policy.py
python tools/verify_debug_name_dependency_audit.py
python tools/audit_debug_name_dependencies.py
python -B main.py
```

## Required final tag procedure

`v1.0.0` may only be tagged after:

- this release checklist branch is reviewed
- this release checklist branch is merged into main
- release-candidate validation passes on main
- memory hashes match expected values
- working tree is clean
- no `v1.0.0` tag already exists

Future tag command only:

```bash
git tag -a v1.0.0 -m "Stable safety-bounded RNDeM CLC prototype checkpoint"
git push origin v1.0.0
```

Do not run this command in this pass.

## Stop-and-review procedure after v1.0.0

After v1.0.0 is tagged:

- stop feature work
- review the full architecture map and diagram
- review v1 readiness criteria
- review v1 release checklist
- review what exists and what explicitly does not exist
- review all forbidden paths
- decide next roadmap only after discussion

Post-v1 design-only contracts may be created after this checkpoint. The Natural
Pattern Data Contract is allowed only as architecture documentation/verifier
work: it must not enable sensory adapters, pattern-processing implementation,
real ContextMemory placement, AKBSM writes, direct `_run_tick()` hooks, default
diagnostics, or behavior influence.

## Release blocker list

- dirty working tree
- failed verifier
- failed `python -B main.py`
- `__pycache__` or `.pyc` left behind
- Memory/AKBSM hash mismatch
- Memory/ExpSM hash mismatch
- marker 36 present
- debug-name high-risk findings > 0
- `semantic_core.json` exists
- `technical_feedback_patterns.json` exists
- direct `_run_tick` diagnostic hook present
- default runtime diagnostic activation present
- real ContextMemory reads/writes present
- proposal storage/queues present
- AKBSM write path present
- behavior/scoring/guard influence present
- Mode C/PolicyPressureReview influence from this subsystem present

## Final checklist

- [ ] main is up to date with origin/main
- [ ] release checklist branch is merged
- [ ] release-candidate verifier passes
- [ ] focused validation passes
- [ ] py_compile passes for new verifier
- [ ] python -B main.py passes
- [ ] git diff --check clean
- [ ] cache cleanup leaves 0 __pycache__ dirs and 0 .pyc files
- [ ] Memory/ExpSM hash matches expected
- [ ] Memory/AKBSM hash matches expected
- [ ] marker 36 absent
- [ ] debug-name high-risk findings are 0
- [ ] semantic_core.json absent
- [ ] technical_feedback_patterns.json absent
- [ ] no runtime source changes in release checklist pass
- [ ] no _run_tick hook/default runtime diagnostics
- [ ] no real ContextMemory placement
- [ ] no AKBSM/ExpSM writes
- [ ] v1.0.0 tag does not already exist
- [ ] v1.0.0 tag points at reviewed main
