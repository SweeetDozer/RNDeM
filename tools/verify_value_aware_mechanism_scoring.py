from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.action.action_candidate_field import ActionCandidateField
from clc.action.action_proposer import ActionProposer
from clc.akbsm.akbsm_association_field import AKBSMAssociationField
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.evaluation_field import EvaluationField
from clc.evaluation.value_feedback_memory_view import ValueFeedbackMemoryView
from clc.expsm.expsm_mechanism_search import MAX_VALUE_BONUS, MAX_VALUE_PENALTY, ExpSMMechanismSearch
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


REAL_EXPSM = PROJECT_ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"
REAL_AKBSM = PROJECT_ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"


def main() -> int:
    real_expsm_before = _sha256(REAL_EXPSM)
    real_akbsm_before = _sha256(REAL_AKBSM)
    with tempfile.TemporaryDirectory(prefix="rndem_value_mechanism_") as temp_dir:
        temp_root = Path(temp_dir)
        registry = PatternRegistry(temp_root / "Memory" / "pattern_manifest.json")
        expsm_path = temp_root / "Memory" / "ExpSM" / "ExpSM_data.json"
        expsm_path.parent.mkdir(parents=True, exist_ok=True)
        target = registry.id("state_integrity_preservation")
        action = registry.id("action_preserve_integrity")
        context = registry.id("internal_tension")
        unrelated_target = registry.id("evaluation_avoidance_target")
        _write_json(expsm_path, _demo_store(target, action, context, unrelated_target))

        memory, id_gen, active_field = _memory_with_target(registry, target, context)
        value_view = ValueFeedbackMemoryView(registry, expsm_path)
        search = ExpSMMechanismSearch(id_gen, registry, expsm_path, value_view)
        operations = search.run(1, memory, active_field, EvaluationField(), AKBSMAssociationField(), SystemState())
        marker28 = [operation for operation in operations if operation.marker == OperationMarker.EXPSM_MECHANISM_SEARCH]
        mechanisms = {
            mechanism.get("experience_id"): mechanism
            for mechanism in (marker28[0].payload.get("mechanisms", ()) if marker28 else ())
            if isinstance(mechanism, Mapping)
        }

        positive = mechanisms.get("positive_linked", {})
        negative = mechanisms.get("negative_linked", {})
        no_value = mechanisms.get("no_value", {})
        unrelated = mechanisms.get("positive_unrelated", {})
        positive_ok = (
            positive.get("value_bonus", 0.0) > 0.0
            and positive.get("value_penalty") == 0.0
            and positive.get("value_adjusted_score", 0.0) > positive.get("base_mechanism_score", 0.0)
            and positive.get("value_adjusted_score", 0.0) - positive.get("base_mechanism_score", 0.0) <= MAX_VALUE_BONUS
        )
        negative_ok = (
            negative.get("value_penalty", 0.0) > 0.0
            and negative.get("value_adjusted_score", 0.0) < negative.get("base_mechanism_score", 0.0)
            and negative.get("base_mechanism_score", 0.0) - negative.get("value_adjusted_score", 0.0) <= MAX_VALUE_PENALTY
        )
        no_value_ok = (
            no_value.get("value_bonus") == 0.0
            and no_value.get("value_penalty") == 0.0
            and no_value.get("value_adjusted_score") == no_value.get("base_mechanism_score")
            and no_value.get("value_trace", {}).get("has_value_feedback") is False
        )
        relevance_ok = (
            positive.get("value_trace", {}).get("linked_target_overlap", 0.0)
            > unrelated.get("value_trace", {}).get("linked_target_overlap", 0.0)
            and positive.get("value_bonus", 0.0) > unrelated.get("value_bonus", 0.0)
        )

        for operation in marker28:
            memory.add_event(operation)
        candidate_field = ActionCandidateField(id_gen)
        ActionProposer(registry).propose(2, memory, active_field, candidate_field, SystemState())
        candidates = candidate_field.debug_snapshot()
        action_metadata_ok = any(
            item.get("source_metadata", {}).get("source") == "expsm_mechanism_search"
            and item.get("source_metadata", {}).get("source_experience_id") == "positive_linked"
            and item.get("source_metadata", {}).get("source_base_mechanism_score") is not None
            and item.get("source_metadata", {}).get("source_value_adjusted_score") is not None
            and item.get("source_metadata", {}).get("source_value_bonus", 0.0) > 0.0
            and isinstance(item.get("source_metadata", {}).get("source_value_trace"), dict)
            for item in candidates
        )

        payload_fields_ok = all(
            key in positive
            for key in (
                "mechanism_score",
                "base_mechanism_score",
                "value_adjusted_score",
                "value_bonus",
                "value_penalty",
                "value_balance",
                "value_confidence",
                "value_risk",
                "value_target_relevance",
                "value_trace",
            )
        )
    real_expsm_unchanged = real_expsm_before == _sha256(REAL_EXPSM)
    real_akbsm_unchanged = real_akbsm_before == _sha256(REAL_AKBSM)
    passed = (
        bool(marker28)
        and payload_fields_ok
        and positive_ok
        and negative_ok
        and no_value_ok
        and relevance_ok
        and action_metadata_ok
        and real_expsm_unchanged
        and real_akbsm_unchanged
    )
    print("Value-aware mechanism scoring verification:")
    print(f"  marker 28 value fields: {'yes' if payload_fields_ok else 'no'}")
    print(f"  positive bonus: {'yes' if positive_ok else 'no'}")
    print(f"  negative penalty: {'yes' if negative_ok else 'no'}")
    print(f"  no-value old behavior: {'yes' if no_value_ok else 'no'}")
    print(f"  target-linked relevance: {'yes' if relevance_ok else 'no'}")
    print(f"  action candidate metadata: {'yes' if action_metadata_ok else 'no'}")
    print(f"  real ExpSM unchanged: {'yes' if real_expsm_unchanged else 'no'}")
    print(f"  real AKBSM unchanged: {'yes' if real_akbsm_unchanged else 'no'}")
    if positive:
        print(
            "  positive example: "
            f"base={positive.get('base_mechanism_score')} adjusted={positive.get('value_adjusted_score')} "
            f"bonus={positive.get('value_bonus')} penalty={positive.get('value_penalty')} "
            f"balance={positive.get('value_balance')} confidence={positive.get('value_confidence')} "
            f"risk={positive.get('value_risk')}"
        )
    if negative:
        print(
            "  negative example: "
            f"base={negative.get('base_mechanism_score')} adjusted={negative.get('value_adjusted_score')} "
            f"bonus={negative.get('value_bonus')} penalty={negative.get('value_penalty')} "
            f"balance={negative.get('value_balance')} confidence={negative.get('value_confidence')} "
            f"risk={negative.get('value_risk')}"
        )
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _demo_store(target: str, action: str, context: str, unrelated_target: str) -> dict[str, Any]:
    base_record = {
        "if": [context],
        "then": [action],
        "result": [target],
        "recommendation": [target],
        "confidence": 0.72,
        "repeatability": 0.62,
        "hits": 3,
        "misses": 1,
        "status": 2,
    }
    records: dict[str, dict[str, Any]] = {}
    for experience_id in ("positive_linked", "positive_unrelated", "negative_linked", "no_value"):
        records[experience_id] = dict(base_record)
    records["positive_linked"]["value_feedback"] = _feedback_block(target, "positive", 2, 0, 1.54, 0.0)
    records["positive_unrelated"]["value_feedback"] = _feedback_block(unrelated_target, "positive", 2, 0, 1.54, 0.0)
    records["negative_linked"]["value_feedback"] = _feedback_block(target, "negative", 0, 3, 0.0, 2.25)
    return {"experience": records, "reflexes": {}}


def _feedback_block(
    target_pattern: str,
    direction: str,
    positive_count: int,
    negative_count: int,
    positive_total: float,
    negative_total: float,
) -> dict[str, Any]:
    return {
        "positive_count": positive_count,
        "negative_count": negative_count,
        "mixed_count": 0,
        "inconclusive_count": 0,
        "positive_strength_total": positive_total,
        "negative_strength_total": negative_total,
        "mixed_strength_total": 0.0,
        "last_review_id": f"review_{direction}",
        "last_updated_tick": 4,
        "target_links": [
            {
                "target_pattern_id": target_pattern,
                "target_kind": "positive_target",
                "target_role_names": ["needed_target", "safety_target"],
                "value_direction": direction,
                "candidate_strength": 0.78,
                "evidence_strength": 0.76,
                "satisfaction_status": "satisfied" if direction == "positive" else "worsened",
                "recommended_future_operation": (
                    "increase_value_confidence" if direction == "positive" else "increase_avoidance_warning"
                ),
            }
        ],
    }


def _memory_with_target(
    registry: PatternRegistry,
    target: str,
    context: str,
) -> tuple[ContextMemory, IdGenerator, ActiveContextField]:
    id_gen = IdGenerator()
    memory = ContextMemory(id_gen, registry)
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.EVALUATION_TARGET_OBSERVED,
            1,
            "verify_value_aware_mechanism_scoring",
            None,
            {
                "target_observation_id": "evaluation_target_value_scoring",
                "pattern_id": target,
                "target_kind": "positive_target",
                "target_role_names": ["needed_target", "safety_target"],
                "target_score": 0.7,
                "evaluation_dimensions": {"need": 0.7, "safety": 0.7, "priority": 0.6},
            },
        )
    )
    active_field = ActiveContextField()
    active_field.activate(context, 0.6, 1, "verify", "context", ttl=5)
    return memory, id_gen, active_field


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
