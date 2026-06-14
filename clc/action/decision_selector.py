from clc.action.action_candidate import ActionCandidate
from clc.action.action_candidate_field import ActionCandidateField
from clc.action.action_scoring import score_breakdown
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState


class DecisionSelector:
    """Selects one internal decision candidate and emits marker 7."""

    module_name = "decision_selector"

    def __init__(self, id_gen: IdGenerator, decision_threshold: float = 0.35, cooldown_ticks: int = 2) -> None:
        self.id_gen = id_gen
        self.decision_threshold = decision_threshold
        self.cooldown_ticks = cooldown_ticks

    def select(
        self,
        tick: int,
        candidate_field: ActionCandidateField,
        system_state: SystemState | None = None,
        mode_action_guard: ModeActionGuard | None = None,
    ) -> ContextOperation | None:
        scored: list[tuple[ActionCandidate, dict[str, float]]] = []
        for candidate in candidate_field.get_top_candidates(limit=20):
            if candidate_field.is_suppressed(candidate.pattern_id, tick):
                continue
            if system_state is not None and mode_action_guard is not None:
                adjusted = mode_action_guard.adjust_candidate(candidate, system_state, tick)
                if adjusted is None:
                    continue
                candidate = adjusted
            scored.append((candidate, score_breakdown(candidate)))
        if not scored:
            return None
        candidate, breakdown = max(scored, key=lambda item: item[1]["final_score"])
        score = breakdown["final_score"]
        if score < self.decision_threshold:
            return None
        payload = {
            "decision_id": self.id_gen.next("decision"),
            "decision_pattern_id": candidate.pattern_id,
            "system_mode_at_selection": system_state.mode if system_state is not None else None,
            "candidate_score": round(score, 3),
            "candidate_activation": round(candidate.activation, 3),
            "confidence": round(candidate.confidence, 3),
            "urgency": round(candidate.urgency, 3),
            "risk": round(candidate.risk, 3),
            "cost": round(candidate.cost, 3),
            "source_pattern_ids": list(candidate.source_pattern_ids),
            "source_event_ids": list(candidate.source_event_ids),
            "score_breakdown": breakdown,
            "ttl": 3,
            "activation": round(candidate.activation, 3),
        }
        expsm_candidates = _expsm_candidate_snapshot(scored, candidate)
        if expsm_candidates:
            payload["expsm_candidate_snapshot"] = expsm_candidates
        if candidate.source_metadata.get("source"):
            payload.update(candidate.source_metadata)
            payload["selected_action"] = candidate.pattern_id
        candidate_field.suppress(candidate.pattern_id, tick + self.cooldown_ticks)
        return ContextOperation(self.id_gen.next("op"), OperationMarker.INTERNAL_DECISION, tick, self.module_name, None, payload)


def _score(candidate: ActionCandidate) -> float:
    return score_breakdown(candidate)["final_score"]


def _expsm_candidate_snapshot(
    scored: list[tuple[ActionCandidate, dict[str, float]]],
    selected: ActionCandidate,
) -> list[dict[str, object]]:
    snapshot: list[dict[str, object]] = []
    for candidate, breakdown in scored:
        source = candidate.source_metadata
        if source.get("source") != "expsm_activation":
            continue
        snapshot.append(
            {
                "candidate_id": candidate.candidate_id,
                "experience_id": str(source.get("source_experience_id", "")),
                "activation_id": str(source.get("source_activation_id", "")),
                "action_pattern": candidate.pattern_id,
                "final_score": breakdown["final_score"],
                "score_breakdown": breakdown,
                "match_score": source.get("source_match_score"),
                "viability": source.get("source_viability"),
                "effective_confidence": source.get("source_effective_confidence"),
                "repeatability": source.get("source_repeatability"),
                "selected": candidate.candidate_id == selected.candidate_id,
            }
        )
    return snapshot
