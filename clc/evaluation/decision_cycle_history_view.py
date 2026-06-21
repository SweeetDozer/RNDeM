from collections import Counter
from dataclasses import dataclass, field
from typing import Any


DEFAULT_DECISION_CYCLE_HISTORY_WINDOW = 20


@dataclass(frozen=True)
class DecisionCycleHistorySnapshot:
    tick: int
    window_size: int
    observed_count: int
    status_counts: dict[str, int]
    confidence_counts: dict[str, int]
    flag_counts: dict[str, int]
    selected_source_counts: dict[str, int]
    value_influenced_count: int
    guard_constrained_count: int
    uncertain_count: int
    risky_or_constrained_count: int
    clean_count: int
    dominant_status: str | None
    dominant_confidence: str | None
    trend_label: str
    warnings: list[str] = field(default_factory=list)


class DecisionCycleHistoryView:
    """Runtime-only aggregate of recent marker 35 decision cycle summaries."""

    def __init__(self, window_size: int = DEFAULT_DECISION_CYCLE_HISTORY_WINDOW) -> None:
        if window_size <= 0:
            raise ValueError("DecisionCycleHistoryView window_size must be positive")
        self.window_size = window_size
        self._snapshot: DecisionCycleHistorySnapshot | None = None

    def refresh(
        self,
        *,
        tick: int,
        decision_cycle_summaries: list[dict[str, Any]],
    ) -> DecisionCycleHistorySnapshot:
        summaries = [summary for summary in decision_cycle_summaries[-self.window_size :] if isinstance(summary, dict)]
        status_counts: Counter[str] = Counter()
        confidence_counts: Counter[str] = Counter()
        flag_counts: Counter[str] = Counter()
        selected_source_counts: Counter[str] = Counter()
        value_influenced_count = 0
        guard_constrained_count = 0
        uncertain_count = 0
        risky_or_constrained_count = 0
        clean_count = 0
        warnings: list[str] = []

        for summary in summaries:
            selected = _dict(summary.get("selected"))
            decision_summary = _dict(summary.get("decision_summary"))
            guard_summary = _dict(summary.get("guard_summary"))
            cycle_summary = _dict(summary.get("cycle_summary"))
            status = _string_or_none(cycle_summary.get("cycle_status"))
            confidence = _string_or_none(cycle_summary.get("cycle_confidence"))
            flags = _string_list(cycle_summary.get("flags"))
            selected_source = _string_or_none(selected.get("source"))
            value_influence = _string_or_none(decision_summary.get("value_influence"))
            is_value_influenced = value_influence in {"positive_bonus", "negative_penalty"} or any(
                flag in flags for flag in ("value_promoted_selected", "value_penalized_selected")
            )
            is_guard_constrained = (
                status in {"guard_constrained_selection", "risky_or_constrained_selection"}
                or "guard_blocked_high_score" in flags
            )
            is_uncertain = status == "uncertain_selection" or any(
                flag in flags for flag in ("narrow_decision", "tie_like_decision")
            )

            if status is None:
                warnings.append("missing_cycle_status")
            else:
                status_counts[status] += 1
                if status == "clean_selection":
                    clean_count += 1
                if status == "risky_or_constrained_selection":
                    risky_or_constrained_count += 1

            if confidence is None:
                warnings.append("missing_cycle_confidence")
            else:
                confidence_counts[confidence] += 1
            if selected_source:
                selected_source_counts[selected_source] += 1
            flag_counts.update(flags)

            if is_value_influenced:
                value_influenced_count += 1
            if is_guard_constrained:
                guard_constrained_count += 1
            if is_uncertain:
                uncertain_count += 1

        observed_count = len(summaries)
        snapshot = DecisionCycleHistorySnapshot(
            tick=tick,
            window_size=self.window_size,
            observed_count=observed_count,
            status_counts=dict(sorted(status_counts.items())),
            confidence_counts=dict(sorted(confidence_counts.items())),
            flag_counts=dict(sorted(flag_counts.items())),
            selected_source_counts=dict(sorted(selected_source_counts.items())),
            value_influenced_count=value_influenced_count,
            guard_constrained_count=guard_constrained_count,
            uncertain_count=uncertain_count,
            risky_or_constrained_count=risky_or_constrained_count,
            clean_count=clean_count,
            dominant_status=_dominant(status_counts),
            dominant_confidence=_dominant(confidence_counts),
            trend_label=_trend_label(
                observed_count=observed_count,
                clean_count=clean_count,
                guard_constrained_count=guard_constrained_count,
                uncertain_count=uncertain_count,
                value_influenced_count=value_influenced_count,
            ),
            warnings=sorted(set(warnings)),
        )
        self._snapshot = snapshot
        return snapshot

    def snapshot(self) -> DecisionCycleHistorySnapshot | None:
        return self._snapshot


def _trend_label(
    *,
    observed_count: int,
    clean_count: int,
    guard_constrained_count: int,
    uncertain_count: int,
    value_influenced_count: int,
) -> str:
    if observed_count == 0:
        return "no_data"
    if clean_count / observed_count >= 0.6:
        return "mostly_clean"
    if guard_constrained_count / observed_count >= 0.3:
        return "guard_constrained_recent_history"
    if uncertain_count / observed_count >= 0.3:
        return "uncertain_recent_history"
    if value_influenced_count / observed_count >= 0.3:
        return "value_influenced_recent_history"
    return "mixed_recent_history"


def _dominant(counter: Counter[str]) -> str | None:
    if not counter:
        return None
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if item]
