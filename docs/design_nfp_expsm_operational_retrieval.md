# Design: NFP-Native ExpSM Operational Retrieval

## Status And Scope

This design/audit boundary is based on `v1.7.0` (`54efc62`). It specifies the
first isolated, read-only route from a live current `NFPWindow` to a selected
persistent NFP-native operational-experience reference. The approved comparator,
retriever, candidate, Activation extension, and selector extension are now
implemented in isolation. It implements no ACTION occurrence, Feedback,
runtime wiring, or memory write.

The checkpoint sequence is:

| Checkpoint | Established boundary |
| --- | --- |
| v1.1.0 | immutable NFP substrate |
| v1.2.0 | world to sensory NFP |
| v1.3.0 | ACTION to world to later sensory consequence |
| v1.4.0 | active present plus bounded recent raw past |
| v1.5.0 | observed-experience evaluation and grouping |
| v1.6.0 | persistent NFP-native representation survives restart |
| v1.7.0 | policy-gated authoritative NFP-native ExpSM CREATE |
| v1.8.0 | read-only persistent operational retrieval and competition |
| Implemented isolated boundary | fresh materialization and guarded execution of remembered ACTION structure |

## Actual SimilarityObserver Audit

`clc/expsm/expsm_similarity_observer.py` contains
`ExpSMSimilarityObserver`. Its current `run(tick, memory, active_field,
system_state)` discards `memory` and `active_field`, runs only in
`consolidation`, reads JSON directly from its configured ExpSM path, and
returns marker-33 `ContextOperation` observations. It does **not** accept a
current query context and is not the active-mode retrieval path.

It accepts only unarchived dict records with non-empty legacy `if`, `then`, and
`result`. It compares record pairs, not query-to-record. Four Jaccard scores are
weighted as `if 0.45 + then 0.30 + result 0.20 + recommendation 0.05`.
`MIN_SIMILARITY_SCORE = 0.45`; connected pairs become groups and at most
`MAX_GROUPS_PER_RUN = 5` are emitted. Record summaries carry ID, confidence
(soft-capped at `.75`), repeatability, hits, misses, and beta-smoothed
viability `(hits + 1) / (hits + misses + 2)`. They carry no action candidate.

Therefore the current observer cannot receive native data through a legacy
string adapter. Its pair-group threshold is not automatically a justified
live-context threshold. The future extension point is the **same
`ExpSMSimilarityObserver` stage**, with a typed representation-aware query
operation and comparator strategy; no `NFPSimilarityObserver` parallel stage.
The existing consolidation `run()` and its legacy pair formula remain intact.

## Actual NFP Similarity Audit

`NFPWindowSimilarity.compare(left, right)` first requires real `NFPWindow`
objects, then equal modality, topology, and frame count. Incompatibility returns
`NFPSimilarityResult(comparable=False, score=None)` with reason
`different_modality`, `different_topology`, or `different_frame_count`.
Compatible windows compare aligned frames in temporal order. Each frame score
is `1 - sum(abs(left_i-right_i))/topology.size`, clamped to `[0,1]`; the window
score is the arithmetic mean of aligned frame scores. Frame IDs, active ticks,
origins, provenance, and debug names do not enter the number.

V1 retrieval preserves exactly these structural rules. It does not add dynamic
time warping, resampling, unordered matching, or a different score scale.

## Actual Activation And Top-N Audit

`ExpSMActivationModule` currently runs in active mode, reads the store itself,
and compares legacy `if` pattern IDs with `ActiveContextField` IDs above
`ACTIVE_THRESHOLD = 0.25`. Coverage is matched-if count divided by record-if
count. Its activation is:

```text
coverage * 0.55
+ min(confidence, 0.75) * 0.20
+ repeatability * 0.15
+ viability * 0.10
```

where viability is `(hits + 1)/(hits + misses + 2)`. Results below
`MIN_MATCH_SCORE = 0.35` are excluded. Surviving dict payloads include exact
experience ID, activation ID, match/coverage, legacy then/result/recommendation,
operational values and trace. They are sorted by activation descending and
bounded by `MAX_ACTIVATIONS_PER_TICK = 3`. Python's stable sort preserves input
order on exact ties, but JSON insertion order is not an explicit cognitive
ranking contract.

The native extension reuses this existing Activation stage and operational
formula. For a native candidate, `context_similarity` occupies the factual
context-match dimension currently occupied by legacy coverage; effective
confidence, repeatability and viability retain their meanings. Hits and misses
enter only through viability. Stored ACTION and effect do not alter context
similarity or imply goodness. The extension consumes a typed candidate and
must not fabricate `if/then/result/recommendation`.

Native results remain distinct by persistent record ID, are ranked by the same
activation formula, and remain subject to the existing top-N bound. A numeric
record-ID fallback may make exact ties deterministic, but only after the
existing activation order keys and only as infrastructure, never superiority.

### Normative Native Activation Contract

The native mapping is exact: `native Activation coverage := context_similarity`.
Here coverage means live current context to persistent stored context similarity.
It excludes ACTION similarity, effect similarity, effect magnitude,
`source_support_count`, and creation provenance. Native candidates enter the
existing formula, without a native-specific aggregate score:

```text
activation =
    coverage      * 0.55
  + confidence    * 0.20
  + repeatability * 0.15
  + viability     * 0.10

coverage = context_similarity
viability = (hits + 1) / (hits + misses + 2)
```

## Actual Action Candidate And Scoring Audit

`ActionProposer._propose_expsm_actions()` currently reads legacy activation
events, iterates `then_patterns`, rejects IDs outside its registered action set,
and creates `ActionCandidate` objects. `ActionCandidateField` keys legacy
ExpSM candidates by action pattern, source experience ID, and activation ID, so
distinct records can coexist. `action_scoring.score_breakdown()` computes the
base action score from confidence `.45`, urgency `.25`, activation `.15`, risk
penalty `.25`, and cost penalty `.15`; an ExpSM activation source then combines
base score `.70` with memory score `.30`. The memory score uses match,
viability, effective confidence, and repeatability.

Those action-level urgency/risk/cost and registered pattern-ID assumptions are
not present in persistent structural ACTION data. The first read-only native
retrieval implementation must not invent them. It therefore stops at typed
operational-experience competition/selection. Converting the structural ACTION
into an executable/action-candidate occurrence is a later reviewed boundary.

## Actual DecisionSelector Audit

`DecisionSelector.select()` receives `ActionCandidateField`, examines at most
20 field candidates, applies cooldown and optional `ModeActionGuard`, computes
`score_breakdown`, and selects `max(final_score)`. Python's stable `max` keeps
the first candidate on an exact tie. A score below the selector's `.35`
threshold yields no decision. Its current output is marker-7
`ContextOperation`; `decision_pattern_id` is a registered action pattern ID,
not a record.

For legacy ExpSM candidates, source metadata is copied into the decision:
`source_experience_id`, `source_activation_id`, match, viability, confidence,
and repeatability. `expsm_candidate_snapshot` keeps every scored legacy ExpSM
candidate and marks the selected candidate. This is how persistent record
identity survives current selection.

`ModeActionGuard` also requires a registered action pattern ID. Consequently a
native structural ACTION cannot truthfully enter the current `ActionCandidate`
or guard contract. The controlled extension is a typed native operational
candidate union accepted by the **existing `DecisionSelector` architecture**,
with a native selection branch that selects among already activated records
and returns `SelectedNFPExpSMExperience`. It is not a second selector and is
not runtime-wired. It preserves record ID, structural ACTION/effect,
context similarity, activation and operational trace. It does not emit or
execute a semantic action command, and it does not claim guard approval.

## Current Selected-Record And Feedback Identity Flow

Today the path is legacy activation `experience_id` -> ActionProposer
`source_experience_id`/`source_activation_id` -> ActionCandidate source
metadata -> DecisionSelector payload and candidate snapshot. Competition uses
the `(experience_id, activation_id)` pair. `ExpSMOutcomeFeedback` links a
selected decision back to exactly that experience and activation before
updating hits/misses/confidence/repeatability. Non-selected alternatives are
explicitly marked `unused_not_punished`.

Native retrieval must preserve the same identity principle, but native
Feedback remains deferred. Future Feedback receives the exact selected
`record_id`; it must never update similarity neighbors or punish unselected
top-N candidates.

### Normative Identity And Feedback Contract

Candidate/pattern identity is not persistent ExpSM record identity. A
`candidate_id`, `activation_id`, `pattern_id`, or selector-local identity names
a transient processing object unless a field is explicitly defined as a source
reference. The persistent `record_id` alone identifies the stored experience.

The required end-to-end source-reference chain is:

```text
persistent NFP-native record_id
-> retrieval candidate source_experience_id or typed equivalent
-> Activation candidate
-> DecisionSelector input
-> selected operational-experience result
```

The persistent source ID survives every step unchanged. This propagation exists
specifically so future native Feedback updates only the selected/used persistent
record by its preserved selected persistent record ID. Content lookup,
similarity-neighbor lookup, group feedback, and all-top-N feedback are forbidden.
Feedback remains deferred; native Feedback mutation is deferred. Selection alone
is not behavioral feedback.

## Retrieval Semantics

The first retrieval key is **current context only**:

```text
current live context
-> what persistent operational experiences occurred in situations like this?
```

Stored ACTION is not a query key because no action has been chosen yet; asking
for current-action similarity would be circular. Stored effect is not a query
key. The consequence is unknown before action. Effect travels with a
candidate as remembered/predicted structural consequence metadata. It remains
a signed delta, not desired outcome, success, failure, reward, pain or utility.

## Retrieval Query And Authority

`NFPExpSMRetrievalQuery` is immutable and contains only a live current
`NFPWindow`. Retrieval configuration is separate. It contains no action,
expected effect, goal, reward, human label, debug name, or filesystem path.

The first behavior-oriented query authority gate requires every query frame to
have `PatternOrigin.EXTERNAL_SENSORY`. Origin decides whether the context may
drive external-world operational recall; it is not a numerical similarity
feature. A structurally identical `INTERNAL_REACTIVATION` window is
`INVALID_QUERY`. Internal associative recall/thought is a separate deferred
mode. Frame IDs, ticks, provenance and debug names are ignored by similarity.

## Live/Persistent Comparator

`LivePersistentNFPContextSimilarity` takes a live `NFPWindow` and a persistent
`SerializedNFPContextV1` directly. It never creates fake historical
`NFPFrame`/`NFPWindow` objects or invents IDs, ticks, origins, or provenance.
It returns the existing `NFPSimilarityResult` convention or an exactly
compatible typed result.

It requires equal modality, topology, and frame count; incompatible data is
`comparable=False, score=None`, not score zero. Compatible data compares
ordered aligned activation values with the exact frame-L1/mean-window formula
audited above. For windows A and B:

```text
NFPWindowSimilarity.compare(A, B).score
== LivePersistentNFPContextSimilarity.compare(
       A, SerializedNFPContextV1.from_window(B)
   ).score
```

within floating-point tolerance. Occurrence metadata differences do not change
the score. Temporal order is never sorted or averaged away.

## Read-Only Retriever And Store Policy

`NFPExpSMRetriever` is configured with a store path outside query/record data.
It freshly opens a store, requires object-valued top-level `experience` and
`reflexes`, and parses each experience through the existing version-aware
`ExpSMRecordAdapter`. It imports no create/update writer,
`MemoryMutationPolicy`, or `ExpSMStoreTransaction` and performs no write.

Adapter outcomes are handled conservatively:

- valid legacy: recognized, supported, non-comparable to an NFP query, skipped;
- NFP-native V1: eligible for structural comparison;
- malformed: `STORE_INVALID`, no candidates;
- unsupported explicit kind/version: `UNSUPPORTED_MEMORY_PRESENT`, reported
  explicitly and no candidate selection in V1 (fail closed);
- malformed top-level/experience/reflex section: `STORE_INVALID`.

Legacy non-comparability is normal and never fabricated into activation arrays.
Unsupported memory is not guessed. `NO_COMPARABLE_RECORDS` is normal when a
valid store has no structurally compatible native records; comparable records
below the configured threshold also yield a normal empty candidate set.

## Retrieval Result And Candidate Contracts

Immutable `NFPExpSMRetrievalResult` statuses are `OK`,
`NO_COMPARABLE_RECORDS`, `INVALID_QUERY`, `STORE_INVALID`, and
`UNSUPPORTED_MEMORY_PRESENT`. These describe retrieval/control state, not
action quality.

Each immutable `NFPExpSMRetrievalCandidate` carries:

```text
record_id (exact persistent identity)
record_kind = nfp_native
representation_version = 1
context_similarity only
SerializedNFPActionV1
SerializedObservedEffectV1 as prediction/consequence metadata
hits, misses, confidence, repeatability
optional non-semantic creation provenance
```

Context similarity excludes ACTION, effect and all operational metadata. Equal
content at different record IDs yields distinct candidates; there is no content
hash, request-ID, similarity dedupe, or merge.

The coexistence invariant is exact: same or similar structural
context/action/effect plus different persistent `record_id` produces distinct
retrieval candidates. There is no content deduplication, context deduplication,
action deduplication, effect deduplication, or candidate collapsing before or
during retrieval, the SimilarityObserver-compatible stage, Activation, top-N,
or DecisionSelector. Multiple similar NFP-native records may coexist in
Activation competition, subject only to the existing `top-N = 3`; they are not
merged into an averaged or representative memory.

## SimilarityObserver Extension Decision

Choose a representation-aware comparator strategy inside the existing
`ExpSMSimilarityObserver` stage. A typed native-query entry point receives
adapter-parsed V1 records and the live query, applies
`LivePersistentNFPContextSimilarity`, and produces typed retrieval candidates.
The existing consolidation pair-grouping `run()` remains unchanged. A named
native query threshold belongs to injected retrieval configuration in this
same stage; the legacy pair threshold `.45` is documented but not blindly
reused as a magic number because it measures a different four-field Jaccard
quantity. Threshold behavior must be tested and explicit.

The extension remains in the same `ExpSMSimilarityObserver` stage. This is one
observer architecture with representation-aware strategies, not a
parallel `NFPSimilarityObserver` and not a semantic-string adapter.

## Activation Compatibility Decision

Extend the existing `ExpSMActivationModule` with a typed input path for
`NFPExpSMRetrievalCandidate`. It must not reread or reinterpret native records
as legacy. `context_similarity` supplies the match dimension; existing
effective-confidence, repeatability, viability, minimum activation score and
top-N mechanics remain. The output keeps structural ACTION/effect and record
ID. Similar records coexist and divergent effects are never averaged or ranked
as good/bad.

## DecisionSelector Compatibility Decision

Extend the existing `DecisionSelector` with a typed native operational
candidate branch rather than creating another selector. The isolated branch
selects an already ranked/activated operational record deterministically,
retaining exact `record_id`, structural ACTION, structural effect,
context-similarity and activation trace in immutable
`SelectedNFPExpSMExperience`. Exact ties use numeric record ID only as a final
stable fallback. Record ID has no cognitive weight.

This branch does not fabricate `ActionCandidate.pattern_id`, urgency, risk,
cost, legacy result/recommendation, or a ModeActionGuard decision. Those require
the later action-materialization/execution design. Selection here means
"selected remembered operational experience", not "performed action".

## Action And Effect Boundaries

Remembered `SerializedNFPActionV1` is memory content, not a live ACTION
occurrence. Selection does not open a ContextMemory causal transition, call
`ActionTransducer`, mutate the world, or create `ACTION + ACTION_GENERATED`.
The separately implemented, explicitly invoked boundary is:

```text
SelectedNFPExpSMExperience
-> persistent structural ACTION
-> fresh action occurrence materializer
-> new frame ID + current tick + ACTION_GENERATED NFPFrame
```

That boundary is deferred. Stored effect remains remembered/predicted
structural consequence metadata, never `desired_effect` or reward.

The mandatory future execution boundary is:

```text
Selected NFP-native operational experience
-> SerializedNFPActionV1
-> fresh ACTION occurrence materialization
-> ACTION + ACTION_GENERATED NFPFrame(current_tick)
-> appropriate existing action guard / ModeActionGuard-compatible gate
-> only if allowed: ActionTransducer / execution
```

Action materialization is deferred. A future materialized executable ACTION must
pass the appropriate action guard before world execution; retrieval or selection
must not bypass guard semantics. `ModeActionGuard` does not participate in
context similarity, retrieval candidate production, or Activation scoring,
because remembered persistent ACTION is not yet an executable occurrence. The
guard belongs only to the later materialized-action-to-execution boundary and
does not alter context retrieval similarity.

## Read-Only And Runtime Boundaries

Retrieval, comparison, activation and isolated selection do not increment hits,
misses, confidence or repeatability. Recall is not Feedback. Unselected records
receive no punishment. Store bytes remain unchanged.

A retrieved but not selected record receives no punishment. A top-N but not
selected record receives no miss increment merely because it lost selection.
The complete retrieval-to-selection path must not invoke Feedback or persist any
update.

The retrieval architecture is strictly `read -> parse -> compare -> rank ->
select`, never `mutate -> commit -> update`. A future retrieval implementation
must not import or call `MemoryMutationPolicy`, the NFP-native ExpSM create
writer, `ExpSMCommitWriter`, `ExpSMUpdateWriter`, `ExpSMStoreTransaction`, or a
native Feedback/update writer during retrieval or competition. The future real
retrieval verifier must AST/import/call-audit retrieval production modules for
the absence of those mutation authorities and Feedback mutation. This document
states that future-verifier obligation; it does not claim to audit retrieval
source that does not yet exist.

The future isolated implementation has no `_run_tick()` or phase wiring, no
normal runtime import, no ActionTransducer call, no ACTION occurrence, no
native Feedback/update, no ExpSM writer or mutation policy, and no AKBSM or
Chronicle/Letopis interaction. Mechanism search remains legacy-only and
unchanged.

## Required Isolated Scenarios

Future `scenarios/nfp_expsm_operational_retrieval.json` and its real verifier
must use fresh temporary mixed stores and cover:

1. valid all-`EXTERNAL_SENSORY` query and structurally identical
   `INTERNAL_REACTIVATION` rejection as epistemic authority, not score;
2. live/live versus live/persistent similarity parity;
3. modality, topology and frame-count incompatibility as non-comparable;
4. occurrence neutrality across IDs, ticks, provenance and debug names;
5. context-only retrieval: a dissimilar context does not match merely because
   ACTION/effect match;
6. action independence: same context with different ACTIONs yields both;
7. effect independence: same context/action with divergent effects yields both;
8. valid legacy records are harmless non-comparable entries in a mixed store;
9. malformed store fails safe and unsupported memory is explicit;
10. same-content records with distinct IDs remain distinct candidates;
11. SimilarityObserver-compatible candidates enter existing Activation top-N
    without merge or fake legacy fields;
12. existing DecisionSelector typed extension preserves selected record ID,
    structural ACTION and effect metadata;
13. freshly reopened store proves restart retrieval with no write-stage objects;
14. no fake persistent NFP reconstruction, action execution, ContextMemory
    transition, Feedback mutation, store-byte change, or `_run_tick()` wiring.

## First Implementation Recommendation

After design review, implement only the isolated read-only comparator,
version-aware retriever, typed candidate, representation-aware extension of the
existing SimilarityObserver stage, typed existing Activation top-N path,
existing DecisionSelector typed selection branch, and selected persistent
experience payload. Use temporary mixed stores and fresh readers.

Still defer runtime wiring, ACTION materialization/execution, ModeActionGuard
for structural actions, native Feedback/update, automatic consolidation,
ExpSM/AKBSM/Chronicle writes, semantic outcome evaluation, reward, pain, goals
and utility.

## Isolated Implementation Status

The approved isolated path is now implemented in
`clc/expsm/nfp_operational_retrieval.py`, with typed entry points on the existing
`ExpSMSimilarityObserver`, `ExpSMActivationModule`, and `DecisionSelector`.
`NFPExpSMRetrievalQuery` contains only a live current context and requires every
frame to be `EXTERNAL_SENSORY`. `LivePersistentNFPContextSimilarity` compares
that window directly with `SerializedNFPContextV1`; it preserves the current
aligned structural formula and typed non-comparable results without fabricating
historical occurrences.

The fresh reader uses `ExpSMRecordAdapter`, fails closed for malformed or
unsupported memory, treats valid legacy records as non-comparable, and keeps
same-content records distinct by persistent ID. Native candidates map
`coverage = context_similarity` into the existing Activation formula and top-N
of three. Persistent `source_experience_id` survives retrieval, Activation, and
typed selection while candidate, activation, and selection IDs remain transient.

The selected payload still contains only persistent structural ACTION and
effect prediction metadata. The production retrieval path imports no mutation
authority and invokes no Feedback, ModeActionGuard, ActionTransducer, runtime,
or writer. The real verifier AST-audits those boundaries and uses freshly
reopened temporary mixed stores. ACTION materialization remains deferred; a
future executable occurrence must pass the appropriate guard before execution.

The guarded occurrence boundary now exists at v1.9. The next design-only
consumer is `docs/design_nfp_native_feedback.md`: it preserves the exact
selected `source_experience_id`; retrieval neighbors and top-N losers receive
no Feedback merely for participating in competition.

The isolated Feedback-evaluation implementation now adds an inert
`NFPFeedbackTargetCore` to each native candidate directly from its parsed
authoritative record. Activation and typed selection preserve it without using
it in similarity, thresholds, scoring, viability, ordering or top-N. Retrieval
still invokes neither evaluation nor persistence.
