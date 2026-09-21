# Design: ShortMemory To ExpSM Boundary

## Status And Checkpoints

Initially a design/audit/verifier boundary based on v1.4.0 at `70d228f`.
An isolated in-memory implementation now exists in `clc/experience/effects.py`,
`evidence.py`, and `grouping.py`; normal runtime and persistent memory still do
not use it.

Implemented behavior follows this document: ObservedEffect is an immutable
signed endpoint delta, ExperienceEvidence is one immutable occurrence, and
context/action/effect similarity remain three independent dimensions. The
grouper creates transient candidates with the first real evidence as exemplar.
Duplicate evidence is an idempotent `DUPLICATE`; evidence matching multiple
candidates returns `AMBIGUOUS` and mutates none. Reaching `min_support` only
makes an explicit proposal request eligible; insertion never creates a proposal.
Proposal != persistent ExpSM representation.

`tools/verify_short_memory_expsm_evaluation.py` exercises real v1.4 transition
and NFP types, zero/signed effects, independent thresholds, divergence,
duplicates, ambiguity and proposal eligibility. Its AST audit prohibits writer,
feedback, activation, selector and persistence calls. The scenario declaration
is `scenarios/short_memory_expsm_evaluation.json`.

| Checkpoint | Established scope |
| --- | --- |
| v1.1.0 | NFP substrate |
| v1.2.0 | world -> sensory NFP |
| v1.3.0 | ACTION -> world -> later sensory consequence |
| v1.4.0 | Context = active present; ShortMemory = bounded recent raw past |
| Next, proposed | raw experience -> effect/evidence -> repeated-experience candidate |

Historical tag meanings are unchanged. Read alongside
[NFP contract](natural_pattern_data_contract.md),
[Context/Short Memory design](design_nfp_context_and_short_memory.md),
[architecture checkpoint](current_architecture_checkpoint.md), and
[runtime phase map](runtime_tick_phase_map.md).

## Existing ExpSM Audit

The following inventory describes existing behavior, not new authorization.

| Source | Actual representation or behavior |
| --- | --- |
| `Memory/ExpSM/Exp_CRUD.py` | JSON maps `experience` and `reflexes`; map keys are record IDs. Experience fields: level, if, then, result, recommendation, confidence, repeatability, source, status, hits, misses, created_at_world, updated_at_world. Reflexes replace level with priority/autonomy_level and add created_from_experience. CRUD includes explicit counter-increment APIs. |
| `Memory/ExpSM/ExpSM_data.json` | Existing records use pattern-ID lists in if/then/result/recommendation, plus writer/feedback metadata. Top-level hits/misses are operational counters. Legacy metadata support_count belongs to the old draft pipeline, not the new candidate type. |
| `clc/storage_models/schemas.py` | ExperienceMatch contains record_id, record_type, similarity, confidence, priority, suggested_patterns; not a native NFP evidence schema. |
| `clc/storage_models/expsm_adapter.py` | Read-only adapter resolves pattern references, skips unresolved NFP placeholders and archived records, matches legacy frame/window inputs through PatternStore; confidence affects thresholding. Optional demo fallback is in-memory. |
| `clc/storage_models/pattern_store.py` | Legacy activation-ID/value comparison and .nfp parsers; not a durable serializer for clc/patterns NFPWindow or signed effect vectors. |
| `clc/expsm/expsm_similarity_observer.py` | Consolidation-mode observer groups record IDs by connected components of pairwise weighted Jaccard scores: if .45, then .30, result .20, recommendation .05; minimum .45. Requires nonempty if/then/result, skips archived records; emits at most five groups per run with group-key deduplication, no writes. |
| `clc/expsm/expsm_activation_module.py` | Active mode, active-field threshold .25; if-pattern coverage; activation = clamp(.55*coverage + .20*effective_confidence + .15*repeatability + .10*viability). effective_confidence <= .75; viability = (hits+1)/(hits+misses+2). Match floor .35; descending top-N, N=3. Similar records may coexist. |
| `clc/action/action_proposer.py`, `clc/action/decision_selector.py` | Activation/mechanism sources become action candidates with source metadata. Selector considers up to 20 candidates, suppression, guards and final_score, selects one above threshold (default .35), then cooldown (default 2). It selects an action candidate, not a new consolidation record. |
| `clc/expsm/expsm_mechanism_search.py` | Separate target/associated-pattern overlap search over existing records, confidence/repeatability and value adjustment; returns ranked mechanisms with experience provenance. Does not understand signed NFP effects. |
| `clc/expsm/expsm_outcome_feedback.py` | Active-mode delayed decision/outcome linkage (delay 2), record/activation/decision deduplication; hit or partial_hit adds one hit, miss adds one miss, no_feedback does nothing. Updates that linked record and metadata; partial_hits is tracked separately. |
| `clc/consolidation/expsm_commit_writer.py` | Reviewed legacy draft commit creates pattern-ID records, confidence from avg_confidence (clamped/rounded), hits=misses=0. This is not a writer for the proposed evidence. |
| `clc/consolidation/expsm_update_writer.py` | Separate reviewed draft update blends confidence = clamp(.65*old + .35*draft avg_confidence), updates repeatability/metadata/timestamp. Not observational ShortMemory grouping. |
| `clc/evaluation/value_feedback_update_writer.py` | Policy-gated reviewed update of value_feedback counts/strengths/target links, separate from simple hits/misses confidence feedback. |

Simple outcome feedback has diminishing returns, not support-count confidence:

```text
h = updated hits; m = updated misses
target = .60 * (1 - exp(-h / 20)) * h / max(1, h+m)
new_confidence = clamp(.75 * min(old_confidence, .75) + .25 * target, 0, .75)
target_repeatability = .90 * (1 - exp(-(h+m) / 10))
new_repeatability = clamp(max(.85 * old_repeatability, target_repeatability), 0, .90)
```

Stored results are rounded to three decimals. Simple-feedback target saturates
at .60; legacy confidence is soft-capped at .75 for this update and activation.
This is not a universal confidence formula for every writer: the reviewed
draft commit/update paths above have their own existing behavior.

The direct activation/mechanism feedback paths check selected source identity.
Important legacy qualification: `_selected_decisions` also accepts fallback
event links or a nearby matching decision pattern for other sources;
`_linked_outcome` has fallback linkage too. Do not describe this as an already
universal strict causal-proof guarantee. The proposed boundary must not reuse
those heuristics to assign raw evidence to a similar unused record.

`clc/runtime/memory_mutation_policy.py` defines the policy-gated writers:

| Profile | Draft write | ExpSM commit/update and value feedback update | AKBSM write |
| --- | --- | --- | --- |
| safe_demo | temporary memory only | blocked | blocked |
| draft_only | allowed | blocked | blocked |
| mutating_memory | allowed | allowed | blocked |

Important limitation: ExpSMOutcomeFeedback and low-level ExpSMCRUD are not
themselves guarded by those writer policy flags. Runtime calls outcome feedback
in its existing phase; safe-demo isolation uses temporary memory. Policy flags
are not a universal filesystem sandbox. No new path may infer write authority
from the mere existence of those APIs. Main's safe demo and existing verifiers
must preserve real memory hashes.

Coverage inspected: tools/verify_expsm_mechanism_search.py,
tools/verify_expsm_mechanism_action_source.py, tools/verify_expsm_reload.py,
tools/verify_memory_mutation_policy.py, tools/verify_scoring_selection_semantics.py,
the value-feedback verifiers, and tools/verify_scenario_fixtures.py with
scenarios/nfp_context_short_memory.json. There is no dedicated schema or
top-N/similarity-observer verifier by those names; do not claim complete
standalone numerical regression coverage from documentation checks.

## Representation Decision

Decision B: existing ExpSM schema needs a controlled extension/migration before
real NFP-native consolidation. Arbitrary JSON flexibility is not compatibility.
Current consumers interpret if/then/result as pattern references; they cannot
faithfully read native context windows, ACTION frames and signed delta effects.
An adapter/richer similarity boundary will also be required, with a versioned
representation contract. No migration or adapter is implemented here.

SimilarityObserver is not directly reusable for three-axis numeric evidence.
Its legacy weighted Jaccard and Activation's weighted ranking stay unchanged;
the no-weighted-score decision below applies to the NEW evidence grouper only.
Do not duplicate or replace the operational observer casually.

Preserve competition: SimilarityObserver groups/finds similar records;
Activation returns top-N; DecisionSelector selects one; Feedback strengthens
only the used record under the intended source-linked contract. Unused similar
records receive no punishment from this new boundary. The audit qualifications
above remain visible, not silently fixed by a docs pass.
Future compatible active records must use this existing decision architecture,
not a parallel selector. Do not collapse all operational records into one
canonical record. ShortMemory/consolidation does not influence selection here.

## Distinct Stages

```text
RecentCausalTransition -> ObservedEffect -> ExperienceEvidence
-> three-axis grouping -> ExpSMConsolidationCandidate
-> optional ExpSMConsolidationProposal -> future explicit controlled consolidation
-> active ExpSM record
```

RecentCausalTransition != ObservedEffect != ExperienceEvidence !=
ExpSMConsolidationCandidate != active ExpSM record.

The transition is raw before/action/after occurrence. Effect describes structural
change. Evidence combines one occurrence and its effect. Candidate groups
repeated evidence that MAY justify a NEW operational record later. Active ExpSM
is operational memory used by similarity/activation/selection. None substitutes
for another. In particular, forbid iterating ShortMemory and writing each raw
transition directly to ExpSM. One occurrence never automatically becomes learned
operational memory. Eviction never triggers consolidation.

## ObservedEffect And Extraction

Proposed immutable ObservedEffect fields:
effect_id, source_transition_id, modality, topology, delta_values,
before_endpoint_ref, after_endpoint_ref, action_tick, observation_tick.
References are opaque transient provenance, not persistence identities.

ObservedEffect is not NFPFrame and is not semantic evaluation.
NFP activations are in [0,1]; derived delta values are in [-1,1]. Experienced
sensory activation != derived description of change. Never coerce a signed
delta into a sensory NFP. Exclude success, failure, good, bad, reward, punishment,
collision, goal_progress, meaning, movement_direction and object_changed fields.

Take the final frame of each window:
before_endpoint = before_sensory_window.frames[-1];
after_endpoint = after_sensory_window.frames[-1].
Require same modality, equal topology, same activation length and qualifying
EXTERNAL_SENSORY provenance for both endpoints (the source transition must
also satisfy existing whole-window qualification). Reject incompatible input;
do not turn it into zero effect.

```text
delta[i] = after_endpoint.values[i] - before_endpoint.values[i]
```

Do not subtract whole overlapping windows: before=[T-2,T-1,T] and
after=[T-1,T,T+1] share history. Context remains the before window, while effect
describes endpoint(T) -> endpoint(T+1), without counting shared history again.
This is observed change, not proof that action alone caused every difference.
Richer temporal effects remain possible later.

Zero-delta effect is valid: A -> ACTION X -> A, including the world-boundary
case, means only no visible endpoint change was observed in this modality at
this step. It is NOT failure, blocked, bad, invalid experience or nothing worth
learning. It may group with repeated zero-effect evidence.

## ExperienceEvidence

Proposed immutable fields: evidence_id, source_transition_id, context_window,
action_frame, observed_effect; optional action_tick and observation_tick.
context_window = transition.before_sensory_window;
action_frame = transition.action_frame;
observed_effect.source_transition_id = transition.transition_id.
Preserve original occurrence provenance. It is not an ExpSM record and contains
no hit, miss, success, failure, reward, utility or confidence evaluation.

Process-local transition IDs need a harness/session namespace when combining
managers. Consume each occurrence once per grouping session; generating another
evidence ID for the same transition must not inflate support. Equal values
from genuinely different occurrences remain distinct evidence. Persistent
identity and cross-session deduplication are deferred, not Python object IDs.

## Three Independent Similarities

Context similarity uses NFPWindowSimilarity: same modality, equal topology and
window length under the substrate rules; aligned frame scores are averaged.
Action similarity uses NFPFrameSimilarity for compatible ACTION frames.
No label or semantic command name defines either score. Provenance qualification
belongs to evidence construction, not to the substrate similarity function.

EffectSimilarity is a proposed deterministic boundary, not implemented here.
For equal modality/topology and equal nonempty vector length, finite deltas in
[-1,1], recommend:

```text
effect_similarity = 1.0 - mean(abs(delta_a[i] - delta_b[i])) / 2.0
```

The range is [0,1]; identical deltas score 1, opposite extremes score 0.
Different modality/topology means comparable = False, not a numeric low match.
No existing NFP comparator safely accepts signed deltas as sensory activation.
Invalid vector shape/range is rejected rather than silently truncated.

Similar context != same entity; similar action != same action occurrence;
similar effect != identical world meaning. Similarity is grouping evidence only.

## Grouping And Candidates

ExperienceEvidenceGrouper is non-authoritative in-memory computation, not a new
memory subsystem. Group only when context threshold AND action threshold AND
effect threshold pass and all three comparisons are comparable. Thresholds are
explicit configuration; production values remain deferred. No weighted
mega-score combines the three axes, and no strong axis compensates for a weak one.

Same context/action with divergent effects retains separate groups/candidates.
Different context must not merge merely because action/effect match; different
action must not merge merely because context/effect match. Recurring candidates
may coexist under hidden causes, partial context or stochastic worlds.

First representative = one real supporting evidence item. Use its context,
action and effect together, not independently mixed exemplars. No averaged
synthetic sensory NFP that was never experienced. Prototype/medoid selection
is deferred. For an initial deterministic harness, compare against fixed first
exemplars in stable creation order and assign to the first qualifying group;
do not transitively merge groups through bridging observations. More advanced
clustering/order-independence is not claimed.

Proposed immutable snapshot or controlled in-memory ExpSMConsolidationCandidate:
candidate_id, representative_context, representative_action,
representative_effect, supporting_evidence_ids, support_count,
first_observation_tick, last_observation_tick.
support_count = number of distinct grouped raw evidence occurrences.
support_count != hits; support_count != confidence; neither truth probability
nor success count. No human semantic labels.

First evidence may create a candidate; repeated evidence increases support.
Configurable min_support makes a candidate eligible for later review only.
Reaching min_support never auto-writes ExpSM and is not good/bad,
successful/failed or correct/wrong evaluation. Initial operational confidence
from support requires a separate later decision.

## Proposal And Feedback Separation

Optional immutable ExpSMConsolidationProposal fields: proposal_id, candidate_id,
representative_context, representative_action, representative_effect,
support_count, source_evidence_ids, created_active_tick.
Non-authoritative, non-persistent by default, not active ExpSM.
Evidence grouping does not authorize permanent mutation; a later explicit
writer/policy review must decide the representation and commit boundary.

PATH A: observational consolidation = ShortMemory -> evidence/effect grouping
-> candidate -> possible NEW ExpSM record later.
PATH B: selected/actually used active record -> action -> observed consequence
-> existing evaluation/feedback -> update only that used record.
These are separate paths. ShortMemory evidence does not mutate existing ExpSM
records, increment hits/misses, or change confidence merely due to similarity.
Unused similar ExpSM records are not punished. Preserve current feedback and
writer behavior; this is no new update authorization and no causal-link repair.

Strong example: E1 and E2 have context A/action X/effect B; E3 has context
A/action X/effect C, with incompatible effect similarity for grouping.
Candidate B support=2; Candidate C support=1. NOT B hits=2, misses=1.
If existing R resembles E but was not selected/used, leave R.hits, R.misses and
R.confidence unchanged. If R was actually used, separate existing Feedback may
update R according to its policy. That is not ShortMemory consolidation.

## Persistence And Memory Boundaries

ShortMemory and native NFP material are process-local, not durable cognitive
objects. NFP persistence/serialization is unresolved: how can a candidate become
persistent ExpSM without dead in-memory references? Require a later stable,
versioned serialized cognitive representation and controlled schema migration.
Do not dump arbitrary Python/dataclass structures into JSON.
Never persist Python object id, process-local memory address, live object
reference or ShortMemory container reference as ExpSM identity. Opaque transient
provenance is not an already solved durable representation.

No ExpSM writes or existing-record mutation. No AKBSM writes:
ExpSM candidate != AKBSM fact. Operational evidence might later support explicit
relations, only through a separate design. No Chronicle/Letopis writes:
not every practical experience becomes autobiographical history.
No root Memory mutation, including semantic_core.json or
technical_feedback_patterns.json. No permanent proposal queues.

Candidate/evidence lifetime is separate from raw ShortMemory retention.
An explicitly consumed occurrence can support a transient candidate after its
raw record is forgotten; this does not authorize persistence or unbounded growth.
The future harness owns bounded candidate lifetime and deduplication scope.
ShortMemory eviction is not an evaluation or consolidation trigger.

## Isolated Implementation And Future Scenarios

Recommend only ObservedEffect, ExperienceEvidence, EffectSimilarity,
ExperienceEvidenceGrouper, ExpSMConsolidationCandidate and optional proposal.
A future isolated harness explicitly invokes extraction -> evidence -> grouping
-> candidate/proposal. No _run_tick integration, no ContextMemory automatic
lifecycle hook, no calls from ShortMemory.remember() or ShortMemory.prune().
No ExpSM writer. No runtime behavior changes, tick reorder, apply_pending move,
Mode C enablement, pressure influence, scoring change or marker 36 addition.

Required future executable scenarios (this pass checks documentation only):

1. Deterministic effect from final before/after frames; finite [-1,1] delta;
   effect is not NFPFrame; overlapping windows do not duplicate shared history.
2. A -> ACTION X -> A produces valid all-zero evidence, not failure or blocked.
3. Evidence retains raw transition identity/context/action/effect provenance;
   replaying one occurrence does not inflate support; reject incompatible input.
4. Context uses NFPWindowSimilarity, action uses NFPFrameSimilarity, effect
   comparison is deterministic; different effect topology is non-comparable.
5. Same context/action/effect groups together; divergent effects split;
   context mismatch and action mismatch each independently prevent merging.
6. E1/E2 -> B and E3 -> C yield support 2 and 1, never hits 2/misses 1.
7. support_count counts raw evidence only, not hits, confidence or success.
8. One observation does not write ExpSM; min_support does not auto-write;
   proposal remains non-authoritative and nonpersistent.
9. Unused similar R retains hits/misses/confidence; used R feedback stays on
   the separate existing path; no similarity-based strengthening/punishment.
10. No AKBSM, Chronicle or root Memory writes; no _run_tick integration;
    ShortMemory eviction invokes no evaluation; separate candidate lifetime.
11. Actual exemplar provenance survives grouping; all three thresholds required;
    operational competition/top-N/selection remain unaffected.

## Deferred Scope

Actual ExpSM writer; persistent NFP/experience serialization; schema migration;
candidate promotion policy; initial confidence assignment from support;
production similarity thresholds; advanced clustering; prototype/medoid
selection; weighted scoring; semantic outcome evaluation; reward/pain;
goals/wants/needs; credit assignment; delayed effects; multi-action chains;
AKBSM evidence conversion; Chronicle promotion; _run_tick integration;
automatic background consolidation; sleep/offline consolidation.

Next: review/merge the isolated implementation. Only after it is stable, design
the candidate/proposal -> persistent ExpSM representation boundary. No current
ExpSM record, schema, SimilarityObserver, Activation, DecisionSelector, Feedback,
writer, root Memory file or runtime phase is changed by this implementation.

That next boundary is now designed in
`design_persistent_nfp_expsm_representation.md`: explicit native record
kind/version, structural JSON-safe values, legacy coexistence, typed adapter
outcomes and proposal -> immutable creation request -> policy -> future writer.
It remains design-only; compatibility B, non-persistence and runtime isolation
remain in force.
