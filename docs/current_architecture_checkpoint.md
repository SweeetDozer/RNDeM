# Current architecture checkpoint

Status: current checkpoint for the stabilized `RNDeM_CLC_Prototype`.

## Purpose

The prototype is a local cognitive loop experiment. It ingests simple audio,
sensor, and image inputs; records runtime context; maintains active/evaluation
fields; proposes and selects internal actions; observes outcomes; and builds
runtime-only diagnostic views over recent decisions.

The current architecture is intentionally conservative. The safe-demo path is
designed to exercise the runtime pipeline without mutating real ExpSM or AKBSM
memory. Planning, LLM calls, chatbot behavior, and behavior-changing
reflection/pressure influence are not implemented.

## Directory and module map

`clc/runtime/`

- `clc_runtime.py` wires the runtime, feed methods, `_run_tick()` phase helpers,
  debug output, and memory profile policy.
- `runtime_phase_map.py` is the descriptive phase map used by verifiers and docs.
- `memory_mutation_policy.py` defines `safe_demo`, `draft_only`, and
  `mutating_memory` profiles.

`clc/context/`

- `ContextMemory` is the runtime chronicle/event log and marker side-list store.
- `ContextOpsPool` queues `ContextOperation` objects before commit.
- `ContextMemoryManager` is the single writer that drains the pool with
  `apply_pending`.
- `ContextRetentionPolicy` and `SideListRetentionPolicy` bound event and
  marker-specific side-list growth.

`clc/action/`

- `ActionProposer` creates action candidates from active runtime context.
- `action_scoring.py` computes candidate score components.
- `DecisionSelector` ranks/selects a candidate and emits internal decisions.
- `ModeActionGuard` constrains actions by system mode.
- `InternalActionExecutor` applies selected internal action effects.
- `DecisionAuditObserver`, `ActionGuardAuditObserver`, and
  `DecisionCycleSummaryObserver` produce observation markers 33, 34, and 35.

`clc/evaluation/`

- `EvaluationSignalModule`, `EvaluationFieldUpdater`, and
  `EvaluationTargetObserver` project evaluation/value observations.
- `TargetSatisfactionObserver`, `ValueFeedbackCandidateBuilder`,
  `ValueFeedbackReviewGate`, `ValueFeedbackUpdateWriter`, and
  `ValueFeedbackMemoryView` cover value feedback observation, review, and
  policy-gated update handling.
- `DecisionCycleHistoryView`, `ReflectionCandidateBuilder`,
  `NeedMoreEvidenceSignalBuilder`, `ReflectionReviewBuilder`,
  `PolicyPressureBuilder`, and `PolicyPressureReviewBuilder` form the
  runtime-only reflection/pressure chain.

`clc/experience/`

- Experience candidate builders, causal traces, candidate grouping,
  learnability filtering, and buffering live here. These are downstream of
  outcome/evaluation observations and remain policy-gated before permanent
  memory writes.

`clc/consolidation/`

- Consolidation pressure, consolidation-mode processing, memory write review,
  draft enrichment/filtering, draft writing, draft commit review, ExpSM commit,
  and ExpSM update review/write modules live here.
- Memory mutation is controlled by `MemoryMutationPolicy`.

`clc/akbsm/`

- `AKBSMAssociationProbe` and `AKBSMAssociationFieldUpdater` produce and project
  runtime association evidence.
- `AKBSMAssociationField` is a runtime field, not a direct AKBSM write path.

`clc/expsm/`

- ExpSM activation, similarity, feedback, competition observation, and
  `ExpSMMechanismSearch` live here.
- `ExpSMMechanismSearch` can produce mechanism-source candidates for future
  ticks, but it runs after current tick selection.

`clc/field/`

- `ActiveContextField` stores active/salient runtime patterns.
- `FieldUpdater` projects `ContextMemory` into the active field.
- `ActivePattern` stores activation, confidence, TTL, and decay state.

`clc/homeostasis/`

- `HomeostasisModule` produces late-tick homeostatic module updates.

`clc/scenarios/`

- `scenario_loader.py` parses fixture JSON.
- `scenario_runner.py` runs fixtures against a temporary `Memory` copy and checks
  marker, retention, reflection, and real-memory invariants.

`tools/`

- Focused verifiers and audit scripts live here. They are the current regression
  harness for runtime safety, phase boundaries, semantic migrations, retention,
  scenarios, and memory mutation policy.

`docs/`

- ADRs, audit summaries, subsystem notes, scenario docs, and this checkpoint
  live here.

`Memory/`

- `Memory/ExpSM/ExpSM_data.json` is operational experience memory.
- `Memory/ExpSM/ExpSM_drafts.json` stores draft experience material.
- `Memory/AKBSM/AKBSM_ne.json` is associative memory/query support.
- `Memory/AKBSM/DB/` stores NFP/pattern material used by pattern stores.
- `Memory/pattern_manifest.json` is the PatternRegistry manifest and semantic
  metadata source.

`scenarios/`

- JSON fixtures for ordinary scenarios, synthetic reflection/pressure scenarios,
  policy-review scenarios, real-input scenarios, and retention pressure.

## Runtime tick pipeline

`CLCRuntime._run_tick()` is split into order-preserving phase helpers:

1. `_phase_00_input_commit`
2. `_phase_01_primary_updates`
3. `_phase_02_field_activation_and_consolidation_pressure`
4. `_phase_03_action_proposal_and_selection`
5. `_phase_04_decision_audit_and_effects`
6. `_phase_05_mode_consolidation_memory_chain`
7. `_phase_06_outcome_evaluation_akbsm_mechanism`
8. `_phase_07_value_feedback`
9. `_phase_08_neuromodulation_projection`
10. `_phase_09_final_field_refresh`
11. `_phase_10_runtime_observation_views`
12. `_phase_11_debug_output`

Important phase invariants:

- `apply_pending` boundaries are semantically significant.
- Current textual apply_pending count = 62.
- Retention runs during `ContextMemoryManager.apply_pending`, not only at the
  end of a tick.
- DecisionSelector before ExpSMMechanismSearch.
- `ExpSMMechanismSearch` candidates are generally next-tick material.
- Reflection/pressure views run in phase 10 and are runtime-only observation.
- PolicyPressureReview does not influence behavior.
- Marker 36 is absent.

## Memory model

`ContextMemory` is the runtime chronicle and marker side-list source. It stores
events, recent decisions, audits, evaluation observations, mechanism searches,
decision-cycle summaries, and retention diagnostics.

`ContextOpsPool` is a staging queue. Producers push operations into it; they do
not directly mutate `ContextMemory`.

`ContextMemoryManager` is the single writer. Its `apply_pending` calls commit
queued operations, update marker side lists, and run retention. Moving these
calls changes runtime semantics.

`ActiveContextField` is the active/salient runtime field used by action proposal,
evaluation, consolidation, and debug output.

`ActionCandidateField` stores current action candidates and their decay state.

`EvaluationField` stores projected evaluation/value state.

`AKBSMAssociationField` stores runtime association probe results.

`ValueFeedbackMemoryView` is a runtime read-view over value feedback metadata in
ExpSM records. It supports value-aware mechanism scoring and target-specific
value scoring without making reflection/pressure behavioral.

`ExpSM` is operational experience memory. In safe-demo checks, real
`ExpSM_data.json` remains unchanged.

`AKBSM` is associative memory/query support. AKBSM writes remain blocked by
default under current mutation policy.

Memory profiles:

- `safe_demo`: allows draft writes only when memory is temporary; blocks ExpSM
  commits, ExpSM updates, value feedback updates, and AKBSM writes.
- `draft_only`: allows draft writes; blocks permanent ExpSM/value/AKBSM writes.
- `mutating_memory`: allows draft, ExpSM commit, ExpSM update, and value
  feedback update; AKBSM writes are still blocked.

## Action and decision model

`ActionProposer` reads `ContextMemory`, `ActiveContextField`, and system state to
create action candidates. `ActionScoring` computes score components from
activation, confidence, urgency, risk, cost, source, and value-related metadata.
`DecisionSelector` ranks candidates and emits an `INTERNAL_DECISION` when one is
selected. `ModeActionGuard` can suppress or constrain candidates by runtime
mode. `InternalActionExecutor` applies selected internal action effects.

The observer layer records what happened after selection:

- `DecisionAuditObserver`
- `ActionGuardAuditObserver`
- `DecisionCycleSummaryObserver`
- `ExpSMCompetitionObserver`

Source labels are stable runtime provenance labels. PatternRegistry debug names
are not semantic control signals; high-risk debug-name findings = 0 and
`legacy_semantic_decision = 0`.

## Evaluation and value feedback model

Evaluation begins after current tick selection. `EvaluationSignalModule` produces
evaluation signals, `EvaluationFieldUpdater` projects them, and
`EvaluationTargetObserver` records target observations. `AKBSMAssociationProbe`
queries associative support, then `AKBSMAssociationFieldUpdater` projects it.

`ExpSMMechanismSearch` uses ExpSM, evaluation, association, and
`ValueFeedbackMemoryView` to find mechanism evidence. Because this runs after
`DecisionSelector`, mechanism-search candidates are generally future material.

The value-feedback chain is:

- `TargetSatisfactionObserver`
- `ValueFeedbackCandidateBuilder`
- `ValueFeedbackReviewGate`
- `ValueFeedbackUpdateWriter`
- `ValueFeedbackMemoryView`

Value-aware mechanism scoring and target-specific value scoring are covered by
focused verifiers. Permanent value feedback updates remain policy-gated.

## AKBSM and ExpSM role split

ExpSM stores operational experience, draft experience material, outcome
feedback, mechanism evidence, and value feedback metadata. ExpSM activation can
affect current tick action proposal before selection, while ExpSM mechanism
search runs after selection.

AKBSM supports associative lookup and association probes. Current safe-demo and
draft-only profiles do not write AKBSM. Even in `mutating_memory`,
`allow_akbsm_write` is currently false.

## Reflection and pressure chain

The runtime-only reflection/pressure chain is:

- `DecisionCycleHistoryView`
- `ReflectionCandidateBuilder`
- `NeedMoreEvidenceSignalBuilder`
- `ReflectionReviewBuilder`
- `PolicyPressureBuilder`
- `PolicyPressureReviewBuilder`

This chain is observational-only. Under the current ADR, it must not affect
scoring, selection, guards, memory gates, memory writes, `FieldUpdater`, or
`NeuromodulationModule`. `PolicyPressureReview` does not influence behavior.

## Scenario and testing structure

Scenario fixtures live in `scenarios/*.json` and run through
`clc/scenarios/scenario_runner.py` against a temporary memory copy.

Fixture groups:

- ordinary scenario fixtures: audio, sensor, decision audit, and basic retention
- synthetic reflection/pressure fixtures: seeded decision-cycle summaries for
  precise reflection-state coverage
- policy review fixtures: focused PolicyPressureReview status coverage
- real-input scenarios: ordinary audio/sensor probes with no synthetic
  reflection/pressure injection
- retention fixtures: context and side-list cap checks

Focused scenario verifiers:

- `tools/verify_scenario_fixtures.py`
- `tools/verify_real_input_scenarios.py`
- `tools/verify_reflection_pressure_scenarios.py`
- `tools/verify_policy_pressure_review_scenarios.py`
- `tools/verify_phase_level_invariants.py`
- `tools/verify_phase_regression_snapshots.py`

## Safety boundaries

- Do not move `ContextMemoryManager.apply_pending` calls without an ADR and
  verifier updates.
- Do not change retention timing as a side effect of phase cleanup.
- Keep `DecisionSelector` before `ExpSMMechanismSearch`.
- Treat mechanism-search candidates as next-tick material unless a future ADR
  explicitly changes that.
- Keep reflection/pressure observational-only.
- Keep `PolicyPressureReview` disconnected from behavior.
- Do not add marker 36 without an explicit marker ADR.
- Preserve PatternRegistry semantics: debug-name strings are not semantic
  control signals.
- Preserve phase-level invariants.
- Preserve current audit state: high-risk debug-name findings = 0 and
  `legacy_semantic_decision = 0`.
- Real safe checks should leave ExpSM and AKBSM hashes unchanged.

## Verifier map

| Verifier | Protected invariant |
| --- | --- |
| `tools/verify_architecture_checkpoint.py` | this checkpoint exists, includes critical safety facts, and core safety verifiers pass |
| `tools/verify_runtime_tick_phase_map.py` | phase map exists and critical phase caveats are documented |
| `tools/verify_run_tick_phase_split_boundaries.py` | `apply_pending`/retention/order boundaries, marker 36 absence, and key safety verifiers |
| `tools/verify_phase_level_invariants.py` | helper phase order, `apply_pending` count, next-tick mechanism-search material, reflection/pressure isolation |
| `tools/verify_phase_regression_snapshots.py` | compact marker, decision, audit, reflection/pressure, retention, and memory-safety baselines for selected scenarios |
| `tools/verify_run_tick_phase_split_equivalence.py` | scenario expectations pass and real ExpSM/AKBSM stay unchanged |
| `tools/verify_policy_pressure_influence_boundary.py` | reflection/pressure disconnected from scoring, guards, gates, fields, and neuromodulation |
| `tools/verify_debug_name_dependency_audit.py` | debug-name audit schema and classifications remain valid |
| `tools/verify_legacy_semantic_decision_migration.py` | high-risk debug-name and legacy semantic decision debt remain resolved |
| `tools/verify_unknown_runtime_logic_split.py` | unknown runtime logic audit split remains clean |
| `tools/verify_memory_mutation_policy.py` | safe/draft/mutating memory write policy |
| `tools/verify_decay_semantics.py` | field decay semantics |
| `tools/verify_context_retention_policy.py` | ContextMemory retention |
| `tools/verify_context_side_list_retention_policy.py` | side-list retention |
| `tools/verify_real_input_scenarios.py` | ordinary audio/sensor real-input pipeline coverage |
| `tools/verify_scenario_fixtures.py` | all scenario marker, retention, reflection, and memory safety fixtures |
| `tools/verify_scoring_selection_semantics.py` | scoring/selection source-label semantics |
| `tools/verify_pattern_semantics.py` | PatternRegistry semantic metadata stability |
| `tools/verify_memory_write_filter_semantics.py` | memory-write semantic filters |
| `tools/verify_draft_semantic_filters.py` | draft semantic filters |
| `tools/verify_learnability_filter_semantics.py` | learnability semantic filtering |

## Known limitations

- No planning.
- No LLM calls.
- No chatbot behavior.
- Reflection/pressure cannot influence behavior yet.
- `PolicyPressureReview` is observational-only.
- Mechanism-search is mostly next-tick material.
- AKBSM writes remain blocked by default.
- Real-input scenarios are still simple audio/sensor probes.
- Git status is unavailable in the current environment.
- One ambiguous runtime audit finding remains in demo/display code:
  `build_demo_image_from_memory()` splits image debug names for display.

## Recommended next work

1. Expand real-input scenarios with more ordinary input combinations.
2. Add deeper phase-level regression snapshots around selected marker windows.
3. Design a behavior influence ADR for reflection/pressure, but do not implement
   influence by default.
4. Later inspect whether AKBSM writes can be safely introduced.
5. Later improve project packaging and git hygiene.
