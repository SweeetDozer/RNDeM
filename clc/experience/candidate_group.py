from dataclasses import dataclass, field
from typing import Any


@dataclass
class CandidateGroup:
    group_id: str
    signature: tuple[Any, ...]
    candidate_ids: set[str] = field(default_factory=set)
    source_event_ids: set[str] = field(default_factory=set)
    support_count: int = 0
    confidence_sum: float = 0.0
    valence_sum: float = 0.0
    priority_sum: float = 0.0
    first_seen_tick: int = 0
    last_seen_tick: int = 0
    emitted_ready: bool = False
    last_emitted_support_count: int = 0
    core_chain: dict[str, set[str]] = field(default_factory=lambda: {
        "decision_patterns": set(),
        "effect_patterns": set(),
        "predicted_patterns": set(),
        "outcome_patterns": set(),
    })
    context_summary: dict[str, set[str]] = field(default_factory=lambda: {
        "label_event_ids": set(),
        "frame_ids": set(),
        "active_patterns": set(),
    })

    @property
    def avg_confidence(self) -> float:
        return self.confidence_sum / self.support_count if self.support_count else 0.0

    @property
    def avg_valence(self) -> float:
        return self.valence_sum / self.support_count if self.support_count else 0.0

    @property
    def avg_priority(self) -> float:
        return self.priority_sum / self.support_count if self.support_count else 0.0

    def debug_snapshot(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "support_count": self.support_count,
            "avg_confidence": round(self.avg_confidence, 3),
            "avg_valence": round(self.avg_valence, 3),
            "avg_priority": round(self.avg_priority, 3),
            "emitted_ready": self.emitted_ready,
            "core_signature": self.signature,
        }
