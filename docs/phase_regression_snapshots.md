# Phase regression snapshots

## Purpose

Phase regression snapshots are compact JSON baselines for selected scenario
runs. They protect current runtime behavior after the phase split and
architecture stabilization without storing raw memory dumps.

Run verification:

```bash
python tools/verify_phase_regression_snapshots.py
```

Regenerate snapshots intentionally:

```bash
python tools/generate_phase_regression_snapshots.py
```

Generation is explicit. Normal verifier runs do not update snapshots.

## Selected scenarios

Snapshots live in `scenarios/regression_snapshots/` and currently cover:

- `real_input_repeated_audio_signal`
- `real_input_conflicting_sensor_signal`
- `real_input_low_confidence_action_loop`
- `real_input_integrity_preservation_loop`
- `real_input_value_target_repetition`
- `real_input_retention_with_observation_views`
- `decision_audit_cycle`
- `retention_pressure`

## Snapshot schema

Each snapshot is a compact object with:

- `schema_version`
- `scenario`
- `tick_count`
- `event_count`
- `marker_sequence`
- `marker_counts`
- `selected_decisions`
- `candidate_source_counts`
- `decision_audit_status_counts`
- `action_guard_status_counts`
- `decision_cycle_summary_status_counts`
- `reflection_review_status_counts`
- `policy_pressure_type_counts`
- `policy_pressure_review_status_counts`
- `need_more_evidence_active_count`
- `retention_summary`
- `side_list_counts`
- `memory_safety`

## Stable and volatile fields

Snapshots intentionally include stable runtime observations:

- marker sequence and marker counts
- normalized selected decision summaries
- action candidate source counts
- decision audit, guard audit, and cycle-summary status counts
- final runtime-only reflection/pressure status counts
- retention and side-list summaries
- real-memory safety flags

Snapshots intentionally exclude volatile values:

- generated operation IDs
- generated decision/audit/review IDs
- temporary directory paths
- object memory addresses
- raw memory dumps
- full candidate snapshots with generated candidate IDs

Scores in selected decision summaries are rounded by the runtime before they are
captured.

## Acceptable changes

Snapshot changes are acceptable only when a deliberate runtime behavior,
scenario, phase ordering, or retention-policy change has been reviewed. In that
case:

1. Update the relevant ADR or architecture note.
2. Run `python tools/generate_phase_regression_snapshots.py`.
3. Review the JSON diff.
4. Run `python tools/verify_phase_regression_snapshots.py`.
5. Run the phase, scenario, audit, and memory-safety verifier suite.

Snapshot changes are not acceptable as incidental churn from refactors,
debug-output edits, or generated ID differences.

## Memory safety

Snapshot generation and verification run scenarios against temporary `Memory`
copies through the scenario runner. Real safe checks are expected to preserve:

- `Memory/ExpSM/ExpSM_data.json`
- `Memory/AKBSM/AKBSM_ne.json`
- absence of `Memory/AKBSM/DB/semantic_core.json`
- absence of `Memory/AKBSM/DB/technical_feedback_patterns.json`
