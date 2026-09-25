# Design: Policy-Gated NFP-Native ExpSM Mutation Path

Status: design/audit/verifier only, based on v1.6.0 (`92729f6`). No writer,
policy, runtime or Memory file is changed by this pass.

## Checkpoint And Scope

| Checkpoint | Boundary |
|---|---|
| v1.1.0 | NFP substrate |
| v1.2.0 | world -> sensory NFP |
| v1.3.0 | ACTION -> world -> sensory consequence |
| v1.4.0 | active present + recent raw past |
| v1.5.0 | observed experience evaluation/grouping |
| v1.6.0 | persistent NFP-native representation survives restart |
| Next | policy-gated authoritative creation of one NFP-native ExpSM record |

The first implementation is CREATE only and isolated from normal runtime. It
does not activate, compare, select or update a native record.

## Actual Current Writer And Store Audit

`Memory/ExpSM/ExpSM_data.json` is one object with `experience` and `reflexes`
maps. Experience IDs are string keys; current checked-in records are legacy
`if`/`then`/`result`/`recommendation` records with hits, misses, confidence,
repeatability, status and timestamps. There is no file-level or legacy-record
representation version.

The runtime legacy creation path is `MemoryDraftWriter` -> reviewed draft in
`ExpSM_drafts.json` -> `ExpSMCommitWriter.run()`. Commit requires consolidation
mode, a recent commit decision, `allow_expsm_commit`, a ready reviewed legacy
draft and non-technical `if` patterns. The writer computes confidence from
draft average confidence and repeatability from seen/support counts, creates
hits=0 and misses=0, and writes legacy fields only. It also deduplicates by
legacy `draft_signature`; that rule is not valid for native creation.

`ExpSMCommitWriter` owns runtime legacy ID allocation. `_next_experience_id`
ignores nonnumeric keys and returns `max(numeric IDs, default 0) + 1`; gaps are
not compacted and existing IDs are not renumbered. Allocation occurs after
loading the store but before the final write. There is no lock, process-wide
critical section or compare-and-swap, so concurrent writers can race.
`Memory/ExpSM/Exp_CRUD.py` independently uses the same max+1 convention, keeps
an in-memory store and writes directly with `open("w")`; it is not the runtime
reviewed commit path and its save is not atomic.

Commit/update writers accept explicit draft and ExpSM paths, so temporary copied
stores are already possible. Their `_atomic_write_json` writes a fixed sibling
`.tmp`, closes it, then calls `Path.replace`. This prevents a partially written
destination when serialization/write fails before replace, but there is no
file or directory fsync, no unique temporary name, no locking, and no recovery
protocol. Two concurrent writers can collide on the temp path. Commit also
writes ExpSM and draft files sequentially, so failure on the second replacement
can leave cross-file state inconsistent. `OSError` becomes a module-update
failure operation; malformed JSON becomes `ValueError` and then a failure
operation. Unexpected serialization/type errors are not comprehensively mapped.

Current `_load_expsm_store` requires a top-level object, but replaces a
non-object `experience` or `reflexes` section with `{}`. That permissive repair
is unsafe for native creation because it could erase malformed existing data.
No complete-store schema validation or post-write readback exists. Existing
top-level keys and records otherwise survive whole-file rewrite.

`ExpSMUpdateWriter` is a separate legacy metadata update path for confidence,
repeatability and metadata. `ExpSMOutcomeFeedback` and value-feedback writers
also have their own update concerns. NFP-native update support is deferred.

## Actual Mutation-Policy And Draft Audit

`MemoryMutationPolicy` has three profiles and independent flags:

| Profile | Actual behavior relevant here |
|---|---|
| `safe_demo` | `allow_expsm_commit=False`; draft writes are allowed only when `memory_is_temporary=True`; no authoritative native creation |
| `draft_only` | `allow_draft_writes=True`, but commit/update/value-feedback flags are false; no authoritative native creation |
| `mutating_memory` | draft, ExpSM commit/update and value-feedback update flags are true; AKBSM remains false |

Draft-only is not merely a name: `MemoryDraftWriter` can persist legacy-shaped
reviewed drafts to the configured `ExpSM_drafts.json`. That schema contains
pattern-ID drafts and legacy commit review state, not
`ExpSMRecordCreationRequest`. The first native creation implementation must not
invent another draft file or squeeze structural NFP values into this legacy
schema. In safe/demo or draft-only policy, a valid native request receives a
normal `DENIED_BY_POLICY` result and remains an inspectable in-memory request.
The existing legacy draft subsystem remains unchanged. A later ADR may extend
that same subsystem version-aware if durable native drafts are actually needed.

Only `mutating_memory` with `allow_expsm_commit=True` may authorize permanent
native creation. Flags for draft, update or value feedback do not imply create
authority. Policy affects authority only; it must never alter context/action/
effect content.

## Authority Separation

```text
ExpSMRecordCreationRequest = validated requested cognitive content
MemoryMutationPolicy       = whether authoritative mutation is permitted
ExpSM store writer         = mechanism performing permitted persistence
NFPExpSMRecordV1           = resulting persistent logical record
```

Therefore request creation != permission; permission != persistence mechanism;
persistence mechanism != operational activation. The immutable request gains no
`save`, `commit`, `persist` or filesystem method. Proposal and request can never
call a writer directly.

## Request Validation Boundary

Add a pure `validate_expsm_creation_request(request)` equivalent before policy
evaluation and again at the typed writer boundary. It accepts only the concrete
`ExpSMRecordCreationRequest`, never an arbitrary dict. It checks:

- kind is `nfp_native` and representation version is exactly 1;
- complete context, ACTION and signed effect structures;
- finite activations in [0,1] and finite deltas in [-1,1];
- context/effect modality and topology compatibility;
- valid requested hits/misses/confidence/repeatability;
- valid immutable creation provenance and positive source_support_count;
- initialization profile is the approved `legacy_crud_defaults_v1`;
- no final record_id, filesystem path or live cognitive object exists;
- canonical JSON conversion succeeds with `allow_nan=False`.

Schema validation and policy authorization are distinct. A valid request may be
denied; an allowed policy cannot legalize malformed or unsupported content.
V1 writer input is typed and complete, so it cannot fill missing context/action/
effect from ContextMemory, ShortMemory or global state. Unknown representation
versions never reach mutation. The current v1.6 raw parser tolerates unrelated
extra raw keys, but the creation path emits only the exact V1 allowlist from
typed values; no arbitrary-extension escape hatch is provided.

## Canonical Writer Extension

Choose option C: narrowly extract/reuse a common ExpSM store transaction
primitive from the existing `ExpSMCommitWriter` architecture. Do not introduce
an NFP database or second store. The primitive owns configured path, strict
load, max+1 allocation, complete serialization and atomic replacement. Existing
legacy commit behavior must be routed through it without changing legacy draft
validation, signature dedupe, record fields or operation payloads. This common
primitive needs focused legacy regression tests because it touches shared I/O.

A small policy-gated native creation orchestrator may sit beside the existing
commit writer. It accepts only a typed request, validates it, checks the actual
`MemoryMutationPolicy`, and invokes the common store transaction. It is an
extension of the existing writer architecture, not a parallel writer/database.
It is configured with an explicit store path for temporary tests. Cognitive
request/record objects never contain that path.

Legacy `ExpSMCommitWriter` remains canonical for legacy reviewed drafts.
`ExpSMUpdateWriter`, CRUD and Feedback paths are unchanged. Native CREATE is
the only new mutation; native hits/misses/confidence/repeatability updates are
deferred until operational selection identity is stable.

## Writer-Owned ID And Materialization

Inside one writer-owned mutation operation:

```text
strictly load current store
-> validate top-level and section shapes
-> allocate max(numeric experience IDs) + 1
-> materialize request + allocated ID as NFPExpSMRecordV1
-> append under experience[record_id]
-> validate the resulting native record/store shape
-> serialize the complete store
-> atomically replace destination
-> report confirmed record ID/record
```

The caller never computes or reserves an ID. Given IDs 1, 2 and 7, the new ID
is 8. Existing IDs and records remain untouched. The first implementation is
single-process only; the operation must hold one in-process writer lock across
load/allocation/write to avoid known threads sharing the writer boundary, while
cross-process/distributed locking is deferred and documented as unsupported.
No ID is considered consumed before successful replacement.

`request_id != record_id`. Request replay is not idempotent: two separately
authorized submissions may create two IDs and two records. Equal canonical
content is not a dedupe key. Native creation never searches SimilarityObserver
or merges with/increments a similar record. Idempotency would require a future
request ledger and explicit policy.

After authorization and ID allocation, deterministic materialization uses the
v1.6 request values unchanged. Initial metadata is the request's validated
`legacy_crud_defaults_v1`: hits=0, misses=0, confidence=.5,
repeatability=.5. `source_support_count` remains creation provenance, never hits
or confidence. Source proposal ID, source support and creation tick are immutable
creation history; normal Feedback must not rewrite them.

## Mixed Store And Compatibility

Native V1 records live in the existing top-level `experience` map beside legacy
records. No separate native list and no file-level version are required because
each native record has `record_kind` and `representation_version`; unversioned
known-shape records remain legacy. `reflexes` and unrelated top-level data are
preserved. No eager migration, renumbering or normalization occurs.

Before mutation, snapshot and validate the store as an object with object-valued
`experience` and `reflexes` sections. Existing record values must be objects;
known native records must parse through the v1.6 adapter. Legacy records remain
opaque to native conversion but must satisfy the established minimum legacy
shape used by coexistence tests. Malformed sections or existing native records
produce `STORE_INVALID`; never replace them with empty maps.

After an isolated write, all legacy IDs, if/then/result/recommendation,
hits/misses/confidence/repeatability must compare equal to the pre-write
snapshot. The new raw record must parse as `NFP_NATIVE_V1` through the v1.6
adapter and structurally equal the request. Writer serializes; adapter parses;
the writer does not create another interpretation.

## Atomicity And Failure Safety

Minimum future behavior improves the shared temp/replace primitive narrowly:

1. validate request, policy and current complete store before mutation;
2. create the complete candidate store in memory without mutating authoritative
   in-memory state;
3. serialize deterministically with strict finite JSON to a unique sibling temp;
4. flush and `os.fsync` the file, close it, then `os.replace` in the same
   directory; fsync the parent directory where supported;
5. clean a leftover temp on failure and retain the old destination;
6. reload/parse in verifier after success.

No partial record becomes authoritative before replacement. A controlled
replace/write failure test uses an injected store primitive/failure hook, not
permission hacks against real Memory. The original store must remain readable
and byte-identical.

`WRITE_FAILED` and `READBACK_FAILED` belong to opposite sides of the
authoritative replacement boundary:

- **WRITE_FAILED:** failure occurs before successful authoritative atomic
  replace. The previous store remains intact, no new record is considered
  persisted, and an explicit retry may be possible after resolving the cause.
- **READBACK_FAILED:** atomic replace completed successfully, or is known to
  have crossed the authoritative replacement boundary, but fresh verification
  through the normal reader/adapter could not confirm the new record. The
  authority state is `INDETERMINATE_FROM_CALLER_PERSPECTIVE`: the new native
  record may already exist authoritatively on disk. This is not equivalent to
  "nothing was written" and is not `WRITE_FAILED`.

Hard invariant: `READBACK_FAILED` MUST NOT automatically retry the same
`ExpSMRecordCreationRequest`. The first write may already have created the
record; retry could allocate a second writer-owned ID. No content deduplication,
request-ID idempotency or automatic rollback is introduced.

Once replace succeeds, the first mutation implementation cannot claim to
restore the previous authoritative store. Such a claim would require a separate,
designed and proven backup/rollback protocol, which does not exist here.
`READBACK_FAILED` is a recovery/reconciliation state, not a transactional
rollback state. Validation before replace should make ordinary invalid requests
impossible at this stage; readback failure indicates an I/O, corruption or
verification problem requiring fresh inspection.

The fixed `.tmp`, absent fsync and absent locking in current commit writer are
known gaps. Improving the common primitive may alter legacy persistence
mechanics and therefore requires exact legacy create/update and failure
regressions. Do not route native creation through direct `ExpSMCRUD.save()`.

## Mutation Result Model

Use an immutable `ExpSMCreateResult` equivalent with persistence-only statuses:

```text
CREATED
DENIED_BY_POLICY
INVALID_REQUEST
UNSUPPORTED_REPRESENTATION
STORE_INVALID
WRITE_FAILED
READBACK_FAILED
```

Fields: status, `record_id: str | None`,
`record: NFPExpSMRecordV1 | None`, `attempted_record_id: str | None`, and stable
reason/code. `record_id` is confirmed authoritative identity and only `CREATED`
returns it with a confirmed record. `attempted_record_id` is an optional,
non-authoritative recovery hint for `READBACK_FAILED`; its presence never means
that persistence was confirmed and it is never substituted for `record_id`.
Only confirmed `CREATED` returns ID and record.

Denial is a normal non-authoritative outcome, not an application error.
Invalid/unsupported/store failures and pre-replace `WRITE_FAILED` return no
authoritative record. `READBACK_FAILED` also returns no confirmed authoritative
record object, but its attempted ID records which writer-owned key must be
reinspected because the new bytes may already be authoritative. Statuses
describe persistence, never good/bad/successful experience semantics.

## READBACK_FAILED Recovery

Recovery is read-only reconciliation, never an implicit second mutation:

1. stop automatic mutation and retry for this request;
2. discard writer-local and in-memory assumptions;
3. reopen the target ExpSM store through a fresh read path;
4. validate the complete store structure;
5. inspect `attempted_record_id` (or an equivalent explicit recovery token);
6. if present, parse that raw record through the normal v1.6 adapter and require
   `NFP_NATIVE_V1`;
7. compare context, action, effect, operational metadata and allowed creation
   provenance with the original request;
8. produce one recovery conclusion without writing.

Recovery conclusions are distinct from normal create statuses:

- `CONFIRMED_PERSISTED`: the attempted ID exists, parses as NFP_NATIVE_V1 and
  exactly matches the request. The first mutation did persist authoritatively;
  this confirms that write and must not resubmit or create a second record.
- `CONFIRMED_ABSENT`: fresh inspection positively proves the attempted ID is
  absent, the complete store is otherwise valid, and there is no evidence of
  the attempted native record. Recovery still performs no retry; any later
  mutation attempt must be a new explicit action.
- `UNRESOLVED_OR_STORE_INVALID`: the store is unreadable/malformed, the attempted
  ID contains unexpected content, the native record is malformed, payload does
  not match, or authority otherwise cannot be established. No automatic retry,
  overwrite, rollback or second record creation is allowed; explicit
  higher-level inspection is required.

All recovery tests use temporary copied stores. They never inject readback
failure into checked-in `Memory/ExpSM/ExpSM_data.json`.

## Required Isolated Scenarios

All mutation tests use an explicitly configured temporary directory and copied
ExpSM store. They snapshot production Memory hashes and root file inventory.

1. **Safe mode:** valid request + `safe_demo` -> `DENIED_BY_POLICY`; bytes
   unchanged and no ID allocated/consumed.
2. **Draft mode:** valid request + `draft_only` -> `DENIED_BY_POLICY`; no native
   draft file is invented; existing legacy draft subsystem behavior is unchanged.
3. **Authoritative create:** copied mixed-capable store + `mutating_memory` ->
   one new native V1 record with writer ID, exact payload/provenance/defaults.
4. **Legacy preservation:** every old ID and legacy semantic/operational field
   remains equal; no migration or renumbering.
5. **ID gap:** 1,2,7 -> 8; a second approved equal request -> 9 and a distinct
   record; canonical JSON/content hash performs no dedupe.
6. **Malformed/unsupported:** invalid ranges, live/missing content or version
   999 -> invalid/unsupported result before policy/write; bytes unchanged.
7. **Store invalid:** malformed JSON, wrong section type or malformed existing
   native record -> `STORE_INVALID`; no replacement.
8. **Write failure:** injected failure before replace -> `WRITE_FAILED`; old
   bytes intact, no partial native record and no authoritative returned record.
9. **Forced post-replace readback failure:** complete serialization and atomic
   replace succeed, then injected fresh readback verification fails. Result is
   `READBACK_FAILED`, not `WRITE_FAILED`; no confirmed record is returned,
   attempted_record_id is retained as a recovery hint, and blind retry is
   forbidden.
10. **READBACK_FAILED recovery:** a fresh reader inspects the temporary store by
    attempted ID. In the common successful-replace case the record parses as
    NFP_NATIVE_V1 and matches the request, yielding `CONFIRMED_PERSISTED` without
    a retry or second record. Tests/design also retain `CONFIRMED_ABSENT` and
    `UNRESOLVED_OR_STORE_INVALID` branches without automatic mutation.
11. **Readback/restart:** after ordinary successful create, destroy writer/request/runtime objects;
   fresh JSON load and v1.6 adapter parse returns NFP_NATIVE_V1 structurally
   equal to request under assigned ID.
12. **No behavior:** no SimilarityObserver, Activation, DecisionSelector,
    Feedback, mechanism search or `_run_tick()` call occurs.

## Operational And Memory Boundaries

Persistence != active retrieval. A newly written native record remains dormant:
SimilarityObserver is unchanged; Activation top-N receives no native candidate;
DecisionSelector sees no new action; Feedback performs no native update. No
automatic path connects ShortMemory, grouping threshold, proposal creation or
eviction to mutation. The chain remains explicit:

```text
candidate -> proposal -> request -> explicit mutation attempt -> policy -> writer
```

No AKBSM or Chronicle write occurs. Normal runtime and `_run_tick()` remain
unchanged. After creation stability, a separate design may cover persistent
native record -> comparison adapter -> SimilarityObserver -> Activation top-N
-> DecisionSelector. Feedback for selected native identity is a later review.

## First Implementation And Deferred Scope

## Implementation Status

The first isolated CREATE implementation is now present in
`clc/experience/expsm_native_create.py`. Its persistence mechanics are shared
with legacy commit writing through
`clc/consolidation/expsm_store_transaction.py`; legacy draft validation,
signature deduplication, record shape, and operation payloads remain unchanged.
The shared transaction uses a unique sibling temporary file, flush plus file
fsync, atomic replacement, best-effort directory fsync where supported, and
failure cleanup. Cross-process writers remain unsupported.

The native path strictly validates the request before policy authorization,
rejects malformed authoritative stores without repair, and permits creation
only when the actual policy grants `allow_expsm_commit`. `CREATED` requires a
fresh strict store load and V1 adapter comparison. A pre-replace failure yields
`WRITE_FAILED`; a post-replace verification failure yields `READBACK_FAILED`,
an unconfirmed `attempted_record_id`, and
`INDETERMINATE_FROM_CALLER_PERSPECTIVE`. The separate reconciliation helper is
read-only and returns confirmed-persisted, confirmed-absent, or unresolved.

Coverage is in `tools/verify_nfp_expsm_policy_gated_create.py` and
`scenarios/nfp_expsm_policy_gated_create.json`. All mutation cases use temporary
stores. Native records remain dormant: there is still no automatic proposal
persistence, normal runtime wiring, native UPDATE, retrieval/activation,
selection, Feedback, AKBSM, or Chronicle path.

The post-`v1.7.0` read-only consumer boundary is designed separately in
`design_nfp_expsm_operational_retrieval.md`. Retrieval does not grant mutation
authority: it must not import the native CREATE writer, update operational
counters, or treat recall/selection as Feedback.

Implemented in this pass: typed request validator; policy-gated create orchestration;
shared/version-aware extension of existing ExpSM store writing; writer-owned ID;
native V1 materialization; temporary-store atomic failure tests; reload/readback.

Deferred: normal runtime wiring; automatic/background/sleep consolidation;
native operational comparison/retrieval/Activation/selection; all native
Feedback/update behavior; cross-process locking; request-id ledger/idempotency;
legacy migration; file-level schema envelope; AKBSM/Chronicle conversion;
semantic success/failure/reward/goals/needs evaluation.

## Read-Only Consumer Update

Native operational comparison, retrieval, Activation competition, and typed
selection now exist as an isolated read-only consumer. This does not extend the
mutation authority described here: retrieval imports/calls no policy, CREATE,
transaction, commit, update, or Feedback writer. It leaves all operational
counters and store bytes unchanged. Native Feedback/UPDATE, action
materialization/execution, and `_run_tick()` wiring remain deferred.

## Native Feedback Update Handoff

`docs/design_nfp_native_feedback.md` requires a fresh exact-ID authoritative
read and reuse of `ExpSMStoreTransaction` for any future native operational
update. `safe_demo` and `draft_only` deny it; `mutating_memory` may permit it.
Post-replace `READBACK_FAILED` remains indeterminate and forbids blind retry.
The isolated `NFPFeedbackApplyWriter` now implements this exact-record
operational UPDATE using the shared transaction. It fresh-loads and parses the
source ID, requires exact TargetCore continuity, then enforces
`allow_expsm_update`. Mutable metric drift is accepted and fresh counters are
authoritative. One HIT or MISS increments one counter; confidence and
repeatability use updated counters. Immutable learned structure and all other
records are preserved.

`safe_demo` and `draft_only` deny while `mutating_memory` may write.
`WRITE_FAILED` is pre-replace and retry-safe; `READBACK_FAILED` is post-replace
and indeterminate, with read-only reconciliation and no blind retry. No CREATE
fallback, replay ledger, automatic Feedback path, runtime wiring, AKBSM write,
or Chronicle write is added.
