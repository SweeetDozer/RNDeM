"""Explicit RAM-only acquisition from an exclusively owned delivery session.

Trusted synchronous test owner, not an authentication boundary or a learner hook.
Only the existing owned-world delivery path is supported in this first pass.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import tempfile
import time
import weakref

from clc.actuation.motor import ActionTransducer
from clc.actuation.remembered_action_execution import NFPRememberedActionExecutionStatus as ExecutionStatus
from clc.experience.evidence import ExperienceEvidence, ExperienceEvidenceComparison, ExperienceEvidenceFactory
from clc.experience.grouping import ExperienceEvidenceGrouper, ExperienceGroupingConfig
from clc.experience.expsm_representation import ExpSMRecordCreationRequestBuilder
from clc.experience.expsm_native_create import (
    ExpSMCreateStatus, ExpSMRecoveryStatus, NFPExpSMCreateWriter,
    reconcile_expsm_readback_failure,
)
from clc.runtime.native_bounded_delivery import DeliveryEvent, NativeDeliverySession, Port
from clc.context.causal_transition import RecentCausalTransition
from clc.transduction import VisualFieldSnapshot, VisualFieldTransducer


@dataclass(frozen=True)
class AcquisitionLimits:
    inputs: int = 16
    evidence: int = 8
    max_values: int = 4096
    max_seconds: float = 60.0

    def __post_init__(self):
        import math
        for value in (self.inputs, self.evidence, self.max_values):
            if type(value) is not int or value < 1:
                raise ValueError('positive integer budgets required')
        if type(self.max_seconds) not in (int, float) or not math.isfinite(self.max_seconds) or self.max_seconds <= 0:
            raise ValueError('positive finite lifetime required')


METADATA_CHARS = 256
MAX_INTEGER_BITS = 64
MAX_TOPOLOGY_RANK = 16


@dataclass(frozen=True)
class OccurrenceReservation:
    execution_occurrence_id: str
    evidence_digest: str


@dataclass(frozen=True)
class AcquisitionStop:
    reason: str
    execution_occurrence_id: str | None = None
    evidence_digest: str | None = None
    error_category: str | None = None


@dataclass(frozen=True)
class ExecutionProvenance:
    """Verified apply binding, without references to the complete source record."""

    status: ExecutionStatus
    source_experience_id: str | None
    execution_occurrence_id: str
    action_frame_id: str
    action_tick: int
    signal_id: int
    signal_source_frame_ref: str
    pending_transition_id: str
    source_proposal_id: str | None
    source_created_at_world: str | None


def _texts_fit(*values):
    return all(value is None or (isinstance(value, str) and len(value) <= METADATA_CHARS)
               for value in values)


def _integers_fit(*values):
    return all(value is None or (type(value) is int and 0 <= value and value.bit_length() <= MAX_INTEGER_BITS)
               for value in values)


@dataclass(frozen=True)
class AcquisitionEnvelope:
    session_id: str
    source_id: str
    execution_occurrence_id: str
    transition_id: str
    before_window_id: str
    action_frame_id: str
    after_window_id: str
    sensor_event_ids: tuple[str, str]
    action_tick: int
    observation_tick: int
    evidence_digest: str
    evidence_id: str
    evidence: ExperienceEvidence
    transition: RecentCausalTransition
    execution: ExecutionProvenance
    sensor_events: tuple[DeliveryEvent, DeliveryEvent]


@dataclass(frozen=True)
class AdmissionResult:
    status: str
    envelope: AcquisitionEnvelope | None = None
    candidate_id: str | None = None


def _digest(transition):
    # Full immutable source content, including actual endpoint and occurrence.
    return hashlib.sha256(json.dumps(asdict(transition), sort_keys=True,
                                     separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


class BoundedNativeAcquisition:
    """One sealed evidence set, one proposal/request and at most one CREATE call.

    All dependencies must remain exclusively owned and unmodified by callers.
    Limits stop admission permanently; dedup keys are never evicted. Diagnostics
    are returned, not accumulated. Candidate count <= evidence budget; proposal,
    request, writer response and reconciliation each have capacity one.
    """

    def __init__(self, session: NativeDeliverySession, *, isolated_root: Path,
                 writer: NFPExpSMCreateWriter, limits: AcquisitionLimits = AcquisitionLimits()):
        if not isinstance(session, NativeDeliverySession):
            raise TypeError('requires owned-world NativeDeliverySession')
        if not isinstance(limits, AcquisitionLimits):
            raise TypeError('limits must be AcquisitionLimits')
        self._session_ref = weakref.ref(session)
        if not _texts_fit(session.session_id, session.delivery.VISUAL_SOURCE):
            raise ValueError('session scope exceeds metadata budget')
        self._session_id = session.session_id
        self._source_id = session.delivery.VISUAL_SOURCE
        self._last_admission_tick = 0
        c = session.components
        # Immutable path values only; no components, bound methods or callbacks.
        self._dependency_paths = tuple(Path(path) for path in (
            c.retriever.store_path, c.activation.expsm_path,
            c.activation.pattern_registry.manifest_path,
            c.context_manager.memory.pattern_registry.manifest_path,
            c.coordinator.mode_action_guard.pattern_registry.manifest_path,
        ))
        self._root = Path(isolated_root).resolve()
        # A deliberately narrow local experiment contract, never a production root.
        temporary = Path(tempfile.gettempdir()).resolve()
        if self._root == temporary or not self._root.is_relative_to(temporary):
            raise ValueError('isolated root must be a dedicated temporary subdirectory')
        self._writer_ref = weakref.ref(writer)
        self._check_paths(writer)
        self.limits = limits
        self._deadline = time.monotonic() + limits.max_seconds
        self._inputs = 0
        self._reservations: dict[str, OccurrenceReservation] = {}
        self._envelopes: dict[str, AcquisitionEnvelope] = {}
        self.stop_diagnostic: AcquisitionStop | None = None
        self._grouper = ExperienceEvidenceGrouper(ExperienceGroupingConfig(1., 1., 1., 2))
        self.state = 'admitting'
        self.proposal = None
        self.request = None
        self.create_result = None
        self.readback = None
        self.attempted = False

    @property
    def _writer(self):
        """Borrow for diagnostic/fault-injection callers; never cache the result."""
        return self._writer_ref()

    def _check_paths(self, writer):
        paths = (writer.transaction.store_path, writer.transaction.resolved_store_path,
                 writer.transaction.lock_path, *self._dependency_paths)
        if any(not Path(p).resolve().is_relative_to(self._root) for p in paths):
            raise ValueError('all store/registry paths must be isolated')
        if not writer.memory_mutation_policy.memory_is_temporary:
            raise ValueError('writer must explicitly declare temporary memory')

    @property
    def envelopes(self):
        return tuple(self._envelopes.values())

    @property
    def candidates(self):
        return self._grouper.candidates

    @property
    def reservations(self):
        return tuple(self._reservations.values())

    @property
    def stop_reason(self):
        return self.stop_diagnostic.reason if self.stop_diagnostic is not None else None

    def _stop(self, reason, *, occurrence=None, digest=None, error=None):
        if self.stop_diagnostic is None:
            # Fixed categories: do not retain arbitrary exception messages,
            # exception objects or traceback graphs.
            category = None
            if error is not None:
                category = next((kind.__name__ for kind in (MemoryError, OSError, ValueError,
                                TypeError, RuntimeError, KeyboardInterrupt, SystemExit)
                                if isinstance(error, kind)), 'external_exception')
            self.stop_diagnostic = AcquisitionStop(reason, occurrence, digest, category)
            self.state = reason
        return self.state

    def _live(self):
        if self.stop_diagnostic is not None:
            return False
        if time.monotonic() >= self._deadline:
            self._stop('stopped_lifetime')
            return False
        return True

    def admit(self, transition) -> AdmissionResult:
        if not self._live() or self.state != 'admitting':
            return AdmissionResult(self.state)
        if self._inputs >= self.limits.inputs:
            self._stop('stopped_input_budget')
            return AdmissionResult(self.state)
        self._inputs += 1
        # Borrow the source for this call only. Cached IDs never authenticate a
        # new occurrence after the actual source session has disappeared.
        session = self._session_ref()
        if session is None:
            self._stop('stopped_session_unavailable')
            return AdmissionResult(self.state)
        # Check a seen occurrence before source validation: a changed digest is a
        # terminal conflict even when the altered transition would fail binding.
        if not isinstance(transition, RecentCausalTransition):
            return AdmissionResult('invalid_transition')
        frames = (*transition.before_sensory_window.frames, transition.action_frame,
                  *transition.after_sensory_window.frames)
        if (len(transition.before_sensory_window.frames) != 1
                or len(transition.after_sensory_window.frames) != 1
                or any(len(frame.values) > self.limits.max_values for frame in frames)):
            self._stop('stopped_payload_budget')
            return AdmissionResult(self.state)
        refs = (transition.transition_id, transition.execution_occurrence_id or '',
                transition.before_sensory_window.provenance_ref, transition.before_sensory_window.debug_name,
                transition.after_sensory_window.provenance_ref, transition.after_sensory_window.debug_name,
                transition.before_sensory_window.window_id, transition.after_sensory_window.window_id,
                *(value for frame in (*transition.before_sensory_window.frames, transition.action_frame,
                                      *transition.after_sensory_window.frames)
                  for value in (frame.frame_id, frame.provenance_ref or '', frame.debug_name or '')))
        if (not _texts_fit(*refs)
                or not _integers_fit(transition.action_tick, transition.observation_tick)
                or any(len(f.topology.shape) > MAX_TOPOLOGY_RANK
                       or not _integers_fit(*f.topology.shape, f.active_tick) for f in frames)):
            self._stop('stopped_payload_budget')
            return AdmissionResult(self.state)
        digest = _digest(transition)
        occurrence = transition.execution_occurrence_id
        previous = self._reservations.get(occurrence)
        if previous is not None:
            if previous.evidence_digest != digest:
                self._stop('stopped_occurrence_conflict', occurrence=occurrence, digest=digest)
                return AdmissionResult(self.state)
            return AdmissionResult('duplicate', self._envelopes[occurrence])
        if len(self._reservations) >= self.limits.evidence:
            self._stop('stopped_evidence_budget')
            return AdmissionResult(self.state)
        binding = self._binding(transition, session)
        if isinstance(binding, str):
            return AdmissionResult(binding)
        execution = next(r.execution for r in session.records if r.tick == transition.action_tick)
        projection = ExecutionProvenance(
            execution.status, execution.source_experience_id, occurrence,
            transition.action_frame.frame_id, transition.action_tick,
            execution.actuator_signal.signal_id, execution.actuator_signal.source_frame_ref,
            execution.pending_transition.transition_id,
            execution.target_core.source_proposal_id if execution.target_core is not None else None,
            execution.target_core.created_at_world if execution.target_core is not None else None,
        )
        self._reservations[occurrence] = OccurrenceReservation(occurrence, digest)
        try:
            evidence = ExperienceEvidenceFactory.build(transition)
        except BaseException as error:
            self._stop('stopped_factory_error', occurrence=occurrence, digest=digest, error=error)
            raise
        if (evidence.context_window is not transition.before_sensory_window
                or evidence.action_frame is not transition.action_frame
                or evidence.source_transition_id != transition.transition_id
                or evidence.action_tick != transition.action_tick
                or evidence.observation_tick != transition.observation_tick):
            self._stop('stopped_factory_binding', occurrence=occurrence, digest=digest)
            return AdmissionResult(self.state)
        effect = evidence.observed_effect
        if (not _texts_fit(evidence.evidence_id, evidence.source_transition_id,
                           effect.effect_id, effect.source_transition_id,
                           effect.before_endpoint_ref, effect.after_endpoint_ref)
                or len(effect.delta_values) > self.limits.max_values
                or len(effect.topology.shape) > MAX_TOPOLOGY_RANK
                or not _integers_fit(*effect.topology.shape, effect.action_tick, effect.observation_tick)):
            self._stop('stopped_metadata_budget', occurrence=occurrence, digest=digest)
            return AdmissionResult(self.state)
        if any(e.evidence_id == evidence.evidence_id for e in self.envelopes):
            self._stop('stopped_evidence_identity_collision')
            return AdmissionResult(self.state)
        envelope = AcquisitionEnvelope(
            self._session_id, self._source_id,
            occurrence, transition.transition_id, transition.before_sensory_window.window_id,
            transition.action_frame.frame_id, transition.after_sensory_window.window_id,
            tuple(e.delivery_event_id for e in binding), transition.action_tick,
            transition.observation_tick, digest, evidence.evidence_id, evidence, transition,
            projection, binding,
        )
        try:
            grouped = self._grouper.observe(evidence)
            self._envelopes[occurrence] = envelope
            self._last_admission_tick = max(self._last_admission_tick, session.heart.tick)
        except BaseException as error:
            self._stop('stopped_grouper_error', occurrence=occurrence, digest=digest, error=error)
            raise
        return AdmissionResult('admitted', envelope, grouped.candidate_id)

    def _binding(self, t, s):
        c = s.components
        if s.session_id != self._session_id or s.delivery.VISUAL_SOURCE != self._source_id:
            return 'session_scope_mismatch'
        if not _integers_fit(s.heart.tick):
            return self._stop('stopped_metadata_budget')
        if not any(t is item for item in c.short_memory.snapshot()):
            return 'transition_not_retained'
        if s.heart.tick != c.world.current_tick or s.stop_report().synchronization_blocked:
            return 'uncertain_world_time'
        if s.heart.tick - t.observation_tick > c.short_memory.max_age_ticks:
            return 'stale_transition'
        before = next((r for r in s.records if r.tick == t.action_tick), None)
        after = next((r for r in s.records if r.tick == t.observation_tick), None)
        if before is None or after is None or after.recent is not t:
            return 'missing_completed_record'
        x = before.execution
        if x is not None and not self._execution_metadata_fit(x):
            return self._stop('stopped_metadata_budget')
        # Unlike .executed (which includes tracking failure), this status is
        # returned only after world.apply returned and pending was registered.
        if (x is None or x.status is not ExecutionStatus.ACTION_EXECUTED_OBSERVATION_PENDING
                or x.detail or x.actuator_signal is None or x.pending_transition is None
                or before.advancement != 'actuator'):
            return 'world_apply_not_confirmed'
        p = x.pending_transition
        if (not t.execution_occurrence_id or x.execution_occurrence_id != t.execution_occurrence_id
                or p.execution_occurrence_id != t.execution_occurrence_id
                or p.transition_id != t.transition_id or x.action_frame is not t.action_frame
                or p.action_frame is not t.action_frame
                or x.before_context_at_T is not t.before_sensory_window
                or before.observation is not t.before_sensory_window
                or after.observation is not t.after_sensory_window
                or p.before_sensory_window is not t.before_sensory_window
                or t.action_tick != t.before_sensory_window.end_tick
                or t.observation_tick != t.action_tick + 1
                or x.actuator_signal != replace(ActionTransducer().transduce(t.action_frame), signal_id=x.actuator_signal.signal_id)):
            return 'execution_transition_mismatch'
        events = []
        for record, window in ((before, t.before_sensory_window), (after, t.after_sensory_window)):
            traces = [j for j in s.delivery.journal if j.stage == 'native_admitted'
                      and j.detail == window.window_id and j.event is not None]
            if len(traces) != 1:
                return 'sensor_provenance_unavailable'
            e = traces[0].event
            if not self._event_metadata_fit(e):
                return self._stop('stopped_metadata_budget')
            if (e.session_id != s.session_id or e.source_id != s.delivery.VISUAL_SOURCE
                    or e.stream_id != s.delivery.VISUAL_STREAM or e.admission_tick != record.tick
                    or e.payload.active_tick != record.tick
                    or e.source_sequence != e.payload.snapshot_id
                    or e.source_timestamp is not None
                    or len(window.frames) != 1
                    or VisualFieldTransducer().transduce(e.payload, frame_id=window.frames[0].frame_id) != window.frames[0]):
                return 'external_sensor_mismatch'
            events.append(e)
        if events[1].port is not Port.CONSEQUENCE or events[1].execution_occurrence_id != t.execution_occurrence_id:
            return 'sensor_occurrence_mismatch'
        return tuple(events)

    def _execution_metadata_fit(self, x):
        # The complete result/target_core/prediction are borrowed only during
        # validation. Only ExecutionProvenance is retained in the envelope.
        if not _texts_fit(x.source_experience_id, x.detail, x.execution_occurrence_id):
            return False
        signal = x.actuator_signal
        if signal is not None and (not _texts_fit(signal.source_frame_ref)
                                   or not _integers_fit(signal.signal_id, signal.active_tick)):
            return False
        core = x.target_core
        if core is not None and (not _texts_fit(core.record_kind, core.source_proposal_id,
                                               core.initialization_profile, core.created_at_world)
                                 or not _integers_fit(core.representation_version, core.source_support_count,
                                                      core.created_active_tick)):
            return False
        return True

    def _event_metadata_fit(self, e):
        if (not isinstance(e.payload, VisualFieldSnapshot) or not isinstance(e.port, Port)
                or len(e.native_refs) > 2):
            return False
        return (_texts_fit(e.session_id, e.source_id, e.stream_id, e.delivery_event_id,
                           e.execution_occurrence_id, *e.native_refs)
                and _integers_fit(e.source_sequence, e.admission_tick, e.admission_order,
                                  e.payload.active_tick, e.payload.snapshot_id, *e.payload.shape)
                and len(e.payload.shape) == 2 and len(e.payload.values) <= self.limits.max_values
                and e.source_timestamp is None)

    def seal(self):
        if self._live() and self.state == 'admitting':
            self.state = 'sealed'
        return self.state

    def _conflicts(self):
        items = self.envelopes
        for i, left in enumerate(items):
            for right in items[i + 1:]:
                comparison = ExperienceEvidenceComparison.compare(left.evidence, right.evidence)
                if (comparison.context_comparable and comparison.context_similarity == 1.
                        and comparison.action_comparable and comparison.action_similarity == 1.
                        and (not comparison.effect_comparable or comparison.effect_similarity != 1.)):
                    return True
        return False

    def prepare(self, candidate_id: str):
        if not self._live() or self.state != 'sealed':
            return None
        if self._conflicts():
            self._stop('stopped_effect_conflict')
            return None
        candidate = next((c for c in self.candidates if c.candidate_id == candidate_id), None)
        if candidate is None:
            return None
        try:
            self.proposal = self._grouper.make_proposal(candidate_id, current_tick=self._last_admission_tick)
        except BaseException as error:
            self._stop('stopped_proposal_error', error=error)
            raise
        if self.proposal is None:
            return None
        # Frozen proposal and support are fixed before builder. No re-entry or
        # retry can allocate another proposal if request construction fails.
        self.state = 'preparing'
        try:
            self.request = ExpSMRecordCreationRequestBuilder.build(
                self.proposal, candidate.representative_evidence,
                request_id=f'{self._session_id}:bounded-acquisition',
            )
        except BaseException as error:
            self._stop('stopped_builder_error', error=error)
            raise
        self.state = 'prepared'
        return self.request

    def create(self, *, test_owner_authorized: bool = False):
        if not self._live() or self.state != 'prepared' or self.attempted:
            return None
        if test_owner_authorized is not True:
            return None
        # Recheck complete fixed support and path confinement immediately before
        # the sole writer call. No alternate writer or automatic retry exists.
        writer = self._writer_ref()
        if writer is None:
            self._stop('stopped_writer_unavailable')
            return None
        self._check_paths(writer)
        if self._conflicts():
            self._stop('stopped_effect_conflict')
            return None
        self.attempted = True
        self.state = 'attempted'
        try:
            result = writer.create(self.request)
        except BaseException as error:
            self._stop('stopped_writer_error', error=error)
            raise
        if not _texts_fit(result.reason, result.record_id, result.attempted_record_id):
            self._stop('stopped_result_metadata_budget')
            return result
        self.create_result = result
        self.state = result.status.value
        identity = result.record_id if result.status is ExpSMCreateStatus.CREATED else result.attempted_record_id
        if identity is not None and result.status in (ExpSMCreateStatus.CREATED, ExpSMCreateStatus.READBACK_FAILED):
            try:
                readback = reconcile_expsm_readback_failure(
                    writer.transaction.store_path, identity, self.request,
                )
            except BaseException as error:
                self._stop('stopped_reconciliation_error', error=error)
                raise
            if not _texts_fit(readback.reason, readback.attempted_record_id):
                self._stop('stopped_result_metadata_budget')
                return result
            self.readback = readback
            self.state = self.readback.status.value
            if self.readback.status is ExpSMRecoveryStatus.UNRESOLVED_OR_STORE_INVALID:
                self._stop('stopped_unresolved')
        return result
