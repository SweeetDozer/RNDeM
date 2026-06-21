from __future__ import annotations

import copy
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
from clc.evaluation.evaluation_field import EvaluationField
from clc.evaluation.evaluation_field_updater import EvaluationFieldUpdater
from clc.evaluation.target_satisfaction_observer import TargetSatisfactionObserver
from clc.evaluation.value_feedback_candidate_builder import ValueFeedbackCandidateBuilder
from clc.evaluation.value_feedback_review_gate import ValueFeedbackReviewGate
from clc.evaluation.value_feedback_update_writer import ValueFeedbackUpdateWriter
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


REAL_EXPSM = PROJECT_ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"
SEMANTIC_CORE_KEYS = ("if", "then", "result", "recommendation")
TECHNICAL_KEYS = ("hits", "misses", "confidence", "repeatability")


def main() -> int:
    real_hash_before = _sha256(REAL_EXPSM)
    with tempfile.TemporaryDirectory(prefix="rndem_negative_value_feedback_") as temp_dir:
        temp_root = Path(temp_dir)
        registry = PatternRegistry(temp_root / "Memory" / "pattern_manifest.json")
        worsened_ready_update = _case_worsened_ready_update(temp_root, registry)
        not_satisfied_wait_no_write = _case_not_satisfied_wait_no_write(temp_root, registry)
        avoidance_reduced_positive_update = _case_avoidance_reduced_positive_update(temp_root, registry)
    real_unchanged = real_hash_before == _sha256(REAL_EXPSM)
    passed = worsened_ready_update and not_satisfied_wait_no_write and avoidance_reduced_positive_update and real_unchanged
    print("negative value feedback loop:")
    print(f"  worsened_ready_update: {'PASS' if worsened_ready_update else 'FAIL'}")
    print(f"  not_satisfied_wait_no_write: {'PASS' if not_satisfied_wait_no_write else 'FAIL'}")
    print(f"  avoidance_reduced_positive_update: {'PASS' if avoidance_reduced_positive_update else 'FAIL'}")
    print(f"  real_expsm_unchanged: {'PASS' if real_unchanged else 'FAIL'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_worsened_ready_update(temp_root: Path, registry: PatternRegistry) -> bool:
    expsm_path = _write_demo_expsm(temp_root, "worsened")
    memory, id_gen, field, evaluation_field = _context(registry)
    _add_mechanism_decision(memory, id_gen, registry, "neg", "positive_target", ["needed_target"], "preserve_target", 1)
    _add_effect(memory, id_gen, registry, "neg", 2)
    _add_outcome(memory, id_gen, registry, "neg_a", "effect_neg", "failed", 3)
    _add_outcome(memory, id_gen, registry, "neg_b", "effect_neg", "failed", 4)
    _add_evaluation_signal(
        memory,
        id_gen,
        registry,
        "neg",
        "outcome_neg_a",
        4,
        {"harmfulness": 0.98, "avoid": 0.92, "usefulness": 0.0, "safety": 0.0},
        target_patterns=[],
    )
    marker29, marker30, marker31, marker32 = _run_chain(5, memory, id_gen, registry, field, evaluation_field, expsm_path)
    after = _read_json(expsm_path)
    record = after["experience"]["2"]
    return (
        marker29.get("satisfaction_status") == "worsened"
        and marker29.get("satisfaction_score", 0.0) < 0.0
        and marker30.get("candidate_type") == "value_negative_candidate"
        and marker30.get("value_direction") == "negative"
        and marker30.get("recommended_future_operation") == "increase_avoidance_warning"
        and marker31.get("review_decision") == "ready"
        and marker31.get("review_reason") == "strong_negative_value_feedback"
        and marker32.get("value_direction") == "negative"
        and record["value_feedback"]["negative_count"] == 1
        and record["value_feedback"]["negative_strength_total"] > 0.0
        and record["value_feedback"]["positive_count"] == 0
        and record["value_feedback"]["target_links"][-1]["satisfaction_status"] == "worsened"
        and record["value_feedback"]["target_links"][-1]["recommended_future_operation"] == "increase_avoidance_warning"
        and _semantic_and_technical_unchanged(_demo_expsm_store(), after)
    )


def _case_not_satisfied_wait_no_write(temp_root: Path, registry: PatternRegistry) -> bool:
    expsm_path = _write_demo_expsm(temp_root, "wait")
    before = _read_json(expsm_path)
    memory, id_gen, field, evaluation_field = _context(registry)
    target = registry.id("state_integrity_preservation")
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.TARGET_SATISFACTION_OBSERVED,
            1,
            "verify_negative_value_feedback_loop",
            None,
            {
                "target_satisfaction_id": "target_satisfaction_wait",
                "source_decision_id": "decision_wait",
                "source_experience_id": "2",
                "source_mechanism_search_id": "mechanism_wait",
                "source_target_observation_id": "target_observation_wait",
                "target_pattern_id": target,
                "target_pattern_name": registry.debug_name(target),
                "target_kind": "positive_target",
                "target_role_names": ["needed_target"],
                "mechanism_purpose": "preserve_target",
                "mechanism_score": 0.50,
                "satisfaction_status": "not_satisfied",
                "satisfaction_score": -0.33,
                "evidence_strength": 0.40,
                "memory_modified": False,
                "permanent_memory_modified": False,
                "expsm_modified": False,
                "akbsm_modified": False,
                "activation": 0.45,
                "ttl": 10,
            },
        )
    )
    marker30, marker31, marker32 = _run_candidate_review_update(2, memory, id_gen, registry, field, expsm_path)
    after = _read_json(expsm_path)
    return (
        marker30.get("candidate_type") == "value_mixed_candidate"
        and marker30.get("value_direction") == "mixed_or_unclear"
        and marker30.get("recommended_future_operation") == "request_more_evidence"
        and marker31.get("review_decision") == "wait"
        and marker32 == {}
        and before == after
    )


def _case_avoidance_reduced_positive_update(temp_root: Path, registry: PatternRegistry) -> bool:
    expsm_path = _write_demo_expsm(temp_root, "avoidance")
    memory, id_gen, field, evaluation_field = _context(registry)
    _add_mechanism_decision(
        memory,
        id_gen,
        registry,
        "avoid",
        "avoidance_target",
        ["avoidance_target", "harmful_target"],
        "mitigate_harm",
        1,
    )
    _add_effect(memory, id_gen, registry, "avoid", 2)
    _add_outcome(memory, id_gen, registry, "avoid_a", "effect_avoid", "confirmed", 3)
    _add_outcome(memory, id_gen, registry, "avoid_b", "effect_avoid", "confirmed", 4)
    _add_evaluation_signal(
        memory,
        id_gen,
        registry,
        "avoid",
        "outcome_avoid_a",
        4,
        {"harmfulness": 0.0, "avoid": 0.0, "usefulness": 0.82, "safety": 0.90},
        target_patterns=[],
    )
    marker29, marker30, marker31, marker32 = _run_chain(5, memory, id_gen, registry, field, evaluation_field, expsm_path)
    after = _read_json(expsm_path)
    record = after["experience"]["2"]
    return (
        marker29.get("satisfaction_status") in {"satisfied", "partially_satisfied"}
        and marker30.get("candidate_type") == "value_positive_candidate"
        and marker30.get("value_direction") == "positive"
        and marker31.get("review_decision") == "ready"
        and marker32.get("value_direction") == "positive"
        and record["value_feedback"]["positive_count"] == 1
        and record["value_feedback"]["negative_count"] == 0
        and _semantic_and_technical_unchanged(_demo_expsm_store(), after)
    )


def _run_chain(
    tick: int,
    memory: ContextMemory,
    id_gen: IdGenerator,
    registry: PatternRegistry,
    field: ActiveContextField,
    evaluation_field: EvaluationField,
    expsm_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    EvaluationFieldUpdater().run(tick - 1, memory, evaluation_field)
    observer = TargetSatisfactionObserver(id_gen, registry)
    observations = observer.run(tick, memory, field, evaluation_field, SystemState(mode="consolidation"))
    for operation in observations:
        memory.add_event(operation)
    marker29 = _first_payload(observations, OperationMarker.TARGET_SATISFACTION_OBSERVED)
    marker30, marker31, marker32 = _run_candidate_review_update(tick + 1, memory, id_gen, registry, field, expsm_path)
    return marker29, marker30, marker31, marker32


def _run_candidate_review_update(
    tick: int,
    memory: ContextMemory,
    id_gen: IdGenerator,
    registry: PatternRegistry,
    field: ActiveContextField,
    expsm_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    state = SystemState(mode="consolidation")
    builder = ValueFeedbackCandidateBuilder(id_gen, registry)
    gate = ValueFeedbackReviewGate(id_gen, registry)
    writer = ValueFeedbackUpdateWriter(id_gen, registry, expsm_path)
    candidates = builder.run(tick, memory, state)
    for operation in candidates:
        memory.add_event(operation)
    reviews = gate.run(tick + 1, memory, state)
    for operation in reviews:
        memory.add_event(operation)
    updates = writer.run(tick + 2, memory, state)
    for operation in updates:
        memory.add_event(operation)
    return (
        _first_payload(candidates, OperationMarker.VALUE_FEEDBACK_CANDIDATE),
        _first_payload(reviews, OperationMarker.VALUE_FEEDBACK_REVIEW),
        _first_payload(updates, OperationMarker.VALUE_FEEDBACK_UPDATED),
    )


def _context(registry: PatternRegistry) -> tuple[ContextMemory, IdGenerator, ActiveContextField, EvaluationField]:
    id_gen = IdGenerator()
    return ContextMemory(id_gen, registry), id_gen, ActiveContextField(), EvaluationField()


def _add_mechanism_decision(
    memory: ContextMemory,
    id_gen: IdGenerator,
    registry: PatternRegistry,
    suffix: str,
    target_kind: str,
    roles: list[str],
    purpose: str,
    tick: int,
) -> None:
    target = registry.id("state_integrity_preservation")
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.INTERNAL_DECISION,
            tick,
            "verify_negative_value_feedback_loop",
            None,
            {
                "decision_id": f"decision_{suffix}",
                "decision_pattern_id": registry.id("action_preserve_integrity"),
                "source": "expsm_mechanism_search",
                "source_experience_id": "2",
                "source_mechanism_search_id": f"mechanism_{suffix}",
                "source_target_observation_id": f"target_observation_{suffix}",
                "source_target_pattern_id": target,
                "source_target_kind": target_kind,
                "source_target_roles": roles,
                "source_mechanism_purpose": purpose,
                "source_mechanism_score": 0.90,
                "activation": 0.72,
                "ttl": 8,
            },
        )
    )


def _add_effect(memory: ContextMemory, id_gen: IdGenerator, registry: PatternRegistry, suffix: str, tick: int) -> None:
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.INTERNAL_ACTION_EFFECT,
            tick,
            "verify_negative_value_feedback_loop",
            None,
            {
                "effect_id": f"effect_{suffix}",
                "source_decision_id": f"decision_{suffix}",
                "effect_pattern_id": registry.id("state_observation_continues"),
                "activation": 0.6,
                "ttl": 6,
            },
        )
    )


def _add_outcome(
    memory: ContextMemory,
    id_gen: IdGenerator,
    registry: PatternRegistry,
    suffix: str,
    source_effect_id: str,
    status: str,
    tick: int,
) -> None:
    decision_suffix = suffix.split("_", 1)[0]
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.OUTCOME_EVALUATION,
            tick,
            "verify_negative_value_feedback_loop",
            None,
            {
                "outcome_id": f"outcome_{suffix}",
                "source_event_id": source_effect_id,
                "source_decision_id": f"decision_{decision_suffix}",
                "source_kind": "effect",
                "outcome_status": status,
                "outcome_pattern_id": registry.id(f"outcome_{status}"),
                "matched_patterns": [],
                "activation": 0.75,
                "ttl": 6,
            },
        )
    )


def _add_evaluation_signal(
    memory: ContextMemory,
    id_gen: IdGenerator,
    registry: PatternRegistry,
    suffix: str,
    source_event_id: str,
    tick: int,
    dimensions: dict[str, float],
    target_patterns: list[str],
) -> None:
    dims = {
        "usefulness": 0.0,
        "need": 0.0,
        "want": 0.0,
        "safety": 0.0,
        "priority": 0.0,
        "harmfulness": 0.0,
        "avoid": 0.0,
    }
    dims.update(dimensions)
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.EVALUATION_SIGNAL,
            tick,
            "verify_negative_value_feedback_loop",
            None,
            {
                "evaluation_id": f"evaluation_signal_{suffix}",
                "source_event_id": source_event_id,
                "source_marker": OperationMarker.OUTCOME_EVALUATION.value,
                "evaluation_scope": "negative_value_feedback_loop",
                "target_patterns": target_patterns,
                "evaluation_dimensions": dims,
                "activation": 0.8,
                "ttl": 10,
            },
        )
    )


def _first_payload(operations: list[ContextOperation], marker: OperationMarker) -> dict[str, Any]:
    for operation in operations:
        if operation.marker == marker:
            return dict(operation.payload)
    return {}


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
                    "target_links": [],
                },
            }
        },
        "reflexes": {},
    }


def _write_demo_expsm(temp_root: Path, case_name: str) -> Path:
    expsm_path = temp_root / case_name / "Memory" / "ExpSM" / "ExpSM_data.json"
    expsm_path.parent.mkdir(parents=True, exist_ok=True)
    expsm_path.write_text(json.dumps(_demo_expsm_store(), indent=2), encoding="utf-8")
    return expsm_path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _semantic_and_technical_unchanged(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_record = before["experience"]["2"]
    after_record = after["experience"]["2"]
    for key in SEMANTIC_CORE_KEYS + TECHNICAL_KEYS:
        if copy.deepcopy(before_record.get(key)) != copy.deepcopy(after_record.get(key)):
            return False
    return True


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
