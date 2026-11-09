"""RND-024 isolated, serialized owner; no ordinary Heart feedback hook.

Dependencies are exclusively owned and must not be mutated by callers. Traces
observe real calls, never replace results. Only this owner's evaluator result
can reach its writer. This is a finite trusted experiment, not a public service.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
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
from clc.experience.expsm_representation import (
    ExpSMRecordAdapter, NFPNativeOperationalRecordV1, NFPExpSMRecordV1,
)
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

# Declared before any observation or feedback. Never tune these from results.
RETRIEVAL_THRESHOLD = 1 / 3
AGREEMENT_THRESHOLD = .75
DEFAULT_SELECTOR = .35
SENSITIVITY_SELECTOR = .4


def make_session(root: Path, *, store=None, column=0, training=False,
                 selector_threshold=DEFAULT_SELECTOR, mode='active', sample_enabled=None):
    root = Path(root).resolve()
    temporary = Path(tempfile.gettempdir()).resolve()
    if root == temporary or not root.is_relative_to(temporary):
        raise ValueError('dedicated temporary root required')
    if selector_threshold not in (DEFAULT_SELECTOR, SENSITIVITY_SELECTOR):
        raise ValueError('only predeclared selector conditions are supported')
    root.mkdir(parents=True, exist_ok=False)
    path = root / 'ExpSM.json'
    # Fixture initialization/copy only. All cognitive mutations use native writers.
    path.write_text(json.dumps({'experience': {}, 'reflexes': {}} if store is None else store))
    ids = IdGenerator()
    registry = PatternRegistry(root / 'manifest.json')
    components = NativeHeartComponents(
        SyntheticClosedLoopVisualWorld(shape=(1, 3), initial_row=0, initial_column=column),
        ContextMemoryManager(ContextMemory(ids, registry), ContextOpsPool()),
        NFPExpSMRetriever(path), NFPExpSMRetrievalConfig(RETRIEVAL_THRESHOLD),
        ExpSMActivationModule(ids, registry, path), DecisionSelector(ids, selector_threshold),
        NFPRememberedActionExecutionCoordinator(ids, ModeActionGuard(registry)),
        ShortMemory(8, 10), SystemState(mode=mode),
    )

    def ingress(tick, delivery):
        if tick == (3 if training else 1):
            delivery.accept(Control.PAUSE, source_id='rnd024-owner', stream_id='control')

    options = {}
    if training:
        options = dict(
            exploration_config=SyntheticExplorationConfig(
                'rnd024-round-robin', ((0., 1.), (1., 0.)), 3, 3),
            exploration_authorization=SyntheticExplorationAuthorization(
                'rnd024-owner', 'rnd024-permit', 'rnd024-round-robin'),
        )
    return NativeDeliverySession(
        components, max_ticks=4 if training else 2, ingress=ingress,
        limits=DeliveryLimits(journal_capacity=128), sample_enabled=sample_enabled, **options), path


@dataclass(frozen=True)
class AcquiredFixture:
    record: NFPExpSMRecordV1
    store_json: str
    support_counts: tuple[int, ...]
    provenance: tuple[object, ...]
    create_status: str
    readback_status: str


def acquire(root: Path) -> AcquiredFixture:
    session, path = make_session(root, training=True)
    writer = NFPExpSMCreateWriter(path, policy_for_profile(
        'mutating_memory', memory_root=root, memory_is_temporary=True))
    owner = BoundedNativeAcquisition(session, isolated_root=root, writer=writer)
    session.run()
    for transition in session.components.short_memory.snapshot():
        if owner.admit(transition).status != 'admitted':
            raise RuntimeError('training evidence not admitted')
    owner.seal()
    supported = [c for c in owner.candidates if c.support_count >= 2]
    if len(supported) != 1 or owner.prepare(supported[0].candidate_id) is None:
        raise RuntimeError('training did not yield one conflict-free supported proposal')
    result = owner.create(test_owner_authorized=True)
    if (result is None or result.status.value != 'created'
            or owner.readback.status.value != 'confirmed_persisted'
            or owner.readback.record != result.record):
        raise RuntimeError('acquisition was not authoritatively confirmed')
    return AcquiredFixture(result.record, path.read_text(),
        tuple(c.support_count for c in owner.candidates),
        tuple(e.exploratory_provenance for e in owner.envelopes),
        result.status.value, owner.readback.status.value)


@contextmanager
def _observe_once(obj, name, traces, key):
    """One real call per boundary; temporary wrappers retain no session later."""
    original = getattr(obj, name)

    def observed(*args, **kwargs):
        if key in traces:
            raise RuntimeError('episode call budget exceeded: ' + key)
        traces[key] = (args, None)  # reserve even if the real call raises
        result = original(*args, **kwargs)
        traces[key] = (args, result)
        return result

    setattr(obj, name, observed)
    try:
        yield
    finally:
        delattr(obj, name)


def authoritative_record(path, source_id):
    state = ExpSMStoreTransaction(path).load_state_strict()
    parsed = ExpSMRecordAdapter.parse(source_id, state.experience[source_id])
    if not isinstance(parsed, NFPNativeOperationalRecordV1):
        raise ValueError('source is not native')
    return parsed.record, state


def _bounded_reason(value, fallback='diagnostic_unavailable'):
    """Admit plain scalar text only; never dispatch subclass operators."""
    if type(fallback) is not str or not 1 <= len(fallback) <= 256:
        fallback = 'diagnostic_unavailable'
    if type(value) is not str or not value:
        return fallback
    return value[:256]


def _exception_reason(exc, fallback):
    """Exception formatting and every component are untrusted inputs."""
    safe_fallback = 'diagnostic_unavailable'
    try:
        safe_fallback = _bounded_reason(fallback)
        label = type(exc).__name__
        if type(label) is not str or not label:
            return safe_fallback
        message = str(exc)
        if type(message) is not str:
            return safe_fallback
        return _bounded_reason(label + ': ' + message, safe_fallback)
    except BaseException:
        return safe_fallback


class FeedbackEpisode:
    """One run, one evaluation, at most one APPLY and one reconciliation.

    Requires a live, exclusively owned, fresh isolated session until observe().
    Thereafter only bounded typed evidence and scalar diagnostics survive.
    No external evidence argument, history, retry loop, or strong session ref.
    """

    def __init__(self, session, *, root, acquired_record, feedback_enabled=True,
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
                or c.world.shape != (1, 3) or c.short_memory.max_entries != 8
                or c.short_memory.max_age_ticks != 10 or session.heart.max_ticks != 2
                or c.retrieval_config.context_similarity_threshold != RETRIEVAL_THRESHOLD
                or c.selector.decision_threshold not in (DEFAULT_SELECTOR, SENSITIVITY_SELECTOR)
                or session.delivery.journal.maxlen != 128):
            raise ValueError('fresh bounded non-exploratory session required')
        self.path = Path(c.retriever.store_path)
        record, state = authoritative_record(self.path, acquired_record.record_id)
        if record != acquired_record or set(state.experience) != {record.record_id}:
            raise ValueError('exact acquired fixture required')
        self._session = weakref.ref(session)
        self._source = record
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
        require(len(retrieved) == len(activated) == 1, 'candidate_budget_or_chain')
        candidate, active = retrieved[0], activated[0]
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
                self.state = self.recovery.status.value
                if self.state == 'reconciliation_conflict' and not self.reason:
                    self.reason = self.recovery.reason
            elif self.result.status is NFPFeedbackApplyStatus.UPDATED:
                record, state = authoritative_record(self.path, self._source.record_id)
                receipt = (state.native_feedback_receipts or {}).get('by_event_key', {}).get(
                    self.result.event_key_digest)
                if (record != self.result.record or record != self.result.intended_record
                        or receipt is None or receipt['evidence_digest'] != self.result.evidence_digest
                        or receipt['event_key'] != self.result.event_key.to_json_data()
                        or state.native_feedback_receipts['execution_occurrence_index'].get(
                            self.evaluation.evidence.execution_occurrence_id) != self.result.event_key_digest):
                    raise ValueError('fresh_authoritative_readback_mismatch')
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
