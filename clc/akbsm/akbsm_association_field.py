from dataclasses import dataclass, field


DECAY = 0.92
MIN_SCORE = 0.03
MAX_PATHS = 5
MAX_PROBES = 12
MAX_TARGET_KINDS = 8
MAX_TARGET_ROLES = 12


@dataclass
class AssociationEntry:
    source_pattern_id: str
    associated_pattern_id: str
    relation_type: str | None = None
    score: float = 0.0
    distance: int = 1
    activation: float = 0.0
    ttl: int = 0
    last_updated_tick: int = 0
    paths: list[list[str]] = field(default_factory=list)
    source_probe_ids: list[str] = field(default_factory=list)
    target_kinds: list[str] = field(default_factory=list)
    target_roles: list[str] = field(default_factory=list)


class AKBSMAssociationField:
    """Runtime-only aggregation of observed AKBSM association facts."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str | None], AssociationEntry] = {}
        self._last_decay_tick: int | None = None

    def update_association(
        self,
        source_pattern_id: str,
        associated_pattern_id: str,
        *,
        relation_type: str | None,
        score: float,
        distance: int,
        path: list[str] | None,
        source_probe_id: str,
        target_kind: str | None,
        target_roles: list[str],
        activation: float,
        ttl: int,
        tick: int,
    ) -> None:
        key = (str(source_pattern_id), str(associated_pattern_id), relation_type)
        entry = self._entries.get(key)
        if entry is None:
            entry = AssociationEntry(
                source_pattern_id=str(source_pattern_id),
                associated_pattern_id=str(associated_pattern_id),
                relation_type=relation_type,
                distance=max(1, int(distance)),
            )
            self._entries[key] = entry
        entry.score = _clamp(max(entry.score * 0.85, score))
        entry.activation = _clamp(max(entry.activation * 0.85, activation))
        entry.ttl = max(entry.ttl, int(ttl))
        entry.distance = min(entry.distance, max(1, int(distance)))
        entry.last_updated_tick = tick
        if path:
            _append_unique_bounded(entry.paths, [str(item) for item in path], MAX_PATHS)
        _append_unique_bounded(entry.source_probe_ids, str(source_probe_id), MAX_PROBES)
        if target_kind:
            _append_unique_bounded(entry.target_kinds, str(target_kind), MAX_TARGET_KINDS)
        for role in target_roles:
            _append_unique_bounded(entry.target_roles, str(role), MAX_TARGET_ROLES)

    def decay(self, tick: int) -> None:
        if self._last_decay_tick == tick:
            return
        self._last_decay_tick = tick
        remaining: dict[tuple[str, str, str | None], AssociationEntry] = {}
        for key, entry in self._entries.items():
            entry.score = _clamp(entry.score * DECAY)
            entry.activation = _clamp(entry.activation * DECAY)
            entry.ttl = max(0, entry.ttl - 1)
            if entry.ttl <= 0 and entry.score < MIN_SCORE and entry.activation < MIN_SCORE:
                continue
            remaining[key] = entry
        self._entries = remaining

    def get_associations(self, source_pattern_id: str, limit: int = 10) -> list[AssociationEntry]:
        entries = [entry for entry in self._entries.values() if entry.source_pattern_id == source_pattern_id]
        return sorted(entries, key=_entry_sort_key, reverse=True)[:limit]

    def top(self, n: int = 10) -> list[AssociationEntry]:
        return sorted(self._entries.values(), key=_entry_sort_key, reverse=True)[:n]

    def snapshot(self) -> dict:
        grouped: dict[str, list[dict]] = {}
        for entry in self.top():
            grouped.setdefault(entry.source_pattern_id, []).append(
                {
                    "associated_pattern_id": entry.associated_pattern_id,
                    "relation_type": entry.relation_type,
                    "score": round(entry.score, 3),
                    "distance": entry.distance,
                    "activation": round(entry.activation, 3),
                    "ttl": entry.ttl,
                    "last_updated_tick": entry.last_updated_tick,
                    "paths": [list(path) for path in entry.paths],
                    "source_probe_ids": list(entry.source_probe_ids),
                    "target_kinds": list(entry.target_kinds),
                    "target_roles": list(entry.target_roles),
                }
            )
        return grouped


def _entry_sort_key(entry: AssociationEntry) -> tuple[float, float, int]:
    return (entry.activation, entry.score, -entry.distance)


def _append_unique_bounded(values: list, value, limit: int) -> None:
    if value in values:
        return
    values.append(value)
    del values[:-limit]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
