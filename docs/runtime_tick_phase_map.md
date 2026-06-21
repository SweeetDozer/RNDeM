# Runtime Tick Phase Map

## Purpose

This document audits the current `CLCRuntime._run_tick()` order without
refactoring it. It records what runs during one tick, what reads and writes each
phase-like section performs, when queued `ContextOperation`s are committed, and
which artifacts can affect current tick behavior versus later ticks.

The map is descriptive only. `_run_tick()` now delegates to helper methods named
after these phase-like sections; the helpers are intended to preserve the
previous order and boundaries.

Any future phase split must preserve `ContextMemoryManager.apply_pending()`
boundaries, retention timing, and current-tick versus next-tick semantics. See
`docs/adr_run_tick_phase_split_boundaries.md`.

## Commit And Retention Timing

Most producers append operations to `ContextOpsPool`. `ContextMemoryManager`
then drains the pool with `apply_pending()`. During each commit:

- `ContextMemory.add_event(...)` records the operation in `events`
- raw/self-generated frames are also added to frame lists
- marker-specific side lists are updated, such as `decisions`,
  `decision_audits`, `evaluation_targets`, `expsm_mechanism_searches`, and
  `decision_cycle_summaries`
- `ContextRetentionPolicy` prunes the event list after operations are applied
- `SideListRetentionPolicy` prunes side lists after event retention, using the
  oldest remaining event tick

Retention therefore runs many times per tick, not only at the end.

## Current Order

The static audit representation lives in
`clc/runtime/runtime_phase_map.py`. Its phase-like sections are:

| Phase | Name | Current Tick Decision? |
| --- | --- | --- |
| 00 | Tick setup and pending input commit | yes |
| 01 | Primary perception, prediction, tone, and thought updates | yes |
| 02 | Active field refresh, decay, ExpSM activation, and consolidation pressure | yes |
| 03 | Action proposal, candidate decay, decision selection, and guard adjustment | yes |
| 04 | Decision observers, guard audit, cycle summary, internal action effects | no |
| 05 | Mode transition and consolidation/memory write chain | no |
| 06 | Outcome, evaluation, AKBSM association, mechanism search, and experience candidates | no |
| 07 | Target satisfaction and value feedback chain | no |
| 08 | Neuromodulation projection over generated side lists | no |
| 09 | Homeostasis and final field/view refresh | no |
| 10 | Runtime-only reflection and pressure views | no |
| 11 | Debug output | no |

Phase-level invariants are checked by:

```bash
python tools/verify_phase_level_invariants.py
```

That verifier checks helper presence, helper call order, `apply_pending(` count,
`DecisionSelector` before `ExpSMMechanismSearch`, runtime-only
reflection/pressure isolation, marker 36 absence, and scenario coverage.

Implemented helper methods:

- `_phase_00_input_commit`
- `_phase_01_primary_updates`
- `_phase_02_field_activation_and_consolidation_pressure`
- `_phase_03_action_proposal_and_selection`
- `_phase_04_decision_audit_and_effects`
- `_phase_05_mode_consolidation_memory_chain`
- `_phase_06_outcome_evaluation_akbsm_mechanism`
- `_phase_07_value_feedback`
- `_phase_08_neuromodulation_projection`
- `_phase_09_final_field_refresh`
- `_phase_10_runtime_observation_views`
- `_phase_11_debug_output`

## Phase Details

### 00. Tick Setup And Pending Input Commit

Modules:

- `ContextOpsPool`
- `ContextMemoryManager`
- `ContextRetentionPolicy`
- `SideListRetentionPolicy`

Reads:

- queued preprocessor operations from `feed_audio`, `feed_sensor`, or
  `feed_image`
- retention policies

Writes:

- `ContextMemory.events`
- raw frame lists
- marker side lists
- retention metrics

Queued operations from input preparation can affect the current tick because
they are committed before active processing begins.

### 01. Primary Perception, Prediction, Tone, And Thought Updates

Modules:

- `RhythmDLM`
- `NoveltyDLM`
- `RiskDLM`
- `InternalStateDLM`
- `SimpleFutureStatePredictor`
- `NeuromodulationModule`
- `ThoughtGeneratorModule`
- `ContextMemoryManager`

Reads:

- `ContextMemory`
- `PatternStore`
- `AKBSMAdapter`
- `ExpSMAdapter`
- `ActiveContextField`

Writes:

- labels
- predictions
- neuromodulation updates
- self-generated thought frames

These operations are committed before the first active field refresh, so they
can affect the current tick.

### 02. Active Field Refresh, Decay, ExpSM Activation, And Consolidation Pressure

Modules:

- `FieldUpdater`
- `ActiveContextField`
- `ExpSMActivationModule`
- `ConsolidationPressureModule`
- `ExpSMUpdateReviewGate`
- `ContextMemoryManager`

Reads:

- `ContextMemory`
- `ActiveContextField`
- `SystemState`
- current tone
- ExpSM data

Writes:

- `ActiveContextField`
- `expsm_activations`
- `consolidation_pressures`
- `expsm_update_reviews`

This phase can affect current tick selection because `ActionProposer` reads the
updated active field.

### 03. Action Proposal, Candidate Decay, Decision Selection, And Guard Adjustment

Modules:

- `ActionProposer`
- `ActionCandidateField`
- `DecisionSelector`
- `ModeActionGuard`
- `action_scoring`

Reads:

- `ContextMemory`
- `ActiveContextField`
- `ActionCandidateField`
- `SystemState`
- current tone

Writes:

- `ActionCandidateField`
- candidate suppression state
- queued `INTERNAL_DECISION` when a decision is selected

This is the current tick action selection point. Candidates present before
`DecisionSelector.select(...)` can influence the current tick decision.

### 04. Decision Observers, Guard Audit, Cycle Summary, Internal Action Effects

Modules:

- `DecisionAuditObserver`
- `ActionGuardAuditObserver`
- `DecisionCycleSummaryObserver`
- `ExpSMCompetitionObserver`
- `InternalActionExecutor`
- `NeuromodulationModule.run_effects`
- `ThoughtGeneratorModule.run_effects`
- `ContextMemoryManager`

Reads:

- selected decision
- `ModeActionGuard` audit state
- `SystemState`
- `ActiveContextField`

Writes:

- `decision_audits`
- `action_guard_audits`
- `decision_cycle_summaries`
- internal action effects
- ExpSM competition observations

These artifacts describe or follow the selected decision. They do not trigger a
second decision selection in the same tick.

### 05. Mode Transition And Consolidation/Memory Write Chain

Modules:

- `SystemModeManager`
- `ModeTransitionCleanup`
- `ConsolidationModeProcessor`
- `MemoryWriteReviewModule`
- `MemoryDraftWriter`
- `DraftCommitGate`
- `ExpSMCommitWriter`
- `ExpSMUpdateWriter`
- `ExpSMAdapter.reload`
- `ValueFeedbackMemoryView.refresh`
- `ContextMemoryManager`

Reads:

- `ContextMemory`
- `ActiveContextField`
- `SystemState`
- `MemoryMutationPolicy`
- ExpSM draft store

Writes:

- mode changes
- consolidation candidates
- memory write reviews
- draft writes and commit reviews
- ExpSM commits/updates only when the mutation policy permits them

This happens after decision selection, so its outputs are later-tick context for
selection.

### 06. Outcome, Evaluation, AKBSM Association, Mechanism Search, And Experience Candidates

Modules:

- `ExpSMSimilarityObserver`
- `OutcomeEvaluator`
- `ExpSMOutcomeFeedback`
- `EvaluationSignalModule`
- `EvaluationFieldUpdater`
- `EvaluationTargetObserver`
- `AKBSMAssociationProbe`
- `AKBSMAssociationFieldUpdater`
- `ExpSMMechanismSearch`
- `ExperienceCandidateBuilder`
- `ExperienceCandidateBuffer`
- `ContextMemoryManager`

Reads:

- `ContextMemory`
- `ActiveContextField`
- `EvaluationField`
- `AKBSMAssociationField`
- ExpSM data
- `ValueFeedbackMemoryView`

Writes:

- outcomes
- ExpSM feedback
- evaluation signals
- evaluation targets
- AKBSM association probes
- ExpSM mechanism search records
- experience candidates

Known ordering caveat: `ExpSMMechanismSearch` runs after
`DecisionSelector`. Candidates sourced from mechanism search therefore may be
next-tick material rather than current-tick decision material.

### 07. Target Satisfaction And Value Feedback Chain

Modules:

- `TargetSatisfactionObserver`
- `ValueFeedbackCandidateBuilder`
- `ValueFeedbackReviewGate`
- `ValueFeedbackUpdateWriter`
- `ExpSMAdapter.reload`
- `ValueFeedbackMemoryView.refresh`
- `ContextMemoryManager`

Reads:

- `ContextMemory`
- `ActiveContextField`
- `EvaluationField`
- `SystemState`
- `MemoryMutationPolicy`

Writes:

- target satisfaction observations
- value feedback candidates
- value feedback reviews
- value feedback updates
- ExpSM value feedback when policy allows

These writes are after the current decision and cannot alter the already
selected action.

### 08. Neuromodulation Projection Over Generated Side Lists

Modules:

- `NeuromodulationModule`
- `ContextMemoryManager`

Reads:

- generated side lists such as outcomes, candidates, reviews, updates, audits,
  targets, and mechanism searches
- current tone

Writes:

- neuromodulation updates

These tone updates are useful runtime state for later processing and future
ticks, not a current-tick selection input.

### 09. Homeostasis And Final Field/View Refresh

Modules:

- `HomeostasisModule`
- `EvaluationFieldUpdater`
- `AKBSMAssociationFieldUpdater`
- `FieldUpdater`
- `ContextMemoryManager`

Reads:

- `ContextMemory`
- current tone
- `ActiveContextField`
- `EvaluationField`
- `AKBSMAssociationField`

Writes:

- module updates
- `EvaluationField`
- `AKBSMAssociationField`
- `ActiveContextField`

This final field refresh occurs after selection and before runtime-only views.

### 10. Runtime-Only Reflection And Pressure Views

Modules:

- `DecisionCycleHistoryView`
- `ReflectionCandidateBuilder`
- `NeedMoreEvidenceSignalBuilder`
- `ReflectionReviewBuilder`
- `PolicyPressureBuilder`
- `PolicyPressureReviewBuilder`

Reads:

- recent marker 35 `decision_cycle_summaries`
- runtime-only recent builder state

Writes:

- `runtime.decision_cycle_history_view`
- `runtime.need_more_evidence_signal`
- `runtime.reflection_review`
- `runtime.policy_pressure`
- `runtime.policy_pressure_review`

The reflection/pressure chain is observational only and affects no behavior.
`PolicyPressureReview` does not influence behavior.

### 11. Debug Output

Modules:

- `CLCRuntime` debug printers
- `ContextMemory.debug_print_state`
- `RetentionDiagnostics`

Reads:

- runtime state
- `ContextMemory`
- fields
- recent diagnostic views

Writes:

- stdout

Debug output is not a control path.

## Current-Tick Versus Next-Tick Effects

- Action candidates present before `DecisionSelector.select(...)` can influence
  the current tick.
- Action candidates, evaluations, audits, feedback, mechanism searches, and
  memory artifacts produced after `DecisionSelector.select(...)` generally
  affect later ticks.
- Evaluation field updates after selection do not change the selected decision
  in the same tick.
- `ExpSMMechanismSearch` candidates may be next-tick material because mechanism
  search occurs after current selection.
- Reflection and pressure artifacts are runtime-only diagnostics and affect no
  behavior.
- Context retention affects the amount of history available after each commit.

## Safe Future Split Proposal

The current helper extraction split `_run_tick()` along the audited phase-like
boundaries after the phase-split ADR. Any later split or movement should:

- preserve the exact current order first
- keep `ContextMemoryManager.apply_pending()` and retention timing equivalent
- preserve current-tick versus next-tick behavior
- keep reflection/pressure diagnostics disconnected from scoring, planning,
  memory gates, `FieldUpdater`, and `NeuromodulationModule`
- add regression tests that compare marker sequences, scenario outputs, and
  memory hashes before and after the split

## Refactor Risks

- Moving `ActionProposer` or `DecisionSelector` later can accidentally make
  evaluation/mechanism-search artifacts current-tick inputs.
- Moving retention can change what history views and side lists see.
- Moving ExpSM reloads can stale or prematurely refresh value feedback views.
- Moving reflection/pressure views earlier can create the temptation to feed
  diagnostics into behavior.
- Splitting without preserving every `apply_pending()` boundary can change side
  list content and event order.
