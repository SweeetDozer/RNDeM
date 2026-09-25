# Design: Persistent NFP-Native ExpSM Representation

## Status And Checkpoints

Originally approved as a design/audit boundary based on v1.5.0 (`35d0660`).
The isolated representation layer is implemented in
`clc/experience/expsm_representation.py`; this document defines the
representation boundary after transient ExpSMConsolidationProposal. The V1
parser, adapter, and creation request now exist, as does a later isolated
policy-gated CREATE writer; schema migration and normal runtime wiring do not.

| Checkpoint | Established scope |
| --- | --- |
| v1.1.0 | NFP substrate |
| v1.2.0 | world -> sensory NFP |
| v1.3.0 | ACTION -> world -> sensory consequence |
| v1.4.0 | active present + bounded recent raw past |
| v1.5.0 | repeated observed-experience evaluation and transient candidates/proposals |
| v1.6.0 | stable persistent NFP-native representation without write authority |
| Post-v1.6 | isolated policy-gated CREATE, still without runtime activation |

Compatibility decision B is preserved: the legacy schema cannot accept native
context/action/effect unchanged. JSON's ability to hold arbitrary keys is not
semantic compatibility.

## Current Persistent ExpSM Audit

`Memory/ExpSM/ExpSM_data.json` is one JSON object with exactly the conventional
sections `experience` and `reflexes`. It has no file-level schema/version field.
At this checkpoint `experience` is a map with string IDs `2` and `3`; `reflexes`
is empty. IDs are external map keys, not fields required in every record.

Legacy experience fields are `level`, `if`, `then`, `result`, `recommendation`,
`confidence`, `repeatability`, `source`, `status`, `hits`, `misses`,
`created_at_world`, `updated_at_world`, plus optional `metadata` and
`value_feedback`. The four pattern fields are lists of pattern references/IDs,
not serialized clc.patterns values. Current records contain no `record_kind`,
`representation_version`, native topology, ordered activation window or signed
effect vector. Legacy metadata contains draft `support_count`; that is unrelated
to the v1.5 proposal support unless an explicit future adapter says otherwise.

Actual readers and writers are distributed rather than mediated by one schema:

| Path | Current behavior and constraint |
| --- | --- |
| `Memory/ExpSM/Exp_CRUD.py` | Loads JSON, merely adds missing section maps, deep-copies reads, accepts arbitrary update fields, writes whole file non-atomically. `create_experience` defaults hits/misses 0, confidence/repeatability .5. Numeric `_next_id` is max numeric key + 1; IDs are never reused and deletion archives/tombstones. No schema validation/version dispatch. |
| `clc/storage_models/expsm_adapter.py` | Read-only legacy adapter accepts map or list sections, recognizes aliases experience(s)/reflex(es), resolves `if` refs through PatternStore, warns/skips `NFP` placeholders, and may install process-only demo fallback records. It cannot parse clc.patterns windows or signed effects. |
| `clc/expsm/expsm_similarity_observer.py` | Independently loads experiences; requires nonempty legacy if/then/result and compares weighted Jaccard (.45/.30/.20/.05). It has no representation dispatch. |
| `clc/expsm/expsm_activation_module.py` | Independently loads records and matches legacy `if` IDs against ActiveContextField; returns top 3. It reads confidence/repeatability/hits/misses and cannot activate native windows. |
| `clc/expsm/expsm_mechanism_search.py` | Independently loads legacy fields and ranks target-related mechanisms. NFP-native context/action/effect has no current mechanism mapping. |
| `clc/expsm/expsm_outcome_feedback.py` | Independently loads and writes the whole JSON file; selected/linked record ID receives hits/misses/confidence/repeatability changes. It is not gated by MemoryMutationPolicy itself. |
| `clc/evaluation/value_feedback_memory_view.py` | Independently reads per-record value_feedback metadata by experience ID. Its operational view can remain record-ID based if the record kind is supported. |
| `clc/consolidation/expsm_commit_writer.py` | Policy-gated legacy draft writer; whole-file atomic temp replacement. Allocates max numeric ID + 1, writes legacy pattern lists, hits/misses 0, confidence from draft avg_confidence and repeatability from seen/support. Deduplicates by legacy draft signature. |
| `clc/consolidation/expsm_update_writer.py` | Policy-gated whole-file metadata update; blends confidence .65 old/.35 draft and updates repeatability/support metadata. Assumes legacy draft lifecycle. |
| `clc/evaluation/value_feedback_update_writer.py` | Policy-gated whole-file update of value_feedback metadata for an individual experience ID. |
| `clc/runtime/clc_runtime.py` | Constructs ExpSMAdapter, SimilarityObserver, Activation, mechanism search, feedback and writers directly over the same path, then reloads the adapter after writes. There is no central version-aware repository. |

The reader/parser audit therefore finds no authoritative persistent schema
validator and no checksum/content hash. Current JSON formatting uses ordinary
`json.load`/`json.dump`; writer variants differ in `ensure_ascii` and newline,
so byte formatting is not identity. No mandatory content hashing is introduced.

MemoryMutationPolicy has actual profiles: `safe_demo` permits draft writes only
when memory is temporary and blocks ExpSM commit/update/value feedback;
`draft_only` permits drafts but blocks those permanent operations;
`mutating_memory` permits draft, ExpSM commit/update and value-feedback update.
AKBSM writes remain blocked in every profile. Low-level CRUD and
ExpSMOutcomeFeedback are important legacy exceptions: policy flags are not a
universal filesystem sandbox. A new writer must never bypass an explicit gate.

## Representation Decision

Compatibility decision B is preserved.

Use record-level explicit discrimination. A new operational experience is:

```text
record_kind = "nfp_native"
representation_version = 1
```

Records from the known legacy baseline that lack both fields are classified
explicitly as `legacy`, not guessed to be NFP-native from nested field presence.
Any partially tagged record is malformed. Unknown kind or NFP-native version is
unsupported/non-loadable. New code must never infer a representation from the
presence of `context_pattern` or other convenient fields.

No file-level version is required for Stage 1 because coexistence occurs inside
the existing `experience` map and adding one is unnecessary to read legacy data.
Record-level discrimination is mandatory. A future file envelope version may be
added only for store-level semantics, independently from representation_version;
it cannot replace record-level kind/version while representations coexist.

## Serialized Cognitive Values

These are explicit JSON-safe value schemas, not live objects and not arbitrary
`dataclasses.asdict()` output. Canonical objects contain dict/list/string/integer
and finite float primitives only. Tuples become JSON arrays; tuple/list identity
has no semantic meaning. No pickle, Python repr or class-qualified object dump.

`SerializedNFPFrameV1`:

```json
{
  "modality": "action",
  "topology": {"shape": [2]},
  "values": [0.0, 1.0]
}
```

`SerializedNFPWindowV1`:

```json
{
  "modality": "visual",
  "topology": {"shape": [16, 16]},
  "frames": [{"values": [0.0, 0.1]}, {"values": [0.2, 0.1]}]
}
```

Window length is `len(frames)`, validated rather than redundantly authoritative.
Every frame inherits the window modality/topology and ordered position. This is
enough to reconstruct fresh NFP frames/windows for NFPWindowSimilarity without
claiming original occurrence identity.

`SerializedObservedEffectV1`:

```json
{
  "modality": "visual",
  "topology": {"shape": [16, 16]},
  "delta_values": [0.0, -0.2, 0.3]
}
```

Activations remain finite and in [0,1]. Signed deltas remain finite and in
[-1,1]; they are not shifted or normalized into NFP activation. Context and
effect modality/topology must agree. Action modality must be ACTION. Shape
dimensions are positive integers and value lengths equal topology size.
No quantization is introduced. If future canonical hashes require float
canonicalization, specify that separately; JSON spelling is not record identity.

## Field Decisions

| Runtime occurrence field | Persistent V1 decision | Reason |
| --- | --- | --- |
| modality/topology/values | include | reusable cognitive structure and similarity input |
| ordered context frames | include values in order | preserves temporal context similarity |
| effect delta_values | include signed | representative observed structural consequence |
| frame_id/window_id/effect_id/evidence_id | exclude from canonical pattern | occurrence identity is not reusable meaning |
| original active_tick/action_tick/observation_tick | exclude from pattern | event time belongs to evidence history; optional creation tick is metadata |
| origin | exclude from canonical values | proposal construction already validates EXTERNAL_SENSORY/ACTION_GENERATED; not matching semantics |
| provenance_ref | exclude | may be process/source-local and is not operational structure |
| debug_name | exclude | diagnostic text must not become identity or similarity |
| hidden world state/semantic labels | prohibit | unavailable to cognitive input and would fabricate meaning |

Persistent operational structure is `similar context + similar action ->
representative observed effect tendency`. Historical evidence remains bounded,
process-local evidence. Do not persist all RecentCausalTransition objects,
ExperienceEvidence objects, supporting IDs or ShortMemory history. Lightweight
creation provenance may retain source_support_count and creation tick, but it
must not participate in pattern matching.

## NFP-Native Record V1

Conceptual `NFPExpSMRecordV1` inside the existing experience map:

```json
{
  "record_kind": "nfp_native",
  "representation_version": 1,
  "context_pattern": {"modality": "visual", "topology": {"shape": [2]}, "frames": [{"values": [0.0, 1.0]}]},
  "action_pattern": {"modality": "action", "topology": {"shape": [2]}, "values": [0.0, 1.0]},
  "effect_pattern": {"modality": "visual", "topology": {"shape": [2]}, "delta_values": [0.1, -0.2]},
  "hits": 0,
  "misses": 0,
  "confidence": 0.5,
  "repeatability": 0.5,
  "status": 2,
  "created_at_world": "...",
  "updated_at_world": "...",
  "creation_metadata": {
    "source_support_count": 3,
    "created_active_tick": 42,
    "initialization_profile": "legacy_crud_defaults_v1"
  }
}
```

The example initialization profile reuses low-level CRUD defaults: hits=0,
misses=0, confidence=.5, repeatability=.5. It is a proposed explicit policy
profile, not an implemented formula and not the legacy draft commit formula.
The creation request must carry/validate the profile; a future writer may enable
it only after policy review. `source_support_count` never initializes hits,
misses, confidence or success. Initial policy changes remain deferred.

`record_id` remains the key in `experience`. The future single authoritative
writer allocates an unused ID under its write transaction. Existing
`max_numeric + 1` is compatible with current data but needs concurrency/atomicity review before
reuse. IDs are opaque, never memory addresses/debug labels/content hashes.
Equal serialized patterns may have distinct IDs, histories, effects, feedback,
confidence and counters; global content deduplication is prohibited.

V1 serializes the candidate's first real representative evidence unchanged in
structural value. It does not average activations into a pattern never observed.
Future medoid/prototype evolution requires another representation decision.

## Version-Aware Adapter And Load Validation

Introduce one future `ExpSMRecordAdapter`/repository boundary before teaching
each consumer new shapes. It returns typed outcomes, not an untyped universal
tuple:

```text
LegacyOperationalRecord
NFPNativeOperationalRecordV1
UnsupportedRecord(kind/version/reason)
MalformedRecord(kind/version/errors)
```

Dispatch rules are exact: known baseline record with no discriminator -> legacy;
`nfp_native` + version 1 -> validate and parse; unknown version -> Unsupported;
unknown kind or partial discriminator -> Unsupported/Malformed. Never downgrade,
guess fields or reinterpret unknown data.

Load validation checks kind/version, map-key record identity, status,
nonnegative integer hits/misses, finite confidence/repeatability in [0,1], all
required context/action/effect structures, positive topology dimensions,
nonempty ordered context, value lengths/ranges, ACTION modality, and
context/effect compatibility. Malformed NFP-native records are isolated and
reported; they are not silently converted to legacy. Valid legacy behavior is
preserved as far as current permissive readers allow.

Round trip means transient representative -> JSON-safe values -> JSON text ->
fresh parse after original objects are discarded -> structurally equivalent
modality, topology, ordered activation values and signed effect deltas. It does
not require Python object identity, frame IDs, ticks, provenance or debug-name
round trip. A future verifier must explicitly discard originals and reconstruct
fresh runtime values.

## Legacy Coexistence And Migration

Stage 0: current unversioned legacy-only store.

Stage 1: version-aware read/validation accepts legacy and NFP-native V1; no
NFP-native writer and no runtime activation. This is the first implementation.

Stage 2: explicit creation request may reach a controlled version-aware writer
only in an approved mutating profile. Existing legacy writers remain behaviorally
unchanged until deliberately evolved.

Stage 3: optional selective legacy migration, only if later evidence proves it
can be lossless. Stage 3 is not required for new records.

Default: never eagerly rewrite legacy records. Do not alter their IDs,
hits/misses/confidence or unrelated metadata. Do not derive activations from
debug names/semantic strings or invent missing context/action/effect arrays.
When structural information is absent, the record remains legacy indefinitely.

A strong coexistence test loads legacy L and NFP-native N, identifies each by
the exact dispatch rules, and proves L was neither rewritten nor reinterpreted.

## Operational Comparability And Competition

Current SimilarityObserver compares legacy if/then/result/recommendation sets;
it cannot consume NFP-native values directly. It remains the architectural
operational-record similarity stage, but later needs typed comparator dispatch.
For two NFP-native V1 records, an adapter can expose separate context/action/effect
comparison material. The grouping policy must remain explicit rather than force
these into the legacy weighted Jaccard tuple.

Legacy <-> NFP-native is non-comparable in V1 unless a later adapter proves exact
structural criteria for a particular legacy record. Human labels/debug names are
never a bridge. Non-comparable records may coexist and compete only through
their representation-specific valid activation paths.

Activation remains top-N and similar operational records may coexist. Current
Activation reads legacy `if`; a future typed activation adapter must compare
current native context with NFP-native context and emit ordinary action candidate
provenance without changing the architectural top-N role. Different recurring
effects are not collapsed at write time.

DecisionSelector remains the only operational selection stage. No
NFPDecisionSelector or ConsolidationSelector is introduced. A future adapter
must reconstruct a fresh action occurrence from serialized structural action,
then enter the existing proposer/scoring/guard/selector route.

Feedback remains record-ID scoped and updates only the actually selected/used
active record. NFP-native records retain addressable hits/misses/confidence and
repeatability. No neighbor/group update and no unused-record punishment.
Existing feedback linkage qualifications remain unchanged by this design.

Mechanism search also remains legacy-only until a separate typed mapping is
designed; effect is observed structural consequence, not desired result,
success, reward or goal satisfaction.

## Proposal To Creation Request

The controlled sequence is:

```text
ExpSMConsolidationCandidate
-> explicit ExpSMConsolidationProposal
-> deterministic representation builder
-> immutable ExpSMRecordCreationRequest
-> validation/review
-> MemoryMutationPolicy
-> future version-aware writer
```

Threshold and eviction trigger none of these automatically. Proposal cannot call
a writer. ShortMemory eviction never creates a request.

Conceptual immutable request:

```text
request_id
record_kind = nfp_native
representation_version = 1
serialized_context
serialized_action
serialized_effect
source_support_count
created_active_tick
initialization_profile
requested operational metadata
```

The request is complete, JSON-safe, inspectable and still non-authoritative.
It contains no live NFP/effect/candidate/proposal/ShortMemory reference. The
proposal ID may be transient audit context for request construction but is not
canonical pattern identity; the persistent record need not retain it. It does
not persist every supporting evidence ID.

Validation stages remain distinct: proposal valid; representation serializable;
schema valid; review approved; policy permits; writer commits. Once built, the
writer must not reinterpret cognitive values semantically.

Policy behavior follows existing flags:

- `safe_demo`: request may be built/validated in memory, no permanent creation;
  demo runtime continues using a temporary Memory copy.
- `draft_only`: request/draft may be inspected under existing draft permission,
  but `allow_expsm_commit=False` prohibits authoritative creation.
- `mutating_memory`: a future reviewed writer may persist only when a dedicated
  version-aware creation path is explicitly approved and `allow_expsm_commit`
  is true. Existing update/value-feedback flags do not imply creation authority.

Prefer a version-aware representation adapter and controlled extension of
ExpSMCommitWriter/repository rather than a second persistence system. The legacy
draft signature deduplication is not valid for native records and must not be
silently reused. The writer implementation is deferred until read/round-trip
behavior is stable. First implement representation, then mutation.

## Required Future Scenarios

1. Deterministically serialize context ordered values, ACTION values and signed
   effect; output contains JSON-safe primitives and no live references.
2. Canonical representation excludes debug names, occurrence IDs, origins,
   provenance and hidden world state from matching semantics.
3. Full restart round trip reconstructs equivalent modality/topology/context
   order/action values/effect deltas after original objects are discarded.
4. Invalid dimensions, nonfinite values, activation outside [0,1], delta outside
   [-1,1], non-ACTION action or context/effect mismatch are rejected.
5. Explicit NFP-native version 1 parses; unknown version fails unsupported and
   is never downgraded or guessed.
6. Legacy L and native N coexist; L stays byte/structurally unchanged and is not
   given invented NFP fields. Legacy/native V1 comparison is non-comparable.
7. Equal serialized patterns under distinct record IDs remain distinct records.
8. Proposal support becomes source_support_count only; hits/misses remain 0 and
   confidence/repeatability follow an explicit initialization profile, never a
   support-derived formula.
9. Proposal -> request is explicit, immutable and leaves ExpSM bytes unchanged;
   candidate threshold and ShortMemory eviction create no request or write.
10. safe_demo/draft_only cannot authorize permanent creation; mutating_memory
    still requires validation/review and a future writer implementation.
11. SimilarityObserver typed boundary is explicit; Activation top-N and
    DecisionSelector roles are unchanged; Feedback targets one used record.
12. No eager migration, AKBSM/Chronicle writes, `_run_tick` integration,
    automatic/background/sleep consolidation or semantic outcome evaluation.

## Implemented Representation Checkpoint

The V1 serialized context/action/effect values, native record parser/serializer,
typed version-aware adapter, immutable creation request and deterministic
proposal/evidence builder now exist. Legacy and native records parse side by
side, unknown versions remain unsupported, and restart round-trip validation
uses fresh JSON-decoded objects. No fake historical NFP occurrence is rebuilt.

The request remains non-authoritative. Final numeric record identity is still
writer-owned; no migration ran, no writer changed, no policy gate executes, no
Memory file is written and normal runtime does not import this layer. Executable
coverage is `tools/verify_persistent_nfp_expsm_representation.py` and
`scenarios/persistent_nfp_expsm_representation.json`.

## Deferred Scope And Safety

Deferred: version-aware repository integration; actual writer support; schema migration
execution; file-envelope version; concurrency-safe ID allocation; initial
confidence policy changes; legacy conversion; cross-representation learned
similarity; SimilarityObserver/Activation/mechanism extensions; runtime wiring;
automatic/background/sleep consolidation; reward/pain/goals/needs evaluation;
AKBSM conversion; Chronicle conversion.

This pass changes no runtime source, ExpSM schema/data/reader/writer, hits,
misses, confidence, SimilarityObserver, Activation, DecisionSelector, Feedback,
mechanism search, Memory file or `_run_tick()`. No ExpSM, AKBSM or Chronicle
write is authorized.

The next boundary is now designed in `design_nfp_expsm_mutation_path.md`. It
keeps this request non-authoritative, places validation before policy/write,
retains writer-owned IDs and extends the existing store architecture rather
than adding a parallel database. That document still grants no write authority.

## Post-v1.6 CREATE Status

The representation now has one isolated authoritative consumer:
`NFPExpSMCreateWriter`. It accepts the existing typed
`ExpSMRecordCreationRequest`, preserves request identity as provenance-only
trace data, allocates the persistent numeric record ID inside the locked
mutation operation, and materializes the existing `NFPExpSMRecordV1` without a
second schema definition. Fresh adapter readback is required before a result is
confirmed as `CREATED`.

This does not make native records operational. Similarity, activation/top-N,
decision selection, Feedback, mechanism search, native UPDATE, and normal
runtime wiring remain deferred. The implementation and verifier do not migrate
legacy records or mutate production Memory.

The proposed first read-only operational use is now specified in
`design_nfp_expsm_operational_retrieval.md`. It compares live context directly
with `SerializedNFPContextV1`, without reconstructing fake historical NFP
occurrences. Persistent ACTION and effect travel as structural candidate
content rather than retrieval keys, and exact persistent record ID survives
competition/selection for a later, separately designed Feedback boundary.

## Post-v1.7 Read-Only Retrieval Status

That isolated consumer now exists. A fresh mixed-store reader parses this V1
representation through `ExpSMRecordAdapter`, compares live external-sensory
context directly with serialized context, and preserves exact record identity
through existing Activation/top-N and typed DecisionSelector entry points.
Transient processing IDs remain separate and equal-content records are not
deduplicated. The consumer has no write authority, Feedback, ACTION
materialization, guard invocation, execution, or normal runtime wiring.

`docs/design_nfp_native_feedback.md` preserves V1's immutable context, ACTION,
predicted effect and creation metadata. A future accepted event may alter only
operational hits, misses, confidence and repeatability for the exact selected
record; durable replay metadata is not silently added to V1.

`NFPFeedbackTargetCore.from_record()` now provides the single transient
ten-field continuity projection of a parsed V1 record. It does not alter this
persistent schema and excludes identity, lifecycle/update metadata and mutable
operational metrics. Canonical JSON round-trip equality is covered by the real
evaluation verifier. The explicit native Feedback apply writer now updates
only operational `hits`, `misses`, `confidence`, `repeatability`, and
`updated_at_world` on the exact existing ID after TargetCore continuity
succeeds. It does not change the V1 schema, context, ACTION, prediction,
creation provenance, status, or `created_at_world`, and adds no replay field or
runtime wiring.
