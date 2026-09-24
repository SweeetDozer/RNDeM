# Design: Remembered NFP Action Materialization And Guarded Execution

## Status And Scope

This design-only pass starts from `v1.8.0` (`f7bbf5e`). It defines the first
isolated boundary after `SelectedNFPExpSMExperience`; it implements no executor,
scenario, Feedback, memory mutation, automatic retrieval-to-execution, or
`_run_tick()` wiring.

| Checkpoint | Boundary |
| --- | --- |
| v1.7.0 | policy-gated persistent experience creation |
| v1.8.0 | persistent experience retrieval and competition |
| Next | fresh materialization plus guarded execution of remembered ACTION structure |

## Current Action-Path Audit

`SelectedNFPExpSMExperience` is immutable selected data: transient selection,
activation and candidate IDs; exact persistent `source_experience_id`;
`SerializedNFPActionV1`; `SerializedObservedEffectV1`; and scores. It has no
tick binding and no execute/act/world method. `DecisionSelector.select_native()`
only selects. remembered ACTION structure != historical ACTION occurrence !=
new current ACTION occurrence.

`SerializedNFPActionV1` validates ACTION modality, positive topology, finite
unit values and matching size, but intentionally stores no historical frame ID,
tick, origin or provenance. `NFPFrame` requires a caller-supplied ID and tick.
There is no global occurrence allocator: producers use explicit harness IDs or
`IdGenerator.next(prefix)`. The future isolated coordinator owns an injected
generator and supplies `next("remembered_action_frame")`; this is a local
occurrence ID, never a persistent record ID.

## Actual ModeActionGuard Audit

`ModeActionGuard` currently accepts `is_allowed(action_pattern_id: str,
system_state, tick)` or `adjust_candidate(ActionCandidate, system_state, tick)`.
It guards registered semantic pattern IDs by mode and can suppress confidence
and urgency. It accepts no `NFPFrame`, structural action, selected experience,
or materialized intent. A legacy adapter would have to invent pattern ID,
urgency, risk and cost.

Choose **a typed extension of the existing guard architecture**, such as
`is_native_action_allowed(intent, system_state, tick)`, returning allow/deny
plus an audit reason. It evaluates the current materialized intent, mode and
tick; it does not score, reshape, mutate, retrieve, or affect Activation. A
fake `ActionCandidate` adapter and guard bypass are forbidden.

## Actual ActionTransducer Audit

`ActionTransducer.transduce()` accepts exactly `NFPFrame` and requires ACTION,
ACTION_GENERATED and `PatternTopology((2,))`. The frame already guarantees
finite `[0,1]` values. It emits only immutable `ActuatorSignal(values,
active_tick, signal_id, source_frame_ref)` with an opaque hash of fresh frame
identity. It cannot accept serialized action, record, selection, prediction or
source record ID.

`SyntheticClosedLoopVisualWorld.apply_actuator_signal()` requires signal tick
equal to `world.current_tick`, mutates physical state, increments time, and
returns `None`. Returning normally is the current acceptance/external-execution
boundary. Selection, materialization, guard approval and transduction are not
external execution.

## Actual ContextMemory Causality Audit

`ContextMemoryManager.observe_action_frame()` requires a current external
VISUAL window ending at action tick, rejects a second pending relation, and
opens `PendingCausalTransition` for exactly T+1. A qualifying T+1 call to
`observe_external_sensory_window()` creates `RecentCausalTransition`; late
evidence clears without completing. `expire_pending_if_overdue()` clears after
T+1. There is no explicit abort/clear API.

The older isolated harness opens pending before world application, assuming
validated calls succeed. That is not a general failure protocol. Remembered
execution preflights current window, absent pending state, and equal manager,
selection, action and world ticks; it calls the world first and opens pending
only after normal return confirms external execution. Thus denied, rejected,
or non-executed actions never open pending. If post-world pending registration
still fails, report the action as executed and never reapply it; the current API
has no transactional world handshake.

## Selection Freshness Contract

An ephemeral `SelectedNFPExecutionRequest` wraps the selected result plus
`selection_context_end_tick`, copied from its live query window. This is not
persistent ExpSM data. The first invariant is:

```text
selection_context_end_tick
== current ContextMemory external window end_tick
== requested action active_tick
== external world current_tick
```

Runtime/harness owns current time; memory supplies values, not when. Mismatch
returns `STALE_SELECTION`: no action materialization for execution, guard,
transducer, world mutation, pending transition, or automatic re-retrieval.

## Materialization Model

Pure `NFPActionOccurrenceMaterializer` accepts a fresh request, current tick and
caller-owned fresh ID. It revalidates persistent structure and returns
`MaterializedNFPActionIntent` containing a fresh NFPFrame with ACTION,
ACTION_GENERATED, selected topology/values and current tick, plus exact
`source_experience_id`, selection/activation provenance, predicted effect and
selection tick.

The frame ID is not derived from `source_experience_id` or historical identity.
Repeated use of one record has equal values/source ID but fresh IDs and later
ticks. Equal ACTIONs from distinct records retain distinct source IDs and
predictions. ACTION_GENERATED means a new motor occurrence, not
INTERNAL_REACTIVATION.

`NFPFrame.provenance_ref` is not reused for the persistent record link: its
semantics are occurrence lineage, while ExpSM ID is another identity domain.
The typed envelope carries the source ID and leaves frame provenance unset
until a separate NFP provenance convention is reviewed.

## Persistent Validation And Actuator Compatibility

Materialization reuses `SerializedNFPActionV1`/`NFPFrame` validation: ACTION,
valid topology, finite unit values and matching count. Current actuator
compatibility separately requires exact `(2,)`. Otherwise return
`ACTUATOR_INCOMPATIBLE` before guard/transduction. Values are never resized,
truncated, padded, remapped, or translated into semantic commands.

## Guarded Execution Ordering

```text
selection + tick binding
-> freshness and Context/world preflight
-> fresh ACTION occurrence
-> actuator compatibility
-> typed ModeActionGuard allow/deny
-> ActionTransducer
-> external world apply/accept
-> ContextMemory.observe_action_frame
-> world snapshot at T+1
-> VisualFieldTransducer / NFPWindowAssembler
-> ContextMemory.observe_external_sensory_window
-> RecentCausalTransition
-> ShortMemory.remember
```

`GUARD_DENIED` means no transducer, signal, world mutation, pending transition,
or attributed consequence. It is control-plane denial, not bad experience or
miss. Guard is allow/deny and cannot alter action values. Transducer rejection
returns `TRANSDUCTION_REJECTED`, with no world or pending call. World rejection
is `WORLD_EXECUTION_FAILED`; the first synthetic harness relies on its
validation-before-mutation behavior. Partial-failure worlds need a later
execution-receipt protocol.

## Observation And Pending Semantics

After normal world return, the action is executed and pending records that
fresh occurrence against the preflighted before window. Next state comes only
from world snapshot -> `VisualFieldTransducer` -> qualifying EXTERNAL_SENSORY
window. Strict ACTION T -> observation T+1 remains. Reuse
`PendingCausalTransition -> RecentCausalTransition` and explicit
`ShortMemory.remember`; create no second causal format.

After execution, snapshot/transduction/assembly failure returns
`ACTION_EXECUTED_OBSERVATION_PENDING` (or a specific observation-failed detail)
and preserves unresolved pending causality. Do not pretend execution did not
happen, clear automatically, reapply the signal, or fabricate after-state.
Exact-T+1 delayed evidence may close it; `expire_pending_if_overdue()` handles
time advancing past T+1.

## Predicted Effect And Actual Consequence

Stored effect is observational predicted metadata only. It cannot modify ACTION
values, guard, `ActuatorSignal`, world physics, sensing, or pending rules. Equal
actions with different predictions create equal physical inputs in equal world
state. Stored predicted effect != actual consequence. Actual consequence is
only real `RecentCausalTransition` and downstream `ObservedEffect`; disagreement
is retained without score, correction, truth assumption, or Feedback.

## Execution Result Model

Future immutable `NFPRememberedActionExecutionResult` distinguishes:

```text
EXECUTED_AND_OBSERVED
STALE_SELECTION
INVALID_SELECTED_EXPERIENCE
ACTUATOR_INCOMPATIBLE
GUARD_DENIED
TRANSDUCTION_REJECTED
WORLD_EXECUTION_FAILED
ACTION_EXECUTED_OBSERVATION_PENDING
```

Executed results retain exact source experience ID, fresh frame ID, action
tick, selection/activation provenance, prediction and optional real transition.
These identities remain distinct. Statuses are control-plane outcomes, never
good/bad, reward, utility, goal progress, or learned success/failure.

## Deferred Feedback Handoff

Future native Feedback evaluation may receive exact `source_experience_id` +
stored predicted effect + actual `RecentCausalTransition`/`ObservedEffect`, and
may update only that source after separate review. Prediction comparison and
hit/miss semantics are deferred. This layer writes no ExpSM, AKBSM,
Chronicle/Letopis, hits, misses, confidence, or repeatability.

## Required Isolated Scenarios

Future `scenarios/nfp_remembered_action_guarded_execution.json` covers selected
data being non-executable; freshness/staleness; fresh ID, current tick and
ACTION_GENERATED; source ID distinct from frame ID; repeated fresh occurrences;
distinct source IDs for equal structures; structural and actuator validation;
no reshaping; materialize-before-guard-before-transducer; denial with no world
or pending effect; allowed real world/sensor T+1 path; prediction/physics
independence; pending only after execution; unresolved post-execution sensing;
RecentCausalTransition reuse; exact source-ID preservation; and no Feedback,
memory write, automatic execution, or `_run_tick()` wiring.

## Runtime And Authority Boundaries

The first implementation is explicit scenario/test-only orchestration. It adds
no normal runtime phase/helper and does not change `_run_tick()`, selection,
retrieval, or Feedback. Retrieval/selection never call execution automatically.
The world sees only `ActuatorSignal`, never memory identity/history/prediction.
The execution layer has no ExpSM, AKBSM or Chronicle writer authority.
