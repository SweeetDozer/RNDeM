from dataclasses import dataclass
from typing import Any

from clc.core.ids import IdGenerator
from clc.evaluation.decision_cycle_history_view import DecisionCycleHistorySnapshot


MAX_REFLECTION_CANDIDATES_PER_TICK = 3
MAX_RECENT_REFLECTION_CANDIDATES = 50


@dataclass(frozen=True)
class ReflectionCandidate:
    reflection_candidate_id: str
    tick: int
    reflection_type: str
    severity: str
    confidence: float
    source: str
    source_trend_label: str
    evidence: dict[str, Any]
    recommended_future_operation: str
    apply_now: bool
    tags: tuple[str, ...]


class ReflectionCandidateBuilder:
    module_name = "reflection_candidate_builder"

    def __init__(
        self,
        id_gen: IdGenerator,
        min_observed_count: int = 5,
        max_recent_reflection_candidates: int = MAX_RECENT_REFLECTION_CANDIDATES,
    ) -> None:
        if min_observed_count <= 0:
            raise ValueError("ReflectionCandidateBuilder min_observed_count must be positive")
        if max_recent_reflection_candidates <= 0:
            raise ValueError("ReflectionCandidateBuilder max_recent_reflection_candidates must be positive")
        self.id_gen = id_gen
        self.min_observed_count = min_observed_count
        self.max_recent_reflection_candidates = max_recent_reflection_candidates
        self._recent_candidates: list[ReflectionCandidate] = []

    def build(
        self,
        *,
        tick: int,
        history_snapshot: DecisionCycleHistorySnapshot | None,
    ) -> list[ReflectionCandidate]:
        candidates: list[ReflectionCandidate] = []
        if history_snapshot is None:
            candidates.append(
                self._candidate(
                    tick,
                    history_snapshot,
                    reflection_type="no_decision_history",
                    severity="info",
                    recommended_future_operation="collect_more_evidence",
                    tags=("no_data",),
                )
            )
            return self._store(candidates)

        observed_count = history_snapshot.observed_count
        trend_label = history_snapshot.trend_label
        if observed_count == 0:
            candidates.append(
                self._candidate(
                    tick,
                    history_snapshot,
                    reflection_type="no_decision_history",
                    severity="info",
                    recommended_future_operation="collect_more_evidence",
                    tags=("no_data",),
                )
            )
            return self._store(candidates)
        if observed_count < self.min_observed_count:
            candidates.append(
                self._candidate(
                    tick,
                    history_snapshot,
                    reflection_type="insufficient_decision_confidence",
                    severity="low",
                    recommended_future_operation="collect_more_evidence",
                    tags=("insufficient_history",),
                )
            )
        if trend_label == "uncertain_recent_history":
            candidates.append(
                self._candidate(
                    tick,
                    history_snapshot,
                    reflection_type="repeated_uncertain_selection",
                    severity="medium",
                    recommended_future_operation="inspect_candidate_discrimination",
                    tags=("uncertain_history",),
                )
            )
        elif trend_label == "guard_constrained_recent_history":
            severity = "high" if history_snapshot.risky_or_constrained_count > 0 else "medium"
            candidates.append(
                self._candidate(
                    tick,
                    history_snapshot,
                    reflection_type="guard_policy_tension",
                    severity=severity,
                    recommended_future_operation="inspect_guard_policy_tension",
                    tags=("guard_constrained",),
                )
            )
        elif trend_label == "mostly_clean":
            candidates.append(
                self._candidate(
                    tick,
                    history_snapshot,
                    reflection_type="stable_clean_selection",
                    severity="info",
                    recommended_future_operation="maintain_current_policy",
                    tags=("stable_history",),
                )
            )
        elif trend_label == "mixed_recent_history":
            candidates.append(
                self._candidate(
                    tick,
                    history_snapshot,
                    reflection_type="mixed_cycle_history",
                    severity="low",
                    recommended_future_operation="review_mixed_history",
                    tags=("mixed_history",),
                )
            )

        if (
            observed_count >= self.min_observed_count
            and history_snapshot.value_influenced_count == 0
            and trend_label not in {"no_data", "value_influenced_recent_history"}
        ):
            candidates.append(
                self._candidate(
                    tick,
                    history_snapshot,
                    reflection_type="weak_value_influence",
                    severity="low",
                    recommended_future_operation="inspect_value_signal_coverage",
                    tags=("value_signal", "weak_value_influence"),
                )
            )
        return self._store(candidates[:MAX_REFLECTION_CANDIDATES_PER_TICK])

    def recent_candidates(self, limit: int = 8) -> list[ReflectionCandidate]:
        return self._recent_candidates[-limit:]

    def _candidate(
        self,
        tick: int,
        history_snapshot: DecisionCycleHistorySnapshot | None,
        *,
        reflection_type: str,
        severity: str,
        recommended_future_operation: str,
        tags: tuple[str, ...],
    ) -> ReflectionCandidate:
        return ReflectionCandidate(
            reflection_candidate_id=self.id_gen.next("reflection_candidate"),
            tick=tick,
            reflection_type=reflection_type,
            severity=severity,
            confidence=_confidence(history_snapshot, severity),
            source="decision_cycle_history_view",
            source_trend_label=history_snapshot.trend_label if history_snapshot is not None else "no_data",
            evidence=_evidence(history_snapshot),
            recommended_future_operation=recommended_future_operation,
            apply_now=False,
            tags=tags,
        )

    def _store(self, candidates: list[ReflectionCandidate]) -> list[ReflectionCandidate]:
        self._recent_candidates.extend(candidates)
        if len(self._recent_candidates) > self.max_recent_reflection_candidates:
            self._recent_candidates = self._recent_candidates[-self.max_recent_reflection_candidates :]
        return candidates


def _confidence(history_snapshot: DecisionCycleHistorySnapshot | None, severity: str) -> float:
    if history_snapshot is None or history_snapshot.window_size <= 0:
        base = 0.0
    else:
        base = min(1.0, history_snapshot.observed_count / history_snapshot.window_size)
    adjustment = {"info": 0.0, "low": 0.0, "medium": 0.05, "high": 0.1}.get(severity, 0.0)
    return round(max(0.0, min(1.0, base + adjustment)), 3)


def _evidence(history_snapshot: DecisionCycleHistorySnapshot | None) -> dict[str, Any]:
    if history_snapshot is None:
        return {
            "observed_count": 0,
            "window_size": 0,
            "trend_label": "no_data",
            "status_counts": {},
            "confidence_counts": {},
            "flag_counts": {},
            "selected_source_counts": {},
            "value_influenced_count": 0,
            "guard_constrained_count": 0,
            "uncertain_count": 0,
            "risky_or_constrained_count": 0,
            "clean_count": 0,
        }
    return {
        "observed_count": history_snapshot.observed_count,
        "window_size": history_snapshot.window_size,
        "trend_label": history_snapshot.trend_label,
        "status_counts": dict(history_snapshot.status_counts),
        "confidence_counts": dict(history_snapshot.confidence_counts),
        "flag_counts": dict(history_snapshot.flag_counts),
        "selected_source_counts": dict(history_snapshot.selected_source_counts),
        "value_influenced_count": history_snapshot.value_influenced_count,
        "guard_constrained_count": history_snapshot.guard_constrained_count,
        "uncertain_count": history_snapshot.uncertain_count,
        "risky_or_constrained_count": history_snapshot.risky_or_constrained_count,
        "clean_count": history_snapshot.clean_count,
    }
