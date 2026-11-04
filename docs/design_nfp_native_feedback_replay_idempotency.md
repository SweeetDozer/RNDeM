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

The implementation must introduce `execution_occurrence_id`: a UUIDv4 created
exactly when the fresh current ACTION occurrence is successfully materialized.
Frame materialization and UUID creation are one conceptual operation returning
one concrete remembered-action execution **attempt**. Failures before successful
materialization have no occurrence ID. The ID is not proof that the world was
changed: existing execution status and the successful return of
`world.apply_actuator_signal()` remain the physical point of no return.

Once created, the same UUID is carried unchanged through the materialized
intent, every post-materialization execution result, pending/recent transition,
Feedback evaluation, `NFPFeedbackEvidence`, and durable event key. It is never
regenerated at world execution, observation, evaluation, apply, reconciliation,
or retry. After world application returns successfully, that UUID is permanently
the identity of the physical occurrence even if causal tracking fails or
observation remains pending. UUIDv4 is probabilistic global uniqueness; the
receipt index also rejects reuse.

## Execution-Status / Occurrence-ID Matrix

The table follows the current coordinator order. An
`INVALID_SELECTED_EXPERIENCE` can occur during request/selected validation or
because materialization failed; in either case no fresh ACTION was successfully
materialized and no UUID exists.

| Status | Fresh ACTION materialized? | Occurrence ID? | World physically executed? | Eligible for Feedback event? |
|---|---:|---:|---:|---|
| `STALE_SELECTION` | No | No | No | No |
| `INVALID_SELECTED_EXPERIENCE` | No | No | No | No |
| `CAUSAL_SLOT_OCCUPIED` | No | No | No | No |
| `ACTUATOR_INCOMPATIBLE` | Yes | Yes, same attempt UUID | No | No |
| `GUARD_DENIED` | Yes | Yes, same attempt UUID | No | No |
| `TRANSDUCTION_REJECTED` | Yes | Yes, same attempt UUID | No | No |
| `WORLD_EXECUTION_FAILED` | Yes | Yes, same attempt UUID | No successful execution | No |
| `ACTION_EXECUTED_CAUSAL_TRACKING_FAILED` | Yes | Yes, fixed physical UUID | Yes | No grounded observation, so no |
| `ACTION_EXECUTED_OBSERVATION_PENDING` | Yes | Yes, fixed physical UUID | Yes | Not yet; only after a matching completed transition |
| `EXECUTED_AND_OBSERVED` | Yes | Yes, fixed physical UUID | Yes | Yes, subject to valid evaluator evidence |

Thus a guard-denied or world-failed attempt may have identity but is not a
Feedback event. Event identity becomes relevant only after successfully
executed, causally grounded HIT/MISS evidence exists.

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

For `ALREADY_APPLIED`, counters, confidence, repeatability, receipt, and
`updated_at_world` remain byte/value unchanged; no clock is consulted. Conflict
also changes no metric, timestamp, or receipt.

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

This matrix primarily models process failure. File fsync and successful directory
fsync strengthen host/power-loss durability, but the current directory fsync is
best-effort and unsupported/filesystem failure is swallowed. The design does not
claim universal power-loss safety.

| Crash point | Authoritative record | Authoritative receipt | Mutation may already be authoritative? | Blind mutation retry safe? | Reconciliation required? | Later retry behavior | Visible result / uncertainty |
|---|---|---|---:|---:|---:|---|---|
| Before transaction begins | old | absent | No | Yes | No | May apply once | No result |
| After in-process RLock acquisition | old | absent | No | Yes | No | May apply once | No result |
| After interprocess flock acquisition | old | absent | No | Yes | No | May apply once | No result |
| After fresh authoritative read | old | absent | No | Yes | No | May apply once | No result |
| After receipt lookup confirms absent | old | absent | No | Yes | No | May apply once | No result |
| After target lookup / representation validation | old | absent | No | Yes | No | May apply once | No result |
| After TargetCore validation | old | absent | No | Yes | No | May apply once | No result |
| After policy validation | old | absent | No | Yes | No | May apply once | No result |
| After fresh operational metrics read | old | absent | No | Yes | No | May apply once | No result |
| After intended record + receipt constructed | old | absent | No | Yes | No | May apply once | No result |
| During temp-file write | old | absent | No | Yes | No | May apply once | `WRITE_FAILED` if reported |
| After file flush, before file fsync | old | absent | No | Yes | No | May apply once | `WRITE_FAILED`/no result |
| After file fsync, before atomic replace | old | absent | No | Yes | No | May apply once | `WRITE_FAILED`/no result |
| Immediately before atomic replace | old | absent | No | Yes | No | May apply once | `WRITE_FAILED`/no result |
| Immediately after atomic replace | updated | present | Yes, both together | No | Yes if call outcome unknown | Read receipt first; same digest is `ALREADY_APPLIED` | Indeterminate/no result |
| After replace, before directory fsync | updated in current namespace | present with record | Yes, both together; power-loss durability not yet strengthened | No | Yes | Read receipt first | Indeterminate; host-loss caveat |
| After best-effort directory fsync, before readback | updated | present | Yes | No | Yes | Read receipt first | Indeterminate; fsync may be unsupported |
| During readback | updated | present | Yes | No | Yes | Same digest becomes `ALREADY_APPLIED` | `READBACK_FAILED`/indeterminate |
| After successful readback | updated | present | Yes, confirmed | No mutation retry; duplicate call is safe | No | `ALREADY_APPLIED` | `UPDATED` was constructible |
| After result construction, before caller receives it | updated | present | Yes, confirmed | No mutation retry; duplicate call is safe | No | `ALREADY_APPLIED` | Lost acknowledgement |

Atomic replacement permits only the complete before-state or complete combined
after-state; never counters without receipt or receipt without counters.

Atomic namespace replacement is distinct from rename durability across sudden
host/power loss. The sibling temp file is flushed and file-fsynced before
replace; directory fsync is attempted afterward. Process-restart semantics use
the authoritative namespace state observed after reopening. Stronger claims for
filesystems where directory fsync is unsupported remain out of scope.

## One-Time `updated_at_world` Transaction Value

For a new event, `intended_updated_at_world` is generated exactly once while
constructing the intended authoritative post-state. That exact value is used in
the updated native record, complete envelope serialization, resulting-record
fingerprint/receipt proof, immediate expected-state readback, and reconciliation
of an indeterminate write. Readback, reconciliation, and retry comparison never
call the clock again.

The deterministic transaction state is `(before state, evidence,
intended_updated_at_world) -> intended after state`. The receipt fingerprint
binds the complete canonical resulting record, including that timestamp, so an
unrelated state with coincidentally equal counters cannot confirm transaction F.
Immediate reconciliation checks this exact post-state. Much later, legitimate
events may have advanced the same record; a normal duplicate F+D then relies on
the durable receipt and returns `ALREADY_APPLIED` without requiring the current
record to equal F's historical fingerprint. The fingerprint proves the original
transaction; it does not freeze the record forever.

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
sibling lock file `Memory/ExpSM/ExpSM_data.lock`, never on the replaceable data
file inode. The first implementation is explicitly Linux/Fedora scoped.

Every authoritative writer uses one lock order:

1. acquire the existing process-wide/path-local in-process `RLock`;
2. open the stable sibling lock file;
3. acquire `fcntl.flock(lock_fd, LOCK_EX)`;
4. fresh-read and perform receipt/target/policy validation;
5. construct, temp-write, file-fsync, atomically replace, directory-fsync, and
   read back the complete store;
6. release flock;
7. close the lock file;
8. release the in-process `RLock`.

The RLock serializes same-process threads; flock serializes cooperating writer
processes. Failure to open the lock file or acquire the exclusive lock returns a
typed infrastructure/lock failure; no write proceeds and there is no RLock-only
fallback. Every ExpSM writer must cooperate before v2 is enabled.

| Case | Required behavior |
|---|---|
| same event, two threads | one update, one `ALREADY_APPLIED` |
| same event, two processes | OS lock; one update, one `ALREADY_APPLIED` |
| different events, same record | serialize; second uses fresh metrics |
| different events, different records | serialize whole-file replacement |

The guarantee covers cooperating writers on the same lock-capable
host/filesystem, not non-cooperating writers.

## Authoritative ExpSM Writer Inventory

| Writer/path | Current write/lock discipline | Stage-1 requirement before v2 |
|---|---|---|
| `NFPExpSMCreateWriter` | `ExpSMStoreTransaction`; in-process RLock only | shared dual-format reader and common lock protocol |
| `NFPFeedbackApplyWriter` | `ExpSMStoreTransaction`; in-process RLock only | common lock protocol; receipts disabled in Stage 1 |
| `ExpSMCommitWriter` | complete-store transaction write without enclosing common read/modify/write lock | move whole cycle under common lock |
| `ExpSMUpdateWriter` | fixed `.tmp` replace; no shared lock/fsync protocol | migrate to common transaction and lock |
| `ValueFeedbackUpdateWriter` | fixed `.tmp` replace; no shared lock/fsync protocol | migrate to common transaction and lock |
| `ExpSMOutcomeFeedback` | legacy `.tmp` replace and bounded keys; no shared lock | migrate entire read/modify/write cycle |
| `Memory/ExpSM/Exp_CRUD.py::ExpSMCRUD` | direct truncating JSON save; no lock/atomic replace | migrate or prohibit authoritative use before v2 |

Draft-store writers are not authoritative `ExpSM_data.json` writers. Any future
helper or migration utility targeting that file must use the same infrastructure;
tests writing isolated temporary fixtures are not production writers.

## Two-Stage Writer / Format Migration

**Stage 1 - persistence infrastructure compatibility** is reviewed and merged
separately. It introduces one dual-format reader accepting the current
unversioned object and future envelope v2, implements the stable lock-file
protocol, and migrates every inventoried writer to the exact common lock order.
During Stage 1 all authoritative writes remain in the current unversioned
`{experience, reflexes}` format; receipts and envelope-v2 writes are disabled.
Concurrent-writer tests prove no repository writer bypasses the lock.

**Stage 2 - envelope v2 and durable receipts** begins only after Stage 1. One
repository-wide capability switch then permits v2 serialization, occurrence
identity/digest, receipt insertion, combined commit, `ALREADY_APPLIED`, and
`EVENT_CONFLICT`. Once a store is v2, every writer preserves v2 and receipts;
downgrading it or serializing only familiar record sections is prohibited.

One replay-aware writer is insufficient. Process A can lock and read S0 while
old process B ignores flock, reads S0, and writes update B as S1; A can then
replace its stale S0-derived candidate as S2 and erase B. An old writer may also
reject v2 or rewrite familiar sections and discard receipts. Therefore all
readers/writers expected to touch the store must be dual-format/lock-compatible
before the Stage-2 switch. Format rollout and writer migration are inseparable.

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

The current authoritative format is an unversioned top-level object with
`experience` and `reflexes` maps, not a list. Stage-1 new readers normalize both
that current format and envelope v2 into one internal model. Legacy and native
V1 records remain unchanged. Stage-1 writers continue emitting only the current
unversioned format under the common lock. Old readers/writers are not declared
v2-compatible and must not touch a v2 store.

Only the Stage-2 repository-wide switch permits an atomic whole-envelope v2
write. No historical receipt is fabricated, no v2 store may be downgraded, and
Production Memory migration remains deferred while temporary-store migration
and round-trip tests are reviewed.

## Durable Duplicate Protection Vs Pending-Event Durability

The receipt ledger protects Feedback events that reach the authoritative apply
transaction. Given valid event/evidence supplied to apply, once it is committed,
lost acknowledgement, process restart, `READBACK_FAILED`, or reconstructed
duplicate request cannot count that committed event again.

It does **not** make transient pre-apply state durable. If a process fails after
physical action, observation, or evaluation but before authoritative apply, and
the execution/evidence objects exist only in memory, that unapplied event may be
lost. A receipt cannot recover an event never committed. The first implementation
does not claim that all executed actions or pending Feedback survive restart,
that all unapplied evidence is recoverable, or that automatic learning is
crash-complete.

Durable pending-learning recovery (for example a Feedback outbox or pending-event
journal) is a separate future problem and is neither designed nor implemented
here. A receipt ledger is not a pending-event queue.

## Runtime Integration Gate

This design adds no implementation, journal, schema field, Memory change,
automatic learning, or `_run_tick()` wiring. Occurrence propagation, digest
types, v2 validation, interprocess locking, combined commit, reconciliation,
restart/crash/concurrency tests, and compatibility tests require a separate
implementation review/checkpoint. Automatic runtime integration remains blocked
until duplicate suppression is implemented/reviewed **and** the project decides
whether pre-apply event loss is acceptable or requires a durable outbox. Replay
receipts alone do not complete autonomous crash recovery; runtime integration
requires its own later design pass.
