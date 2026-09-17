# Design: First Closed-Loop Action Consequence

## Status

Post-v1.2 isolated implementation complete.

The first mechanical action/consequence causal path is implemented under
`clc/actuation/` with external scenario/test support in
`scenarios/support/synthetic_closed_loop_visual_world.py`. It implements only
numeric `ACTION` + `ACTION_GENERATED` frame transduction into immutable
`ActuatorSignal` objects and an external synthetic world transition whose
consequence is observed only through a later `VisualFieldSnapshot` and existing
`VisualFieldTransducer`.

This document still does not modify `clc/patterns/`, does not modify
`clc/transduction/`, does not wire anything into normal runtime or
`_run_tick()`, and does not add autonomous action selection, semantic action
names, success/failure callbacks, reward, pain, persistence, ContextMemory
placement, AKBSM writes, ExpSM writes, chronicle writes, prediction, replay
scheduling, or cross-modal binding.

This design does not wire anything into normal runtime or `_run_tick()`.

## Relationship To Existing Architecture

The next isolated layer, `docs/design_nfp_context_and_short_memory.md`, assigns pending
before/action/after capture to existing ContextMemory infrastructure and completed
raw transitions to bounded Short Memory. It preserves the isolated v1.3.0 loop
and strict T -> T+1 external consequence rule. No separate ExperienceCapture
memory subsystem, semantic evaluation or permanent writer is introduced.
Its executable harness now uses the existing ActionTransducer, external world,
VisualFieldTransducer and sliding windows to complete Context pending state and
explicitly retain RecentCausalTransition in ShortMemory. The v1.3.0 loop itself
is unchanged, including equal-valued sensory consequences at a world boundary.

The current checkpoints separate three layers:

```text
v1.1.0:
NFP representation substrate

v1.2.0:
external world -> natural sensory NFP

next closed-loop layer:
ACTION NFP -> external world -> subsequent sensory NFP
```

The next closed-loop layer is the first mechanical action/consequence loop. It
is not learned behavior. It is not autonomous behavior. The internal/action
generation mechanism remains test-harness supplied for now.

In the first implementation, ACTION frames remain harness-generated. Actuation
is numeric and non-semantic, replayed `ACTION` frames cannot execute, the world
transition returns no semantic result, strict `T -> T+1` causality is enforced
by tick checks, and the same action values may produce different later sensory
activation in different hidden world states. No learning or normal runtime
wiring is added yet.

## Canonical Causal Model

The first closed-loop design uses this causal order:

```text
sensory NFP at tick T
        |
        v
internal/action-generation mechanism
        |
        v
ACTION NFPFrame at tick T
        |
        v
action transduction
        |
        v
actuator signal
        |
        v
world transition T -> T+1
        |
        v
sensor snapshot at T+1
        |
        v
VISUAL EXTERNAL_SENSORY NFPFrame at T+1
```

The internal/action-generation mechanism is not designed here. The test harness
supplies ACTION NFPFrames. This validates causal mechanics only. It does not
yet represent learned/selected behavior.

## Fundamental Consequence Rule

An action does not know its consequence.

An actuator does not report semantic consequence truth.

The environment changes.

The consequence becomes available only through subsequent sensory/internal
activation.

The consequence becomes available only through subsequent sensory/internal activation.

APIs equivalent to the following are forbidden:

```text
result = actuator.apply(...)
result.success
result.failed
result.moved_right
result.collision
result.blocked
result.reward
result.consequence
```

For the first implementation, applying an actuator signal should conceptually
return:

```text
None
```

or otherwise expose no semantic result to RNDeM. The test harness may inspect
hidden world state to verify mechanics. RNDeM may not.

## Action-Frame Timing

Use one `ACTION NFPFrame` as the causal action activation for one world
transition:

```text
ACTION frame at tick T
-> actuator signal for transition T -> T+1
-> world state at T+1
```

`NFPFrame` is the current motor activation. `NFPWindow` is temporal
history/dynamics of motor activation.

`NFPWindow` is temporal history/dynamics of motor activation.

An `ACTION NFPWindow` may later describe temporal motor activity/history, but
the first actuator boundary consumes one frame at a time. Do not interpret a
whole action window as one opaque semantic command.

Do not interpret a whole action window as one opaque semantic command.

Same numeric action values at different ticks are distinct frame occurrences:

```text
values equal
pattern occurrence different
active_tick different
```

## Action Origin

The first actuator accepts only:

```text
modality = ACTION
origin = ACTION_GENERATED
```

It must reject:

```text
VISUAL
AUDIO
INTERNAL
INTERNAL_REACTIVATION
EXTERNAL_SENSORY
```

as direct actuator commands.

Internal replay of an old action pattern must not automatically actuate the
world:

```text
remembering an action
!=
performing an action
```

Future cognition must explicitly generate an `ACTION` + `ACTION_GENERATED`
occurrence before actuation.

## Action Topology

The first synthetic motor interface should use a tiny fixed numeric topology:

```text
PatternTopology((2,))
```

The cognitive ACTION frame contains only:

```text
(channel_0_activation, channel_1_activation)
```

with normalized activation values:

```text
0.0 .. 1.0
```

Do not expose cognitive semantic fields such as:

```text
left
right
move_left
move_right
direction
distance
velocity
command
```

## Physical Wiring Model

Fixed body/actuator wiring is allowed.

For the first synthetic body:

```text
signed_drive = channel_1 - channel_0
```

Conceptually:

```text
signed_drive > 0 -> positive horizontal physical influence
signed_drive < 0 -> negative horizontal physical influence
signed_drive = 0 -> no horizontal influence
```

The exact first implementation may quantize non-zero drive to one cell per
transition. This wiring is not semantic knowledge supplied to RNDeM. It is
analogous to physical body wiring:

```text
motor activation
-> muscle/actuator force
```

RNDeM receives no declaration that channel 0 "means left" or channel 1 "means
right". It may only learn recurring sensory consequences of activating those
channels.

## ActionTransducer Boundary

The future RNDeM-side boundary is equivalent to:

```text
ActionTransducer.transduce(action_frame) -> ActuatorSignal
```

Recommended future location:

```text
clc/actuation/
    __init__.py
    motor.py
```

The transducer must:

- accept only `ACTION` + `ACTION_GENERATED` `NFPFrame`
- validate expected actuator topology
- copy numeric activation values
- preserve active tick
- create opaque signal identity/provenance

It must not add:

- movement name
- direction label
- expected consequence
- success prediction
- world coordinate
- semantic command

## ActuatorSignal

`ActuatorSignal` is an immutable numeric-only boundary object.

Conceptual fields:

```text
values: tuple[float, ...]
active_tick: int
signal_id: int
source_frame_ref: str
```

No semantic fields are allowed. Prohibit fields equivalent to:

```text
command
direction
target
movement
expected_result
success
failure
collision
reward
object
```

This mirrors the sensory side:

```text
world state
!= sensor snapshot
!= sensory NFP

action NFP
!= actuator signal
!= world state transition
```

## Opaque Action Provenance

As with sensory provenance, actuator provenance must identify occurrence rather
than meaning.

Actuator provenance must identify occurrence rather than meaning.

Acceptable conceptual forms:

```text
action_frame:000123
actuator_signal:000456
```

Avoid semantic forms:

```text
move_right
escape_wall
go_to_target
```

## First Closed-Loop Synthetic World

The first implementation should use a scenario/test-only world with hidden
physical state.

The scenario/test-only world has hidden physical state.

Do not put this environment inside cognition.

Recommended future support class:

```text
SyntheticClosedLoopVisualWorld
```

under:

```text
scenarios/support/
```

The world should contain a hidden controllable excitation/body location
rendered into the 16x16 visual scalar field.

Conceptually:

```text
hidden world state:
body_row
body_column

visible sensor field:
16x16 scalar field with localized activation representing physical state
```

The words "body", "position", and "horizontal" are test/world concepts. RNDeM
receives only the numeric visual field.

RNDeM receives only the numeric visual field.

## Initial Physical Dynamics

Keep the first dynamics minimal:

```text
vertical coordinate fixed
two actuator channels influence horizontal position
```

Example:

```text
drive = channel_1 - channel_0

if drive > threshold:
    physical column += 1

if drive < -threshold:
    physical column -= 1

otherwise:
    no change
```

Clamp physical position to valid world bounds. Exact threshold may be simple,
for example zero with deterministic sign.

Do not expose this interpretation through cognitive APIs.

## Boundary Behavior

At an interior position:

```text
same ACTION activation
-> world position changes
-> next visual NFP changes
```

At a boundary:

```text
same ACTION activation
-> physical clamp prevents position change
-> next visual NFP may remain unchanged
```

There must be no callback to RNDeM such as:

```text
blocked=True
success=False
collision=True
```

This proves:

```text
action consequence depends on world state,
not on semantic truth encoded in the action.
```

## Same Action, Different Consequences

This is a required scenario.

Example:

```text
World state A:
controllable excitation at interior position

Action frame X:
same numeric ACTION activation

Result:
next visual field differs from previous field
```

Then:

```text
World state B:
controllable excitation already at boundary

Action frame X:
identical ACTION activation

Result:
next visual field may remain unchanged
```

RNDeM-facing action representation is identical. Observed consequence differs
because environmental context differs.

Strong causal-integrity test:

```text
ACTION frame X:
values = identical in both trials

Trial A:
world state = interior

Trial B:
world state = boundary

Result:
ActuatorSignal is equivalent numerically,
but subsequent sensory NFP differs by environmental context.

No result flag is supplied.
```

This demonstrates:

```text
action does not contain consequence truth.
```

## World Transition API

Design an external-world method equivalent to:

```text
world.apply_actuator_signal(signal)
```

It should mutate external world state. It must not return semantic result
information.

It must not return semantic result information.

Recommended:

```text
-> None
```

The world may internally validate tick ordering, signal shape, and numeric
values, but may not send interpretation back to cognition.

## Tick Semantics

Use strict causal order:

```text
tick T:
    sensory state already exists
    ACTION frame generated for T
    action transduced
    actuator signal applied

transition:
    world T -> T+1

tick T+1:
    new sensor snapshot
    new EXTERNAL_SENSORY VISUAL NFPFrame
```

Do not allow consequence sensory data to claim tick T if it is caused by an
action at T.

This gives explicit temporal causality:

```text
action(T)
precedes
consequence_observation(T+1)
```

Do not require wall-clock timing.

## Harness-Generated Action For Now

The first closed-loop scenario must not pretend RNDeM already selects actions
autonomously.

Document explicitly:

```text
The test harness supplies ACTION NFPFrames.

This validates causal mechanics only.

It does not yet represent learned/selected behavior.
```

Future work will replace the harness action source with internal action
generation/selection.

Future work will replace the harness action source with internal action generation/selection.

## No Semantic Command Helper In Cognition

Do not create cognition-side APIs like:

```text
move_left()
move_right()
stand_still()
```

Scenario/test helpers may create numeric action frames for readability, but
those helpers must remain outside RNDeM cognitive code and must not attach
semantic metadata to the frame.

Scenario/test helpers must not attach semantic metadata to the frame.

Prefer tests directly constructing numeric activation tuples.

## Sensory Consequence Path

After world transition:

```text
SyntheticClosedLoopVisualWorld
-> VisualFieldSnapshot
-> existing VisualFieldTransducer
-> VISUAL EXTERNAL_SENSORY NFPFrame
```

Use the existing transduction concepts. Do not invent a semantic consequence
object between world and sensory input.

The consequence is the subsequent sensory state.

## No Direct Action-To-Sensory Shortcut

Explicitly prohibit:

```text
ActionTransducer
-> directly constructs VISUAL consequence frame
```

The path must go through the external world:

```text
ACTION NFP
-> actuator
-> world
-> sensor snapshot
-> sensory transduction
-> VISUAL NFP
```

This causal separation is mandatory.

## No Direct Experience Write

Closed-loop mechanics must not yet automatically create:

```text
ExpSM record
AKBSM relation
chronicle entry
reward update
confidence update
```

Those are later learning/evaluation layers. This pass defines physical
causality only.

This pass defines physical causality only.

## Proposed Future Implementation Components

Design only:

```text
clc/actuation/
    ActionTransducer
    ActuatorSignal

scenarios/support/
    SyntheticClosedLoopVisualWorld
```

Reuse:

```text
NFPFrame
VisualFieldSnapshot
VisualFieldTransducer
```

Do not duplicate sensory substrate.

## Required Future Implementation Scenarios

The first implementation must cover:

- ACTION + ACTION_GENERATED frame accepted by ActionTransducer
- non-ACTION modality rejected
- ACTION + INTERNAL_REACTIVATION rejected
- wrong action topology rejected
- action values copied into immutable ActuatorSignal
- actuator signal carries active tick
- actuator provenance is opaque
- actuator signal has no semantic command/result fields
- world accepts numeric actuator signal
- world transition returns no semantic outcome
- positive antagonistic drive changes hidden physical position when possible
- negative antagonistic drive changes hidden physical position when possible
- balanced action produces no physical movement
- same ACTION values at different ticks are distinct occurrences
- action at tick T affects sensory observation at T+1
- next snapshot produces VISUAL EXTERNAL_SENSORY NFPFrame
- interior action produces changed visual activation
- same action at boundary may produce unchanged visual activation
- same action + different world state produces different sensory consequence
- no success/failure/collision callback exists
- hidden world position does not enter NFP provenance
- action meaning labels do not enter ActuatorSignal
- no direct action->VISUAL NFP shortcut
- no AKBSM writes
- no ExpSM writes
- no chronicle writes
- no ContextMemory placement
- no _run_tick integration

## Replay-Safety Rule

The real actuator boundary must reject:

```text
ACTION modality + INTERNAL_REACTIVATION
```

Remembering/replaying an action must not physically execute it. Future
cognition must explicitly turn internal processing into a new:

```text
ACTION + ACTION_GENERATED
```

occurrence before world actuation.

## Deferred Scope

Deferred:

- autonomous action selection
- DecisionSelector integration
- `_run_tick()` integration
- ExpSM learning
- AKBSM learning
- credit assignment
- reward
- pain
- collision sensing
- proprioception
- internal-state sensing
- multi-axis movement
- continuous physics
- acceleration
- velocity memory
- action prediction
- planning
- goal systems
- motor learning
- action-window execution
- camera/microphone hardware
- real physical actuators

## Safety Boundary

This design pass is documentation and verifier only. It does not implement
actuation, does not modify `clc/patterns/`, does not modify `clc/transduction/`,
does not create `clc/actuation/`, does not modify `_run_tick()`, does not wire
anything into normal runtime, does not modify Memory, and does not create or
modify `semantic_core.json` or `technical_feedback_patterns.json`.
