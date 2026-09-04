# Post-v0.0.2 Safety Architecture Checkpoint

## Status

This is a documentation checkpoint after v0.0.2.

It is not a new runtime release.

This checkpoint is tagged as `v0.0.3`.

## Scope

This checkpoint summarizes post-v0.0.2 safety architecture now present on
`main`. It records what has been designed, what has been scaffolded, what
remains disabled, what is explicitly forbidden, and which verifier/scenario
layers protect the system.

This document does not change runtime behavior, enable Mode C, implement AKBSM
writes, enable AKBSM proposal creation, connect `PolicyPressureReview` to
memory gates, connect any module to AKBSM writers, or add marker 36.

## Baseline

`v0.0.1` = stable prototype baseline.

`v0.0.2` = expanded real-input scenario coverage.

`post-v0.0.2` `main` contains safety architecture additions.

`v0.0.3` marks the post-v0.0.2 safety architecture checkpoint.

## Current runtime guarantees

- default behavior unchanged from before safety scaffolding
- Mode C disabled by default
- Mode C provider no-op by default
- AKBSM writes blocked
- draft proposal scaffold exists
- draft proposal scaffold disabled by default
- draft proposal provider is no-op
- `PolicyPressureReview` observational/disconnected
- marker 36 absent
- ExpSM/AKBSM memory hashes unchanged

Current expected memory hashes:

```text
Memory/ExpSM/ExpSM_data.json:
6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e

Memory/AKBSM/AKBSM_ne.json:
0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd
```

## Mode C state

Design docs exist:

- `docs/adr_behavior_influence_modes.md`
- `docs/design_mode_c_memory_gate_influence.md`
- `docs/adr_mode_c_first_experiment.md`

First experiment ADR exists.

Disabled scaffold exists:

- `clc/runtime/mode_c_advisory.py`

`ModeCMemoryGateAdvisoryProvider` is no-op by default.

Disabled scenario fixtures exist.

No enabled behavior exists.

No gate integration exists.

No scoring/selection influence exists.

`PolicyPressureReview` remains disconnected from behavior and memory gates.

`MemoryWriteReviewModule` remains unchanged by Mode C.

## AKBSM write state

Write-policy ADR exists:

- `docs/adr_akbsm_write_policy.md`

Write-disabled scenarios exist.

Draft proposal design exists:

- `docs/design_akbsm_draft_association_proposal.md`

Draft proposal scaffold exists:

- `clc/runtime/akbsm_draft_proposal.py`
- `tools/verify_akbsm_draft_proposal_scaffold.py`

First enabled draft proposal experiment ADR exists:

- `docs/adr_akbsm_first_enabled_draft_proposal_experiment.md`

AKBSM writes blocked.

AKBSM proposal creation disabled by default.

`AKBSMAssociationProposal` is immutable metadata only.

`commit_allowed` defaults to `False` and `commit_allowed=True` is rejected.

`AKBSMDraftProposalProvider` is no-op by default.

No AKBSM writes exist.

No permanent AKBSM mutation path exists.

The draft proposal design remains design-only for behavior and writes. It does
not approve proposal storage, commit behavior, relation type creation, concept
creation, or writer calls.

The first enabled draft proposal experiment ADR remains design-only. It selects
`AKBSMAssociationProbe` as the only future proposal source, defers
AKBSMAssociationField, forbids behavior, pressure, scoring, action, value,
Mode C, ExpSM, and memory writer sources, keeps the experiment unimplemented,
leaves default runtime unchanged, and keeps AKBSM writes blocked.

## Scenario coverage

Scenario-only coverage groups:

- real-input scenario expansion
- disabled Mode C scenario coverage
- AKBSM write-disabled scenario coverage
- disabled AKBSM draft proposal scenario coverage

Disabled Mode C fixtures:

- `scenarios/mode_c_disabled_no_effect.json`
- `scenarios/mode_c_safe_demo_no_effect.json`
- `scenarios/mode_c_draft_only_metadata_absent.json`
- `scenarios/mode_c_policy_flag_default_no_advisory.json`
- `scenarios/mode_c_pressure_review_still_observational.json`

AKBSM write-disabled fixtures:

- `scenarios/akbsm_write_disabled_no_effect.json`
- `scenarios/akbsm_safe_demo_no_write.json`
- `scenarios/akbsm_draft_only_no_commit.json`
- `scenarios/akbsm_mutating_memory_still_blocked.json`
- `scenarios/akbsm_pressure_review_no_graph_write.json`
- `scenarios/akbsm_repeated_signal_no_association_write.json`

Disabled AKBSM draft proposal fixtures:

- `scenarios/akbsm_draft_proposal_disabled_no_effect.json`
- `scenarios/akbsm_draft_proposal_safe_demo_no_proposal.json`
- `scenarios/akbsm_draft_proposal_draft_only_no_proposal.json`
- `scenarios/akbsm_draft_proposal_mutating_memory_no_proposal.json`
- `scenarios/akbsm_draft_proposal_repeated_signal_no_proposal.json`
- `scenarios/akbsm_draft_proposal_pressure_review_no_proposal.json`

Mode C disabled, AKBSM write-disabled, and disabled AKBSM draft proposal
fixtures are scenario-only coverage. They do not expand phase regression snapshots.

## Verifier coverage

New/important safety architecture verifiers:

- `tools/verify_behavior_influence_adr.py`
- `tools/verify_mode_c_design_doc.py`
- `tools/verify_mode_c_first_experiment_adr.py`
- `tools/verify_mode_c_disabled_scaffold.py`
- `tools/verify_mode_c_disabled_scenarios.py`
- `tools/verify_akbsm_write_policy_adr.py`
- `tools/verify_akbsm_write_disabled_scenarios.py`
- `tools/verify_akbsm_draft_proposal_design.py`
- `tools/verify_akbsm_draft_proposal_scaffold.py`
- `tools/verify_akbsm_draft_proposal_disabled_scenarios.py`
- `tools/verify_akbsm_first_enabled_draft_proposal_adr.py`

Existing core guards:

- `tools/verify_policy_pressure_influence_boundary.py`
- `tools/verify_memory_mutation_policy.py`
- `tools/verify_phase_regression_snapshots.py`
- `tools/verify_phase_level_invariants.py`
- `tools/verify_debug_name_dependency_audit.py`
- `tools/audit_debug_name_dependencies.py`

Important audit facts:

- debug-name audit high-risk findings remain 0
- `legacy_semantic_decision` remains 0

## Memory safety

Safe checks must leave real ExpSM and AKBSM unchanged.

`safe_demo` uses temporary memory and must not mutate real AKBSM.

`draft_only` may allow draft metadata in existing non-AKBSM flows, but must not
commit AKBSM writes.

`mutating_memory` still does not imply AKBSM writes are allowed.

## Forbidden changes without explicit approval

- enabling Mode C
- connecting `PolicyPressureReview` to memory gates
- connecting `ModeCMemoryGateAdvisoryProvider` to `MemoryWriteReviewModule`
  behavior
- allowing Mode C to approve/commit/reject memory writes
- allowing Mode C to affect `DecisionSelector`, `ActionScoring`,
  `ActionProposer`, or `ModeActionGuard`
- implementing AKBSM writes
- enabling AKBSM proposal creation
- committing AKBSM draft proposals
- mutating AKBSM from `PolicyPressureReview`, Mode C, ValueFeedback, or
  `DecisionSelector`
- creating marker 36
- changing ExpSM/AKBSM memory files

## Known limitations

- Mode C scaffold exists but is not wired to behavior.
- AKBSM proposal behavior is design-only; disabled scaffold exists.
- First enabled AKBSM draft proposal experiment is design-only; it selects
  `AKBSMAssociationProbe` only and defers AKBSMAssociationField.
- Disabled scenarios verify no-effect/no-write, not future enabled behavior.
- Phase snapshots were not expanded for disabled scenario-only coverage.
- Remote feature branches may remain as historical PR references.

## Recommended next safe paths

Option A: stop before enabled behavior.

Option B: add disabled AKBSM draft proposal scenario fixtures.

Option C: create a design-only ADR for the first enabled AKBSM draft proposal
experiment.

Option D: prepare v0.0.3 safety checkpoint tag only after explicit approval.

## Release/tag policy

No tag is created by implementation/scaffold passes.

Do not create later checkpoint tags without explicit approval.

Any future tag should follow a clean validation pass, unchanged memory hashes,
cache cleanup, and a reviewed checkpoint/release note.
