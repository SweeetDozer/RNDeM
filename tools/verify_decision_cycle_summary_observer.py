from pathlib import Path
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.action.action_candidate import ActionCandidate
from clc.action.action_scoring import score_breakdown
from clc.action.decision_cycle_summary_observer import DecisionCycleSummaryObserver
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.experience.causal_trace import CausalTrace
from clc.experience.learnability_filter import LearnabilityFilter
from clc.system.system_state import SystemState


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="decision_cycle_summary_verify_") as temp_dir:
        registry = PatternRegistry(Path(temp_dir) / "pattern_manifest.json")
        id_gen = IdGenerator()
        observer = DecisionCycleSummaryObserver(id_gen, registry)
        results = {
            "clean_high_confidence_selection": _case_clean_high(id_gen, registry, observer),
            "value_influenced_selection": _case_value_influenced(id_gen, registry, observer),
            "guard_constrained_high_severity": _case_guard_high(id_gen, registry, observer),
            "uncertain_narrow_or_tie": _case_uncertain(id_gen, registry, observer),
            "missing_guard_audit": _case_missing_guard(id_gen, registry, observer),
            "no_selector_or_learning_effect": _case_no_selector_or_learning_effect(registry, observer),
        }

    print("Decision cycle summary observer verification:")
    for key, value in results.items():
        print(f"  {key}: {'yes' if value else 'no'}")
    passed = all(results.values())
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_clean_high(id_gen: IdGenerator, registry: PatternRegistry, observer: DecisionCycleSummaryObserver) -> bool:
    summary = _run_summary(
        id_gen,
        registry,
        observer,
        1,
        _decision_audit(
            registry,
            "decision_clean",
            "decision_audit_clean",
            registry.id("action_preserve_integrity"),
            audit_confidence="clear_win",
            score_margin=0.25,
            value_influence="none_or_tiny",
            value_scope="no_value",
        ),
        _guard_audit(
            registry,
            "decision_clean",
            "action_guard_audit_clean",
            guard_effect="no_blocked_candidates",
            severity="none",
        ),
    )
    cycle = summary.get("cycle_summary", {})
    return cycle.get("cycle_status") == "clean_selection" and cycle.get("cycle_confidence") == "high"


def _case_value_influenced(id_gen: IdGenerator, registry: PatternRegistry, observer: DecisionCycleSummaryObserver) -> bool:
    summary = _run_summary(
        id_gen,
        registry,
        observer,
        2,
        _decision_audit(
            registry,
            "decision_value",
            "decision_audit_value",
            registry.id("action_inspect_pattern"),
            audit_confidence="clear_win",
            score_margin=0.18,
            value_influence="positive_bonus",
            value_scope="target_specific",
            value_delta=0.033,
            ranking_effect="promoted",
            source="expsm_mechanism_search",
        ),
        _guard_audit(
            registry,
            "decision_value",
            "action_guard_audit_value",
            guard_effect="no_blocked_candidates",
            severity="none",
        ),
    )
    cycle = summary.get("cycle_summary", {})
    flags = set(cycle.get("flags", ()))
    decision = summary.get("decision_summary", {})
    return (
        cycle.get("cycle_status") == "value_influenced_selection"
        and "value_promoted_selected" in flags
        and "target_specific_value_used" in flags
        and decision.get("value_delta") == 0.033
    )


def _case_guard_high(id_gen: IdGenerator, registry: PatternRegistry, observer: DecisionCycleSummaryObserver) -> bool:
    summary = _run_summary(
        id_gen,
        registry,
        observer,
        3,
        _decision_audit(
            registry,
            "decision_guard_high",
            "decision_audit_guard_high",
            registry.id("action_preserve_integrity"),
            audit_confidence="clear_win",
            score_margin=0.12,
            value_influence="none_or_tiny",
            value_scope="no_value",
        ),
        _guard_audit(
            registry,
            "decision_guard_high",
            "action_guard_audit_guard_high",
            guard_effect="blocked_high_score_candidate",
            severity="high",
            blocked_count=1,
        ),
    )
    cycle = summary.get("cycle_summary", {})
    flags = set(cycle.get("flags", ()))
    return (
        cycle.get("cycle_status") in {"risky_or_constrained_selection", "guard_constrained_selection"}
        and cycle.get("cycle_confidence") == "low"
        and "guard_blocked_high_score" in flags
    )


def _case_uncertain(id_gen: IdGenerator, registry: PatternRegistry, observer: DecisionCycleSummaryObserver) -> bool:
    summary = _run_summary(
        id_gen,
        registry,
        observer,
        4,
        _decision_audit(
            registry,
            "decision_uncertain",
            "decision_audit_uncertain",
            registry.id("action_continue_observation"),
            audit_confidence="narrow_win",
            score_margin=0.035,
            value_influence="none_or_tiny",
            value_scope="no_value",
        ),
        _guard_audit(
            registry,
            "decision_uncertain",
            "action_guard_audit_uncertain",
            guard_effect="no_blocked_candidates",
            severity="none",
        ),
    )
    cycle = summary.get("cycle_summary", {})
    flags = set(cycle.get("flags", ()))
    return (
        cycle.get("cycle_status") == "uncertain_selection"
        and cycle.get("cycle_confidence") in {"medium", "low"}
        and "narrow_decision" in flags
    )


def _case_missing_guard(id_gen: IdGenerator, registry: PatternRegistry, observer: DecisionCycleSummaryObserver) -> bool:
    summary = _run_summary(
        id_gen,
        registry,
        observer,
        5,
        _decision_audit(
            registry,
            "decision_missing_guard",
            "decision_audit_missing_guard",
            registry.id("action_wait_more_data"),
            audit_confidence="single_candidate",
            score_margin=None,
            value_influence="none_or_tiny",
            value_scope="no_value",
        ),
        None,
    )
    guard = summary.get("guard_summary", {})
    flags = set(summary.get("cycle_summary", {}).get("flags", ()))
    return guard.get("available") is False and "guard_summary_missing" in flags


def _case_no_selector_or_learning_effect(registry: PatternRegistry, observer: DecisionCycleSummaryObserver) -> bool:
    candidate = ActionCandidate(
        candidate_id="candidate_cycle_score_check",
        pattern_id=registry.id("action_preserve_integrity"),
        activation=0.7,
        confidence=0.8,
        urgency=0.5,
        risk=0.1,
        cost=0.1,
        source_pattern_ids=(),
        source_event_ids=(),
        source_metadata={},
        created_at_tick=1,
        updated_at_tick=1,
    )
    before = score_breakdown(candidate)
    after = score_breakdown(candidate)
    marker_check = OperationMarker.EXPERIENCE_CANDIDATE not in {
        operation.marker for operation in observer.run(99, ContextMemory(IdGenerator(), registry), SystemState())
    }
    trace = CausalTrace(
        source_outcome_id="outcome_decision_cycle_skip",
        source_outcome_status="inconclusive",
        decision_event_ids=(),
        effect_event_ids=(),
        prediction_event_ids=(),
        decision_patterns=(registry.id("decision_cycle_summary"),),
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
    return before == after and marker_check and classification.get("learnable") is False


def _run_summary(
    id_gen: IdGenerator,
    registry: PatternRegistry,
    observer: DecisionCycleSummaryObserver,
    tick: int,
    decision_audit: dict[str, object],
    guard_audit: dict[str, object] | None,
) -> dict[str, object]:
    memory = ContextMemory(id_gen, registry)
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.DECISION_AUDIT_OBSERVED,
            tick,
            "verify_decision_cycle_summary",
            None,
            decision_audit,
        )
    )
    if guard_audit is not None:
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.ACTION_GUARD_AUDIT_OBSERVED,
                tick,
                "verify_decision_cycle_summary",
                None,
                guard_audit,
            )
        )
    operations = observer.run(tick, memory, SystemState())
    if len(operations) != 1:
        raise AssertionError(f"Expected one decision cycle summary, got {len(operations)}")
    if operations[0].marker != OperationMarker.DECISION_CYCLE_SUMMARY:
        raise AssertionError(f"Unexpected marker {operations[0].marker}")
    return dict(operations[0].payload)


def _decision_audit(
    registry: PatternRegistry,
    decision_id: str,
    audit_id: str,
    action_pattern: str,
    *,
    audit_confidence: str,
    score_margin: float | None,
    value_influence: str,
    value_scope: str,
    value_delta: float | None = None,
    ranking_effect: str = "unchanged",
    source: str = "baseline/internal",
) -> dict[str, object]:
    return {
        "decision_audit_id": audit_id,
        "audit_kind": registry.id("decision_audit_observed"),
        "source_decision_id": decision_id,
        "selected": {
            "candidate_id": f"candidate_{decision_id}",
            "action_pattern": action_pattern,
            "action_debug_name": registry.debug_name(action_pattern),
            "source": source,
            "final_score": 0.51,
            "source_experience_id": "2" if source == "expsm_mechanism_search" else None,
            "source_mechanism_search_id": "expsm_mechanism_search_001" if source == "expsm_mechanism_search" else None,
        },
        "alternatives": [
            {
                "candidate_id": f"candidate_{decision_id}_alt",
                "action_pattern": registry.id("action_reduce_load"),
                "action_debug_name": "action_reduce_load",
                "source": "baseline/internal",
                "final_score": 0.40,
            }
        ],
        "audit": {
            "audit_confidence": audit_confidence,
            "score_margin": score_margin,
            "value_influence": value_influence,
            "value_scope": value_scope,
            "value_delta": value_delta,
            "ranking_effect": ranking_effect,
        },
        "activation": 0.45,
        "ttl": 8,
    }


def _guard_audit(
    registry: PatternRegistry,
    decision_id: str,
    audit_id: str,
    *,
    guard_effect: str,
    severity: str,
    blocked_count: int = 0,
) -> dict[str, object]:
    blocked = [
        {
            "candidate_id": f"blocked_{index}",
            "action_pattern_id": registry.id("action_exit_consolidation_mode"),
            "action_pattern_name": "action_exit_consolidation_mode",
            "final_score": 0.82,
            "guard_status": "blocked",
            "guard_reason": "blocked_by_mode",
            "would_have_ranked_above_selected": True,
        }
        for index in range(blocked_count)
    ]
    return {
        "action_guard_audit_id": audit_id,
        "audit_kind": registry.id("action_guard_audit_observed"),
        "source_decision_id": decision_id,
        "summary": {
            "proposed_count": blocked_count + 1,
            "allowed_count": 1,
            "blocked_count": blocked_count,
            "guard_effect": guard_effect,
            "severity": severity,
        },
        "selected": {
            "action_pattern_id": registry.id("action_preserve_integrity"),
            "action_pattern_name": "action_preserve_integrity",
            "final_score": 0.51,
            "guard_status": "allowed",
            "guard_reason": "allowed",
        },
        "blocked_candidates": blocked,
        "activation": 0.45,
        "ttl": 8,
    }


if __name__ == "__main__":
    raise SystemExit(main())
