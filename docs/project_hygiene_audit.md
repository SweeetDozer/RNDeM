# Project hygiene audit

Status: current repository/project hygiene checkpoint.

Post-v1.4 docs/audit/verifier pass:
`docs/design_short_memory_to_expsm_boundary.md` separates raw observations from
operational feedback, records existing writer-policy limitations, and defers
NFP persistence/schema migration. `tools/verify_short_memory_to_expsm_boundary_design.py`
checks documentation clauses only. Runtime, root Memory, tick order and old
verifier expectations remain unchanged; this pass does not merge or tag.

The subsequent isolated implementation is limited to three new processing
modules under `clc/experience/`, one fixture, one real verifier, and these
post-v1 references. The verifier uses AST import/call inspection and real
transitions to prove that grouping has no writer, Feedback, SimilarityObserver,
Activation, DecisionSelector, persistence, or `_run_tick()` authority. Existing
ExpSM-shaped operational state and root Memory hashes remain unchanged.

Post-v1.5 persistence design audit:
`docs/design_persistent_nfp_expsm_representation.md` records the absence of a
central schema/version-aware ExpSM loader and maps direct readers/writers. It
chooses record-level versioning, legacy/native coexistence and a no-write
creation-request boundary. The documentation verifier is
`tools/verify_persistent_nfp_expsm_representation_design.py`. No source under
runtime/ExpSM/writers and no root Memory file is changed by this pass.

The subsequent implementation adds one isolated production module, one fixture
and one real verifier. AST coverage confirms the module imports no writers,
mutation policy, runtime, SimilarityObserver, Activation, DecisionSelector or
Feedback path. It parses legacy/native representations without replacing the
existing loader, and canonical restart tests perform no filesystem writes.
Final record IDs remain owned by a future writer; migration and runtime wiring
remain deferred.

Post-v1.6 mutation-path audit:
`docs/design_nfp_expsm_mutation_path.md` records that runtime legacy commit uses
path-injected `ExpSMCommitWriter`, max-numeric+1 IDs and temp-file replacement,
while CRUD and draft storage have different/direct persistence behavior. The
design requires a shared strict store transaction, policy-gated native CREATE
and temporary-copy tests. `tools/verify_nfp_expsm_mutation_path_design.py`
checks this documentation contract. No writer, policy, Memory or runtime source
is modified in this pass.

Post-v1.3 Context/Short Memory design audit:
`docs/design_nfp_context_and_short_memory.md` inventories existing context,
operation queue, active field and local temporary-metadata infrastructure.
The existing ContextMemoryManager now has additive isolated NFP methods with
lazy imports; its constructor signature and apply_pending body are preserved.
Short Memory retains raw recent transitions with active-tick bounds; temporary
diagnostic metadata remains non-authoritative. The executable coverage is in
`tools/verify_nfp_context_short_memory.py` and `scenarios/nfp_context_short_memory.json`.
Normal runtime, Memory files, substrate/transduction/actuation and historical
checkpoint meanings are unchanged. No merge or tag is part of this code pass.

## Git status result

Working directory:

```text
/home/mors/Документы/RNDeM_CLC_Prototype
```

Git is now configured for this prototype repository.

```text
main tracks origin/main
origin uses git@github.com:SweeetDozer/RNDeM.git
v0.0.1 marks the stable RNDeM CLC prototype baseline
v0.0.2 marks expanded real-input scenario coverage
```

Current workflow recommendation:

- keep `main` stable;
- use short review branches for architecture/design passes;
- push review branches without automatic merge or tag unless explicitly asked;
- treat `docs/post_v0_0_2_safety_architecture_checkpoint.md` as a
  documentation checkpoint, not a runtime release;
- preserve baseline tags and memory-safety verifier expectations.

## Packaging files

Present:

- `.gitignore`
- `README.md`
- `main.py`
- `clc/`
- `tools/`
- `docs/`
- `Memory/`
- `scenarios/`

Missing:

- `pyproject.toml`
- `requirements.txt`
- `setup.cfg`
- `setup.py`
- `Makefile`

Current packaging state is script-oriented rather than installable-package
oriented. That is acceptable for the current prototype, but a future packaging
pass should decide whether to add `pyproject.toml`, dependency declarations, and
a standard test command.

## `.gitignore` audit

`.gitignore` now includes conservative cache/local artifact patterns:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
venv/
env/
.env
*.log
.DS_Store
Thumbs.db
```

It intentionally does not ignore:

- `Memory/`
- `docs/`
- `scenarios/`
- `*.json`
- `scenarios/regression_snapshots/*.snapshot.json`

Those paths contain source data, audit baselines, memory state, and scenario
baselines that need explicit project policy before being ignored.

## Generated and cache file policy

Safe generated/cache artifacts should stay ignored:

- Python bytecode and `__pycache__/`
- pytest/mypy/ruff caches
- virtual environments
- local `.env`
- OS metadata
- ad-hoc `*.log` audit output

Current root-level `*.log` files, if present, should remain local unless a later
audit-output policy says otherwise. This pass did not delete or move them.

## Memory tracking policy recommendation

Memory files are project state, not generic cache:

- `Memory/ExpSM/ExpSM_data.json`
- `Memory/ExpSM/ExpSM_drafts.json`
- `Memory/AKBSM/AKBSM_ne.json`
- `Memory/AKBSM/DB/*.nfp`
- `Memory/pattern_manifest.json`

Recommendation: do not broadly ignore `Memory/`. Decide explicitly whether
baseline memory is tracked, partially tracked, or stored outside Git. Until that
policy exists, keep verifiers checking real ExpSM/AKBSM hashes and avoid
mutating memory in safe-demo checks.

## Regression snapshot tracking recommendation

Regression snapshots should probably be tracked. They are compact baselines used
by `tools/verify_phase_regression_snapshots.py`, and they intentionally exclude
volatile IDs, raw memory dumps, and temporary paths.

Recommendation: keep tracking `scenarios/regression_snapshots/*.snapshot.json`
as reviewable baselines.

## ADR tracking recommendation

Architecture decision records are project state and should be tracked. Current
high-level ADRs include:

- `docs/adr_run_tick_phase_split_boundaries.md`
- `docs/adr_policy_pressure_influence_boundary.md`
- `docs/adr_behavior_influence_modes.md`
- `docs/adr_akbsm_write_policy.md`
- `docs/adr_akbsm_first_enabled_draft_proposal_experiment.md`
- `docs/adr_akbsm_draft_proposal_review_lifecycle.md`
- `docs/design_akbsm_draft_proposal_review_lifecycle_implementation.md`
- `docs/post_v0_0_2_safety_architecture_checkpoint.md`

`docs/adr_behavior_influence_modes.md` is proposed / discussion-only. It
documents future behavior influence modes without changing runtime behavior.

`docs/adr_akbsm_write_policy.md` is proposed / design-only. It documents that
AKBSM writes remain blocked by default and that future AKBSM write work needs
separate gates, verifiers, scenario coverage, auditability, and rollback.

`docs/post_v0_0_2_safety_architecture_checkpoint.md` summarizes safety
architecture after v0.0.2. It is the checkpoint documented by tag `v0.0.3`.

`docs/adr_akbsm_first_enabled_draft_proposal_experiment.md` now has a
controlled test/scenario-only implementation. It selects
`AKBSMAssociationProbe` as the only proposal source, defers
AKBSMAssociationField, forbids behavior/pressure/scoring/action/value, Mode C,
ExpSM, and memory writer sources, and leaves default runtime and AKBSM writes
unchanged.

`tools/verify_akbsm_probe_draft_proposal_experiment.py` verifies that this
experiment remains disabled by default, creates temporary metadata only from
`AKBSMAssociationProbe` when explicitly enabled by test/scenario policy,
rejects forbidden sources and commit-enabled proposals, avoids storage/wiring,
and preserves real Memory hashes.

`docs/adr_akbsm_draft_proposal_review_lifecycle.md` defines a design-only
future lifecycle for temporary AKBSM draft proposals. Lifecycle states are
metadata-only, no lifecycle state means commit/write/persist, review means
classification only, `accepted_for_observation` is not AKBSM write approval,
implementation is not added, and runtime behavior remains unchanged.

`tools/verify_akbsm_draft_proposal_review_lifecycle_adr.py` verifies the
lifecycle ADR text, metadata-only state/transition vocabulary, forbidden
write-like states and transitions, storage policy, doc references, and existing
AKBSM proposal safety verifiers.

`docs/design_akbsm_draft_proposal_review_lifecycle_implementation.md` is a
design-only implementation plan. Lifecycle implementation is still not added,
the first future implementation should be metadata-only and scenario/test-only,
test-local provider/controller return values are preferred before ContextMemory
metadata, no storage/writes/commit path exists yet, and AKBSM writes remain
blocked.

`tools/verify_akbsm_draft_proposal_lifecycle_implementation_plan.py` verifies
the design-only status, tentative future components, transition plan,
forbidden authorities, storage strategy, implementation sequence, doc
references, and existing AKBSM proposal safety verifiers.

`clc/runtime/akbsm_proposal_lifecycle.py` adds the isolated metadata-only
AKBSM proposal lifecycle state/record/result scaffold. It defines the allowed
state vocabulary, transition table, and test/scenario-only transition
controller scaffold, but does not add review service behavior, transition
execution, storage, normal runtime wiring, proposal
commit/apply/save/write/persist/mutate path, or AKBSM writes.

`tools/verify_akbsm_draft_proposal_lifecycle_state_scaffold.py` verifies the
state/record/result scaffold, exact allowed states/transitions, forbidden
write-like state names, absent transition execution/service/storage/wiring,
marker 36 absence, unchanged real Memory hashes, and existing AKBSM proposal
safety verifiers.

`docs/adr_akbsm_draft_proposal_transition_controller_experiment.md` defines a
design-only first metadata-only transition controller experiment. The
metadata-only transition controller scaffold is implemented, transition
execution is not implemented, the controller is test/scenario-only, allowed
first storage is test-local controller return values only, no proposal
storage/writes/commit path exists, and AKBSM writes remain blocked.

`tools/verify_akbsm_draft_proposal_transition_controller_adr.py` verifies the
transition controller ADR text, design-only status, controller shape, allowed
authority, forbidden authorities, transition semantics, storage policy, doc
references, and existing AKBSM proposal safety verifiers.

`tools/verify_akbsm_draft_proposal_transition_controller_scaffold.py` verifies
the transition controller scaffold, explicit test/scenario authority, exact
allowed transition behavior, forbidden/write-like transition rejection,
immutable record copy behavior, absent storage/runtime wiring, marker 36
absence, unchanged real Memory hashes, and existing AKBSM proposal safety
verifiers.

`scenarios/akbsm_transition_controller_metadata_coverage.json` and
`tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py` add
metadata-only scenario coverage for the transition controller. The coverage
proves allowed transitions, forbidden transitions, write-like target rejection,
immutable record copy behavior, unchanged proposals, metadata-only expiration,
absent proposal storage, absent ContextMemory storage, absent normal runtime
wiring, marker 36 absence, and unchanged real Memory hashes.

`docs/adr_akbsm_proposal_contextmemory_metadata_integration.md` defines a
design-only future temporary ContextMemory metadata integration. It allows only
scenario/test-only temporary metadata copies of AKBSM proposal review records
in a later explicit pass and forbids proposal storage, review record
persistence, permanent proposal queues, normal runtime wiring, behavior/scoring
influence, Mode C/PolicyPressureReview control, and AKBSM/ExpSM writes.

`tools/verify_akbsm_proposal_contextmemory_metadata_adr.py` verifies the ADR
text, design-only status, allowed temporary metadata shape, forbidden
data/instructions, forbidden authorities, TTL/retention requirements, rejected
alternatives, doc references, and existing AKBSM proposal safety verifiers.

`clc/runtime/akbsm_proposal_contextmemory_metadata.py`,
`scenarios/akbsm_proposal_contextmemory_metadata_scaffold.json`, and
`tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py` add
scenario/test-only ContextMemory-compatible metadata payload scaffold coverage.
The scaffold builds immutable temporary metadata payloads only, does not write
into ContextMemory, does not call `ContextMemoryManager`, does not persist
review records, adds no proposal storage, keeps normal runtime unwired, and
keeps AKBSM writes blocked.

`clc/runtime/akbsm_proposal_contextmemory_metadata.py`,
`scenarios/akbsm_proposal_contextmemory_metadata_integration_scaffold.json`,
and `tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py`
add scenario/test-only ContextMemory metadata integration boundary coverage.
The boundary returns temporary metadata-only deferred results, writes no review
records into ContextMemory, calls no `ContextMemoryManager`, creates no
permanent proposal storage or review record persistence, keeps normal runtime
unwired, and keeps AKBSM writes blocked.

`docs/adr_contextmemory_temporary_metadata_placement_api.md` and
`tools/verify_contextmemory_temporary_metadata_placement_api_adr.py` add a
design-only ADR for a safe temporary ContextMemory metadata placement API. The
API is not implemented yet, current AKBSM proposal ContextMemory integration
remains Shape B/deferred boundary, real ContextMemory placement is still
deferred, no proposal storage exists, no normal runtime wiring exists, and
AKBSM writes remain blocked.

`clc/runtime/context_temporary_metadata.py`,
`scenarios/contextmemory_temporary_metadata_placement_scaffold.json`, and
`tools/verify_contextmemory_temporary_metadata_placement_scaffold.py` add
scenario/test-only ContextMemory temporary metadata placement scaffold coverage.
The scaffold requires explicit authority, requires TTL/expiration, accepts
metadata-only temporary entries, rejects write-like metadata, remains local to
an explicitly created placement object, is not wired into normal runtime, does
not create permanent storage/queues, keeps AKBSM proposal metadata
non-authoritative for writes, and keeps AKBSM writes blocked.

`clc/runtime/akbsm_proposal_contextmemory_metadata.py`,
`scenarios/akbsm_proposal_temporary_metadata_placement_adapter.json`, and
`tools/verify_akbsm_proposal_temporary_metadata_placement_adapter.py` add
scenario/test-only adapter coverage from AKBSM proposal review metadata into
the generic local temporary metadata placement scaffold. The adapter requires
explicit authority and TTL/expiration, remains no-op without authority, rejects
write-like metadata, does not call `ContextMemoryManager`, creates no storage,
keeps normal runtime unwired, and keeps AKBSM writes blocked.

`scenarios/contextmemory_temporary_metadata_negative_retention_coverage.json`
and `tools/verify_contextmemory_temporary_metadata_negative_retention.py` add
negative/retention coverage for the generic placement scaffold and AKBSM
adapter. The coverage verifies authority rejection, TTL/expiration rejection,
invalid expiration rejection, write-like key/value/nested/instruction
rejection, local expiration/removal, no runtime wiring, no real ContextMemory
writes, and unchanged real ExpSM/AKBSM hashes.

`docs/adr_contextmemory_temporary_metadata_runtime_observation.md` and
`tools/verify_contextmemory_temporary_metadata_runtime_observation_adr.py` add a
design-only runtime observation boundary for temporary metadata. The ADR keeps
future observation read-only diagnostic, requires explicit observation
authority or a diagnostic flag, ignores expired metadata, forbids behavior,
scoring, guard, Mode C, `PolicyPressureReview`, memory writer, AKBSM writer,
storage, queue, and persistence influence, and leaves normal runtime wiring and
AKBSM writes blocked.

`clc/runtime/context_temporary_metadata_observation.py`,
`scenarios/contextmemory_temporary_metadata_runtime_observation_scaffold.json`,
and `tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py`
add a read-only diagnostic observation scaffold for local temporary metadata
placement state. The scaffold requires explicit diagnostic authority, keeps
observation authority separate from placement and write authority, ignores
expired metadata as active metadata, may report expired entries only as
diagnostics, returns metadata-only reports, has no normal runtime or
`_run_tick()` wiring, performs no real ContextMemory writes, and does not
influence behavior/scoring/guards/Mode C/PolicyPressureReview.

`scenarios/contextmemory_temporary_metadata_runtime_observation_negative_no_behavior.json`
and `tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py`
add negative/no-behavior hardening for the observer. The coverage verifies
missing/unknown/placement-authority rejection, observation authority cannot
place metadata or authorize writes, expired metadata remains inactive,
observation reports contain no writer commands or behavior/scoring/guard/Mode
C/PolicyPressureReview instructions, AKBSM proposal metadata remains
non-authoritative for writes, and the observer remains unwired from normal
runtime and `_run_tick()`.

`docs/adr_contextmemory_temporary_metadata_diagnostic_wiring.md` and
`tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_adr.py` add a
design-only ADR for first controlled diagnostic runtime wiring. Diagnostic
runtime wiring is not implemented yet, no runtime source code changed, no
`_run_tick()` wiring exists, the observer remains unwired from behavior paths,
no real ContextMemory reads/writes exist, no behavior/scoring/guard influence
exists, AKBSM proposal metadata remains non-authoritative for writes, and AKBSM
writes remain blocked.

`clc/runtime/context_temporary_metadata_diagnostics.py`,
`scenarios/contextmemory_temporary_metadata_diagnostic_wiring_scaffold.json`,
and `tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py`
add the explicit diagnostic runtime-facing scaffold. It is manually
authority-gated, wraps only the existing local observer, returns read-only
metadata-only reports, has no normal runtime or `_run_tick()` wiring, calls no
`ContextMemoryManager`, creates no storage or queues, performs no real
ContextMemory reads/writes, and includes no-behavior-influence checks in the
scaffold verifier.

`scenarios/contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.json`
and
`tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.py`
add negative/no-behavior hardening for the diagnostic wiring scaffold. The
coverage verifies diagnostic authority separation, no metadata placement or
write authorization by diagnostic authority, expired metadata active-ignore
behavior, no writer-command or behavior/scoring/guard/Mode C/
PolicyPressureReview instruction fields, no normal runtime or `_run_tick()`
diagnostic calls, no real ContextMemory reads/writes, and AKBSM proposal
metadata remaining non-authoritative for writes.

`docs/adr_contextmemory_temporary_metadata_tick_diagnostic_visibility.md` and
`tools/verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py`
add a design-only ADR for optional tick-facing diagnostic visibility. The ADR
prefers external diagnostic wrapper/harness, defers any direct `_run_tick()`
diagnostic hook, changes no runtime source code, adds no `_run_tick()` wiring,
keeps diagnostics unwired from behavior paths, adds no real ContextMemory
reads/writes, and leaves AKBSM writes blocked.

`clc/runtime/context_temporary_metadata_tick_diagnostics.py`,
`scenarios/contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.json`,
and `tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py`
add an external tick diagnostic wrapper scaffold. The scaffold runs only a
provided tick callable from an explicit diagnostic harness, passes no diagnostic
data into that callable, preserves behavior output, returns diagnostic snapshot
data separately, stays outside `_run_tick()`, remains read-only and
metadata-only, calls no `ContextMemoryManager`, creates no real ContextMemory
reads/writes, and includes no-behavior-influence checks in the scaffold
verifier.

`scenarios/contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.json`
and
`tools/verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py`
add negative/no-behavior hardening for the wrapper. The coverage verifies
authority separation, diagnostic authority cannot place metadata or authorize
writes, wrapped behavior output equals direct callable output with diagnostics
enabled or disabled, tick args/kwargs are unchanged, diagnostic data is not
passed into the callable, diagnostic snapshots are separate, no writer-command
or behavior/scoring/guard/Mode C/PolicyPressureReview instruction fields are
present, expired metadata is ignored as active metadata, and the wrapper remains
outside normal runtime and `_run_tick()` with no real ContextMemory reads/writes
and blocked AKBSM writes.

`docs/contextmemory_temporary_metadata_architecture_map.md` and
`tools/verify_contextmemory_temporary_metadata_architecture_map.py` add a
docs-only architecture map/checkpoint for the temporary metadata / AKBSM
proposal diagnostic ladder from `v0.1.0` through `v0.7.0`, plus the post-tag
hardening commits. The map documents component order, allowed local data flow,
authority separation, TTL/expiration semantics, no-write boundaries,
no-behavior-influence boundaries, runtime and `_run_tick()` boundaries,
verifier/scenario coverage, current safe stopping point, possible next branches,
and forbidden next steps.

`docs/contextmemory_temporary_metadata_architecture_diagram.md` and
`tools/verify_contextmemory_temporary_metadata_architecture_diagram.py` add a
docs-only visualization/checkpoint for the same ladder. The diagram uses
Mermaid and text blocks to show the component ladder, allowed data flow,
authority separation, no-write boundary, no-behavior-influence boundary,
runtime/`_run_tick()` boundary, safe stopping point, forbidden paths, and
related documents.

`docs/v1_readiness_criteria.md` and `tools/verify_v1_readiness_criteria.py`
add docs-only readiness criteria for a future `v1.0.0` safety-bounded prototype
checkpoint. The criteria define v1 as a review/stopping point, not AGI,
autonomous self-modification, AKBSM/ExpSM write permission, real ContextMemory
placement, direct `_run_tick()` hooks, default runtime diagnostics, or behavior
influence. The document also records required verifier, scenario, memory,
runtime, documentation, and release-validation invariants.

`docs/v1_release_checklist.md` and `tools/verify_v1_release_candidate.py` add a
docs/verifier-only release-candidate checklist for the future `v1.0.0` tag. The
checklist documents release blockers, required validation, stop-and-review
procedure, and the future tag command only. It does not tag `v1.0.0`, keeps
direct `_run_tick()` hooks deferred, keeps real ContextMemory placement absent,
and keeps AKBSM writes blocked.

`docs/natural_pattern_data_contract.md` and
`tools/verify_natural_pattern_data_contract.py` start post-v1 architecture work
as docs/verifier-only assets. They define natural activation patterns as the
future data substrate, reject labels/tokens/prompts as primary truth, and keep
v1 safety boundaries unchanged.

`docs/design_minimal_activation_pattern_substrate.md` and
`tools/verify_minimal_activation_pattern_substrate_design.py` refined that
contract into the implementation boundary for modality/origin/topology
NFP frames, windows, sequences, frame/window similarity, and reactivation while
forbidding persistence, sensor adapters, memory writes, and `_run_tick()`
wiring.

`clc/patterns/`, `scenarios/minimal_activation_pattern_substrate.json`, and
`tools/verify_minimal_activation_pattern_substrate.py` add the first isolated
post-v1 natural activation-pattern substrate implementation. It explicitly
preserves `NFPFrame -> NFPWindow -> NFPSequence`, is in-memory only,
immutable/effectively immutable, runtime-independent, and has no sensory
adapters, semantic recognition, persistence, AKBSM/ExpSM writes, real
ContextMemory placement, or `_run_tick()` wiring.

`docs/design_first_natural_pattern_transduction.md`,
`tools/verify_first_natural_pattern_transduction_design.py`, and
`tools/verify_first_natural_pattern_transduction.py` cover the first post-v1.1
natural-pattern source/transduction implementation. A tiny synthetic visual
scalar-field environment remains external test/scenario support,
RNDeM-facing data is label-free numeric sensory activation, and
camera/microphone/OpenCV integration, semantic recognition, memory writes,
persistence, real ContextMemory placement, and `_run_tick()` wiring remain
absent. The implemented code lives under `clc/transduction/` and scenario/test
support lives under `scenarios/support/`.

`docs/design_first_closed_loop_action_consequence.md`,
`tools/verify_first_closed_loop_action_consequence_design.py`, and
`tools/verify_first_closed_loop_action_consequence.py` cover the first
post-v1.2 closed-loop action/consequence implementation. It is isolated
scenario/test support only: harness-supplied `ACTION` + `ACTION_GENERATED`
NFPFrames become numeric-only actuator signals, mutate an external
scenario/test world, and return only as subsequent sensory NFP activation.
ACTION frames remain harness-generated, replayed/internal ACTION frames cannot
execute, world transitions return no semantic result, strict `T -> T+1`
causality is enforced, and same action values may have different sensory
consequences in different hidden world states. Autonomous action selection,
learning, success/failure/collision callbacks, reward/pain, runtime wiring,
persistence, ContextMemory placement, and AKBSM/ExpSM/chronicle writes remain
absent.

## Audit output tracking recommendation

`docs/debug_name_dependency_audit.json` and
`docs/debug_name_dependency_audit.md` are generated by audit tooling, but they
serve as current baseline reports. They may be tracked if the project wants
reviewable audit drift. If they become too noisy, keep the verifier output
tracked in docs and move raw generated reports to an ignored artifact directory
in a later packaging pass.

## NFP-Native Retrieval Design Audit

- The design and its verifier are documentation/tooling only; no retrieval
  source module, runtime import, scenario execution path, or writer was added.
- The verifier mechanically checks audited source constants/formulas and limits
  this branch to the expected documentation plus verifier files.
- Future retrieval fixtures must use temporary mixed stores, preserve both
  production Memory hashes, and prove byte-identical read-only behavior.
- Action materialization, ModeActionGuard treatment for structural ACTION,
  native Feedback and all writes remain explicit unresolved boundaries rather
  than hidden adapters.

## Recommended safe next actions

## NFP-native ExpSM CREATE Audit

- The isolated policy-gated CREATE source, shared store transaction, scenario,
  and real verifier are tracked explicitly.
- Production `Memory/ExpSM/ExpSM_data.json` and `Memory/AKBSM/AKBSM_ne.json`
  are hash-guarded by the verifier; mutation coverage uses temporary stores.
- Temporary files are unique siblings and are removed on failed writes. The
  shared transaction performs file fsync and best-effort directory fsync.
- The implementation is not imported or called by normal runtime and adds no
  proposal automation, native UPDATE, behavior influence, or secondary store.
- Recovery is read-only and has no create/write call; post-replace failures are
  not represented as safe retries.

## NFP-native ExpSM Retrieval Audit

- The isolated retrieval source, scenario fixture, and real verifier are
  tracked explicitly; verifier stores are temporary and freshly reopened.
- The native entry points extend existing SimilarityObserver, Activation, and
  DecisionSelector classes without parallel stages or normal runtime wiring.
- Production retrieval modules are AST-audited for absence of mutation policy,
  writers/transactions, Feedback, ActionTransducer, ModeActionGuard, and
  `_run_tick()` authority.
- Production Memory hashes are guarded; retrieval, competition, and selection
  leave bytes and operational counters unchanged.

1. Keep `main` stable and use review branches for design-only passes.
2. Decide whether baseline `Memory/` files are tracked project assets or
   operator-local state.
3. Decide whether root-level historical `*.log` files should be archived or
   removed.
4. Add `pyproject.toml` and dependency metadata only after current scripts and
   verifier commands are mapped.
5. Keep regression snapshots tracked as reviewable baselines.
6. Keep AKBSM proposal scaffolding disabled by default in normal runtime.
7. Keep the first enabled AKBSM draft proposal experiment test/scenario-only
   until a later explicit pass approves any storage or wiring.
8. Review `docs/adr_akbsm_draft_proposal_review_lifecycle.md` before any
   proposal lifecycle implementation, storage, commit, persistence, or wiring.
9. Review `docs/design_akbsm_draft_proposal_review_lifecycle_implementation.md`
   before adding transition execution, review controller/service code, storage,
   runtime wiring, or proposal commit behavior.
10. Review `docs/adr_akbsm_proposal_contextmemory_metadata_integration.md`
    before adding any temporary ContextMemory proposal metadata integration.
11. Review `docs/adr_contextmemory_temporary_metadata_placement_api.md` before
    implementing any safe temporary ContextMemory metadata placement API.
12. Keep ContextMemory temporary metadata placement scenario/test-only until a
    later explicit pass approves real placement semantics.
13. Keep ContextMemory temporary metadata runtime observation design-only until
    a later explicit pass adds read-only diagnostic scenarios and no-behavior-
    influence verification.
14. Keep the ContextMemory temporary metadata runtime observation scaffold
    local/scaffold-only until a later explicit pass approves normal-runtime
    diagnostic wiring with no behavior influence.
15. Keep observer negative/no-behavior coverage green before considering any
    normal-runtime diagnostic observation wiring.
16. Review `docs/adr_contextmemory_temporary_metadata_diagnostic_wiring.md`
    before adding any diagnostic runtime wiring surface.
17. Keep the explicit temporary metadata diagnostic scaffold manual-only until
    a later approved pass adds any broader diagnostic path with equivalent
    no-behavior-influence coverage.
18. Keep diagnostic wiring negative/no-behavior coverage green before any
    `_run_tick()` or normal runtime diagnostic wiring is considered.
19. Review `docs/adr_contextmemory_temporary_metadata_tick_diagnostic_visibility.md`
    before implementing any tick-facing diagnostic visibility.
20. Keep the external tick diagnostic wrapper scaffold outside `_run_tick()`
    unless a later ADR/pass explicitly approves a direct hook with equivalent
    no-behavior-influence coverage.
21. Keep external tick wrapper negative/no-behavior coverage green before any
    default runtime wiring or direct `_run_tick()` diagnostic hook is considered.
22. Use `docs/contextmemory_temporary_metadata_architecture_map.md` as the
    review checkpoint before any direct `_run_tick()` hook, real temporary
    ContextMemory placement, proposal storage, AKBSM writes, or behavior
    influence branch.
23. Use `docs/contextmemory_temporary_metadata_architecture_diagram.md` as the
    visual review aid for the same boundaries before choosing any runtime or
    storage integration branch.
24. Use `docs/v1_readiness_criteria.md` as the release-boundary checklist
    before considering any `v1.0.0` tag.
25. Use `docs/v1_release_checklist.md` and
    `tools/verify_v1_release_candidate.py` for the final release-candidate
    review before any separate `v1.0.0` tag pass.
26. Treat `docs/natural_pattern_data_contract.md` as post-v1 architecture work:
    it is a design contract for future natural activation-pattern data, not a
    runtime implementation, sensor adapter, file input API, AKBSM write policy
    change, or ContextMemory placement approval.
27. Treat `docs/design_minimal_activation_pattern_substrate.md` and the
    isolated `clc/patterns/` package as the review gate before any source,
    transduction, persistence, ContextMemory, AKBSM, ExpSM, or `_run_tick()`
    integration.
28. Review `docs/design_first_natural_pattern_transduction.md` before
    implementing any isolated synthetic visual environment, label-free
    `VisualFieldTransducer`, or `NFPWindowAssembler`.

## Remembered Action Guarded-Execution Design

- The design and isolated production implementation are mechanically checked by
  dedicated verifiers and scenario metadata.
- Retrieval, selection, normal runtime orchestration, phase order, and Memory
  remain unchanged; the existing guard has only a typed native allow/deny entry.
- Persistent source identity stays distinct from fresh occurrence identity;
  exact before-context and exactly-once post-world failure are tested. No
  Feedback, writes, automatic execution, or `_run_tick()` wiring is added.

## NFP-Native Feedback Design

- The design audits legacy formulas, ObservedEffect bounds, policy modes,
  transaction recovery and bounded replay behavior against current source.
- Native HIT/MISS is structural prediction reliability only; no utility,
  reward, neighbor reinforcement or structural rule rewrite is introduced.
- Evaluation and mutation are separate, and no production source, scenario,
  runtime phase or Memory file changes in this pass.
