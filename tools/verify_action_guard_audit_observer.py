from pathlib import Path
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.action.action_candidate import ActionCandidate
from clc.action.action_guard_audit_observer import ActionGuardAuditObserver
from clc.action.action_scoring import score_breakdown
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.experience.causal_trace import CausalTrace
from clc.experience.learnability_filter import LearnabilityFilter
from clc.system.system_state import SystemState


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="action_guard_audit_verify_") as temp_dir:
        registry = PatternRegistry(Path(temp_dir) / "pattern_manifest.json")
        id_gen = IdGenerator()
        observer = ActionGuardAuditObserver(id_gen, registry)
        state = SystemState()

        results = {
            "no_blocked_candidates": _case_no_blocked(id_gen, registry, observer, state),
            "low_score_blocked_candidate": _case_low_blocked(id_gen, registry, observer, state),
            "high_score_blocked_candidate": _case_high_blocked(id_gen, registry, observer, state),
            "selected_only_allowed_candidate": _case_selected_only_allowed(id_gen, registry, observer, state),
            "no_selector_or_learning_effect": _case_no_selector_or_learning_effect(registry, observer),
        }

    print("Action guard audit observer verification:")
    for key, value in results.items():
        print(f"  {key}: {'yes' if value else 'no'}")
    passed = all(results.values())
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_no_blocked(
    id_gen: IdGenerator,
    registry: PatternRegistry,
    observer: ActionGuardAuditObserver,
    state: SystemState,
) -> bool:
    selected = _candidate("candidate_a_selected", registry.id("action_preserve_integrity"), 0.70, "allowed")
    alt = _candidate("candidate_a_alt", registry.id("action_reduce_load"), 0.55, "allowed")
    audit = _run_case(id_gen, registry, observer, state, 1, "decision_guard_a", selected, [selected, alt])
    summary = audit.get("summary", {})
    return summary.get("guard_effect") == "no_blocked_candidates" and summary.get("severity") == "none"


def _case_low_blocked(
    id_gen: IdGenerator,
    registry: PatternRegistry,
    observer: ActionGuardAuditObserver,
    state: SystemState,
) -> bool:
    selected = _candidate("candidate_b_selected", registry.id("action_preserve_integrity"), 0.70, "allowed")
    blocked = _candidate("candidate_b_blocked", registry.id("action_exit_consolidation_mode"), 0.20, "blocked")
    audit = _run_case(id_gen, registry, observer, state, 2, "decision_guard_b", selected, [selected, blocked])
    summary = audit.get("summary", {})
    return summary.get("guard_effect") == "blocked_low_score_only" and summary.get("severity") in {"low", "medium"}


def _case_high_blocked(
    id_gen: IdGenerator,
    registry: PatternRegistry,
    observer: ActionGuardAuditObserver,
    state: SystemState,
) -> bool:
    selected = _candidate("candidate_c_selected", registry.id("action_preserve_integrity"), 0.51, "allowed")
    blocked = _candidate("candidate_c_blocked", registry.id("action_exit_consolidation_mode"), 0.82, "blocked")
    audit = _run_case(id_gen, registry, observer, state, 3, "decision_guard_c", selected, [selected, blocked])
    summary = audit.get("summary", {})
    blocked_out = audit.get("blocked_candidates", [{}])[0]
    return (
        summary.get("guard_effect") == "blocked_high_score_candidate"
        and summary.get("severity") == "high"
        and blocked_out.get("would_have_ranked_above_selected") is True
    )


def _case_selected_only_allowed(
    id_gen: IdGenerator,
    registry: PatternRegistry,
    observer: ActionGuardAuditObserver,
    state: SystemState,
) -> bool:
    selected = _candidate("candidate_d_selected", registry.id("action_preserve_integrity"), 0.52, "allowed")
    blocked_a = _candidate("candidate_d_blocked_a", registry.id("action_exit_consolidation_mode"), 0.30, "blocked")
    blocked_b = _candidate("candidate_d_blocked_b", registry.id("action_enter_consolidation_mode"), 0.25, "blocked")
    audit = _run_case(id_gen, registry, observer, state, 4, "decision_guard_d", selected, [selected, blocked_a, blocked_b])
    return audit.get("summary", {}).get("guard_effect") == "selected_was_only_allowed_candidate"


def _case_no_selector_or_learning_effect(registry: PatternRegistry, observer: ActionGuardAuditObserver) -> bool:
    candidate = ActionCandidate(
        candidate_id="candidate_score_check",
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
        source_outcome_id="outcome_guard_audit_skip",
        source_outcome_status="inconclusive",
        decision_event_ids=(),
        effect_event_ids=(),
        prediction_event_ids=(),
        decision_patterns=(registry.id("action_guard_audit_observed"),),
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


def _run_case(
    id_gen: IdGenerator,
    registry: PatternRegistry,
    observer: ActionGuardAuditObserver,
    state: SystemState,
    tick: int,
    decision_id: str,
    selected: dict[str, object],
    snapshot: list[dict[str, object]],
) -> dict[str, object]:
    memory = ContextMemory(id_gen, registry)
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.INTERNAL_DECISION,
            tick,
            "verify_action_guard_audit",
            None,
            {
                "decision_id": decision_id,
                "decision_pattern_id": selected["action_pattern_id"],
                "candidate_score": selected["final_score"],
                "system_mode_at_selection": state.mode,
                "guard_candidate_audit_snapshot": snapshot,
            },
        )
    )
    operations = observer.run(tick, memory, state)
    if len(operations) != 1:
        raise AssertionError(f"Expected one action guard audit, got {len(operations)}")
    if operations[0].marker != OperationMarker.ACTION_GUARD_AUDIT_OBSERVED:
        raise AssertionError(f"Unexpected marker {operations[0].marker}")
    return dict(operations[0].payload)


def _candidate(candidate_id: str, pattern_id: str, final_score: float, guard_status: str) -> dict[str, object]:
    return {
        "tick": 1,
        "candidate_id": candidate_id,
        "action_pattern_id": pattern_id,
        "source": "baseline/internal",
        "guard_status": guard_status,
        "guard_reason": "allowed" if guard_status == "allowed" else "blocked_by_mode",
        "final_score": final_score,
        "pre_guard_final_score": final_score,
        "score_breakdown": {"base_score": final_score, "final_score": final_score},
        "activation": 0.7,
        "confidence": 0.7,
        "urgency": 0.4,
        "risk": 0.2,
        "cost": 0.1,
    }


if __name__ == "__main__":
    raise SystemExit(main())
