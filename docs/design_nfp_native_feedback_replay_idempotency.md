# Durable NFP-Native Feedback Replay Protection Design

This is the design-only gate after `v1.10.0` (`e5b703b`). It changes no
production type, apply behavior, store, Memory fixture, or runtime wiring.

## Current Duplicate-Application Failure

Today one execution E can produce HIT evidence for record 42 and apply can move
hits 10 -> 11. If the acknowledgement is lost or the process restarts, the same
evidence can be submitted again and move 11 -> 12. Classification is already
settled; duplicate persistent application is the defect. The target guarantee
is **durable at-most-once mutation per canonical Feedback event plus idempotent
retry of an already committed event**, not a casual exactly-once claim.

## Execution Occurrence Identity Audit

`IdGenerator` is a process-local prefix counter starting at one. Remembered
action `frame_id` values therefore repeat after restart. `CLCRuntime` constructs
a new generator, `ContextMemoryManager` starts `_nfp_current_tick` at zero and
its transition counter at one, and caller ticks are not persisted. Transition
IDs are process-local too. There is no existing restart-safe execution, run,
session, or occurrence identity. Thus `(source_experience_id, frame_id, tick)`
is not an approved durable key.

The implementation must introduce `execution_occurrence_id`: a UUIDv4 generated
once by the execution coordinator before prospective physical materialization,
carried unchanged through intent, executed result, pending/recent transition,
and `NFPFeedbackEvidence`, and never generated at apply. Only an actually
executed action can yield applicable evidence. UUIDv4 is probabilistic global
uniqueness; the receipt index also rejects reuse.

## Canonical Feedback Event Identity

```text
NativeFeedbackEventKeyV1 {
  feedback_event_identity_version = 1
  source_experience_id
  execution_occurrence_id
}
```

The key identifies which grounded occurrence updated which selected record. It
excludes HIT/MISS, threshold, similarity, action/context values, effects, and
timestamps. Two genuine executions of record 42 have distinct occurrence UUIDs
even with identical outcomes. Retry reproduces the same key because identity
originates once at execution. A global occurrence index rejects the same UUID
paired with another source record as `EVENT_CONFLICT`; one physical occurrence
cannot reinforce two experiences.

## Evidence Digest Semantics

`FeedbackEvidenceDigestV1` identifies what payload is claimed for the event. Its
schema contains digest version 1, evaluator representation version 1, source ID,
occurrence UUID, every TargetCore field, action frame ID/tick, predicted effect,
the complete actual effect (transition, modality, topology, signed deltas,
endpoint refs and ticks), similarity, threshold, and classification.

Canonical serialization uses the existing strict JSON convention: UTF-8,
sorted object keys, compact separators, arrays for tuples, enum strings,
`allow_nan=False`, finite floats, and deterministic shortest round-trip JSON
numbers without pre-hash rounding. SHA-256 is deterministic identity/integrity,
not authentication. Both `feedback_evidence_digest_version = 1` and the full
digest are stored.

## Event-Key Vs Payload Distinction

Event identity answers **which observation**; the evidence digest answers what
evaluated claim is attached to that observation.

- same key + same digest -> `ALREADY_APPLIED`, successful no-op;
- same key + different digest -> `EVENT_CONFLICT`, no mutation;
- same occurrence + different source -> `EVENT_CONFLICT`;
- different occurrences + same source -> two legitimate events.

Classification and threshold affect the digest, never event identity. Replaying
the same occurrence after re-evaluation therefore conflicts rather than becoming
a second environmental observation.

## Durable Receipt Semantics

A receipt stores identity version, full key, digest version/digest, source ID,
occurrence UUID, classification, applied record ID, applied UTC timestamp, and a
deterministic post-update record fingerprint. It does not copy all evidence.
Receipts are operational mutation-safety metadata, not ExpSM experience, AKBSM
fact, or Chronicle event.

## Chosen Persistence Architecture

The mandatory architecture is **A: same atomic authoritative ExpSM envelope**:

```json
{
  "store_schema_version": 2,
  "experience": {},
  "reflexes": {},
  "native_feedback_receipts": {
    "identity_version": 1,
    "digest_version": 1,
    "by_event_key": {},
    "execution_occurrence_index": {}
  }
}
```

The event-key map uses SHA-256 of canonical key JSON but each receipt retains the
full key and verifies it. The occurrence index maps UUID to event-key digest.
The current unversioned `{experience, reflexes}` envelope is schema v1 with an
empty ledger. Receipt data is top-level, not record-local: the exact 17-field
`NFPExpSMRecordV1` schema stays unchanged, so this does not silently redefine
`NFP_NATIVE_V1`.

Current readers address `experience` and `reflexes` by name and transaction
validation preserves extra top-level keys. Before v2 is enabled, every writer
must be proven to preserve v2 metadata and use the shared lock; otherwise it
must fail closed.

## Atomic Record+Receipt Commit

One exclusive transaction validates evidence and derives key/digest, locks,
fresh-loads the full envelope, checks both receipt indexes, then either returns
`ALREADY_APPLIED`/`EVENT_CONFLICT` or performs exact ID, native V1, TargetCore,
policy and fresh-metric gates. One candidate envelope contains both the updated
record and receipt/index entries. One temp serialization, fsync, atomic replace,
directory fsync, and full readback commits/verifies both.

Known same-digest receipts take precedence over later missing/stale targets
because no new mutation is requested. Conflicting digest takes precedence too.
Unseen denied, missing, non-native, stale, or invalid events create no receipt.

## Crash Matrix

| Failure point | Record | Receipt | Retry/result |
|---|---|---|---|
| Before transaction | before | absent | safe new attempt |
| After fresh read | before | absent | safe new attempt |
| After receipt absence check | before | absent | safe under held lock |
| After intended state constructed | before | absent | safe new attempt |
| During temp write | before | absent | `WRITE_FAILED`, safe retry |
| After temp fsync | before | absent | `WRITE_FAILED`, safe retry |
| Before atomic replace | before | absent | `WRITE_FAILED`, safe retry |
| After atomic replace | updated | present | never mutate blindly |
| Before readback | updated | present | read/reconcile |
| During readback | updated | present | `READBACK_FAILED` |
| After readback | updated | present | `UPDATED`; retry is duplicate |
| Before caller receives result | updated | present | retry is `ALREADY_APPLIED` |

Atomic replacement permits only the complete before-state or complete combined
after-state; never counters without receipt or receipt without counters.

## READBACK_FAILED Retry/Reconciliation

Post-replace failure remains indeterminate and never invokes apply again. A
later fresh call sees same receipt/digest and returns `ALREADY_APPLIED` without
changing metrics or `updated_at_world`. Read-only reconciliation yields
`RECONCILED_APPLIED`, `RECONCILED_NOT_APPLIED`, or
`RECONCILIATION_CONFLICT`. Applied requires matching receipt, occurrence index,
post-update fingerprint, and exact intended record. Receipt absence plus exact
before-state confirms not applied; all mixed states remain conflict/unresolved.

## Concurrency / Lock Scope

Current `ExpSMStoreTransaction` has a class-level `threading.RLock`: it protects
threads in one process only and has no file lock. The implementation must add an
exclusive advisory interprocess lock (Linux `fcntl.flock(LOCK_EX)`) on a stable
sibling lock file, held across read/check/build/replace/readback. Unsupported
locking fails closed. Every ExpSM writer must cooperate before v2 is enabled.

| Case | Required behavior |
|---|---|
| same event, two threads | one update, one `ALREADY_APPLIED` |
| same event, two processes | OS lock; one update, one `ALREADY_APPLIED` |
| different events, same record | serialize; second uses fresh metrics |
| different events, different records | serialize whole-file replacement |

The guarantee covers cooperating writers on the same lock-capable host/filesystem,
not non-cooperating writers.

## Event Conflict Semantics

Future results add `ALREADY_APPLIED` and `EVENT_CONFLICT`; reconciliation adds
`RECONCILED_APPLIED`, `RECONCILED_NOT_APPLIED`, and
`RECONCILIATION_CONFLICT`. Conflict is persistence/integrity failure, not MISS.
Results preserve key/digest/source/classification and truthful authority state.

## Policy Interaction

Receipt lookup precedes policy for a known event: a committed same-digest retry
is a no-op under any profile. For unseen events, `safe_demo` and `draft_only`
return `DENIED_BY_POLICY` and persist no receipt; later `mutating_memory` may
apply once. Denied-attempt audit is separate from applied receipts.

## TargetCore Interaction

Receipts do not replace TargetCore. New events still require exact fresh source
ID, `NFP_NATIVE_V1`, `C2 == carried TargetCore`, policy, and fresh metrics.
Failures create no receipt. Receipt metadata is excluded from TargetCore;
operational drift remains accepted. No similarity/content scan touches neighbors.

## Storage Growth

Receipts are retained without eviction in the first safe version. Legacy
`applied_feedback_keys[-24:]` is bounded and cannot provide permanent replay
protection; increasing the bound does not fix this. Growth is accepted.
Compaction, archived segments, database uniqueness, watermarks, or accumulators
are separate future designs because delayed/out-of-order Feedback makes a simple
last-event watermark unsafe.

## Backward Compatibility / Migration

Old stores read as schema v1 with no receipts; legacy and native V1 records stay
unchanged in either envelope. Existing named-section readers remain compatible,
but implementation tests must prove every adapter/writer. New writers preserve
v2 metadata and lock; old binaries must not write v2. Migration is an atomic
whole-envelope rewrite on the first policy-permitted new event or by a separately
reviewed tool; no historical receipts are fabricated. Production Memory
migration remains deferred and temporary stores are required first.

## Runtime Integration Gate

This design adds no implementation, journal, schema field, Memory change,
automatic learning, or `_run_tick()` wiring. Occurrence propagation, digest
types, v2 validation, interprocess locking, combined commit, reconciliation,
restart/crash/concurrency tests, and compatibility tests require a separate
implementation review/checkpoint. Automatic runtime integration remains blocked
until then and requires its own later design pass.
