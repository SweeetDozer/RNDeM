from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimePhaseEntry:
    phase_id: str
    phase_name: str
    location_hint: str
    modules: tuple[str, ...]
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    queues_context_ops: bool
    can_affect_current_tick_decision: bool
    notes: tuple[str, ...]


RUNTIME_PHASE_MAP: tuple[RuntimePhaseEntry, ...] = (
    RuntimePhaseEntry(
        phase_id="00",
        phase_name="Tick setup and pending input commit",
        location_hint="CLCRuntime._phase_00_input_commit",
        modules=("ContextOpsPool", "ContextMemoryManager", "ContextRetentionPolicy", "SideListRetentionPolicy"),
        reads=("queued preprocessor operations", "ContextRetentionPolicy", "SideListRetentionPolicy"),
        writes=("ContextMemory.events", "ContextMemory side lists", "raw_frames", "retention metrics"),
        queues_context_ops=False,
        can_affect_current_tick_decision=True,
        notes=("External feed_* input is committed before active processing and can affect the current tick.",),
    ),
    RuntimePhaseEntry(
        phase_id="01",
        phase_name="Primary perception, prediction, tone, and thought updates",
        location_hint="CLCRuntime._phase_01_primary_updates",
        modules=(
            "RhythmDLM",
            "NoveltyDLM",
            "RiskDLM",
            "InternalStateDLM",
            "SimpleFutureStatePredictor",
            "NeuromodulationModule",
            "ThoughtGeneratorModule",
            "ContextMemoryManager",
        ),
        reads=("ContextMemory", "ActiveContextField", "PatternStore", "AKBSMAdapter", "ExpSMAdapter"),
        writes=("ContextMemory.labels", "predictions", "neuromodulation_updates", "thought_frames"),
        queues_context_ops=True,
        can_affect_current_tick_decision=True,
        notes=("Each producer is followed by ContextMemoryManager.apply_pending().",),
    ),
    RuntimePhaseEntry(
        phase_id="02",
        phase_name="Active field refresh, decay, ExpSM activation, and consolidation pressure",
        location_hint="CLCRuntime._phase_02_field_activation_and_consolidation_pressure",
        modules=(
            "FieldUpdater",
            "ActiveContextField",
            "ExpSMActivationModule",
            "ConsolidationPressureModule",
            "ExpSMUpdateReviewGate",
            "ContextMemoryManager",
        ),
        reads=("ContextMemory", "ActiveContextField", "SystemState", "ToneState", "ExpSM data"),
        writes=("ActiveContextField", "ContextMemory.expsm_activations", "consolidation_pressures", "expsm_update_reviews"),
        queues_context_ops=True,
        can_affect_current_tick_decision=True,
        notes=("ActionProposer reads the field after these refreshes, so their outputs can affect current selection.",),
    ),
    RuntimePhaseEntry(
        phase_id="03",
        phase_name="Action proposal, candidate decay, decision selection, and guard adjustment",
        location_hint="CLCRuntime._phase_03_action_proposal_and_selection",
        modules=("ActionProposer", "ActionCandidateField", "DecisionSelector", "ModeActionGuard", "action_scoring"),
        reads=("ContextMemory", "ActiveContextField", "ActionCandidateField", "SystemState", "ToneState"),
        writes=("ActionCandidateField", "suppression state", "ContextOpsPool INTERNAL_DECISION when selected"),
        queues_context_ops=True,
        can_affect_current_tick_decision=True,
        notes=("Candidates already in ActionCandidateField and newly proposed candidates are decision material.",),
    ),
    RuntimePhaseEntry(
        phase_id="04",
        phase_name="Decision observers, guard audit, cycle summary, internal action effects",
        location_hint="CLCRuntime._phase_04_decision_audit_and_effects",
        modules=(
            "DecisionAuditObserver",
            "ActionGuardAuditObserver",
            "DecisionCycleSummaryObserver",
            "ExpSMCompetitionObserver",
            "InternalActionExecutor",
            "NeuromodulationModule.run_effects",
            "ThoughtGeneratorModule.run_effects",
            "ContextMemoryManager",
        ),
        reads=("ContextMemory.decisions", "ModeActionGuard audit state", "SystemState", "ActiveContextField"),
        writes=("decision_audits", "action_guard_audits", "decision_cycle_summaries", "effects", "expsm_competition_observations"),
        queues_context_ops=True,
        can_affect_current_tick_decision=False,
        notes=("These artifacts describe or follow the selected decision; they do not reselect within the same tick.",),
    ),
    RuntimePhaseEntry(
        phase_id="05",
        phase_name="Mode transition and consolidation/memory write chain",
        location_hint="CLCRuntime._phase_05_mode_consolidation_memory_chain",
        modules=(
            "SystemModeManager",
            "ModeTransitionCleanup",
            "ConsolidationModeProcessor",
            "MemoryWriteReviewModule",
            "MemoryDraftWriter",
            "DraftCommitGate",
            "ExpSMCommitWriter",
            "ExpSMUpdateWriter",
            "ExpSMAdapter.reload",
            "ValueFeedbackMemoryView.refresh",
            "ContextMemoryManager",
        ),
        reads=("ContextMemory", "ActiveContextField", "SystemState", "MemoryMutationPolicy", "ExpSM drafts"),
        writes=("system_mode_changes", "experience_candidates", "memory_write_reviews", "drafts", "ExpSM when policy allows"),
        queues_context_ops=True,
        can_affect_current_tick_decision=False,
        notes=("Commit/update actions happen after current decision selection and become later-tick context.",),
    ),
    RuntimePhaseEntry(
        phase_id="06",
        phase_name="Outcome, evaluation, AKBSM association, mechanism search, and experience candidates",
        location_hint="CLCRuntime._phase_06_outcome_evaluation_akbsm_mechanism",
        modules=(
            "ExpSMSimilarityObserver",
            "OutcomeEvaluator",
            "ExpSMOutcomeFeedback",
            "EvaluationSignalModule",
            "EvaluationFieldUpdater",
            "EvaluationTargetObserver",
            "AKBSMAssociationProbe",
            "AKBSMAssociationFieldUpdater",
            "ExpSMMechanismSearch",
            "ExperienceCandidateBuilder",
            "ExperienceCandidateBuffer",
            "ContextMemoryManager",
        ),
        reads=("ContextMemory", "ActiveContextField", "EvaluationField", "AKBSMAssociationField", "ExpSM data", "ValueFeedbackMemoryView"),
        writes=("outcomes", "expsm_feedback", "evaluation_signals", "evaluation_targets", "akbsm_association_probes", "expsm_mechanism_searches", "experience_candidates"),
        queues_context_ops=True,
        can_affect_current_tick_decision=False,
        notes=("ExpSMMechanismSearch candidates are emitted after DecisionSelector and are generally next-tick material.",),
    ),
    RuntimePhaseEntry(
        phase_id="07",
        phase_name="Target satisfaction and value feedback chain",
        location_hint="CLCRuntime._phase_07_value_feedback",
        modules=(
            "TargetSatisfactionObserver",
            "ValueFeedbackCandidateBuilder",
            "ValueFeedbackReviewGate",
            "ValueFeedbackUpdateWriter",
            "ExpSMAdapter.reload",
            "ValueFeedbackMemoryView.refresh",
            "ContextMemoryManager",
        ),
        reads=("ContextMemory", "ActiveContextField", "EvaluationField", "SystemState", "MemoryMutationPolicy"),
        writes=("target_satisfaction_observations", "value_feedback_candidates", "value_feedback_reviews", "value_feedback_updates", "ExpSM value_feedback when policy allows"),
        queues_context_ops=True,
        can_affect_current_tick_decision=False,
        notes=("Value feedback updates are after selection and cannot alter the already selected action.",),
    ),
    RuntimePhaseEntry(
        phase_id="08",
        phase_name="Neuromodulation projection over generated side lists",
        location_hint="CLCRuntime._phase_08_neuromodulation_projection",
        modules=("NeuromodulationModule", "ContextMemoryManager"),
        reads=("ContextMemory side lists", "ToneState"),
        writes=("ContextMemory.neuromodulation_updates",),
        queues_context_ops=True,
        can_affect_current_tick_decision=False,
        notes=("Tone updates here affect later phases/debug and future ticks, not current selection.",),
    ),
    RuntimePhaseEntry(
        phase_id="09",
        phase_name="Homeostasis and final field/view refresh",
        location_hint="CLCRuntime._phase_09_final_field_refresh",
        modules=("HomeostasisModule", "EvaluationFieldUpdater", "AKBSMAssociationFieldUpdater", "FieldUpdater", "ContextMemoryManager"),
        reads=("ContextMemory", "ToneState", "ActiveContextField", "EvaluationField", "AKBSMAssociationField"),
        writes=("ContextMemory.module_updates", "EvaluationField", "AKBSMAssociationField", "ActiveContextField"),
        queues_context_ops=True,
        can_affect_current_tick_decision=False,
        notes=("This refresh happens after selection and before diagnostic runtime-only views.",),
    ),
    RuntimePhaseEntry(
        phase_id="10",
        phase_name="Runtime-only reflection and pressure views",
        location_hint="CLCRuntime._phase_10_runtime_observation_views",
        modules=(
            "DecisionCycleHistoryView",
            "ReflectionCandidateBuilder",
            "NeedMoreEvidenceSignalBuilder",
            "ReflectionReviewBuilder",
            "PolicyPressureBuilder",
            "PolicyPressureReviewBuilder",
        ),
        reads=("ContextMemory.decision_cycle_summaries", "runtime-only recent builders"),
        writes=("runtime.decision_cycle_history_view", "runtime.need_more_evidence_signal", "runtime.reflection_review", "runtime.policy_pressure", "runtime.policy_pressure_review"),
        queues_context_ops=False,
        can_affect_current_tick_decision=False,
        notes=("Reflection/pressure chain is observational only and affects no behavior.", "PolicyPressureReview does not influence behavior."),
    ),
    RuntimePhaseEntry(
        phase_id="11",
        phase_name="Debug output",
        location_hint="CLCRuntime._phase_11_debug_output",
        modules=("CLCRuntime debug printers", "ContextMemory.debug_print_state", "RetentionDiagnostics"),
        reads=("runtime state", "ContextMemory", "fields", "recent diagnostic views"),
        writes=("stdout",),
        queues_context_ops=False,
        can_affect_current_tick_decision=False,
        notes=("Debug output is not a control path.",),
    ),
)


def phase_by_id(phase_id: str) -> RuntimePhaseEntry | None:
    for entry in RUNTIME_PHASE_MAP:
        if entry.phase_id == phase_id:
            return entry
    return None
