from clc.context.context_memory import ContextMemory
from clc.evaluation.evaluation_field import EvaluationField


class EvaluationFieldUpdater:
    module_name = "evaluation_field_updater"

    def __init__(self) -> None:
        self.applied_evaluation_ids: set[str] = set()

    def run(self, tick: int, memory: ContextMemory, evaluation_field: EvaluationField) -> None:
        for signal in memory.get_recent_evaluation_signals(24):
            evaluation_id = str(signal.get("evaluation_id", ""))
            if not evaluation_id or evaluation_id in self.applied_evaluation_ids:
                continue
            self.applied_evaluation_ids.add(evaluation_id)
            dimensions = signal.get("evaluation_dimensions", {})
            if not isinstance(dimensions, dict):
                continue
            source_id = str(signal.get("source_event_id") or evaluation_id)
            scope = str(signal.get("evaluation_scope") or "unknown")
            activation = float(signal.get("activation", 0.6) or 0.0)
            ttl = int(signal.get("ttl", 10) or 10)
            for pattern_id in signal.get("target_patterns", ()):
                evaluation_field.update_pattern(
                    str(pattern_id),
                    dimensions,
                    source_id=source_id,
                    scope=scope,
                    activation=activation,
                    ttl=ttl,
                    tick=tick,
                )
        evaluation_field.decay(tick)
        if len(self.applied_evaluation_ids) > 512:
            self.applied_evaluation_ids = set(list(self.applied_evaluation_ids)[-256:])
