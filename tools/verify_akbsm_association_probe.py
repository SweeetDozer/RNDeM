from pathlib import Path
import hashlib
import json
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.akbsm.akbsm_association_probe import AKBSMAssociationProbe
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.evaluation_field import EvaluationField
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


REAL_AKBSM = Path("Memory") / "AKBSM" / "AKBSM_ne.json"


def main() -> int:
    before_hash = _sha256(REAL_AKBSM)
    with tempfile.TemporaryDirectory(prefix="rndem_akbsm_probe_") as temp_dir:
        temp_root = Path(temp_dir)
        registry = PatternRegistry(temp_root / "pattern_manifest.json")
        source = registry.id("state_integrity_preservation")
        target = registry.id("state_stability_high")
        akbsm_root = temp_root / "AKBSM"
        akbsm_root.mkdir()
        (akbsm_root / "AKBSM_ne.json").write_text(
            json.dumps(
                {
                    "edge_001": {
                        "from": source,
                        "type": "related_to",
                        "to": target,
                        "confidence": 0.78,
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        id_gen = IdGenerator()
        memory = ContextMemory(id_gen, registry)
        target_payload = {
            "target_observation_id": "evaluation_target_test",
            "pattern_id": source,
            "target_kind": "positive_target",
            "target_role_names": ["needed_target", "safety_target"],
            "target_score": 0.62,
        }
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.EVALUATION_TARGET_OBSERVED,
                1,
                "test",
                None,
                target_payload,
            )
        )
        probe = AKBSMAssociationProbe(id_gen, registry, akbsm_root)
        operations = probe.run(1, memory, ActiveContextField(), EvaluationField(), SystemState())
        marker27 = [operation for operation in operations if operation.marker == OperationMarker.AKBSM_ASSOCIATION_PROBE]
        association_seen = bool(marker27 and marker27[0].payload.get("associations_found") == 1)
        target_seen = False
        if marker27:
            associated = marker27[0].payload.get("associated_patterns", ())
            target_seen = any(item.get("pattern_id") == target for item in associated)
    after_hash = _sha256(REAL_AKBSM)
    unchanged = before_hash == after_hash
    passed = bool(association_seen and target_seen and unchanged)
    print("AKBSM association probe verification:")
    print("  temp AKBSM: yes")
    print(f"  marker 27 emitted: {'yes' if marker27 else 'no'}")
    print(f"  association found: {'yes' if association_seen else 'no'}")
    print(f"  associated target observed: {'yes' if target_seen else 'no'}")
    print(f"  real AKBSM unchanged: {'yes' if unchanged else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
