# Scenario fixtures

Scenario fixtures live in `scenarios/*.json`. They are partial golden tests for
runtime marker flow: a fixture defines input events, runs them against a
temporary copy of `Memory`, and checks marker presence, forbidden markers,
marker order, retention pressure, and real-memory immutability.

The verifier is:

```bash
python tools/verify_scenario_fixtures.py
```

## Schema

```json
{
  "schema_version": 1,
  "name": "audio_periodic",
  "description": "Human-readable purpose.",
  "runtime": {
    "profile": "safe_demo",
    "memory_is_temporary": true,
    "max_ticks": 6,
    "context_max_events": 5000,
    "protected_recent_events": 200,
    "side_list_default_max_entries": 500
  },
  "inputs": [
    {
      "tick": 1,
      "source": "scenario_name",
      "kind": "audio",
      "patterns": ["aud_freq_440"],
      "activation": 0.9,
      "payload": {}
    }
  ],
  "expect": {
    "required_markers": [1, 6, 12],
    "forbidden_markers": [17, 20],
    "marker_order": [[1, 6]],
    "min_event_count": 40,
    "memory_unchanged": true,
    "retention_pruned_events": false,
    "side_list_caps_respected": true,
    "decision_cycle_summary_observed": true,
    "reflection": {
      "history_trend_label": "uncertain_recent_history",
      "candidate_types": ["repeated_uncertain_selection"],
      "need_more_evidence_active": true,
      "reflection_review_status": "needs_more_evidence",
      "policy_pressure_type": "evidence_pressure",
      "policy_pressure_active": true
    }
  }
}
```

`required_markers` is intentionally partial. These fixtures should not lock down
the complete runtime log; they should only pin markers that are important to a
scenario contract.

`min_event_count` is optional. It is useful for real-input fixtures that should
exercise enough of the runtime pipeline to produce downstream observation views
without pinning exact marker counts.

`decision_cycle_summary_observed` is optional and currently used by the focused
real-input verifier. It defaults to `true` there because most real-input
fixtures should naturally reach marker 35. Calm repeated-input probes can set it
to `false` to document that they intentionally remain below the
decision-summary path.

## Input kinds

`audio` calls `CLCRuntime.feed_audio` with `payload.frequencies`.

`sensor` calls `CLCRuntime.feed_sensor` with `cpu_temp`, `memory_usage`,
`damage_flag`, and `resource_pressure`.

`image` calls `CLCRuntime.feed_image` with `payload.pixels`.

`module_update_burst` is a test-only pressure adapter. It pushes a burst of
`MODULE_UPDATE` operations into the context manager and applies pending
retention. This exists so retention fixtures can exercise event and side-list
bounds without changing runtime scoring, tick phases, or permanent memory.

## Reflection expectations

Fixtures can optionally define `expect.reflection` fields for the runtime-only
reflection/pressure chain. Supported fields are:

- `history_trend_label`
- `candidate_types`
- `need_more_evidence_active`
- `need_more_evidence_reason`
- `reflection_review_status`
- `reflection_review_primary_issue`
- `policy_pressure_type`
- `policy_pressure_active`
- `policy_pressure_recommended_future_operation`
- `policy_pressure_review_status`
- `policy_pressure_review_primary_issue`
- `policy_pressure_review_pressure_type`
- `policy_pressure_review_active`
- `policy_pressure_review_recommended_future_operation`

The test-only input kind `synthetic_policy_pressure_review` may be used by
scenario fixtures to build a runtime-only `PolicyPressureReview` without writing
`ContextMemory` or permanent memory. It exists only for review states that the
full upstream chain cannot naturally produce under current dominance rules.

Fixtures can also include `synthetic_decision_cycle_summaries` to seed marker 35
payloads into temporary runtime memory before inputs run. This is test-only and
does not modify real memory.

## Real-input scenarios

Real-input fixtures live beside the synthetic fixtures and are documented in
`docs/real_input_scenarios.md`. They use ordinary `audio` and `sensor` inputs
only, then assert the decision audit, guard audit, decision-cycle summary, and
runtime-only reflection/pressure observations produced by the normal pipeline.
One stable repetition probe explicitly asserts that no decision-cycle summary is
expected; the rest of the expanded real-input set keeps marker 35 as part of the
scenario contract.

The focused verifier is:

```bash
python tools/verify_real_input_scenarios.py
```

Selected fixtures also have compact regression snapshots:

```bash
python tools/verify_phase_regression_snapshots.py
```

Snapshots are stored in `scenarios/regression_snapshots/` and are regenerated
explicitly with `python tools/generate_phase_regression_snapshots.py`.
New real-input expansion fixtures are scenario coverage only for now and are not
added automatically to `tools.phase_regression_snapshots.SELECTED_SCENARIOS`.

## Disabled Mode C fixtures

Disabled Mode C fixtures live beside the other scenario fixtures:

- `mode_c_disabled_no_effect`
- `mode_c_safe_demo_no_effect`
- `mode_c_draft_only_metadata_absent`
- `mode_c_policy_flag_default_no_advisory`
- `mode_c_pressure_review_still_observational`

They prove the disabled scaffold has no default behavior effect, no marker 36,
no real-memory mutation, and no `PolicyPressureReview` connection to memory
gates. They are scenario-only coverage because they verify scaffold/no-effect
behavior rather than canonical phase output. The phase regression snapshot set
was not expanded for these fixtures.

The focused verifier is:

```bash
python tools/verify_mode_c_disabled_scenarios.py
```

## AKBSM write-disabled fixtures

AKBSM write-disabled fixtures live beside the other scenario fixtures:

- `akbsm_write_disabled_no_effect`
- `akbsm_safe_demo_no_write`
- `akbsm_draft_only_no_commit`
- `akbsm_mutating_memory_still_blocked`
- `akbsm_pressure_review_no_graph_write`
- `akbsm_repeated_signal_no_association_write`

They prove current runtime profiles do not write AKBSM, `safe_demo` blocks
AKBSM writes, `draft_only` does not commit AKBSM writes, `mutating_memory`
still leaves AKBSM writes blocked by policy, and `PolicyPressureReview` or Mode
C cannot write AKBSM. They also keep marker 36 absent and real Memory hashes
unchanged.

They are scenario-only coverage because they verify no-write safety rather than
canonical phase output. The phase regression snapshot set was not expanded for
these fixtures.

The focused verifier is:

```bash
python tools/verify_akbsm_write_disabled_scenarios.py
```

## AKBSM draft proposal disabled fixtures

AKBSM draft proposal disabled fixtures live beside the other scenario fixtures:

- `akbsm_draft_proposal_disabled_no_effect`
- `akbsm_draft_proposal_safe_demo_no_proposal`
- `akbsm_draft_proposal_draft_only_no_proposal`
- `akbsm_draft_proposal_mutating_memory_no_proposal`
- `akbsm_draft_proposal_repeated_signal_no_proposal`
- `akbsm_draft_proposal_pressure_review_no_proposal`

They prove the draft proposal provider remains no-op under current profiles,
does not create proposal metadata, does not write `ContextMemory`, does not
write AKBSM, keeps marker 36 absent, and leaves real Memory hashes unchanged.

They are scenario-only coverage because they verify disabled scaffold/no-effect
safety rather than canonical phase output. The phase regression snapshot set was
not expanded for these fixtures.

The focused verifier is:

```bash
python tools/verify_akbsm_draft_proposal_disabled_scenarios.py
```

## Memory safety

The scenario runner copies `Memory` into a temporary directory and creates
`CLCRuntime(..., memory_is_temporary=True)`. The verifier also checks that the
real memory hashes for ExpSM and AKBSM are unchanged before and after all
fixtures.
