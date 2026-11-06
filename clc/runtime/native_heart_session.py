"""B2 lifecycle owner: fresh observation, housekeeping, native execution, time."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4
import math
import time

from clc.action.decision_selector import DecisionSelector
from clc.actuation.remembered_action_execution import (
    NFPRememberedActionExecutionStatus as Status, SelectedNFPExecutionRequest,
    NFPRememberedActionExecutionResult, NFPRememberedActionExecutionCoordinator,
)
from clc.context.causal_transition import PendingCausalTransition, RecentCausalTransition
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.short_memory import ShortMemory
from clc.echo.expectations import EchoExpectations, EchoMatch
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.nfp_operational_retrieval import (
    NFPExpSMRetrievalQuery, NFPExpSMRetriever, NFPExpSMRetrievalConfig,
)
from clc.internal.admission import AdmissionLimits, ComparisonAdmission, ComparisonRequest
from clc.internal.multitick import MultiTickComparison, WorkLimits, WorkSnapshot
from clc.patterns import NFPWindow
from clc.runtime.heart import Heart, HeartState
from clc.runtime.synthetic_time_adapter import SyntheticTimeAdapter
from clc.system.system_state import SystemState
from clc.transduction import VisualFieldSnapshot, VisualFieldTransducer


@dataclass(frozen=True)
class NativeHeartComponents:
    """Explicit, exclusively owned production dependencies; no default paths."""

    world: object
    context_manager: ContextMemoryManager
    retriever: NFPExpSMRetriever
    retrieval_config: NFPExpSMRetrievalConfig
    activation: ExpSMActivationModule
    selector: DecisionSelector
    coordinator: NFPRememberedActionExecutionCoordinator
    short_memory: ShortMemory
    system_state: SystemState


@dataclass(frozen=True)
class NativeHeartTick:
    tick: int
    observation: NFPWindow | None
    recent: RecentCausalTransition | None
    expired: PendingCausalTransition | None
    execution: NFPRememberedActionExecutionResult | None
    advancement: str
    diagnostic: str
    echo_matches: tuple[EchoMatch, ...] = ()


@dataclass(frozen=True)
class NativeHeartStop:
    heart_tick: int
    world_tick: int
    heart_state: HeartState
    heart_diagnostic: str
    pending: PendingCausalTransition | None
    unresolved_occurrences: tuple[str, ...]
    in_flight: bool
    synchronization_blocked: bool
    diagnostic: str


class NativeHeartSession:
    """Reuses B1 production components without calling or changing B1.run().

    Supply exclusively owned components, never share them with another session.
    No default sensor: None means no new input, never a fabricated observation.
    All operations are synchronous and serialized; no concurrent caller contract.
    """

    def __init__(
        self, components: NativeHeartComponents, *, max_ticks: int,
        sensor: Callable[[int], VisualFieldSnapshot | None] | None = None,
        initial_tick: int = 0,
        echo: EchoExpectations | None = None,
        internal_work_limits: WorkLimits | None = None,
        admission_limits: AdmissionLimits | None = None,
    ) -> None:
        self.heart = Heart(max_ticks=max_ticks, initial_tick=initial_tick)
        if components.world.current_tick != initial_tick:
            raise ValueError("initial Heart/world ticks must agree")
        self.components = components
        self.echo = echo
        self._internal_work = (MultiTickComparison(internal_work_limits)
                               if internal_work_limits is not None else None)
        if admission_limits is not None and internal_work_limits is None:
            raise ValueError("DAR requires explicit internal_work_limits")
        self._admission = (ComparisonAdmission(admission_limits, internal_work_limits)
                           if admission_limits is not None else None)
        self._dar_dispatching = False
        self.sensor = sensor
        self.time_adapter = SyntheticTimeAdapter(components.world)
        self.session_id = str(uuid4())
        self.records: list[NativeHeartTick] = []
        self.diagnostic = "ready"
        self._seen_snapshots: set[int] = set()
        self._unresolved: set[str] = set()
        self._in_flight = False
        self._inside_pulse = False

    def submit_internal_comparison(self, left: NFPWindow, right: NFPWindow) -> WorkSnapshot:
        if self._admission is not None and not self._dar_dispatching:
            raise ValueError("DAR owns the slot; use submit_comparison_request")
        if self._internal_work is None:
            raise ValueError("internal work is not enabled")
        if self.heart.state is HeartState.STOPPED or self._inside_pulse:
            raise ValueError("submit only at a live session boundary")
        return self._internal_work.submit(left, right, current_tick=self.heart.tick)

    def internal_work_snapshot(self) -> WorkSnapshot | None:
        return self._internal_work.snapshot() if self._internal_work is not None else None

    def cancel_internal_work(self) -> WorkSnapshot | None:
        if self._admission is not None:
            raise ValueError("DAR owns the slot; cancel by request ID")
        return self._internal_work.cancel() if self._internal_work is not None else None

    def release_internal_work(self) -> None:
        if self._admission is not None:
            raise ValueError("DAR owns the slot; release by request ID")
        if self._internal_work is not None:
            self._internal_work.release()

    def _close_internal_work(self) -> None:
        if self.heart.state is HeartState.STOPPED:
            if self._admission is None:
                self.cancel_internal_work()
            else:
                for request in self.comparison_requests():
                    self.cancel_comparison_request(request.request_id)

    def start(self) -> None:
        self.heart.start()

    def pause(self) -> None:
        self.heart.pause()

    def resume(self) -> None:
        self.heart.resume()

    def stop(self) -> NativeHeartStop:
        self.heart.stop()
        self._close_internal_work()
        return self.stop_report()

    def stop_report(self) -> NativeHeartStop:
        c = self.components
        return NativeHeartStop(
            self.heart.tick, c.world.current_tick, self.heart.state, self.heart.diagnostic,
            c.context_manager.pending_causal_transition,
            tuple(sorted(self._unresolved)), self._in_flight,
            self.time_adapter.blocked, self.diagnostic,
        )

    def step(self) -> NativeHeartTick | None:
        before = len(self.records)
        try:
            self._dispatch_comparison()
            self.heart.step(self._pulse)
            self._collect_comparison()
        finally:
            self._close_internal_work()
        return self.records[-1] if len(self.records) > before else None

    def run(self, **pacing: object) -> tuple[NativeHeartTick, ...]:
        try:
            if self._admission is None:
                self.heart.run(self._pulse, **pacing)
            else:
                self._run_admitted(**pacing)
        finally:
            self._close_internal_work()
        return tuple(self.records)

    def _request_boundary(self):
        if self._admission is None:
            raise ValueError("DAR is not enabled")
        if self._inside_pulse:
            raise ValueError("request mutation only at a session boundary")
        return self._admission

    def submit_comparison_request(self, left: NFPWindow, right: NFPWindow) -> ComparisonRequest:
        admission = self._request_boundary()
        if self.heart.state is HeartState.STOPPED:
            raise ValueError("session stopped")
        return admission.submit(left, right, self.heart.tick)

    def comparison_requests(self) -> tuple[ComparisonRequest, ...]:
        return self._admission.snapshots() if self._admission is not None else ()

    def cancel_comparison_request(self, request_id: str) -> ComparisonRequest:
        admission = self._request_boundary()
        if admission.active == request_id:
            admission.update(self._internal_work.cancel())
            self._internal_work.release()
        return admission.cancel_queued(request_id)

    def release_comparison_request(self, request_id: str) -> None:
        self._request_boundary().release(request_id)

    def _collect_comparison(self):
        if self._admission is not None and self._admission.active is not None:
            self._admission.update(self._internal_work.snapshot())
            if self._admission.active is None:
                self._internal_work.release()

    def _dispatch_comparison(self):
        if self._admission is None or not self.heart.admission_open:
            return
        entry = self._admission.next_inputs()
        if entry is not None:
            key, (left, right) = entry
            self._dar_dispatching = True
            try:
                work = self.submit_internal_comparison(left, right)
            finally:
                self._dar_dispatching = False
            self._admission.dispatched(key, work)

    def _run_admitted(self, *, paced=False, interval=0.01,
                      clock=time.monotonic, sleep=time.sleep):
        # Same pacing policy as Heart.run; each dispatch precedes Heart.step.
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval must be finite and positive")
        self.start()
        try:
            deadline = clock() if paced else 0.0
            while self.heart.state is HeartState.RUNNING:
                if paced:
                    delay = deadline - clock()
                    while delay > 0 and self.heart.state is HeartState.RUNNING:
                        sleep(min(delay, 0.05))
                        delay = deadline - clock()
                    if self.heart.state is not HeartState.RUNNING:
                        break
                self.step()
                if paced:
                    deadline = clock() + interval
        except BaseException:
            self.heart.stop("paced_or_pulse_failure; restart_forbidden")
            raise

    def _pulse(self, tick: int) -> None:
        self._inside_pulse = True
        c = self.components
        manager = c.context_manager
        observation = recent = expired = execution = None
        advancement = "none"
        self.diagnostic = "opening_tick"
        try:
            self.time_adapter.open(tick)
            snapshot = self.sensor(tick) if self.sensor else None
            if snapshot is not None:
                if snapshot.active_tick != tick or snapshot.snapshot_id in self._seen_snapshots:
                    raise ValueError("sensor tick/identity is not fresh; evidence is never relabelled")
                frame = VisualFieldTransducer().transduce(
                    snapshot, frame_id=f"{self.session_id}:visual:{tick}",
                )
                observation = NFPWindow(f"{self.session_id}:window:{tick}", (frame,))
                recent = manager.observe_external_sensory_window(observation)
                self._seen_snapshots.add(snapshot.snapshot_id)
                if recent is not None:
                    c.short_memory.remember(recent, current_tick=tick)
                    self._unresolved.discard(recent.execution_occurrence_id)
            expired = manager.expire_pending_if_overdue(tick)
            c.short_memory.prune(tick)
            echo_matches = self.echo.advance(tick, observation) if self.echo is not None else ()
            if self._internal_work is not None and self.heart.admission_open:
                self._internal_work.advance(tick)
            self.diagnostic = "no_new_input"
            # No query on an old present. Pending is resolved/expired before admission.
            if observation is not None and self.heart.admission_open:
                retrieval = c.retriever.retrieve(NFPExpSMRetrievalQuery(observation), c.retrieval_config)
                activated = c.activation.activate_native(retrieval.candidates)
                selected = c.selector.select_native(activated)
                self.diagnostic = "no_native_match" if not retrieval.candidates else "selection_none"
                if selected is not None and self.heart.admission_open:
                    self._in_flight = True
                    self.diagnostic = "execution_incomplete; physical_result_may_be_uncertain"
                    execution = c.coordinator.execute(
                        SelectedNFPExecutionRequest(selected, tick), context_manager=manager,
                        world=c.world, system_state=c.system_state,
                        observe_consequence=False, short_memory=c.short_memory,
                    )
                    self._in_flight = False
                    self.diagnostic = execution.status.value
                    if execution.actuator_signal is not None and execution.execution_occurrence_id:
                        self._unresolved.add(execution.execution_occurrence_id)
                    if execution.actuator_signal is not None and (
                        execution.status is not Status.ACTION_EXECUTED_OBSERVATION_PENDING
                        or execution.detail or execution.pending_transition is None
                    ):
                        self.time_adapter.block()
                        self.heart.stop("uncertain_execution; restart_forbidden")
                        self.diagnostic += "; physical_result_may_be_uncertain; stopped"
                        self.records.append(NativeHeartTick(
                            tick, observation, recent, expired, execution, advancement, self.diagnostic, echo_matches,
                        ))
                        return
            advancement = self.time_adapter.finish(
                actuator_advanced=execution is not None and execution.actuator_signal is not None,
            )
            self.records.append(NativeHeartTick(
                tick, observation, recent, expired, execution, advancement, self.diagnostic, echo_matches,
            ))
        except BaseException:
            self.time_adapter.block()
            self.heart.stop("session_failure; restart_forbidden")
            self.diagnostic += "; session_failed; no_retry"
            raise

        finally:
            self._inside_pulse = False
