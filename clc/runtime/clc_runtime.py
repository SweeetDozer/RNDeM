from pathlib import Path
import shutil
import tempfile

from clc.action.action_candidate_field import ActionCandidateField
from clc.action.action_proposer import ActionProposer
from clc.action.decision_selector import DecisionSelector
from clc.action.internal_action_executor import InternalActionExecutor
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
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.pattern_registry import PatternRegistry
from clc.dlm.internal_state_dlm import InternalStateDLM
from clc.dlm.novelty_dlm import NoveltyDLM
from clc.dlm.rhythm_dlm import RhythmDLM
from clc.dlm.risk_dlm import RiskDLM
from clc.experience.experience_candidate_buffer import ExperienceCandidateBuffer
from clc.experience.experience_candidate_builder import ExperienceCandidateBuilder
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.expsm_competition_observer import ExpSMCompetitionObserver
from clc.expsm.expsm_outcome_feedback import ExpSMOutcomeFeedback
from clc.expsm.expsm_similarity_observer import ExpSMSimilarityObserver
from clc.field.active_context_field import ActiveContextField
from clc.field.field_updater import FieldUpdater
from clc.homeostasis.homeostasis_module import HomeostasisModule
from clc.neuromodulation.neuromodulation_module import NeuromodulationModule
from clc.outcome.outcome_evaluator import OutcomeEvaluator
from clc.prediction.simple_future_state_predictor import SimpleFutureStatePredictor
from clc.preprocessing.input_preprocessor import InputPreprocessor
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

    def __init__(self, memory_root: Path | str = MEMORY_ROOT) -> None:
        self.id_gen = IdGenerator()
        self.memory_root = Path(memory_root)
        self.pattern_registry = PatternRegistry(self.memory_root / "pattern_manifest.json")
        self.ops_pool = ContextOpsPool()
        self.memory = ContextMemory(self.id_gen, self.pattern_registry)
        self.system_state = SystemState()
        self.active_field = ActiveContextField()
        self.action_candidate_field = ActionCandidateField(self.id_gen)
        self.field_updater = FieldUpdater(self.pattern_registry)
        self.manager = ContextMemoryManager(self.memory, self.ops_pool)
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
        self.internal_action_executor = InternalActionExecutor(self.id_gen, self.pattern_registry)
        self.outcome_evaluator = OutcomeEvaluator(self.id_gen, self.pattern_registry)
        self.experience_candidate_builder = ExperienceCandidateBuilder(self.id_gen, self.pattern_registry)
        self.experience_candidate_buffer = ExperienceCandidateBuffer(self.id_gen, self.pattern_registry)
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
        self.manager.apply_pending()
        active_processing = self.system_state.mode in {"active", "recovery"}
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
        self.action_proposer.propose(tick, self.memory, self.active_field, self.action_candidate_field, self.system_state)
        self.action_candidate_field.decay_all(tick)
        decision = self.decision_selector.select(
            tick,
            self.action_candidate_field,
            self.system_state,
            self.mode_action_guard,
        )
        if decision is not None:
            self.ops_pool.push(decision)
            self.manager.apply_pending()
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
        if active_processing and self.system_state.mode != "consolidation":
            self.ops_pool.extend(self.outcome_evaluator.run(tick, self.memory, self.active_field))
            self.manager.apply_pending()
            self.ops_pool.extend(self.expsm_outcome_feedback.run(tick, self.memory, self.active_field, self.system_state))
            self.manager.apply_pending()
            self._reload_expsm_if_modified(tick)
            self.field_updater.update_from_memory(tick, self.memory, self.active_field)
            self.ops_pool.extend(self.experience_candidate_builder.run(tick, self.memory, self.active_field))
            self.manager.apply_pending()
            self.ops_pool.extend(self.experience_candidate_buffer.run(tick, self.memory, self.active_field))
            self.manager.apply_pending()
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
        self.ops_pool.extend(self.homeostasis.run(tick, self.memory, self.memory.get_current_tone(), self.active_field))
        self.manager.apply_pending()
        self.field_updater.update_from_memory(tick, self.memory, self.active_field)
        self._debug_print_system_state()
        self.memory.debug_print_state(tick)
        self._debug_print_learnability()
        self._debug_print_mode_action_guard(tick)
        self._debug_print_mode_transition_cleanup(tick)
        self._debug_print_candidate_buffer()
        self._debug_print_draft_store()
        self._debug_print_active_field()
        self._debug_print_action_candidates()

    def _reload_expsm_if_modified(self, tick: int) -> None:
        reload_markers = {
            OperationMarker.MEMORY_COMMITTED,
            OperationMarker.MEMORY_UPDATED,
            OperationMarker.EXPSM_FEEDBACK,
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
            print("ExpSM repository reloaded after memory write")

    def _debug_print_system_state(self) -> None:
        print("system state:")
        print(f"  mode: {self.system_state.mode}")
        print(f"  entered_tick: {self.system_state.mode_entered_tick}")
        print(f"  last_consolidation_tick: {self.system_state.last_consolidation_tick}")
        print(f"  depth: {round(self.system_state.consolidation_depth, 3)}")

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


def demo_run() -> None:
    with tempfile.TemporaryDirectory(prefix="rndem_clc_demo_memory_") as temp_dir:
        demo_memory_root = Path(temp_dir) / "Memory"
        if MEMORY_ROOT.exists():
            shutil.copytree(MEMORY_ROOT, demo_memory_root)
            print(f"Demo memory isolation: using temporary copy at {demo_memory_root}")
        else:
            print("Demo memory isolation: Memory folder missing; using fallback runtime memory")
        runtime = CLCRuntime(demo_memory_root)
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
