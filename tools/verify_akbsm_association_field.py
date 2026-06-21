from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.akbsm.akbsm_association_field import AKBSMAssociationField
from clc.akbsm.akbsm_association_field_updater import AKBSMAssociationFieldUpdater
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rndem_akbsm_field_") as temp_dir:
        registry = PatternRegistry(Path(temp_dir) / "pattern_manifest.json")
        source = registry.id("state_integrity_preservation")
        associated = registry.id("state_stability_high")
        id_gen = IdGenerator()
        memory = ContextMemory(id_gen, registry)
        field = AKBSMAssociationField()
        updater = AKBSMAssociationFieldUpdater()
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.AKBSM_ASSOCIATION_PROBE,
                1,
                "test",
                None,
                {
                    "probe_id": "akbsm_probe_test",
                    "source_pattern_id": source,
                    "target_kind": "positive_target",
                    "target_role_names": ["needed_target", "safety_target"],
                    "activation": 0.55,
                    "ttl": 10,
                    "associated_patterns": [
                        {
                            "pattern_id": associated,
                            "relation_type": "related_to",
                            "score": 0.78,
                            "distance": 1,
                            "path": [source, associated],
                        }
                    ],
                },
            )
        )
        updater.run(1, memory, field)
        first = field.get_associations(source)
        updater.run(1, memory, field)
        second = field.get_associations(source)
        score_after_tick_1 = second[0].score if second else 0.0
        ttl_after_tick_1 = second[0].ttl if second else 0
        probe_ids_after_repeat = list(second[0].source_probe_ids) if second else []
        updater.run(2, memory, field)
        third = field.get_associations(source)
        score_after_tick_2 = third[0].score if third else 0.0
        ttl_after_tick_2 = third[0].ttl if third else 0

    aggregation_ok = bool(
        first
        and first[0].source_pattern_id == source
        and first[0].associated_pattern_id == associated
        and first[0].relation_type == "related_to"
        and first[0].distance == 1
        and first[0].paths == [[source, associated]]
    )
    idempotency_ok = probe_ids_after_repeat == ["akbsm_probe_test"]
    decay_ok = bool(score_after_tick_2 < score_after_tick_1 and ttl_after_tick_2 == ttl_after_tick_1 - 1)
    passed = aggregation_ok and idempotency_ok and decay_ok
    print("AKBSM association field verification:")
    print(f"  aggregation: {'yes' if aggregation_ok else 'no'}")
    print(f"  idempotency: {'yes' if idempotency_ok else 'no'}")
    print(f"  decay: {'yes' if decay_ok else 'no'}")
    print(f"  score tick1 -> tick2: {round(score_after_tick_1, 3)} -> {round(score_after_tick_2, 3)}")
    print(f"  ttl tick1 -> tick2: {ttl_after_tick_1} -> {ttl_after_tick_2}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
