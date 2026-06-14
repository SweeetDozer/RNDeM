from collections import defaultdict


class IdGenerator:
    """Small deterministic id source for readable demo traces."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)

    def next(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}_{self._counters[prefix]:03d}"
