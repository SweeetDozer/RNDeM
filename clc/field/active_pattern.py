from dataclasses import dataclass


@dataclass(frozen=True)
class ActivePattern:
    pattern_id: str
    activation: float
    kind: str
    source_event_ids: tuple[str, ...]
    created_at_tick: int
    updated_at_tick: int
    last_decay_tick: int | None = None
    decay_rate: float = 0.1
    ttl: int | None = None
    expires_at_tick: int | None = None
