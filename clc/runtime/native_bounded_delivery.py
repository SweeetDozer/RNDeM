"""Session-local bounded delivery for B2; no cognitive or persistence authority.

The sole native consumer is fed by this owner's direct world.snapshot() producer.
Caller-supplied source names never authenticate evidence for a pending execution.
All calls are serialized. Producer callbacks must themselves return in bounded time.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable
from uuid import uuid4

from clc.patterns import NFPFrame
from clc.runtime.heart import HeartState
from clc.runtime.native_heart_session import NativeHeartComponents, NativeHeartSession
from clc.transduction import VisualFieldSnapshot


class Port(str, Enum):
    SENSORY = 'sensory'
    CONSEQUENCE = 'execution_consequence'
    CONTROL = 'diagnostics_control'


class Control(str, Enum):
    TICK = 'tick'
    PAUSE = 'pause'
    STOP = 'stop'
    OVERLOAD = 'overload'
    DELIVERY_FAILURE = 'delivery_failure'


@dataclass(frozen=True)
class DeliveryLimits:
    sensory_capacity: int = 8
    control_capacity: int = 4
    dispatch_budget: int = 8
    journal_capacity: int = 32
    max_values: int = 4096

    def __post_init__(self):
        for name, value in vars(self).items():
            if type(value) is not int or value < 1:
                raise ValueError(f'{name} must be a positive integer')
        # One control plus one protected observation must fit every dispatch.
        if self.dispatch_budget < 2:
            raise ValueError('dispatch_budget must reserve control + visual slots')


@dataclass(frozen=True)
class DeliveryEvent:
    session_id: str
    source_id: str
    stream_id: str
    delivery_event_id: str
    port: Port
    source_sequence: int | None
    source_timestamp: float | None
    admission_tick: int
    admission_order: int
    native_refs: tuple[str, ...]
    execution_occurrence_id: str | None
    payload: VisualFieldSnapshot | NFPFrame | Control


@dataclass(frozen=True)
class DeliveryResult:
    event: DeliveryEvent | None
    status: str


@dataclass(frozen=True)
class DeliveryTrace:
    event: DeliveryEvent | None
    stage: str
    detail: str = ''


class BoundedNativeDelivery:
    """Three explicit ports, with a single private authoritative visual slot.

    accept() is the optional producer port, open only inside the Heart sensor
    callback. dispatch() delivers optional payloads to a bounded observer journal.
    The owner alone can supply the reserved visual slot. There is no ACTION port,
    caller-provided critical bit, ID registry, retry or persistence mechanism.
    """

    VISUAL_SOURCE = 'owned-synthetic-world'
    VISUAL_STREAM = 'visual'

    def __init__(self, session_id: str, limits: DeliveryLimits):
        self.session_id = session_id
        self.limits = limits
        self.journal: deque[DeliveryTrace] = deque(maxlen=limits.journal_capacity)
        self.counts: Counter[str] = Counter()
        self._sensory: deque[DeliveryEvent] = deque()
        self._control: deque[DeliveryEvent] = deque()
        self._visual: DeliveryEvent | None = None
        self._tick: int | None = None
        self._order = 0
        self._closed = False

    @property
    def depths(self) -> tuple[int, int, int]:
        return len(self._sensory), len(self._control), int(self._visual is not None)

    def _trace(self, event: DeliveryEvent | None, stage: str, detail: str = ''):
        self.counts[stage] += 1
        self.journal.append(DeliveryTrace(event, stage, detail))

    def _begin(self, tick: int):
        if self._closed or self._tick is not None:
            raise RuntimeError('delivery lifecycle is closed or reentrant')
        self._tick = tick

    def _end(self):
        self._tick = None

    def _event(self, source: str, stream: str, port: Port, payload,
               sequence=None, timestamp=None, occurrence=None) -> DeliveryEvent:
        if self._tick is None:
            raise RuntimeError('admission requires an open Heart tick')
        self._order += 1
        refs = ()
        if isinstance(payload, VisualFieldSnapshot):
            refs = (f'sensor_snapshot:{payload.snapshot_id:06d}',)
        elif isinstance(payload, NFPFrame):
            refs = (payload.frame_id, payload.provenance_ref) if payload.provenance_ref else (payload.frame_id,)
        return DeliveryEvent(self.session_id, source, stream, str(uuid4()), port,
                             sequence, timestamp, self._tick, self._order, refs,
                             occurrence, payload)

    def accept(self, payload: VisualFieldSnapshot | NFPFrame | Control, *,
               source_id: str, stream_id: str, source_sequence: int | None = None,
               source_timestamp: float | None = None) -> DeliveryResult:
        """Optional delivery only; naming the owned producer cannot grant access."""
        if self._closed or self._tick is None:
            self._trace(None, 'rejected', 'port_not_open')
            return DeliveryResult(None, 'port_not_open')
        if any(not isinstance(x, str) or not x.strip() or len(x) > 128
               for x in (source_id, stream_id)):
            raise ValueError('source/stream must be nonempty strings of at most 128 characters')
        if source_sequence is not None and (type(source_sequence) is not int or source_sequence < 0):
            raise ValueError('sequence must be a nonnegative integer')
        if source_timestamp is not None:
            import math
            if type(source_timestamp) not in (int, float) or not math.isfinite(source_timestamp):
                raise ValueError('timestamp must be finite')
        if not isinstance(payload, (VisualFieldSnapshot, NFPFrame, Control)):
            raise TypeError('only snapshot, NFPFrame or typed control is supported')
        if isinstance(payload, (VisualFieldSnapshot, NFPFrame)):
            if len(payload.values) > self.limits.max_values:
                self._trace(None, 'rejected', 'payload_limit')
                return DeliveryResult(None, 'payload_limit')
            if isinstance(payload, NFPFrame) and any(len(x) > 256 for x in (payload.frame_id, payload.provenance_ref or '')):
                raise ValueError('native references exceed delivery limit')
        if source_id == self.VISUAL_SOURCE:
            self._trace(None, 'rejected', 'reserved_source')
            return DeliveryResult(None, 'reserved_source')
        port = Port.CONTROL if isinstance(payload, Control) else Port.SENSORY
        other_queue = self._sensory if port is Port.CONTROL else self._control
        if any(e.source_id == source_id and e.stream_id == stream_id for e in other_queue):
            self._trace(None, 'rejected', 'stream_port_conflict')
            return DeliveryResult(None, 'stream_port_conflict')
        event = self._event(source_id, stream_id, port, payload, source_sequence, source_timestamp)
        queue = self._control if port is Port.CONTROL else self._sensory
        capacity = self.limits.control_capacity if port is Port.CONTROL else self.limits.sensory_capacity
        if len(queue) >= capacity:
            self._trace(event, 'rejected', 'overflow')
            return DeliveryResult(event, 'overflow')
        queue.append(event)
        self._trace(event, 'accepted')
        return DeliveryResult(event, 'accepted')

    def _reserve_visual(self, snapshot: VisualFieldSnapshot, pending) -> DeliveryResult:
        """Called only with an actual sample of this owner's execution world."""
        port = Port.CONSEQUENCE if pending is not None else Port.SENSORY
        event = self._event(self.VISUAL_SOURCE, self.VISUAL_STREAM, port, snapshot,
                            sequence=snapshot.snapshot_id,
                            occurrence=pending.execution_occurrence_id if pending is not None else None)
        if self._visual is not None or len(snapshot.values) > self.limits.max_values:
            self._trace(event, 'required_failure', 'protected_slot_or_payload_limit')
            return DeliveryResult(event, 'required_delivery_failed')
        self._visual = event
        self._trace(event, 'accepted')
        return DeliveryResult(event, 'accepted')

    def _dispatch(self, owner: NativeHeartSession) -> DeliveryEvent | None:
        budget = self.limits.dispatch_budget
        if self._control:
            event = self._control.popleft()
            self._trace(event, 'delivered', 'lifecycle_consumer')
            if event.payload is Control.STOP:
                owner.stop()
            elif event.payload is Control.PAUSE:
                owner.pause()
            budget -= 1
        visual = self._visual
        self._visual = None
        if visual is not None:
            pending = owner.components.context_manager.pending_causal_transition
            # A routing string never supplies this binding: the producer is the
            # exact same owned world used by coordinator, sampled after open(T).
            valid = visual.payload.active_tick == self._tick
            if pending is not None:
                valid = valid and (visual.execution_occurrence_id == pending.execution_occurrence_id
                                   and self._tick == pending.expected_observation_tick)
            if not valid:
                self._trace(visual, 'required_failure', 'tick_or_pending_binding')
                owner.stop()
                visual = None
            else:
                self._trace(visual, 'delivered', 'native_visual_consumer')
            budget -= 1
        while budget and self._sensory:
            self._trace(self._sensory.popleft(), 'delivered', 'observer_only')
            budget -= 1
        return visual

    def close(self):
        for queue in (self._sensory, self._control):
            while queue:
                self._trace(queue.popleft(), 'cancelled', 'terminal_stop')
        if self._visual is not None:
            self._trace(self._visual, 'cancelled', 'terminal_stop')
            self._visual = None
        self._closed = True


class NativeDeliverySession(NativeHeartSession):
    """B2 adapter: direct owned-world sampling, optional observer/control ingress.

    No external payload can become native present. The fixed producer/consumer
    binding is established by exclusive ownership of components.world, rather than
    inferred from mutable event metadata. Sampling may be disabled for a tick;
    no substitute observation is manufactured. B2's finite max_ticks bounds its
    existing records, snapshot IDs and unresolved-occurrence bookkeeping.
    """

    def __init__(self, components: NativeHeartComponents, *, max_ticks: int,
                 limits: DeliveryLimits = DeliveryLimits(),
                 ingress: Callable[[int, BoundedNativeDelivery], None] | None = None,
                 sample_enabled: Callable[[int], bool] | None = None,
                 initial_tick: int = 0):
        if components.context_manager.pending_causal_transition is not None:
            raise ValueError('cannot bind an execution started outside this delivery session')
        super().__init__(components, max_ticks=max_ticks, initial_tick=initial_tick,
                         sensor=self._sample_and_dispatch)
        self.delivery = BoundedNativeDelivery(self.session_id, limits)
        self.ingress = ingress
        self.sample_enabled = sample_enabled
        self._delivered_visual: DeliveryEvent | None = None

    def _sample_and_dispatch(self, tick):
        d = self.delivery
        d._begin(tick)
        try:
            if self.ingress is not None:
                self.ingress(tick, d)
            # Never deliver old pending as if sampled at T+2. B2 expiration owns
            # overdue relations; no native observation is admitted on that pulse.
            pending = self.components.context_manager.pending_causal_transition
            if pending is not None and tick > pending.expected_observation_tick:
                d._trace(None, 'missing_observation', 'pending_overdue; expire_in_B2')
            elif self.sample_enabled is None or self.sample_enabled(tick):
                snapshot = self.components.world.snapshot()
                result = d._reserve_visual(snapshot, pending)
                if result.status != 'accepted':
                    self.heart.stop('required_delivery_failed; no_retry')
                    # Preserve the undelivered slot for close() diagnostics.
                    return None
            self._delivered_visual = d._dispatch(self)
            return self._delivered_visual.payload if self._delivered_visual is not None else None
        finally:
            d._end()

    def _pulse(self, tick):
        self._delivered_visual = None
        try:
            super()._pulse(tick)
            event = self._delivered_visual
            if event is not None and self.records and self.records[-1].tick == tick:
                record = self.records[-1]
                if record.observation is not None:
                    self.delivery._trace(event, 'native_admitted', record.observation.window_id)
                    if record.recent is not None:
                        self.delivery._trace(event, 'causal_observed', record.recent.transition_id)
                    # B2 queries exactly once for a fresh observation while its
                    # lifecycle gate is open. No transport-level decision occurs.
                    if record.diagnostic != 'no_new_input':
                        self.delivery._trace(event, 'retrieval_used')
        except BaseException:
            self.delivery._trace(self._delivered_visual, 'delivery_failure', 'B2_pulse_failed; no_retry')
            raise
        finally:
            if self.heart.state is HeartState.STOPPED:
                self.delivery.close()

    def stop(self):
        result = super().stop()
        if hasattr(self, 'delivery'):
            # During a pulse stop is deferred by Heart; current safe boundary
            # processing is still owned by B2. Queue cancellation follows pulse.
            if self.heart.state is HeartState.STOPPED:
                self.delivery.close()
        return result

    def step(self):
        try:
            return super().step()
        finally:
            if self.heart.state is HeartState.STOPPED:
                self.delivery.close()

    def run(self, **pacing):
        try:
            return super().run(**pacing)
        finally:
            if self.heart.state is HeartState.STOPPED:
                self.delivery.close()
