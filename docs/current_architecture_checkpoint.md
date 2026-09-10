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
- `mode_c_advisory.py` defines disabled-by-default Mode C advisory payload
  scaffold. It is metadata-only and not wired into memory gates.
- `akbsm_draft_proposal.py` defines disabled-by-default AKBSM draft proposal
  payload/provider scaffold. It is metadata-only and not wired into AKBSM
  writers, behavior modules, or storage.
- `akbsm_proposal_contextmemory_metadata.py` defines scenario/test-only
  ContextMemory-compatible AKBSM proposal metadata payload and integration
  boundary scaffolds. They create immutable temporary metadata/deferred results
  only and do not write into ContextMemory.

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
- Controlled AKBSM draft proposal creation exists only as an explicit
  test/scenario provider path from `AKBSMAssociationProbe`; normal runtime
  remains disabled and unconnected.

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
- `mode_c_memory_gate_advisory_enabled`: defaults to `False` in every profile.
  The disabled scaffold has no safe_demo effect and does not connect
  `PolicyPressureReview` to `MemoryWriteReviewModule`.
- `akbsm_draft_proposals_enabled`: defaults to `False` in every profile. The
  disabled scaffold has no safe_demo effect and does not create, store, or
  commit AKBSM proposals.

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

`docs/adr_akbsm_write_policy.md` documents future AKBSM write policy as
proposed / design-only architecture. It keeps the current policy in Mode 0: no
AKBSM writes. `AKBSMAssociationProposal` now exists as immutable
metadata-only scaffold, but the provider is disabled/no-op by default and no
proposal storage, commit path, relation type creation, concept creation, or
AKBSM mutation is implemented.

`docs/adr_akbsm_first_enabled_draft_proposal_experiment.md` documents the first
controlled enabled draft proposal experiment. The source is
`AKBSMAssociationProbe` only; AKBSMAssociationField is deferred. Behavior,
pressure, scoring, action, value, Mode C, ExpSM, and memory writer sources are
forbidden. The provider path is test/scenario-only, default runtime is
unchanged, and AKBSM writes remain blocked.

`docs/adr_akbsm_draft_proposal_review_lifecycle.md` defines a design-only
future lifecycle for temporary AKBSM draft proposal review. Lifecycle states
are metadata-only, no lifecycle state means commit/write/persist, review means
classification only, and `accepted_for_observation` is not AKBSM write
approval.

`docs/design_akbsm_draft_proposal_review_lifecycle_implementation.md` is a
design-only implementation plan. Runtime lifecycle implementation is limited to
the metadata-only state/record/result scaffold and test/scenario-only transition
controller scaffold in `clc/runtime/akbsm_proposal_lifecycle.py`. Transition
execution, review service behavior, proposal storage, normal runtime wiring,
and storage/writes/commit paths are still not added; proposal creation remains
test/scenario-only and AKBSM writes remain blocked.

`docs/adr_akbsm_draft_proposal_transition_controller_experiment.md` is a
design-only ADR for the first metadata-only transition controller experiment.
The metadata-only transition controller scaffold is implemented, transition
execution is not implemented, the controller is test/scenario-only, allowed
first storage is test-local controller return values only, no proposal
storage/writes/commit path exists, and AKBSM writes remain blocked.

Transition controller scenario coverage exists in
`scenarios/akbsm_transition_controller_metadata_coverage.json` and
`tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py`. It is
metadata-only/test-scenario-only coverage for allowed transitions, forbidden
transitions, write-like target rejection, immutable copy behavior, metadata-only
expiration, absent storage, absent ContextMemory storage, absent normal runtime
wiring, unchanged real ExpSM/AKBSM hashes, and marker 36 absence.

`docs/adr_akbsm_proposal_contextmemory_metadata_integration.md` is a
design-only ADR for a possible future temporary ContextMemory metadata
integration. No ContextMemory integration is implemented, no proposal storage is
added, no review record persistence is added, normal runtime remains
disconnected, and AKBSM writes remain blocked. Any first future integration must
be scenario/test-only and may only store temporary metadata copies of proposal
review records.

`clc/runtime/akbsm_proposal_contextmemory_metadata.py` adds an isolated
scenario/test-only ContextMemory-compatible metadata payload scaffold. It builds
immutable temporary metadata payloads from proposal review records and optional
transition results, but does not call `ContextMemoryManager`, does not write
into ContextMemory, does not persist files, and does not add normal runtime
wiring.

The same module also adds a scenario/test-only ContextMemory metadata
integration boundary scaffold. Since no dedicated safe temporary ContextMemory
metadata placement API exists yet, the boundary returns a temporary
metadata-only deferred-placement result instead of placing review records in
ContextMemory. It requires explicit scenario/test authority, adds no proposal
storage or review record persistence, creates no permanent proposal queues, and
does not add behavior influence.

`docs/adr_contextmemory_temporary_metadata_placement_api.md` defines the
design-only future safe temporary ContextMemory metadata placement API. The API
is not implemented yet, current AKBSM proposal ContextMemory integration
remains Shape B/deferred boundary, real ContextMemory placement is still
deferred, no proposal storage exists, no normal runtime wiring exists, and
AKBSM writes remain blocked.

`clc/runtime/context_temporary_metadata.py` adds the scenario/test-only
ContextMemory temporary metadata placement scaffold. The scaffold requires
explicit authority, requires TTL/expiration, accepts metadata-only temporary
entries, rejects write-like metadata, keeps entries local to an explicitly
created placement object, is not wired into normal runtime, does not create
permanent storage/queues, keeps AKBSM proposal metadata non-authoritative for
writes, and keeps AKBSM writes blocked.

`docs/adr_contextmemory_temporary_metadata_runtime_observation.md` defines the
design-only future temporary metadata runtime observation boundary. No runtime
observation is implemented, future observation is read-only diagnostic material
only, no normal runtime wiring exists, observation authority is not placement or
write authority, and AKBSM writes remain blocked.

`clc/runtime/context_temporary_metadata_observation.py` adds an isolated
read-only diagnostic observation scaffold for local temporary metadata placement
state. It requires explicit observation authority, ignores expired metadata as
active metadata, may include expired entries only as diagnostics, returns
metadata-only reports, has no normal runtime or `_run_tick()` wiring, performs
no real ContextMemory writes, and does not influence behavior/scoring/guards/
Mode C/PolicyPressureReview.

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

`docs/adr_behavior_influence_modes.md` documents possible future behavior
influence modes as proposed / discussion-only architecture. It does not approve
or implement behavior influence. Current behavior remains Mode A:
observation-only.

`docs/design_mode_c_memory_gate_influence.md` documents a possible Mode C
advisory memory-gate design. The current code contains only disabled
infrastructure for future metadata. No memory gate currently reads
`PolicyPressureReview`, `PolicyPressure`,
`ReflectionReview`, `NeedMoreEvidenceSignal`, or any reflection/pressure
advisory payload.

`docs/adr_mode_c_first_experiment.md` records the accepted design decision for a
possible first Mode C experiment: `PolicyPressureReview` as the only source and
`MemoryWriteReviewModule` as the first target. The source/target behavior is
not implemented; current Mode A behavior is unchanged.

`docs/post_v0_0_2_safety_architecture_checkpoint.md` summarizes the current
post-v0.0.2 safety architecture state. It is a documentation checkpoint, not a
new runtime release, and it does not create a tag.

## Scenario and testing structure

Scenario fixtures live in `scenarios/*.json` and run through
`clc/scenarios/scenario_runner.py` against a temporary memory copy.

Fixture groups:

- ordinary scenario fixtures: audio, sensor, decision audit, and basic retention
- synthetic reflection/pressure fixtures: seeded decision-cycle summaries for
  precise reflection-state coverage
- policy review fixtures: focused PolicyPressureReview status coverage
- real-input scenarios: ordinary audio/sensor probes with no synthetic
  reflection/pressure injection, including mixed input, stable repetition,
  conflict-then-stabilize, value/target conflict, retention, and guard-audit
  probes
- disabled Mode C fixtures: scenario-only coverage proving the scaffold has no
  default behavior effect, `PolicyPressureReview` remains observational, marker
  36 is absent, and real Memory is unchanged
- AKBSM write-disabled fixtures: scenario-only coverage proving AKBSM remains
  blocked under current profiles, `PolicyPressureReview` and Mode C cannot write
  AKBSM, marker 36 is absent, and real Memory is unchanged
- AKBSM draft proposal disabled fixtures: scenario-only coverage proving the
  draft proposal provider stays no-op, proposal metadata is absent, marker 36 is
  absent, and real Memory is unchanged
- retention fixtures: context and side-list cap checks

Focused scenario verifiers:

- `tools/verify_scenario_fixtures.py`
- `tools/verify_real_input_scenarios.py`
- `tools/verify_mode_c_disabled_scenarios.py`
- `tools/verify_akbsm_write_disabled_scenarios.py`
- `tools/verify_akbsm_draft_proposal_disabled_scenarios.py`
- `tools/verify_reflection_pressure_scenarios.py`
- `tools/verify_policy_pressure_review_scenarios.py`
- `tools/verify_phase_level_invariants.py`
- `tools/verify_phase_regression_snapshots.py`

Disabled Mode C fixtures are not part of the phase regression snapshot set. They
are scenario-only coverage because they verify scaffold/no-effect behavior
rather than canonical phase output.

AKBSM write-disabled fixtures are not part of the phase regression snapshot set.
They are scenario-only coverage because they verify no-write safety rather than
canonical phase output.

AKBSM draft proposal disabled fixtures are not part of the phase regression
snapshot set. They are scenario-only coverage because they verify disabled
proposal/no-effect safety rather than canonical phase output.

## Safety boundaries

- Do not move `ContextMemoryManager.apply_pending` calls without an ADR and
  verifier updates.
- Do not change retention timing as a side effect of phase cleanup.
- Keep `DecisionSelector` before `ExpSMMechanismSearch`.
- Treat mechanism-search candidates as next-tick material unless a future ADR
  explicitly changes that.
- Keep reflection/pressure observational-only.
- Keep `PolicyPressureReview` disconnected from behavior.
- Treat behavior influence modes beyond observation-only as proposed
  discussion-only until a later accepted ADR, feature flag, verifier updates,
  memory safety checks, and rollback instructions exist.
- Treat the Mode C memory-gate advisory scaffold as disabled infrastructure
  only; do not connect reflection/pressure to memory gates until a later
  accepted implementation pass updates policy, gates, scenarios, and verifiers.
- Treat the Mode C first-experiment ADR as a source/target design decision; the
  current scaffold adds a disabled policy gate and metadata type only.
- Treat the AKBSM write-policy ADR as design-only. Do not implement permanent
  AKBSM writes without a later accepted ADR, explicit write policy, review gate,
  relation registry validation, rollback journal, scenario coverage, and memory
  hash verifier updates.
- Treat the draft-only AKBSM association proposal scaffold as disabled
  infrastructure only. `AKBSMAssociationProposal` and
  `AKBSMDraftProposalProvider` exist, but proposal creation is disabled/no-op by
  default and no proposal storage, writer connection, relation type creation,
  concept creation, or AKBSM mutation is implemented.
- Treat the first enabled AKBSM draft proposal experiment as test/scenario-only.
  Do not add proposal storage or runtime wiring until a later pass explicitly
  approves it, keeps AKBSMAssociationField deferred, and adds the required
  scenario and verifier coverage.
- Treat the AKBSM draft proposal review lifecycle ADR as design-only. Do not
  implement lifecycle storage, lifecycle runtime wiring, proposal commit,
  proposal persistence, behavior influence, Mode C influence, or AKBSM mutation
  until a later explicit implementation pass adds scenarios and verifiers.
- Treat the AKBSM draft proposal review lifecycle implementation plan as
  design-only. The metadata-only state/record/result scaffold may exist, but do
  not add transition execution, review controller/service code, proposal
  storage, or runtime wiring until a later explicit implementation pass.
- Treat future AKBSM proposal ContextMemory metadata integration as design-only.
  Do not add ContextMemory storage, review record persistence, permanent
  proposal queues, normal runtime wiring, or AKBSM writes until a later explicit
  implementation pass adds temporary scenario/test-only metadata coverage and
  verifiers.
- Treat the AKBSM proposal ContextMemory metadata scaffold as payload-only
  scenario/test infrastructure. It is not ContextMemory storage, not AKBSM write
  approval, and not a proposal commit/apply/save/write/persist/mutate path.
- Treat the AKBSM proposal ContextMemory metadata integration scaffold as a
  scenario/test-only deferred boundary. It returns temporary metadata only; it
  is not permanent storage, not review record persistence, not behavior
  influence, not normal runtime wiring, and not AKBSM write approval.
- Treat the temporary ContextMemory metadata placement API ADR as design-only.
  The API is not implemented yet; current AKBSM proposal ContextMemory
  integration remains Shape B/deferred boundary, real ContextMemory placement
  is still deferred, no proposal storage exists, no normal runtime wiring
  exists, and AKBSM writes remain blocked.
- Treat the ContextMemory temporary metadata placement scaffold as
  scenario/test-only local metadata infrastructure. It requires explicit
  authority and TTL/expiration, rejects write-like metadata, is not normal
  runtime wiring, does not create permanent storage/queues, and does not make
  AKBSM proposal metadata authoritative for writes.
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
| `tools/verify_behavior_influence_adr.py` | behavior influence modes ADR exists, documents current observation-only policy, forbidden direct connections, and core safety verifiers |
| `tools/verify_mode_c_design_doc.py` | Mode C memory-gate advisory design exists, stays design-only, documents forbidden behavior, and core safety verifiers pass |
| `tools/verify_mode_c_first_experiment_adr.py` | first Mode C experiment ADR exists, documents source/target choice, forbidden effects, profile policy, future scenarios/verifiers, and core safety verifiers |
| `tools/verify_post_v0_0_2_safety_checkpoint.py` | post-v0.0.2 safety checkpoint exists, documents baseline, disabled Mode C state, blocked AKBSM state, forbidden changes, scenario/verifier coverage, and core safety verifiers |
| `tools/verify_mode_c_disabled_scaffold.py` | Mode C scaffold remains disabled by default, metadata-only, disconnected from behavior, marker 36 absent, and real ExpSM/AKBSM hashes unchanged |
| `tools/verify_mode_c_disabled_scenarios.py` | disabled Mode C fixtures exist, pass scenario runner, keep scaffold no-op, preserve influence boundary, and leave real ExpSM/AKBSM hashes unchanged |
| `tools/verify_akbsm_write_policy_adr.py` | AKBSM write-policy ADR exists, documents no-write current policy, candidate write modes, forbidden writes, future coverage, and core AKBSM/memory safety verifiers |
| `tools/verify_akbsm_write_disabled_scenarios.py` | AKBSM write-disabled fixtures exist, pass scenario runner, keep AKBSM writes blocked by policy, preserve AKBSM association probes, and leave real ExpSM/AKBSM hashes unchanged |
| `tools/verify_akbsm_draft_proposal_design.py` | draft-only AKBSM association proposal design exists, documents disabled scaffold status, metadata-only proposal shape, forbidden behavior, profile policy, future coverage, and core safety verifiers |
| `tools/verify_akbsm_draft_proposal_scaffold.py` | AKBSM proposal scaffold remains disabled/no-op by default, metadata-only, disconnected from behavior/writers/storage, marker 36 absent, and real ExpSM/AKBSM hashes unchanged |
| `tools/verify_akbsm_draft_proposal_disabled_scenarios.py` | disabled AKBSM draft proposal fixtures exist, pass scenario runner, keep proposal provider no-op, prevent proposal wiring/writes, keep marker 36 absent, and leave real ExpSM/AKBSM hashes unchanged |
| `tools/verify_akbsm_first_enabled_draft_proposal_adr.py` | first enabled AKBSM draft proposal experiment ADR exists, documents `AKBSMAssociationProbe` as the only future source, defers `AKBSMAssociationField`, forbids behavior/pressure/scoring/action/value/writer sources, and keeps current safety verifiers passing |
| `tools/verify_akbsm_probe_draft_proposal_experiment.py` | controlled test/scenario-only AKBSM probe proposal experiment creates temporary metadata only when explicitly enabled, stays disabled by default, rejects forbidden sources and `commit_allowed=True`, has no commit/storage path, and leaves real ExpSM/AKBSM hashes unchanged |
| `tools/verify_akbsm_draft_proposal_review_lifecycle_adr.py` | draft proposal review lifecycle ADR exists, documents metadata-only states/transitions, forbids write-like states and commit/apply/save/write/persist/mutate paths, documents storage policy, and keeps existing AKBSM proposal safety verifiers passing |
| `tools/verify_akbsm_draft_proposal_lifecycle_implementation_plan.py` | draft proposal lifecycle implementation plan exists, stays design-only, documents tentative metadata-only components, allowed transitions, forbidden authorities, temporary storage strategy, future sequence, and keeps existing safety verifiers passing |
| `tools/verify_akbsm_draft_proposal_lifecycle_state_scaffold.py` | isolated lifecycle state/record/result scaffold exists as immutable metadata only, allowed states/transitions are exact, transition execution/service/storage/wiring are absent, and real ExpSM/AKBSM hashes remain unchanged |
| `tools/verify_akbsm_draft_proposal_transition_controller_adr.py` | transition controller experiment ADR exists, stays design-only, documents metadata-only test/scenario authority, transition semantics, storage limits, forbidden authorities, and keeps existing safety verifiers passing |
| `tools/verify_akbsm_draft_proposal_transition_controller_scaffold.py` | transition controller scaffold exists, requires explicit test/scenario authority, accepts only allowed metadata transitions, rejects forbidden/write-like targets, has no storage/runtime wiring, and leaves real ExpSM/AKBSM hashes unchanged |
| `tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py` | transition controller scenario fixture coverage exists, covers allowed/forbidden/write-like transitions, immutable copy behavior, metadata-only expiration, no storage/runtime wiring, and unchanged real ExpSM/AKBSM hashes |
| `tools/verify_akbsm_proposal_contextmemory_metadata_adr.py` | future temporary ContextMemory proposal metadata ADR exists, stays design-only, allows only scenario/test-only temporary metadata copies, forbids persistence/storage/writes/runtime wiring, and keeps existing safety verifiers passing |
| `tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py` | ContextMemory-compatible proposal metadata payload scaffold exists, requires explicit scenario/test authority, creates immutable temporary metadata only, forbids storage/writes/runtime wiring, and leaves real ExpSM/AKBSM hashes unchanged |
| `tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py` | ContextMemory proposal metadata integration boundary scaffold exists, requires explicit scenario/test authority, returns temporary deferred metadata only, forbids ContextMemory placement/storage/writes/runtime wiring, and leaves real ExpSM/AKBSM hashes unchanged |
| `tools/verify_contextmemory_temporary_metadata_placement_api_adr.py` | temporary ContextMemory metadata placement API ADR exists, stays design-only, requires future scenario/test-only authority and TTL/expiration, forbids storage/writes/runtime wiring/behavior influence, and keeps existing safety verifiers passing |
| `tools/verify_contextmemory_temporary_metadata_placement_scaffold.py` | ContextMemory temporary metadata placement scaffold exists, requires explicit scenario/test authority and TTL/expiration, rejects write-like metadata, stays local-only/unwired, and leaves real ExpSM/AKBSM hashes unchanged |
| `tools/verify_akbsm_proposal_temporary_metadata_placement_adapter.py` | AKBSM proposal temporary metadata placement adapter requires explicit scenario/test authority and TTL/expiration, converts proposal review metadata into the generic local scaffold only, rejects write-like metadata, has no ContextMemoryManager/runtime wiring, and leaves real ExpSM/AKBSM hashes unchanged |
| `tools/verify_contextmemory_temporary_metadata_negative_retention.py` | negative/retention coverage verifies generic placement and AKBSM adapter reject missing/unknown authority, missing/invalid TTL/expiration, write-like keys/values/nested instructions, expire temporary metadata locally, preserve no runtime wiring, and leave real ExpSM/AKBSM hashes unchanged |
| `tools/verify_contextmemory_temporary_metadata_runtime_observation_adr.py` | temporary metadata runtime observation ADR exists, stays design-only, limits future observation to read-only diagnostics, forbids behavior influence/runtime wiring/storage/writes, and keeps existing safety verifiers passing |
| `tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py` | read-only temporary metadata observation scaffold exists, requires explicit diagnostic authority, ignores expired metadata as active metadata, proves no behavior/scoring/guard/Mode C/PolicyPressureReview/runtime wiring, and leaves real ExpSM/AKBSM hashes unchanged |
| `tools/verify_debug_name_dependency_audit.py` | debug-name audit schema and classifications remain valid |
| `tools/verify_legacy_semantic_decision_migration.py` | high-risk debug-name and legacy semantic decision debt remain resolved |
| `tools/verify_unknown_runtime_logic_split.py` | unknown runtime logic audit split remains clean |
| `tools/verify_memory_mutation_policy.py` | safe/draft/mutating memory write policy |
| `tools/verify_decay_semantics.py` | field decay semantics |
| `tools/verify_context_retention_policy.py` | ContextMemory retention |
| `tools/verify_context_side_list_retention_policy.py` | side-list retention |
| `tools/verify_real_input_scenarios.py` | ordinary audio/sensor real-input pipeline coverage, including scenario-only expansion fixtures |
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
- Reflection/pressure cannot influence behavior yet; behavior influence modes
  are documented only as proposed / discussion-only architecture.
- Mode C memory-gate advisory influence has disabled scaffold only and is not
  behavior-enabled.
- Mode C first-experiment source/target choice is accepted as design; the
  source is not connected to the target by default.
- `PolicyPressureReview` is observational-only.
- Mechanism-search is mostly next-tick material.
- AKBSM writes remain blocked by default.
- AKBSM write policy is design-only for permanent writes; no permanent AKBSM
  write path is implemented.
- Draft-only AKBSM association proposal scaffold exists, but the provider is
  disabled/no-op by default and no proposal storage or commit path is
  implemented.
- First enabled AKBSM draft proposal experiment is implemented only as a
  test/scenario provider path. The selected source is
  `AKBSMAssociationProbe` only, while AKBSMAssociationField and
  behavior/pressure/scoring/action/value/writer sources are deferred or
  forbidden.
- AKBSM draft proposal review lifecycle is design-only. Its states are
  metadata-only; `accepted_for_observation` is not AKBSM write approval; and no
  lifecycle transition execution, storage, commit path, or runtime behavior
  change is added.
- AKBSM draft proposal lifecycle state/record/result scaffold exists as
  metadata-only code. The first future controller/storage implementation should
  use scenario/test-only records and test-local provider/controller return
  values before any ContextMemory metadata.
- AKBSM draft proposal transition controller scaffold is implemented as
  metadata-only and test/scenario-only. Transition execution, storage, runtime
  wiring, and first storage beyond test-local controller return values are not
  implemented.
- AKBSM draft proposal transition controller scenario coverage exists as
  metadata-only fixture data and verifier checks. It does not add proposal
  storage, ContextMemory storage, runtime wiring, or commit/apply/save/write/
  persist/mutate paths.
- Future AKBSM proposal ContextMemory metadata integration is design-only. No
  ContextMemory integration is implemented; any future first integration must
  be temporary scenario/test-only metadata copies and must not create proposal
  storage, review record persistence, normal runtime wiring, or AKBSM writes.
- AKBSM proposal ContextMemory metadata scaffold exists, but it only creates
  temporary metadata payloads for scenario/test use. It does not write into
  ContextMemory, call `ContextMemoryManager`, persist review records, or create
  normal runtime wiring.
- AKBSM proposal ContextMemory metadata integration scaffold exists, but it is
  a deferred boundary result only. It does not place review records in
  ContextMemory, create permanent proposal storage, persist review records, or
  add normal runtime wiring.
- Temporary ContextMemory metadata placement API ADR exists, but the API is not
  implemented yet. Current AKBSM proposal ContextMemory integration remains
  Shape B/deferred boundary, real ContextMemory placement is still deferred, no
  proposal storage exists, no normal runtime wiring exists, and AKBSM writes
  remain blocked.
- ContextMemory temporary metadata placement scaffold exists, but it is
  scenario/test-only, requires explicit authority and TTL/expiration, accepts
  metadata-only temporary entries, rejects write-like metadata, is not wired
  into normal runtime, does not create permanent storage/queues, and keeps
  AKBSM proposal metadata non-authoritative for writes.
- AKBSM proposal temporary metadata placement adapter exists, but it only
  targets the generic local temporary metadata scaffold under explicit
  scenario/test authority and TTL/expiration; it adds no real ContextMemory
  writes or normal runtime wiring.
- Negative/retention coverage exists for generic temporary metadata placement
  and the AKBSM adapter, covering authority rejection, TTL/expiration rejection,
  invalid expiration, write-like metadata rejection, nested instruction
  rejection, and local expiration/removal without real memory mutation.
- Temporary metadata runtime observation ADR exists, but it is design-only.
  No runtime observation is implemented; future observation is read-only
  diagnostic material only, no normal runtime wiring exists, no behavior
  influence is approved, and AKBSM writes remain blocked.
- Read-only temporary metadata runtime observation scaffold exists, but it is
  local/scaffold-only and diagnostic-only. It requires explicit observation
  authority, ignores expired metadata as active metadata, has no normal runtime
  or `_run_tick()` wiring, creates no real ContextMemory writes, and does not
  influence behavior/scoring/guards/Mode C/PolicyPressureReview.
- Post-v0.0.2 safety architecture checkpoint is tagged as `v0.0.3`.
- Real-input scenarios are still simple audio/sensor probes, but now include
  mixed, stable, conflict, retention, value/target, and guard-audit coverage.
- Git status is unavailable in the current environment.
- One ambiguous runtime audit finding remains in demo/display code:
  `build_demo_image_from_memory()` splits image debug names for display.

## Recommended next work

1. Review `docs/adr_mode_c_first_experiment.md` before any implementation pass.
2. Review `docs/design_mode_c_memory_gate_influence.md` and answer remaining
   Mode C open questions before implementation.
3. Review `docs/adr_behavior_influence_modes.md` and decide whether Mode A
   remains the only accepted mode for the next pass.
4. Add deeper phase-level regression snapshots around selected marker windows.
5. Review `docs/adr_akbsm_write_policy.md` and
   `docs/design_akbsm_draft_association_proposal.md` and
   `docs/adr_akbsm_first_enabled_draft_proposal_experiment.md` before any AKBSM
   proposal implementation pass.
6. Review `docs/post_v0_0_2_safety_architecture_checkpoint.md` before any
   post-v0.0.2 safety tag or enabled behavior pass.
