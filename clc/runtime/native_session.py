"""Bounded synchronous native B1 wiring, independent of CLCRuntime."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from clc.action.decision_selector import DecisionSelector
from clc.actuation.remembered_action_execution import (
    NFPRememberedActionExecutionCoordinator,
    NFPRememberedActionExecutionResult,
    NFPRememberedActionExecutionStatus as ExecutionStatus,
    SelectedNFPExecutionRequest,
)
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.short_memory import ShortMemory
from clc.core.ids import IdGenerator
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.nfp_operational_retrieval import (
    NFPExpSMRetriever, NFPExpSMRetrievalConfig, NFPExpSMRetrievalQuery,
    NFPExpSMRetrievalResult, ActivatedNFPExpSMCandidate, SelectedNFPExpSMExperience,
)
from clc.patterns import NFPWindow
from clc.system.system_state import SystemState
from clc.transduction import VisualFieldTransducer


@dataclass(frozen=True)
class NativeSessionEpisode:
    session_id: str
    source_id: str
    before: NFPWindow
    retrieval: NFPExpSMRetrievalResult
    activated: tuple[ActivatedNFPExpSMCandidate, ...]
    selected: SelectedNFPExpSMExperience | None
    execution: NFPRememberedActionExecutionResult | None
    retained: bool
    diagnostic: str


class NativeSession:
    """One bounded series; stopped sessions cannot be restarted or retry actions.

    Components are explicitly supplied by an isolated owner. No writable path,
    default registry, fixture policy, scheduler or recovery authority is owned here.
    Local frame/provenance counters are interpreted within session_id/source_id.
    """

    def __init__(
        self, *, world: object, context_manager: ContextMemoryManager,
        retriever: NFPExpSMRetriever, retrieval_config: NFPExpSMRetrievalConfig,
        activation: ExpSMActivationModule, selector: DecisionSelector,
        coordinator: NFPRememberedActionExecutionCoordinator,
        short_memory: ShortMemory, system_state: SystemState,
        max_episodes: int, source_id: str = "synthetic_visual",
    ) -> None:
        if isinstance(max_episodes, bool) or not isinstance(max_episodes, int) or max_episodes <= 0:
            raise ValueError("max_episodes must be a positive integer")
        if not source_id.strip():
            raise ValueError("source_id must be non-empty")
        self.session_id = str(uuid4())
        self.source_id = source_id
        self.world = world
        self.context_manager = context_manager
        self.retriever = retriever
        self.retrieval_config = retrieval_config
        self.activation = activation
        self.selector = selector
        self.coordinator = coordinator
        self.short_memory = short_memory
        self.system_state = system_state
        self.max_episodes = max_episodes
        self.episodes: list[NativeSessionEpisode] = []
        self.stopped = False
        self.diagnostic = "ready"
        self._ids = IdGenerator()

    def run(self) -> tuple[NativeSessionEpisode, ...]:
        if self.stopped:
            return tuple(self.episodes)
        # Latch before entering any external operation. Even an unexpected exception
        # cannot make a second run repeat a potentially materialized occurrence.
        self.stopped = True
        self.diagnostic = "initial_observation_failed; no_session_execution"
        if self.context_manager.current_external_sensory_window is None:
            snapshot = self.world.snapshot()
            frame = VisualFieldTransducer().transduce(
                snapshot, frame_id=self._ids.next("session_initial_frame"),
            )
            self.context_manager.observe_external_sensory_window(
                NFPWindow(self._ids.next("session_initial_window"), (frame,)),
            )
        for _ in range(self.max_episodes):
            before = self.context_manager.current_external_sensory_window
            self.diagnostic = "retrieval_or_selection_failed; no_new_execution"
            retrieval = self.retriever.retrieve(
                NFPExpSMRetrievalQuery(before), self.retrieval_config,
            )
            activated = self.activation.activate_native(retrieval.candidates)
            selected = self.selector.select_native(activated)
            execution = None
            retained = False
            diagnostic = "no_native_match" if not retrieval.candidates else "selection_none"
            if selected is not None:
                self.diagnostic = "execution_incomplete; physical_result_may_be_uncertain; session_stopped"
                execution = self.coordinator.execute(
                    SelectedNFPExecutionRequest(selected, before.end_tick),
                    context_manager=self.context_manager, world=self.world,
                    system_state=self.system_state, observe_consequence=True,
                    short_memory=self.short_memory,
                )
                recent = execution.recent_transition
                retained = recent is not None and any(
                    entry is recent for entry in self.short_memory.snapshot()
                )
                diagnostic = execution.status.value
                if execution.status is ExecutionStatus.EXECUTED_AND_OBSERVED and retained and not execution.detail:
                    diagnostic = "completed"
                elif execution.actuator_signal is not None:
                    diagnostic += "; physical_result_may_be_uncertain; session_stopped"
                if execution.detail:
                    diagnostic += ": " + execution.detail
            self.episodes.append(NativeSessionEpisode(
                self.session_id, self.source_id, before, retrieval, activated,
                selected, execution, retained, diagnostic,
            ))
            self.diagnostic = diagnostic
            if diagnostic != "completed":
                break
        else:
            self.diagnostic = "episode_budget_exhausted"
        return tuple(self.episodes)
