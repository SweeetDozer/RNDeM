from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from clc.actuation.motor import ACTION_MOTOR_TOPOLOGY, ActionTransducer, ActuatorSignal
from clc.context.causal_transition import PendingCausalTransition, RecentCausalTransition
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.short_memory import ShortMemory
from clc.core.ids import IdGenerator
from clc.experience.expsm_representation import SerializedNFPActionV1, SerializedObservedEffectV1
from clc.expsm.nfp_operational_retrieval import SelectedNFPExpSMExperience
from clc.expsm.nfp_feedback_target import NFPFeedbackTargetCore
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState
from clc.transduction import VisualFieldTransducer


class NFPRememberedActionExecutionStatus(str, Enum):
    EXECUTED_AND_OBSERVED = "executed_and_observed"
    STALE_SELECTION = "stale_selection"
    INVALID_SELECTED_EXPERIENCE = "invalid_selected_experience"
    CAUSAL_SLOT_OCCUPIED = "causal_slot_occupied"
    ACTUATOR_INCOMPATIBLE = "actuator_incompatible"
    GUARD_DENIED = "guard_denied"
    TRANSDUCTION_REJECTED = "transduction_rejected"
    WORLD_EXECUTION_FAILED = "world_execution_failed"
    ACTION_EXECUTED_CAUSAL_TRACKING_FAILED = "action_executed_causal_tracking_failed"
    ACTION_EXECUTED_OBSERVATION_PENDING = "action_executed_observation_pending"

    @property
    def executed(self) -> bool:
        return self in {
            self.EXECUTED_AND_OBSERVED,
            self.ACTION_EXECUTED_CAUSAL_TRACKING_FAILED,
            self.ACTION_EXECUTED_OBSERVATION_PENDING,
        }


@dataclass(frozen=True)
class SelectedNFPExecutionRequest:
    selected: SelectedNFPExpSMExperience
    selection_context_end_tick: int

    def __post_init__(self) -> None:
        if not isinstance(self.selected, SelectedNFPExpSMExperience):
            raise TypeError("selected must be SelectedNFPExpSMExperience")
        if not isinstance(self.selection_context_end_tick, int) or isinstance(
            self.selection_context_end_tick, bool
        ):
            raise TypeError("selection_context_end_tick must be an integer")
        if self.selection_context_end_tick < 0:
            raise ValueError("selection_context_end_tick must be >= 0")


@dataclass(frozen=True)
class MaterializedNFPActionIntent:
    action_frame: NFPFrame
    source_experience_id: str
    source_activation_id: str
    selection_id: str
    predicted_effect: SerializedObservedEffectV1
    selection_context_end_tick: int
    before_context_at_T: NFPWindow
    target_core: NFPFeedbackTargetCore | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action_frame, NFPFrame):
            raise TypeError("action_frame must be NFPFrame")
        if self.action_frame.modality is not PatternModality.ACTION:
            raise ValueError("action_frame modality must be ACTION")
        if self.action_frame.origin is not PatternOrigin.ACTION_GENERATED:
            raise ValueError("action_frame origin must be ACTION_GENERATED")
        if not isinstance(self.before_context_at_T, NFPWindow):
            raise TypeError("before_context_at_T must be NFPWindow")
        if self.before_context_at_T.end_tick != self.selection_context_end_tick:
            raise ValueError("before context must end at selection context tick")
        if self.action_frame.active_tick != self.selection_context_end_tick:
            raise ValueError("action tick must equal selection context tick")
        for value, name in (
            (self.source_experience_id, "source_experience_id"),
            (self.source_activation_id, "source_activation_id"),
            (self.selection_id, "selection_id"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if self.action_frame.frame_id in {
            self.source_experience_id, self.source_activation_id, self.selection_id,
        }:
            raise ValueError("fresh action frame identity must be independent")
        if not isinstance(self.predicted_effect, SerializedObservedEffectV1):
            raise TypeError("predicted_effect must be SerializedObservedEffectV1")


@dataclass(frozen=True)
class NFPRememberedActionExecutionResult:
    status: NFPRememberedActionExecutionStatus
    source_experience_id: str | None = None
    action_frame: NFPFrame | None = None
    before_context_at_T: NFPWindow | None = None
    predicted_effect: SerializedObservedEffectV1 | None = None
    actuator_signal: ActuatorSignal | None = None
    pending_transition: PendingCausalTransition | None = None
    recent_transition: RecentCausalTransition | None = None
    detail: str = ""
    target_core: NFPFeedbackTargetCore | None = None

    @property
    def executed(self) -> bool:
        return self.status.executed


class NFPActionOccurrenceMaterializer:
    """Pure conversion of remembered structure into one current occurrence."""

    @staticmethod
    def materialize(
        request: SelectedNFPExecutionRequest,
        *,
        active_tick: int,
        frame_id: str,
        before_context_at_T: NFPWindow,
    ) -> MaterializedNFPActionIntent:
        if not isinstance(request, SelectedNFPExecutionRequest):
            raise TypeError("request must be SelectedNFPExecutionRequest")
        selected = request.selected
        action = selected.action
        frame = NFPFrame(
            frame_id=frame_id,
            modality=PatternModality(action.modality),
            origin=PatternOrigin.ACTION_GENERATED,
            topology=PatternTopology(action.topology),
            values=action.values,
            active_tick=active_tick,
            provenance_ref=None,
            debug_name=None,
        )
        return MaterializedNFPActionIntent(
            action_frame=frame,
            source_experience_id=selected.source_experience_id,
            source_activation_id=selected.activation_id,
            selection_id=selected.selection_id,
            predicted_effect=selected.effect,
            selection_context_end_tick=request.selection_context_end_tick,
            before_context_at_T=before_context_at_T,
            target_core=selected.target_core,
        )


class NFPRememberedActionExecutionCoordinator:
    """Explicit serialized coordinator; it owns neither retrieval nor Feedback."""

    def __init__(
        self,
        id_gen: IdGenerator,
        mode_action_guard: ModeActionGuard,
        action_transducer: ActionTransducer | None = None,
        visual_transducer: VisualFieldTransducer | None = None,
    ) -> None:
        self.id_gen = id_gen
        self.mode_action_guard = mode_action_guard
        self.action_transducer = action_transducer or ActionTransducer()
        self.visual_transducer = visual_transducer or VisualFieldTransducer()

    def execute(
        self,
        request: SelectedNFPExecutionRequest,
        *,
        context_manager: ContextMemoryManager,
        world: object,
        system_state: SystemState,
        observe_consequence: bool = True,
        short_memory: ShortMemory | None = None,
    ) -> NFPRememberedActionExecutionResult:
        if not isinstance(request, SelectedNFPExecutionRequest):
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.INVALID_SELECTED_EXPERIENCE,
                detail="request_type_invalid",
            )
        selected = request.selected
        if not isinstance(selected.action, SerializedNFPActionV1) or not isinstance(
            selected.effect, SerializedObservedEffectV1
        ):
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.INVALID_SELECTED_EXPERIENCE,
                source_experience_id=selected.source_experience_id,
                detail="selected_action_or_effect_invalid",
            )
        common = {
            "source_experience_id": selected.source_experience_id,
            "predicted_effect": selected.effect,
            "target_core": selected.target_core,
        }

        before_context_at_T = context_manager.current_external_sensory_window
        world_tick = getattr(world, "current_tick", None)
        if (
            before_context_at_T is None
            or request.selection_context_end_tick != before_context_at_T.end_tick
            or request.selection_context_end_tick != world_tick
        ):
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.STALE_SELECTION,
                detail="selection_context_tick_mismatch",
                **common,
            )
        active_tick = request.selection_context_end_tick

        if context_manager.pending_causal_transition is not None:
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.CAUSAL_SLOT_OCCUPIED,
                before_context_at_T=before_context_at_T,
                detail="pending_causal_transition_exists",
                **common,
            )

        frame_id = self._fresh_frame_id(selected)
        try:
            intent = NFPActionOccurrenceMaterializer.materialize(
                request,
                active_tick=active_tick,
                frame_id=frame_id,
                before_context_at_T=before_context_at_T,
            )
        except Exception as exc:
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.INVALID_SELECTED_EXPERIENCE,
                before_context_at_T=before_context_at_T,
                detail=str(exc),
                **common,
            )

        frame = intent.action_frame
        materialized = {
            **common,
            "action_frame": frame,
            "before_context_at_T": before_context_at_T,
        }
        if frame.topology != ACTION_MOTOR_TOPOLOGY:
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.ACTUATOR_INCOMPATIBLE,
                detail="action_topology_incompatible",
                **materialized,
            )
        if not self.mode_action_guard.is_native_action_allowed(intent, system_state, active_tick):
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.GUARD_DENIED,
                detail="native_action_denied_by_mode",
                **materialized,
            )
        try:
            signal = self.action_transducer.transduce(frame)
        except Exception as exc:
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.TRANSDUCTION_REJECTED,
                detail=str(exc),
                **materialized,
            )
        try:
            world.apply_actuator_signal(signal)
        except Exception as exc:
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.WORLD_EXECUTION_FAILED,
                actuator_signal=signal,
                detail=str(exc),
                **materialized,
            )

        executed = {**materialized, "actuator_signal": signal}
        try:
            pending = context_manager.observe_action_frame(frame)
        except Exception as exc:
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.ACTION_EXECUTED_CAUSAL_TRACKING_FAILED,
                detail=str(exc),
                **executed,
            )
        if not observe_consequence:
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.ACTION_EXECUTED_OBSERVATION_PENDING,
                pending_transition=pending,
                **executed,
            )
        try:
            snapshot = world.snapshot()
            after_frame = self.visual_transducer.transduce(
                snapshot, frame_id=self.id_gen.next("remembered_action_observation_frame"),
            )
            after_window = NFPWindow(
                self.id_gen.next("remembered_action_observation_window"), (after_frame,),
            )
            recent = context_manager.observe_external_sensory_window(after_window)
        except Exception as exc:
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.ACTION_EXECUTED_OBSERVATION_PENDING,
                pending_transition=pending,
                detail=str(exc),
                **executed,
            )
        if recent is None:
            return NFPRememberedActionExecutionResult(
                NFPRememberedActionExecutionStatus.ACTION_EXECUTED_OBSERVATION_PENDING,
                pending_transition=context_manager.pending_causal_transition,
                detail="causal_observation_not_completed",
                **executed,
            )
        detail = ""
        if short_memory is not None:
            try:
                short_memory.remember(recent, current_tick=recent.observation_tick)
            except Exception as exc:
                detail = f"short_memory_retention_failed: {exc}"
        return NFPRememberedActionExecutionResult(
            NFPRememberedActionExecutionStatus.EXECUTED_AND_OBSERVED,
            recent_transition=recent,
            detail=detail,
            **executed,
        )

    def _fresh_frame_id(self, selected: SelectedNFPExpSMExperience) -> str:
        forbidden = {
            selected.source_experience_id,
            selected.activation_id,
            selected.retrieval_candidate_id,
            selected.selection_id,
        }
        while True:
            frame_id = self.id_gen.next("remembered_action_frame")
            if frame_id not in forbidden:
                return frame_id
