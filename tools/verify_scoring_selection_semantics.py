from __future__ import annotations

from pathlib import Path
import sys
from collections.abc import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.action.action_candidate import ActionCandidate  # noqa: E402
from clc.action.action_candidate_field import ActionCandidateField  # noqa: E402
from clc.action.action_scoring import score_breakdown  # noqa: E402
from clc.action.candidate_sources import (  # noqa: E402
    SOURCE_EXPSM_ACTIVATION,
    SOURCE_EXPSM_MECHANISM_SEARCH,
    is_expsm_activation_source,
    is_expsm_mechanism_search_source,
)
from clc.action.decision_selector import DecisionSelector  # noqa: E402
from clc.core.ids import IdGenerator  # noqa: E402
from clc.core.pattern_registry import PatternRegistry  # noqa: E402


MIGRATED_FILES = (
    PROJECT_ROOT / "clc" / "action" / "action_scoring.py",
    PROJECT_ROOT / "clc" / "action" / "decision_selector.py",
)


def main() -> int:
    registry = PatternRegistry(PROJECT_ROOT / "Memory" / "pattern_manifest.json")
    checks = {
        "normal action semantic metadata": _normal_action_semantics(registry),
        "non-actions not action material": _non_action_semantics(registry),
        "default candidate scoring preserved": _default_scoring_preserved(registry),
        "expsm activation source scoring preserved": _activation_scoring_preserved(registry),
        "mechanism source value metadata preserved": _mechanism_value_scoring_preserved(registry),
        "selector activation snapshot preserved": _selector_activation_snapshot_preserved(registry),
        "stable source helpers classify sources": _source_helpers_ok(),
        "no debug_name semantic dependency": _no_debug_name_dependency(),
    }
    passed = all(checks.values())
    print("Scoring/selection semantic migration verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _normal_action_semantics(registry: PatternRegistry) -> bool:
    action_id = registry.id("action_preserve_integrity")
    effect_id = registry.id("state_integrity_preservation")
    return (
        registry.is_action(action_id)
        and registry.has_tag(action_id, "ordinary_action")
        and registry.semantic_class(effect_id) in {"effect", "target"}
        and registry.has_tag(effect_id, "ordinary_effect")
    )


def _non_action_semantics(registry: PatternRegistry) -> bool:
    names = (
        "aud_freq_440",
        "prediction_future_state",
        "outcome_confirmed",
        "decision_audit_observed",
    )
    return all(not registry.is_action(registry.id(name)) for name in names)


def _default_scoring_preserved(registry: PatternRegistry) -> bool:
    candidate = _candidate(registry, activation=0.8, confidence=0.6, urgency=0.4, risk=0.2, cost=0.1)
    breakdown = score_breakdown(candidate)
    expected = round(0.6 * 0.45 + 0.4 * 0.25 + 0.8 * 0.15 - 0.2 * 0.25 - 0.1 * 0.15, 3)
    return breakdown.get("base_score") == expected and breakdown.get("final_score") == expected


def _activation_scoring_preserved(registry: PatternRegistry) -> bool:
    candidate = _candidate(
        registry,
        activation=0.7,
        confidence=0.65,
        urgency=0.45,
        risk=0.04,
        cost=0.12,
        source_metadata={
            "source": SOURCE_EXPSM_ACTIVATION,
            "source_match_score": 0.9,
            "source_viability": 0.8,
            "source_effective_confidence": 0.7,
            "source_repeatability": 0.6,
        },
    )
    breakdown = score_breakdown(candidate)
    return (
        is_expsm_activation_source(candidate.source_metadata)
        and "memory_score" in breakdown
        and "expsm_bonus" in breakdown
        and breakdown["final_score"] == 0.571
    )


def _mechanism_value_scoring_preserved(registry: PatternRegistry) -> bool:
    candidate = _candidate(
        registry,
        activation=0.75,
        confidence=0.7,
        urgency=0.5,
        risk=0.05,
        cost=0.14,
        source_metadata={
            "source": SOURCE_EXPSM_MECHANISM_SEARCH,
            "source_mechanism_score": 0.82,
            "source_base_mechanism_score": 0.78,
            "source_value_adjusted_score": 0.82,
            "source_value_bonus": 0.08,
            "source_value_penalty": 0.02,
            "source_value_balance": 0.5,
            "source_value_confidence": 0.6,
            "source_value_risk": 0.1,
            "source_viability": 0.75,
            "source_effective_confidence": 0.7,
            "source_repeatability": 0.65,
            "source_target_score": 0.9,
        },
    )
    breakdown = score_breakdown(candidate)
    return (
        is_expsm_mechanism_search_source(candidate.source_metadata)
        and breakdown.get("source_value_bonus") == 0.08
        and breakdown.get("source_value_penalty") == 0.02
        and breakdown.get("source_value_balance") == 0.5
        and breakdown.get("source_target_score") == 0.9
        and breakdown.get("final_score") == 0.608
    )


def _selector_activation_snapshot_preserved(registry: PatternRegistry) -> bool:
    id_gen = IdGenerator()
    field = ActionCandidateField(id_gen)
    action_id = registry.id("action_preserve_integrity")
    field.propose(
        action_id,
        amount=0.85,
        tick=1,
        confidence=0.85,
        urgency=0.5,
        risk=0.04,
        cost=0.12,
        source_metadata={
            "source": SOURCE_EXPSM_ACTIVATION,
            "source_experience_id": "exp_activation",
            "source_activation_id": "act_1",
            "source_match_score": 0.9,
            "source_viability": 0.8,
            "source_effective_confidence": 0.75,
            "source_repeatability": 0.7,
        },
    )
    field.propose(
        action_id,
        amount=0.65,
        tick=1,
        confidence=0.72,
        urgency=0.45,
        risk=0.05,
        cost=0.14,
        source_metadata={
            "source": SOURCE_EXPSM_MECHANISM_SEARCH,
            "source_experience_id": "exp_mechanism",
            "source_mechanism_search_id": "search_1",
            "source_mechanism_score": 0.7,
            "source_base_mechanism_score": 0.7,
            "source_value_adjusted_score": 0.7,
            "source_value_bonus": 0.0,
            "source_value_penalty": 0.0,
            "source_value_confidence": 0.0,
            "source_value_risk": 0.0,
            "source_viability": 0.7,
            "source_effective_confidence": 0.7,
            "source_repeatability": 0.7,
            "source_target_score": 0.7,
        },
    )
    decision = DecisionSelector(id_gen, decision_threshold=0.1).select(1, field)
    if decision is None:
        return False
    snapshot = decision.payload.get("expsm_candidate_snapshot")
    if not isinstance(snapshot, Sequence) or isinstance(snapshot, (str, bytes)) or len(snapshot) != 1:
        return False
    return snapshot[0].get("activation_id") == "act_1"


def _source_helpers_ok() -> bool:
    return (
        is_expsm_activation_source({"source": SOURCE_EXPSM_ACTIVATION})
        and not is_expsm_activation_source({"source": SOURCE_EXPSM_MECHANISM_SEARCH})
        and is_expsm_mechanism_search_source({"source": SOURCE_EXPSM_MECHANISM_SEARCH})
        and not is_expsm_mechanism_search_source({"source": "manual"})
    )


def _no_debug_name_dependency() -> bool:
    return all("debug_name" not in path.read_text(encoding="utf-8") for path in MIGRATED_FILES)


def _candidate(
    registry: PatternRegistry,
    *,
    activation: float,
    confidence: float,
    urgency: float,
    risk: float,
    cost: float,
    source_metadata: dict[str, object] | None = None,
) -> ActionCandidate:
    return ActionCandidate(
        candidate_id="candidate_verify",
        pattern_id=registry.id("action_preserve_integrity"),
        activation=activation,
        confidence=confidence,
        urgency=urgency,
        risk=risk,
        cost=cost,
        source_pattern_ids=(),
        source_event_ids=(),
        source_metadata=dict(source_metadata or {}),
        created_at_tick=1,
        updated_at_tick=1,
    )


if __name__ == "__main__":
    raise SystemExit(main())
