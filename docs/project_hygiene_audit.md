# Project hygiene audit

Status: current repository/project hygiene checkpoint.

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

## Audit output tracking recommendation

`docs/debug_name_dependency_audit.json` and
`docs/debug_name_dependency_audit.md` are generated by audit tooling, but they
serve as current baseline reports. They may be tracked if the project wants
reviewable audit drift. If they become too noisy, keep the verifier output
tracked in docs and move raw generated reports to an ignored artifact directory
in a later packaging pass.

## Recommended safe next actions

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
