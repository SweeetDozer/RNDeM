from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.prediction.base_predictor import BasePredictor
from clc.storage_models.expsm_adapter import ExpSMAdapter


class SimpleFutureStatePredictor(BasePredictor):
    module_name = "simple_future_state_predictor"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry, expsm_adapter: ExpSMAdapter) -> None:
        self.id_gen = id_gen
        self.future_state_id = pattern_registry.id("prediction_future_state")
        self.expsm_adapter = expsm_adapter
        self.periodic_id = pattern_registry.id("periodic_audio_pattern")
        self.internal_risk_id = pattern_registry.id("internal_state_risk")
        self.novelty_id = pattern_registry.id("novel_activation_pattern")
        self.attention_audio_id = pattern_registry.id("internal_attention_audio")
        self.tension_id = pattern_registry.id("internal_tension")
        self.instability_id = pattern_registry.id("internal_instability")
        self.preserve_integrity_id = pattern_registry.id("internal_preserve_integrity")
        self.learning_candidate_id = pattern_registry.id("internal_learning_candidate")
        self.attention_visual_id = pattern_registry.id("internal_attention_visual")
        self._last_signature: tuple[int, ...] | None = None

    def run(self, tick: int, memory: ContextMemory) -> list[ContextOperation]:
        labels = [label for label in memory.recent_labels(8) if label.get("_event_tick") == tick]
        signature = tuple(label["label_id"] for label in labels)
        if not labels or signature == self._last_signature:
            return []
        self._last_signature = signature
        by_pattern = {label["label_pattern_id"]: label for label in labels}
        predictions: list[dict] = []
        predictions.extend(self._direct_memory_predictions(memory))
        predictions.extend(self._memory_predictions(labels))
        if self.periodic_id in by_pattern and any(label.get("risk", 0.0) >= 0.4 for label in labels):
            predictions.append(self._future_state([self.periodic_id], {self.attention_audio_id: 0.8, self.tension_id: 0.5}, 0.68, {"tension": 0.2, "curiosity": 0.1, "risk_sensitivity": 0.3}, []))
        if self.internal_risk_id in by_pattern:
            predictions.append(self._future_state([self.internal_risk_id], {self.instability_id: 0.8, self.preserve_integrity_id: 0.7}, 0.76, {"tension": 0.35, "risk_sensitivity": 0.25, "stability": -0.2}, [self.internal_risk_id]))
        novelty = by_pattern.get(self.novelty_id)
        if novelty and novelty.get("risk", 0.0) < 0.4:
            predictions.append(self._future_state([self.novelty_id], {self.learning_candidate_id: 0.75, self.attention_visual_id: 0.55}, 0.62, {"curiosity": 0.25, "tension": -0.05}, [self.novelty_id]))
        return [
            ContextOperation(self.id_gen.next("op"), OperationMarker.PREDICTION, tick, self.module_name, None, prediction)
            for prediction in predictions
        ]

    def _memory_predictions(self, labels: list[dict]) -> list[dict]:
        predictions: list[dict] = []
        for label in labels:
            matched_records = label.get("matched_records", [])
            for record in matched_records:
                suggested_patterns = tuple(record.get("suggested_patterns", ()))
                if not suggested_patterns:
                    continue
                probability = min(1.0, float(record.get("similarity", 0.0)) * float(record.get("confidence", 0.0)))
                predictions.append(
                    {
                        "prediction_id": self.id_gen.next("prediction"),
                        "prediction_kind": self.future_state_id,
                        "prediction_pattern_id": self.future_state_id,
                        "based_on_pattern_ids": [label["label_pattern_id"]],
                        "based_on_records": [record.get("record_id")],
                        "predicted_patterns": list(suggested_patterns),
                        "predicted_pattern": {"activations": {pattern_id: probability for pattern_id in suggested_patterns}},
                        "probability": round(probability, 3),
                        "expected_tone_delta": {"tension": 0.2, "risk_sensitivity": 0.3},
                        "confirmation_pattern_ids": list(suggested_patterns),
                        "ttl": 6,
                        "decay": 0.18,
                        "activation": round(probability, 3),
                    }
                )
        return predictions

    def _direct_memory_predictions(self, memory: ContextMemory) -> list[dict]:
        latest = [frame for frame in memory.get_recent_frames(1) if frame.origin != "self_generated"]
        if not latest:
            return []
        window = memory.build_window(1, source=latest[-1].source, origin=latest[-1].origin)
        if window is None:
            return []
        matches = self.expsm_adapter.match_reflexes(window, memory, threshold=0.5)
        matches.extend(self.expsm_adapter.match_experiences(window, memory, threshold=0.5))
        predictions: list[dict] = []
        for match in matches[:2]:
            if not match.suggested_patterns:
                continue
            probability = min(1.0, match.similarity * match.confidence)
            predictions.append(
                {
                    "prediction_id": self.id_gen.next("prediction"),
                    "prediction_kind": self.future_state_id,
                    "prediction_pattern_id": self.future_state_id,
                    "based_on_pattern_ids": [],
                    "based_on_records": [match.record_id],
                    "predicted_patterns": list(match.suggested_patterns),
                    "predicted_pattern": {"activations": {pattern_id: probability for pattern_id in match.suggested_patterns}},
                    "probability": round(probability, 3),
                    "expected_tone_delta": {"tension": 0.2, "risk_sensitivity": 0.3},
                    "confirmation_pattern_ids": list(match.suggested_patterns),
                    "ttl": 6,
                    "decay": 0.18,
                    "activation": round(probability, 3),
                }
            )
        return predictions

    def _future_state(self, based_on_pattern_ids: list[str], activations: dict[str, float], probability: float, tone_delta: dict[str, float], confirmation_pattern_ids: list[str]) -> dict:
        return {
            "prediction_id": self.id_gen.next("prediction"),
            "prediction_kind": self.future_state_id,
            "prediction_pattern_id": self.future_state_id,
            "based_on_pattern_ids": based_on_pattern_ids,
            "predicted_patterns": list(activations.keys()),
            "confirmation_pattern_ids": confirmation_pattern_ids,
            "predicted_pattern": {"activations": activations},
            "probability": probability,
            "expected_tone_delta": tone_delta,
            "ttl": 2,
            "decay": 0.2,
        }
