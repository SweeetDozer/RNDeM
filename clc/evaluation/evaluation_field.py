from dataclasses import dataclass, field


DIMENSION_KEYS = ("usefulness", "harmfulness", "need", "want", "avoid", "safety", "priority")
DECAY = 0.92
MIN_VALUE = 0.03
MAX_REFS = 12


@dataclass
class EvaluationEntry:
    pattern_id: str
    usefulness: float = 0.0
    harmfulness: float = 0.0
    need: float = 0.0
    want: float = 0.0
    avoid: float = 0.0
    safety: float = 0.0
    priority: float = 0.0
    activation: float = 0.0
    ttl: int = 0
    last_updated_tick: int = 0
    sources: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)


class EvaluationField:
    """Runtime-only field of current value-like evaluations."""

    def __init__(self) -> None:
        self._entries: dict[str, EvaluationEntry] = {}
        self._last_decay_tick: int | None = None

    def update_pattern(
        self,
        pattern_id: str,
        dimensions: dict[str, float],
        *,
        source_id: str,
        scope: str,
        activation: float,
        ttl: int,
        tick: int,
    ) -> None:
        entry = self._entries.get(pattern_id)
        if entry is None:
            entry = EvaluationEntry(pattern_id=pattern_id, last_updated_tick=tick)
            self._entries[pattern_id] = entry
        for key in DIMENSION_KEYS:
            old = getattr(entry, key)
            incoming = _clamp(dimensions.get(key, 0.0))
            setattr(entry, key, _clamp(max(old * 0.85, incoming)))
        entry.activation = _clamp(max(entry.activation * 0.85, activation))
        entry.ttl = max(entry.ttl, int(ttl))
        entry.last_updated_tick = tick
        _append_unique_bounded(entry.sources, source_id)
        _append_unique_bounded(entry.scopes, scope)

    def decay(self, tick: int) -> None:
        if self._last_decay_tick == tick:
            return
        self._last_decay_tick = tick
        remaining: dict[str, EvaluationEntry] = {}
        for pattern_id, entry in self._entries.items():
            entry.ttl = max(0, entry.ttl - 1)
            for key in DIMENSION_KEYS:
                setattr(entry, key, _clamp(getattr(entry, key) * DECAY))
            entry.activation = _clamp(entry.activation * DECAY)
            if entry.ttl <= 0 and all(getattr(entry, key) < MIN_VALUE for key in DIMENSION_KEYS):
                continue
            remaining[pattern_id] = entry
        self._entries = remaining

    def get(self, pattern_id: str) -> EvaluationEntry | None:
        return self._entries.get(pattern_id)

    def top(self, n: int = 10) -> list[EvaluationEntry]:
        return sorted(self._entries.values(), key=_entry_score, reverse=True)[:n]

    def snapshot(self) -> dict:
        return {
            entry.pattern_id: {
                "usefulness": round(entry.usefulness, 3),
                "harmfulness": round(entry.harmfulness, 3),
                "need": round(entry.need, 3),
                "want": round(entry.want, 3),
                "avoid": round(entry.avoid, 3),
                "safety": round(entry.safety, 3),
                "priority": round(entry.priority, 3),
                "activation": round(entry.activation, 3),
                "ttl": entry.ttl,
                "last_updated_tick": entry.last_updated_tick,
                "sources": list(entry.sources),
                "scopes": list(entry.scopes),
            }
            for entry in self.top()
        }


def _entry_score(entry: EvaluationEntry) -> float:
    return max(*(getattr(entry, key) for key in DIMENSION_KEYS), entry.activation)


def _append_unique_bounded(values: list[str], value: str) -> None:
    if not value or value in values:
        return
    values.append(value)
    del values[:-MAX_REFS]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
