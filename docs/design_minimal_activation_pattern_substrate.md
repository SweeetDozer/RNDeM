# Design: Minimal Activation Pattern Substrate

## Status

Post-v1 architecture/design document.

This document is docs/verifier only. It does not implement runtime pattern
classes, `_run_tick()` wiring, pattern persistence, sensor adapters, semantic
recognition, text/token semantic input, AKBSM writes, ExpSM writes, real
ContextMemory placement, pattern replay scheduling, or cross-modal binding.

This document does not implement runtime pattern classes.

The Natural Pattern Data Contract defines what RNDeM considers fundamental
data. This design defines the first concrete internal representation boundary
for that data.

Natural Pattern Data Contract defines what RNDeM considers fundamental data.

## Design Goal

Define a minimal implementation-ready substrate for:

- ActivationPattern
- PatternFrame
- PatternTrace
- PatternOrigin
- PatternModality
- PatternTopology
- PatternSimilarity
- PatternReactivation

The next implementation pass should be isolated and scenario/test driven. It
should not be wired into normal runtime or `_run_tick()`.

## Fundamental Decision

Use a common pattern envelope with modality-specific topology.

Do not force all modalities to share the same geometric shape.

Conceptually:

```text
ActivationPattern
|-- modality
|-- origin
|-- topology
|-- activation values
|-- active-time metadata
`-- provenance
```

The common abstraction is the activation-pattern contract. The topology/shape
belongs to the modality.

The topology/shape belongs to the modality.

Examples:

- visual -> spatial field topology
- audio -> temporal/frequency-like topology
- internal -> distributed state/channel topology
- pain/damage -> internal channel topology
- reward -> internal evaluative channel topology
- action -> action/motor channel topology

These are examples, not permanent hardware representations.

## PatternModality

Minimum modalities:

- VISUAL
- AUDIO
- INTERNAL
- PAIN_DAMAGE
- REWARD_SUCCESS
- ACTION

Memory/reactivation is not itself a sensory modality.

A reactivated visual pattern remains VISUAL. A reactivated audio pattern
remains AUDIO. Its origin changes; its modality does not.

Modality expresses what kind of activation it is.

## PatternOrigin

Minimum origins:

- EXTERNAL_SENSORY
- INTERNAL_STATE
- INTERNAL_REACTIVATION
- ACTION_GENERATED

Origin expresses how the current activation entered the substrate.

Do not conflate modality and origin.

Future extension points may include simulated sensory origin, imported
fixture-origin, or tool-mediated origin, but the v1.x implementation should stay
minimal.

## Critical Provenance Rule

An internally reactivated pattern is not new environmental evidence.

Internal replay may participate in reasoning. Internal replay may activate
associations. Internal replay may influence expectations. Internal replay may
influence action preparation. Internal replay may be compared to current
external sensory patterns.

But INTERNAL_REACTIVATION must not by itself count as fresh external
confirmation of an AKBSM relation.

INTERNAL_REACTIVATION must not by itself count as fresh external confirmation.

Repeated self-replay must not allow RNDeM to strengthen a belief merely by
remembering it repeatedly.

Internal reactivation alone must not generate a new environmental consequence
record.

Internal reactivation alone must not generate a new environmental consequence record.

Future AKBSM/ExpSM evaluation must preserve provenance.

## ActivationPattern

ActivationPattern is an immutable or effectively immutable occurrence-level
activation snapshot.

Required conceptual fields:

- pattern_id
- modality
- origin
- topology
- values
- active_tick
- source_ref / provenance_ref optional

Do not require a human-readable semantic name.

Optional debug metadata may exist separately. Pattern identity must not be
derived from a debug label.

One ActivationPattern represents one modality/domain occurrence.

Do not create multimodal ActivationPattern payloads. Cross-modal binding
belongs to a future episode/context/association layer.

Cross-modal binding belongs to a future episode/context/association layer.

Example future relationship:

```text
visual pattern V
audio pattern A
internal pattern I
```

may be bound by a future event/episode structure. Their raw values should not
be merged into one pattern merely because they occurred together.

## Values

The first implementation should use simple normalized numeric activation values
in the range:

```text
0.0 .. 1.0
```

This is an implementation substrate choice, not a claim that biological neurons
operate identically.

Do not add symbolic meaning to individual values.

## PatternTopology

PatternTopology is a lightweight descriptor of how activation values are
arranged. It describes structure without defining semantic meaning.

Conceptual examples:

```text
shape=(16,16)         # visual field
shape=(32,8)          # possible audio time/frequency field
shape=(12,)           # internal channels
shape=(6,)            # action channels
```

Do not interpret shape dimensions as semantic labels.

Topology may include a topology/domain identifier if useful. Keep the first
implementation simple.

## PatternFrame

PatternFrame is a collection of activation patterns belonging to one logical
active-time slice.

PatternFrame is a collection belonging to one logical active-time slice.

Conceptually:

```text
PatternFrame
|-- active_tick
`-- patterns[]
```

A frame may contain multiple modalities simultaneously.

Example:

```text
tick 120:
  visual pattern
  audio pattern
  internal-state pattern
```

The patterns remain distinct. PatternFrame is not semantic interpretation.
PatternFrame does not itself mean "event".

## PatternTrace

PatternTrace is a bounded ordered trace of occurrences across active time.

Conceptually:

```text
PatternTrace
|-- trace_id
|-- frames / pattern occurrences
|-- start_tick
|-- end_tick
`-- provenance
```

For the minimal implementation, keep it generic.

Do not decide final long-term retention/consolidation policy yet.

A PatternTrace is not automatically AKBSM knowledge, ExpSM experience, or a
chronicle fact. It is substrate material that later systems may consume.

## Active Time

Use RNDeM active-time/tick semantics where practical.

`active_tick` is the primary temporal coordinate of the pattern substrate.

active_tick is the primary temporal coordinate.

Do not make wall-clock time fundamental to pattern identity.

External timestamps may later exist as metadata, but they are not the
fundamental lifetime axis.

This aligns with the existing RNDeM heart/active-tick concept. Do not implement
Heart integration in this pass.

Do not implement Heart integration in this pass.

## PatternSimilarity

PatternSimilarity is a measurement boundary, not semantic identity.

Conceptually:

```text
similar(pattern_a, pattern_b)
```

may only be directly meaningful when topology/modality compatibility rules
permit comparison.

First implementation recommendation:

- same modality
- compatible topology
- normalized activation-distance/similarity

Do not choose a sophisticated neural embedding algorithm yet.

Do not use human labels.

Similarity must not automatically create AKBSM relations.

Return a similarity score as a measurement, not truth.

## Cross-Modality Similarity

Do not directly compare raw VISUAL values with raw AUDIO values in the minimal
substrate.

Raw cross-modal similarity is not part of the minimal substrate.

Cross-modal relationships belong to learned association/binding layers.

## PatternReactivation

PatternReactivation creates a new occurrence that refers to a previously
experienced pattern/trace while preserving modality and changing
provenance/origin.

Conceptually:

```text
external VISUAL pattern P at tick 100

later internal replay:
VISUAL pattern P' at tick 300
origin = INTERNAL_REACTIVATION
source_ref = P / trace
```

P' is a new activation occurrence. It is not the same event as P.

It may reproduce all or part of P's activation values.

Do not define final replay fidelity/noise model yet.

## External Vs Internal Equality

Two patterns may have identical activation values while representing different
epistemic situations.

Example:

```text
Pattern A:
modality = VISUAL
origin = EXTERNAL_SENSORY

Pattern B:
modality = VISUAL
origin = INTERNAL_REACTIVATION
```

Their values may be identical. They are not equivalent as evidence.

## Action Patterns

ACTION is a normal activation modality/domain in the substrate.

An action pattern:

- does not contain its own consequence
- does not declare whether it succeeded
- does not directly write ExpSM

Consequences arrive later through sensory/internal patterns.

This preserves:

```text
action
-> environment
-> consequence
-> sensory/internal activation
```

rather than:

```text
action function
-> return value treated as truth
```

## Pain / Reward / Internal Patterns

PAIN_DAMAGE and REWARD_SUCCESS may initially be represented as dedicated pattern
modalities/domains because they are important evaluative signals.

However:

- they are still activation patterns
- they are not magic scalar truth injected directly into AKBSM
- they do not directly authorize memory writes
- their interpretation belongs to later evaluation/experience mechanisms

Do not overdesign affect/emotion here.

## Pattern Identity

Distinguish:

- occurrence identity
- pattern similarity
- stable learned entity identity

An ActivationPattern.pattern_id identifies the occurrence/object.

It does not mean that two different occurrences with similar values are already
the same learned entity.

It does not mean that two different occurrences with similar values are already the same learned entity.

Stable entities are future AKBSM/pattern-abstraction work.

## Debug Labels

Optional debug labels may be allowed as non-semantic metadata only.

```text
debug_name="dog"
```

does not mean the pattern is a dog.

No runtime logic may branch on debug labels.

This preserves the existing debug-name safety philosophy.

## Mutability

Recommend immutable/frozen pattern/frame objects for the first implementation.

New sensory state should create new occurrences rather than mutate historical
occurrences in place.

A trace/container may accumulate references according to its own controlled API.

Reasons:

- historical occurrence identity should remain stable
- provenance should remain auditable
- replay should create a new occurrence

## No Persistence Yet

The minimal substrate remains in-memory only.

Do not define:

- disk persistence
- AKBSM writes
- ExpSM writes
- ContextMemory placement
- long-term trace storage

Those require later passes.

## No _run_tick Wiring Yet

The first implementation of this substrate must initially be isolated.

Do not wire it into `_run_tick()` in the next implementation pass unless a
later explicit integration pass approves it.

Initial validation should use isolated/scenario/test harnesses.

## Minimal Next Implementation Scope

The next implementation pass should implement only:

- PatternModality
- PatternOrigin
- PatternTopology
- ActivationPattern
- PatternFrame
- PatternTrace
- PatternSimilarity
- PatternReactivation

Suggested module location:

```text
clc/patterns/
```

Possible files, adjusted to project style:

```text
clc/patterns/model.py
clc/patterns/similarity.py
clc/patterns/reactivation.py
```

Keep it small.

Do not implement modality encoders. Do not implement sensor hardware. Do not
implement semantic recognition.

## Required Isolated Scenarios For Next Implementation

Future isolated scenario coverage should include:

- create visual external pattern
- create audio external pattern
- create internal-state pattern
- create action pattern
- frame contains multiple distinct modalities
- same-modality compatible patterns can be compared
- incompatible topology comparison is rejected/safe-no-op
- raw cross-modality similarity is rejected
- reactivation preserves modality
- reactivation changes origin to INTERNAL_REACTIVATION
- reactivation creates new occurrence identity
- reactivated pattern preserves source provenance
- reactivated pattern is not marked as external evidence
- identical external/replayed values remain epistemically distinct
- debug labels do not define identity
- action pattern contains no consequence truth
- no AKBSM/ExpSM/ContextMemory writes occur

## Deferred Questions

Deferred:

- camera transduction
- microphone transduction
- exact audio representation
- visual resolution
- sparse representation
- compression
- long-term trace retention
- pattern consolidation
- stable entity formation
- cross-modal episode binding
- cross-modal learned association
- prediction
- internal replay scheduling
- working-memory placement
- AKBSM pattern-node mapping
- ExpSM pattern serialization
- AKBSM revision thresholds
- sensor noise models
- motor hardware

## Safety Boundaries

This design does not weaken the Natural Pattern Data Contract.

This pass does not create or modify:

- runtime pattern classes
- `_run_tick()`
- normal runtime wiring
- camera/microphone adapters
- text/token semantic input
- class labels as semantic truth
- AKBSM writes
- new ExpSM writes
- real ContextMemory placement
- pattern persistence
- pattern replay scheduling
- cross-modal binding implementation
- `semantic_core.json`
- `technical_feedback_patterns.json`

Do not tag or merge from this design pass.
