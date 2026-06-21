from clc.action.action_candidate import ActionCandidate
from clc.action.candidate_sources import (
    is_expsm_activation_source,
    is_expsm_mechanism_search_source,
)


def score_breakdown(candidate: ActionCandidate) -> dict[str, float]:
    base_confidence = _clamp(candidate.confidence)
    urgency = _clamp(candidate.urgency)
    activation = _clamp(candidate.activation)
    risk_penalty = _clamp(candidate.risk) * 0.25
    cost_penalty = _clamp(candidate.cost) * 0.15
    base_score = (
        base_confidence * 0.45
        + urgency * 0.25
        + activation * 0.15
        - risk_penalty
        - cost_penalty
    )
    base_score = _clamp(base_score)
    breakdown = {
        "base_confidence": round(base_confidence, 3),
        "urgency": round(urgency, 3),
        "activation": round(activation, 3),
        "risk_penalty": round(risk_penalty, 3),
        "cost_penalty": round(cost_penalty, 3),
        "base_score": round(base_score, 3),
    }
    if is_expsm_activation_source(candidate.source_metadata):
        source_match_score = _metadata_float(candidate, "source_match_score")
        source_viability = _metadata_float(candidate, "source_viability")
        source_effective_confidence = _metadata_float(candidate, "source_effective_confidence")
        source_repeatability = _metadata_float(candidate, "source_repeatability", default=None)
        if source_repeatability is None:
            memory_score = (
                source_match_score * 0.40
                + source_viability * 0.30
                + source_effective_confidence * 0.30
            )
        else:
            memory_score = (
                source_match_score * 0.35
                + source_viability * 0.25
                + source_effective_confidence * 0.25
                + source_repeatability * 0.15
            )
            breakdown["source_repeatability"] = round(source_repeatability, 3)
        memory_score = _clamp(memory_score)
        final_score = _clamp(base_score * 0.70 + memory_score * 0.30)
        breakdown.update(
            {
                "source_match_score": round(source_match_score, 3),
                "source_viability": round(source_viability, 3),
                "source_effective_confidence": round(source_effective_confidence, 3),
                "memory_score": round(memory_score, 3),
                "expsm_bonus": round(final_score - base_score, 3),
                "final_score": round(final_score, 3),
            }
        )
        return breakdown
    if is_expsm_mechanism_search_source(candidate.source_metadata):
        source_mechanism_score = _metadata_float(candidate, "source_mechanism_score")
        source_base_mechanism_score = _metadata_float(candidate, "source_base_mechanism_score")
        source_value_adjusted_score = _metadata_float(candidate, "source_value_adjusted_score")
        source_value_bonus = _metadata_float(candidate, "source_value_bonus")
        source_value_penalty = _metadata_float(candidate, "source_value_penalty")
        source_value_balance = _metadata_signed_float(candidate, "source_value_balance", default=None)
        source_value_confidence = _metadata_float(candidate, "source_value_confidence")
        source_value_risk = _metadata_float(candidate, "source_value_risk")
        source_viability = _metadata_float(candidate, "source_viability")
        source_effective_confidence = _metadata_float(candidate, "source_effective_confidence")
        source_repeatability = _metadata_float(candidate, "source_repeatability")
        source_target_score = _metadata_float(candidate, "source_target_score")
        mechanism_source_score = _clamp(
            source_mechanism_score * 0.40
            + source_viability * 0.20
            + source_effective_confidence * 0.20
            + source_repeatability * 0.10
            + source_target_score * 0.10
        )
        final_score = _clamp(base_score * 0.65 + mechanism_source_score * 0.35)
        breakdown.update(
            {
                "source_mechanism_score": round(source_mechanism_score, 3),
                "source_base_mechanism_score": round(source_base_mechanism_score, 3),
                "source_value_adjusted_score": round(source_value_adjusted_score, 3),
                "source_value_bonus": round(source_value_bonus, 3),
                "source_value_penalty": round(source_value_penalty, 3),
                "source_value_confidence": round(source_value_confidence, 3),
                "source_value_risk": round(source_value_risk, 3),
                "source_target_score": round(source_target_score, 3),
                "source_viability": round(source_viability, 3),
                "source_effective_confidence": round(source_effective_confidence, 3),
                "source_repeatability": round(source_repeatability, 3),
                "mechanism_source_score": round(mechanism_source_score, 3),
                "final_score": round(final_score, 3),
            }
        )
        if source_value_balance is not None:
            breakdown["source_value_balance"] = round(source_value_balance, 3)
        return breakdown
    breakdown["final_score"] = round(base_score, 3)
    return breakdown


def final_score(candidate: ActionCandidate) -> float:
    return score_breakdown(candidate)["final_score"]


def _metadata_float(candidate: ActionCandidate, key: str, default: float | None = 0.0) -> float | None:
    value = candidate.source_metadata.get(key, default)
    if value is None:
        return None
    try:
        return _clamp(float(value))
    except (TypeError, ValueError):
        return default


def _metadata_signed_float(candidate: ActionCandidate, key: str, default: float | None = 0.0) -> float | None:
    value = candidate.source_metadata.get(key, default)
    if value is None:
        return None
    try:
        return max(-1.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
