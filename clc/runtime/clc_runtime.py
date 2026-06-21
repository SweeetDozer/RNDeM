from pathlib import Path
import shutil
import tempfile

from clc.action.action_candidate_field import ActionCandidateField
from clc.action.action_proposer import ActionProposer
from clc.action.action_guard_audit_observer import ActionGuardAuditObserver
from clc.action.decision_audit_observer import DecisionAuditObserver
from clc.action.decision_cycle_summary_observer import DecisionCycleSummaryObserver
from clc.action.decision_selector import DecisionSelector
from clc.action.internal_action_executor import InternalActionExecutor
from clc.akbsm.akbsm_association_field import AKBSMAssociationField
from clc.akbsm.akbsm_association_field_updater import AKBSMAssociationFieldUpdater
from clc.akbsm.akbsm_association_probe import AKBSMAssociationProbe
from clc.consolidation.consolidation_mode_processor import ConsolidationModeProcessor
from clc.consolidation.consolidation_pressure_module import ConsolidationPressureModule
from clc.consolidation.draft_commit_gate import DraftCommitGate
from clc.consolidation.expsm_commit_writer import ExpSMCommitWriter
from clc.consolidation.expsm_update_review_gate import ExpSMUpdateReviewGate
from clc.consolidation.expsm_update_writer import ExpSMUpdateWriter
from clc.consolidation.memory_draft_writer import MemoryDraftWriter
from clc.consolidation.memory_write_review_module import MemoryWriteReviewModule
from clc.context.context_memory import ContextMemory
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.context_ops_pool import ContextOpsPool
from clc.context.context_retention_policy import ContextRetentionPolicy, SideListRetentionPolicy
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.pattern_registry import PatternRegistry
from clc.diagnostics.retention_diagnostics import (
    RetentionDiagnostics,
    format_retention_metrics,
    format_side_list_retention_metrics,
)
from clc.dlm.internal_state_dlm import InternalStateDLM
from clc.dlm.novelty_dlm import NoveltyDLM
from clc.dlm.rhythm_dlm import RhythmDLM
from clc.dlm.risk_dlm import RiskDLM
from clc.evaluation.evaluation_field import EvaluationField
from clc.evaluation.evaluation_field_updater import EvaluationFieldUpdater
from clc.evaluation.evaluation_signal_module import EvaluationSignalModule
from clc.evaluation.evaluation_target_observer import EvaluationTargetObserver
from clc.evaluation.decision_cycle_history_view import DecisionCycleHistoryView
from clc.evaluation.need_more_evidence_signal import NeedMoreEvidenceSignalBuilder
from clc.evaluation.policy_pressure import PolicyPressureBuilder
from clc.evaluation.policy_pressure_review import PolicyPressureReviewBuilder
from clc.evaluation.reflection_candidate_builder import ReflectionCandidateBuilder
from clc.evaluation.reflection_review import ReflectionReviewBuilder
from clc.evaluation.target_satisfaction_observer import TargetSatisfactionObserver
from clc.evaluation.value_feedback_candidate_builder import ValueFeedbackCandidateBuilder
from clc.evaluation.value_feedback_memory_view import ValueFeedbackMemoryView
from clc.evaluation.value_feedback_review_gate import ValueFeedbackReviewGate
from clc.evaluation.value_feedback_update_writer import ValueFeedbackUpdateWriter
from clc.experience.experience_candidate_buffer import ExperienceCandidateBuffer
from clc.experience.experience_candidate_builder import ExperienceCandidateBuilder
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.expsm_competition_observer import ExpSMCompetitionObserver
from clc.expsm.expsm_mechanism_search import ExpSMMechanismSearch
from clc.expsm.expsm_outcome_feedback import ExpSMOutcomeFeedback
from clc.expsm.expsm_similarity_observer import ExpSMSimilarityObserver
from clc.field.active_context_field import ActiveContextField
from clc.field.field_updater import FieldUpdater
from clc.homeostasis.homeostasis_module import HomeostasisModule
from clc.neuromodulation.neuromodulation_module import NeuromodulationModule
from clc.outcome.outcome_evaluator import OutcomeEvaluator
from clc.prediction.simple_future_state_predictor import SimpleFutureStatePredictor
from clc.preprocessing.input_preprocessor import InputPreprocessor
from clc.runtime.memory_mutation_policy import MemoryMutationPolicy, RuntimeProfile, policy_for_profile
from clc.storage_models.akbsm_adapter import AKBSMAdapter
from clc.storage_models.expsm_adapter import ExpSMAdapter
from clc.storage_models.fake_akbsm import FakeAKBSM
from clc.storage_models.fake_expsm import FakeExpSM
from clc.storage_models.pattern_store import PatternStore
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.mode_transition_cleanup import ModeTransitionCleanup
from clc.system.system_mode_manager import SystemModeManager
from clc.system.system_state import SystemState
from clc.thought.thought_generator import ThoughtGeneratorModule

MEMORY_ROOT = Path("Memory")


class CLCRuntime:
    """Minimal continuous context loop runtime.

    Each tick:
    1. external preprocessor operations are committed
    2. DLM and prediction modules read memory and enqueue operations
    3. neuromodulation updates tone
    4. thoughts are generated as internal NFP frames and committed
    """

    def __init__(
        self,
        memory_root: Path | str = MEMORY_ROOT,
        *,
        profile: RuntimeProfile | str = RuntimeProfile.SAFE_DEMO,
        memory_mutation_policy: MemoryMutationPolicy | None = None,
        memory_is_temporary: bool = False,
        context_retention_policy: ContextRetentionPolicy | None = None,
        side_list_retention_policy: SideListRetentionPolicy | None = None,
    ) -> None:
        self.id_gen = IdGenerator()
        self.memory_root = Path(memory_root)
        self.memory_mutation_policy = memory_mutation_policy or policy_for_profile(
            profile,
            memory_root=self.memory_root,
            memory_is_temporary=memory_is_temporary,
        )
        self.pattern_registry = PatternRegistry(self.memory_root / "pattern_manifest.json")
        self.ops_pool = ContextOpsPool()
        self.memory = ContextMemory(self.id_gen, self.pattern_registry)
        self.system_state = SystemState()
        self.system_state.runtime_profile = self.memory_mutation_policy.profile.value
        self.system_state.memory_mutation_policy = self.memory_mutation_policy.summary()
        self.active_field = ActiveContextField()
        self.evaluation_field = EvaluationField()
        self.value_feedback_memory_view = ValueFeedbackMemoryView(
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_data.json",
        )
        self.decision_cycle_history_view = DecisionCycleHistoryView()
        self.reflection_candidate_builder = ReflectionCandidateBuilder(self.id_gen)
        self.need_more_evidence_signal_builder = NeedMoreEvidenceSignalBuilder(self.id_gen)
        self.need_more_evidence_signal = None
        self.reflection_review_builder = ReflectionReviewBuilder(self.id_gen)
        self.reflection_review = None
        self.policy_pressure_builder = PolicyPressureBuilder(self.id_gen)
        self.policy_pressure = None
        self.policy_pressure_review_builder = PolicyPressureReviewBuilder(self.id_gen)
        self.policy_pressure_review = None
        self.akbsm_association_field = AKBSMAssociationField()
        self.action_candidate_field = ActionCandidateField(self.id_gen)
        self.field_updater = FieldUpdater(self.pattern_registry)
        self.evaluation_field_updater = EvaluationFieldUpdater()
        self.akbsm_association_field_updater = AKBSMAssociationFieldUpdater()
        self.context_retention_policy = context_retention_policy or ContextRetentionPolicy()
        self.side_list_retention_policy = side_list_retention_policy or SideListRetentionPolicy()
        self.manager = ContextMemoryManager(
            self.memory,
            self.ops_pool,
            self.context_retention_policy,
            self.side_list_retention_policy,
        )
        self._expsm_reload_event_ids: set[str] = set()
        self.preprocessor = InputPreprocessor(self.id_gen, self.pattern_registry)
        self.pattern_store = PatternStore(self.memory_root / "AKBSM" / "DB", self.pattern_registry)
        self._install_fallback_patterns_if_needed()
        self.akbsm = AKBSMAdapter(self.memory_root / "AKBSM" / "AKBSM_ne.json")
        self.expsm = ExpSMAdapter(self.memory_root / "ExpSM" / "ExpSM_data.json", self.pattern_store, self.pattern_registry)
        self.fallback_akbsm = FakeAKBSM(self.pattern_registry)
        self.fallback_expsm = FakeExpSM(self.pattern_registry)
        self.dlms = [
            RhythmDLM(self.id_gen, self.pattern_registry),
            NoveltyDLM(self.id_gen, self.pattern_registry, self.pattern_store, self.akbsm),
            RiskDLM(self.id_gen, self.pattern_registry, self.expsm, self.fallback_expsm),
            InternalStateDLM(self.id_gen, self.pattern_registry),
        ]
        self.predictors = [SimpleFutureStatePredictor(self.id_gen, self.pattern_registry, self.expsm)]
        self.neuromodulation = NeuromodulationModule(self.id_gen, self.pattern_registry)
        self.thought_generator = ThoughtGeneratorModule(self.id_gen, self.pattern_registry)
        self.action_proposer = ActionProposer(self.pattern_registry)
        self.mode_action_guard = ModeActionGuard(self.pattern_registry)
        self.mode_transition_cleanup = ModeTransitionCleanup(self.pattern_registry)
        self.decision_selector = DecisionSelector(self.id_gen)
        self.decision_audit_observer = DecisionAuditObserver(self.id_gen, self.pattern_registry)
        self.action_guard_audit_observer = ActionGuardAuditObserver(self.id_gen, self.pattern_registry)
        self.decision_cycle_summary_observer = DecisionCycleSummaryObserver(self.id_gen, self.pattern_registry)
        self.internal_action_executor = InternalActionExecutor(self.id_gen, self.pattern_registry)
        self.outcome_evaluator = OutcomeEvaluator(self.id_gen, self.pattern_registry)
        self.evaluation_signal = EvaluationSignalModule(self.id_gen, self.pattern_registry)
        self.evaluation_target_observer = EvaluationTargetObserver(self.id_gen, self.pattern_registry)
        self.target_satisfaction_observer = TargetSatisfactionObserver(self.id_gen, self.pattern_registry)
        self.value_feedback_candidate_builder = ValueFeedbackCandidateBuilder(self.id_gen, self.pattern_registry)
        self.value_feedback_review_gate = ValueFeedbackReviewGate(self.id_gen, self.pattern_registry)
        self.value_feedback_update_writer = ValueFeedbackUpdateWriter(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_data.json",
            self.memory_mutation_policy,
        )
        self.akbsm_association_probe = AKBSMAssociationProbe(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "AKBSM",
        )
        self.expsm_mechanism_search = ExpSMMechanismSearch(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_data.json",
            self.value_feedback_memory_view,
        )
        self.experience_candidate_builder = ExperienceCandidateBuilder(self.id_gen, self.pattern_registry)
        self.experience_candidate_buffer = ExperienceCandidateBuffer(self.id_gen, self.pattern_registry)
        self.retention_diagnostics = RetentionDiagnostics(self.memory_root / "ExpSM" / "ExpSM_drafts.json")
        self.expsm_activation = ExpSMActivationModule(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_data.json",
        )
        self.expsm_outcome_feedback = ExpSMOutcomeFeedback(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_data.json",
        )
        self.expsm_competition_observer = ExpSMCompetitionObserver(self.id_gen, self.pattern_registry)
        self.expsm_similarity_observer = ExpSMSimilarityObserver(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_data.json",
        )
        self.consolidation_pressure = ConsolidationPressureModule(self.id_gen, self.pattern_registry)
        self.system_mode_manager = SystemModeManager(self.id_gen, self.pattern_registry)
        self.consolidation_processor = ConsolidationModeProcessor(self.id_gen, self.pattern_registry)
        self.memory_write_review = MemoryWriteReviewModule(self.id_gen, self.pattern_registry)
        self.memory_draft_writer = MemoryDraftWriter(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_drafts.json",
            self.memory_mutation_policy,
        )
        self.draft_commit_gate = DraftCommitGate(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_drafts.json",
        )
        self.expsm_commit_writer = ExpSMCommitWriter(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_drafts.json",
            self.memory_root / "ExpSM" / "ExpSM_data.json",
            self.memory_mutation_policy,
        )
        self.expsm_update_review_gate = ExpSMUpdateReviewGate(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_drafts.json",
        )
        self.expsm_update_writer = ExpSMUpdateWriter(
            self.id_gen,
            self.pattern_registry,
            self.memory_root / "ExpSM" / "ExpSM_drafts.json",
            self.memory_root / "ExpSM" / "ExpSM_data.json",
            self.memory_mutation_policy,
        )
        self.homeostasis = HomeostasisModule(self.id_gen, self.pattern_registry)

    def memory_summary(self) -> dict[str, int]:
        return {
            "patterns": len(self.pattern_store.list_patterns()),
            "akbsm_edges": len(self.akbsm.list_edges()),
            "expsm_experiences": len(self.expsm.list_experiences()),
            "expsm_reflexes": len(self.expsm.list_reflexes()),
        }

    def debug_print_memory_summary(self) -> None:
        summary = self.memory_summary()
        print("Memory loading summary:")
        print(f"  NFP patterns loaded: {summary['patterns']}")
        print(f"  AKBSM edges loaded: {summary['akbsm_edges']}")
        print(f"  ExpSM experiences loaded: {summary['expsm_experiences']}")
        print(f"  ExpSM reflexes loaded: {summary['expsm_reflexes']}")
        warnings = self.pattern_store.warnings + self.akbsm.warnings + self.expsm.consume_warnings()
        if warnings:
            print("  warnings:")
            for warning in warnings:
                print(f"    {warning}")
        self._debug_print_runtime_profile()
        # TODO: WL must be redesigned as self-generated NFP/self-space pattern storage before integration.

    def _install_fallback_patterns_if_needed(self) -> None:
        if self.pattern_store.list_patterns():
            return
        self.pattern_store.add_pattern(
            "fallback_audio_rhythm",
            {
                self.pattern_registry.id("aud_freq_440"): 0.8,
                self.pattern_registry.id("aud_freq_880"): 0.2,
            },
            "fallback://audio_rhythm",
        )
        self.pattern_store.add_pattern(
            "fallback_internal_warning",
            {
                self.pattern_registry.id("sen_integrity_warning"): 1.0,
                self.pattern_registry.id("sen_memory_pressure"): 0.8,
            },
            "fallback://internal_warning",
        )

    def feed_audio(self, tick: int, frequencies: dict[int, float]) -> None:
        self.ops_pool.push(self.preprocessor.audio(tick, frequencies))
        self._run_tick(tick)

    def feed_sensor(self, tick: int, cpu_temp: float, memory_usage: float, damage_flag: bool, resource_pressure: float) -> None:
        self.ops_pool.push(self.preprocessor.sensor(tick, cpu_temp, memory_usage, damage_flag, resource_pressure))
        self._run_tick(tick)

    def feed_image(self, tick: int, pixels: list[list[tuple[float, float, float]]]) -> None:
        self.ops_pool.push(self.preprocessor.image(tick, pixels))
        self._run_tick(tick)

    def build_demo_image_from_memory(self, pattern_id: str = "1", size: int = 2) -> list[list[tuple[float, float, float]]] | None:
        values = self.pattern_store.activation_values.get(pattern_id)
        if not values:
            return None
        pixels = [[{"r": 0.0, "g": 0.0, "b": 0.0} for _ in range(size)] for _ in range(size)]
        found = False
        for activation_id, value in values.items():
            debug_name = self.pattern_registry.debug_name(activation_id)
            parts = debug_name.split("_")
            if len(parts) != 4 or parts[0] != "img":
                continue
            try:
                x = int(parts[1][1:])
                y = int(parts[2][1:])
            except ValueError:
                continue
            channel = parts[3]
            if x >= size or y >= size or channel not in {"r", "g", "b"}:
                continue
            pixels[y][x][channel] = value
            found = True
        if not found:
            return None
        return [[(pixel["r"], pixel["g"], pixel["b"]) for pixel in row] for row in pixels]

    def _run_tick(self, tick: int) -> None:
        self._phase_00_input_commit()
        active_processing = self.system_state.mode in {"active", "recovery"}
        self._phase_01_primary_updates(tick, active_processing)
        self._phase_02_field_activation_and_consolidation_pressure(tick)
        decision = self._phase_03_action_proposal_and_selection(tick)
        self._phase_04_decision_audit_and_effects(tick, decision)
        self._phase_05_mode_consolidation_memory_chain(tick)
        self._phase_06_outcome_evaluation_akbsm_mechanism(tick, active_processing)
        self._phase_07_value_feedback(tick)
        self._phase_08_neuromodulation_projection(tick)
        self._phase_09_final_field_refresh(tick)
        self._phase_10_runtime_observation_views(tick)
        self._phase_11_debug_output(tick)

    def _phase_00_input_commit(self) -> None:
        self.manager.apply_pending()

    def _phase_01_primary_updates(self, tick: int, active_processing: bool) -> None:
        if active_processing:
            for dlm in self.dlms:
                self.ops_pool.extend(dlm.run(tick, self.memory))
            self.manager.apply_pending()
            for predictor in self.predictors:
                self.ops_pool.extend(predictor.run(tick, self.memory))
            self.manager.apply_pending()
            self.ops_pool.extend(self.neuromodulation.run(tick, self.memory))
            self.manager.apply_pending()
            self.ops_pool.extend(self.thought_generator.run(tick, self.memory, self.active_field))
            self.manager.apply_pending()

    def _phase_02_field_activation_and_consolidation_pressure(self, tick: int) -> None:
        self.field_updater.update_from_memory(tick, self.memory, self.active_field)
        self.active_field.decay_all(tick)
        self.ops_pool.extend(self.expsm_activation.run(tick, self.memory, self.active_field, self.system_state))
        self.manager.apply_pending()
        self.field_updater.update_from_memory(tick, self.memory, self.active_field)
        self.ops_pool.extend(
            self.consolidation_pressure.run(
                tick,
                self.memory,
                self.memory.get_current_tone(),
                self.active_field,
                self.system_state,
            )
        )
        self.manager.apply_pending()
        self.field_updater.update_from_memory(tick, self.memory, self.active_field)
        self.ops_pool.extend(self.expsm_update_review_gate.run(tick, self.memory, self.active_field, self.system_state))
        self.manager.apply_pending()
        self.field_updater.update_from_memory(tick, self.memory, self.active_field)

    def _phase_03_action_proposal_and_selection(self, tick: int):
        self.action_proposer.propose(tick, self.memory, self.active_field, self.action_candidate_field, self.system_state)
        self.action_candidate_field.decay_all(tick)
        return self.decision_selector.select(
            tick,
            self.action_candidate_field,
            self.system_state,
            self.mode_action_guard,
        )

    def _phase_04_decision_audit_and_effects(self, tick: int, decision) -> None:
        if decision is not None:
            self.ops_pool.push(decision)
            self.manager.apply_pending()
            self.ops_pool.extend(self.decision_audit_observer.run(tick, self.memory, self.system_state))
            self.manager.apply_pending()
            self.field_updater.update_from_memory(tick, self.memory, self.active_field)
            self.ops_pool.extend(self.action_guard_audit_observer.run(tick, self.memory, self.system_state))
            self.manager.apply_pending()
            self.field_updater.update_from_memory(tick, self.memory, self.active_field)
            self.ops_pool.extend(self.decision_cycle_summary_observer.run(tick, self.memory, self.system_state))
            self.manager.apply_pending()
            self.field_updater.update_from_memory(tick, self.memory, self.active_field)
            self.ops_pool.extend(self.expsm_competition_observer.run(tick, self.memory, self.active_field, self.system_state))
            self.manager.apply_pending()
            self.field_updater.update_from_memory(tick, self.memory, self.active_field)
            self.ops_pool.extend(
                self.internal_action_executor.run(
                    tick,
                    self.memory,
                    self.system_state,
                    self.mode_action_guard,
                )
            )
            self.manager.apply_pending()
            self.ops_pool.extend(self.neuromodulation.run_effects(tick, self.memory))
            self.manager.apply_pending()
            self.ops_pool.extend(self.thought_generator.run_effects(tick, self.memory))
            self.manager.apply_pending()

    def _phase_05_mode_consolidation_memory_chain(self, tick: int) -> None:
        self.ops_pool.extend(self.system_mode_manager.run(tick, self.memory, self.system_state, self.active_field))
        self.manager.apply_pending()
        self.field_updater.update_from_memory(tick, self.memory, self.active_field)
        self._cleanup_mode_transitions(tick)
        self.ops_pool.extend(
            self.consolidation_processor.run(
                tick,
                self.memory,
                self.memory.get_current_tone(),
                self.active_field,
                self.system_state,
            )
        )
        self.manager.apply_pending()
        self.ops_pool.extend(self.memory_write_review.run(tick, self.memory, self.active_field, self.system_state))
        self.manager.apply_pending()
        self.ops_pool.extend(self.memory_draft_writer.run(tick, self.memory, self.active_field, self.system_state))
        self.manager.apply_pending()
        self.ops_pool.extend(self.draft_commit_gate.run(tick, self.memory, self.active_field, self.system_state))
        self.manager.apply_pending()
        self.ops_pool.extend(self.expsm_commit_writer.run(tick, self.memory, self.active_field, self.system_state))
        self.manager.apply_pending()
        self.ops_pool.extend(self.expsm_update_writer.run(tick, self.memory, self.active_field, self.system_state))
        self.manager.apply_pending()
        self._reload_expsm_if_modified(tick)
        self.ops_pool.extend(self.expsm_similarity_observer.run(tick, self.memory, self.active_field, self.system_state))
        self.manager.apply_pending()
        self.field_updater.update_from_memory(tick, self.memory, self.active_field)

    def _phase_06_outcome_evaluation_akbsm_mechanism(self, tick: int, active_processing: bool) -> None:
        if active_processing and self.system_state.mode != "consolidation":
            self.ops_pool.extend(self.outcome_evaluator.run(tick, self.memory, self.active_field))
            self.manager.apply_pending()
            self.ops_pool.extend(self.expsm_outcome_feedback.run(tick, self.memory, self.active_field, self.system_state))
            self.manager.apply_pending()
            self._reload_expsm_if_modified(tick)
            self.ops_pool.extend(self.evaluation_signal.run(tick, self.memory, self.active_field, self.system_state))
            self.manager.apply_pending()
            self.evaluation_field_updater.run(tick, self.memory, self.evaluation_field)
            self.ops_pool.extend(
                self.evaluation_target_observer.run(tick, self.memory, self.evaluation_field, self.system_state)
            )
            self.manager.apply_pending()
            self.ops_pool.extend(
                self.akbsm_association_probe.run(
                    tick,
                    self.memory,
                    self.active_field,
                    self.evaluation_field,
                    self.system_state,
                )
            )
            self.manager.apply_pending()
            self.akbsm_association_field_updater.run(tick, self.memory, self.akbsm_association_field)
            self.ops_pool.extend(
                self.expsm_mechanism_search.run(
                    tick,
                    self.memory,
                    self.active_field,
                    self.evaluation_field,
                    self.akbsm_association_field,
                    self.system_state,
                )
            )
            self.manager.apply_pending()
            self.field_updater.update_from_memory(tick, self.memory, self.active_field)
            self.ops_pool.extend(self.experience_candidate_builder.run(tick, self.memory, self.active_field))
            self.manager.apply_pending()
            self.ops_pool.extend(self.experience_candidate_buffer.run(tick, self.memory, self.active_field))
            self.manager.apply_pending()

    def _phase_07_value_feedback(self, tick: int) -> None:
        self.ops_pool.extend(
            self.target_satisfaction_observer.run(
                tick,
                self.memory,
                self.active_field,
                self.evaluation_field,
                self.system_state,
            )
        )
        self.manager.apply_pending()
        self.ops_pool.extend(self.value_feedback_candidate_builder.run(tick, self.memory, self.system_state))
        self.manager.apply_pending()
        self.ops_pool.extend(self.value_feedback_review_gate.run(tick, self.memory, self.system_state))
        self.manager.apply_pending()
        self.ops_pool.extend(self.value_feedback_update_writer.run(tick, self.memory, self.system_state))
        self.manager.apply_pending()
        self._reload_expsm_if_modified(tick)
        self.field_updater.update_from_memory(tick, self.memory, self.active_field)

    def _phase_08_neuromodulation_projection(self, tick: int) -> None:
        self.ops_pool.extend(self.neuromodulation.run_outcomes(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_candidates(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_consolidation_candidates(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_memory_write_reviews(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_memory_draft_writes(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_memory_draft_commit_reviews(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_memory_commits(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_committed_draft_observations(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_expsm_update_reviews(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_memory_updates(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_expsm_activations(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_expsm_feedback(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_expsm_similarity_observations(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_expsm_competition_observations(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_decision_audits(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_action_guard_audits(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_decision_cycle_summaries(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_evaluation_signals(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_evaluation_targets(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_akbsm_association_probes(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_expsm_mechanism_searches(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_target_satisfaction_observations(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_value_feedback_candidates(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_value_feedback_reviews(tick, self.memory))
        self.manager.apply_pending()
        self.ops_pool.extend(self.neuromodulation.run_value_feedback_updates(tick, self.memory))
        self.manager.apply_pending()

    def _phase_09_final_field_refresh(self, tick: int) -> None:
        self.ops_pool.extend(self.homeostasis.run(tick, self.memory, self.memory.get_current_tone(), self.active_field))
        self.manager.apply_pending()
        self.evaluation_field_updater.run(tick, self.memory, self.evaluation_field)
        self.akbsm_association_field_updater.run(tick, self.memory, self.akbsm_association_field)
        self.field_updater.update_from_memory(tick, self.memory, self.active_field)

    def _phase_10_runtime_observation_views(self, tick: int) -> None:
        history_snapshot = self.decision_cycle_history_view.refresh(
            tick=tick,
            decision_cycle_summaries=self.memory.get_recent_decision_cycle_summaries(
                self.decision_cycle_history_view.window_size
            ),
        )
        reflection_candidates = self.reflection_candidate_builder.build(tick=tick, history_snapshot=history_snapshot)
        self.need_more_evidence_signal = self.need_more_evidence_signal_builder.build(
            tick=tick,
            reflection_candidates=reflection_candidates,
        )
        self.reflection_review = self.reflection_review_builder.build(
            tick=tick,
            history_snapshot=history_snapshot,
            reflection_candidates=reflection_candidates,
            need_more_evidence_signal=self.need_more_evidence_signal,
        )
        self.policy_pressure = self.policy_pressure_builder.build(
            tick=tick,
            reflection_review=self.reflection_review,
        )
        self.policy_pressure_review = self.policy_pressure_review_builder.build(
            tick=tick,
            policy_pressure=self.policy_pressure,
        )

    def _phase_11_debug_output(self, tick: int) -> None:
        self._debug_print_system_state()
        self._debug_print_runtime_profile()
        self._debug_print_memory_mutation_blocks()
        self._debug_print_context_retention()
        self._debug_print_side_list_retention()
        self.memory.debug_print_state(tick)
        self._debug_print_learnability()
        self._debug_print_mode_action_guard(tick)
        self._debug_print_mode_transition_cleanup(tick)
        self._debug_print_candidate_buffer()
        self._debug_print_draft_store()
        self._debug_print_retention_diagnostics(tick)
        self._debug_print_side_list_retention_diagnostics(tick)
        self._debug_print_active_field()
        self._debug_print_evaluation_field()
        self._debug_print_value_feedback_memory_view()
        self._debug_print_akbsm_association_field()
        self._debug_print_decision_cycle_history()
        self._debug_print_reflection_candidates()
        self._debug_print_need_more_evidence_signal()
        self._debug_print_reflection_review()
        self._debug_print_policy_pressure()
        self._debug_print_policy_pressure_review()
        self._debug_print_decision_cycle_summaries()
        self._debug_print_action_candidates()

    def _reload_expsm_if_modified(self, tick: int) -> None:
        reload_markers = {
            OperationMarker.MEMORY_COMMITTED,
            OperationMarker.MEMORY_UPDATED,
            OperationMarker.EXPSM_FEEDBACK,
            OperationMarker.VALUE_FEEDBACK_UPDATED,
        }
        should_reload = False
        for event in self.memory.events:
            if event.tick != tick or event.op_id in self._expsm_reload_event_ids or event.marker not in reload_markers:
                continue
            payload = dict(event.payload)
            if not payload.get("permanent_memory_modified"):
                continue
            if payload.get("target") not in {None, "ExpSM", "expsm"} and event.marker != OperationMarker.EXPSM_FEEDBACK:
                continue
            self._expsm_reload_event_ids.add(event.op_id)
            should_reload = True
        if should_reload:
            self.expsm.reload(tick)
            self.value_feedback_memory_view.refresh()
            print("ExpSM repository reloaded after memory write")

    def _debug_print_system_state(self) -> None:
        print("system state:")
        print(f"  mode: {self.system_state.mode}")
        print(f"  entered_tick: {self.system_state.mode_entered_tick}")
        print(f"  last_consolidation_tick: {self.system_state.last_consolidation_tick}")
        print(f"  depth: {round(self.system_state.consolidation_depth, 3)}")

    def _debug_print_runtime_profile(self) -> None:
        policy = self.memory_mutation_policy
        print("runtime profile:")
        print(f"  profile={policy.profile.value}")
        print(f"  memory_is_temporary={str(policy.memory_is_temporary).lower()}")
        print(f"  allow_draft_writes={str(policy.allow_draft_writes).lower()}")
        print(f"  allow_expsm_commit={str(policy.allow_expsm_commit).lower()}")
        print(f"  allow_expsm_update={str(policy.allow_expsm_update).lower()}")
        print(f"  allow_value_feedback_update={str(policy.allow_value_feedback_update).lower()}")
        print(f"  allow_akbsm_write={str(policy.allow_akbsm_write).lower()}")

    def _debug_print_memory_mutation_blocks(self) -> None:
        blocked = [
            update
            for update in self.memory.module_updates[-12:]
            if update.get("blocked_by_policy")
        ]
        print("memory mutation blocked:")
        if not blocked:
            print("  none")
            return
        for update in blocked[-6:]:
            print(f"  writer={update.get('writer') or update.get('module')}")
            print(f"    reason={update.get('reason')}")
            print(f"    profile={update.get('runtime_profile')}")

    def _debug_print_context_retention(self) -> None:
        result = self.memory.last_context_retention_result
        if result is None or result.pruned_count <= 0:
            return
        print("context retention:")
        print(
            f"  before={result.before_count} after={result.after_count} "
            f"pruned={result.pruned_count} max_events={result.max_events}"
        )

    def _debug_print_side_list_retention(self) -> None:
        result = self.memory.last_side_list_retention_result
        if result is None or result.total_pruned <= 0:
            return
        print("side-list retention:")
        print(
            f"  total_before={result.total_before} total_after={result.total_after} "
            f"pruned={result.total_pruned} oldest_event_tick={result.oldest_event_tick}"
        )
        printed = 0
        for name, item in result.per_list.items():
            pruned = int(item.get("pruned_by_tick") or 0) + int(item.get("pruned_by_max_entries") or 0)
            if pruned <= 0:
                continue
            print(
                f"  {name} before={item.get('before')} after={item.get('after')} "
                f"pruned_by_tick={item.get('pruned_by_tick')} "
                f"pruned_by_max={item.get('pruned_by_max_entries')}"
            )
            printed += 1
            if printed >= 6:
                break

    def _debug_print_learnability(self) -> None:
        print("learnability skipped:")
        skipped = self.experience_candidate_builder.debug_skipped_learnability(limit=8)
        if not skipped:
            print("  none")
            return
        for item in skipped:
            reasons = [self.pattern_registry.debug_name(pattern_id) for pattern_id in item.get("reason_patterns", ())]
            core = item.get("core_chain", {})
            decisions = [self.pattern_registry.debug_name(pattern_id) for pattern_id in core.get("decision_patterns", ())]
            effects = [self.pattern_registry.debug_name(pattern_id) for pattern_id in core.get("effect_patterns", ())]
            predictions = [self.pattern_registry.debug_name(pattern_id) for pattern_id in core.get("predicted_patterns", ())]
            print(
                f"  tick={item.get('tick')} outcome={item.get('outcome_id')} "
                f"category={item.get('category')} confidence={item.get('confidence')} "
                f"reasons={reasons}"
            )
            print(f"    core: decisions={decisions} effects={effects} predictions={predictions}")

    def _cleanup_mode_transitions(self, tick: int) -> None:
        for mode_change in self.memory.get_recent_system_mode_changes(4):
            if mode_change.get("_event_tick") != tick:
                continue
            self.mode_transition_cleanup.cleanup(
                tick,
                mode_change.get("from_mode", ""),
                mode_change.get("to_mode", ""),
                self.active_field,
                self.action_candidate_field,
            )

    def _debug_print_mode_action_guard(self, tick: int) -> None:
        print("mode action guard:")
        events = self.mode_action_guard.recent_events(tick)
        if not events:
            print("  none")
            return
        for event in events:
            print(
                f"  {event['event_type']}: {event['debug_name']} "
                f"reason={event['reason']}"
            )

    def _debug_print_mode_transition_cleanup(self, tick: int) -> None:
        print("mode transition cleanup:")
        events = self.mode_transition_cleanup.recent_events(tick)
        if not events:
            print("  none")
            return
        for event in events:
            removed_active = [
                self.mode_transition_cleanup.debug_name(pattern_id)
                for pattern_id in event.get("removed_active_patterns", ())
            ]
            removed_candidates = [
                self.mode_transition_cleanup.debug_name(pattern_id)
                for pattern_id in event.get("removed_action_candidates", ())
            ]
            print(f"  {event.get('from_mode')} -> {event.get('to_mode')}")
            print(f"    removed active patterns: {removed_active}")
            print(f"    removed action candidates: {removed_candidates}")

    def _debug_print_active_field(self) -> None:
        print("active field:")
        snapshot = self.active_field.debug_snapshot()
        if not snapshot:
            print("  none")
            return
        for item in snapshot:
            debug_name = self.pattern_registry.debug_name(item["pattern_id"])
            ttl = f" ttl={item['ttl']}" if item.get("ttl") is not None else ""
            expires = f" expires_at={item['expires_at_tick']}" if item.get("expires_at_tick") is not None else ""
            print(f"  {item['pattern_id']} / {debug_name}: {item['activation']} kind={item['kind']}{ttl}{expires}")

    def _debug_print_evaluation_field(self) -> None:
        print("evaluation field:")
        snapshot = self.evaluation_field.snapshot()
        if not snapshot:
            print("  none")
            return
        for pattern_id, item in snapshot.items():
            print(f"  {self.pattern_registry.debug_name(pattern_id)}:")
            print(
                f"    usefulness={item['usefulness']} harmfulness={item['harmfulness']} "
                f"need={item['need']} want={item['want']} avoid={item['avoid']} "
                f"safety={item['safety']} priority={item['priority']} "
                f"activation={item['activation']} ttl={item['ttl']}"
            )
            sources = ", ".join(item.get("sources", ()))
            scopes = ", ".join(item.get("scopes", ()))
            print(f"    sources={sources} scopes={scopes}")

    def _debug_print_value_feedback_memory_view(self) -> None:
        print("value feedback memory view:")
        records = [
            record
            for record in self.value_feedback_memory_view.snapshot().get("records", [])
            if (
                record.get("positive_count", 0)
                or record.get("negative_count", 0)
                or record.get("mixed_count", 0)
                or record.get("inconclusive_count", 0)
            )
        ]
        if not records:
            print("  no value-feedback records")
            return
        for record in records[:6]:
            print(f"  experience {record.get('experience_id')}:")
            print(f"    positive={record.get('positive_count')} avg={record.get('positive_avg_strength'):.2f}")
            print(f"    negative={record.get('negative_count')} avg={record.get('negative_avg_strength'):.2f}")
            print(
                f"    balance={record.get('value_balance'):.2f} "
                f"confidence={record.get('value_confidence'):.2f} "
                f"risk={record.get('value_risk'):.2f}"
            )
            targets = [
                self.pattern_registry.debug_name(pattern_id)
                for pattern_id in record.get("linked_target_patterns", [])
            ]
            print(f"    targets: {', '.join(targets) if targets else 'none'}")

    def _debug_print_akbsm_association_field(self) -> None:
        print("akbsm association field:")
        snapshot = self.akbsm_association_field.snapshot()
        if not snapshot:
            print("  none")
            return
        for source_pattern_id, associations in snapshot.items():
            print(f"  source: {self.pattern_registry.debug_name(source_pattern_id)}")
            for association in associations:
                associated_id = association.get("associated_pattern_id", "")
                probes = ", ".join(association.get("source_probe_ids", ()))
                print(f"    associated: {self.pattern_registry.debug_name(str(associated_id))}")
                print(
                    f"      relation: {association.get('relation_type')} "
                    f"score: {association.get('score')} "
                    f"distance: {association.get('distance')} "
                    f"ttl: {association.get('ttl')}"
                )
                print(f"      probes: {probes}")

    def _debug_print_decision_cycle_summaries(self) -> None:
        print("decision cycle summaries:")
        summaries = self.memory.get_recent_decision_cycle_summaries(6)
        if not summaries:
            print("  none")
            return
        for summary in summaries[-6:]:
            selected = summary.get("selected", {})
            decision = summary.get("decision_summary", {})
            guard = summary.get("guard_summary", {})
            cycle = summary.get("cycle_summary", {})
            action_name = self.pattern_registry.debug_name(str(selected.get("action_pattern_id", ""))) if isinstance(selected, dict) else ""
            print(f"  {summary.get('decision_cycle_summary_id')}")
            if isinstance(selected, dict):
                print(
                    f"    selected: {action_name} source={selected.get('source')} "
                    f"score={selected.get('final_score')}"
                )
            if isinstance(cycle, dict):
                print(
                    f"    status: {cycle.get('cycle_status')} "
                    f"confidence={cycle.get('cycle_confidence')}"
                )
            if isinstance(decision, dict):
                print(
                    f"    decision: {decision.get('audit_confidence')} "
                    f"margin={decision.get('score_margin')}"
                )
                print(
                    f"    value: {decision.get('value_influence')} "
                    f"{decision.get('value_influence_scope')} "
                    f"delta={decision.get('value_delta')}"
                )
            if isinstance(guard, dict) and guard.get("available"):
                print(f"    guard: {guard.get('guard_effect')} severity={guard.get('severity')}")
            else:
                print("    guard: missing")
            flags = cycle.get("flags", ()) if isinstance(cycle, dict) else ()
            print(f"    flags: {', '.join(flags) if flags else 'none'}")

    def _debug_print_decision_cycle_history(self) -> None:
        print("decision cycle history:")
        snapshot = self.decision_cycle_history_view.snapshot()
        if snapshot is None or snapshot.observed_count <= 0:
            window_size = snapshot.window_size if snapshot is not None else self.decision_cycle_history_view.window_size
            print(f"  window={window_size} observed=0 trend=no_data")
            return
        print(
            f"  window={snapshot.window_size} observed={snapshot.observed_count} "
            f"trend={snapshot.trend_label}"
        )
        print(f"  statuses={_format_counts(snapshot.status_counts)}")
        print(f"  confidence={_format_counts(snapshot.confidence_counts)}")
        print(f"  flags={_format_counts(snapshot.flag_counts)}")
        print(f"  selected_sources={_format_counts(snapshot.selected_source_counts)}")

    def _debug_print_reflection_candidates(self) -> None:
        candidates = self.reflection_candidate_builder.recent_candidates(limit=3)
        if not candidates:
            print("reflection candidates: none")
            return
        print("reflection candidates:")
        for candidate in candidates:
            evidence = candidate.evidence
            print(
                f"  {candidate.reflection_candidate_id} type={candidate.reflection_type} "
                f"severity={candidate.severity} confidence={candidate.confidence:.2f}"
            )
            print(
                f"    trend={candidate.source_trend_label} "
                f"observed={evidence.get('observed_count', 0)}"
            )
            print(
                f"    recommended_future_operation={candidate.recommended_future_operation} "
                f"apply_now={str(candidate.apply_now).lower()}"
            )

    def _debug_print_need_more_evidence_signal(self) -> None:
        signal = self.need_more_evidence_signal
        print("need more evidence signal:")
        if signal is None:
            print("  active=false reason=no_evidence_gap_detected")
            return
        if not signal.active:
            print(f"  active=false reason={signal.reason}")
            return
        print(
            f"  active=true severity={signal.severity} confidence={signal.confidence:.2f} "
            f"reason={signal.reason}"
        )
        print(
            f"  recommended_future_operation={signal.recommended_future_operation} "
            f"apply_now={str(signal.apply_now).lower()}"
        )

    def _debug_print_reflection_review(self) -> None:
        review = self.reflection_review
        print("reflection review:")
        if review is None:
            print("  status=no_reflection_data severity=info confidence=0.00")
            return
        print(
            f"  status={review.review_status} severity={review.severity} "
            f"confidence={review.confidence:.2f} primary_issue={review.primary_issue}"
        )
        if review.summary:
            print(f"  summary={review.summary}")
        print(
            f"  recommended_future_operation={review.recommended_future_operation} "
            f"apply_now={str(review.apply_now).lower()}"
        )

    def _debug_print_policy_pressure(self) -> None:
        pressure = self.policy_pressure
        print("policy pressure:")
        if pressure is None:
            print("  active=false type=no_policy_pressure severity=info confidence=0.00")
            return
        print(
            f"  active={str(pressure.active).lower()} type={pressure.pressure_type} "
            f"severity={pressure.severity} confidence={pressure.confidence:.2f}"
        )
        if pressure.active:
            print(
                f"  source_review={pressure.source_review_status} "
                f"primary_issue={pressure.source_primary_issue}"
            )
            print(
                f"  recommended_future_operation={pressure.recommended_future_operation} "
                f"apply_now={str(pressure.apply_now).lower()}"
            )

    def _debug_print_policy_pressure_review(self) -> None:
        review = self.policy_pressure_review
        print("policy pressure review:")
        if review is None:
            print("  status=no_pressure_data severity=info confidence=0.00 pressure=no_policy_pressure active=false")
            return
        print(
            f"  status={review.review_status} severity={review.severity} "
            f"confidence={review.confidence:.2f} pressure={review.pressure_type} "
            f"active={str(review.pressure_active).lower()}"
        )
        if review.summary:
            print(f"  summary={review.summary}")
        print(
            f"  recommended_future_operation={review.recommended_future_operation} "
            f"apply_now={str(review.apply_now).lower()}"
        )

    def _debug_print_action_candidates(self) -> None:
        print("action candidates:")
        snapshot = self.action_candidate_field.debug_snapshot()
        if not snapshot:
            print("  none")
            return
        for item in snapshot:
            debug_name = self.pattern_registry.debug_name(item["pattern_id"])
            ttl = f" ttl={item['ttl']}" if item.get("ttl") is not None else ""
            expires = f" expires_at={item['expires_at_tick']}" if item.get("expires_at_tick") is not None else ""
            print(
                f"  {item['candidate_id']} {item['pattern_id']} / {debug_name}: "
                f"activation={item['activation']} confidence={item['confidence']} "
                f"urgency={item['urgency']} risk={item['risk']} cost={item['cost']}{ttl}{expires}"
            )
            breakdown = item.get("score_breakdown", {})
            if isinstance(breakdown, dict):
                print(
                    f"    score: base={breakdown.get('base_score')} "
                    f"final={breakdown.get('final_score')} "
                    f"risk_penalty={breakdown.get('risk_penalty')} "
                    f"cost_penalty={breakdown.get('cost_penalty')}"
                )
            source = item.get("source_metadata", {})
            if isinstance(source, dict) and source.get("source") == "expsm_activation":
                print(
                    f"    source=expsm_activation experience_id={source.get('source_experience_id')} "
                    f"activation_id={source.get('source_activation_id')} "
                    f"match_score={source.get('source_match_score')} "
                    f"viability={source.get('source_viability')} "
                    f"effective_confidence={source.get('source_effective_confidence')} "
                    f"repeatability={source.get('source_repeatability')}"
                )
                if isinstance(breakdown, dict):
                    print(
                        f"    memory_score={breakdown.get('memory_score')} "
                        f"expsm_bonus={breakdown.get('expsm_bonus')}"
                    )
            elif isinstance(source, dict) and source.get("source") == "expsm_mechanism_search":
                print(
                    f"    source=expsm_mechanism_search experience_id={source.get('source_experience_id')} "
                    f"mechanism_search_id={source.get('source_mechanism_search_id')} "
                    f"target={self.pattern_registry.debug_name(str(source.get('source_target_pattern_id')))} "
                    f"target_kind={source.get('source_target_kind')} "
                    f"purpose={source.get('source_mechanism_purpose')} "
                    f"mechanism_score={source.get('source_mechanism_score')} "
                    f"base={source.get('source_base_mechanism_score')} "
                    f"adjusted={source.get('source_value_adjusted_score')}"
                )
                print(
                    f"    value_bonus={source.get('source_value_bonus')} "
                    f"penalty={source.get('source_value_penalty')} "
                    f"balance={source.get('source_value_balance')} "
                    f"confidence={source.get('source_value_confidence')} "
                    f"risk={source.get('source_value_risk')}"
                )
                print(
                    f"    value_mode={source.get('source_value_scoring_mode')} "
                    f"target_bonus={source.get('source_target_specific_value_bonus')} "
                    f"target_penalty={source.get('source_target_specific_value_penalty')} "
                    f"generic_bonus={source.get('source_generic_value_bonus')} "
                    f"generic_penalty={source.get('source_generic_value_penalty')} "
                    f"helpful_match={source.get('source_target_helpful_match_score')} "
                    f"risky_match={source.get('source_target_risky_match_score')}"
                )
                if isinstance(breakdown, dict):
                    print(
                        f"    mechanism_source_score={breakdown.get('mechanism_source_score')} "
                        f"final_score={breakdown.get('final_score')}"
                    )

    def _debug_print_candidate_buffer(self) -> None:
        print("candidate buffer groups:")
        snapshot = self.experience_candidate_buffer.debug_snapshot()
        if not snapshot:
            print("  none")
            return
        for item in snapshot[:8]:
            print(
                f"  {item['group_id']} support={item['support_count']} "
                f"avg_confidence={item['avg_confidence']} avg_valence={item['avg_valence']} "
                f"avg_priority={item['avg_priority']} emitted_ready={item['emitted_ready']} "
                f"core_signature={self._debug_signature(item.get('core_signature'))}"
            )

    def _debug_print_draft_store(self) -> None:
        print("draft store:")
        summary = self.draft_commit_gate.debug_summary()
        if not summary:
            print("  none")
            return
        print(
            f"  total_drafts: {summary.get('total_drafts', 0)} "
            f"ready_to_commit: {summary.get('ready_to_commit', 0)} "
            f"wait_more_evidence: {summary.get('wait_more_evidence', 0)} "
            f"rejected: {summary.get('rejected', 0)} "
            f"archived: {summary.get('archived', 0)}"
        )

    def _debug_print_retention_diagnostics(self, tick: int) -> None:
        metrics = self.retention_diagnostics.collect(
            tick=tick,
            memory=self.memory,
            active_field=self.active_field,
            action_candidate_field=self.action_candidate_field,
            evaluation_field=self.evaluation_field,
            akbsm_association_field=self.akbsm_association_field,
            experience_candidate_buffer=self.experience_candidate_buffer,
        )
        for line in format_retention_metrics(metrics):
            print(line)

    def _debug_print_side_list_retention_diagnostics(self, tick: int) -> None:
        metrics = self.retention_diagnostics.collect(
            tick=tick,
            memory=self.memory,
        )
        for line in format_side_list_retention_metrics(metrics):
            print(line)

    def _debug_signature(self, signature: object) -> object:
        if not isinstance(signature, (list, tuple)) or not signature:
            return signature
        debug_items: list[object] = [signature[0]]
        for item in signature[1:]:
            if isinstance(item, (list, tuple)):
                debug_items.append([self.pattern_registry.debug_name(pattern_id) for pattern_id in item])
            else:
                debug_items.append(item)
        return debug_items


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "{}"
    items = ", ".join(f"{key}: {value}" for key, value in sorted(counts.items()))
    return "{" + items + "}"


def demo_run() -> None:
    with tempfile.TemporaryDirectory(prefix="rndem_clc_demo_memory_") as temp_dir:
        demo_memory_root = Path(temp_dir) / "Memory"
        if MEMORY_ROOT.exists():
            shutil.copytree(MEMORY_ROOT, demo_memory_root)
            print(f"Demo memory isolation: using temporary copy at {demo_memory_root}")
        else:
            print("Demo memory isolation: Memory folder missing; using fallback runtime memory")
        runtime = CLCRuntime(demo_memory_root, profile=RuntimeProfile.SAFE_DEMO, memory_is_temporary=True)
        _run_demo_scenarios(runtime)


def _run_demo_scenarios(runtime: CLCRuntime) -> None:
    print("RNDeM CLC Prototype")
    print("Internal flow uses NFP frames, context operations, labels, predictions, tone, and self-generated NFPs.")
    runtime.debug_print_memory_summary()
    print("\nScenario 1: audio periodic pattern")
    audio_values = [0.2, 0.9, 0.25, 0.85, 0.2, 0.9]
    for tick, value in enumerate(audio_values, start=1):
        runtime.feed_audio(tick, {440: value, 880: 0.2, 1200: 0.1})
    print("\nScenario 2: sensor/internal warning")
    runtime.feed_sensor(7, cpu_temp=88.0, memory_usage=0.92, damage_flag=True, resource_pressure=0.8)
    print("\nScenario 3: novelty without risk")
    runtime.feed_image(
        8,
        [
            [(250, 20, 80), (10, 240, 60)],
            [(40, 30, 230), (220, 220, 40)],
        ],
    )
    print("\nScenario 4: memory-overlap image pattern")
    memory_pixels = runtime.build_demo_image_from_memory("1")
    if memory_pixels is None:
        print("No image-like memory pattern available for scenario 4.")
    else:
        runtime.feed_image(9, memory_pixels)
    print("\nScenario 5: outcome and homeostasis follow-up ticks")
    for tick in range(10, 22):
        runtime.feed_audio(tick, {440: 0.25, 880: 0.2, 1200: 0.1})
