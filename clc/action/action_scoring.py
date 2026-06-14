from clc.action.action_candidate import ActionCandidate


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
    if candidate.source_metadata.get("source") == "expsm_activation":
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


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
