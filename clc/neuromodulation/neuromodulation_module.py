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
