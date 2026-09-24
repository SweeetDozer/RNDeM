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

The fresh NFP-native target's representation version and immutable core
(context, ACTION, predicted effect, creation metadata) must equal the selected
core captured in the evidence request. Drift is
`STALE_OR_CHANGED_TARGET`, with no update.

The current `SelectedNFPExpSMExperience` does not carry serialized context or
creation metadata. A future implementation must therefore add the narrowest
transient typed `NFPFeedbackTargetCore` (or equivalent) captured from the exact
selected record during retrieval, containing source ID, representation/version,
context, ACTION, predicted effect and creation metadata. Evaluation evidence
retains that immutable expected core for apply-time equality. It is not
persisted, does not affect selection, and must not be reconstructed by a new
similarity search. Without this handoff, native apply must remain unavailable;
same-ID core consistency cannot be honestly proven from the current selected
payload alone.

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

## Authority Boundary

Execution never calls evaluation automatically; evaluation never writes; apply
is explicit and policy-gated. This design adds no implementation, runtime phase,
`_run_tick()` call, automatic execution-to-Feedback link, neighbor
reinforcement, reward/utility semantics, ExpSM/AKBSM/Chronicle write, or Memory
change.
