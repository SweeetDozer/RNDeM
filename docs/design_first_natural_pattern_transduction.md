# Design: First Natural Pattern Transduction

## Status

Proposed post-v1.1 design.

This document is docs/verifier only. It does not implement a transduction
layer, does not modify `clc/patterns/`, does not wire anything into normal
runtime or `_run_tick()`, and does not add camera/microphone support, OpenCV,
semantic recognition, text/token input, persistence, ContextMemory placement,
AKBSM writes, ExpSM writes, cross-modal binding, prediction, or replay
scheduling.

This document does not implement a transduction layer.

This document does not wire anything into normal runtime or `_run_tick()`.

## Relationship To Existing Architecture

Natural Pattern Data Contract defines what fundamental data is.

NFP substrate `v1.1.0` defines Frame/Window/Sequence representation:

```text
NFPFrame
-> NFPWindow
-> NFPSequence
```

First Natural Pattern Transduction defines how an external world first creates
genuine `EXTERNAL_SENSORY` `NFPFrame` objects.

The first source design is intentionally small:

```text
environment
-> sensor-accessible physical field
-> transduction
-> VISUAL NFPFrame
-> NFPWindow
```

It is not a recognition system.

## Natural Relative To RNDeM

The synthetic world is engineered by us, but its sensory data can still be
natural from RNDeM's perspective.

Natural here means:

```text
RNDeM receives only the sensory activation caused by the environment.

RNDeM does not receive the human semantic description of what caused it.
```

The environment/harness may internally know how a stimulus is generated, but
the RNDeM-facing transducer must not expose:

- object type
- class ID
- "dot"
- "moving object"
- "moves right"
- trajectory label
- semantic name
- ground-truth category
- human interpretation

The cognitive substrate receives only activation.

## First Synthetic Environment

The first source should be a minimal visual scalar-field environment.

Recommended initial size:

```text
16 x 16
```

This is intentionally tiny. Resolution is adjustable later.

The important permanent structure is:

```text
spatial field
-> NFPFrame
-> temporal NFPWindow
```

The field contains normalized physical/simulated intensity values:

```text
0.0 .. 1.0
```

Conceptually:

```text
SyntheticVisualField
shape = (16,16)
values = numeric field only
```

Do not attach semantic meaning to coordinates or values.

## Environment Vs Sensory Boundary

The design separates:

```text
world state
```

from:

```text
agent sensory state
```

RNDeM must not receive direct access to the environment object's internal
state.

The environment may contain harness-only state necessary to evolve the field.
The transducer sees only a sensor-readable field/snapshot.

Conceptually:

```text
Synthetic world
      |
      v
numeric visual field snapshot
      |
      v
VisualFieldTransducer
      |
      v
NFPFrame
```

Do not design:

```text
Synthetic world
-> object list
-> semantic object data
-> RNDeM
```

## Hidden Environment Truth

It is acceptable for the test harness to know things RNDeM does not.

For example, the harness may know that an excitation follows coordinates:

```text
(2,4)
(3,4)
(4,4)
(5,4)
```

That trajectory is ground truth for testing only.

RNDeM must not receive:

- direction="right"
- velocity
- object_name
- class="moving_dot"

as cognitive input.

The only sensory consequence is the changing visual field.

## First Stimulus Model

Use the simplest possible changing field.

Example concept:

```text
background intensity = 0.0
one localized excitation = 1.0
```

Across active ticks:

```text
tick 10 -> excitation at one spatial position
tick 11 -> excitation at another spatial position
tick 12 -> excitation at another spatial position
```

This results in multiple VISUAL `NFPFrame` objects.

Do not call this object a semantic entity inside the RNDeM-facing API. Terms
such as "moving point" may be used only in documentation/testing explanation.

## Sensor Snapshot

Define a minimal intermediate sensor snapshot boundary.

It should contain only:

- shape
- numeric field values
- sensor tick / active tick
- opaque source identity if necessary

No semantic labels.

The snapshot is not yet an NFP. It represents what the transducer can sense.

This distinction remains explicit:

```text
environment state
!=
sensor snapshot
!=
NFPFrame
```

## Visual Transduction

Design a deterministic label-free visual transducer.

Conceptually:

```text
VisualFieldTransducer.transduce(snapshot, *, frame_id) -> NFPFrame
```

For the first implementation, transduction may intentionally be simple.

Recommended mapping:

```text
snapshot shape
-> PatternTopology(shape)

snapshot numeric values
-> NFPFrame.values
```

Use deterministic row-major flattening.

The resulting `NFPFrame` must have:

- modality = VISUAL
- origin = EXTERNAL_SENSORY
- active_tick = snapshot active tick
- topology = snapshot shape
- values = copied activation values

The transducer creates a new immutable NFP occurrence. It must not alias
mutable environment storage into the frame.

The transducer must not alias mutable environment storage.

## Why Simple Transduction Is Acceptable Initially

The first transducer is not intended to model a biological retina.

Its purpose is to establish the architectural boundary:

```text
world physics/state
-> sensory measurement
-> neural-style activation representation
```

Later transduction may introduce receptive fields, sensor noise, contrast
processing, different channel arrangements, downsampling, or retina-like local
preprocessing without changing the fundamental NFP Frame/Window architecture.

retina-like local preprocessing is deferred.

Do not implement or design those deeply now.

## No Semantic Preprocessing

The first transducer must not perform:

- classification
- segmentation into named objects
- object identity extraction
- OCR
- feature labels
- direction labels
- motion labels
- human-readable interpretation

The transducer converts physical/simulated sensor values into activation
values. It does not explain them.

## Label Leakage Rule

Human/debug metadata that does not change the sensory field must not change the
produced NFP activation.

If two test harness states have identical numeric visual fields but one is
internally/debug-described as:

```text
stimulus A
```

and another as:

```text
stimulus B
```

then their transduced activation values must be identical.

Semantic/debug names must not affect:

- topology
- activation values
- modality
- similarity

Occurrence identity and tick may naturally differ.

Strong anti-leakage test concept:

```text
World/Harness A:
hidden debug description = "moves right"

World/Harness B:
hidden debug description = "banana"

visible sensor field = identical

Result:
transduced NFP topology/values must be identical
```

The purpose is to mechanically prove that semantic metadata is not part of
transduction.

## Provenance Rule

Provenance may identify the sensory occurrence/source boundary, but must not
smuggle semantic truth into the cognitive substrate.

Provenance must not smuggle semantic truth.

Prefer opaque provenance such as:

```text
sensor_snapshot:000123
```

rather than:

```text
dog_at_x5_y3
moving_point_right
red_ball
```

Human-readable test/debug metadata must remain outside cognitive pattern
identity.

## Active Time

Use existing RNDeM active-tick semantics.

The synthetic environment is stepped explicitly:

```text
world.step(active_tick)
```

or an equivalent API.

The resulting sensor snapshot and `NFPFrame` preserve that active tick.

Do not make wall-clock time fundamental.

## Window Assembly

Design a small non-semantic window assembler after transduction.

Conceptually:

```text
NFPFrame
NFPFrame
NFPFrame
...
    |
    v
NFPWindowAssembler
    |
    v
NFPWindow
```

The assembler does not perform recognition. It only groups ordered compatible
frames.

The assembler groups ordered compatible frames.

Recommended initial behavior:

- window_size configurable
- same modality required
- same topology required
- strictly increasing active ticks

A sliding window with stride 1 is acceptable for the first implementation.

Do not require contiguous tick numbers unless necessary.

Do not add semantic event boundaries.

Important distinction:

```text
VisualFieldTransducer:
physical/simulated sensor state -> activation frame

NFPWindowAssembler:
ordered frames -> temporal activation window
```

Neither performs recognition.

## Why Window Matters Immediately

At three ticks:

```text
tick 1:
activation concentrated at spatial position A

tick 2:
activation concentrated at spatial position B

tick 3:
activation concentrated at spatial position C
```

No individual frame contains "motion".

The temporal change exists in:

```text
NFPWindow(frame1, frame2, frame3)
```

Future recognition/prediction systems may discover recurring temporal
relations.

The source/transduction layer must not write motion, direction, object, or
velocity into the window.

The source/transduction layer must not write motion, direction, object, or velocity.

## NFPSequence

Do not require the first source implementation to create long `NFPSequence`
objects automatically.

The existing substrate already supports sequences.

For this design:

```text
environment
-> NFPFrame
-> NFPWindow
```

is sufficient.

Sequence construction may come later or be exercised only as substrate
compatibility.

Do not add sequence semantics.

## No Direct Memory Authority

Neither the environment, sensor snapshot, transducer, nor window assembler may:

- write AKBSM
- write ExpSM
- write chronicle
- place real ContextMemory
- change confidence
- assert facts
- create learned entities

They produce transient natural-pattern substrate material only.

## No Runtime Wiring

The first implementation must remain isolated.

Do not connect it to:

- CLCRuntime
- `_run_tick()`
- DecisionSelector
- ActionProposer
- ActionScoring
- ModeActionGuard
- PolicyPressureReview
- memory writers

Initial tests/scenarios operate through a standalone harness.

## Suggested Future Implementation Location

Design only.

Recommended:

```text
clc/transduction/
    __init__.py
    visual.py
    windowing.py
```

Keep the synthetic environment outside the cognitive substrate.

Preferred location:

```text
scenarios/support/synthetic_visual_world.py
```

or an equivalent test/scenario-support location.

Reason:

```text
the synthetic world is an external test environment,
not part of RNDeM cognition.
```

Do not implement these files in this pass.

## Proposed Future Types

The minimal future implementation should use concepts equivalent to:

- VisualFieldSnapshot
- VisualFieldTransducer
- NFPWindowAssembler
- SyntheticVisualWorld

Exact names may be adjusted to project conventions.

## First Implementation Scenario Coverage

The next implementation pass should cover:

- static 16x16 field produces VISUAL EXTERNAL_SENSORY NFPFrame
- frame topology matches field shape
- frame activation values correspond deterministically to field values
- transduction copies data rather than aliasing mutable world storage
- frame active_tick matches sensor/world tick
- provenance is opaque/non-semantic
- different ticks produce distinct frame occurrence IDs
- same physical field at different ticks may produce equal activation values
- different hidden/debug labels with identical physical field produce identical activation values
- changing one field cell changes only the corresponding activation position under the initial direct transduction mapping
- moving localized excitation produces an ordered series of NFPFrames
- window assembler creates ordered NFPWindow
- window contains no semantic motion/direction label
- static field produces temporally repeated activation pattern
- moving field produces temporal variation visible only through frame sequence/window
- debug names do not affect NFP values
- no AKBSM writes
- no ExpSM writes
- no ContextMemory placement
- no runtime wiring

## Environment Authority

The sensor/transducer observes the environment.

It does not ask the environment what the stimulus "means".

Future consequences must similarly come through changed sensory/internal state
rather than semantic callback results.

This preserves:

```text
action
-> environment changes
-> sensor state changes
-> NFP changes
```

## Deferred Scope

Deferred:

- camera hardware
- microphone hardware
- OpenCV
- real image files as cognitive input
- audio files as semantic input
- retina simulation
- multi-channel color vision
- sensor noise
- receptive fields
- attention/foveation
- sensor movement
- agent body position
- occlusion
- depth
- object segmentation
- semantic recognition
- stable entity formation
- cross-modal binding
- audio transduction
- action-to-world integration
- prediction
- replay scheduling
- AKBSM mapping
- ExpSM serialization
- ContextMemory placement
- `_run_tick()` integration

## Safety Boundary

This design does not implement the transduction layer. It does not add files
under `clc/transduction/` or `scenarios/support/`. It changes no Memory files
and does not create `semantic_core.json` or `technical_feedback_patterns.json`.

This design does not add files under `clc/transduction/`.

Do not tag or merge from this design pass.
