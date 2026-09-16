# Design: NFP Context And Short Memory

## Status And Checkpoints

Design-only audit after v1.3.0 (`a72f1c2`). No memory implementation is added.
This document does not authorize normal runtime wiring or permanent writes.

| Checkpoint | Established scope |
| --- | --- |
| v1.1.0 | NFP Frame/Window/Sequence substrate |
| v1.2.0 | external world -> sensory NFP |
| v1.3.0 | ACTION NFP -> world -> later sensory NFP |
| Proposed next | Context active present + Short Memory completed recent past |

Read alongside `natural_pattern_data_contract.md`,
`design_minimal_activation_pattern_substrate.md`,
`design_first_natural_pattern_transduction.md`, and
`design_first_closed_loop_action_consequence.md`. Historical checkpoint scope
is unchanged. A future isolated implementation may justify v1.4.0 only after
separate review; this pass creates no tag.

## Existing ContextMemory Audit

Searches covered ContextMemory, ContextMemoryManager, apply_pending, temporary
metadata, context temporary metadata, memory placement, working memory, short
memory, and temporary memory under `clc/`, `Memory/`, `docs/`, and `tools/`.
The relevant implementation inventory is:

| Existing file | Observed responsibility and compatibility boundary |
| --- | --- |
| `clc/context/context_memory.py` | `ContextMemory` owns raw_frames, thought_frames, events, ContextWindow references, tone_state, and marker-specific side lists. `add_frame()` separates legacy self_generated frames; `add_event()` dispatches marker payloads. Recent getters and `build_window()` expose legacy context. It already stores substantive runtime state, not only temporary metadata. |
| `clc/context/context_memory_manager.py` | `ContextMemoryManager` is the single writer. `apply_pending()` drains operations, adds frames/events, then applies event and side-list retention only when operations were applied. |
| `clc/context/context_ops_pool.py` | `ContextOpsPool` queues producer operations in a deque; the manager drains it. It is an exchange mechanism, not another memory layer. |
| `clc/context/context_retention_policy.py` | Configurable event count and side-list bounds; side lists can follow the oldest retained event tick. This is not the proposed Short Memory age policy. |
| `clc/context/window.py` | Legacy `ContextWindow` carries from_tick, to_tick, frame_ids. It is not the natural-pattern NFPWindow. |
| `clc/core/nfp.py` | Legacy `NFPFrame` uses tick, string origin/source, activation mapping, TTL/decay. It is distinct from `clc.patterns.NFPFrame`. |
| `clc/field/active_context_field.py`, `clc/field/field_updater.py` | ActiveContextField holds salient pattern activations with decay/TTL; FieldUpdater projects legacy context into that field. This is not a completed-transition ShortMemory store. |
| `clc/runtime/clc_runtime.py` | Constructs memory, pool and manager; phase helpers call apply_pending at established boundaries. No new NFP context path is connected here. |
| `clc/runtime/context_temporary_metadata.py` | Local ContextTemporaryMetadataPlacement scaffold with explicit authority, immutable metadata entries and TTL/expiration; it does not place into real ContextMemory. |
| `clc/runtime/akbsm_proposal_contextmemory_metadata.py` | Proposal metadata payload, deferred integration boundary, and adapter to the local placement scaffold; no real manager write authority. |
| `clc/runtime/context_temporary_metadata_observation.py` | Read-only local metadata observer under separate authority. |
| `clc/runtime/context_temporary_metadata_diagnostics.py` | Explicit diagnostic provider, without behavior authority. |
| `clc/runtime/context_temporary_metadata_tick_diagnostics.py` | External callable wrapper returns behavior output separately from diagnostics; not a normal _run_tick hook. |
| `clc/patterns/model.py`, `clc/transduction/windowing.py` | Immutable natural NFPFrame/NFPWindow and sensory assembler; isolated substrate, not existing ContextMemory storage. |
| `Memory/ExpSM/`, `Memory/AKBSM/` | Existing permanent memory files/CRUD; not destinations for this proposed lifecycle. No NFP-native ShortMemory implementation was found in the audited code. |

Supporting evidence is documented in `context_retention_policy.md`,
`adr_contextmemory_temporary_metadata_placement_api.md`, the runtime observation,
diagnostic wiring and tick diagnostic visibility ADRs, and
`contextmemory_temporary_metadata_architecture_map.md`. Existing placement,
observation, diagnostic and negative/retention verifiers cover the local
metadata ladder; they do not prove NFP context or Short Memory behavior.

The legacy event log is sometimes described as context history. It must not
be silently equated with the future autobiographical Chronicle / Letopis.
Existing experience/consolidation modules process legacy evaluated candidates;
this design does not route raw natural transitions through those modules.

## Architecture Decision

Reuse/evolve ContextMemoryManager: yes, it can safely host a future typed
active-present extension if that extension has explicit, isolated entry points
and leaves legacy operations, event dispatch, retention and consumers intact.
No parallel duplicate ContextMemory architecture is proposed.

Recommend an optional typed `NFPContextState` owned by existing ContextMemory,
with manager-owned observation/lifecycle methods used only by an isolated
harness initially. NFPContextState is state, not a parallel top-level manager.
Do not rename/delete ContextMemoryManager. Do not feed natural NFPFrame objects
to legacy add_frame: the APIs and origin conventions differ. Keep the old
raw/thought lists, ContextWindow, marker payloads and apply_pending timing
unchanged. Default construction must preserve current behavior.

Future components are PendingCausalTransition, RecentCausalTransition, the
typed context extension, and ShortMemory. There is no separate ExperienceCapture
memory subsystem. Do not introduce ExperienceCaptureMemory,
ExperienceCaptureStore, TransitionMemory, or EpisodeMemory as top-level stores.
Capturing before/action/after is a responsibility split across Context and Short
Memory. A completed transition is a value object inside Short Memory.

Context Memory = active present. Short Memory = bounded recent past.
The shared module workspace is an exchange mechanism: producers queue
ContextOperation objects, the manager applies them, and fields expose active
views. This does not make every inter-module message permanent context. Future
typed scene state must not inherit retention/authority from arbitrary messages.

## Active Present And Provenance

Context answers "what is active / relevant now?" Presence does not imply an
AKBSM fact, ExpSM learned rule, chronicle event, confidence increase, or semantic
interpretation. Context is not a statement of permanent truth.

The broader state can hold current sensory windows, current internal-state
activation, active internal reactivation/thought, current/recent ACTION,
pending causal transition, and current active tick / scene boundary. Initially
support only current EXTERNAL_SENSORY VISUAL NFPWindow, current ACTION +
ACTION_GENERATED NFPFrame, and one pending immediate transition. Other modalities
remain extensible rather than being represented as visual data.

External and internal material may coexist with preserved origin/provenance.
Keep their typed roles distinct; never flatten them into an indistinguishable
context blob. INTERNAL_REACTIVATION cannot satisfy an awaited external
consequence. Remembered consequence != experienced consequence.

NFPWindowAssembler is a temporal substrate/buffer mechanism, not Context Memory.
NFPWindow is a pattern structure, not a memory layer. Context selects active
material; Short Memory retains completed recent material. Window overlap is
allowed: before ending at T and after ending at T+1 may share earlier frames.
Timing and provenance distinguish the observations, not disjoint frame sets.

## Pending Transition And Qualification

PendingCausalTransition is current-state data stored in Context Memory, not a
memory subsystem. Conceptual immutable fields:

```text
transition_id
before_sensory_window
action_frame
action_tick
expected_observation_tick = action_tick + 1
```

Before must be VISUAL external sensory material. The general temporal bound is
`before_sensory_window.end_tick <= action_tick`; the first strict immediate
T -> T+1 model requires equality, so stale pre-action observations are rejected.
The action frame must have modality ACTION, origin ACTION_GENERATED, and
active_tick equal to action_tick. ACTION + INTERNAL_REACTIVATION cannot open
an executable/pending transition. Observing an action does not itself actuate
the world; the existing separate actuator path remains responsible for that.

For both sensory windows choose the stronger invariant: every frame has origin
EXTERNAL_SENSORY and the window modality is VISUAL. Existing NFPWindow.frames
exposes origin on every frame, so this can be proven without substrate changes.
NFPWindow itself checks modality/topology and increasing ticks, not uniform
origin. NFPWindowAssembler already rejects non-external frames, but the future
context boundary must independently validate directly constructed windows too.
A mixed-origin window is not qualifying evidence even if its endpoint is external.

After must have `after_sensory_window.end_tick == expected_observation_tick`.
Use compatible before/after visual topology in the first harness. A later tick
must not be associated automatically; delayed credit assignment is deferred.
Internal replay and wrong-tick material cannot complete the pending transition.

Initially allow at most one immediate pending transition. A second action while
pending must be explicitly rejected/deferred, never silently overwrite it.
No success, failure, reward, collision, meaning or expected semantic result is
part of pending state.

## Lifecycle And Missing Evidence

1. Context observes the latest qualifying external visual window ending T.
2. The harness supplies ACTION + ACTION_GENERATED at T.
3. Context creates the pending record with expected observation T+1.
4. Actuation changes the external world through the existing isolated loop.
5. A new qualifying EXTERNAL_SENSORY visual window arrives ending T+1.
6. Context constructs the completed immutable raw transition.
7. The isolated coordinator transfers it once into Short Memory.
8. Context clears pending state and advances to the new sensory window.

Future handoff must validate before mutation and avoid either duplicate insertion
or losing a completed record on a rejected insertion. Exact API is deferred;
the isolated manager/coordinator must make completion, insertion and clearing
one coherent operation. No permanent memory writer participates.

Without qualifying evidence, state remains pending until a bounded active-time
deadline, then becomes expired/incomplete and is released. Recommend allowing
observations during T+1, expiring when the explicit active clock advances past
T+1. Process same-tick observations before advancing that deadline. Rejected
internal replay does not itself advance time or expire pending state. Clock
regression and stale late delivery must not reopen an expired transition.
Exact timeout configuration may be revisited, but cannot widen the strict
observation tick rule silently. Incomplete means required observation was not
captured; it does not mean action failed. Do not fabricate a completed record.

Current sensory context advances with new qualifying windows, even after a
missing transition expires. Historical windows must not accumulate forever in
Context: preserve what pending references require, then retain completed material
in Short Memory or release it. At T pending is in Context and absent from Short;
at T+1 it is completed in Short and no longer pending in Context.

## Completed Transition And Short Memory

RecentCausalTransition is an immutable data record inside Short Memory:

```text
transition_id
before_sensory_window
action_frame
after_sensory_window
action_tick
observation_tick
optional opaque context/provenance references
```

Before/action/after remain non-semantic raw material. Exclude fields for success,
failure, good, bad, collision, reward, goal_progress and meaning. No semantic
difference object such as delta="moved right" or changed_object is introduced.
The windows themselves are evidence for future comparison.

This records an observed temporal transition, not proof that the action caused
all differences. Other world processes may contribute; later learning must not
infer exclusive causation from this record alone.

Short Memory initially holds only recently completed RecentCausalTransition
records in insertion/temporal order. It is bounded recent raw past, not permanent
storage. Use opaque occurrence IDs, preserve frame/window identity and provenance,
and reject duplicate transition insertion. Human debug/semantic names do not
define transition identity, retention, qualification or ordering.

Neither Context nor Short Memory may store hidden world state: row, column,
boundary state, hidden_debug_description or physical movement label. Admit only
observable/action-side NFP material. Existing optional debug_name fields are not
authority; the initial harness supplies label-free frames/windows and opaque
references, as the current transduction path does. Do not smuggle world fields
through free-form provenance or auxiliary metadata.

## Retention And Permanent Memory Boundaries

Short Memory uses deterministic active-time retention with both max_entries and
max_age_ticks. Recommend positive integer bounds, monotonic RNDeM active ticks,
age measured from observation_tick, and eviction when
`current_tick - observation_tick > max_age_ticks`. Age equal to the limit is
retained. Apply age pruning then evict oldest entries to meet max_entries on
insertion and explicit active-time advancement; no wall-clock aging. Preserve
the order of survivors. Exact default bound values belong to implementation.

Eviction does not imply consolidation. An evicted record may simply disappear.
Neither old age, repeated occurrence nor capacity pressure grants write authority.

- No ExpSM write: future evaluation/similarity/consolidation may derive useful
  operational experience (similar context + action -> observed tendency/effect).
  Thresholds and consolidation mechanisms are deferred.
- No AKBSM write: future repeated/evaluated evidence may inform explicit world-model
  relations; one RecentCausalTransition never directly becomes AKBSM truth.
- No chronicle write: future autobiographically relevant events may enter
  Chronicle / Letopis; every raw transition is not automatically history.

## Old Temporary Metadata Relationship

Old temporary metadata remains non-authoritative, diagnostic/scaffold bounded.
Its placement, observer, diagnostic provider and external tick wrapper retain
their explicit authority and TTL boundaries. Proposal metadata presence is not
NFP-native active cognition, sensory evidence, action occurrence or truth.
No proposal code starts calling ContextMemoryManager through this design.

Typed NFP active-present state contains validated natural frames/windows and
pending temporal relationships. Temporary diagnostic metadata contains scaffold
reports/references. Even if future infrastructure is shared, these types and
authority domains must remain separate; metadata must never complete a pending
transition or automatically enter Short Memory.

## Proposed Isolated Harness And Required Scenarios

Proposed calls below express roles, not an implemented API:

```text
visual_window_T -> context.observe_sensory(...)
action_T -> context.observe_action(...) -> pending
ACTION -> actuator -> external world transition
visual_window_T1 -> context.observe_sensory(...) -> completion
RecentCausalTransition -> ShortMemory
Context -> newest sensory state, no pending transition
```

Use the existing manager with the typed extension, instantiated by the harness.
No runtime wiring, no _run_tick integration and no permanent Memory writes.
Required future scenarios:

- Accept current EXTERNAL_SENSORY visual window and ACTION_GENERATED occurrence.
- Capture before window and action, expected observation tick T+1.
- Reject ACTION replay as an opener, stale before window and wrong modality.
- Internal visual reactivation cannot close pending; Short Memory stays unchanged.
- Reject mixed-origin windows and wrong-tick observations as consequences.
- External sensory T+1 completes exactly once with before/action/after intact.
- Completed records contain no success/failure/reward or semantic delta fields.
- Context advances; the old completed transition no longer remains pending.
- At most one pending transition; second action is explicitly rejected/deferred.
- Missing evidence expires/incompletes without semantic failure or Short insertion.
- Short Memory preserves insertion/temporal ordering and rejects duplicate IDs.
- Enforce max_entries and max_age_ticks, including exact age boundary and idle ticks.
- Eviction writes neither ExpSM nor AKBSM nor chronicle.
- Sliding window overlap is accepted; immutable shared frame references stay intact.
- Hidden world state never enters either memory; debug names do not define identity.
- Legacy operations/retention and apply_pending timing remain unchanged.
- No _run_tick integration, permanent Memory writes or proposal storage.

Strong epistemic-integrity test: open pending with external before and generated
action, present VISUAL INTERNAL_REACTIVATION at T+1, assert pending unresolved
and Short unchanged; then present real external sensory T+1, assert completion
and one raw record in Short. Remembering an outcome != experiencing an outcome.

Strong memory-layer test: unresolved current transition exists only in Context;
after valid observation Context no longer marks it pending and Short contains
the completed raw transition. This distinguishes active present from recent past.

## Deferred Scope And Safety

Deferred: _run_tick integration, automatic runtime placement, multi-action pending
transitions, delayed consequences, credit assignment, long causal chains,
reward/pain evaluation, success/failure evaluation, autonomous action selection,
ExpSM consolidation, AKBSM consolidation, chronicle consolidation, importance
scoring, forgetting based on semantic relevance, sleep consolidation, memory
replay scheduling, cross-modal causal episodes, audio consequences, proprioception,
body-state consequences, long-term NFP persistence, compression, pattern
abstraction and stable entity formation.

This pass changes only documentation and a design verifier. No runtime behavior,
ContextMemory placement or ShortMemory implementation changes. No edits to
clc/patterns/, clc/transduction/, clc/actuation/, Memory, semantic_core.json or
technical_feedback_patterns.json. No apply_pending moves, retention timing
changes, persistence, consolidation, Mode C enablement, PolicyPressureReview
connection or marker 36. Existing AKBSM write blocking stays intact.
