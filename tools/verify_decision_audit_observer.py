from pathlib import Path
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.action.decision_audit_observer import DecisionAuditObserver
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.experience.causal_trace import CausalTrace
from clc.experience.learnability_filter import LearnabilityFilter
from clc.system.system_state import SystemState


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="decision_audit_verify_") as temp_dir:
        registry = PatternRegistry(Path(temp_dir) / "pattern_manifest.json")
        id_gen = IdGenerator()
        memory = ContextMemory(id_gen, registry)
        observer = DecisionAuditObserver(id_gen, registry)

        results = {
            "clear_win_no_value": _case_clear_win(memory, observer, id_gen, registry),
            "target_specific_positive_bonus": _case_positive_bonus(memory, observer, id_gen, registry),
            "negative_penalty_demotion": _case_negative_penalty(memory, observer, id_gen, registry),
            "alternatives_bounded_sorted": _case_bounded_sorted(memory, observer, id_gen, registry),
            "no_learning_marker": _case_no_learning_marker(observer, registry),
        }

    print("Decision audit observer verification:")
    for key, value in results.items():
        print(f"  {key}: {'yes' if value else 'no'}")
    passed = all(results.values())
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_clear_win(
    memory: ContextMemory,
    observer: DecisionAuditObserver,
    id_gen: IdGenerator,
    registry: PatternRegistry,
) -> bool:
    op = _decision_op(
        id_gen,
        1,
        "decision_clear",
        registry.id("action_preserve_integrity"),
        0.82,
        [
            _candidate("candidate_clear_selected", registry.id("action_preserve_integrity"), 0.82, selected=True),
            _candidate("candidate_clear_alt", registry.id("action_reduce_load"), 0.50),
        ],
    )
    memory.add_event(op)
    audit = _single_audit(observer.run(1, memory, SystemState()))
    audit_data = audit.get("audit", {})
    return (
        audit_data.get("audit_confidence") == "clear_win"
        and audit_data.get("value_influence") == "none_or_tiny"
        and audit_data.get("value_scope") == "no_value"
    )


def _case_positive_bonus(
    memory: ContextMemory,
    observer: DecisionAuditObserver,
    id_gen: IdGenerator,
    registry: PatternRegistry,
) -> bool:
    target = registry.id("evaluation_needed_target")
    selected = _candidate(
        "candidate_positive_selected",
        registry.id("action_inspect_pattern"),
        0.55,
        selected=True,
        source="expsm_mechanism_search",
        source_base_mechanism_score=0.50,
        source_value_adjusted_score=0.54,
        source_mechanism_score=0.54,
        source_value_scoring_mode="target_specific",
        source_target_pattern_id=target,
        source_target_specific_value_bonus=0.04,
    )
    alternative = _candidate(
        "candidate_positive_alt",
        registry.id("action_continue_observation"),
        0.50,
        source="expsm_mechanism_search",
        source_base_mechanism_score=0.49,
        source_value_adjusted_score=0.49,
        source_mechanism_score=0.49,
        source_value_scoring_mode="no_value",
    )
    memory.add_event(_decision_op(id_gen, 2, "decision_positive", selected["action_pattern"], 0.55, [selected, alternative]))
    audit = _single_audit(observer.run(2, memory, SystemState()))
    audit_data = audit.get("audit", {})
    return (
        audit_data.get("audit_confidence") == "narrow_win"
        and audit_data.get("value_influence") == "positive_bonus"
        and audit_data.get("value_scope") == "target_specific"
        and float(audit_data.get("value_delta", 0.0)) > 0.0
    )


def _case_negative_penalty(
    memory: ContextMemory,
    observer: DecisionAuditObserver,
    id_gen: IdGenerator,
    registry: PatternRegistry,
) -> bool:
    selected = _candidate(
        "candidate_negative_selected",
        registry.id("action_reduce_load"),
        0.70,
        selected=True,
        source="expsm_mechanism_search",
        source_base_mechanism_score=0.60,
        source_value_adjusted_score=0.52,
        source_mechanism_score=0.52,
        source_value_scoring_mode="target_specific",
        source_target_specific_value_penalty=0.08,
    )
    alternative = _candidate(
        "candidate_negative_alt",
        registry.id("action_continue_observation"),
        0.65,
        source="expsm_mechanism_search",
        source_base_mechanism_score=0.55,
        source_value_adjusted_score=0.56,
        source_mechanism_score=0.56,
        source_value_scoring_mode="target_specific",
        source_target_specific_value_bonus=0.01,
    )
    memory.add_event(_decision_op(id_gen, 3, "decision_negative", selected["action_pattern"], 0.70, [selected, alternative]))
    audit = _single_audit(observer.run(3, memory, SystemState()))
    audit_data = audit.get("audit", {})
    return (
        audit_data.get("value_influence") == "negative_penalty"
        and audit_data.get("ranking_effect") in {"demoted", "unchanged"}
        and float(audit_data.get("value_delta", 0.0)) < 0.0
    )


def _case_bounded_sorted(
    memory: ContextMemory,
    observer: DecisionAuditObserver,
    id_gen: IdGenerator,
    registry: PatternRegistry,
) -> bool:
    selected = _candidate("candidate_bound_selected", registry.id("action_preserve_integrity"), 0.95, selected=True)
    alternatives = [
        _candidate(f"candidate_bound_alt_{index}", registry.id("action_continue_observation"), 0.90 - index * 0.03)
        for index in range(12)
    ]
    memory.add_event(_decision_op(id_gen, 4, "decision_bounded", selected["action_pattern"], 0.95, [selected] + alternatives))
    audit = _single_audit(observer.run(4, memory, SystemState()))
    alternatives_out = audit.get("alternatives", [])
    scores = [float(item.get("final_score", 0.0)) for item in alternatives_out]
    return len(alternatives_out) == 8 and scores == sorted(scores, reverse=True)


def _case_no_learning_marker(observer: DecisionAuditObserver, registry: PatternRegistry) -> bool:
    marker_check = OperationMarker.EXPERIENCE_CANDIDATE not in {
        operation.marker for operation in observer.run(99, ContextMemory(IdGenerator(), registry), SystemState())
    }
    trace = CausalTrace(
        source_outcome_id="outcome_audit_skip",
        source_outcome_status="inconclusive",
        decision_event_ids=(),
        effect_event_ids=(),
        prediction_event_ids=(),
        decision_patterns=(registry.id("decision_audit_observed"),),
        effect_patterns=(),
        predicted_patterns=(),
        outcome_patterns=(),
        context_label_event_ids=(),
        context_frame_ids=(),
        context_window_ids=(),
        context_active_patterns=(),
        context_prediction_event_ids=(),
    )
    classification = LearnabilityFilter(registry).classify_trace(trace)
    return marker_check and classification.get("learnable") is False


def _decision_op(
    id_gen: IdGenerator,
    tick: int,
    decision_id: str,
    action_pattern: str,
    score: float,
    candidates: list[dict[str, object]],
) -> ContextOperation:
    payload = {
        "decision_id": decision_id,
        "decision_pattern_id": action_pattern,
        "candidate_score": score,
        "score_breakdown": {"final_score": score},
        "decision_candidate_audit_snapshot": candidates,
    }
    selected = next((candidate for candidate in candidates if candidate.get("selected")), candidates[0])
    payload.update({key: value for key, value in selected.items() if key.startswith("source") or key == "source"})
    return ContextOperation(id_gen.next("op"), OperationMarker.INTERNAL_DECISION, tick, "verify_decision_audit", None, payload)


def _candidate(
    candidate_id: str,
    action_pattern: str,
    final_score: float,
    selected: bool = False,
    source: str | None = None,
    **metadata: object,
) -> dict[str, object]:
    candidate = {
        "candidate_id": candidate_id,
        "action_pattern": action_pattern,
        "final_score": final_score,
        "score_breakdown": {"final_score": final_score},
        "activation": 0.7,
        "confidence": 0.7,
        "urgency": 0.4,
        "risk": 0.2,
        "cost": 0.1,
        "selected": selected,
    }
    if source is not None:
        candidate["source"] = source
    candidate.update(metadata)
    return candidate


def _single_audit(operations: list[ContextOperation]) -> dict[str, object]:
    if len(operations) != 1:
        raise AssertionError(f"Expected one audit operation, got {len(operations)}")
    operation = operations[0]
    if operation.marker != OperationMarker.DECISION_AUDIT_OBSERVED:
        raise AssertionError(f"Unexpected marker {operation.marker}")
    return dict(operation.payload)


if __name__ == "__main__":
    raise SystemExit(main())
