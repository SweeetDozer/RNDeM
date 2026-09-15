# Design: Minimal Activation Pattern Substrate

## Status

Post-v1 architecture/design document with isolated implementation complete.

The minimal runtime-independent substrate is implemented in `clc/patterns/`.
It remains in-memory only and isolated from normal CLC runtime behavior. This
document still does not approve `_run_tick()` wiring, pattern persistence,
sensor adapters, semantic recognition, text/token semantic input, AKBSM writes,
ExpSM writes, real ContextMemory placement, pattern replay scheduling, or
cross-modal binding.

The Natural Pattern Data Contract defines what RNDeM considers fundamental
data. This design defines the first concrete internal representation boundary
for that data and does not weaken the Natural Pattern Data Contract.

The Natural Pattern Data Contract defines what RNDeM considers fundamental data.

## Design Goal

Define a minimal implementation-ready substrate for:

- NFPFrame
- NFPWindow
- NFPSequence
- PatternOrigin
- PatternModality
- PatternTopology
- NFPFrameSimilarity
- NFPWindowSimilarity
- NFPReactivation

The implementation is isolated and scenario/test driven. It is not wired into
normal runtime or `_run_tick()`.

## Fundamental Temporal Hierarchy

The natural-pattern substrate uses:

```text
NFPFrame
-> NFPWindow
-> NFPSequence
```

This hierarchy is fundamental.

`NFPFrame` is one modality-specific activation state at one active tick.

`NFPWindow` is a short ordered temporal group of compatible `NFPFrame` objects.

`NFPSequence` is a longer ordered temporal structure composed from
`NFPWindow` objects.

A frame represents instantaneous activation. A window represents local temporal
dynamics. A sequence represents longer temporal behavior or process.

A window represents local temporal dynamics.

Do not collapse `NFPWindow` and `NFPSequence` into one generic trace
abstraction.

## Common Envelope

Use a common pattern envelope with modality-specific topology.

Do not force all modalities to share the same geometric shape.

Conceptually:

```text
NFPFrame
|-- frame_id
|-- modality
|-- origin
|-- topology
|-- activation values
|-- active_tick
`-- provenance
```

The common abstraction is the activation-pattern contract. The topology/shape
belongs to the modality.

The topology/shape belongs to the modality.

Examples:

- visual -> spatial field topology
- audio -> frequency-channel frame topology, with temporal structure in window
- internal -> distributed state/channel topology
- pain/damage -> internal channel topology
- reward -> internal evaluative channel topology
- action -> action/motor channel topology

These are examples, not permanent hardware representations.

The initial implementation uses small/simple topologies while preserving the
intended long-term structure. Resolution is adjustable; the Frame -> Window ->
Sequence hierarchy is not.

## PatternModality

Minimum modalities:

- VISUAL
- AUDIO
- INTERNAL
- PAIN_DAMAGE
- REWARD_SUCCESS
- ACTION

Memory/reactivation is not itself a sensory modality.

A reactivated visual frame remains VISUAL. A reactivated audio frame remains
AUDIO. Its origin changes; its modality does not.

Modality expresses what kind of activation it is.

## PatternOrigin

Minimum origins:

- EXTERNAL_SENSORY
- INTERNAL_STATE
- INTERNAL_REACTIVATION
- ACTION_GENERATED

Origin expresses how the current activation entered the substrate.

Do not conflate modality and origin.

## Critical Provenance Rule

An internally reactivated pattern is not new environmental evidence.

Internal replay may participate in reasoning, associations, expectations, and
action preparation. It may be compared to current external sensory frames.

But INTERNAL_REACTIVATION must not by itself count as fresh external
confirmation of an AKBSM relation.

INTERNAL_REACTIVATION must not by itself count as fresh external confirmation.

Repeated self-replay must not allow RNDeM to strengthen a belief merely by
remembering it repeatedly.

Internal reactivation alone must not generate a new environmental consequence
record.

Future AKBSM/ExpSM evaluation must preserve provenance.

## NFPFrame

`NFPFrame` is an immutable or effectively immutable occurrence-level activation
snapshot.

Required fields:

- frame_id
- modality
- origin
- topology
- values
- active_tick
- provenance_ref optional
- debug_name optional

Do not require a human-readable semantic name.

Optional debug metadata may exist separately. Frame identity must not be
derived from a debug label.

One `NFPFrame` represents one modality/domain occurrence at one active tick.

Do not create multimodal `NFPFrame` payloads. Cross-modal binding belongs to a
future episode/context/association layer.

Cross-modal binding belongs to a future episode/context/association layer.

## PatternMoment

`PatternMoment` is an optional multimodal same-tick grouping helper for
distinct modality-specific `NFPFrame` objects at the same active tick.

It may contain visual, audio, internal, pain/damage, reward/success, and action
frames simultaneously.

`PatternMoment` is not an `NFPFrame`. It is not semantic interpretation and it
does not itself mean "event".

## Values

The first implementation uses simple normalized numeric activation values in
the range:

```text
0.0 .. 1.0
```

Do not add symbolic meaning to individual values.

## PatternTopology

`PatternTopology` is a lightweight descriptor of how activation values are
arranged. It describes structure without defining semantic meaning.

Conceptual examples:

```text
shape=(16,16)         # visual frame field
shape=(8,)            # audio frequency-channel frame
shape=(12,)           # internal channels
shape=(6,)            # action channels
```

Do not interpret shape dimensions as semantic labels.

Do not commit to final visual resolution. Do not commit to final audio
representation. Audio temporal structure belongs in `NFPWindow`.

## NFPWindow

`NFPWindow` is a short ordered temporal group of compatible `NFPFrame` objects.

Required invariants:

- window_id is non-empty
- at least one frame
- all frames share modality
- all frames share compatible/equal topology
- frame active_ticks strictly increase
- duplicate frame IDs are rejected

Derived properties:

- modality
- topology
- start_tick
- end_tick
- length

A single frame can express spatial/state activation. A window can express local
dynamics.

Example visual movement:

```text
tick 10: activation at x=1
tick 11: activation at x=2
tick 12: activation at x=3
```

The movement exists in the window, not in any one frame.

Example audio:

```text
tick 20: frequency activation A
tick 21: frequency activation B
tick 22: frequency activation C
```

The local sound structure exists across the window.

## NFPSequence

`NFPSequence` is a longer ordered temporal structure made from `NFPWindow`
objects.

Required invariants:

- sequence_id is non-empty
- at least one window
- windows share modality
- windows use compatible/equal topology
- windows are ordered by temporal position

Do not overdesign overlap rules yet. If windows overlap in time, preserve their
ordering and leave detailed overlap policy deferred.

Derived properties:

- modality
- topology
- start_tick
- end_tick
- window_count

A sequence is substrate material. It is not automatically an entity, event,
AKBSM truth, ExpSM experience, or chronicle fact.

## Active Time

Use RNDeM active-time/tick semantics where practical.

`active_tick` is the primary temporal coordinate of the pattern substrate.

active_tick is the primary temporal coordinate.

Do not make wall-clock time fundamental to pattern identity.

Do not implement Heart integration in this pass.

## Similarity

Similarity is a measurement boundary, not semantic identity.

Frame similarity measures instantaneous activation resemblance.

Window similarity measures short temporal-pattern resemblance.

They are not interchangeable.

### NFPFrameSimilarity

Frame similarity uses:

```text
1.0 - mean(abs(left_i - right_i))
```

Only same modality and compatible/equal topology frames are comparable.

Different modality or topology returns non-comparable with no score.

### NFPWindowSimilarity

Window similarity is deterministic and minimal.

Only same modality, compatible/equal topology, same frame count windows are
comparable.

The first implementation computes:

```text
mean(aligned frame similarity scores)
```

Do not implement dynamic time warping, learned embedding, temporal alignment,
neural similarity, or sequence similarity yet.

Raw cross-modal similarity is rejected. Cross-modal relationships belong to
learned association/binding layers.

Cross-modal relationships belong to learned association/binding layers.

## NFPReactivation

`NFPReactivation.reactivate_frame()` creates a new frame occurrence that refers
to a previously experienced frame while preserving modality and changing
origin/provenance.

Required behavior:

- new frame identity
- new active_tick
- same modality
- same topology
- same values
- origin = INTERNAL_REACTIVATION
- provenance_ref = source frame ID

The source frame remains immutable.

Window/sequence replay scheduling is not implemented. The model allows future
replay to reconstruct a temporal series of internally reactivated `NFPFrame`
objects, but scheduler and timing policy are deferred.

## External Vs Internal Equality

Two frames may have identical activation values while representing different
epistemic situations.

Example:

```text
NFPFrame A:
modality = VISUAL
origin = EXTERNAL_SENSORY

NFPFrame B:
modality = VISUAL
origin = INTERNAL_REACTIVATION
```

Their values may be identical. They are not equivalent as evidence.

## Action Patterns

ACTION is a normal activation modality/domain in the substrate.

ACTION frames and ACTION windows may describe motor/action-channel dynamics.

An action frame/window:

- does not contain its own consequence
- does not declare whether it succeeded
- does not directly write ExpSM

Consequences arrive later through sensory/internal frames.

Consequences arrive later through sensory/internal patterns.

## Pain / Reward / Internal Patterns

PAIN_DAMAGE and REWARD_SUCCESS are ordinary activation modalities/domains.

They are not magic scalar truth injected directly into AKBSM, and they do not
directly authorize memory writes.

## Pattern Identity

Distinguish:

- occurrence identity
- frame similarity
- window similarity
- stable learned entity identity

An `NFPFrame.frame_id` identifies the frame occurrence/object.

It does not mean that two different occurrences with similar values are already
the same learned entity.

Stable entities are future AKBSM/pattern-abstraction work.

## Debug Labels

Optional debug labels are non-semantic metadata only.

```text
debug_name="dog"
```

does not mean the frame is a dog.

No runtime logic may branch on debug labels.

## No Persistence Yet

The minimal substrate remains in-memory only.

Do not define:

- disk persistence
- AKBSM writes
- ExpSM writes
- ContextMemory placement
- long-term sequence storage

## No _run_tick Wiring Yet

This substrate is isolated.

Do not wire it into `_run_tick()` unless a later explicit integration pass
approves it.

Initial validation uses isolated/scenario/test harnesses.

## Natural Data Flow

The substrate reinforces:

```text
world
-> transduction
-> NFPFrames
-> NFPWindows
-> NFPSequences
-> later associations/experience/action
```

It does not implement:

```text
image file -> semantic image object
audio file -> transcript
text -> token meaning
```

## Implemented Isolated Scenario Coverage

`scenarios/minimal_activation_pattern_substrate.json` and
`tools/verify_minimal_activation_pattern_substrate.py` cover:

- create VISUAL external NFPFrame
- create AUDIO external NFPFrame
- create INTERNAL frame
- create ACTION frame
- NFPFrame validation
- NFPWindow accepts ordered same-modality compatible frames
- NFPWindow rejects mixed modalities
- NFPWindow rejects incompatible topology
- NFPWindow rejects duplicate frame IDs
- NFPWindow rejects unordered ticks
- NFPWindow exposes modality/topology/start/end/length
- NFPSequence accepts ordered compatible windows
- NFPSequence rejects mixed modality
- NFPSequence rejects incompatible topology
- NFPSequence exposes start/end/window_count
- frame similarity identical = 1.0
- frame similarity differing activation = [0,1]
- cross-modal frame comparison non-comparable
- topology mismatch non-comparable
- identical windows = 1.0
- different compatible windows produce deterministic score
- different window lengths non-comparable
- reactivation creates a new NFPFrame
- reactivation preserves modality/topology/values
- reactivation origin becomes INTERNAL_REACTIVATION
- external and internally replayed identical values remain epistemically distinct
- debug_name does not affect similarity
- no AKBSM writes
- no ExpSM writes
- no ContextMemory writes
- no `_run_tick()` integration

## Deferred Questions

Deferred:

- camera transduction
- microphone transduction
- exact audio representation
- visual resolution
- sparse representation
- compression
- long-term sequence retention
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

This implementation does not create or modify:

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

Do not tag or merge from this implementation pass.
