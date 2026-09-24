# NFP-Native Feedback Design

## Scope And Progression

This design-only boundary follows `v1.9.0` (`66efa5c`): v1.7 created persistent
NFP-native experiences, v1.8 retrieved and selected them, and v1.9 explicitly
executed a fresh guarded occurrence. The next isolated boundary compares a
remembered structural prediction with the actual externally observed effect.
This is prediction reliability, not outcome utility. It adds no implementation,
`_run_tick()` wiring, automatic Feedback, or Memory
mutation.

## Current Legacy Feedback Audit

`ExpSMOutcomeFeedback` is semantically legacy-specific. A `confirmed` outcome
is a hit unless expected semantic patterns and actual semantic patterns are
both present and disjoint; `partially_confirmed` is a partial hit;
`failed`/`expired` are misses; `inconclusive` is no feedback. Those meanings
depend on outcome labels, result/recommendation patterns and internal effect
events. They are not NFP prediction-reliability semantics and MUST NOT classify
native evidence.

The target is the exact `experience_id` propagated from the selected activation
or mechanism decision. Non-selected candidates are not punished. The legacy
key is `(experience_id, activation-or-search-id, decision_id)`. It is checked
in an in-process set and in `metadata.applied_feedback_keys`, but only the last
24 persisted keys are retained. Therefore legacy replay protection is bounded,
not durable for arbitrary history, and does not justify crash-safe idempotency.

For one legacy hit or partial hit, `hits += 1`; for one miss, `misses += 1`.
The generic numerical formulas are:

```text
hit_strength = 0.60 * (1 - exp(-hits / 20))
success_ratio = hits / max(1, hits + misses)
target_confidence = clamp(hit_strength * success_ratio, 0, 0.60)
new_confidence = clamp(0.75 * min(old_confidence, 0.75)
                       + 0.25 * target_confidence, 0, 0.75)

target_repeatability = 0.90 * (1 - exp(-(hits + misses) / 10))
new_repeatability = clamp(max(0.85 * old_repeatability,
                              target_repeatability), 0, 0.90)
```

The formulas consume counters only; classification feeding those counters is
legacy-semantic. Native HIT/MISS may reuse these exact generic formulas after a
typed native classifier. Repeatability is treated as accumulated externally
grounded trial evidence, so both native agreement and disagreement count as a
trial. Viability remains derived as `(hits + 1) / (hits + misses + 2)` and is
never persisted separately.

The legacy implementation increments `hits` or `misses` first and then computes
both confidence and repeatability from those updated counters. The first native
implementation must preserve that sequencing: classify, increment exactly one
counter, derive both targets from the post-increment counters, then persist the
four operational fields together.

Legacy Feedback writes its JSON directly and is not the native mutation model.
`ExpSMUpdateWriter` is a consolidation-draft metadata updater, not a native
Feedback writer. `MemoryMutationPolicy` permits authoritative ExpSM updates only
when `allow_expsm_update` is true: false for `safe_demo` and `draft_only`, true
for `mutating_memory`. Pure evaluation requires no mutation policy.

## Observed Effect Audit

`ObservedEffectExtractor` derives actual evidence only from a
`RecentCausalTransition`. It subtracts aligned endpoint activations as
`after_i - before_i`, preserves modality, topology and channel order, and
requires observation tick `action_tick + 1`. Since endpoint activations are in
`[0,1]`, signed deltas are validated in `[-1,1]`.

`SerializedObservedEffectV1` has the same modality/topology/aligned signed-delta
shape and validates finite values in `[-1,1]`. A direct native comparator must
compare it to `ObservedEffect` without fabricating frames, windows, IDs, ticks,
or origins.

## Direct Structural Comparator

Compatibility is checked before arithmetic: modality, topology, and aligned
value count must match. Incompatibility is `INCOMPARABLE_EFFECT`, never a score
of zero and never a miss. Malformed prediction and actual evidence are
`INVALID_PREDICTION` and `INVALID_ACTUAL_EFFECT`.

For compatible bounded effects:

```text
mean_abs_error = mean(abs(predicted_i - actual_i))
effect_similarity = 1 - mean_abs_error / 2
```

The audited range guarantees a score in `[0,1]`; malformed values are rejected,
not clamped. Channel order and sign matter. Positive is not good and negative
is not bad. This metric measures structural prediction accuracy only.

`native_effect_agreement_threshold` is explicit required configuration and is
unrelated to retrieval/context thresholds. At the boundary, score equal to the
threshold is a HIT; a lower comparable score is a MISS.

## Evaluation Result Model

Pure `evaluate_native_feedback(...)` conceptually accepts the execution result,
a `RecentCausalTransition`, stored `SerializedObservedEffectV1`, and explicit
threshold. It returns an immutable result with one of:

```text
HIT
MISS
NOT_ELIGIBLE_EXECUTION
OBSERVATION_PENDING
CAUSAL_TRACKING_UNAVAILABLE
TRANSITION_MISMATCH
INCOMPARABLE_EFFECT
INVALID_ACTUAL_EFFECT
INVALID_PREDICTION
```

Only `EXECUTED_AND_OBSERVED` may produce HIT/MISS. Every pre-execution status is
`NOT_ELIGIBLE_EXECUTION`; tracking failure is
`CAUSAL_TRACKING_UNAVAILABLE`; observation pending is `OBSERVATION_PENDING`, not
a miss. A later explicit call may use a completed transition.

Eligibility requires exact causal linkage:

```text
execution.action_frame.frame_id == transition.action_frame.frame_id
execution.action_frame.active_tick == transition.action_frame.active_tick
transition.action_tick == execution.action_frame.active_tick
transition.observation_tick == transition.action_tick + 1
```

Mismatch is `TRANSITION_MISMATCH`. Actual effect authority is exclusively
`ObservedEffectExtractor.extract(transition)`. Stored prediction, hidden world
state, debug labels, reward and utility are never actual evidence.

HIT means the remembered structural effect predicted actual structural change
at or above threshold. MISS means comparable evidence was below threshold.
Neither means desirable/undesirable, success/failure, reward/punishment, or
good/bad. Retrieval, selection, INTERNAL_REACTIVATION, guard denial, failed
execution, unavailable evidence and incomparable structure create no hit/miss.

HIT/MISS evidence carries exact `source_experience_id`, action frame ID/tick,
predicted effect, actual effect, similarity, threshold and classification.
No evidence object is fabricated for other statuses.

`source_activation_id` is legacy trace/provenance and may remain diagnostic; it
does not choose the persistent target and is not sufficient replay identity.

## Persistent V1 Field Audit

The authoritative schema below is derived from `NFPExpSMRecordV1`, its two
metadata value objects, and its JSON adapter. `record_id` is the persistent map
key supplied to `from_json_data`; the remaining names are JSON fields (nested
creation fields are shown individually). Each current persistent V1 field
appears exactly once.

<!-- NFP_V1_FIELD_AUDIT_START -->
| field | persistent? | mutable after creation? | operational metric? | immutable TargetCore field? | class and reason |
| --- | --- | --- | --- | --- | --- |
| `record_id` | yes, map key | no for a record | no | EXCLUDED | A: exact identity is carried separately as `source_experience_id`; duplicating it in TargetCore would blur address and content continuity. |
| `record_kind` | yes | no | no | INCLUDED | A: `nfp_native` identifies the representation family and must still match. |
| `representation_version` | yes | no | no | INCLUDED | A: version `1` defines the parser and structural meaning. |
| `context_pattern` | yes | no | no | INCLUDED | B: serialized learned context is continuity-critical structure. |
| `action_pattern` | yes | no | no | INCLUDED | B: serialized ACTION is continuity-critical structure. |
| `effect_pattern` | yes | no | no | INCLUDED | B: serialized predicted effect is continuity-critical structure. |
| `source_support_count` | yes, nested in `creation_metadata` | no | no | INCLUDED | C: immutable evidence support at creation identifies this learned record. |
| `source_proposal_id` | yes, nested in `creation_metadata` | no | no | INCLUDED | C: immutable proposal provenance identifies this learned record. |
| `created_active_tick` | yes, nested in `creation_metadata` | no | no | INCLUDED | C: immutable cognitive creation tick identifies this learned record. |
| `initialization_profile` | yes, nested in `creation_metadata` | no | no | INCLUDED | C: immutable initialization semantics determine the record's origin. |
| `status` | yes | yes, lifecycle/archival state | no | EXCLUDED | E: lifecycle state is independently mutable; native validity is checked before comparison, while continuity concerns learned structure. |
| `created_at_world` | yes when present | no | no | INCLUDED | C: optional immutable store-creation provenance is parsed and round-trips unchanged across restart. |
| `updated_at_world` | yes when present | yes on writes | no | EXCLUDED | E: write timestamp changes during legitimate operational updates. |
| `hits` | yes | yes | yes | EXCLUDED | D: Feedback is allowed to increment it. |
| `misses` | yes | yes | yes | EXCLUDED | D: Feedback is allowed to increment it. |
| `confidence` | yes | yes | yes | EXCLUDED | D: Feedback recomputes it from updated counters. |
| `repeatability` | yes | yes | yes | EXCLUDED | D: Feedback recomputes it from updated counters. |
<!-- NFP_V1_FIELD_AUDIT_END -->

`status` is validated by the V1 parser as a non-negative integer, but the legacy
CRUD surface also treats status as lifecycle/archive state. No current native
Feedback writer exists and the native create path initializes it rather than
using it as learned content. The first Feedback design therefore EXCLUDES
`status` from TargetCore. A schema-valid status-only lifecycle change does not
make an otherwise identical learned rule stale; an archived or otherwise
unreadable representation still fails the representation/validity gate.

`created_at_world` is optional persisted creation provenance. Current creation
materializes it once, parsers preserve it, and operational updates have no
reason to regenerate it, so it is INCLUDED (including exact `None` versus
string state). `updated_at_world` is explicitly a mutable write timestamp and
is EXCLUDED.

## NFPFeedbackTargetCore Exact Schema

`source_experience_id` answers **which record was selected**.
`NFPFeedbackTargetCore` answers **what immutable persistent experience
structure was selected**. Apply requires both; TargetCore never replaces or
duplicates the record ID.

The exact conceptual TargetCore schema is:

```text
record_kind: str
representation_version: int
context_pattern: SerializedNFPContextV1
action_pattern: SerializedNFPActionV1
effect_pattern: SerializedObservedEffectV1
source_support_count: int
source_proposal_id: str
created_active_tick: int
initialization_profile: str
created_at_world: str | None
```

These ten fields are INCLUDED. The separately carried `source_experience_id`
and the seven EXCLUDED fields are not members: `record_id`, `status`,
`updated_at_world`, `hits`, `misses`, `confidence`, and `repeatability`.
Every inclusion/exclusion decision corresponds to exactly one row in the field
audit above.

Equality is exact typed structural equality after parsing canonical persistent
JSON, including tuple order, modality, topology, values, optional timestamp and
all creation-provenance values. `SerializedNFPContextV1`,
`SerializedNFPActionV1`, and `SerializedObservedEffectV1` parse JSON numbers to
validated finite Python floats and serialize those values directly; a normal
JSON write/read round-trip does not recompute them. Exact equality is therefore
appropriate. There is no tolerance, similarity, approximate context matching,
content ranking, debug-label comparison, or human-name comparison.

## TargetCore Origin, Propagation, And Lifetime

TargetCore is constructed during retrieval/candidate creation from the same
fresh authoritative `NFPExpSMRecordV1` that produced the native candidate. It
is not constructed from selected ACTION alone and not first invented from the
fresh read at Feedback apply time.

The complete normative propagation chain is:

```text
authoritative NFPExpSMRecordV1 (source_experience_id=R, immutable core=C)
-> NFP retrieval candidate (source_experience_id=R, target_core=C)
-> selected native result (source_experience_id=R, target_core=C)
-> remembered-action execution result (source_experience_id=R, target_core=C)
-> native Feedback evidence (source_experience_id=R, target_core=C)
-> fresh authoritative apply read of record R (derive C2; compare C2 == C)
```

Each hop preserves the exact typed value. Selection does not reread the store,
and later stages MUST NOT reconstruct TargetCore from ACTION, predicted effect,
record ID, or execution frame because those payloads omit context and creation
provenance. The future retrieval candidate, selected result, guarded execution
envelope/result, and Feedback evidence therefore each carry both
`source_experience_id` and `target_core` intact through materialization, guard,
world execution and evaluation.

`NFPFeedbackTargetCore` is transient / ephemeral. Its lifetime is authoritative
retrieval read -> selection -> execution -> explicit Feedback apply, after
which it may be discarded. It is not a new ExpSM persisted schema field, Memory
file, Chronicle record, or Python-object-identity requirement; typed values may
cross freshly recreated pipeline objects or a process restart without writing
root Memory.

TargetCore is cognitively inert. It does not affect context similarity,
threshold filtering, Activation, top-N, DecisionSelector scoring, action
values, materialization, guard decisions, actuator signals, world physics, or
predicted/actual comparison score. Its sole purpose is mutation-target
continuity checking.

## Exact Target And Fresh Read

Future `apply_native_feedback(...)` is a separate explicit mutation boundary.
Its only target key is the selected `source_experience_id`; there is no lookup
by similarity, context, action/effect content, hash, adjacency or top-N
membership. Similar neighbors, top-N losers and records with identical ACTION
receive nothing.

Under the path-local transaction lock it must freshly load the authoritative
store, locate the exact ID, and parse it with `ExpSMRecordAdapter`. Missing,
legacy, malformed and unsupported targets fail closed as `TARGET_NOT_FOUND`,
`TARGET_NOT_NATIVE`, `STORE_INVALID`, or
`UNSUPPORTED_TARGET_REPRESENTATION`. No fallback record is allowed.

Feedback evidence contains `source_experience_id=R` and the historical
`target_core=C`. Apply reopens the authoritative store, looks up exact `R`,
parses and verifies NFP_NATIVE_V1, derives current core `C2`, and performs the
exact check `C2 == C` before any operational metric mutation. Only equality may
continue to the independent policy gate and update calculation. Policy may also
be checked earlier for security, but permission never overrides stale-target
detection and continuity is always verified before writing.

If `R` exists but `C2 != C`, including drift in context, ACTION, predicted
effect, any included creation field, or `created_at_world`, apply returns
`STALE_OR_CHANGED_TARGET` with no update. It performs no similarity fallback,
nearby-record lookup, or reconstruction. A missing exact `R` is
`TARGET_NOT_FOUND`. A legacy, unsupported, or malformed exact target fails
closed as `TARGET_NOT_NATIVE`, `UNSUPPORTED_TARGET_REPRESENTATION`, or
`STORE_INVALID`; it is never reinterpreted as V1.

The current `SelectedNFPExpSMExperience` does not carry serialized context,
creation provenance, or TargetCore. Without this handoff, native apply must
remain unavailable; same-ID continuity cannot be proven from the current
selected payload alone.

## Native Operational Update

One accepted event modifies exactly one record and increments exactly one
counter:

```text
HIT  -> hits + 1; misses unchanged
MISS -> misses + 1; hits unchanged
```

It then applies the audited generic confidence and repeatability formulas above.
Only `hits`, `misses`, `confidence`, and `repeatability` may change. Record ID,
record kind/version, context, ACTION, predicted effect, creation provenance and
source support count remain byte/structurally unchanged. A miss never rewrites
the prediction; contradictory experience may become a separate competing
record later. Future retrieval recomputes viability/Activation; Feedback never
directly changes similarity, Activation, or DecisionSelector state.

Mutation statuses are separate from evaluation statuses:

```text
UPDATED
DENIED_BY_POLICY
TARGET_NOT_FOUND
TARGET_NOT_NATIVE
UNSUPPORTED_TARGET_REPRESENTATION
STALE_OR_CHANGED_TARGET
STORE_INVALID
WRITE_FAILED
READBACK_FAILED
```

## Policy And Transaction Boundary

Evaluation is always read-only. Apply requires `allow_expsm_update`; therefore
`safe_demo` and `draft_only` deny authoritative native Feedback while
`mutating_memory` may permit it. No native draft mechanism is invented.

The future native writer must reuse `ExpSMStoreTransaction`: path-local lock,
fresh strict load, unique same-directory temporary file, complete JSON
serialization, flush and file fsync, atomic replace, best-effort directory
fsync and cleanup. It must add fresh readback verification around that shared
transaction rather than reuse the legacy direct writer.

Pre-replace failure is `WRITE_FAILED` and preserves old authoritative bytes.
Failure after replace during fresh readback is `READBACK_FAILED`: the update may
already be authoritative, so there is no rollback and no blind retry. Read-only
reconciliation must distinguish `CONFIRMED_PERSISTED`, `CONFIRMED_ABSENT` (not
applied), and `UNRESOLVED_OR_STORE_INVALID`, following the existing v1.7
contract. A confirmed persisted result must not apply the increment again.

## Replay Decision And Concurrency Scope

No current mechanism provides unbounded durable native execution-evidence
deduplication. The first isolated implementation therefore uses explicit path
B: serialized single application by the caller, no automatic retry, and no
claim of crash-safe idempotency. The occurrence identity is conceptually
`(source_experience_id, action_frame_id, action_tick)` plus canonical transition
identity, never effect content alone.

This limitation is mechanically required and BLOCKS `_run_tick()` or autonomous
Feedback wiring until durable replay protection and schema/version consequences
are separately designed. No replay field is silently added to NFP_NATIVE_V1.

## Required Isolated Scenarios

Future implementation tests cover perfect agreement, exact threshold, ordinary
and sign disagreement, incomparable topology, malformed evidence, transition
mismatch, tracking failure, observation pending then later matching completion,
guard denial, exact selected-record-only update, unchanged top-N losers, equal
ACTION records remaining independent, policy denial, permitted mutation,
pre-replace failure, post-replace readback reconciliation, no blind retry,
single-application limitation, immutable core after miss, and fresh store read.

Target continuity scenarios additionally cover: unchanged `C` allows a
policy-permitted apply; same-ID changes to context, ACTION, predicted effect,
each included creation field, or `created_at_world` return
`STALE_OR_CHANGED_TARGET`; changes only to `hits`, `misses`, `confidence`,
`repeatability`, `updated_at_world`, or a schema-valid lifecycle `status` do not
invalidate continuity. Restart coverage recreates every transient pipeline
object and compares the carried typed value without object identity or Memory
persistence. Missing and wrong-representation cases retain the fail-closed
statuses above.

## Authority Boundary

Execution never calls evaluation automatically; evaluation never writes; apply
is explicit and policy-gated. This design adds no implementation, runtime phase,
`_run_tick()` call, automatic execution-to-Feedback link, neighbor
reinforcement, reward/utility semantics, ExpSM/AKBSM/Chronicle write, or Memory
change.
