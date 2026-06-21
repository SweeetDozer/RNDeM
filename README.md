# RNDeM CLC Prototype

Local cognitive loop prototype with a conservative safe-demo runtime, scenario
fixtures, phase regression snapshots, and focused verifier scripts.

Start with:

- `docs/current_architecture_checkpoint.md`
- `docs/adr_behavior_influence_modes.md`
- `docs/design_mode_c_memory_gate_influence.md`
- `docs/phase_regression_snapshots.md`
- `docs/project_hygiene_audit.md`

Useful checks:

```bash
python tools/verify_project_hygiene.py
python tools/verify_behavior_influence_adr.py
python tools/verify_mode_c_design_doc.py
python tools/verify_phase_regression_snapshots.py
python tools/verify_phase_level_invariants.py
python tools/verify_scenario_fixtures.py
```

Git is configured for this prototype. `main` contains the current baseline and
tags `v0.0.1` and `v0.0.2`; architecture/design branches should be reviewed and
merged manually.
