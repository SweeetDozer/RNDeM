from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.value_feedback_memory_view import ValueFeedbackMemoryView
from clc.evaluation.value_feedback_update_writer import ValueFeedbackUpdateWriter
from clc.system.system_state import SystemState


REAL_EXPSM = PROJECT_ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"


def main() -> int:
    real_hash_before = _sha256(REAL_EXPSM)
    with tempfile.TemporaryDirectory(prefix="rndem_value_feedback_view_") as temp_dir:
        temp_root = Path(temp_dir)
        registry = PatternRegistry(temp_root / "Memory" / "pattern_manifest.json")
        expsm_path = temp_root / "Memory" / "ExpSM" / "ExpSM_data.json"
        expsm_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(expsm_path, _demo_store(registry))

        view = ValueFeedbackMemoryView(registry, expsm_path)
        positive = view.get("positive")
        negative = view.get("negative")
        neutral = view.get("neutral")
        before_update = view.get("refresh")
        _apply_temp_value_feedback_update(registry, expsm_path)
        view.refresh()
        after_update = view.get("refresh")

        positive_ok = (
            positive is not None
            and positive.positive_count == 1
            and positive.negative_count == 0
            and positive.value_balance > 0.0
            and positive.value_risk == 0.0
            and positive.linked_target_patterns
        )
        negative_ok = (
            negative is not None
            and negative.negative_count >= 2
            and negative.value_balance < 0.0
            and negative.value_risk > 0.0
        )
        neutral_ok = (
            neutral is not None
            and neutral.positive_count == 0
            and neutral.negative_count == 0
            and neutral.value_balance == 0.0
            and neutral.value_confidence == 0.0
            and neutral.value_risk == 0.0
        )
        refresh_ok = (
            before_update is not None
            and after_update is not None
            and before_update.positive_count == 0
            and after_update.positive_count == 1
            and after_update.value_balance > before_update.value_balance
        )
        snapshot = view.snapshot()
        snapshot_ok = (
            snapshot.get("record_count") == 4
            and snapshot.get("records_with_value_feedback") == 3
            and len(snapshot.get("records", [])) == 4
        )
    real_unchanged = real_hash_before == _sha256(REAL_EXPSM)
    passed = positive_ok and negative_ok and neutral_ok and refresh_ok and snapshot_ok and real_unchanged
    print("Value feedback memory view verification:")
    print(f"  positive-only record: {'yes' if positive_ok else 'no'}")
    print(f"  negative-heavy record: {'yes' if negative_ok else 'no'}")
    print(f"  neutral missing-block record: {'yes' if neutral_ok else 'no'}")
    print(f"  refresh after temp update: {'yes' if refresh_ok else 'no'}")
    print(f"  snapshot serializable: {'yes' if snapshot_ok else 'no'}")
    print(f"  real ExpSM unchanged: {'yes' if real_unchanged else 'no'}")
    if positive is not None:
        print(
            "  positive example: "
            f"experience={positive.experience_id} balance={positive.value_balance} "
            f"confidence={positive.value_confidence} risk={positive.value_risk}"
        )
    if negative is not None:
        print(
            "  negative example: "
            f"experience={negative.experience_id} balance={negative.value_balance} "
            f"confidence={negative.value_confidence} risk={negative.value_risk}"
        )
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _demo_store(registry: PatternRegistry) -> dict[str, Any]:
    target = registry.id("state_integrity_preservation")
    avoid_target = registry.id("evaluation_avoidance_target")
    return {
        "experience": {
            "positive": {
                "if": ["pat_if"],
                "then": ["pat_then"],
                "result": ["pat_result"],
                "recommendation": ["pat_recommend"],
                "value_feedback": {
                    "positive_count": 1,
                    "negative_count": 0,
                    "mixed_count": 0,
                    "inconclusive_count": 0,
                    "positive_strength_total": 0.84,
                    "negative_strength_total": 0.0,
                    "mixed_strength_total": 0.0,
                    "last_review_id": "review_positive",
                    "last_updated_tick": 7,
                    "target_links": [
                        {
                            "target_pattern_id": target,
                            "target_kind": "positive_target",
                            "target_role_names": ["needed_target", "safety_target"],
                            "value_direction": "positive",
                            "candidate_strength": 0.84,
                            "evidence_strength": 0.78,
                            "satisfaction_status": "satisfied",
                            "recommended_future_operation": "increase_value_confidence",
                        }
                    ],
                },
            },
            "negative": {
                "if": ["pat_if"],
                "then": ["pat_then"],
                "result": ["pat_result"],
                "recommendation": ["pat_recommend"],
                "value_feedback": {
                    "positive_count": 0,
                    "negative_count": 2,
                    "mixed_count": 1,
                    "inconclusive_count": 0,
                    "positive_strength_total": 0.0,
                    "negative_strength_total": 1.55,
                    "mixed_strength_total": 0.3,
                    "last_review_id": "review_negative",
                    "last_updated_tick": 8,
                    "target_links": [
                        {
                            "target_pattern_id": avoid_target,
                            "target_kind": "avoidance_target",
                            "target_role_names": ["avoidance_target", "harmful_target"],
                            "value_direction": "negative",
                            "candidate_strength": 0.81,
                            "evidence_strength": 0.76,
                            "satisfaction_status": "worsened",
                            "recommended_future_operation": "increase_avoidance_warning",
                        }
                    ],
                },
            },
            "neutral": {
                "if": ["pat_if"],
                "then": ["pat_then"],
                "result": ["pat_result"],
                "recommendation": ["pat_recommend"],
            },
            "refresh": {
                "if": ["pat_if"],
                "then": ["pat_then"],
                "result": ["pat_result"],
                "recommendation": ["pat_recommend"],
                "value_feedback": {
                    "positive_count": 0,
                    "negative_count": 0,
                    "mixed_count": 0,
                    "inconclusive_count": 0,
                    "positive_strength_total": 0.0,
                    "negative_strength_total": 0.0,
                    "mixed_strength_total": 0.0,
                    "target_links": [],
                },
            },
        },
        "reflexes": {
            "ignored_reflex": {
                "value_feedback": {
                    "negative_count": 9,
                    "negative_strength_total": 9.0,
                }
            }
        },
    }


def _apply_temp_value_feedback_update(registry: PatternRegistry, expsm_path: Path) -> None:
    id_gen = IdGenerator()
    memory = ContextMemory(id_gen, registry)
    target = registry.id("state_integrity_preservation")
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.VALUE_FEEDBACK_REVIEW,
            1,
            "verify_value_feedback_memory_view",
            None,
            {
                "value_feedback_review_id": "review_refresh",
                "source_value_feedback_candidate_id": "candidate_refresh",
                "source_target_satisfaction_id": "target_satisfaction_refresh",
                "source_experience_id": "refresh",
                "source_mechanism_search_id": "mechanism_refresh",
                "source_target_observation_id": "target_observation_refresh",
                "target_pattern_id": target,
                "target_pattern_name": registry.debug_name(target),
                "target_kind": "positive_target",
                "target_role_names": ["needed_target"],
                "candidate_type": "value_positive_candidate",
                "value_direction": "positive",
                "candidate_strength": 0.82,
                "evidence_strength": 0.74,
                "satisfaction_status": "satisfied",
                "satisfaction_score": 0.70,
                "review_decision": "ready",
                "review_reason": "strong_positive_value_feedback",
                "recommended_future_operation": "increase_value_confidence",
                "ready_for_future_application": True,
                "apply_now": False,
                "activation": 0.5,
                "ttl": 12,
            },
        )
    )
    writer = ValueFeedbackUpdateWriter(id_gen, registry, expsm_path)
    writer.run(2, memory, SystemState(mode="consolidation"))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
