from clc.context.context_memory import ContextMemory
from clc.core.markers import OperationMarker
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.neuromodulation.tone_state import ToneState


class FieldUpdater:
    """Projects committed events into the active field."""

    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.pattern_registry = pattern_registry
        self._processed_event_ids: set[str] = set()
        self.tone_ids = {
            "tension": pattern_registry.id("tone_tension"),
            "curiosity": pattern_registry.id("tone_curiosity"),
            "risk_sensitivity": pattern_registry.id("tone_risk_sensitivity"),
            "integrity_low": pattern_registry.id("tone_integrity_low"),
            "fatigue": pattern_registry.id("tone_fatigue"),
        }
        self.outcome_ids = {
            "confirmed": pattern_registry.id("outcome_confirmed"),
            "partially_confirmed": pattern_registry.id("outcome_partially_confirmed"),
            "failed": pattern_registry.id("outcome_failed"),
            "expired": pattern_registry.id("outcome_expired"),
            "inconclusive": pattern_registry.id("outcome_inconclusive"),
        }
        self.experience_ids = {
            "positive_candidate": pattern_registry.id("experience_positive_candidate"),
            "negative_candidate": pattern_registry.id("experience_negative_candidate"),
            "weak_candidate": pattern_registry.id("experience_weak_candidate"),
            "pending_consolidation": pattern_registry.id("experience_pending_consolidation"),
        }
        self.consolidation_ids = {
            "ready": pattern_registry.id("consolidation_candidate_ready"),
            "positive": pattern_registry.id("consolidation_positive_candidate"),
            "negative": pattern_registry.id("consolidation_negative_candidate"),
            "pending_memory_write": pattern_registry.id("consolidation_pending_memory_write"),
        }
        self.pressure_ids = {
            "low": pattern_registry.id("consolidation_pressure_low"),
            "medium": pattern_registry.id("consolidation_pressure_medium"),
            "high": pattern_registry.id("consolidation_pressure_high"),
        }
        self.mode_ids = {
            "active": pattern_registry.id("system_mode_active"),
            "consolidation": pattern_registry.id("system_mode_consolidation"),
            "recovery": pattern_registry.id("system_mode_recovery"),
        }
        self.memory_review_kind = pattern_registry.id("memory_write_review")
        self.memory_review_status_ids = {
            "approved_for_expsm": pattern_registry.id("memory_review_approved_for_expsm"),
            "needs_more_support": pattern_registry.id("memory_review_needs_more_support"),
            "rejected_duplicate": pattern_registry.id("memory_review_rejected_duplicate"),
            "rejected_incomplete_core": pattern_registry.id("memory_review_rejected_incomplete_core"),
            "rejected_low_value": pattern_registry.id("memory_review_rejected_low_value"),
            "rejected_unstable": pattern_registry.id("memory_review_rejected_unstable"),
        }
        self.memory_draft_ids = {
            "written": pattern_registry.id("memory_draft_written"),
            "pending_commit": pattern_registry.id("memory_draft_pending_commit"),
            "exp_sm": pattern_registry.id("memory_draft_exp_sm"),
            "success": pattern_registry.id("memory_draft_write_success"),
            "created": pattern_registry.id("memory_draft_created"),
            "merged": pattern_registry.id("memory_draft_merged"),
            "strengthened": pattern_registry.id("memory_draft_strengthened"),
            "duplicate_merged": pattern_registry.id("memory_draft_duplicate_merged"),
        }
        self.draft_commit_review_kind = pattern_registry.id("memory_draft_commit_review")
        self.draft_commit_status_ids = {
            "ready_to_commit": pattern_registry.id("draft_commit_ready_to_commit"),
            "wait_more_evidence": pattern_registry.id("draft_commit_wait_more_evidence"),
            "rejected_low_quality": pattern_registry.id("draft_commit_rejected_low_quality"),
            "rejected_incomplete": pattern_registry.id("draft_commit_rejected_incomplete"),
            "rejected_no_relevant_context": pattern_registry.id("draft_commit_rejected_no_relevant_context"),
            "rejected_technical_context": pattern_registry.id("draft_commit_rejected_technical_context"),
            "archived_duplicate": pattern_registry.id("draft_commit_archived_duplicate"),
        }
        self.memory_commit_ids = {
            "committed": pattern_registry.id("memory_committed"),
            "expsm": pattern_registry.id("memory_committed_expsm"),
            "success": pattern_registry.id("memory_commit_success"),
        }
        self.committed_draft_observation_ids = {
            "observed": pattern_registry.id("committed_draft_observed"),
            "strengthened": pattern_registry.id("committed_draft_strengthened"),
            "pending_update": pattern_registry.id("committed_draft_pending_expsm_update"),
        }
        self.expsm_update_review_ids = {
            "review": pattern_registry.id("expsm_update_review"),
            "approved_for_expsm_update": pattern_registry.id("expsm_update_approved_for_update"),
            "wait_more_post_commit_evidence": pattern_registry.id("expsm_update_wait_more_evidence"),
            "rejected_no_significant_delta": pattern_registry.id("expsm_update_rejected_no_significant_delta"),
            "rejected_invalid_committed_draft": pattern_registry.id("expsm_update_rejected_invalid_committed_draft"),
            "rejected_missing_commit_snapshot": pattern_registry.id("expsm_update_rejected_missing_commit_snapshot"),
        }
        self.memory_update_ids = {
            "updated": pattern_registry.id("memory_updated"),
            "expsm": pattern_registry.id("memory_updated_expsm"),
            "success": pattern_registry.id("memory_update_success"),
            "metadata_only": pattern_registry.id("memory_update_metadata_only"),
        }
        self.expsm_activation_ids = {
            "activation": pattern_registry.id("expsm_activation"),
            "matched": pattern_registry.id("expsm_record_matched"),
            "recommendation": pattern_registry.id("expsm_recommendation_active"),
            "then": pattern_registry.id("expsm_then_active"),
            "result": pattern_registry.id("expsm_result_expected"),
        }
        self.expsm_feedback_ids = {
            "feedback": pattern_registry.id("expsm_feedback"),
            "hit": pattern_registry.id("expsm_feedback_hit"),
            "partial_hit": pattern_registry.id("expsm_feedback_partial_hit"),
            "miss": pattern_registry.id("expsm_feedback_miss"),
            "success": pattern_registry.id("expsm_feedback_success"),
            "failure": pattern_registry.id("expsm_feedback_failure"),
            "updated": pattern_registry.id("expsm_feedback_record_updated"),
        }
        self.expsm_similarity_ids = {
            "observed": pattern_registry.id("expsm_similarity_observed"),
            "group": pattern_registry.id("expsm_similar_records_group"),
            "future_competition": pattern_registry.id("expsm_future_competition_candidate"),
            "high": pattern_registry.id("expsm_similarity_high"),
            "medium": pattern_registry.id("expsm_similarity_medium"),
        }
        self.expsm_competition_ids = {
            "observed": pattern_registry.id("expsm_competition_observed"),
            "selected": pattern_registry.id("expsm_competition_selected_record"),
            "alternative": pattern_registry.id("expsm_competition_alternative_record"),
            "not_punished": pattern_registry.id("expsm_unused_alternative_not_punished"),
            "same_action": pattern_registry.id("expsm_competition_same_action"),
            "different_actions": pattern_registry.id("expsm_competition_different_actions"),
        }
        self.evaluation_ids = {
            "signal": pattern_registry.id("evaluation_signal"),
            "useful": pattern_registry.id("evaluation_useful"),
            "useless": pattern_registry.id("evaluation_useless"),
            "harmful": pattern_registry.id("evaluation_harmful"),
            "safe": pattern_registry.id("evaluation_safe"),
            "needed": pattern_registry.id("evaluation_needed"),
            "wanted": pattern_registry.id("evaluation_wanted"),
            "avoid": pattern_registry.id("evaluation_avoid"),
            "priority_high": pattern_registry.id("evaluation_priority_high"),
            "priority_medium": pattern_registry.id("evaluation_priority_medium"),
            "priority_low": pattern_registry.id("evaluation_priority_low"),
        }
        self.evaluation_target_ids = {
            "observed": pattern_registry.id("evaluation_target_observed"),
            "needed_target": pattern_registry.id("evaluation_needed_target"),
            "wanted_target": pattern_registry.id("evaluation_wanted_target"),
            "useful_target": pattern_registry.id("evaluation_useful_target"),
            "safety_target": pattern_registry.id("evaluation_safety_target"),
            "avoidance_target": pattern_registry.id("evaluation_avoidance_target"),
            "harmful_target": pattern_registry.id("evaluation_harmful_target"),
            "mixed_target": pattern_registry.id("evaluation_mixed_target"),
            "positive_target": pattern_registry.id("evaluation_positive_target"),
        }
        self.akbsm_association_ids = {
            "probe": pattern_registry.id("akbsm_association_probe"),
            "found": pattern_registry.id("akbsm_association_found"),
            "missing": pattern_registry.id("akbsm_association_missing"),
            "associated_pattern": pattern_registry.id("akbsm_associated_pattern"),
            "relation_observed": pattern_registry.id("akbsm_relation_observed"),
            "target_probe": pattern_registry.id("akbsm_target_probe"),
        }
        self.expsm_mechanism_ids = {
            "search": pattern_registry.id("expsm_mechanism_search"),
            "found": pattern_registry.id("expsm_mechanism_found"),
            "missing": pattern_registry.id("expsm_mechanism_missing"),
            "obtain_target": pattern_registry.id("expsm_mechanism_obtain_target"),
            "preserve_target": pattern_registry.id("expsm_mechanism_preserve_target"),
            "avoid_target": pattern_registry.id("expsm_mechanism_avoid_target"),
            "mitigate_harm": pattern_registry.id("expsm_mechanism_mitigate_harm"),
            "unknown_potential": pattern_registry.id("expsm_mechanism_unknown_potential"),
            "candidate": pattern_registry.id("target_mechanism_candidate"),
        }
        self.target_satisfaction_ids = {
            "observer": pattern_registry.id("target_satisfaction_observer"),
            "observed": pattern_registry.id("target_satisfaction_observed"),
            "satisfied": pattern_registry.id("target_satisfied"),
            "partially_satisfied": pattern_registry.id("target_partially_satisfied"),
            "not_satisfied": pattern_registry.id("target_not_satisfied"),
            "worsened": pattern_registry.id("target_worsened"),
            "inconclusive": pattern_registry.id("target_satisfaction_inconclusive"),
            "positive_evidence": pattern_registry.id("target_satisfaction_positive_evidence"),
            "negative_evidence": pattern_registry.id("target_satisfaction_negative_evidence"),
        }
        self.value_feedback_ids = {
            "candidate": pattern_registry.id("value_feedback_candidate"),
            "value_positive_candidate": pattern_registry.id("value_positive_candidate"),
            "value_negative_candidate": pattern_registry.id("value_negative_candidate"),
            "value_mixed_candidate": pattern_registry.id("value_mixed_candidate"),
            "value_inconclusive_candidate": pattern_registry.id("value_inconclusive_candidate"),
            "increase_value_confidence": pattern_registry.id("value_feedback_increase_candidate"),
            "decrease_value_confidence": pattern_registry.id("value_feedback_decrease_candidate"),
            "increase_target_usefulness_link": pattern_registry.id("value_feedback_increase_candidate"),
            "increase_avoidance_warning": pattern_registry.id("value_feedback_decrease_candidate"),
            "request_more_evidence": pattern_registry.id("value_feedback_request_more_evidence"),
            "no_value_update": pattern_registry.id("value_feedback_review_candidate"),
        }
        self.value_feedback_review_ids = {
            "review": pattern_registry.id("value_feedback_review"),
            "ready": pattern_registry.id("value_feedback_review_ready"),
            "wait": pattern_registry.id("value_feedback_review_wait"),
            "reject": pattern_registry.id("value_feedback_review_reject"),
            "archive": pattern_registry.id("value_feedback_review_archive"),
            "ready_for_future_application": pattern_registry.id("value_feedback_ready_for_future_application"),
            "not_ready": pattern_registry.id("value_feedback_not_ready"),
            "strong_positive_value_feedback": pattern_registry.id("value_feedback_review_strong_positive"),
            "strong_negative_value_feedback": pattern_registry.id("value_feedback_review_strong_negative"),
            "weak_evidence_wait": pattern_registry.id("value_feedback_review_weak_evidence"),
            "insufficient_evidence_reject": pattern_registry.id("value_feedback_review_insufficient_evidence"),
            "weak_negative_evidence_wait": pattern_registry.id("value_feedback_review_weak_negative_evidence"),
            "negative_insufficient_evidence_reject": pattern_registry.id("value_feedback_review_negative_insufficient_evidence"),
            "inconclusive_wait": pattern_registry.id("value_feedback_review_inconclusive"),
            "missing_trace_reject": pattern_registry.id("value_feedback_review_insufficient_evidence"),
            "duplicate_archive": pattern_registry.id("value_feedback_review_archive"),
        }
        self.value_feedback_update_ids = {
            "updated": pattern_registry.id("value_feedback_updated"),
            "positive": pattern_registry.id("value_feedback_update_positive"),
            "negative": pattern_registry.id("value_feedback_update_negative"),
            "mixed": pattern_registry.id("value_feedback_update_mixed"),
            "inconclusive": pattern_registry.id("value_feedback_update_inconclusive"),
            "metadata": pattern_registry.id("value_feedback_metadata_updated"),
            "semantic_preserved": pattern_registry.id("value_feedback_semantic_core_preserved"),
            "technical_preserved": pattern_registry.id("value_feedback_technical_feedback_preserved"),
        }
        self.decision_audit_ids = {
            "observed": pattern_registry.id("decision_audit_observed"),
            "clear_win": pattern_registry.id("decision_audit_clear_win"),
            "narrow_win": pattern_registry.id("decision_audit_narrow_win"),
            "tie_like": pattern_registry.id("decision_audit_tie_like"),
            "single_candidate": pattern_registry.id("decision_audit_single_candidate"),
            "promoted": pattern_registry.id("decision_audit_value_promoted"),
            "demoted": pattern_registry.id("decision_audit_value_demoted"),
            "unchanged": pattern_registry.id("decision_audit_value_unchanged"),
            "positive_bonus": pattern_registry.id("decision_audit_value_positive_bonus"),
            "negative_penalty": pattern_registry.id("decision_audit_value_negative_penalty"),
            "none_or_tiny": pattern_registry.id("decision_audit_value_none_or_tiny"),
            "target_specific": pattern_registry.id("decision_audit_target_specific_value"),
            "generic_fallback": pattern_registry.id("decision_audit_generic_value"),
            "no_value": pattern_registry.id("decision_audit_no_value"),
        }
        self.action_guard_audit_ids = {
            "observed": pattern_registry.id("action_guard_audit_observed"),
            "no_blocked_candidates": pattern_registry.id("action_guard_audit_no_blocked_candidates"),
            "blocked_low_score_only": pattern_registry.id("action_guard_audit_blocked_low_score_only"),
            "blocked_high_score_candidate": pattern_registry.id("action_guard_audit_blocked_high_score_candidate"),
            "selected_was_only_allowed_candidate": pattern_registry.id("action_guard_audit_selected_only_allowed"),
            "allowed": pattern_registry.id("action_guard_audit_allowed_candidate"),
            "blocked": pattern_registry.id("action_guard_audit_blocked_candidate"),
            "none": pattern_registry.id("action_guard_audit_severity_none"),
            "low": pattern_registry.id("action_guard_audit_severity_low"),
            "medium": pattern_registry.id("action_guard_audit_severity_medium"),
            "high": pattern_registry.id("action_guard_audit_severity_high"),
        }
        self.decision_cycle_ids = {
            "summary": pattern_registry.id("decision_cycle_summary"),
            "clean_selection": pattern_registry.id("decision_cycle_clean_selection"),
            "value_influenced_selection": pattern_registry.id("decision_cycle_value_influenced_selection"),
            "guard_constrained_selection": pattern_registry.id("decision_cycle_guard_constrained_selection"),
            "uncertain_selection": pattern_registry.id("decision_cycle_uncertain_selection"),
            "risky_or_constrained_selection": pattern_registry.id("decision_cycle_risky_or_constrained_selection"),
            "high": pattern_registry.id("decision_cycle_confidence_high"),
            "medium": pattern_registry.id("decision_cycle_confidence_medium"),
            "low": pattern_registry.id("decision_cycle_confidence_low"),
            "value_promoted_selected": pattern_registry.id("decision_cycle_value_promoted_selected"),
            "value_penalized_selected": pattern_registry.id("decision_cycle_value_penalized_selected"),
            "guard_blocked_high_score": pattern_registry.id("decision_cycle_guard_blocked_high_score"),
            "narrow_decision": pattern_registry.id("decision_cycle_narrow_decision"),
            "tie_like_decision": pattern_registry.id("decision_cycle_tie_like_decision"),
            "single_candidate": pattern_registry.id("decision_cycle_single_candidate"),
            "target_specific_value_used": pattern_registry.id("decision_cycle_target_specific_value_used"),
            "no_value_influence": pattern_registry.id("decision_cycle_no_value_influence"),
            "guard_summary_missing": pattern_registry.id("decision_cycle_guard_summary_missing"),
        }

    def update_from_memory(self, tick: int, memory: ContextMemory, active_field: ActiveContextField) -> None:
        for event in memory.events:
            if event.op_id in self._processed_event_ids:
                continue
            self._processed_event_ids.add(event.op_id)
            payload = dict(event.payload)
            if event.marker == OperationMarker.LABEL:
                self._activate_label(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.PREDICTION:
                self._activate_prediction(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.SELF_GENERATED_THOUGHT:
                frame = payload.get("frame")
                if frame is not None:
                    for pattern_id, amount in frame.activations.items():
                        active_field.activate(pattern_id, amount, event.tick, "thought", event.op_id, frame.decay, frame.ttl, mode="reinforce")
            elif event.marker == OperationMarker.NEUROMODULATION_UPDATE:
                self._activate_tone(event.op_id, event.tick, payload.get("tone_state"), active_field)
                self._activate_homeostasis(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.INTERNAL_DECISION:
                self._activate_decision(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.INTERNAL_ACTION_EFFECT:
                self._activate_effect(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.OUTCOME_EVALUATION:
                self._activate_outcome(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.EXPERIENCE_CANDIDATE:
                self._activate_experience_candidate(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.CONSOLIDATION_CANDIDATE:
                self._activate_consolidation_candidate(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.CONSOLIDATION_PRESSURE:
                self._activate_consolidation_pressure(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.SYSTEM_MODE_CHANGE:
                self._activate_system_mode(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.MEMORY_WRITE_REVIEW:
                self._activate_memory_write_review(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.MEMORY_DRAFT_WRITTEN:
                self._activate_memory_draft_write(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.MEMORY_DRAFT_COMMIT_REVIEW:
                self._activate_memory_draft_commit_review(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.MEMORY_COMMITTED:
                self._activate_memory_commit(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.COMMITTED_DRAFT_OBSERVED:
                self._activate_committed_draft_observation(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.EXPSM_UPDATE_REVIEW:
                self._activate_expsm_update_review(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.MEMORY_UPDATED:
                self._activate_memory_update(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.EXPSM_ACTIVATION:
                self._activate_expsm_activation(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.EXPSM_FEEDBACK:
                self._activate_expsm_feedback(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.EXPSM_SIMILARITY_OBSERVED:
                self._activate_expsm_similarity(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.EXPSM_COMPETITION_OBSERVED:
                self._activate_expsm_competition(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.EVALUATION_SIGNAL:
                self._activate_evaluation_signal(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.EVALUATION_TARGET_OBSERVED:
                self._activate_evaluation_target(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.AKBSM_ASSOCIATION_PROBE:
                self._activate_akbsm_association_probe(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.EXPSM_MECHANISM_SEARCH:
                self._activate_expsm_mechanism_search(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.TARGET_SATISFACTION_OBSERVED:
                self._activate_target_satisfaction(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.VALUE_FEEDBACK_CANDIDATE:
                self._activate_value_feedback_candidate(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.VALUE_FEEDBACK_REVIEW:
                self._activate_value_feedback_review(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.VALUE_FEEDBACK_UPDATED:
                self._activate_value_feedback_update(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.DECISION_AUDIT_OBSERVED:
                self._activate_decision_audit(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.ACTION_GUARD_AUDIT_OBSERVED:
                self._activate_action_guard_audit(event.op_id, event.tick, payload, active_field)
            elif event.marker == OperationMarker.DECISION_CYCLE_SUMMARY:
                self._activate_decision_cycle_summary(event.op_id, event.tick, payload, active_field)

    def _activate_label(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        pattern_id = payload.get("label_kind") or payload.get("label_pattern_id")
        if not pattern_id:
            return
        amount = payload.get("activation", payload.get("risk", payload.get("novelty_score", payload.get("confidence", 0.0))))
        active_field.activate(pattern_id, amount, tick, "label", event_id, payload.get("decay", 0.1), payload.get("ttl"), mode="reinforce")

    def _activate_prediction(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        prediction_id = payload.get("prediction_kind") or payload.get("prediction_pattern_id")
        amount = payload.get("activation", payload.get("probability", 0.0))
        if prediction_id:
            active_field.activate(prediction_id, amount, tick, "prediction", event_id, payload.get("decay", 0.1), payload.get("ttl"), mode="reinforce")
        for pattern_id in payload.get("predicted_patterns", ()):
            active_field.activate(pattern_id, amount, tick, "predicted_pattern", event_id, payload.get("decay", 0.1), payload.get("ttl"), mode="reinforce")

    def _activate_tone(self, event_id: str, tick: int, tone: object, active_field: ActiveContextField) -> None:
        if not isinstance(tone, ToneState):
            return
        active_field.activate(self.tone_ids["tension"], tone.tension, tick, "tone", event_id, 0.08, 3, mode="set")
        active_field.activate(self.tone_ids["curiosity"], tone.curiosity, tick, "tone", event_id, 0.08, 3, mode="set")
        active_field.activate(self.tone_ids["risk_sensitivity"], tone.risk_sensitivity, tick, "tone", event_id, 0.08, 3, mode="set")
        active_field.activate(self.tone_ids["fatigue"], tone.fatigue, tick, "tone", event_id, 0.05, 4, mode="set")
        active_field.activate(self.tone_ids["integrity_low"], 1.0 - tone.integrity, tick, "tone", event_id, 0.08, 3, mode="set")

    def _activate_decision(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        pattern_id = payload.get("decision_pattern_id")
        if not pattern_id:
            return
        active_field.activate(pattern_id, payload.get("activation", 0.0), tick, "decision", event_id, 0.12, payload.get("ttl"), mode="reinforce")

    def _activate_effect(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        pattern_id = payload.get("effect_pattern_id")
        if pattern_id:
            active_field.activate(pattern_id, payload.get("activation", 0.0), tick, "effect", event_id, 0.1, payload.get("ttl"), mode="reinforce")
        for thought_pattern_id in payload.get("generate_thought_patterns", ()):
            active_field.activate(thought_pattern_id, 0.35, tick, "effect_thought_request", event_id, 0.12, payload.get("ttl"), mode="reinforce")
        for secondary_pattern_id in payload.get("secondary_effect_patterns", ()):
            active_field.activate(secondary_pattern_id, payload.get("activation", 0.0) * 0.8, tick, "effect", event_id, 0.1, payload.get("ttl"), mode="reinforce")

    def _activate_outcome(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        status = payload.get("outcome_status")
        pattern_id = payload.get("outcome_pattern_id") or self.outcome_ids.get(status)
        amount = payload.get("activation", payload.get("confidence", 0.0))
        if pattern_id:
            active_field.activate(pattern_id, amount, tick, "outcome", event_id, 0.1, payload.get("ttl"), mode="reinforce")
        for matched_pattern_id in payload.get("matched_patterns", ()):
            active_field.activate(matched_pattern_id, 0.2 * amount, tick, "outcome_match", event_id, 0.12, payload.get("ttl"), mode="reinforce")

    def _activate_homeostasis(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.5)
        ttl = payload.get("ttl", 4)
        for pattern_id in payload.get("homeostasis_patterns", ()):
            active_field.activate(pattern_id, amount, tick, "homeostasis", event_id, 0.1, ttl, mode="reinforce")

    def _activate_experience_candidate(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.5)
        ttl = payload.get("ttl", 8)
        candidate_kind = payload.get("candidate_kind")
        if candidate_kind:
            active_field.activate(candidate_kind, amount, tick, "experience_candidate", event_id, 0.08, ttl, mode="reinforce")
        status_pattern = payload.get("candidate_status_pattern_id") or self.experience_ids.get(payload.get("candidate_status"))
        if status_pattern:
            active_field.activate(status_pattern, amount, tick, "experience_candidate", event_id, 0.08, ttl, mode="reinforce")
        write_status_pattern = payload.get("write_status_pattern_id") or self.experience_ids.get("pending_consolidation")
        if payload.get("write_status") == "pending_consolidation" and write_status_pattern:
            active_field.activate(write_status_pattern, amount * 0.9, tick, "experience_candidate", event_id, 0.08, ttl, mode="reinforce")
        pattern_refs = payload.get("core_chain") or payload.get("pattern_refs", {})
        for key in ("decision_patterns", "effect_patterns", "outcome_patterns"):
            for pattern_id in pattern_refs.get(key, ()):
                active_field.activate(pattern_id, amount * 0.15, tick, "experience_candidate_ref", event_id, 0.12, ttl, mode="reinforce")

    def _activate_consolidation_candidate(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.6)
        ttl = payload.get("ttl", 12)
        candidate_kind = payload.get("candidate_kind")
        if candidate_kind:
            active_field.activate(candidate_kind, amount, tick, "consolidation_candidate", event_id, 0.06, ttl, mode="reinforce")
        active_field.activate(self.consolidation_ids["ready"], amount, tick, "consolidation_candidate", event_id, 0.06, ttl, mode="reinforce")
        if payload.get("write_status") == "pending_memory_consolidation":
            active_field.activate(self.consolidation_ids["pending_memory_write"], amount, tick, "consolidation_candidate", event_id, 0.06, ttl, mode="reinforce")
        avg_valence = payload.get("avg_valence", 0.0)
        if avg_valence > 0.0:
            active_field.activate(self.consolidation_ids["positive"], amount, tick, "consolidation_candidate", event_id, 0.06, ttl, mode="reinforce")
        elif avg_valence < 0.0:
            active_field.activate(self.consolidation_ids["negative"], amount, tick, "consolidation_candidate", event_id, 0.06, ttl, mode="reinforce")
        core_chain = payload.get("core_chain") or payload.get("pattern_refs", {})
        for key in ("decision_patterns", "effect_patterns", "outcome_patterns"):
            for pattern_id in core_chain.get(key, ()):
                active_field.activate(pattern_id, amount * 0.12, tick, "consolidation_candidate_ref", event_id, 0.1, ttl, mode="reinforce")

    def _activate_consolidation_pressure(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", payload.get("pressure_value", 0.0))
        ttl = payload.get("ttl", 6)
        pressure_kind = payload.get("pressure_kind")
        if pressure_kind:
            active_field.activate(pressure_kind, amount, tick, "consolidation_pressure", event_id, 0.08, ttl, mode="set")
        level_pattern = self.pressure_ids.get(payload.get("pressure_level"))
        if level_pattern:
            active_field.activate(level_pattern, amount, tick, "consolidation_pressure", event_id, 0.08, ttl, mode="set")
        for pattern_id in payload.get("pressure_patterns", ()):
            active_field.activate(pattern_id, amount, tick, "consolidation_pressure", event_id, 0.08, ttl, mode="set")

    def _activate_system_mode(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        mode_pattern = payload.get("mode_pattern_id") or self.mode_ids.get(payload.get("to_mode"))
        to_mode = payload.get("to_mode")
        for mode_name, pattern_id in self.mode_ids.items():
            if mode_name != to_mode:
                active_field.suppress(pattern_id, 1.0)
        if mode_pattern:
            active_field.activate(mode_pattern, 1.0, tick, "system_mode", event_id, 0.04, payload.get("ttl", 6), mode="set")
        for pattern_id in payload.get("reason_patterns", ()):
            if pattern_id in self.mode_ids.values():
                continue
            active_field.activate(pattern_id, payload.get("activation", 0.8), tick, "system_mode_reason", event_id, 0.08, payload.get("ttl", 6), mode="max")

    def _activate_memory_write_review(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.6)
        ttl = payload.get("ttl", 14)
        review_kind = payload.get("review_kind") or self.memory_review_kind
        active_field.activate(review_kind, amount, tick, "memory_write_review", event_id, 0.05, ttl, mode="reinforce")
        status_pattern = payload.get("review_status_pattern_id") or self.memory_review_status_ids.get(payload.get("review_status"))
        if status_pattern:
            active_field.activate(status_pattern, amount, tick, "memory_write_review", event_id, 0.05, ttl, mode="reinforce")
        for pattern_id in payload.get("reasons", ()):
            active_field.activate(pattern_id, amount * 0.75, tick, "memory_write_review_reason", event_id, 0.06, ttl, mode="reinforce")

    def _activate_memory_draft_write(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.7)
        ttl = payload.get("ttl", 12)
        draft_kind = payload.get("draft_kind") or self.memory_draft_ids["written"]
        active_field.activate(draft_kind, amount, tick, "memory_draft", event_id, 0.05, ttl, mode="reinforce")
        active_field.activate(self.memory_draft_ids["pending_commit"], amount, tick, "memory_draft", event_id, 0.05, ttl, mode="reinforce")
        active_field.activate(self.memory_draft_ids["exp_sm"], amount, tick, "memory_draft", event_id, 0.05, ttl, mode="reinforce")
        active_field.activate(self.memory_draft_ids["success"], amount, tick, "memory_draft", event_id, 0.05, ttl, mode="reinforce")
        write_kind = payload.get("write_kind")
        if write_kind == "draft_created":
            active_field.activate(self.memory_draft_ids["created"], amount, tick, "memory_draft", event_id, 0.05, ttl, mode="reinforce")
        elif write_kind == "draft_merged":
            active_field.activate(self.memory_draft_ids["merged"], amount, tick, "memory_draft", event_id, 0.05, ttl, mode="reinforce")
            active_field.activate(self.memory_draft_ids["strengthened"], amount, tick, "memory_draft", event_id, 0.05, ttl, mode="reinforce")
            active_field.activate(self.memory_draft_ids["duplicate_merged"], amount, tick, "memory_draft", event_id, 0.05, ttl, mode="reinforce")

    def _activate_memory_draft_commit_review(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.7)
        ttl = payload.get("ttl", 16)
        active_field.activate(self.draft_commit_review_kind, amount, tick, "memory_draft_commit_review", event_id, 0.05, ttl, mode="reinforce")
        status_pattern = payload.get("review_status_pattern_id") or self.draft_commit_status_ids.get(payload.get("review_status"))
        if status_pattern:
            active_field.activate(status_pattern, amount, tick, "memory_draft_commit_review", event_id, 0.05, ttl, mode="reinforce")
        for pattern_id in payload.get("reasons", ()):
            active_field.activate(pattern_id, amount * 0.65, tick, "memory_draft_commit_reason", event_id, 0.06, ttl, mode="reinforce")

    def _activate_memory_commit(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.8)
        ttl = payload.get("ttl", 18)
        commit_kind = payload.get("commit_kind") or self.memory_commit_ids["committed"]
        active_field.activate(commit_kind, amount, tick, "memory_commit", event_id, 0.04, ttl, mode="reinforce")
        active_field.activate(self.memory_commit_ids["expsm"], amount, tick, "memory_commit", event_id, 0.04, ttl, mode="reinforce")
        active_field.activate(self.memory_commit_ids["success"], amount, tick, "memory_commit", event_id, 0.04, ttl, mode="reinforce")

    def _activate_committed_draft_observation(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.7)
        ttl = payload.get("ttl", 12)
        observation_kind = payload.get("observation_kind") or self.committed_draft_observation_ids["observed"]
        active_field.activate(observation_kind, amount, tick, "committed_draft_observation", event_id, 0.05, ttl, mode="reinforce")
        active_field.activate(self.committed_draft_observation_ids["strengthened"], amount, tick, "committed_draft_observation", event_id, 0.05, ttl, mode="reinforce")
        if payload.get("pending_expsm_update"):
            active_field.activate(self.committed_draft_observation_ids["pending_update"], amount, tick, "committed_draft_observation", event_id, 0.05, ttl, mode="reinforce")

    def _activate_expsm_update_review(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.7)
        ttl = payload.get("ttl", 14)
        active_field.activate(self.expsm_update_review_ids["review"], amount, tick, "expsm_update_review", event_id, 0.05, ttl, mode="reinforce")
        status_pattern = payload.get("review_status_pattern_id") or self.expsm_update_review_ids.get(payload.get("review_status"))
        if status_pattern:
            active_field.activate(status_pattern, amount, tick, "expsm_update_review", event_id, 0.05, ttl, mode="reinforce")

    def _activate_memory_update(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.8)
        ttl = payload.get("ttl", 18)
        active_field.activate(payload.get("update_kind") or self.memory_update_ids["updated"], amount, tick, "memory_update", event_id, 0.04, ttl, mode="reinforce")
        active_field.activate(self.memory_update_ids["expsm"], amount, tick, "memory_update", event_id, 0.04, ttl, mode="reinforce")
        active_field.activate(self.memory_update_ids["success"], amount, tick, "memory_update", event_id, 0.04, ttl, mode="reinforce")
        if payload.get("update_mode") == "metadata_only":
            active_field.activate(self.memory_update_ids["metadata_only"], amount, tick, "memory_update", event_id, 0.04, ttl, mode="reinforce")

    def _activate_expsm_activation(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.6)
        ttl = payload.get("ttl", 6)
        active_field.activate(payload.get("activation_kind") or self.expsm_activation_ids["activation"], amount, tick, "expsm_activation", event_id, 0.08, ttl, mode="reinforce")
        active_field.activate(self.expsm_activation_ids["matched"], amount, tick, "expsm_activation", event_id, 0.08, ttl, mode="reinforce")
        active_field.activate(self.expsm_activation_ids["recommendation"], amount, tick, "expsm_activation", event_id, 0.08, ttl, mode="reinforce")
        pattern_amount = amount * 0.65
        for pattern_id in payload.get("then_patterns", ()):
            active_field.activate(self.expsm_activation_ids["then"], pattern_amount, tick, "expsm_then_marker", event_id, 0.1, ttl, mode="reinforce")
            active_field.activate(pattern_id, pattern_amount, tick, "expsm_then", event_id, 0.1, ttl, mode="reinforce")
        for pattern_id in payload.get("recommendation_patterns", ()):
            active_field.activate(pattern_id, pattern_amount, tick, "expsm_recommendation", event_id, 0.1, ttl, mode="reinforce")
        for pattern_id in payload.get("result_patterns", ()):
            active_field.activate(self.expsm_activation_ids["result"], pattern_amount, tick, "expsm_result_marker", event_id, 0.1, ttl, mode="reinforce")
            active_field.activate(pattern_id, pattern_amount, tick, "expsm_expected_result", event_id, 0.1, ttl, mode="reinforce")

    def _activate_expsm_feedback(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.7)
        ttl = payload.get("ttl", 12)
        active_field.activate(payload.get("feedback_kind") or self.expsm_feedback_ids["feedback"], amount, tick, "expsm_feedback", event_id, 0.05, ttl, mode="reinforce")
        active_field.activate(self.expsm_feedback_ids["updated"], amount, tick, "expsm_feedback", event_id, 0.05, ttl, mode="reinforce")
        status = payload.get("feedback_status")
        if status == "hit":
            active_field.activate(self.expsm_feedback_ids["hit"], amount, tick, "expsm_feedback", event_id, 0.05, ttl, mode="reinforce")
            active_field.activate(self.expsm_feedback_ids["success"], amount, tick, "expsm_feedback", event_id, 0.05, ttl, mode="reinforce")
        elif status == "partial_hit":
            active_field.activate(self.expsm_feedback_ids["partial_hit"], amount, tick, "expsm_feedback", event_id, 0.05, ttl, mode="reinforce")
            active_field.activate(self.expsm_feedback_ids["success"], amount, tick, "expsm_feedback", event_id, 0.05, ttl, mode="reinforce")
        elif status == "miss":
            active_field.activate(self.expsm_feedback_ids["miss"], amount, tick, "expsm_feedback", event_id, 0.05, ttl, mode="reinforce")
            active_field.activate(self.expsm_feedback_ids["failure"], amount, tick, "expsm_feedback", event_id, 0.05, ttl, mode="reinforce")

    def _activate_expsm_similarity(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.6)
        ttl = payload.get("ttl", 20)
        active_field.activate(payload.get("observation_kind") or self.expsm_similarity_ids["observed"], amount, tick, "expsm_similarity", event_id, 0.04, ttl, mode="reinforce")
        active_field.activate(self.expsm_similarity_ids["group"], amount, tick, "expsm_similarity", event_id, 0.04, ttl, mode="reinforce")
        active_field.activate(self.expsm_similarity_ids["future_competition"], amount, tick, "expsm_similarity", event_id, 0.04, ttl, mode="reinforce")
        level_id = self.expsm_similarity_ids["high"] if payload.get("max_similarity_score", 0.0) >= 0.70 else self.expsm_similarity_ids["medium"]
        active_field.activate(level_id, amount, tick, "expsm_similarity", event_id, 0.04, ttl, mode="reinforce")

    def _activate_expsm_competition(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.6)
        ttl = payload.get("ttl", 12)
        active_field.activate(payload.get("observation_kind") or self.expsm_competition_ids["observed"], amount, tick, "expsm_competition", event_id, 0.04, ttl, mode="reinforce")
        active_field.activate(self.expsm_competition_ids["selected"], amount, tick, "expsm_competition", event_id, 0.04, ttl, mode="reinforce")
        active_field.activate(self.expsm_competition_ids["alternative"], amount, tick, "expsm_competition", event_id, 0.04, ttl, mode="reinforce")
        active_field.activate(self.expsm_competition_ids["not_punished"], amount, tick, "expsm_competition", event_id, 0.04, ttl, mode="reinforce")
        action_pattern_id = self.expsm_competition_ids["same_action"] if payload.get("same_action_pattern") else self.expsm_competition_ids["different_actions"]
        active_field.activate(action_pattern_id, amount, tick, "expsm_competition", event_id, 0.04, ttl, mode="reinforce")

    def _activate_evaluation_signal(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.6)
        ttl = payload.get("ttl", 10)
        dimensions = payload.get("evaluation_dimensions", {})
        active_field.activate(payload.get("evaluation_kind") or self.evaluation_ids["signal"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
        for pattern_id in payload.get("evaluation_patterns", ()):
            active_field.activate(pattern_id, amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
        if isinstance(dimensions, dict):
            if dimensions.get("usefulness", 0.0) >= 0.5:
                active_field.activate(self.evaluation_ids["useful"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
            if dimensions.get("usefulness", 1.0) <= 0.15 and dimensions.get("priority", 0.0) >= 0.2:
                active_field.activate(self.evaluation_ids["useless"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
            if dimensions.get("harmfulness", 0.0) >= 0.5:
                active_field.activate(self.evaluation_ids["harmful"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
            if dimensions.get("safety", 0.0) >= 0.5:
                active_field.activate(self.evaluation_ids["safe"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
            if dimensions.get("need", 0.0) >= 0.5:
                active_field.activate(self.evaluation_ids["needed"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
            if dimensions.get("want", 0.0) >= 0.5:
                active_field.activate(self.evaluation_ids["wanted"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
            if dimensions.get("avoid", 0.0) >= 0.5:
                active_field.activate(self.evaluation_ids["avoid"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
            priority = dimensions.get("priority", 0.0)
            if priority >= 0.7:
                active_field.activate(self.evaluation_ids["priority_high"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
            elif priority >= 0.4:
                active_field.activate(self.evaluation_ids["priority_medium"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
            else:
                active_field.activate(self.evaluation_ids["priority_low"], amount, tick, "evaluation", event_id, 0.05, ttl, mode="reinforce")
        for target_pattern_id in payload.get("target_patterns", ()):
            active_field.activate(target_pattern_id, amount * 0.45, tick, "evaluated_pattern", event_id, 0.08, ttl, mode="reinforce")

    def _activate_evaluation_target(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.6)
        ttl = payload.get("ttl", 12)
        active_field.activate(
            payload.get("observation_kind") or self.evaluation_target_ids["observed"],
            amount,
            tick,
            "evaluation_target",
            event_id,
            0.05,
            ttl,
            mode="reinforce",
        )
        for role_id in payload.get("target_roles", ()):
            active_field.activate(role_id, amount, tick, "evaluation_target", event_id, 0.05, ttl, mode="reinforce")
        kind = payload.get("target_kind")
        kind_id = payload.get("target_kind_pattern") or self.evaluation_target_ids.get(kind)
        if kind_id:
            active_field.activate(kind_id, amount, tick, "evaluation_target", event_id, 0.05, ttl, mode="reinforce")
        pattern_id = payload.get("pattern_id")
        if pattern_id:
            active_field.activate(
                pattern_id,
                amount * 0.40,
                tick,
                "evaluated_target_pattern",
                event_id,
                0.08,
                ttl,
                mode="reinforce",
            )

    def _activate_akbsm_association_probe(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.55)
        ttl = payload.get("ttl", 10)
        active_field.activate(payload.get("probe_kind") or self.akbsm_association_ids["probe"], amount, tick, "akbsm_association", event_id, 0.05, ttl, mode="reinforce")
        active_field.activate(self.akbsm_association_ids["target_probe"], amount, tick, "akbsm_association", event_id, 0.05, ttl, mode="reinforce")
        associations = payload.get("associated_patterns", ())
        if associations:
            active_field.activate(self.akbsm_association_ids["found"], amount, tick, "akbsm_association", event_id, 0.05, ttl, mode="reinforce")
            active_field.activate(self.akbsm_association_ids["associated_pattern"], amount, tick, "akbsm_association", event_id, 0.05, ttl, mode="reinforce")
            active_field.activate(self.akbsm_association_ids["relation_observed"], amount, tick, "akbsm_association", event_id, 0.05, ttl, mode="reinforce")
            for association in associations:
                if not isinstance(association, dict):
                    continue
                pattern_id = association.get("pattern_id")
                if not pattern_id:
                    continue
                association_amount = float(association.get("score", 0.0) or 0.0) * 0.35
                active_field.activate(pattern_id, association_amount, tick, "akbsm_associated_pattern", event_id, 0.08, min(int(ttl), 8), mode="reinforce")
        else:
            active_field.activate(self.akbsm_association_ids["missing"], amount, tick, "akbsm_association", event_id, 0.05, ttl, mode="reinforce")

    def _activate_expsm_mechanism_search(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.60)
        ttl = payload.get("ttl", 10)
        active_field.activate(payload.get("search_kind") or self.expsm_mechanism_ids["search"], amount, tick, "expsm_mechanism", event_id, 0.05, ttl, mode="reinforce")
        mechanisms = payload.get("mechanisms", ())
        if mechanisms:
            active_field.activate(self.expsm_mechanism_ids["found"], amount, tick, "expsm_mechanism", event_id, 0.05, ttl, mode="reinforce")
            active_field.activate(self.expsm_mechanism_ids["candidate"], amount, tick, "expsm_mechanism", event_id, 0.05, ttl, mode="reinforce")
        else:
            active_field.activate(self.expsm_mechanism_ids["missing"], amount, tick, "expsm_mechanism", event_id, 0.05, ttl, mode="reinforce")
        target_pattern = payload.get("target_pattern_id")
        if target_pattern:
            active_field.activate(target_pattern, amount * 0.30, tick, "expsm_mechanism_target", event_id, 0.08, ttl, mode="reinforce")
        for mechanism in mechanisms:
            if not isinstance(mechanism, dict):
                continue
            score = float(mechanism.get("mechanism_score", 0.0) or 0.0)
            candidate_activation = score * 0.35
            purpose_id = self.expsm_mechanism_ids.get(mechanism.get("mechanism_purpose"))
            if purpose_id:
                active_field.activate(purpose_id, candidate_activation, tick, "expsm_mechanism", event_id, 0.06, ttl, mode="reinforce")
            for pattern_id in mechanism.get("matched_target_patterns", ()):
                active_field.activate(pattern_id, candidate_activation, tick, "expsm_mechanism_match", event_id, 0.08, ttl, mode="reinforce")
            for pattern_id in mechanism.get("matched_associated_patterns", ()):
                active_field.activate(pattern_id, candidate_activation, tick, "expsm_mechanism_match", event_id, 0.08, ttl, mode="reinforce")
            for pattern_id in mechanism.get("then_patterns", ()):
                active_field.activate(pattern_id, candidate_activation, tick, "expsm_mechanism_then", event_id, 0.08, ttl, mode="reinforce")

    def _activate_target_satisfaction(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.55)
        ttl = payload.get("ttl", 10)
        active_field.activate(
            payload.get("observer_kind") or self.target_satisfaction_ids["observer"],
            amount,
            tick,
            "target_satisfaction",
            event_id,
            0.05,
            ttl,
            mode="reinforce",
        )
        active_field.activate(
            payload.get("observation_kind") or self.target_satisfaction_ids["observed"],
            amount,
            tick,
            "target_satisfaction",
            event_id,
            0.05,
            ttl,
            mode="reinforce",
        )
        status_id = payload.get("status_pattern_id") or self.target_satisfaction_ids.get(payload.get("satisfaction_status"))
        if status_id:
            active_field.activate(status_id, amount, tick, "target_satisfaction", event_id, 0.05, ttl, mode="reinforce")
        if payload.get("positive_evidence_pattern_id") or payload.get("evidence", {}).get("positive_dimensions"):
            active_field.activate(self.target_satisfaction_ids["positive_evidence"], amount * 0.75, tick, "target_satisfaction", event_id, 0.06, ttl, mode="reinforce")
        if payload.get("negative_evidence_pattern_id") or payload.get("evidence", {}).get("negative_dimensions"):
            active_field.activate(self.target_satisfaction_ids["negative_evidence"], amount * 0.75, tick, "target_satisfaction", event_id, 0.06, ttl, mode="reinforce")
        target_pattern = payload.get("target_pattern_id")
        if target_pattern:
            target_activation = abs(float(payload.get("satisfaction_score", 0.0) or 0.0)) * 0.25
            active_field.activate(target_pattern, target_activation, tick, "target_satisfaction_target", event_id, 0.08, ttl, mode="reinforce")

    def _activate_value_feedback_candidate(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.55)
        ttl = payload.get("ttl", 10)
        active_field.activate(
            payload.get("candidate_kind") or self.value_feedback_ids["candidate"],
            amount,
            tick,
            "value_feedback_candidate",
            event_id,
            0.05,
            ttl,
            mode="reinforce",
        )
        candidate_type_id = payload.get("candidate_type_pattern_id") or self.value_feedback_ids.get(payload.get("candidate_type"))
        if candidate_type_id:
            active_field.activate(candidate_type_id, amount, tick, "value_feedback_candidate", event_id, 0.05, ttl, mode="reinforce")
        operation_id = payload.get("recommended_operation_pattern_id") or self.value_feedback_ids.get(payload.get("recommended_future_operation"))
        if operation_id:
            active_field.activate(operation_id, amount * 0.85, tick, "value_feedback_candidate", event_id, 0.05, ttl, mode="reinforce")

    def _activate_value_feedback_review(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.50)
        ttl = payload.get("ttl", 12)
        active_field.activate(
            payload.get("review_kind") or self.value_feedback_review_ids["review"],
            amount,
            tick,
            "value_feedback_review",
            event_id,
            0.05,
            ttl,
            mode="reinforce",
        )
        decision_id = payload.get("review_decision_pattern_id") or self.value_feedback_review_ids.get(payload.get("review_decision"))
        if decision_id:
            active_field.activate(decision_id, amount, tick, "value_feedback_review", event_id, 0.05, ttl, mode="reinforce")
        readiness_id = payload.get("readiness_pattern_id") or self.value_feedback_review_ids[
            "ready_for_future_application" if payload.get("ready_for_future_application") else "not_ready"
        ]
        active_field.activate(readiness_id, amount * 0.85, tick, "value_feedback_review", event_id, 0.05, ttl, mode="reinforce")
        reason_id = payload.get("review_reason_pattern_id") or self.value_feedback_review_ids.get(payload.get("review_reason"))
        if reason_id:
            active_field.activate(reason_id, amount * 0.75, tick, "value_feedback_review", event_id, 0.05, ttl, mode="reinforce")

    def _activate_value_feedback_update(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.50)
        ttl = payload.get("ttl", 12)
        active_field.activate(
            payload.get("update_kind") or self.value_feedback_update_ids["updated"],
            amount,
            tick,
            "value_feedback_update",
            event_id,
            0.05,
            ttl,
            mode="reinforce",
        )
        active_field.activate(self.value_feedback_update_ids["metadata"], amount, tick, "value_feedback_update", event_id, 0.05, ttl, mode="reinforce")
        direction_id = self.value_feedback_update_ids.get(_value_feedback_update_bucket(payload))
        if direction_id:
            active_field.activate(direction_id, amount, tick, "value_feedback_update", event_id, 0.05, ttl, mode="reinforce")
        if payload.get("semantic_core_modified") is False:
            active_field.activate(self.value_feedback_update_ids["semantic_preserved"], amount * 0.85, tick, "value_feedback_update", event_id, 0.05, ttl, mode="reinforce")
        if payload.get("technical_feedback_modified") is False:
            active_field.activate(self.value_feedback_update_ids["technical_preserved"], amount * 0.85, tick, "value_feedback_update", event_id, 0.05, ttl, mode="reinforce")

    def _activate_decision_audit(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.45)
        ttl = payload.get("ttl", 8)
        active_field.activate(
            payload.get("audit_kind") or self.decision_audit_ids["observed"],
            amount,
            tick,
            "decision_audit",
            event_id,
            0.06,
            ttl,
            mode="reinforce",
        )
        audit = payload.get("audit", {})
        if not isinstance(audit, dict):
            return
        for key in (
            "audit_confidence_pattern",
            "value_influence_pattern",
            "value_scope_pattern",
            "ranking_effect_pattern",
        ):
            pattern_id = audit.get(key)
            if pattern_id:
                active_field.activate(pattern_id, amount * 0.85, tick, "decision_audit", event_id, 0.06, ttl, mode="reinforce")

    def _activate_action_guard_audit(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.45)
        ttl = payload.get("ttl", 8)
        active_field.activate(
            payload.get("audit_kind") or self.action_guard_audit_ids["observed"],
            amount,
            tick,
            "action_guard_audit",
            event_id,
            0.06,
            ttl,
            mode="reinforce",
        )
        summary = payload.get("summary", {})
        if not isinstance(summary, dict):
            return
        effect_id = summary.get("guard_effect_pattern") or self.action_guard_audit_ids.get(summary.get("guard_effect"))
        severity_id = summary.get("severity_pattern") or self.action_guard_audit_ids.get(summary.get("severity"))
        if effect_id:
            active_field.activate(effect_id, amount * 0.85, tick, "action_guard_audit", event_id, 0.06, ttl, mode="reinforce")
        if severity_id:
            active_field.activate(severity_id, amount * 0.85, tick, "action_guard_audit", event_id, 0.06, ttl, mode="reinforce")
        if payload.get("allowed_candidates"):
            active_field.activate(self.action_guard_audit_ids["allowed"], amount * 0.70, tick, "action_guard_audit", event_id, 0.06, ttl, mode="reinforce")
        if payload.get("blocked_candidates"):
            active_field.activate(self.action_guard_audit_ids["blocked"], amount * 0.70, tick, "action_guard_audit", event_id, 0.06, ttl, mode="reinforce")

    def _activate_decision_cycle_summary(self, event_id: str, tick: int, payload: dict, active_field: ActiveContextField) -> None:
        amount = payload.get("activation", 0.45)
        ttl = payload.get("ttl", 8)
        active_field.activate(
            payload.get("summary_kind") or self.decision_cycle_ids["summary"],
            amount,
            tick,
            "decision_cycle_summary",
            event_id,
            0.06,
            ttl,
            mode="reinforce",
        )
        cycle = payload.get("cycle_summary", {})
        if not isinstance(cycle, dict):
            return
        status_id = cycle.get("cycle_status_pattern_id") or self.decision_cycle_ids.get(cycle.get("cycle_status"))
        confidence_id = cycle.get("cycle_confidence_pattern_id") or self.decision_cycle_ids.get(cycle.get("cycle_confidence"))
        if status_id:
            active_field.activate(status_id, amount * 0.9, tick, "decision_cycle_summary", event_id, 0.06, ttl, mode="reinforce")
        if confidence_id:
            active_field.activate(confidence_id, amount * 0.8, tick, "decision_cycle_summary", event_id, 0.06, ttl, mode="reinforce")
        for pattern_id in cycle.get("flag_pattern_ids", ()):
            active_field.activate(pattern_id, amount * 0.75, tick, "decision_cycle_summary", event_id, 0.06, ttl, mode="reinforce")


def _value_feedback_update_bucket(payload: dict) -> str:
    direction = payload.get("value_direction")
    candidate_type = payload.get("candidate_type")
    if direction == "positive" or candidate_type == "value_positive_candidate":
        return "positive"
    if direction == "negative" or candidate_type == "value_negative_candidate":
        return "negative"
    if direction == "inconclusive" or candidate_type == "value_inconclusive_candidate":
        return "inconclusive"
    return "mixed"
