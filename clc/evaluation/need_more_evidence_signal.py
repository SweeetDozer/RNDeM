from dataclasses import dataclass
from typing import Any

from clc.core.ids import IdGenerator
from clc.evaluation.reflection_candidate_builder import ReflectionCandidate


MAX_RECENT_NEED_MORE_EVIDENCE_SIGNALS = 50

_SEVERITY_PRIORITY = {"info": 0, "low": 1, "medium": 2, "high": 3}
_REASON_PRIORITY = {
    "repeated_uncertain_selection": 0,
    "insufficient_decision_confidence": 1,
    "guard_policy_tension": 2,
    "mixed_cycle_history": 3,
    "weak_value_influence": 4,
    "stable_clean_selection": 5,
    "no_decision_history": 6,
}


@dataclass(frozen=True)
class NeedMoreEvidenceSignal:
    signal_id: str
    tick: int
    active: bool
    severity: str
    confidence: float
    reason: str
    source_reflection_types: tuple[str, ...]
    recommended_future_operation: str
    evidence: dict[str, Any]
    apply_now: bool
    tags: tuple[str, ...]


class NeedMoreEvidenceSignalBuilder:
    module_name = "need_more_evidence_signal_builder"

    def __init__(
        self,
        id_gen: IdGenerator,
        min_confidence: float = 0.4,
        max_recent_need_more_evidence_signals: int = MAX_RECENT_NEED_MORE_EVIDENCE_SIGNALS,
    ) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("NeedMoreEvidenceSignalBuilder min_confidence must be between 0.0 and 1.0")
        if max_recent_need_more_evidence_signals <= 0:
            raise ValueError("NeedMoreEvidenceSignalBuilder max_recent_need_more_evidence_signals must be positive")
        self.id_gen = id_gen
        self.min_confidence = min_confidence
        self.max_recent_need_more_evidence_signals = max_recent_need_more_evidence_signals
        self.latest_signal: NeedMoreEvidenceSignal | None = None
        self._recent_signals: list[NeedMoreEvidenceSignal] = []

    def build(
        self,
        *,
        tick: int,
        reflection_candidates: list[ReflectionCandidate],
    ) -> NeedMoreEvidenceSignal:
        active_options = [
            option
            for candidate in reflection_candidates
            if (option := _active_option(candidate)) is not None
        ]
        if active_options:
            chosen = sorted(active_options, key=_option_sort_key)[0]
            source_reflection_types = tuple(
                sorted(
                    {
                        candidate.reflection_type
                        for candidate in reflection_candidates
                        if candidate.reflection_type == chosen["reason"]
                    }
                )
            )
            confidence = _clamp(max(candidate.confidence for candidate in reflection_candidates if candidate.reflection_type == chosen["reason"]))
            signal = NeedMoreEvidenceSignal(
                signal_id=self.id_gen.next("need_more_evidence_signal"),
                tick=tick,
                active=True,
                severity=chosen["severity"],
                confidence=confidence,
                reason=chosen["reason"],
                source_reflection_types=source_reflection_types,
                recommended_future_operation=chosen["recommended_future_operation"],
                evidence=_evidence(reflection_candidates, active_options, self.min_confidence),
                apply_now=False,
                tags=("need_more_evidence", chosen["reason"]),
            )
            return self._store(signal)

        signal = NeedMoreEvidenceSignal(
            signal_id=self.id_gen.next("need_more_evidence_signal"),
            tick=tick,
            active=False,
            severity="info",
            confidence=0.0,
            reason="no_evidence_gap_detected",
            source_reflection_types=(),
            recommended_future_operation="maintain_current_policy",
            evidence=_evidence(reflection_candidates, active_options, self.min_confidence),
            apply_now=False,
            tags=("no_evidence_gap_detected",),
        )
        return self._store(signal)

    def recent_signals(self, limit: int = 8) -> list[NeedMoreEvidenceSignal]:
        return self._recent_signals[-limit:]

    def _store(self, signal: NeedMoreEvidenceSignal) -> NeedMoreEvidenceSignal:
        self.latest_signal = signal
        self._recent_signals.append(signal)
        if len(self._recent_signals) > self.max_recent_need_more_evidence_signals:
            self._recent_signals = self._recent_signals[-self.max_recent_need_more_evidence_signals :]
        return signal


def _active_option(candidate: ReflectionCandidate) -> dict[str, str] | None:
    if candidate.reflection_type == "repeated_uncertain_selection":
        return {
            "reason": "repeated_uncertain_selection",
            "severity": "medium",
            "recommended_future_operation": "collect_more_evidence",
        }
    if candidate.reflection_type == "insufficient_decision_confidence":
        return {
            "reason": "insufficient_decision_confidence",
            "severity": "low",
            "recommended_future_operation": "collect_more_evidence",
        }
    if candidate.reflection_type == "mixed_cycle_history":
        return {
            "reason": "mixed_cycle_history",
            "severity": "low",
            "recommended_future_operation": "inspect_recent_decision_context",
        }
    if candidate.reflection_type == "guard_policy_tension" and candidate.severity in {"medium", "high"}:
        return {
            "reason": "guard_policy_tension",
            "severity": "high" if candidate.severity == "high" else "medium",
            "recommended_future_operation": "inspect_guard_policy_tension",
        }
    return None


def _option_sort_key(option: dict[str, str]) -> tuple[int, int]:
    severity_rank = -_SEVERITY_PRIORITY.get(option["severity"], 0)
    reason_rank = _REASON_PRIORITY.get(option["reason"], len(_REASON_PRIORITY))
    return severity_rank, reason_rank


def _evidence(
    reflection_candidates: list[ReflectionCandidate],
    active_options: list[dict[str, str]],
    min_confidence: float,
) -> dict[str, Any]:
    all_reflection_types = [candidate.reflection_type for candidate in reflection_candidates]
    active_reflection_types = [option["reason"] for option in active_options]
    warning_reflection_types = [
        candidate.reflection_type
        for candidate in reflection_candidates
        if candidate.reflection_type == "weak_value_influence"
    ]
    return {
        "reflection_count": len(reflection_candidates),
        "active_reflection_types": sorted(set(active_reflection_types)),
        "all_reflection_types": all_reflection_types,
        "max_reflection_confidence": _clamp(
            max((candidate.confidence for candidate in reflection_candidates), default=0.0)
        ),
        "source_trend_labels": sorted({candidate.source_trend_label for candidate in reflection_candidates}),
        "reasons_seen": sorted(set(active_reflection_types + warning_reflection_types)),
        "warning_reflection_types": sorted(set(warning_reflection_types)),
        "min_confidence": min_confidence,
    }


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)
