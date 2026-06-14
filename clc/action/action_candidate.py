from dataclasses import dataclass


@dataclass(frozen=True)
class ActionCandidate:
    candidate_id: str
    pattern_id: str
    activation: float
    confidence: float
    urgency: float
    risk: float
    cost: float
    source_pattern_ids: tuple[str, ...]
    source_event_ids: tuple[str, ...]
    source_metadata: dict[str, object]
    created_at_tick: int
    updated_at_tick: int
    ttl: int | None = None
    expires_at_tick: int | None = None
    decay_rate: float = 0.1
