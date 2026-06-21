from dataclasses import dataclass


@dataclass(frozen=True)
class ContextWindow:
    window_id: str
    from_tick: int
    to_tick: int
    frame_ids: tuple[str, ...]
