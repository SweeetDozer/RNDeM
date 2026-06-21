# `_run_tick()` Phase Split Boundaries

Status: accepted / current

## Context

`CLCRuntime._run_tick()` is currently a large order-sensitive runtime pipeline.
The descriptive phase map in `docs/runtime_tick_phase_map.md` records the
current order and its current-tick versus next-tick effects.

Several details are especially sensitive:

- `ContextMemoryManager.apply_pending()` boundaries also define retention
  timing.
- `DecisionSelector` currently runs before `ExpSMMechanismSearch`.
- `ExpSMMechanismSearch` candidates are therefore usually next-tick material.
- The reflection/pressure chain is observational-only.
- `PolicyPressureReview` does not influence behavior.

Current `clc/runtime/clc_runtime.py` contains 62 textual
`apply_pending(` calls. This count is documented as an audit reference, not as a
perfect semantic model.

## Decision

Current policy:

- `_run_tick()` may be split into named helper methods in the future.
- The split must preserve observable behavior.
- The split must preserve all current `ContextMemoryManager.apply_pending()`
  boundaries.
- The split must preserve retention timing.
- The split must preserve `DecisionSelector` versus `ExpSMMechanismSearch`
  ordering.
- The split must preserve the reflection/pressure observational-only boundary.
- The split must preserve marker sequence expectations in scenario fixtures.

The order-preserving helper extraction has now been implemented. This ADR
continues to define the safety boundary for later changes.

## Allowed Future Split

Helper extraction is allowed only if it is order-preserving. Current helper
names:

```python
def _phase_00_input_commit(...): ...
def _phase_01_primary_updates(...): ...
def _phase_02_field_activation_and_consolidation_pressure(...): ...
def _phase_03_action_proposal_and_selection(...): ...
def _phase_04_decision_audit_and_effects(...): ...
def _phase_05_mode_consolidation_memory_chain(...): ...
def _phase_06_outcome_evaluation_akbsm_mechanism(...): ...
def _phase_07_value_feedback(...): ...
def _phase_08_neuromodulation_projection(...): ...
def _phase_09_final_field_refresh(...): ...
def _phase_10_runtime_observation_views(...): ...
def _phase_11_debug_output(...): ...
```

The exact names may evolve only if the same order and invariants remain clear
and verifiable.

## Forbidden Without Explicit ADR

- Moving `DecisionSelector` after `ExpSMMechanismSearch`.
- Moving `ExpSMMechanismSearch` before `DecisionSelector`.
- Moving or removing `ContextMemoryManager.apply_pending()` boundaries.
- Running retention only once at end of tick if current behavior runs it
  multiple times.
- Making reflection/pressure outputs influence scoring, gates, memory,
  `FieldUpdater`, or `NeuromodulationModule`.
- Adding marker 36 for reflection/pressure review without explicit marker ADR.
- Changing field decay timing.
- Changing `ActionCandidateField` refresh timing.
- Changing `ValueFeedbackMemoryView` refresh timing.

## Required Invariants

Any future split must preserve these invariants:

- All existing scenario fixtures pass.
- Reflection/pressure scenario verifiers pass.
- PolicyPressure influence boundary verifier passes.
- Runtime phase map verifier passes.
- Marker sequence expectations remain stable.
- Real ExpSM/AKBSM hashes stay unchanged for safe-demo/test runs.
- No new permanent memory writes appear.
- No marker 36 implementation appears.

## Verification

Run:

```bash
python tools/verify_run_tick_phase_split_boundaries.py
python tools/verify_phase_level_invariants.py
```

The verifier checks that this ADR exists, critical invariants are documented,
the runtime phase map still passes, the PolicyPressure influence boundary still
passes, marker 36 is absent from implementation paths, and scenario verifiers
still pass.

`verify_phase_level_invariants.py` adds deeper AST/source-order checks for the
current helper structure, `_run_tick()` helper order, `apply_pending(` count,
`DecisionSelector` before `ExpSMMechanismSearch`, reflection/pressure isolation,
marker 36 absence, and real-input scenario coverage.

It also reports the current `apply_pending(` count in `clc_runtime.py`. The
check fails if the count is zero and warns if it differs from the documented
reference count of 62.

## Consequences

This ADR makes the future phase split possible without silently changing runtime
control semantics. It also makes the risky edges visible before any helper
extraction starts.

## Future Options

- Tighten phase split equivalence coverage around marker sequence and memory
  hash regression checks.
- Continue scoring/selection semantic migration before splitting.
- Add more real-input scenario coverage before splitting.
- Keep phase-level invariant tests updated when a future ADR deliberately
  changes phase boundaries.
