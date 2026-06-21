from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry


class NeuromodulationModule:
    module_name = "neuromodulation_module"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.novelty_id = pattern_registry.id("novel_activation_pattern")
        self.internal_risk_id = pattern_registry.id("internal_state_risk")
        self.contradiction_id = pattern_registry.id("contradiction_pattern")
        self._last_tick = 0
        self._handled_effect_ids: set[str] = set()
        self._handled_outcome_ids: set[str] = set()
        self._handled_candidate_ids: set[str] = set()
        self._handled_consolidation_candidate_ids: set[str] = set()
        self._handled_memory_review_ids: set[str] = set()
        self._handled_memory_draft_write_ids: set[str] = set()
        self._handled_memory_draft_commit_review_ids: set[str] = set()
        self._handled_memory_commit_ids: set[str] = set()
        self._handled_committed_draft_observation_ids: set[str] = set()
        self._handled_expsm_update_review_ids: set[str] = set()
        self._handled_memory_update_ids: set[str] = set()
        self._handled_expsm_activation_ids: set[str] = set()
        self._handled_expsm_feedback_ids: set[str] = set()
        self._handled_expsm_similarity_ids: set[str] = set()
        self._handled_expsm_competition_ids: set[str] = set()
        self._handled_evaluation_signal_ids: set[str] = set()
        self._handled_evaluation_target_ids: set[str] = set()
        self._handled_akbsm_association_probe_ids: set[str] = set()
        self._handled_expsm_mechanism_search_ids: set[str] = set()
        self._handled_target_satisfaction_ids: set[str] = set()
        self._handled_value_feedback_candidate_ids: set[str] = set()
        self._handled_value_feedback_review_ids: set[str] = set()
        self._handled_value_feedback_update_ids: set[str] = set()
        self._handled_decision_audit_ids: set[str] = set()
        self._handled_action_guard_audit_ids: set[str] = set()
        self._handled_decision_cycle_summary_ids: set[str] = set()

    def run(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        if tick == self._last_tick:
            return []
        self._last_tick = tick
        tone = memory.get_current_tone()
        labels = [label for label in memory.recent_labels(10) if label.get("_event_tick") == tick]
        predictions = [prediction for prediction in memory.recent_predictions(5) if prediction.get("_event_tick") == tick]
        outcomes = [
            outcome
            for outcome in memory.get_recent_outcomes(12)
            if outcome.get("_event_tick", tick) < tick and outcome.get("outcome_id") not in self._handled_outcome_ids
        ]
        risk = max([label.get("risk", 0.0) for label in labels] + [0.0])
        novelty = max([label.get("confidence", 0.0) for label in labels if label.get("label_pattern_id") == self.novelty_id] + [0.0])
        internal_risk = max([label.get("risk", 0.0) for label in labels if label.get("label_pattern_id") == self.internal_risk_id] + [0.0])
        contradiction = any(label.get("label_pattern_id") == self.contradiction_id for label in labels)
        delta = {
            "fatigue": 0.02,
            "satisfaction": -0.03,
            "pain": -0.02,
        }
        if risk >= 0.6:
            delta["tension"] = delta.get("tension", 0.0) + 0.18
            delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.12
        elif risk < 0.35:
            delta["tension"] = delta.get("tension", 0.0) - 0.04
        if novelty >= 0.55 and risk < 0.4:
            delta["curiosity"] = delta.get("curiosity", 0.0) + 0.2
        if contradiction:
            delta["tension"] = delta.get("tension", 0.0) + 0.2
            delta["stability"] = delta.get("stability", 0.0) - 0.12
        if internal_risk >= 0.6:
            delta["integrity"] = delta.get("integrity", 0.0) - 0.12
            delta["tension"] = delta.get("tension", 0.0) + 0.18
        for prediction in predictions:
            for key, value in prediction.get("expected_tone_delta", {}).items():
                delta[key] = delta.get(key, 0.0) + (value * prediction.get("probability", 0.0))
        handled_outcome_ids: list[str] = []
        for outcome in outcomes:
            outcome_id = outcome.get("outcome_id")
            if not outcome_id:
                continue
            handled_outcome_ids.append(outcome_id)
            self._handled_outcome_ids.add(outcome_id)
            for key, value in outcome.get("tone_delta", {}).items():
                delta[key] = delta.get(key, 0.0) + float(value)
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_outcome_ids": handled_outcome_ids,
            "based_on_recent_label_count": len(labels),
            "based_on_recent_prediction_count": len(predictions),
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_effects(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        effects = [
            effect
            for effect in memory.get_recent_effects(8)
            if effect.get("_event_tick") == tick and effect.get("effect_id") not in self._handled_effect_ids
        ]
        if not effects:
            return []
        tone = memory.get_current_tone()
        delta: dict[str, float] = {}
        handled: list[str] = []
        for effect in effects:
            handled.append(effect["effect_id"])
            self._handled_effect_ids.add(effect["effect_id"])
            for key, value in effect.get("tone_delta", {}).items():
                delta[key] = delta.get(key, 0.0) + float(value)
        if not delta:
            return []
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_effect_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_outcomes(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        outcomes = [
            outcome
            for outcome in memory.get_recent_outcomes(12)
            if outcome.get("_event_tick") == tick and outcome.get("outcome_id") not in self._handled_outcome_ids
        ]
        if not outcomes:
            return []
        tone = memory.get_current_tone()
        delta: dict[str, float] = {}
        handled: list[str] = []
        for outcome in outcomes:
            outcome_id = outcome.get("outcome_id")
            if not outcome_id:
                continue
            handled.append(outcome_id)
            self._handled_outcome_ids.add(outcome_id)
            for key, value in outcome.get("tone_delta", {}).items():
                delta[key] = delta.get(key, 0.0) + float(value)
        if not delta:
            return []
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_outcome_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_candidates(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        candidates = [
            candidate
            for candidate in memory.get_recent_experience_candidates(12)
            if candidate.get("_event_tick") == tick and candidate.get("candidate_id") not in self._handled_candidate_ids
        ]
        if not candidates:
            return []
        tone = memory.get_current_tone()
        delta: dict[str, float] = {}
        handled: list[str] = []
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id")
            if not candidate_id:
                continue
            handled.append(candidate_id)
            self._handled_candidate_ids.add(candidate_id)
            status = candidate.get("candidate_status")
            activation = float(candidate.get("activation", 0.5))
            if status == "positive_candidate":
                delta["satisfaction"] = delta.get("satisfaction", 0.0) + 0.02 * activation
                delta["stability"] = delta.get("stability", 0.0) + 0.01 * activation
            elif status == "negative_candidate":
                delta["pain"] = delta.get("pain", 0.0) + 0.02 * activation
                delta["tension"] = delta.get("tension", 0.0) + 0.015 * activation
                delta["stability"] = delta.get("stability", 0.0) - 0.01 * activation
            elif status == "weak_candidate":
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.01 * activation
                delta["tension"] = delta.get("tension", 0.0) + 0.005 * activation
        if not delta:
            return []
        delta = _cap_candidate_delta(delta)
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_experience_candidate_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_consolidation_candidates(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        candidates = [
            candidate
            for candidate in memory.get_recent_consolidation_candidates(12)
            if candidate.get("_event_tick") == tick
            and candidate.get("consolidation_candidate_id") not in self._handled_consolidation_candidate_ids
        ]
        if not candidates:
            return []
        tone = memory.get_current_tone()
        delta: dict[str, float] = {}
        handled: list[str] = []
        for candidate in candidates:
            candidate_id = candidate.get("consolidation_candidate_id")
            if not candidate_id:
                continue
            handled.append(candidate_id)
            self._handled_consolidation_candidate_ids.add(candidate_id)
            activation = float(candidate.get("activation", 0.6))
            avg_valence = float(candidate.get("avg_valence", 0.0))
            if avg_valence >= 0.0:
                delta["satisfaction"] = delta.get("satisfaction", 0.0) + 0.015 * activation
                delta["stability"] = delta.get("stability", 0.0) + 0.005 * activation
            else:
                delta["pain"] = delta.get("pain", 0.0) + 0.01 * activation
                delta["tension"] = delta.get("tension", 0.0) + 0.01 * activation
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.005 * activation
        if not delta:
            return []
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_consolidation_candidate_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_memory_write_reviews(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        reviews = [
            review
            for review in memory.get_recent_memory_write_reviews(12)
            if review.get("_event_tick") == tick and review.get("review_id") not in self._handled_memory_review_ids
        ]
        if not reviews:
            return []
        tone = memory.get_current_tone()
        delta: dict[str, float] = {}
        handled: list[str] = []
        for review in reviews:
            review_id = review.get("review_id")
            if not review_id:
                continue
            handled.append(review_id)
            self._handled_memory_review_ids.add(review_id)
            status = review.get("review_status")
            if status == "approved_for_expsm":
                delta["satisfaction"] = delta.get("satisfaction", 0.0) + 0.015
                delta["stability"] = delta.get("stability", 0.0) + 0.01
                delta["fatigue"] = delta.get("fatigue", 0.0) - 0.01
            elif status == "needs_more_support":
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.005
                delta["tension"] = delta.get("tension", 0.0) + 0.003
            elif status in {"rejected_low_value", "rejected_duplicate"}:
                delta["satisfaction"] = delta.get("satisfaction", 0.0) - 0.003
                delta["fatigue"] = delta.get("fatigue", 0.0) - 0.005
            elif status in {"rejected_incomplete_core", "rejected_unstable"}:
                delta["tension"] = delta.get("tension", 0.0) + 0.005
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.005
        if not delta:
            return []
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_memory_write_review_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_memory_draft_writes(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        draft_writes = [
            draft_write
            for draft_write in memory.get_recent_memory_draft_writes(12)
            if draft_write.get("_event_tick") == tick
            and draft_write.get("draft_write_id") not in self._handled_memory_draft_write_ids
        ]
        if not draft_writes:
            return []
        tone = memory.get_current_tone()
        handled: list[str] = []
        created_count = 0
        merged_count = 0
        for draft_write in draft_writes:
            draft_write_id = draft_write.get("draft_write_id")
            if not draft_write_id:
                continue
            handled.append(draft_write_id)
            self._handled_memory_draft_write_ids.add(draft_write_id)
            if draft_write.get("write_kind") == "draft_merged":
                merged_count += 1
            else:
                created_count += 1
        if not handled:
            return []
        delta = {
            "satisfaction": 0.02 * created_count + 0.012 * merged_count,
            "stability": 0.01 * created_count + 0.015 * merged_count,
            "fatigue": -0.015 * created_count - 0.01 * merged_count,
        }
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_memory_draft_write_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_memory_draft_commit_reviews(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        reviews = [
            review
            for review in memory.get_recent_memory_draft_commit_reviews(12)
            if review.get("_event_tick") == tick
            and review.get("commit_review_id") not in self._handled_memory_draft_commit_review_ids
        ]
        if not reviews:
            return []
        tone = memory.get_current_tone()
        delta: dict[str, float] = {}
        handled: list[str] = []
        for review in reviews:
            review_id = review.get("commit_review_id")
            if not review_id:
                continue
            handled.append(review_id)
            self._handled_memory_draft_commit_review_ids.add(review_id)
            status = review.get("review_status")
            if status == "ready_to_commit":
                delta["satisfaction"] = delta.get("satisfaction", 0.0) + 0.018
                delta["stability"] = delta.get("stability", 0.0) + 0.015
                delta["fatigue"] = delta.get("fatigue", 0.0) - 0.01
            elif status == "wait_more_evidence":
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.006
                delta["tension"] = delta.get("tension", 0.0) + 0.002
            elif status in {"rejected_low_quality", "rejected_incomplete", "rejected_no_relevant_context", "rejected_technical_context"}:
                delta["tension"] = delta.get("tension", 0.0) + 0.004
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.004
            elif status == "archived_duplicate":
                delta["stability"] = delta.get("stability", 0.0) + 0.006
                delta["fatigue"] = delta.get("fatigue", 0.0) - 0.004
        if not delta:
            return []
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_memory_draft_commit_review_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_memory_commits(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        commits = [
            commit
            for commit in memory.get_recent_memory_commits(8)
            if commit.get("_event_tick") == tick and commit.get("memory_commit_id") not in self._handled_memory_commit_ids
        ]
        if not commits:
            return []
        handled: list[str] = []
        for commit in commits:
            commit_id = commit.get("memory_commit_id")
            if not commit_id:
                continue
            handled.append(commit_id)
            self._handled_memory_commit_ids.add(commit_id)
        if not handled:
            return []
        tone = memory.get_current_tone()
        delta = {
            "satisfaction": 0.025,
            "stability": 0.02,
            "fatigue": -0.02,
        }
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_memory_commit_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_committed_draft_observations(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        observations = [
            observation
            for observation in memory.get_recent_committed_draft_observations(12)
            if observation.get("_event_tick") == tick
            and observation.get("observation_id") not in self._handled_committed_draft_observation_ids
        ]
        if not observations:
            return []
        handled: list[str] = []
        for observation in observations:
            observation_id = observation.get("observation_id")
            if not observation_id:
                continue
            handled.append(observation_id)
            self._handled_committed_draft_observation_ids.add(observation_id)
        if not handled:
            return []
        count = len(handled)
        tone = memory.get_current_tone()
        delta = {
            "stability": 0.012 * count,
            "satisfaction": 0.008 * count,
            "fatigue": -0.004 * count,
        }
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_committed_draft_observation_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_expsm_update_reviews(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        reviews = [
            review
            for review in memory.get_recent_expsm_update_reviews(12)
            if review.get("_event_tick") == tick and review.get("update_review_id") not in self._handled_expsm_update_review_ids
        ]
        if not reviews:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for review in reviews:
            review_id = review.get("update_review_id")
            if not review_id:
                continue
            handled.append(review_id)
            self._handled_expsm_update_review_ids.add(review_id)
            status = review.get("review_status")
            if status == "approved_for_expsm_update":
                delta["stability"] = delta.get("stability", 0.0) + 0.01
                delta["satisfaction"] = delta.get("satisfaction", 0.0) + 0.008
                delta["fatigue"] = delta.get("fatigue", 0.0) - 0.004
            elif status == "wait_more_post_commit_evidence":
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.004
            elif status == "rejected_no_significant_delta":
                delta["stability"] = delta.get("stability", 0.0) + 0.004
                delta["fatigue"] = delta.get("fatigue", 0.0) - 0.002
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_expsm_update_review_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_memory_updates(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        updates = [
            update
            for update in memory.get_recent_memory_updates(8)
            if update.get("_event_tick") == tick and update.get("memory_update_id") not in self._handled_memory_update_ids
        ]
        if not updates:
            return []
        handled: list[str] = []
        for update in updates:
            update_id = update.get("memory_update_id")
            if not update_id:
                continue
            handled.append(update_id)
            self._handled_memory_update_ids.add(update_id)
        if not handled:
            return []
        tone = memory.get_current_tone()
        delta = {
            "satisfaction": 0.014 * len(handled),
            "stability": 0.018 * len(handled),
            "fatigue": -0.008 * len(handled),
        }
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_memory_update_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_expsm_activations(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        activations = [
            activation
            for activation in memory.get_recent_expsm_activations(8)
            if activation.get("_event_tick") == tick and activation.get("activation_id") not in self._handled_expsm_activation_ids
        ]
        if not activations:
            return []
        handled: list[str] = []
        for activation in activations:
            activation_id = activation.get("activation_id")
            if not activation_id:
                continue
            handled.append(activation_id)
            self._handled_expsm_activation_ids.add(activation_id)
        if not handled:
            return []
        tone = memory.get_current_tone()
        delta = {
            "stability": 0.006 * len(handled),
            "curiosity": -0.003 * len(handled),
        }
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_expsm_activation_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_expsm_feedback(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        feedback_events = [
            feedback
            for feedback in memory.get_recent_expsm_feedback(8)
            if feedback.get("_event_tick") == tick and feedback.get("feedback_id") not in self._handled_expsm_feedback_ids
        ]
        if not feedback_events:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for feedback in feedback_events:
            feedback_id = feedback.get("feedback_id")
            if not feedback_id:
                continue
            handled.append(feedback_id)
            self._handled_expsm_feedback_ids.add(feedback_id)
            status = feedback.get("feedback_status")
            if status == "hit":
                delta["satisfaction"] = delta.get("satisfaction", 0.0) + 0.018
                delta["stability"] = delta.get("stability", 0.0) + 0.012
                delta["tension"] = delta.get("tension", 0.0) - 0.006
            elif status == "partial_hit":
                delta["satisfaction"] = delta.get("satisfaction", 0.0) + 0.008
                delta["stability"] = delta.get("stability", 0.0) + 0.004
            elif status == "miss":
                delta["pain"] = delta.get("pain", 0.0) + 0.015
                delta["tension"] = delta.get("tension", 0.0) + 0.012
                delta["stability"] = delta.get("stability", 0.0) - 0.008
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_expsm_feedback_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_expsm_similarity_observations(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        observations = [
            observation
            for observation in memory.get_recent_expsm_similarity_observations(8)
            if observation.get("_event_tick") == tick
            and observation.get("similarity_observation_id") not in self._handled_expsm_similarity_ids
        ]
        if not observations:
            return []
        handled: list[str] = []
        for observation in observations:
            observation_id = observation.get("similarity_observation_id")
            if not observation_id:
                continue
            handled.append(observation_id)
            self._handled_expsm_similarity_ids.add(observation_id)
        if not handled:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(curiosity=0.006 * len(handled), tension=0.002 * len(handled))
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {
                "curiosity": round(0.006 * len(handled), 3),
                "tension": round(0.002 * len(handled), 3),
            },
            "based_on_expsm_similarity_observation_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_expsm_competition_observations(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        observations = [
            observation
            for observation in memory.get_recent_expsm_competition_observations(8)
            if observation.get("_event_tick") == tick
            and observation.get("competition_observation_id") not in self._handled_expsm_competition_ids
        ]
        if not observations:
            return []
        handled: list[str] = []
        for observation in observations:
            observation_id = observation.get("competition_observation_id")
            if not observation_id:
                continue
            handled.append(observation_id)
            self._handled_expsm_competition_ids.add(observation_id)
        if not handled:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(curiosity=0.006 * len(handled), tension=0.003 * len(handled))
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {
                "curiosity": round(0.006 * len(handled), 3),
                "tension": round(0.003 * len(handled), 3),
            },
            "based_on_expsm_competition_observation_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_evaluation_signals(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        signals = [
            signal
            for signal in memory.get_recent_evaluation_signals(8)
            if signal.get("_event_tick") == tick
            and signal.get("evaluation_id") not in self._handled_evaluation_signal_ids
        ]
        if not signals:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for signal in signals:
            evaluation_id = signal.get("evaluation_id")
            if not evaluation_id:
                continue
            handled.append(evaluation_id)
            self._handled_evaluation_signal_ids.add(evaluation_id)
            dimensions = signal.get("evaluation_dimensions", {})
            if not isinstance(dimensions, dict):
                continue
            if dimensions.get("usefulness", 0.0) >= 0.5 or dimensions.get("safety", 0.0) >= 0.5:
                delta["stability"] = delta.get("stability", 0.0) + 0.006
                delta["satisfaction"] = delta.get("satisfaction", 0.0) + 0.006
            if dimensions.get("harmfulness", 0.0) >= 0.5 or dimensions.get("avoid", 0.0) >= 0.5:
                delta["tension"] = delta.get("tension", 0.0) + 0.008
                delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.006
            if dimensions.get("need", 0.0) >= 0.5 or dimensions.get("priority", 0.0) >= 0.7:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.004
                delta["tension"] = delta.get("tension", 0.0) + 0.003
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_evaluation_signal_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_evaluation_targets(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        targets = [
            target
            for target in memory.get_recent_evaluation_targets(8)
            if target.get("_event_tick") == tick
            and target.get("target_observation_id") not in self._handled_evaluation_target_ids
        ]
        if not targets:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for target in targets:
            target_id = target.get("target_observation_id")
            if not target_id:
                continue
            handled.append(target_id)
            self._handled_evaluation_target_ids.add(target_id)
            target_kind = target.get("target_kind")
            role_names = set(target.get("target_role_names", ()))
            if target_kind == "mixed_target":
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.003
                delta["tension"] = delta.get("tension", 0.0) + 0.003
            elif target_kind == "avoidance_target" or role_names & {"avoidance_target", "harmful_target"}:
                delta["tension"] = delta.get("tension", 0.0) + 0.006
                delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.006
            elif role_names & {"needed_target", "wanted_target", "useful_target", "safety_target"}:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.004
                delta["stability"] = delta.get("stability", 0.0) + 0.004
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_evaluation_target_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_akbsm_association_probes(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        probes = [
            probe
            for probe in memory.get_recent_akbsm_association_probes(8)
            if probe.get("_event_tick") == tick
            and probe.get("probe_id") not in self._handled_akbsm_association_probe_ids
        ]
        if not probes:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for probe in probes:
            probe_id = probe.get("probe_id")
            if not probe_id:
                continue
            handled.append(probe_id)
            self._handled_akbsm_association_probe_ids.add(probe_id)
            if int(probe.get("associations_found", 0) or 0) > 0:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.006
                delta["stability"] = delta.get("stability", 0.0) + 0.002
            else:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.003
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_akbsm_association_probe_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_expsm_mechanism_searches(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        searches = [
            search
            for search in memory.get_recent_expsm_mechanism_searches(8)
            if search.get("_event_tick") == tick
            and search.get("mechanism_search_id") not in self._handled_expsm_mechanism_search_ids
        ]
        if not searches:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for search in searches:
            search_id = search.get("mechanism_search_id")
            if not search_id:
                continue
            handled.append(search_id)
            self._handled_expsm_mechanism_search_ids.add(search_id)
            mechanisms = search.get("mechanisms", ())
            if mechanisms:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.006
                delta["stability"] = delta.get("stability", 0.0) + 0.003
            if any(
                isinstance(mechanism, dict)
                and mechanism.get("mechanism_purpose") in {"avoid_target", "mitigate_harm"}
                for mechanism in mechanisms
            ):
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.004
                delta["tension"] = delta.get("tension", 0.0) - 0.002
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_expsm_mechanism_search_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_target_satisfaction_observations(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        observations = [
            observation
            for observation in memory.get_recent_target_satisfaction_observations(8)
            if observation.get("_event_tick") == tick
            and observation.get("target_satisfaction_id") not in self._handled_target_satisfaction_ids
        ]
        if not observations:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for observation in observations:
            observation_id = observation.get("target_satisfaction_id")
            if not observation_id:
                continue
            handled.append(observation_id)
            self._handled_target_satisfaction_ids.add(observation_id)
            status = observation.get("satisfaction_status")
            if status in {"satisfied", "partially_satisfied"}:
                delta["stability"] = delta.get("stability", 0.0) + 0.006
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.002
                delta["tension"] = delta.get("tension", 0.0) - 0.003
            elif status in {"not_satisfied", "worsened"}:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.004
                delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.005
                delta["tension"] = delta.get("tension", 0.0) + 0.004
            elif status == "inconclusive":
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.002
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_target_satisfaction_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_value_feedback_candidates(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        candidates = [
            candidate
            for candidate in memory.get_recent_value_feedback_candidates(8)
            if candidate.get("_event_tick") == tick
            and candidate.get("value_feedback_candidate_id") not in self._handled_value_feedback_candidate_ids
        ]
        if not candidates:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for candidate in candidates:
            candidate_id = candidate.get("value_feedback_candidate_id")
            if not candidate_id:
                continue
            handled.append(candidate_id)
            self._handled_value_feedback_candidate_ids.add(candidate_id)
            candidate_type = candidate.get("candidate_type")
            direction = candidate.get("value_direction")
            if candidate_type == "value_positive_candidate" or direction == "positive":
                delta["stability"] = delta.get("stability", 0.0) + 0.003
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.001
            elif candidate_type == "value_negative_candidate" or direction == "negative":
                delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.003
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.002
            else:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.002
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_value_feedback_candidate_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_value_feedback_reviews(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        reviews = [
            review
            for review in memory.get_recent_value_feedback_reviews(8)
            if review.get("_event_tick") == tick
            and review.get("value_feedback_review_id") not in self._handled_value_feedback_review_ids
        ]
        if not reviews:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for review in reviews:
            review_id = review.get("value_feedback_review_id")
            if not review_id:
                continue
            handled.append(review_id)
            self._handled_value_feedback_review_ids.add(review_id)
            decision = review.get("review_decision")
            if decision == "ready":
                delta["stability"] = delta.get("stability", 0.0) + 0.003
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.001
            elif decision == "wait":
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.002
            elif decision == "reject":
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.001
                delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.002
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_value_feedback_review_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_value_feedback_updates(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        updates = [
            update
            for update in memory.get_recent_value_feedback_updates(8)
            if update.get("_event_tick") == tick
            and update.get("value_feedback_update_id") not in self._handled_value_feedback_update_ids
        ]
        if not updates:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for update in updates:
            update_id = update.get("value_feedback_update_id")
            if not update_id:
                continue
            handled.append(update_id)
            self._handled_value_feedback_update_ids.add(update_id)
            candidate_type = update.get("candidate_type")
            direction = update.get("value_direction")
            if candidate_type == "value_positive_candidate" or direction == "positive":
                delta["stability"] = delta.get("stability", 0.0) + 0.003
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.001
            elif candidate_type == "value_negative_candidate" or direction == "negative":
                delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.003
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.002
            else:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.002
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_value_feedback_update_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_decision_audits(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        audits = [
            audit
            for audit in memory.get_recent_decision_audits(8)
            if audit.get("_event_tick") == tick
            and audit.get("decision_audit_id") not in self._handled_decision_audit_ids
        ]
        if not audits:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for audit_event in audits:
            audit_id = audit_event.get("decision_audit_id")
            if not audit_id:
                continue
            handled.append(audit_id)
            self._handled_decision_audit_ids.add(audit_id)
            audit = audit_event.get("audit", {})
            if not isinstance(audit, dict):
                continue
            confidence = audit.get("audit_confidence")
            influence = audit.get("value_influence")
            ranking = audit.get("ranking_effect")
            if confidence in {"narrow_win", "tie_like"}:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.003
            elif confidence == "clear_win":
                delta["stability"] = delta.get("stability", 0.0) + 0.002
            if influence == "negative_penalty" or ranking == "demoted":
                delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.002
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.001
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_decision_audit_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_action_guard_audits(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        audits = [
            audit
            for audit in memory.get_recent_action_guard_audits(8)
            if audit.get("_event_tick") == tick
            and audit.get("action_guard_audit_id") not in self._handled_action_guard_audit_ids
        ]
        if not audits:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for audit_event in audits:
            audit_id = audit_event.get("action_guard_audit_id")
            if not audit_id:
                continue
            handled.append(audit_id)
            self._handled_action_guard_audit_ids.add(audit_id)
            summary = audit_event.get("summary", {})
            if not isinstance(summary, dict):
                continue
            severity = summary.get("severity")
            if severity in {"none", "low"}:
                delta["stability"] = delta.get("stability", 0.0) + 0.001
            elif severity in {"medium", "high"}:
                delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.003
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.002
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_action_guard_audit_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]

    def run_decision_cycle_summaries(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        summaries = [
            summary
            for summary in memory.get_recent_decision_cycle_summaries(8)
            if summary.get("_event_tick") == tick
            and summary.get("decision_cycle_summary_id") not in self._handled_decision_cycle_summary_ids
        ]
        if not summaries:
            return []
        delta: dict[str, float] = {}
        handled: list[str] = []
        for summary in summaries:
            summary_id = summary.get("decision_cycle_summary_id")
            if not summary_id:
                continue
            handled.append(summary_id)
            self._handled_decision_cycle_summary_ids.add(summary_id)
            cycle = summary.get("cycle_summary", {})
            if not isinstance(cycle, dict):
                continue
            status = cycle.get("cycle_status")
            confidence = cycle.get("cycle_confidence")
            flags = set(cycle.get("flags", ()))
            if status == "clean_selection" and confidence == "high":
                delta["stability"] = delta.get("stability", 0.0) + 0.002
            if status == "uncertain_selection" or flags & {"narrow_decision", "tie_like_decision"}:
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.003
            if status == "risky_or_constrained_selection" or "guard_blocked_high_score" in flags:
                delta["risk_sensitivity"] = delta.get("risk_sensitivity", 0.0) + 0.003
                delta["curiosity"] = delta.get("curiosity", 0.0) + 0.002
        if not handled or not delta:
            return []
        tone = memory.get_current_tone()
        next_tone = tone.shifted(**delta)
        payload = {
            "tone_update_id": self.id_gen.next("tone"),
            "tone_state": next_tone,
            "delta": {key: round(value, 3) for key, value in delta.items()},
            "based_on_decision_cycle_summary_ids": handled,
            "based_on_recent_label_count": 0,
            "based_on_recent_prediction_count": 0,
        }
        return [ContextOperation(self.id_gen.next("op"), OperationMarker.NEUROMODULATION_UPDATE, tick, self.module_name, None, payload)]


def _cap_candidate_delta(delta: dict[str, float]) -> dict[str, float]:
    caps = {
        "satisfaction": 0.03,
        "stability": 0.015,
        "pain": 0.03,
        "tension": 0.025,
        "curiosity": 0.02,
    }
    return {
        key: max(-caps.get(key, 0.03), min(caps.get(key, 0.03), value))
        for key, value in delta.items()
    }
