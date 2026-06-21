from pathlib import Path
import hashlib
import json
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.akbsm.akbsm_association_field import AKBSMAssociationField
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.evaluation_field import EvaluationField
from clc.expsm.expsm_mechanism_search import ExpSMMechanismSearch
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


REAL_EXPSM = Path("Memory") / "ExpSM" / "ExpSM_data.json"
REAL_AKBSM = Path("Memory") / "AKBSM" / "AKBSM_ne.json"


def main() -> int:
    expsm_before = _sha256(REAL_EXPSM)
    akbsm_before = _sha256(REAL_AKBSM)
    with tempfile.TemporaryDirectory(prefix="rndem_expsm_mechanism_") as temp_dir:
        temp_root = Path(temp_dir)
        registry = PatternRegistry(temp_root / "pattern_manifest.json")
        target = registry.id("state_integrity_preservation")
        associated = registry.id("state_stability_high")
        action = registry.id("action_preserve_integrity")
        context = registry.id("internal_tension")
        expsm_path = temp_root / "ExpSM_data.json"
        expsm_path.write_text(
            json.dumps(
                {
                    "experience": {
                        "mechanism_1": {
                            "if": [context],
                            "then": [action],
                            "result": [target],
                            "recommendation": [associated],
                            "confidence": 0.95,
                            "repeatability": 0.9,
                            "hits": 9,
                            "misses": 1,
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
        id_gen = IdGenerator()
        memory = ContextMemory(id_gen, registry)
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.EVALUATION_TARGET_OBSERVED,
                1,
                "test",
                None,
                {
                    "target_observation_id": "evaluation_target_test",
                    "pattern_id": target,
                    "target_kind": "positive_target",
                    "target_role_names": ["needed_target", "safety_target"],
                    "target_score": 0.7,
                    "evaluation_dimensions": {"need": 0.7, "safety": 0.7, "priority": 0.6},
                },
            )
        )
        active_field = ActiveContextField()
        active_field.activate(context, 0.6, 1, "test", "source", ttl=5)
        association_field = AKBSMAssociationField()
        association_field.update_association(
            target,
            associated,
            relation_type="related_to",
            score=0.78,
            distance=1,
            path=[target, associated],
            source_probe_id="akbsm_probe_test",
            target_kind="positive_target",
            target_roles=["needed_target", "safety_target"],
            activation=0.55,
            ttl=10,
            tick=1,
        )
        search = ExpSMMechanismSearch(id_gen, registry, expsm_path)
        operations = search.run(1, memory, active_field, EvaluationField(), association_field, SystemState())
        marker28 = [operation for operation in operations if operation.marker == OperationMarker.EXPSM_MECHANISM_SEARCH]
        found = bool(marker28 and marker28[0].payload.get("mechanisms_found") == 1)
        mechanism = marker28[0].payload.get("mechanisms", [{}])[0] if marker28 else {}
        purpose_ok = mechanism.get("mechanism_purpose") == "obtain_target"
        score_ok = float(mechanism.get("mechanism_score", 0.0) or 0.0) >= 0.25
    expsm_unchanged = expsm_before == _sha256(REAL_EXPSM)
    akbsm_unchanged = akbsm_before == _sha256(REAL_AKBSM)
    passed = found and purpose_ok and score_ok and expsm_unchanged and akbsm_unchanged
    print("ExpSM mechanism search verification:")
    print("  temp ExpSM: yes")
    print(f"  marker 28 emitted: {'yes' if marker28 else 'no'}")
    print(f"  mechanism found: {'yes' if found else 'no'}")
    print(f"  purpose obtain_target: {'yes' if purpose_ok else 'no'}")
    print(f"  score above threshold: {'yes' if score_ok else 'no'}")
    print(f"  real ExpSM unchanged: {'yes' if expsm_unchanged else 'no'}")
    print(f"  real AKBSM unchanged: {'yes' if akbsm_unchanged else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
