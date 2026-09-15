# Natural Pattern Data Contract

## Status

Post-v1 architecture/design contract.

This document is docs-only. It does not implement sensory processing, pattern
processing, memory writers, real ContextMemory placement, AKBSM writes, ExpSM
writes, sensor adapters, file input APIs, direct `_run_tick()` hooks, default
runtime diagnostics, or behavior influence.

`v1.0.0` remains the safe runtime/container baseline. This contract defines the
kind of data substrate future post-v1 CLC development should introduce.

## Core Principle

RNDeM does not fundamentally operate on text, images, audio files, labels, or
symbolic requests.

RNDeM fundamentally operates on activation patterns produced by continuous
interaction with its environment and internal state.

Natural activation patterns are the fundamental data of RNDeM.

## Natural Data

Natural data is data experienced through RNDeM's sensory or internal interfaces
as activation patterns.

Examples:

- visual activation pattern
- audio activation pattern
- body/internal-state activation pattern
- pain/damage pattern
- success/reward pattern
- action activation pattern
- memory replay/reactivation pattern

A natural pattern is what the agent experiences. It is not required to carry a
human-readable label.

## Artificial And Symbolic Data

Artificial/symbolic data includes:

- text token
- string command
- class label
- `"dog"`
- `"fire"`
- image filename
- audio filename
- pre-labeled object
- JSON instruction interpreted directly as meaning

These must not be treated as primary reality.

If RNDeM ever encounters text, text must first exist as natural sensory
phenomena, such as a visible glyph pattern, heard speech pattern, or
motor/writing pattern. Semantic meaning must emerge later through associations.

## Fundamental Processing Model

The fundamental RNDeM model is not:

```text
input
-> process
-> output
```

The intended model is a continuous loop:

```text
environment
-> sensory activation patterns
-> internal activation/state
-> associations / experience / expectations
-> action activation pattern
-> environment changes
-> consequences return through sensory/internal patterns
-> experience changes
-> next activation state
```

There is no special moment where RNDeM is waiting for a prompt. There is no
mandatory request/response transaction.

There is no mandatory request/response transaction.

Input, processing, action, consequence, memory, and internal reactivation are
parts of one continuous living loop.

## Activation Pattern

An activation pattern is a representation-agnostic occurrence of structured
activation in some sensory, internal, memory, or action domain.

At minimum, an activation pattern conceptually includes:

- modality/domain
- activation topology/shape
- activation values
- temporal position/order
- source context
- optional internal origin

This contract does not commit to a specific implementation such as tensor,
matrix, neuron object, sparse vector, or dense vector.

Pattern identity is not the same thing as a human label. Two similar patterns
may later become associated with the same internal entity, but the label must
not be injected as ground truth.

## Modalities

Required conceptual modalities include:

- visual
- audio
- internal/body state
- pain/damage/error
- reward/success
- action/motor
- memory/reactivation

Different modalities may use different topologies:

- visual: spatial activation field
- audio: temporal/frequency-like activation structure
- internal state: distributed state activation
- action: activation over possible motor/action channels

These examples do not lock the future implementation.

## Visual Data

RNDeM should not fundamentally receive:

```text
"This is a dog"
class_id=dog
dog.png interpreted as dog
```

It should receive sensory activation generated from the visual source:

```text
camera/environment
-> visual transduction
-> activation field
-> internal processing
```

A file may later be used as a simulation source for tests, but the file itself
must not become semantic truth.

The file itself must not become semantic truth.

## Audio Data

RNDeM should not fundamentally receive:

```text
"bell"
transcript="hello"
speech token sequence as already-understood meaning
```

Instead:

```text
sound source
-> sensory/transduction layer
-> temporal/frequency activation pattern
-> internal processing
```

Speech meaning must emerge by associating recurring sound patterns with other
experienced patterns.

## Text

Text is not a privileged input modality.

A written word is a visual pattern. A spoken word is an audio pattern. A typed
or written action is a motor/action pattern.

Meaning emerges from association among those patterns and other world
experience. Direct token/text semantic input must not be added to the core CLC
contract.

## Internal Pattern Reactivation

RNDeM must eventually be able to reactivate previously experienced patterns
internally without the external stimulus currently being present.

RNDeM must reactivate previously experienced patterns internally.

Examples:

- memory recall
- expectation
- prediction
- imagined/replayed visual pattern
- replayed sound pattern
- self-instruction
- action preparation

An internally reactivated pattern must be able to participate in the same
internal processing substrate as externally triggered patterns, while retaining
metadata that distinguishes external sensory origin from internal
reactivation.

This is necessary for self-instruction and internal thought.

## Action As Activation Pattern

Action is not merely output.

An action should conceptually be represented as an activation pattern affecting
action/motor channels:

An action activation pattern affects action/motor channels.

Action as activation pattern means affecting action/motor channels.

```text
sensory pattern
-> internal state
-> action activation pattern
-> world consequence
```

The consequence must be learned from subsequent sensory/internal input.
Function return values must not be treated as learned consequences or world
truth.

## Pattern Traces

A PatternTrace is a memory-compatible historical trace of a pattern occurrence,
not necessarily the original full raw activation field forever.

Future design must decide:

- what raw detail is retained
- what abstractions are retained
- how repeated patterns become stable entities
- how similarity is computed
- how traces decay or consolidate

Those decisions are deferred.

## AKBSM Relationship

AKBSM is explicit associative world-model memory.

Principles:

- AKBSM stores explicit nodes/relations, not distributed neural weights.
- An active AKBSM relation represents RNDeM's current asserted model of the
  world.
- A relation may currently be treated as a fact by RNDeM without being
  eternally immutable.
- AKBSM is static in representation but adaptive under experience.

An active AKBSM relation represents RNDeM's current asserted model of the world.

Static means a stored relation does not continuously drift just because
inference is running.

Adaptive means sufficient contradictory experience may cause the relation/node
structure to be revised.

Example:

```text
fire -> temperature -> cold
```

may be RNDeM's current active belief.

Repeated contradictory experience:

```text
fire
-> contact/proximity
-> high-temperature sensory pattern
-> damage/pain consequence
```

may eventually cause reconstruction into:

```text
fire -> temperature -> hot
```

The old incorrect active relation should not remain as active world knowledge
merely because it existed before.

## History Of Changed Knowledge

AKBSM represents the current active world model.

When an old belief is replaced, the old relation may be removed/replaced from
active AKBSM.

The fact that RNDeM previously believed the old relation belongs to chronicle /
letopis memory, not the active AKBSM world model.

The superseded belief belongs to chronicle / letopis memory.

Example historical fact:

```text
At earlier active-time T, I believed fire was cold.
Later experience contradicted this and the active AKBSM relation was revised.
```

This preserves biography/history without polluting the active world model with
obsolete claims.

## Facts And Hypotheses

AKBSM must not be reduced to pure numeric probability.

Distinguish:

- current fact / accepted knowledge
- hypothesis
- possible association
- uncertain relation
- contradicted/revisable knowledge

Confidence/evidence metadata may exist, but confidence is metadata about
support for a relation. Confidence is not the relation itself.

RNDeM should conceptually be able to express:

```text
As far as I know, X is Y.
I currently consider X->Y a fact.
I suspect X may be related to Z.
My previous belief X->Y was contradicted.
```

instead of treating all knowledge as only probabilistic token prediction.

## ExpSM Relationship

ExpSM is operational experience memory.

Conceptually:

```text
pattern/context
-> action pattern
-> observed consequence
-> outcome/effect metadata
```

ExpSM should support:

- when a similar state occurs
- what actions were tried
- what happened afterward

ExpSM is not the historical chronicle. ExpSM is not merely text instructions.
ExpSM is operational experience learned from pattern-action-consequence loops.

Existing v1 decisions remain preserved:

- hits/misses
- slowly saturating confidence
- similar records may coexist
- SimilarityObserver
- Activation top-N
- DecisionSelector chooses
- Feedback strengthens only used record

This pass does not change runtime implementation.

## Chronicle / Letopis Relationship

Chronicle memory is history:

- what happened
- what was experienced
- what RNDeM previously believed
- when knowledge changed
- important autobiographical events

Chronicle history must not automatically become active AKBSM truth.

## Shared Working / Context Memory

Future working/context memory should contain temporary active pattern/context
material.

Future working/context memory should contain temporary active pattern/context material.

Temporary presence must not automatically convert into:

- AKBSM truth
- ExpSM rule
- permanent fact
- write approval

This is consistent with v1 temporary metadata safety boundaries.

## Labels And Naming

Human-readable names are optional metadata/debug/interface conveniences. They
must not define identity.

Example:

```text
debug_name="dog_pattern"
```

does not make the pattern semantically a dog.

Identity and meaning must emerge from internal associations and experience.
This preserves the current debug-name safety philosophy.

## Learning Principle

RNDeM learns consequences through subsequent experience, not by trusting
action-function return values as world truth.

The environment/sensory loop is authoritative evidence. This aligns with the
existing Actions/Consequences concept.

## Truth Pressure / Adaptive Knowledge Principle

The active world model may contain strong facts.

Strong facts are still revisable if repeated, reliable environmental experience
contradicts them.

The environment does not directly rewrite knowledge after one arbitrary
mismatch. Contradiction should accumulate through experience/evaluation
mechanisms.

Exact revision thresholds are deferred.

## Anti-GPT Constraints

RNDeM's core data architecture must not become:

```text
prompt
-> tokenization
-> model inference
-> response
```

or:

```text
labeled image
-> class prediction
```

or:

```text
audio
-> transcript
-> symbolic reasoning only
```

Those may someday exist as peripheral tools/translators, but they cannot define
the internal cognitive substrate.

## Compatibility With v1

The Natural Pattern Data Contract does not invalidate v1.

v1 remains the safe runtime/container baseline. This contract defines the kind
of data substrate that future post-v1 CLC development should introduce.

This pass does not enable:

- real ContextMemory placement
- AKBSM writes
- ExpSM writes beyond current policy
- direct `_run_tick()` hooks
- default diagnostics
- behavior influence
- sensor adapters
- text/image/audio file input APIs

## Deferred Design Questions

Deferred:

- exact ActivationPattern Python representation
- dense vs sparse patterns
- pattern dimensionality
- visual resolution
- audio representation
- similarity algorithm
- pattern compression
- pattern trace retention
- pattern consolidation
- pattern-to-entity threshold
- cross-modal binding algorithm
- AKBSM revision thresholds
- contradiction accumulation thresholds
- internal replay scheduling
- action pattern representation
- sensor hardware adapters
- camera implementation
- microphone implementation

## Recommended Next Step

The first implementation after explicit approval should be a minimal
modality-agnostic activation-pattern substrate, before real camera/microphone
integration.

The first implementation should be a minimal modality-agnostic activation-pattern substrate.

Suggested future components, design only:

- ActivationPattern
- PatternFrame
- PatternTrace
- PatternOrigin
- PatternModality
- PatternSimilarity
- PatternReactivation

Do not implement them in this pass.
