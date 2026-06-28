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
python tools/verify_akbsm_write_policy_adr.py
python tools/verify_akbsm_write_disabled_scenarios.py
python tools/verify_akbsm_draft_proposal_design.py
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
Draft-only AKBSM association proposals are documented as design-only in
`docs/design_akbsm_draft_association_proposal.md`; no proposal object or write
path is implemented.
AKBSM write-disabled fixtures are scenario-only coverage and are not added to
the phase regression snapshot set.

Git is configured for this prototype. `main` contains the current baseline and
tags `v0.0.1` and `v0.0.2`; architecture/design branches should be reviewed and
merged manually.
