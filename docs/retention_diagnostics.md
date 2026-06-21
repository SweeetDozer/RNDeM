# Retention Diagnostics

This audit pass adds read-only runtime growth counters. It does not prune,
compact, delete, score, decay, reorder, or write memory.

## Measured

- ContextMemory event count, raw frame count, and window count.
- Recent marker counts over the last 200 context events.
- ActiveContextField runtime pattern count.
- ActionCandidateField runtime candidate count.
- EvaluationField runtime entry count.
- AKBSMAssociationField runtime entry count.
- ExperienceCandidateBuffer group count and total candidate ids held by groups.
- ExpSM draft-store total count and draft status counts.
- Last ContextMemory retention result when available.
- Marker-specific side-list counts, tick bounds, stale-entry counts, and last
  side-list retention result.
- Estimated pressure from context event count: low below 500 events, medium below
  2000 events, high at 2000 events or more.

If a structure is not present or is not countable, the diagnostic reports
`None`/`unknown` and records a warning instead of inventing a value.

## Not Measured

- Object sizes in bytes or process RSS.
- Long-term semantic importance.
- Safety of deleting, merging, or compacting any item.
- User-facing quality of retained experiences.
- ExpSM/AKBSM graph density beyond the runtime association field count.
- Hidden Python/container overhead.

## Risk Areas

- ContextMemory events grow monotonically during a run.
- Raw frames and windows can grow with continuous sensory input.
- Side lists are now pruned after event retention, but unknown-tick entries are
  preserved by default and can still require inspection.
- Candidate buffers and draft stores can accumulate if consolidation does not
  resolve them.
- Runtime-only fields can retain stale entries if TTL/decay semantics regress.
- Debug snapshots are intentionally bounded, so diagnostics use underlying
  containers for exact counts.

## Future Policy Options

- Retention budgets per structure.
- Explicit compaction policies for old ContextMemory events.
- Draft-store archival and review TTLs.
- Runtime-only field pressure feedback.
- Separate diagnostics for process memory and serialized storage size.
- Policy-gated pruning modules with verifier coverage before activation.
- Side-list compaction/summarization before pruning.
