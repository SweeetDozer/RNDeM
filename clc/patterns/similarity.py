from __future__ import annotations

from dataclasses import dataclass

from clc.patterns.model import ActivationPattern


@dataclass(frozen=True)
class PatternSimilarity:
    """Deterministic raw activation similarity measurement."""

    comparable: bool
    score: float | None
    reason: str | None = None

    @staticmethod
    def compare(left: ActivationPattern, right: ActivationPattern) -> "PatternSimilarity":
        if not isinstance(left, ActivationPattern) or not isinstance(right, ActivationPattern):
            raise TypeError("PatternSimilarity.compare requires ActivationPattern objects")
        if left.modality != right.modality:
            return PatternSimilarity(comparable=False, score=None, reason="different_modality")
        if left.topology != right.topology:
            return PatternSimilarity(comparable=False, score=None, reason="different_topology")
        distance = sum(abs(left_value - right_value) for left_value, right_value in zip(left.values, right.values))
        score = 1.0 - (distance / left.topology.size)
        return PatternSimilarity(comparable=True, score=max(0.0, min(1.0, score)), reason=None)
