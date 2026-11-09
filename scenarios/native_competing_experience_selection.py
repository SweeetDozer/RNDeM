"""RND-025 isolated competing acquired experiences; explicit invocation only.

Trusted serialized ownership, no Heart learning hooks. Initialization copies only
whole snapshots; all learned CREATE/APPLY operations use existing native writers.
The bounded two-candidate episode mirrors RND-024 provenance/exception boundaries
without changing or weakening its one-record owner.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import tempfile
import weakref

from clc.action.decision_selector import DecisionSelector
from clc.actuation.remembered_action_execution import (
    NFPRememberedActionExecutionCoordinator, NFPRememberedActionExecutionStatus,
)
from clc.actuation.synthetic_exploration import (
    SyntheticExplorationAuthorization, SyntheticExplorationConfig,
)
from clc.consolidation.expsm_store_transaction import ExpSMStoreTransaction
from clc.context.context_memory import ContextMemory
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.context_ops_pool import ContextOpsPool
from clc.context.short_memory import ShortMemory
from clc.core.ids import IdGenerator
from clc.core.pattern_registry import PatternRegistry
from clc.experience.bounded_native_acquisition import BoundedNativeAcquisition
from clc.experience.expsm_native_create import NFPExpSMCreateWriter
from clc.experience.expsm_representation import NFPExpSMRecordV1
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.nfp_feedback_target import NFPFeedbackTargetCore
from clc.expsm.nfp_native_feedback import NFPFeedbackEvaluator, NFPFeedbackEvaluationConfig
from clc.expsm.nfp_native_feedback_apply import (
    NFPFeedbackApplyWriter, NFPFeedbackApplyStatus,
    reconcile_nfp_feedback_readback_failure,
)
from clc.expsm.nfp_operational_retrieval import NFPExpSMRetriever, NFPExpSMRetrievalConfig
from clc.runtime.memory_mutation_policy import policy_for_profile
from clc.runtime.native_bounded_delivery import NativeDeliverySession, DeliveryLimits, Control, Port
from clc.runtime.native_heart_session import NativeHeartComponents
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState
from clc.transduction import VisualFieldTransducer
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld

from scenarios.native_outcome_feedback_loop import (
    _observe_once, _bounded_reason, _exception_reason, authoritative_record,
)

# Fixed before any observation. No sensitivity tuning in this experiment.
RETRIEVAL_THRESHOLD = 1 / 3
AGREEMENT_THRESHOLD = .75
DEFAULT_SELECTOR = .35
RIGHT = (0., 1.)
LEFT = (1., 0.)
EMPTY = b'{"experience": {}, "reflexes": {}}'


def temporary_root(root):
    root = Path(root).resolve()
    temporary = Path(tempfile.gettempdir()).resolve()
    if root == temporary or not root.is_relative_to(temporary):
        raise ValueError('dedicated temporary root required')
    return root


def make_session(root, *, store_bytes=None, training=None, authorized=True,
                 actions=3, mode='active', sample_enabled=None):
    """Initialize an empty store or copy a complete authoritative snapshot.

    training is A/B or None. Writes after initialization belong to native writers.
    Each factory call exclusively owns fresh world/components under its own root.
    """
    root = temporary_root(root)
    if training not in (None, 'A', 'B') or type(actions) is not int or not 1 <= actions <= 3:
        raise ValueError('bounded known training configuration required')
    if training is not None and store_bytes is not None:
        raise ValueError('training read store must start empty')
    if store_bytes is not None and type(store_bytes) is not bytes:
        raise ValueError('complete store bytes required')
    root.mkdir(parents=True, exist_ok=False)
    path = root / 'ExpSM.json'
    path.write_bytes(EMPTY if store_bytes is None else store_bytes)
    ids = IdGenerator()
    registry = PatternRegistry(root / 'manifest.json')
    components = NativeHeartComponents(
        SyntheticClosedLoopVisualWorld(shape=(1, 3), initial_row=0, initial_column=1),
        ContextMemoryManager(ContextMemory(ids, registry), ContextOpsPool()),
        NFPExpSMRetriever(path), NFPExpSMRetrievalConfig(RETRIEVAL_THRESHOLD),
        ExpSMActivationModule(ids, registry, path), DecisionSelector(ids, DEFAULT_SELECTOR),
        NFPRememberedActionExecutionCoordinator(ids, ModeActionGuard(registry)),
        ShortMemory(8, 10), SystemState(mode=mode),
    )

    def ingress(tick, delivery):
        if tick == (actions if training else 1):
            delivery.accept(Control.PAUSE, source_id='rnd025-owner', stream_id='control')

    options = {}
    if training:
        configuration = 'rnd025-' + training
        options = dict(
            exploration_config=SyntheticExplorationConfig(
                configuration, (RIGHT, LEFT) if training == 'A' else (LEFT, RIGHT),
                actions, actions),
            exploration_authorization=(SyntheticExplorationAuthorization(
                'rnd025-owner-' + training, 'rnd025-permit-' + training, configuration)
                if authorized else None),
        )
    return NativeDeliverySession(
        components, max_ticks=actions + 1 if training else 2, ingress=ingress,
        limits=DeliveryLimits(journal_capacity=128), sample_enabled=sample_enabled,
        **options), path


@dataclass(frozen=True)
class AcquisitionTrace:
    session_id: str
    request_id: str
    occurrences: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    support_counts: tuple[int, ...]
    exploratory_provenance: tuple[object, ...]
    create_status: str
    readback_status: str


@dataclass(frozen=True)
class AcquiredPair:
    records: tuple[NFPExpSMRecordV1, ...]
    store_bytes: bytes
    traces: tuple[AcquisitionTrace, ...]


def acquire_pair(root):
    """Two empty training readers, two owners, one isolated CREATE destination.

    No owner is re-entered after uncertainty; caller must stop on any exception.
    Local proposal counters are deliberately not used as cross-session identities.
    """
    root = temporary_root(root)
    root.mkdir(parents=True, exist_ok=False)
    destination = root / 'competition.json'
    destination.write_bytes(EMPTY)
    writer = NFPExpSMCreateWriter(destination, policy_for_profile(
        'mutating_memory', memory_root=root, memory_is_temporary=True))
    records, traces = [], []
    for name in ('A', 'B'):
        session, path = make_session(root / ('training-' + name), training=name)
        owner = BoundedNativeAcquisition(session, isolated_root=root, writer=writer)
        session.run()
        retained = session.components.short_memory.snapshot()
        if len(retained) != 3 or path.read_bytes() != EMPTY:
            raise ValueError('three genuine transitions from empty reader required')
        if [owner.admit(t).status for t in retained] != ['admitted'] * 3:
            raise ValueError('full retained set must be admitted')
        if sorted(c.support_count for c in owner.candidates) != [1, 2]:
            raise ValueError('exact support 2/1 required')
        owner.seal()
        supported = next(c for c in owner.candidates if c.support_count == 2)
        if owner.prepare(supported.candidate_id) is None:
            raise ValueError('conflict-free supported proposal required')
        result = owner.create(test_owner_authorized=True)
        if (result is None or result.status.value != 'created'
                or owner.readback.status.value != 'confirmed_persisted'
                or owner.readback.record != result.record):
            raise ValueError('CREATE not authoritatively confirmed; no retry')
        record, state = authoritative_record(destination, result.record_id)
        expected_action = RIGHT if name == 'A' else LEFT
        expected_effect = (0., -1., 1.) if name == 'A' else (1., -1., 0.)
        if (record != result.record or record.context.frames != ((0., 1., 0.),)
                or record.action.values != expected_action
                or record.effect.delta_values != expected_effect
                or len(state.experience) != len(records) + 1
                or any(authoritative_record(destination, r.record_id)[0] != r for r in records)):
            raise ValueError('independent acquired semantics or prior record changed')
        records.append(record)
        traces.append(AcquisitionTrace(session.session_id, owner.request.request_id,
            tuple(e.execution_occurrence_id for e in owner.envelopes),
            tuple(e.evidence.evidence_id for e in owner.envelopes),
            tuple(c.support_count for c in owner.candidates),
            tuple(e.exploratory_provenance for e in owner.envelopes),
            result.status.value, owner.readback.status.value))
    if (records[0].record_id == records[1].record_id
            or traces[0].session_id == traces[1].session_id
            or traces[0].request_id == traces[1].request_id
            or set(traces[0].occurrences) & set(traces[1].occurrences)
            or set(traces[0].evidence_ids) & set(traces[1].evidence_ids)
            or any(p is None for t in traces for p in t.exploratory_provenance)):
        raise ValueError('independent provenance required')
    return AcquiredPair(tuple(records), destination.read_bytes(), tuple(traces))


class CompetingEpisode:
    """One run, one evaluation, at most one APPLY and one reconciliation.

    Requires a live, exclusively owned, fresh isolated session until observe().
    Thereafter only bounded typed evidence and scalar diagnostics survive.
    No external evidence argument, history, retry loop, or strong session ref.
    """

    def __init__(self, session, *, root, acquired_records, feedback_enabled=True,
                 profile='mutating_memory'):
        root = Path(root).resolve()
        temporary = Path(tempfile.gettempdir()).resolve()
        if root == temporary or not root.is_relative_to(temporary):
            raise ValueError('dedicated temporary root required')
        c = session.components
        paths = (c.retriever.store_path, c.activation.expsm_path,
                 c.activation.pattern_registry.manifest_path,
                 c.context_manager.memory.pattern_registry.manifest_path,
                 c.coordinator.mode_action_guard.pattern_registry.manifest_path)
        if any(not Path(p).resolve().is_relative_to(root) for p in paths):
            raise ValueError('all dependencies must be isolated')
        if (session.exploration is not None or session.records or c.world.current_tick != 0
                or c.world.hidden_position != (0, 1) or c.world.shape != (1, 3)
                or c.short_memory.max_entries != 8
                or c.short_memory.max_age_ticks != 10 or session.heart.max_ticks != 2
                or c.retrieval_config.context_similarity_threshold != RETRIEVAL_THRESHOLD
                or c.selector.decision_threshold != DEFAULT_SELECTOR
                or session.delivery.journal.maxlen != 128):
            raise ValueError('fresh bounded non-exploratory session required')
        self.path = Path(c.retriever.store_path)
        if (type(acquired_records) is not tuple or len(acquired_records) != 2
                or any(not isinstance(r, NFPExpSMRecordV1) for r in acquired_records)
                or len({r.record_id for r in acquired_records}) != 2):
            raise ValueError('two distinct acquired records required')
        self._records = {r.record_id: r for r in acquired_records}
        expected_effects = {RIGHT: (0., -1., 1.), LEFT: (1., -1., 0.)}
        if ({r.action.values for r in acquired_records} != {RIGHT, LEFT}
                or any(r.context.frames != ((0., 1., 0.),)
                       or r.context.topology != (1, 3)
                       or r.action.topology != (2,)
                       or r.effect.delta_values != expected_effects[r.action.values]
                       or r.creation_metadata.source_support_count != 2
                       for r in acquired_records)):
            raise ValueError('acquired center/right and center/left pair required')
        for source_id, expected in self._records.items():
            record, state = authoritative_record(self.path, source_id)
            if record != expected or set(state.experience) != set(self._records):
                raise ValueError('exact acquired pair required')
        self._session = weakref.ref(session)
        self._source = None  # established only from the real selected chain
        self.retrieval_order = self.activation_order = self.scores = ()
        self.context_values = self.actual_values = self.executed_action = None
        self.execution_occurrence_id = None
        self._enabled = feedback_enabled
        self._writer = NFPFeedbackApplyWriter(self.path, policy_for_profile(
            profile, memory_root=root, memory_is_temporary=True))
        self.state = 'new'
        self.reason = ''
        self.evaluation = self.result = self.recovery = self.readback = None
        self.activation = self.context_similarity = self.selected_source = None
        self.physical_calls = 0
        self.attempted = False

    def _stop(self, reason):
        self.state = 'stopped'
        if not self.reason:
            self.reason = _bounded_reason(reason)

    def observe(self):
        if self.state != 'new':
            return self.evaluation
        self.state = 'observing'
        session = self._session()
        if session is None:
            self._stop('session_released_before_binding')
            return None
        c = session.components
        traces = {}
        try:
            from contextlib import ExitStack
            with ExitStack() as stack:
                for obj, name, key in (
                    (c.retriever, 'retrieve', 'retrieval'),
                    (c.activation, 'activate_native', 'activation'),
                    (c.selector, 'select_native', 'selection'),
                    (c.coordinator, 'execute', 'execution'),
                    (c.world, 'apply_actuator_signal', 'physical'),
                ):
                    stack.enter_context(_observe_once(obj, name, traces, key))
                session.run()
            self.physical_calls = int('physical' in traces)
            self._bind_and_evaluate(session, traces)
        except BaseException as exc:
            self.state = 'stopped'
            self.physical_calls = int('physical' in traces)
            if not self.reason:
                self.reason = 'observation_exception'
                try:
                    self.reason = _bounded_reason(_exception_reason(exc, self.reason), self.reason)
                except BaseException:
                    pass  # even a failed diagnostic helper cannot replace exc
            raise  # original error/traceback, never replace it with a recovery error
        return self.evaluation

    def _bind_and_evaluate(self, session, traces):
        def require(condition, reason):
            if not condition:
                raise ValueError(reason)

        require(len(session.records) <= 2, 'tick_budget')
        require('selection' in traces, 'no_selection_call')
        selected = traces['selection'][1]
        if selected is None:
            activated = traces['activation'][1]
            if len(activated) == 1:
                self.activation = activated[0].activation
                self.context_similarity = activated[0].context_similarity
            self.state = 'no_selection'
            return
        self.selected_source = selected.source_experience_id
        self.activation = selected.activation
        self.context_similarity = selected.context_similarity
        require('execution' in traces, 'unexecuted_selection')
        request = traces['execution'][0][0]
        execution = traces['execution'][1]
        require(request.selected is selected, 'unselected_action')
        retrieved = traces['retrieval'][1].candidates
        activated = traces['activation'][1]
        require(len(retrieved) == len(activated) == 2, 'candidate_budget_or_chain')
        require({c.source_experience_id for c in retrieved} == set(self._records)
                == {a.source_experience_id for a in activated}, 'candidate_sources')
        for c in retrieved:
            a = next(a for a in activated if a.retrieval_candidate_id == c.candidate_id)
            record = self._records[c.source_experience_id]
            require(c.target_core == a.target_core == NFPFeedbackTargetCore.from_record(record)
                    and c.source_experience_id == a.source_experience_id
                    and c.action == a.action == record.action
                    and c.effect == a.effect == record.effect
                    and (c.hits, c.misses, c.confidence, c.repeatability)
                    == (record.operational.hits, record.operational.misses,
                        record.operational.confidence, record.operational.repeatability)
                    and c.context_similarity == a.context_similarity == 1., 'candidate_record_chain')
        require(selected.source_experience_id in self._records, 'source_mismatch')
        self._source = self._records[selected.source_experience_id]
        candidate = next(c for c in retrieved if c.source_experience_id == self._source.record_id)
        active = next(a for a in activated if a.source_experience_id == self._source.record_id)
        self.retrieval_order = tuple(c.source_experience_id for c in retrieved)
        self.activation_order = tuple(a.source_experience_id for a in activated)
        self.scores = tuple((a.source_experience_id, a.activation) for a in activated)
        core = NFPFeedbackTargetCore.from_record(self._source)
        require(candidate.source_experience_id == active.source_experience_id
                == selected.source_experience_id == execution.source_experience_id
                == self._source.record_id, 'source_mismatch')
        require(candidate.candidate_id == active.retrieval_candidate_id
                == selected.retrieval_candidate_id
                and active.activation_id == selected.activation_id, 'selection_chain')
        require(candidate.target_core == active.target_core == selected.target_core
                == execution.target_core == core, 'target_core_mismatch')
        require(candidate.effect == selected.effect == execution.predicted_effect
                == self._source.effect and selected.action == self._source.action,
                'expected_provenance_mismatch')
        require(execution.exploratory_intent is None, 'exploration_not_off')
        if (execution.status is not NFPRememberedActionExecutionStatus.ACTION_EXECUTED_OBSERVATION_PENDING
                or execution.detail or not execution.guard_passed):
            self._stop('ineligible_execution: ' + _bounded_reason(execution.status.value))
            return
        retained = session.components.short_memory.snapshot()
        require(len(retained) <= 1, 'retention_budget')
        if not retained:
            self._stop('missing_retained_actual_t_plus_1')
            return
        t = retained[0]
        before, after = session.records
        p = execution.pending_transition
        require(before.execution is execution and after.recent is t
                and before.advancement == 'actuator' and self.physical_calls == 1,
                'execution_not_confirmed')
        require(traces['physical'][0][0] is execution.actuator_signal
                and execution.actuator_signal.values == selected.action.values
                and execution.actuator_signal.active_tick == t.action_tick,
                'physical_signal_mismatch')
        require(not session.stop_report().synchronization_blocked
                and session.heart.tick == session.components.world.current_tick,
                'uncertain_execution')
        require(p is not None and t.execution_occurrence_id == execution.execution_occurrence_id
                == p.execution_occurrence_id and p.transition_id == t.transition_id
                and t.action_frame is execution.action_frame is p.action_frame
                and execution.before_context_at_T is t.before_sensory_window
                is p.before_sensory_window is before.observation
                and after.observation is t.after_sensory_window
                and t.action_frame.values == selected.action.values
                and t.action_tick == request.selection_context_end_tick
                == t.before_sensory_window.end_tick
                and t.observation_tick == t.action_tick + 1, 'occurrence_transition_mismatch')
        for tick, window in ((t.action_tick, t.before_sensory_window),
                             (t.observation_tick, t.after_sensory_window)):
            events = [j.event for j in session.delivery.journal
                      if j.stage == 'native_admitted' and j.detail == window.window_id]
            require(len(events) == 1 and events[0] is not None, 'missing_sensor_provenance')
            e = events[0]
            require(e.session_id == session.session_id
                    and e.source_id == session.delivery.VISUAL_SOURCE
                    and e.stream_id == session.delivery.VISUAL_STREAM
                    and e.admission_tick == e.payload.active_tick == tick
                    and e.source_sequence == e.payload.snapshot_id
                    and e.source_timestamp is None
                    and len(window.frames) == 1
                    and VisualFieldTransducer().transduce(
                        e.payload, frame_id=window.frames[0].frame_id) == window.frames[0],
                    'owned_sensor_mismatch')
            if tick == t.observation_tick:
                require(e.port is Port.CONSEQUENCE
                        and e.execution_occurrence_id == t.execution_occurrence_id,
                        'sensor_occurrence_mismatch')
        self.context_values = t.before_sensory_window.frames[0].values
        self.actual_values = t.after_sensory_window.frames[0].values
        self.executed_action = t.action_frame.values
        self.execution_occurrence_id = execution.execution_occurrence_id
        self.evaluation = NFPFeedbackEvaluator.evaluate(
            execution, t, NFPFeedbackEvaluationConfig(AGREEMENT_THRESHOLD))
        if self.evaluation.evidence is not None:
            self.state = 'evaluated'
        else:
            self._stop('feedback_evaluation_ineligible')

    def apply(self):
        if self.state != 'evaluated' or self.attempted:
            return self.result
        if not self._enabled:
            self.state = 'feedback_disabled'
            return None
        self.attempted = True  # latch before any writer entry, including exceptions
        self.state = 'applying'
        try:
            result = self._writer.apply(self.evaluation.evidence)
            # Keep authoritative fields unchanged; admit diagnostic text only.
            self.result = replace(result, reason=_bounded_reason(result.reason))
            if self.result.status is NFPFeedbackApplyStatus.READBACK_FAILED:
                self.state = 'persistence_uncertain'
                recovery = reconcile_nfp_feedback_readback_failure(self.path, self.result)
                self.recovery = replace(recovery, reason=_bounded_reason(recovery.reason))
                if self.recovery.status.value == 'reconciled_applied':
                    self._check_other_records()
                self.state = self.recovery.status.value
                if self.state == 'reconciliation_conflict' and not self.reason:
                    self.reason = self.recovery.reason
            elif self.result.status is NFPFeedbackApplyStatus.UPDATED:
                record, state = authoritative_record(self.path, self._source.record_id)
                receipt = (state.native_feedback_receipts or {}).get('by_event_key', {}).get(
                    self.result.event_key_digest)
                if (record != self.result.record or record != self.result.intended_record
                        or receipt is None or receipt['evidence_digest'] != self.result.evidence_digest
                        or receipt['source_experience_id'] != self._source.record_id
                        or receipt['event_key'] != self.result.event_key.to_json_data()
                        or state.native_feedback_receipts['execution_occurrence_index'].get(
                            self.evaluation.evidence.execution_occurrence_id) != self.result.event_key_digest):
                    raise ValueError('fresh_authoritative_readback_mismatch')
                self._check_other_records()
                self.readback = record
                self.state = 'confirmed_applied'
            elif self.result.status is NFPFeedbackApplyStatus.WRITE_FAILED:
                # Existing reconciliation accepts READBACK_FAILED only. Do not
                # relabel this result or trust retry_safe after possible replace.
                self.state = 'persistence_uncertain'
                if not self.reason:
                    self.reason = 'WRITE_FAILED; no retry; reconciliation API inapplicable'
            else:
                self.state = self.result.status.value
                if not self.reason:
                    self.reason = self.result.reason
        except BaseException as exc:
            # APPLY/reconciliation may have changed storage. Never re-enter.
            self.state = 'persistence_uncertain'
            if not self.reason:
                self.reason = 'persistence_exception'
                try:
                    self.reason = _bounded_reason(_exception_reason(exc, self.reason), self.reason)
                except BaseException:
                    pass
            raise
        return self.result

    def _check_other_records(self):
        for source_id, expected in self._records.items():
            record, state = authoritative_record(self.path, source_id)
            if set(state.experience) != set(self._records):
                raise ValueError('competition inventory changed')
            if source_id != self._source.record_id and record != expected:
                raise ValueError('feedback changed unselected record')
