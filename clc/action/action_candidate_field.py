from dataclasses import replace

from clc.action.action_candidate import ActionCandidate
from clc.action.action_scoring import final_score, score_breakdown
from clc.action.candidate_sources import (
    is_expsm_activation_source,
    is_expsm_mechanism_search_source,
)
from clc.core.ids import IdGenerator


class ActionCandidateField:
    """Current internal action candidates.

    This is not execution. It is a short-lived field of possible internal
    decisions represented by pattern ids.
    """

    def __init__(self, id_gen: IdGenerator) -> None:
        self.id_gen = id_gen
        self._candidates: dict[str, ActionCandidate] = {}
        self.cooldowns: dict[str, int] = {}

    def propose(
        self,
        pattern_id: str,
        amount: float,
        tick: int,
        confidence: float = 0.5,
        urgency: float = 0.0,
        risk: float = 0.0,
        cost: float = 0.1,
        source_pattern_ids: tuple[str, ...] = (),
        source_event_ids: tuple[str, ...] = (),
        source_metadata: dict[str, object] | None = None,
        ttl: int | None = 3,
        decay_rate: float = 0.1,
    ) -> None:
        if self.is_suppressed(pattern_id, tick):
            return
        amount = _clamp(amount)
        if amount <= 0.0:
            return
        expires_at_tick = tick + ttl if ttl is not None else None
        source_metadata = dict(source_metadata or {})
        candidate_key = self._candidate_key(pattern_id, source_metadata)
        existing = self._candidates.get(candidate_key)
        if existing is None:
            self._candidates[candidate_key] = ActionCandidate(
                candidate_id=self.id_gen.next("candidate"),
                pattern_id=pattern_id,
                activation=amount,
                confidence=_clamp(confidence),
                urgency=_clamp(urgency),
                risk=_clamp(risk),
                cost=_clamp(cost),
                source_pattern_ids=tuple(dict.fromkeys(source_pattern_ids)),
                source_event_ids=tuple(dict.fromkeys(source_event_ids)),
                source_metadata=source_metadata,
                created_at_tick=tick,
                updated_at_tick=tick,
                last_decay_tick=tick,
                ttl=ttl,
                expires_at_tick=expires_at_tick,
                decay_rate=decay_rate,
            )
            return
        activation = _clamp(existing.activation + amount * (1.0 - existing.activation))
        merged_metadata = dict(existing.source_metadata)
        merged_metadata.update(source_metadata)
        self._candidates[candidate_key] = replace(
            existing,
            activation=activation,
            confidence=max(existing.confidence, _clamp(confidence)),
            urgency=max(existing.urgency, _clamp(urgency)),
            risk=max(existing.risk, _clamp(risk)),
            cost=min(existing.cost, _clamp(cost)),
            source_pattern_ids=tuple(dict.fromkeys(existing.source_pattern_ids + source_pattern_ids)),
            source_event_ids=tuple(dict.fromkeys(existing.source_event_ids + source_event_ids)),
            source_metadata=merged_metadata,
            updated_at_tick=tick,
            last_decay_tick=tick,
            ttl=ttl,
            expires_at_tick=expires_at_tick,
            decay_rate=min(existing.decay_rate, decay_rate),
        )

    def decay_all(self, tick: int) -> None:
        remaining: dict[str, ActionCandidate] = {}
        for candidate_key, candidate in self._candidates.items():
            if candidate.expires_at_tick is not None and tick >= candidate.expires_at_tick:
                continue
            last_decay_tick = candidate.last_decay_tick if candidate.last_decay_tick is not None else candidate.updated_at_tick
            elapsed = max(0, tick - last_decay_tick)
            if elapsed <= 0:
                remaining[candidate_key] = candidate
                continue
            activation = _clamp(candidate.activation - candidate.decay_rate * elapsed)
            if activation <= 0.01:
                continue
            remaining[candidate_key] = replace(candidate, activation=activation, last_decay_tick=tick)
        self._candidates = remaining

    def get_top_candidates(self, limit: int = 10) -> list[ActionCandidate]:
        return sorted(self._candidates.values(), key=_candidate_sort_score, reverse=True)[:limit]

    def keep_only(self, pattern_ids: set[str]) -> None:
        self._candidates = {
            candidate_key: candidate
            for candidate_key, candidate in self._candidates.items()
            if candidate.pattern_id in pattern_ids
        }

    def remove(self, pattern_id: str) -> bool:
        removed = False
        for candidate_key, candidate in list(self._candidates.items()):
            if candidate.pattern_id == pattern_id:
                del self._candidates[candidate_key]
                removed = True
        return removed

    def suppress(self, pattern_id: str, until_tick: int) -> None:
        self.cooldowns[pattern_id] = until_tick
        for candidate_key, existing in list(self._candidates.items()):
            if existing.pattern_id == pattern_id:
                self._candidates[candidate_key] = replace(existing, activation=_clamp(existing.activation * 0.35))

    def is_suppressed(self, pattern_id: str, tick: int) -> bool:
        until_tick = self.cooldowns.get(pattern_id)
        if until_tick is None:
            return False
        if tick >= until_tick:
            del self.cooldowns[pattern_id]
            return False
        return True

    def debug_snapshot(self) -> list[dict]:
        return [
            {
                "candidate_id": candidate.candidate_id,
                "pattern_id": candidate.pattern_id,
                "activation": round(candidate.activation, 3),
                "confidence": round(candidate.confidence, 3),
                "urgency": round(candidate.urgency, 3),
                "risk": round(candidate.risk, 3),
                "cost": round(candidate.cost, 3),
                "score_breakdown": score_breakdown(candidate),
                "source_metadata": dict(candidate.source_metadata),
                "ttl": candidate.ttl,
                "expires_at_tick": candidate.expires_at_tick,
                "updated_at_tick": candidate.updated_at_tick,
                "last_decay_tick": candidate.last_decay_tick,
            }
            for candidate in self.get_top_candidates()
        ]

    def _candidate_key(self, pattern_id: str, source_metadata: dict[str, object]) -> str:
        if is_expsm_activation_source(source_metadata) and source_metadata.get("source_experience_id"):
            return "|".join(
                (
                    pattern_id,
                    "expsm",
                    str(source_metadata.get("source_experience_id", "")),
                    str(source_metadata.get("source_activation_id", "")),
                )
            )
        if is_expsm_mechanism_search_source(source_metadata) and source_metadata.get("source_experience_id"):
            return "|".join(
                (
                    pattern_id,
                    "expsm_mechanism",
                    str(source_metadata.get("source_experience_id", "")),
                    str(source_metadata.get("source_mechanism_search_id", "")),
                )
            )
        return pattern_id


def _candidate_sort_score(candidate: ActionCandidate) -> float:
    return final_score(candidate)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
