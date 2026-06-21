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
from clc.evaluation.value_feedback_candidate_builder import ValueFeedbackCandidateBuilder
from clc.field.active_context_field import ActiveContextField
from clc.field.field_updater import FieldUpdater
from clc.neuromodulation.neuromodulation_module import NeuromodulationModule
from clc.system.system_state import SystemState


REAL_EXPSM = Path("Memory") / "ExpSM" / "ExpSM_data.json"


def main() -> int:
    before_hash = _sha256(REAL_EXPSM)
    with tempfile.TemporaryDirectory(prefix="rndem_value_feedback_") as temp_dir:
        registry = PatternRegistry(Path(temp_dir) / "pattern_manifest.json")
        id_gen = IdGenerator()
        memory = ContextMemory(id_gen, registry)
        active_field = ActiveContextField()
        field_updater = FieldUpdater(registry)
        neuromodulation = NeuromodulationModule(id_gen, registry)
        builder = ValueFeedbackCandidateBuilder(id_gen, registry)
        target = registry.id("state_integrity_preservation")
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.TARGET_SATISFACTION_OBSERVED,
                1,
                "test",
                None,
                {
                    "target_satisfaction_id": "target_satisfaction_test",
                    "source_decision_id": "decision_test",
                    "source_experience_id": "2",
                    "source_mechanism_search_id": "expsm_mechanism_search_test",
                    "source_target_observation_id": "evaluation_target_test",
                    "target_pattern_id": target,
                    "target_pattern_name": "state_integrity_preservation",
                    "target_kind": "positive_target",
                    "target_role_names": ["needed_target", "safety_target"],
                    "mechanism_purpose": "preserve_target",
                    "mechanism_score": 0.62,
                    "satisfaction_status": "satisfied",
                    "satisfaction_score": 0.91,
                    "evidence_strength": 0.86,
                    "memory_modified": False,
                    "permanent_memory_modified": False,
                    "expsm_modified": False,
                    "akbsm_modified": False,
                    "activation": 0.7,
                    "ttl": 10,
                },
            )
        )
        operations = builder.run(2, memory, SystemState())
        marker30 = [operation for operation in operations if operation.marker == OperationMarker.VALUE_FEEDBACK_CANDIDATE]
        if marker30:
            memory.add_event(marker30[0])
            field_updater.update_from_memory(2, memory, active_field)
        tone_ops = neuromodulation.run_value_feedback_candidates(2, memory)
        payload = dict(marker30[0].payload) if marker30 else {}
        required_ok = all(
            payload.get(key) not in {None, ""}
            for key in (
                "source_target_satisfaction_id",
                "source_experience_id",
                "source_mechanism_search_id",
                "target_pattern_id",
                "satisfaction_status",
                "satisfaction_score",
                "evidence_strength",
                "candidate_type",
                "value_direction",
                "candidate_strength",
                "recommended_future_operation",
            )
        )
        observation_only = (
            payload.get("apply_now") is False
            and payload.get("memory_modified") is False
            and payload.get("permanent_memory_modified") is False
            and payload.get("expsm_modified") is False
            and payload.get("akbsm_modified") is False
        )
        field_ok = any(
            item["pattern_id"] == registry.id("value_feedback_candidate")
            for item in active_field.debug_snapshot()
        )
        tone_ok = bool(tone_ops and tone_ops[0].payload.get("based_on_value_feedback_candidate_ids"))
        no_marker10 = all(operation.marker != OperationMarker.EXPERIENCE_CANDIDATE for operation in operations)
    unchanged = before_hash == _sha256(REAL_EXPSM)
    passed = bool(marker30) and required_ok and observation_only and field_ok and tone_ok and no_marker10 and unchanged
    print("Value feedback candidate verification:")
    print(f"  marker 30 emitted: {'yes' if marker30 else 'no'}")
    print(f"  required payload fields: {'yes' if required_ok else 'no'}")
    print(f"  observation-only flags: {'yes' if observation_only else 'no'}")
    print(f"  active field projection: {'yes' if field_ok else 'no'}")
    print(f"  neuromodulation handled once: {'yes' if tone_ok else 'no'}")
    print(f"  no marker 10 from builder: {'yes' if no_marker10 else 'no'}")
    print(f"  real ExpSM unchanged: {'yes' if unchanged else 'no'}")
    if payload:
        print(
            "  example: "
            f"{payload.get('target_pattern_name')} "
            f"type={payload.get('candidate_type')} "
            f"direction={payload.get('value_direction')} "
            f"strength={payload.get('candidate_strength')} "
            f"future={payload.get('recommended_future_operation')}"
        )
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
