from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_MAX_EVENTS = 5000
DEFAULT_PROTECTED_RECENT_EVENTS = 200
SIDE_LIST_NAMES = (
    "raw_frames",
    "thought_frames",
    "windows",
    "labels",
    "predictions",
    "decisions",
    "effects",
    "outcomes",
    "experience_candidates",
    "consolidation_candidates",
    "memory_write_reviews",
    "memory_draft_writes",
    "memory_draft_commit_reviews",
    "memory_commits",
    "committed_draft_observations",
    "expsm_update_reviews",
    "memory_updates",
    "expsm_activations",
    "expsm_feedback",
    "expsm_similarity_observations",
    "expsm_competition_observations",
    "evaluation_signals",
    "evaluation_targets",
    "akbsm_association_probes",
    "expsm_mechanism_searches",
    "target_satisfaction_observations",
    "value_feedback_candidates",
    "value_feedback_reviews",
    "value_feedback_updates",
    "decision_audits",
    "action_guard_audits",
    "decision_cycle_summaries",
    "consolidation_pressures",
    "system_mode_changes",
    "neuromodulation_updates",
    "module_updates",
)
SIDE_LIST_DEFAULT_MAX_ENTRIES = {
    "labels": 500,
    "predictions": 500,
    "decisions": 300,
    "effects": 300,
    "outcomes": 300,
    "experience_candidates": 300,
    "decision_audits": 300,
    "action_guard_audits": 300,
    "decision_cycle_summaries": 300,
    "value_feedback_candidates": 300,
    "value_feedback_reviews": 300,
    "value_feedback_updates": 300,
    "target_satisfaction_observations": 300,
    "expsm_activations": 300,
    "expsm_feedback": 300,
    "expsm_mechanism_searches": 300,
    "akbsm_association_probes": 300,
    "raw_frames": 300,
    "thought_frames": 300,
    "windows": 300,
}


@dataclass(frozen=True)
class ContextRetentionPolicy:
    max_events: int | None = DEFAULT_MAX_EVENTS
    protected_recent_events: int = DEFAULT_PROTECTED_RECENT_EVENTS
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.max_events is not None and self.max_events <= 0:
            raise ValueError("max_events must be None or > 0")
        if self.protected_recent_events < 0:
            raise ValueError("protected_recent_events must be >= 0")
        if self.enabled and self.max_events is not None and self.protected_recent_events > self.max_events:
            raise ValueError("protected_recent_events must be <= max_events")


@dataclass(frozen=True)
class ContextRetentionResult:
    enabled: bool
    max_events: int | None
    before_count: int
    after_count: int
    pruned_count: int
    oldest_remaining_tick: int | None
    newest_remaining_tick: int | None


@dataclass(frozen=True)
class SideListRetentionPolicy:
    enabled: bool = True
    prune_older_than_oldest_event: bool = True
    default_max_entries: int | None = 500
    per_list_max_entries: dict[str, int | None] = field(default_factory=dict)
    keep_unknown_tick_entries: bool = True

    def __post_init__(self) -> None:
        if self.default_max_entries is not None and self.default_max_entries <= 0:
            raise ValueError("default_max_entries must be None or > 0")
        for name, max_entries in self.per_list_max_entries.items():
            if max_entries is not None and max_entries <= 0:
                raise ValueError(f"per-list max entries for {name} must be None or > 0")

    def max_entries_for(self, name: str) -> int | None:
        if name in self.per_list_max_entries:
            return self.per_list_max_entries[name]
        if self.default_max_entries == 500:
            return SIDE_LIST_DEFAULT_MAX_ENTRIES.get(name, self.default_max_entries)
        return self.default_max_entries


@dataclass(frozen=True)
class SideListRetentionResult:
    enabled: bool
    oldest_event_tick: int | None
    total_before: int
    total_after: int
    total_pruned: int
    per_list: dict[str, dict[str, int | None]]
    warnings: list[str]
