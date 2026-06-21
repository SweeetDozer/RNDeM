from dataclasses import replace

from clc.field.active_pattern import ActivePattern


class ActiveContextField:
    """Current active pattern field; history remains in ContextMemory."""

    def __init__(self) -> None:
        self._patterns: dict[str, ActivePattern] = {}

    def activate(
        self,
        pattern_id: str,
        amount: float,
        tick: int,
        kind: str,
        source_event_id: str | None = None,
        decay_rate: float = 0.1,
        ttl: int | None = None,
        mode: str = "reinforce",
    ) -> None:
        amount = _clamp(amount)
        if amount <= 0.0 and mode != "set":
            return
        existing = self._patterns.get(pattern_id)
        sources = (source_event_id,) if source_event_id else ()
        expires_at_tick = tick + ttl if ttl is not None else None
        if existing is None:
            self._patterns[pattern_id] = ActivePattern(
                pattern_id=pattern_id,
                activation=amount,
                kind=kind,
                source_event_ids=sources,
                created_at_tick=tick,
                updated_at_tick=tick,
                last_decay_tick=tick,
                decay_rate=decay_rate,
                ttl=ttl,
                expires_at_tick=expires_at_tick,
            )
            return
        activation = _activation_for_mode(existing.activation, amount, mode)
        merged_sources = tuple(dict.fromkeys(existing.source_event_ids + sources))
        self._patterns[pattern_id] = replace(
            existing,
            activation=activation,
            kind=kind,
            source_event_ids=merged_sources,
            updated_at_tick=tick,
            last_decay_tick=tick,
            decay_rate=min(existing.decay_rate, decay_rate),
            ttl=ttl,
            expires_at_tick=expires_at_tick,
        )

    def decay_all(self, tick: int) -> None:
        remaining: dict[str, ActivePattern] = {}
        for pattern_id, pattern in self._patterns.items():
            if pattern.expires_at_tick is not None and tick >= pattern.expires_at_tick:
                continue
            last_decay_tick = pattern.last_decay_tick if pattern.last_decay_tick is not None else pattern.updated_at_tick
            elapsed = max(0, tick - last_decay_tick)
            if elapsed <= 0:
                remaining[pattern_id] = pattern
                continue
            activation = _clamp(pattern.activation - pattern.decay_rate * elapsed)
            if activation <= 0.01:
                continue
            remaining[pattern_id] = replace(pattern, activation=activation, last_decay_tick=tick)
        self._patterns = remaining

    def suppress(self, pattern_id: str, amount: float = 1.0) -> None:
        existing = self._patterns.get(pattern_id)
        if existing is None:
            return
        activation = _clamp(existing.activation * (1.0 - _clamp(amount)))
        if activation <= 0.01:
            del self._patterns[pattern_id]
            return
        self._patterns[pattern_id] = replace(existing, activation=activation)

    def get_top_patterns(self, limit: int = 10) -> list[ActivePattern]:
        return sorted(self._patterns.values(), key=lambda pattern: pattern.activation, reverse=True)[:limit]

    def get_patterns_above(self, threshold: float) -> list[ActivePattern]:
        return [pattern for pattern in self.get_top_patterns(limit=len(self._patterns)) if pattern.activation >= threshold]

    def debug_snapshot(self) -> list[dict]:
        return [
            {
                "pattern_id": pattern.pattern_id,
                "activation": round(pattern.activation, 3),
                "kind": pattern.kind,
                "ttl": pattern.ttl,
                "expires_at_tick": pattern.expires_at_tick,
                "updated_at_tick": pattern.updated_at_tick,
                "last_decay_tick": pattern.last_decay_tick,
            }
            for pattern in self.get_top_patterns()
        ]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _activation_for_mode(old: float, amount: float, mode: str) -> float:
    if mode == "reinforce":
        return _clamp(old + amount * (1.0 - old))
    if mode == "set":
        return _clamp(amount)
    if mode == "max":
        return _clamp(max(old, amount))
    raise ValueError(f"Unsupported active field activation mode: {mode}")
