from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.value_feedback_update_writer import ValueFeedbackUpdateWriter
from clc.system.system_state import SystemState


SEMANTIC_CORE_KEYS = ("if", "then", "result", "recommendation")
TECHNICAL_KEYS = ("hits", "misses", "confidence", "repeatability")


def main() -> int:
    real_expsm_path = ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"
    real_hash_before = _hash_file(real_expsm_path)
    with tempfile.TemporaryDirectory(prefix="rndem_value_feedback_update_") as temp_dir:
        temp_root = Path(temp_dir)
        expsm_path = temp_root / "Memory" / "ExpSM" / "ExpSM_data.json"
        manifest_path = temp_root / "Memory" / "pattern_manifest.json"
        expsm_path.parent.mkdir(parents=True, exist_ok=True)
        registry = PatternRegistry(manifest_path)
        id_gen = IdGenerator()
        memory = ContextMemory(id_gen, registry)
        state = SystemState(mode="consolidation")
        before_store = _demo_expsm_store()
        _write_json(expsm_path, before_store)

        writer = ValueFeedbackUpdateWriter(id_gen, registry, expsm_path)
        review_payload = _ready_review(registry)
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.VALUE_FEEDBACK_REVIEW,
                1,
                "verify_value_feedback_update_writer",
                None,
                review_payload,
            )
        )

        operations = writer.run(2, memory, state)
        for operation in operations:
            memory.add_event(operation)
        after_store = _read_json(expsm_path)
        duplicate_operations = writer.run(3, memory, state)
        duplicate_store = _read_json(expsm_path)

    real_hash_after = _hash_file(real_expsm_path)
    checks = {
        "temp memory": True,
        "marker 32 emitted": _has_marker32(operations),
        "only value_feedback changed": _only_value_feedback_changed(before_store, after_store),
        "semantic core unchanged": _subset(before_store, SEMANTIC_CORE_KEYS) == _subset(after_store, SEMANTIC_CORE_KEYS),
        "technical feedback unchanged": _subset(before_store, TECHNICAL_KEYS) == _subset(after_store, TECHNICAL_KEYS),
        "duplicate skipped": not duplicate_operations and after_store == duplicate_store,
        "target_links bounded": len(after_store["experience"]["2"]["value_feedback"]["target_links"]) == 32,
        "real ExpSM_data.json unchanged": real_hash_before == real_hash_after,
    }
    passed = all(checks.values())
    print("Value feedback update writer verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _demo_expsm_store() -> dict[str, Any]:
    return {
        "experience": {
            "2": {
                "if": ["pat_if"],
                "then": ["pat_then"],
                "result": ["pat_result"],
                "recommendation": ["pat_recommend"],
                "hits": 2,
                "misses": 1,
                "confidence": 0.51,
                "repeatability": 0.52,
                "value_feedback": {
                    "positive_count": 0,
                    "negative_count": 0,
                    "mixed_count": 0,
                    "inconclusive_count": 0,
                    "positive_strength_total": 0.0,
                    "negative_strength_total": 0.0,
                    "mixed_strength_total": 0.0,
                    "last_review_id": None,
                    "last_candidate_id": None,
                    "last_target_satisfaction_id": None,
                    "last_updated_tick": None,
                    "target_links": [
                        {"value_feedback_review_id": f"old_review_{idx}", "target_pattern_id": f"old_target_{idx}"}
                        for idx in range(32)
                    ],
                },
            }
        },
        "reflexes": {},
    }


def _ready_review(registry: PatternRegistry) -> dict[str, Any]:
    target_pattern = registry.id("evaluation_useful_target")
    return {
        "value_feedback_review_id": "review_ready_001",
        "source_value_feedback_candidate_id": "candidate_001",
        "source_target_satisfaction_id": "target_satisfaction_001",
        "source_experience_id": "2",
        "source_mechanism_search_id": "mechanism_search_001",
        "source_target_observation_id": "target_observation_001",
        "target_pattern_id": target_pattern,
        "target_pattern_name": registry.debug_name(target_pattern),
        "target_kind": "useful_target",
        "target_role_names": ["useful_target"],
        "candidate_type": "value_positive_candidate",
        "value_direction": "positive",
        "candidate_strength": 0.84,
        "evidence_strength": 0.78,
        "satisfaction_status": "satisfied",
        "satisfaction_score": 0.72,
        "review_decision": "ready",
        "review_reason": "strong_positive_value_feedback",
        "recommended_future_operation": "increase_target_usefulness_link",
        "ready_for_future_application": True,
        "apply_now": False,
        "activation": 0.5,
        "ttl": 12,
    }


def _has_marker32(operations: list[ContextOperation]) -> bool:
    updates = [operation for operation in operations if operation.marker == OperationMarker.VALUE_FEEDBACK_UPDATED]
    if len(updates) != 1:
        return False
    payload = dict(updates[0].payload)
    return (
        payload.get("semantic_core_modified") is False
        and payload.get("technical_feedback_modified") is False
        and payload.get("expsm_modified") is True
        and payload.get("akbsm_modified") is False
    )


def _only_value_feedback_changed(before_store: dict[str, Any], after_store: dict[str, Any]) -> bool:
    before = copy.deepcopy(before_store)
    after = copy.deepcopy(after_store)
    before["experience"]["2"].pop("value_feedback", None)
    after["experience"]["2"].pop("value_feedback", None)
    if before != after:
        return False
    feedback = after_store["experience"]["2"].get("value_feedback", {})
    return (
        feedback.get("positive_count") == 1
        and feedback.get("positive_strength_total") == 0.84
        and feedback.get("last_review_id") == "review_ready_001"
        and feedback.get("target_links", [])[-1].get("value_feedback_review_id") == "review_ready_001"
    )


def _subset(store: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    record = store["experience"]["2"]
    return {key: copy.deepcopy(record.get(key)) for key in keys}


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
