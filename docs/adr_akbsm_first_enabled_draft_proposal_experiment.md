# ADR: First Enabled AKBSM Draft Proposal Experiment

## Status

Accepted / controlled test-scenario experiment implemented.

This ADR now has a narrow implementation: explicit test/scenario-only provider
proposal creation from `AKBSMAssociationProbe`. It does not enable normal
runtime proposal creation, enable AKBSM writes, change runtime behavior,
connect proposals to behavior modules, connect `PolicyPressureReview` to AKBSM
proposals, enable Mode C, or add marker 36.

## Context

`v0.0.4` marks the disabled AKBSM draft proposal scaffold checkpoint.
`AKBSMAssociationProposal` and `AKBSMDraftProposalProvider` exist, but
`akbsm_draft_proposals_enabled` defaults to `False`, the provider remains
no-op by default, disabled proposal scenarios pass, no proposal commit path
exists, and AKBSM writes remain blocked.

The first controlled experiment can create temporary draft proposal metadata
when explicitly enabled by scenario/test policy. This ADR decides that source
and its boundaries before any storage or write path exists.

## Decision

The first controlled enabled AKBSM draft proposal experiment may use
`AKBSMAssociationProbe` as the only proposal source.

AKBSMAssociationField is deferred.

The experiment remains disabled by default. It may be enabled only by an
explicit scenario/test policy flag. It must not be enabled in normal runtime
and must not be enabled by `safe_demo`, `draft_only`, or `mutating_memory`
defaults.

## First Enabled Source

`AKBSMAssociationProbe` is closest to associative evidence. It observes possible
association evidence without being a behavior selector. It is less dangerous
than pressure, review, scoring, or action modules because it does not need to
justify an already selected action.

A draft proposal from this source must mean:

> there is enough evidence to suggest reviewing a possible association

It must not mean:

> write this association to AKBSM

It must not mean:

> approve this memory write

It must not mean:

> change behavior

It must not mean:

> change scoring

It must not mean:

> create a relation type

It must not mean:

> create a concept

## Forbidden Sources

These sources are forbidden for the first enabled draft proposal experiment:

- `AKBSMAssociationField`
- `PolicyPressureReview`
- Mode C advisory
- `DecisionSelector`
- `ActionScoring`
- `ActionProposer`
- `ModeActionGuard`
- ValueFeedback
- ExpSM writers/update paths
- memory writers
- `MemoryWriteReviewModule`
- `ExpSMUpdateWriter`
- `ValueFeedbackUpdateWriter`
- any AKBSM writer/save path

Proposal creation must start from association evidence, not from behavior
pressure, scoring, selected actions, guards, value feedback, Mode C advisory,
or write-side modules.

## Allowed Proposal Payload

The future implementation may produce `AKBSMAssociationProposal` metadata only.

Required payload constraints:

- proposals must be immutable metadata
- proposals must include source, tick, subject id, relation type, object id,
  confidence, evidence, and reason
- proposals must have `commit_allowed=False`
- `commit_allowed=True` remains rejected
- proposal confidence must stay within `0.0..1.0`
- proposal evidence must be explicit review evidence

The future implementation cannot set `commit_allowed=True`.

## Allowed Temporary Storage

Allowed storage for the future experiment:

- temporary ContextMemory metadata
- scenario/debug output

The proposal lifetime must be temporary. The proposal dies with
context/session/scenario unless a future explicit ADR introduces a review-gated
persistence mechanism.

## Forbidden Effects

The future experiment must not:

- cannot write AKBSM
- cannot write ExpSM
- cannot create concepts
- cannot create relation types
- cannot persist proposals to permanent files
- persist proposals to permanent association files
- affect behavior
- affect scoring
- affect guards
- affect Mode C
- affect `DecisionSelector`
- affect `ActionScoring`
- affect `ActionProposer`
- affect `ModeActionGuard`
- connect `PolicyPressureReview` to AKBSM proposals
- connect `PolicyPressureReview` to memory gates
- add marker 36

## Implemented Experiment Boundary

The controlled provider experiment exists in
`clc/runtime/akbsm_draft_proposal.py`.

It is enabled only by explicit test/scenario policy construction:

- `akbsm_draft_proposals_enabled=True`
- `source="AKBSMAssociationProbe"`

Normal runtime remains disabled and does not wire the provider into
`CLCRuntime`, `_run_tick()`, scoring, selection, guards, Mode C, writers, or
storage.

Generated proposals are temporary metadata-only
`AKBSMAssociationProposal` objects with `commit_allowed=False`.
`commit_allowed=True` is rejected.

## Required Future Implementation Constraints

Any future implementation pass must:

- remain disabled by default
- require an explicit scenario/test policy flag
- keep normal runtime defaults unchanged
- keep `safe_demo`, `draft_only`, and `mutating_memory` defaults disabled
- create temporary draft proposal metadata only
- create `commit_allowed=False` proposals only
- reject `commit_allowed=True`
- avoid all AKBSM and ExpSM writes
- avoid permanent proposal persistence
- keep proposal creation source-limited to `AKBSMAssociationProbe`
- keep all forbidden sources unreferenced by the implementation
- preserve tick order and `ContextMemoryManager.apply_pending()` placement
- preserve retention timing
- avoid `_run_tick()` refactors except tiny hook placement explicitly approved
  by the implementation pass

## Required Future Scenario Coverage

The future implementation pass must add scenario coverage before or with
implementation:

- enabled probe creates temporary draft proposal metadata
- proposal has `commit_allowed=False`
- `commit_allowed=True` remains rejected
- proposal does not mutate AKBSM
- proposal does not mutate ExpSM
- proposal does not create relation types
- proposal does not create concepts
- proposal does not affect `DecisionSelector`, `ActionScoring`,
  `ActionProposer`, or `ModeActionGuard`
- proposal does not involve Mode C
- PolicyPressureReview cannot create proposal
- normal default runtime still creates no proposals
- disabled fixtures still pass

## Required Future Verifier Coverage

Future verifier expectations:

- verify enabled experiment flag is explicit
- verify default remains disabled
- verify proposal source is `AKBSMAssociationProbe` only
- verify forbidden sources are not referenced by implementation
- verify proposal payload is metadata-only
- verify `commit_allowed=False`
- verify commit_allowed=False
- verify commit_allowed=True rejected
- verify no AKBSM mutation
- verify no ExpSM mutation
- verify no permanent proposal persistence
- verify no behavior/scoring/guard/Mode C integration
- verify marker 36 absent
- verify memory hashes unchanged
- verify provider remains no-op by default
- verify no proposal commit path exists

## Memory Safety Requirements

Real memory hashes must stay unchanged in safe checks:

```text
Memory/ExpSM/ExpSM_data.json:
6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e

Memory/AKBSM/AKBSM_ne.json:
0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd
```

Forbidden storage:

- `Memory/AKBSM/*`
- `Memory/ExpSM/*`
- `semantic_core.json`
- `technical_feedback_patterns.json`
- any permanent proposal file
- any permanent association file

## Why This Is Not An AKBSM Write

The proposed future artifact is reviewable evidence metadata, not a graph
operation. It must not create, update, delete, approve, or persist AKBSM
associations. It must not create relation types or concepts. It must not become
input to an AKBSM writer or permanent storage path.

The proposal says only that associative evidence may deserve review. It does
not authorize mutation.

## Consequences

The project gets a narrow first enabled experiment boundary without accepting
any AKBSM write path.

The safest source is chosen before implementation work starts:
`AKBSMAssociationProbe` only. `AKBSMAssociationField` and all behavior,
pressure, scoring, action, value, Mode C, ExpSM, and memory writer paths remain
outside the first experiment.

Normal runtime behavior remains unchanged until a later implementation pass is
explicitly approved.

## Rejected Alternatives

- `PolicyPressureReview` as proposal source
- Mode C advisory as proposal source
- `DecisionSelector`-driven proposal generation
- ValueFeedback-driven proposal generation
- `AKBSMAssociationField` as first enabled source
- permanent proposal storage
- direct AKBSM write
- creating relation types from proposals
- creating concepts from proposals

These alternatives are either behavior-pressure-driven, too broad, too close to
write paths, or make proposals look like commands instead of reviewable
evidence metadata.

## Next Steps

1. Review and merge this ADR branch.
2. Stop before implementation unless an explicit implementation pass is
   approved.
3. If approved later, implement only disabled-by-default scenario/test-flagged
   proposal metadata from `AKBSMAssociationProbe`, with the required scenarios
   and verifiers in the same pass.
