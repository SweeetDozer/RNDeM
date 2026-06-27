# AKBSM Write Policy

Status: proposed / design-only

## Context

AKBSM is the prototype's associative memory/query support. It is high-risk
because a bad association can corrupt later semantic graph lookup, make weak
evidence look authoritative, or hide a conflict behind a convenient relation.

Current runtime code may query AKBSM through association probes and project
runtime-only association fields, but this ADR does not approve any AKBSM write
implementation. It documents future policy boundaries before any AKBSM write
path exists.

This ADR does not change runtime behavior, enable Mode C, connect
`PolicyPressureReview` to memory gates, add new cognitive markers, add marker
36, or modify ExpSM, value feedback memory, or AKBSM.

## Current Policy

Current AKBSM writes are blocked.

AKBSM is treated as high-risk associative memory.

`safe_demo` must never write AKBSM. It should exercise runtime behavior through
temporary memory copies and leave real AKBSM unchanged.

`draft_only` may allow draft metadata in other memory flows, but it must not
commit AKBSM writes.

`mutating_memory` still does not imply AKBSM writes are allowed. Even where
selected permanent ExpSM or value-feedback writes may be allowed by policy,
AKBSM writes remain blocked by default.

## Decision Not Yet Made

No AKBSM write mode is accepted by this ADR. The recommended current policy is
to stay in Mode 0: no AKBSM writes.

Any move beyond Mode 0 requires a later accepted ADR or implementation pass,
explicit runtime policy, verifier updates, scenario coverage, memory safety
hash checks, auditability, and rollback instructions.

## Candidate Write Modes

### Mode 0: No AKBSM Writes

Current mode. Runtime may query AKBSM and produce runtime-only observations, but
it must not mutate the AKBSM graph.

### Mode 1: Draft-Only AKBSM Proposal

Runtime may create metadata that proposes a possible association, but the
proposal is not a graph mutation and cannot be committed by default.

This is the recommended first future step if AKBSM write work is ever approved.

### Mode 2: Temporary-Session AKBSM Association

Runtime may create an association in temporary session memory only. It must not
touch real AKBSM and must be discarded with the session unless explicitly
exported by a later approved workflow.

This mode remains unapproved.

### Mode 3: Review-Gated Permanent AKBSM Association

Runtime may commit a permanent association only after explicit policy, review,
evidence, registry validation, conflict checks, audit, rollback journal, and
scenario coverage all exist.

This mode remains unapproved.

### Mode 4: Autonomous AKBSM Update

Runtime autonomously creates, changes, or deletes AKBSM relations.

This mode is forbidden.

## Allowed First Write Type

The safest future write-like artifact is a draft-only proposal:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AKBSMAssociationProposal:
    source: str
    tick: int
    subject_id: str
    relation_type: str
    object_id: str
    confidence: float
    evidence: tuple[str, ...]
    reason: str
    commit_allowed: bool = False
```

Rules:

- `commit_allowed` must default to `False`.
- `AKBSMAssociationProposal` is metadata only.
- The proposal must not modify AKBSM.
- The proposal must not create new semantic core concepts by itself.
- The proposal must not create relation types.
- The proposal must include source, tick, evidence, and reason.

First future step recommendation: draft-only AKBSM proposal. Permanent AKBSM
writes should not be implemented until strong scenario coverage and rollback
exist.

## Forbidden Writes

The following are forbidden unless later explicitly approved:

- direct AKBSM graph mutation from runtime observations
- direct AKBSM graph mutation from `PolicyPressureReview`
- direct AKBSM graph mutation from Mode C advisory
- direct AKBSM graph mutation from ValueFeedback
- direct AKBSM graph mutation from `DecisionSelector`
- autonomous relation creation
- autonomous relation deletion
- relation type creation without registry approval
- writing associations with low confidence
- writing associations without evidence
- overwriting existing associations without version/rollback path
- creating new marker IDs
- marker 36

No hidden adapter or renamed helper may create the same direct write effect.

## Runtime Profile Policy

`safe_demo`:

- AKBSM writes forbidden.
- AKBSM proposals forbidden unless explicitly future-enabled as temporary debug
  metadata.
- Real AKBSM hashes must remain unchanged.

`draft_only`:

- Future `AKBSMAssociationProposal` may be allowed as draft metadata only.
- No permanent AKBSM mutation.
- `commit_allowed` remains `False` by default.

`mutating_memory`:

- Permanent AKBSM writes still forbidden by default.
- Future review-gated permanent write requires a separate ADR and verifier
  suite.
- `allow_akbsm_write` must remain false until that later approval exists.

## Required Gates

Future permanent AKBSM write requires:

- explicit `AKBSMWritePolicy` flag
- review gate
- confidence threshold
- evidence threshold
- relation type registry validation
- duplicate/conflict detection
- rollback journal
- audit entry
- scenario coverage
- memory hash verifier update

These gates are cumulative. Missing any gate means no permanent AKBSM write.

## Required Verifiers

Current design-only verifier:

- `tools/verify_akbsm_write_policy_adr.py`

Future verifier requirements:

- future `tools/verify_akbsm_write_draft_policy.py`
- future `tools/verify_akbsm_no_write_safe_demo.py`
- future `tools/verify_akbsm_relation_registry.py`
- future `tools/verify_akbsm_rollback_journal.py`
- `tools/verify_memory_mutation_policy.py` update
- `tools/verify_phase_regression_snapshots.py` update

Required future checks include disabled-by-default behavior, real AKBSM hash
stability in safe checks, duplicate/conflict detection, relation registry
validation, and rollback proof.

## Required Scenario Coverage

Future scenario names:

- `akbsm_write_disabled_no_effect`
- `akbsm_safe_demo_no_write`
- `akbsm_draft_only_proposal_no_commit`
- `akbsm_low_confidence_proposal_rejected`
- `akbsm_duplicate_association_detected`
- `akbsm_conflicting_association_requires_review`
- `akbsm_rollback_journal_required`

These are future scenario names only. This ADR does not add scenario files or
snapshots.

## Auditability

Every proposal must have source, tick, evidence, and reason.

Every future commit must have a review result.

Every future commit must be reversible.

Every future commit must be explainable in logs/docs.

No silent AKBSM mutation is allowed.

## Rollback

Rollback for a future AKBSM write implementation must:

1. Disable the AKBSM write flag.
2. Restore AKBSM from a previous hash-backed snapshot.
3. Replay rollback journal if implemented.
4. Rerun memory hash checks.
5. Rerun scenario and phase regression verifiers.

If disabling the AKBSM write flag does not restore no-write behavior, the
implementation should be reverted.

## Consequences

The project can discuss AKBSM write safety without adding a write path. Current
AKBSM remains read/query support plus runtime-only association projections.

Mode 0 remains the current policy. Mode 1, draft-only AKBSM proposal, is the
only recommended first future step. Permanent writes wait for a separate ADR,
new verifier suite, scenario coverage, and rollback.

Autonomous AKBSM updates are forbidden.

## Open Questions

- Should AKBSM proposals be stored in ContextMemory or separate draft memory?
- Should relation types be fixed numeric IDs only?
- Should AKBSM writes require human approval in early versions?
- Should temporary-session AKBSM associations exist at all?
- Should AKBSM writes be allowed before Mode C behavior is enabled?
- Should AKBSM participate in Mode C advisory decisions?
- What is the minimum evidence threshold for an association?
