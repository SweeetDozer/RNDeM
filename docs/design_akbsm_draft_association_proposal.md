# Draft-only AKBSM Association Proposal Design

Status: design accepted / disabled scaffold implemented / AKBSM writes not implemented

## Context

AKBSM is associative memory/query support. Current runtime code may read AKBSM
through association probes and runtime-only association fields, but no runtime
module may mutate AKBSM.

This document refines the future Mode 1 direction from
`docs/adr_akbsm_write_policy.md`: a draft-only association proposal that is
metadata-only and cannot commit. The current implementation adds only a
disabled-by-default runtime scaffold; it does not add a writer, gate, marker,
scenario, storage path, or runtime behavior.

## Current policy

AKBSM writes remain blocked.

No runtime module may mutate AKBSM.

`AKBSMAssociationProposal` and `AKBSMDraftProposalProvider` exist as runtime
scaffold only in `clc/runtime/akbsm_draft_proposal.py`.

`akbsm_draft_proposals_enabled` defaults to `False` in all runtime profiles.

The provider is no-op and returns no proposals.

This document remains design-only for behavior and AKBSM writes.

## Design goal

`AKBSMAssociationProposal` should mean:

> the runtime observed enough evidence to propose that an association might
> exist

It must not mean:

> write this association into AKBSM

The proposal is a conservative review artifact. It is evidence metadata, not a
graph operation.

## Non-goals

- Implement AKBSM writes.
- Enable AKBSM writes.
- Enable runtime AKBSM proposal creation.
- Persist runtime AKBSM proposals.
- Connect any module to AKBSM writers.
- Change default behavior.
- Enable Mode C behavior.
- Connect `PolicyPressureReview` to memory gates.
- Change tick order, retention timing, scoring, guards, or memory writers.
- Add marker 36.

## Proposal shape

Payload:

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

- `commit_allowed` defaults to `False`.
- The proposal is immutable.
- The proposal is metadata-only.
- The proposal cannot call writers.
- The proposal cannot mutate AKBSM.
- The proposal cannot create relation types.
- The proposal cannot create concepts by itself.

## Allowed proposal sources

Possible future first sources if proposal creation is explicitly enabled later:

- `AKBSMAssociationProbe`
- `AKBSMAssociationField`
- repeated stable real-input scenarios
- explicit review-only modules

Recommended first future source: `AKBSMAssociationProbe` or
`AKBSMAssociationField`, whichever is closest to read-only AKBSM association
evidence at implementation time.

## Forbidden proposal sources

Forbidden direct sources:

- `DecisionSelector`
- `ActionScoring`
- `ActionProposer`
- `ModeActionGuard`
- `PolicyPressureReview`
- Mode C advisory
- `ValueFeedbackUpdateWriter`
- `ExpSMUpdateWriter`
- any permanent memory writer

Proposal creation should start from association evidence, not behavior pressure
or write-side modules.

## Proposal storage options

Option A: `ContextMemory` temporary `MODULE_UPDATE` / draft metadata.

Option B: separate draft proposal list.

Option C: scenario/debug output only.

Option D: future DraftMemory subsystem.

Recommended first future storage: `ContextMemory` temporary metadata or
scenario/debug output only.

No permanent file writes.

No AKBSM file writes.

No proposal storage is implemented in the current scaffold.

## Validation requirements

Future proposal validation must require:

- `subject_id` exists or is explicitly unresolved.
- `object_id` exists or is explicitly unresolved.
- `relation_type` exists in an approved relation registry.
- `confidence` is within `0.0..1.0`.
- `evidence` is non-empty.
- `reason` is non-empty.
- `commit_allowed` is `False` by default.

Current scaffold validation requires confidence within `0.0..1.0` and rejects
`commit_allowed=True`.

## Confidence/evidence policy

Low confidence: no proposal, or debug-only note.

Medium confidence: draft proposal allowed only if evidence threshold passes.

High confidence: draft proposal allowed, but still no commit.

No confidence level may trigger permanent AKBSM write.

## Relation type policy

Proposal may reference existing relation types only.

Proposal may not create relation types.

Unknown relation types must be rejected or marked unresolved.

Numeric relation IDs must remain stable.

## Deduplication/conflict policy

Duplicate proposals should merge evidence rather than create spam.

Conflicting proposals must require review.

No proposal may overwrite an existing association.

No proposal may delete an association.

## Auditability

No silent proposal creation is allowed.

Every future proposal must record:

- source
- tick
- evidence
- reason
- confidence
- relation type
- profile
- runtime policy state

## Runtime profile policy

`safe_demo`:

- no permanent AKBSM write
- proposal disabled by default
- current scaffold provider is no-op

`draft_only`:

- draft proposal creation remains disabled by default
- no permanent AKBSM write

`mutating_memory`:

- draft proposal creation remains disabled by default
- permanent AKBSM write still forbidden without separate ADR

## Required future verifiers

- `tools/verify_akbsm_draft_proposal_design.py`
- `tools/verify_akbsm_draft_proposal_scaffold.py`
- future `tools/verify_akbsm_draft_proposal_no_commit.py`
- future `tools/verify_akbsm_proposal_validation.py`
- future `tools/verify_akbsm_relation_type_policy.py`
- future `tools/verify_akbsm_proposal_dedup_conflict.py`
- `tools/verify_memory_mutation_policy.py` update

## Required future scenarios

- `akbsm_proposal_disabled_no_effect`
- `akbsm_draft_only_proposal_no_commit`
- `akbsm_low_confidence_no_proposal`
- `akbsm_medium_confidence_proposal_metadata_only`
- `akbsm_duplicate_proposal_merges_evidence`
- `akbsm_conflicting_proposal_requires_review`
- `akbsm_unknown_relation_type_rejected`

## Rollback / discard

Draft proposals must be discardable without touching AKBSM.

Disabling the future proposal flag must remove proposal creation without
changing runtime behavior.

If a future proposal path mutates AKBSM, writes files, changes relation types,
creates concepts, or affects behavior selection, it must be rejected or
reverted.

## Open questions

- Should the first implementation store proposals in `ContextMemory` metadata
  or scenario/debug output only?
- Should unresolved concept IDs be allowed, or should missing concepts always
  reject the proposal?
- What relation registry should define approved relation types?
- What evidence threshold is enough for medium-confidence draft metadata?
- Should duplicate merge policy keep every evidence item or a bounded sample?
- Should conflict review require a human-facing export before any future commit
  design?
