from pathlib import Path
import hashlib
import json
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.action.action_candidate_field import ActionCandidateField
from clc.action.action_proposer import ActionProposer
from clc.action.decision_selector import DecisionSelector
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.expsm.expsm_outcome_feedback import ExpSMOutcomeFeedback
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


REAL_EXPSM = Path("Memory") / "ExpSM" / "ExpSM_data.json"


def main() -> int:
    before_hash = _sha256(REAL_EXPSM)
    with tempfile.TemporaryDirectory(prefix="rndem_mechanism_action_") as temp_dir:
        temp_root = Path(temp_dir)
        registry = PatternRegistry(temp_root / "pattern_manifest.json")
        id_gen = IdGenerator()
        memory = ContextMemory(id_gen, registry)
        candidate_field = ActionCandidateField(id_gen)
        proposer = ActionProposer(registry)
        selector = DecisionSelector(id_gen, decision_threshold=0.05)
        target = registry.id("state_integrity_preservation")
        action = registry.id("action_preserve_integrity")
        expsm_path = temp_root / "ExpSM_data.json"
        expsm_path.write_text(
            json.dumps(
                {
                    "experience": {
                        "mechanism_1": {
                            "if": [registry.id("internal_tension")],
                            "then": [action],
                            "result": [target],
                            "recommendation": [target],
                            "confidence": 0.7,
                            "repeatability": 0.6,
                            "hits": 1,
                            "misses": 0,
                            "status": 2,
                        }
                    },
                    "reflexes": {},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.EXPSM_MECHANISM_SEARCH,
                1,
                "test",
                None,
                {
                    "mechanism_search_id": "expsm_mechanism_search_test",
                    "source_target_observation_id": "evaluation_target_test",
                    "target_pattern_id": target,
                    "target_kind": "positive_target",
                    "target_role_names": ["needed_target"],
                    "target_score": 0.8,
                    "mechanisms": [
                        {
                            "experience_id": "mechanism_1",
                            "mechanism_purpose": "preserve_target",
                            "mechanism_score": 0.72,
                            "viability": 0.75,
                            "effective_confidence": 0.7,
                            "repeatability": 0.6,
                            "then_patterns": [action],
                        }
                    ],
                },
            )
        )
        proposer.propose(2, memory, ActiveContextField(), candidate_field, SystemState())
        candidates = candidate_field.debug_snapshot()
        candidate_ok = any(
            item.get("source_metadata", {}).get("source") == "expsm_mechanism_search"
            and item.get("pattern_id") == action
            for item in candidates
        )
        decision_op = selector.select(2, candidate_field, SystemState())
        decision_ok = bool(
            decision_op is not None
            and decision_op.payload.get("source") == "expsm_mechanism_search"
            and decision_op.payload.get("source_experience_id") == "mechanism_1"
        )
        if decision_op is not None:
            memory.add_event(decision_op)
            decision_id = decision_op.payload.get("decision_id")
            memory.add_event(
                ContextOperation(
                    id_gen.next("op"),
                    OperationMarker.INTERNAL_ACTION_EFFECT,
                    2,
                    "test",
                    None,
                    {
                        "effect_id": "effect_test",
                        "source_decision_id": decision_id,
                        "effect_pattern_id": target,
                        "effect_kind": target,
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
                        "outcome_id": "outcome_test",
                        "source_event_id": "effect_test",
                        "source_decision_id": decision_id,
                        "outcome_status": "confirmed",
                        "outcome_pattern_id": target,
                        "matched_patterns": [target],
                    },
                )
            )
        feedback_module = ExpSMOutcomeFeedback(id_gen, registry, expsm_path)
        feedback_ops = feedback_module.run(4, memory, ActiveContextField(), SystemState())
        feedback_ok = any(
            op.payload.get("trace_source") == "direct_decision_mechanism_source"
            and op.payload.get("experience_id") == "mechanism_1"
            for op in feedback_ops
        )
    unchanged = before_hash == _sha256(REAL_EXPSM)
    passed = candidate_ok and decision_ok and feedback_ok and unchanged
    print("ExpSM mechanism action source verification:")
    print(f"  candidate source created: {'yes' if candidate_ok else 'no'}")
    print(f"  marker 7 source trace: {'yes' if decision_ok else 'no'}")
    print(f"  direct feedback trace: {'yes' if feedback_ok else 'no'}")
    print(f"  real ExpSM unchanged: {'yes' if unchanged else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
