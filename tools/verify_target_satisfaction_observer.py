from pathlib import Path
import hashlib
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.evaluation_field import EvaluationField
from clc.evaluation.evaluation_field_updater import EvaluationFieldUpdater
from clc.evaluation.target_satisfaction_observer import TargetSatisfactionObserver
from clc.field.active_context_field import ActiveContextField
from clc.field.field_updater import FieldUpdater
from clc.neuromodulation.neuromodulation_module import NeuromodulationModule
from clc.system.system_state import SystemState


REAL_EXPSM = Path("Memory") / "ExpSM" / "ExpSM_data.json"


def main() -> int:
    before_hash = _sha256(REAL_EXPSM)
    with tempfile.TemporaryDirectory(prefix="rndem_target_satisfaction_") as temp_dir:
        registry = PatternRegistry(Path(temp_dir) / "pattern_manifest.json")
        id_gen = IdGenerator()
        memory = ContextMemory(id_gen, registry)
        active_field = ActiveContextField()
        evaluation_field = EvaluationField()
        evaluation_updater = EvaluationFieldUpdater()
        field_updater = FieldUpdater(registry)
        neuromodulation = NeuromodulationModule(id_gen, registry)
        observer = TargetSatisfactionObserver(id_gen, registry)
        system_state = SystemState()

        target = registry.id("state_integrity_preservation")
        action = registry.id("action_preserve_integrity")
        decision_id = "decision_mechanism_test"
        effect_id = "effect_mechanism_test"
        outcome_id = "outcome_mechanism_test"
        evaluation_id = "evaluation_signal_mechanism_test"

        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.INTERNAL_DECISION,
                1,
                "test",
                None,
                {
                    "decision_id": decision_id,
                    "decision_pattern_id": action,
                    "source": "expsm_mechanism_search",
                    "source_experience_id": "2",
                    "source_mechanism_search_id": "expsm_mechanism_search_test",
                    "source_target_observation_id": "evaluation_target_test",
                    "source_target_pattern_id": target,
                    "source_target_kind": "positive_target",
                    "source_target_roles": ["needed_target", "safety_target"],
                    "source_mechanism_purpose": "preserve_target",
                    "source_mechanism_score": 0.66,
                    "activation": 0.72,
                    "ttl": 3,
                },
            )
        )
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.INTERNAL_ACTION_EFFECT,
                2,
                "test",
                None,
                {
                    "effect_id": effect_id,
                    "source_decision_id": decision_id,
                    "effect_pattern_id": target,
                    "activation": 0.8,
                    "ttl": 4,
                },
            )
        )
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.OUTCOME_EVALUATION,
                3,
                "test",
                None,
                {
                    "outcome_id": outcome_id,
                    "source_event_id": effect_id,
                    "source_decision_id": decision_id,
                    "source_kind": "effect",
                    "outcome_status": "confirmed",
                    "outcome_pattern_id": registry.id("outcome_confirmed"),
                    "matched_patterns": [target],
                    "activation": 0.8,
                    "ttl": 5,
                },
            )
        )
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.EVALUATION_SIGNAL,
                3,
                "test",
                None,
                {
                    "evaluation_id": evaluation_id,
                    "source_event_id": outcome_id,
                    "source_marker": OperationMarker.OUTCOME_EVALUATION.value,
                    "evaluation_scope": "target_satisfaction_test",
                    "target_patterns": [target],
                    "evaluation_dimensions": {
                        "usefulness": 0.42,
                        "need": 0.36,
                        "want": 0.0,
                        "safety": 0.48,
                        "priority": 0.32,
                        "harmfulness": 0.02,
                        "avoid": 0.0,
                    },
                    "activation": 0.7,
                    "ttl": 10,
                },
            )
        )
        evaluation_updater.run(3, memory, evaluation_field)
        operations = observer.run(4, memory, active_field, evaluation_field, system_state)
        marker29 = [operation for operation in operations if operation.marker == OperationMarker.TARGET_SATISFACTION_OBSERVED]
        if marker29:
            memory.add_event(marker29[0])
            field_updater.update_from_memory(4, memory, active_field)
        tone_ops = neuromodulation.run_target_satisfaction_observations(4, memory)

        payload = dict(marker29[0].payload) if marker29 else {}
        required_ok = all(
            payload.get(key)
            for key in (
                "source_decision_id",
                "source_experience_id",
                "source_mechanism_search_id",
                "source_target_observation_id",
                "target_pattern_id",
                "satisfaction_status",
                "satisfaction_score",
                "evidence_strength",
            )
        )
        observation_only = (
            payload.get("memory_modified") is False
            and payload.get("permanent_memory_modified") is False
            and payload.get("expsm_modified") is False
            and payload.get("akbsm_modified") is False
        )
        field_ok = any(
            item["pattern_id"] == registry.id("target_satisfaction_observed")
            for item in active_field.debug_snapshot()
        )
        tone_ok = bool(tone_ops and tone_ops[0].payload.get("based_on_target_satisfaction_ids"))
        no_marker10 = all(operation.marker != OperationMarker.EXPERIENCE_CANDIDATE for operation in operations)
    unchanged = before_hash == _sha256(REAL_EXPSM)
    passed = bool(marker29) and required_ok and observation_only and field_ok and tone_ok and no_marker10 and unchanged
    print("Target satisfaction observer verification:")
    print(f"  marker 29 emitted: {'yes' if marker29 else 'no'}")
    print(f"  required payload fields: {'yes' if required_ok else 'no'}")
    print(f"  observation-only flags: {'yes' if observation_only else 'no'}")
    print(f"  active field projection: {'yes' if field_ok else 'no'}")
    print(f"  neuromodulation handled once: {'yes' if tone_ok else 'no'}")
    print(f"  no marker 10 from observer: {'yes' if no_marker10 else 'no'}")
    print(f"  real ExpSM unchanged: {'yes' if unchanged else 'no'}")
    if payload:
        print(
            "  example: "
            f"{payload.get('target_pattern_name')} "
            f"status={payload.get('satisfaction_status')} "
            f"score={payload.get('satisfaction_score')} "
            f"evidence={payload.get('evidence_strength')}"
        )
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
