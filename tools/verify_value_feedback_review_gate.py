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
from clc.evaluation.value_feedback_review_gate import ValueFeedbackReviewGate
from clc.field.active_context_field import ActiveContextField
from clc.field.field_updater import FieldUpdater
from clc.neuromodulation.neuromodulation_module import NeuromodulationModule
from clc.system.system_state import SystemState


REAL_EXPSM = Path("Memory") / "ExpSM" / "ExpSM_data.json"


def main() -> int:
    before_hash = _sha256(REAL_EXPSM)
    with tempfile.TemporaryDirectory(prefix="rndem_value_feedback_review_") as temp_dir:
        registry = PatternRegistry(Path(temp_dir) / "pattern_manifest.json")
        id_gen = IdGenerator()
        memory = ContextMemory(id_gen, registry)
        active_field = ActiveContextField()
        field_updater = FieldUpdater(registry)
        neuromodulation = NeuromodulationModule(id_gen, registry)
        gate = ValueFeedbackReviewGate(id_gen, registry)
        state = SystemState(mode="consolidation")
        target = registry.id("state_integrity_preservation")
        _add_candidate(memory, id_gen, target, "value_feedback_candidate_ready", "value_positive_candidate", 0.86, 0.80, "satisfied", 0.92)
        _add_candidate(memory, id_gen, target, "value_feedback_candidate_wait", "value_mixed_candidate", 0.42, 0.31, "not_satisfied", -0.05)
        _add_candidate(memory, id_gen, target, "value_feedback_candidate_reject", "value_positive_candidate", 0.74, 0.09, "satisfied", 0.66, source_experience_id="")

        operations = gate.run(2, memory, state)
        reviews = [operation for operation in operations if operation.marker == OperationMarker.VALUE_FEEDBACK_REVIEW]
        for review in reviews:
            memory.add_event(review)
        field_updater.update_from_memory(2, memory, active_field)
        tone_ops = neuromodulation.run_value_feedback_reviews(2, memory)

        by_source = {op.payload.get("source_value_feedback_candidate_id"): dict(op.payload) for op in reviews}
        ready_ok = by_source.get("value_feedback_candidate_ready", {}).get("review_decision") == "ready"
        wait_ok = by_source.get("value_feedback_candidate_wait", {}).get("review_decision") == "wait"
        reject_ok = by_source.get("value_feedback_candidate_reject", {}).get("review_decision") == "reject"
        required_ok = _required_review_fields(by_source.get("value_feedback_candidate_ready", {}))
        observation_only = all(
            payload.get("apply_now") is False
            and payload.get("memory_modified") is False
            and payload.get("permanent_memory_modified") is False
            and payload.get("expsm_modified") is False
            and payload.get("akbsm_modified") is False
            for payload in by_source.values()
        )
        field_ok = any(
            item["pattern_id"] == registry.id("value_feedback_review")
            for item in active_field.debug_snapshot()
        )
        tone_ok = bool(tone_ops and tone_ops[0].payload.get("based_on_value_feedback_review_ids"))
        no_marker10 = all(operation.marker != OperationMarker.EXPERIENCE_CANDIDATE for operation in operations)
    unchanged = before_hash == _sha256(REAL_EXPSM)
    passed = ready_ok and wait_ok and reject_ok and required_ok and observation_only and field_ok and tone_ok and no_marker10 and unchanged
    print("Value feedback review gate verification:")
    print(f"  ready case: {'yes' if ready_ok else 'no'}")
    print(f"  wait case: {'yes' if wait_ok else 'no'}")
    print(f"  reject case: {'yes' if reject_ok else 'no'}")
    print(f"  required payload fields: {'yes' if required_ok else 'no'}")
    print(f"  review-only flags: {'yes' if observation_only else 'no'}")
    print(f"  active field projection: {'yes' if field_ok else 'no'}")
    print(f"  neuromodulation handled once: {'yes' if tone_ok else 'no'}")
    print(f"  no marker 10 from gate: {'yes' if no_marker10 else 'no'}")
    print(f"  real ExpSM unchanged: {'yes' if unchanged else 'no'}")
    example = by_source.get("value_feedback_candidate_ready", {})
    if example:
        print(
            "  example: "
            f"{example.get('target_pattern_name')} "
            f"decision={example.get('review_decision')} "
            f"reason={example.get('review_reason')} "
            f"strength={example.get('candidate_strength')} "
            f"evidence={example.get('evidence_strength')}"
        )
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _add_candidate(
    memory: ContextMemory,
    id_gen: IdGenerator,
    target: str,
    candidate_id: str,
    candidate_type: str,
    strength: float,
    evidence: float,
    satisfaction_status: str,
    satisfaction_score: float,
    source_experience_id: str = "2",
) -> None:
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.VALUE_FEEDBACK_CANDIDATE,
            1,
            "test",
            None,
            {
                "value_feedback_candidate_id": candidate_id,
                "candidate_kind": "value_feedback_candidate",
                "candidate_type": candidate_type,
                "value_direction": "positive" if satisfaction_score > 0.2 else "mixed_or_unclear",
                "candidate_strength": strength,
                "recommended_future_operation": "increase_value_confidence",
                "apply_now": False,
                "source_target_satisfaction_id": f"target_satisfaction_{candidate_id}",
                "source_decision_id": f"decision_{candidate_id}",
                "source_experience_id": source_experience_id,
                "source_mechanism_search_id": f"expsm_mechanism_search_{candidate_id}",
                "source_target_observation_id": f"evaluation_target_{candidate_id}",
                "target_pattern_id": target,
                "target_pattern_name": "state_integrity_preservation",
                "target_kind": "positive_target",
                "target_role_names": ["needed_target", "safety_target"],
                "mechanism_purpose": "preserve_target",
                "mechanism_score": 0.61,
                "satisfaction_status": satisfaction_status,
                "satisfaction_score": satisfaction_score,
                "evidence_strength": evidence,
                "memory_modified": False,
                "permanent_memory_modified": False,
                "expsm_modified": False,
                "akbsm_modified": False,
                "activation": 0.55,
                "ttl": 10,
            },
        )
    )


def _required_review_fields(payload: dict) -> bool:
    return all(
        payload.get(key) not in {None, ""}
        for key in (
            "source_value_feedback_candidate_id",
            "source_experience_id",
            "target_pattern_id",
            "candidate_type",
            "value_direction",
            "candidate_strength",
            "evidence_strength",
            "review_decision",
            "review_reason",
            "recommended_future_operation",
        )
    ) and payload.get("apply_now") is False and "ready_for_future_application" in payload


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
