from typing import Any

from clc.core.pattern_registry import PatternRegistry
from clc.experience.causal_trace import CausalTrace


class LearnabilityFilter:
    """Classifies whether a causal trace should become ordinary experience memory."""

    module_name = "learnability_filter"

    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.reason_patterns = {
            "normal": pattern_registry.id("learnability_normal_action_effect"),
            "maintenance": pattern_registry.id("learnability_skip_maintenance"),
            "mode_management": pattern_registry.id("learnability_skip_mode_management"),
            "consolidation_internal": pattern_registry.id("learnability_skip_consolidation_internal"),
            "homeostasis": pattern_registry.id("learnability_skip_homeostasis"),
            "unknown": pattern_registry.id("learnability_unknown"),
            "skipped": pattern_registry.id("learnability_skipped"),
        }
        self.learnable_actions = {
            pattern_registry.id("action_increase_attention"),
            pattern_registry.id("action_preserve_integrity"),
            pattern_registry.id("action_reduce_load"),
            pattern_registry.id("action_wait_more_data"),
            pattern_registry.id("action_continue_observation"),
            pattern_registry.id("action_inspect_pattern"),
            pattern_registry.id("action_generate_more_thought"),
        }
        self.learnable_effects = {
            pattern_registry.id("state_attention_increased"),
            pattern_registry.id("state_integrity_preservation"),
            pattern_registry.id("state_load_reduced"),
            pattern_registry.id("state_observation_continues"),
            pattern_registry.id("state_pattern_inspection"),
            pattern_registry.id("state_waiting_for_more_data"),
            pattern_registry.id("state_more_thought_requested"),
        }
        self.mode_management_patterns = {
            pattern_registry.id("action_enter_consolidation_mode"),
            pattern_registry.id("action_exit_consolidation_mode"),
            pattern_registry.id("state_consolidation_mode_entered"),
            pattern_registry.id("state_consolidation_mode_exited"),
        }
        self.consolidation_internal_patterns = {
            pattern_registry.id("state_consolidation_processing"),
            pattern_registry.id("state_pending_candidates_reviewed"),
            pattern_registry.id("state_context_load_reduced"),
            pattern_registry.id("state_memory_candidate_created"),
            pattern_registry.id("action_commit_memory_draft"),
            pattern_registry.id("state_memory_draft_commit_requested"),
            pattern_registry.id("committed_draft_observed"),
            pattern_registry.id("committed_draft_strengthened"),
            pattern_registry.id("committed_draft_pending_expsm_update"),
            pattern_registry.id("action_review_committed_memory_update"),
            pattern_registry.id("state_committed_memory_update_review_requested"),
            pattern_registry.id("expsm_update_review"),
            pattern_registry.id("expsm_update_approved_for_update"),
            pattern_registry.id("expsm_update_wait_more_evidence"),
            pattern_registry.id("action_update_committed_expsm_record"),
            pattern_registry.id("state_committed_expsm_update_requested"),
            pattern_registry.id("memory_updated"),
            pattern_registry.id("memory_updated_expsm"),
            pattern_registry.id("memory_update_success"),
            pattern_registry.id("memory_update_metadata_only"),
            pattern_registry.id("memory_update_duplicate_skipped"),
            pattern_registry.id("memory_update_failed"),
            pattern_registry.id("state_memory_updated"),
            pattern_registry.id("state_memory_update_failed"),
            pattern_registry.id("expsm_activation"),
            pattern_registry.id("expsm_record_matched"),
            pattern_registry.id("expsm_recommendation_active"),
            pattern_registry.id("expsm_then_active"),
            pattern_registry.id("expsm_result_expected"),
            pattern_registry.id("expsm_feedback"),
            pattern_registry.id("expsm_feedback_hit"),
            pattern_registry.id("expsm_feedback_partial_hit"),
            pattern_registry.id("expsm_feedback_miss"),
            pattern_registry.id("expsm_feedback_no_feedback"),
            pattern_registry.id("expsm_feedback_success"),
            pattern_registry.id("expsm_feedback_failure"),
            pattern_registry.id("expsm_feedback_record_updated"),
            pattern_registry.id("expsm_similarity_observed"),
            pattern_registry.id("expsm_similar_records_group"),
            pattern_registry.id("expsm_future_competition_candidate"),
            pattern_registry.id("expsm_similarity_high"),
            pattern_registry.id("expsm_similarity_medium"),
            pattern_registry.id("expsm_competition_observed"),
            pattern_registry.id("expsm_competition_selected_record"),
            pattern_registry.id("expsm_competition_alternative_record"),
            pattern_registry.id("expsm_unused_alternative_not_punished"),
            pattern_registry.id("expsm_competition_same_action"),
            pattern_registry.id("expsm_competition_different_actions"),
            pattern_registry.id("draft_commit_ready_to_commit"),
            pattern_registry.id("memory_draft_commit_review"),
            pattern_registry.id("memory_committed"),
            pattern_registry.id("memory_committed_expsm"),
            pattern_registry.id("memory_commit_success"),
            pattern_registry.id("memory_commit_duplicate_skipped"),
            pattern_registry.id("memory_commit_failed"),
            pattern_registry.id("state_memory_committed"),
            pattern_registry.id("state_memory_commit_failed"),
        }
        self.homeostasis_patterns = {
            pattern_registry.id("homeostasis_update"),
            pattern_registry.id("homeostasis_tension_relief"),
            pattern_registry.id("homeostasis_risk_normalization"),
            pattern_registry.id("homeostasis_reduce_load_pressure"),
            pattern_registry.id("homeostasis_preserve_integrity_pressure"),
        }
        self.maintenance_patterns = {
            pattern_registry.id("consolidation_pressure"),
            pattern_registry.id("consolidation_pressure_low"),
            pattern_registry.id("consolidation_pressure_medium"),
            pattern_registry.id("consolidation_pressure_high"),
            pattern_registry.id("system_mode_active"),
            pattern_registry.id("system_mode_consolidation"),
            pattern_registry.id("system_mode_recovery"),
        }

    def classify_trace(self, trace: CausalTrace) -> dict[str, Any]:
        core_patterns = set(trace.decision_patterns + trace.effect_patterns + trace.predicted_patterns)
        if core_patterns & self.mode_management_patterns:
            return self._classification("mode_management", False, "mode_management", 0.95)
        if core_patterns & self.consolidation_internal_patterns:
            return self._classification("consolidation_internal", False, "consolidation_internal", 0.95)
        if core_patterns & self.homeostasis_patterns:
            return self._classification("homeostasis", False, "homeostasis", 0.9)
        if core_patterns & self.maintenance_patterns:
            return self._classification("maintenance", False, "maintenance", 0.9)

        if trace.decision_patterns or trace.effect_patterns:
            if _all_known(trace.decision_patterns, self.learnable_actions) and _all_known(trace.effect_patterns, self.learnable_effects):
                return self._classification("learnable", True, "normal", 0.85)
            return self._classification("unknown", False, "unknown", 0.55)

        if trace.predicted_patterns and not core_patterns & (
            self.mode_management_patterns
            | self.consolidation_internal_patterns
            | self.homeostasis_patterns
            | self.maintenance_patterns
        ):
            return self._classification("learnable", True, "normal", 0.6)

        return self._classification("unknown", False, "unknown", 0.5)

    def is_learnable(self, trace: CausalTrace) -> bool:
        return bool(self.classify_trace(trace)["learnable"])

    def _classification(self, category: str, learnable: bool, reason_key: str, confidence: float) -> dict[str, Any]:
        reason_patterns = [self.reason_patterns[reason_key]]
        if not learnable:
            reason_patterns.append(self.reason_patterns["skipped"])
        return {
            "category": category,
            "learnable": learnable,
            "reason_patterns": reason_patterns,
            "confidence": confidence,
        }


def _all_known(values: tuple[str, ...], known_values: set[str]) -> bool:
    return all(value in known_values for value in values)
