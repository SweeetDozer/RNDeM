# Phase-level invariants

## Purpose

`tools/verify_phase_level_invariants.py` protects the order-sensitive runtime
semantics that were exposed by the `_run_tick()` helper split. It is a
testing/invariant verifier only. It does not change runtime behavior, scoring,
field decay, memory mutation policy, retention timing, or marker definitions.

Run:

```bash
python tools/verify_phase_level_invariants.py
```

## Covered invariants

- `CLCRuntime` exposes the expected `_phase_00..._phase_11` helper methods.
- `_run_tick()` calls those helpers in ascending phase order.
- `clc/runtime/clc_runtime.py` still contains the documented 62 textual
  `apply_pending(` calls.
- `apply_pending()` calls remain inside phase helpers, preserving commit and
  retention boundary visibility.
- `DecisionSelector` remains before `ExpSMMechanismSearch` in both source order
  and `runtime_phase_map.py`.
- A real audio probe observes same-tick `INTERNAL_DECISION` before
  `EXPSM_MECHANISM_SEARCH`, so mechanism-search candidates remain future
  material rather than current-tick selection material.
- Runtime-only reflection/pressure views remain after behavior phases.
- Scoring, selection, guard, memory gate, `FieldUpdater`, and
  `NeuromodulationModule` behavior modules do not import or use the
  reflection/pressure builders or output types.
- Marker 36 is absent from implementation files.
- Real-input and broader scenario fixtures still pass.

## Relationship to other verifiers

This verifier complements:

- `tools/verify_runtime_tick_phase_map.py`
- `tools/verify_run_tick_phase_split_boundaries.py`
- `tools/verify_run_tick_phase_split_equivalence.py`
- `tools/verify_policy_pressure_influence_boundary.py`
- `tools/verify_phase_regression_snapshots.py`
- `tools/verify_real_input_scenarios.py`
- `tools/verify_scenario_fixtures.py`

The phase-level verifier intentionally reuses the real-input and scenario
fixtures as black-box coverage after its static checks. Exact marker counts are
left to the fixtures only where they are stable; this verifier focuses on phase
ordering and isolation boundaries.
