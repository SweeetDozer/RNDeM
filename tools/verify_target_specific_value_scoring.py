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
from clc.expsm.expsm_mechanism_search import ExpSMMechanismSearch
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


REAL_EXPSM = PROJECT_ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"
REAL_AKBSM = PROJECT_ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"


def main() -> int:
    real_expsm_before = _sha256(REAL_EXPSM)
    real_akbsm_before = _sha256(REAL_AKBSM)
    with tempfile.TemporaryDirectory(prefix="rndem_target_value_scoring_") as temp_dir:
        temp_root = Path(temp_dir)
        registry = PatternRegistry(temp_root / "Memory" / "pattern_manifest.json")
        target_a = registry.id("state_integrity_preservation")
        target_b = registry.id("state_load_reduced")
        unrelated = registry.id("evaluation_avoidance_target")
        action = registry.id("action_preserve_integrity")
        context = registry.id("internal_tension")
        expsm_path = temp_root / "Memory" / "ExpSM" / "ExpSM_data.json"
        expsm_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(expsm_path, _demo_store(target_a, target_b, unrelated, action, context))

        mechanisms, marker28, memory, id_gen, active_field = _run_search(registry, expsm_path, target_a, context, target_b)
        helpful = mechanisms.get("exact_helpful", {})
        risky = mechanisms.get("exact_risky", {})
        unrelated_record = mechanisms.get("unrelated_value", {})
        associated = mechanisms.get("associated_helpful", {})

        helpful_ok = (
            helpful.get("value_scoring_mode") == "target_specific"
            and helpful.get("target_specific_value_bonus", 0.0) > helpful.get("generic_value_bonus", 0.0)
            and helpful.get("value_adjusted_score", 0.0) > helpful.get("base_mechanism_score", 0.0)
        )
        risky_ok = (
            risky.get("value_scoring_mode") == "target_specific"
            and risky.get("target_specific_value_penalty", 0.0) > risky.get("generic_value_penalty", 0.0)
            and risky.get("value_adjusted_score", 1.0) < risky.get("base_mechanism_score", 0.0)
        )
        unrelated_ok = (
            unrelated_record.get("target_helpful_match_score") == 0.0
            and unrelated_record.get("target_risky_match_score") == 0.0
            and unrelated_record.get("value_scoring_mode") in {"generic_fallback", "no_value"}
        )
        associated_ok = (
            associated.get("value_scoring_mode") == "target_specific"
            and associated.get("target_helpful_match_score", 0.0) > 0.0
            and associated.get("target_specific_value_bonus", 0.0) > 0.0
        )

        for operation in marker28:
            memory.add_event(operation)
        candidate_field = ActionCandidateField(id_gen)
        ActionProposer(registry).propose(2, memory, active_field, candidate_field, SystemState())
        candidates = candidate_field.debug_snapshot()
        action_metadata_ok = any(
            item.get("source_metadata", {}).get("source") == "expsm_mechanism_search"
            and item.get("source_metadata", {}).get("source_experience_id") == "exact_helpful"
            and item.get("source_metadata", {}).get("source_value_scoring_mode") == "target_specific"
            and item.get("source_metadata", {}).get("source_target_helpful_match_score") is not None
            and item.get("source_metadata", {}).get("source_target_risky_match_score") is not None
            and isinstance(item.get("source_metadata", {}).get("source_target_value_trace"), dict)
            for item in candidates
        )
        payload_fields_ok = all(
            key in helpful
            for key in (
                "value_scoring_mode",
                "target_specific_value_bonus",
                "target_specific_value_penalty",
                "generic_value_bonus",
                "generic_value_penalty",
                "target_helpful_match_score",
                "target_risky_match_score",
                "target_value_trace",
            )
        )
    real_expsm_unchanged = real_expsm_before == _sha256(REAL_EXPSM)
    real_akbsm_unchanged = real_akbsm_before == _sha256(REAL_AKBSM)
    passed = (
        bool(marker28)
        and payload_fields_ok
        and helpful_ok
        and risky_ok
        and unrelated_ok
        and associated_ok
        and action_metadata_ok
        and real_expsm_unchanged
        and real_akbsm_unchanged
    )
    print("Target-specific value scoring verification:")
    print(f"  marker 28 target value fields: {'yes' if payload_fields_ok else 'no'}")
    print(f"  exact helpful beats generic: {'yes' if helpful_ok else 'no'}")
    print(f"  exact risky beats generic: {'yes' if risky_ok else 'no'}")
    print(f"  unrelated no false target match: {'yes' if unrelated_ok else 'no'}")
    print(f"  associated pattern match: {'yes' if associated_ok else 'no'}")
    print(f"  action candidate metadata: {'yes' if action_metadata_ok else 'no'}")
    print(f"  real ExpSM unchanged: {'yes' if real_expsm_unchanged else 'no'}")
    print(f"  real AKBSM unchanged: {'yes' if real_akbsm_unchanged else 'no'}")
    if helpful:
        print(
            "  helpful example: "
            f"base={helpful.get('base_mechanism_score')} adjusted={helpful.get('value_adjusted_score')} "
            f"mode={helpful.get('value_scoring_mode')} "
            f"generic_bonus={helpful.get('generic_value_bonus')} "
            f"target_bonus={helpful.get('target_specific_value_bonus')} "
            f"helpful_match={helpful.get('target_helpful_match_score')}"
        )
    if risky:
        print(
            "  risky example: "
            f"base={risky.get('base_mechanism_score')} adjusted={risky.get('value_adjusted_score')} "
            f"mode={risky.get('value_scoring_mode')} "
            f"generic_penalty={risky.get('generic_value_penalty')} "
            f"target_penalty={risky.get('target_specific_value_penalty')} "
            f"risky_match={risky.get('target_risky_match_score')}"
        )
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _run_search(
    registry: PatternRegistry,
    expsm_path: Path,
    target_a: str,
    context: str,
    target_b: str,
) -> tuple[dict[str, Mapping[str, Any]], list[ContextOperation], ContextMemory, IdGenerator, ActiveContextField]:
    memory, id_gen, active_field = _memory_with_target(registry, target_a, context)
    association_field = AKBSMAssociationField()
    association_field.update_association(
        target_a,
        target_b,
        relation_type="related_to",
        score=0.82,
        distance=1,
        path=[target_a, target_b],
        source_probe_id="probe_associated_value",
        target_kind="positive_target",
        target_roles=["needed_target", "safety_target"],
        activation=0.7,
        ttl=10,
        tick=1,
    )
    view = ValueFeedbackMemoryView(registry, expsm_path)
    search = ExpSMMechanismSearch(id_gen, registry, expsm_path, view)
    operations = search.run(1, memory, active_field, EvaluationField(), association_field, SystemState())
    marker28 = [operation for operation in operations if operation.marker == OperationMarker.EXPSM_MECHANISM_SEARCH]
    mechanisms = {
        mechanism.get("experience_id"): mechanism
        for mechanism in (marker28[0].payload.get("mechanisms", ()) if marker28 else ())
        if isinstance(mechanism, Mapping)
    }
    return mechanisms, marker28, memory, id_gen, active_field


def _demo_store(target_a: str, target_b: str, unrelated: str, action: str, context: str) -> dict[str, Any]:
    base = {
        "if": [context],
        "then": [action],
        "result": [target_a],
        "recommendation": [target_a],
        "confidence": 0.72,
        "repeatability": 0.62,
        "hits": 3,
        "misses": 1,
        "status": 2,
    }
    records: dict[str, dict[str, Any]] = {}
    for record_id in ("exact_helpful", "exact_risky", "unrelated_value", "associated_helpful", "no_value"):
        records[record_id] = dict(base)
    records["exact_helpful"]["value_feedback"] = _feedback(target_a, "positive", "positive_target", ["needed_target", "safety_target"], 3, 0, 2.4, 0.0)
    records["exact_risky"]["value_feedback"] = _feedback(target_a, "negative", "positive_target", ["needed_target", "safety_target"], 0, 3, 0.0, 2.55)
    records["unrelated_value"]["value_feedback"] = _feedback(unrelated, "positive", "avoidance_target", ["avoidance_target"], 3, 0, 2.4, 0.0)
    records["associated_helpful"]["value_feedback"] = _feedback(target_b, "positive", "positive_target", ["needed_target"], 2, 0, 1.6, 0.0)
    return {"experience": records, "reflexes": {}}


def _feedback(
    target_pattern: str,
    direction: str,
    target_kind: str,
    roles: list[str],
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
        "last_review_id": f"review_{direction}_{target_pattern}",
        "last_updated_tick": 5,
        "target_links": [
            {
                "target_pattern_id": target_pattern,
                "target_kind": target_kind,
                "target_role_names": roles,
                "value_direction": direction,
                "candidate_strength": max(positive_total, negative_total) / max(positive_count + negative_count, 1),
                "evidence_strength": 0.8,
                "satisfaction_status": "satisfied" if direction == "positive" else "worsened",
                "recommended_future_operation": (
                    "increase_value_confidence" if direction == "positive" else "increase_avoidance_warning"
                ),
            }
        ],
    }


def _memory_with_target(registry: PatternRegistry, target: str, context: str) -> tuple[ContextMemory, IdGenerator, ActiveContextField]:
    id_gen = IdGenerator()
    memory = ContextMemory(id_gen, registry)
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.EVALUATION_TARGET_OBSERVED,
            1,
            "verify_target_specific_value_scoring",
            None,
            {
                "target_observation_id": "evaluation_target_specific_value",
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
