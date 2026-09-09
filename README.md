# RNDeM CLC Prototype

Local cognitive loop prototype with a conservative safe-demo runtime, scenario
fixtures, phase regression snapshots, and focused verifier scripts.

Start with:

- `docs/current_architecture_checkpoint.md`
- `docs/adr_behavior_influence_modes.md`
- `docs/design_mode_c_memory_gate_influence.md`
- `docs/adr_mode_c_first_experiment.md`
- `docs/adr_akbsm_write_policy.md`
- `docs/design_akbsm_draft_association_proposal.md`
- `docs/adr_akbsm_first_enabled_draft_proposal_experiment.md`
- `docs/adr_akbsm_draft_proposal_review_lifecycle.md`
- `docs/design_akbsm_draft_proposal_review_lifecycle_implementation.md`
- `docs/adr_akbsm_draft_proposal_transition_controller_experiment.md`
- `docs/adr_akbsm_proposal_contextmemory_metadata_integration.md`
- `docs/post_v0_0_2_safety_architecture_checkpoint.md`
- `docs/phase_regression_snapshots.md`
- `docs/project_hygiene_audit.md`

Useful checks:

```bash
python tools/verify_project_hygiene.py
python tools/verify_behavior_influence_adr.py
python tools/verify_mode_c_design_doc.py
python tools/verify_mode_c_first_experiment_adr.py
python tools/verify_mode_c_disabled_scaffold.py
python tools/verify_mode_c_disabled_scenarios.py
python tools/verify_post_v0_0_2_safety_checkpoint.py
python tools/verify_akbsm_write_policy_adr.py
python tools/verify_akbsm_write_disabled_scenarios.py
python tools/verify_akbsm_draft_proposal_design.py
python tools/verify_akbsm_draft_proposal_scaffold.py
python tools/verify_akbsm_draft_proposal_disabled_scenarios.py
python tools/verify_akbsm_first_enabled_draft_proposal_adr.py
python tools/verify_akbsm_probe_draft_proposal_experiment.py
python tools/verify_akbsm_draft_proposal_review_lifecycle_adr.py
python tools/verify_akbsm_draft_proposal_lifecycle_implementation_plan.py
python tools/verify_akbsm_draft_proposal_lifecycle_state_scaffold.py
python tools/verify_akbsm_draft_proposal_transition_controller_adr.py
python tools/verify_akbsm_draft_proposal_transition_controller_scaffold.py
python tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py
python tools/verify_akbsm_proposal_contextmemory_metadata_adr.py
python tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py
python tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py
python tools/verify_contextmemory_temporary_metadata_placement_api_adr.py
python tools/verify_phase_regression_snapshots.py
python tools/verify_phase_level_invariants.py
python tools/verify_scenario_fixtures.py
```

Mode C has disabled-by-default scaffold only. `PolicyPressureReview` is not
connected to memory gates by default, marker 36 is absent, and future enabled
behavior still requires explicit approval. Disabled Mode C fixtures are
scenario-only coverage and are not added to the phase regression snapshot set.
AKBSM write policy is documented as design-only in
`docs/adr_akbsm_write_policy.md`; AKBSM writes remain blocked by default.
Draft-only AKBSM association proposals now have a disabled-by-default runtime
scaffold in `clc/runtime/akbsm_draft_proposal.py`; the provider is no-op by
default, proposals are metadata-only, and no write path is implemented.
AKBSM write-disabled fixtures are scenario-only coverage and are not added to
the phase regression snapshot set.
Disabled AKBSM draft proposal fixtures are scenario-only coverage for the no-op
provider/scaffold boundary and are not added to the phase regression snapshot
set.
The first enabled draft proposal experiment is documented in
`docs/adr_akbsm_first_enabled_draft_proposal_experiment.md` and exists as a
controlled test/scenario-only provider path: the enabled source is
`AKBSMAssociationProbe` only, AKBSMAssociationField is deferred, behavior,
pressure, scoring, action, value, Mode C, ExpSM, and memory writer sources
remain forbidden, proposal creation remains disabled in normal runtime, and
AKBSM writes remain blocked.
The proposal review lifecycle is design-only in
`docs/adr_akbsm_draft_proposal_review_lifecycle.md`. Lifecycle states are
metadata-only, no lifecycle state means commit/write/persist, review means
classification only, and `accepted_for_observation` is not AKBSM write
approval.
The lifecycle implementation plan is design-only in
`docs/design_akbsm_draft_proposal_review_lifecycle_implementation.md`.
Runtime lifecycle implementation is limited to the metadata-only
state/record/result scaffold in `clc/runtime/akbsm_proposal_lifecycle.py`.
Transition execution, review service behavior, proposal storage, normal runtime
wiring, and storage/writes/commit paths are still not added; proposal creation
remains test/scenario-only and AKBSM writes remain blocked.
The first metadata-only transition controller experiment is design-only in
`docs/adr_akbsm_draft_proposal_transition_controller_experiment.md`. The
metadata-only transition controller scaffold exists, transition execution is
not implemented, the controller is metadata-only and test/scenario-only, allowed
first storage is test-local controller return values only, no proposal
storage/writes/commit path exists, and AKBSM writes remain blocked.
Transition controller scenario coverage exists in
`scenarios/akbsm_transition_controller_metadata_coverage.json`; it is
metadata-only, test/scenario-only, adds no storage or runtime wiring, and keeps
proposal commit/apply/save/write/persist/mutate paths absent.
Future temporary ContextMemory metadata integration is documented as
design-only in `docs/adr_akbsm_proposal_contextmemory_metadata_integration.md`.
No ContextMemory integration is implemented, any first future storage must be
temporary scenario/test-only metadata copies, and AKBSM writes remain blocked.
The scenario/test-only ContextMemory-compatible metadata payload scaffold exists
in `clc/runtime/akbsm_proposal_contextmemory_metadata.py`; it creates immutable
temporary metadata payloads only, does not write into ContextMemory, does not
call `ContextMemoryManager`, adds no proposal storage or review record
persistence, and has no normal runtime wiring.
The scenario/test-only ContextMemory metadata integration scaffold also exists
in `clc/runtime/akbsm_proposal_contextmemory_metadata.py`; because no safe
temporary ContextMemory placement API exists yet, it returns a temporary
metadata-only deferred-boundary result instead of writing review records into
ContextMemory. It adds no permanent proposal storage, no permanent review
record persistence, no proposal commit/apply/save/write/persist/mutate path,
and no normal runtime wiring.
The temporary ContextMemory metadata placement API ADR exists in
`docs/adr_contextmemory_temporary_metadata_placement_api.md`; the API is not
implemented yet, current AKBSM proposal ContextMemory integration remains
Shape B/deferred boundary, real ContextMemory placement is still deferred, no
proposal storage exists, no normal runtime wiring exists, and AKBSM writes
remain blocked.
Current AKBSM proposal ContextMemory integration remains Shape B/deferred boundary.
Post-v0.0.2 safety architecture is summarized in
`docs/post_v0_0_2_safety_architecture_checkpoint.md`; it is tagged as
`v0.0.3` and is not an enabled-behavior runtime release.

Git is configured for this prototype. `main` contains the current baseline and
tags `v0.0.1`, `v0.0.2`, `v0.0.3`, `v0.0.4`, `v0.0.5`, `v0.0.6`, `v0.0.7`,
`v0.0.8`, `v0.0.9`, `v0.0.10`, `v0.0.11`, and `v0.1.0`;
architecture/design branches should be reviewed and merged manually.
