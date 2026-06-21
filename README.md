# RNDeM CLC Prototype

Local cognitive loop prototype with a conservative safe-demo runtime, scenario
fixtures, phase regression snapshots, and focused verifier scripts.

Start with:

- `docs/current_architecture_checkpoint.md`
- `docs/phase_regression_snapshots.md`
- `docs/project_hygiene_audit.md`

Useful checks:

```bash
python tools/verify_project_hygiene.py
python tools/verify_phase_regression_snapshots.py
python tools/verify_phase_level_invariants.py
python tools/verify_scenario_fixtures.py
```

The current directory contains an empty `.git` directory, but it is not a valid
Git repository. Do not initialize or repair Git state without an explicit
operator decision.
