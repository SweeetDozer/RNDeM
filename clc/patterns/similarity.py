from __future__ import annotations

from dataclasses import dataclass

from clc.patterns.model import NFPFrame, NFPWindow


@dataclass(frozen=True)
class NFPSimilarityResult:
    """Deterministic activation similarity measurement result."""

    comparable: bool
    score: float | None
    reason: str | None = None


class NFPFrameSimilarity:
    """Instantaneous frame activation resemblance."""

    @staticmethod
    def compare(left: NFPFrame, right: NFPFrame) -> NFPSimilarityResult:
        if not isinstance(left, NFPFrame) or not isinstance(right, NFPFrame):
            raise TypeError("NFPFrameSimilarity.compare requires NFPFrame objects")
        if left.modality != right.modality:
            return NFPSimilarityResult(comparable=False, score=None, reason="different_modality")
        if left.topology != right.topology:
            return NFPSimilarityResult(comparable=False, score=None, reason="different_topology")
        distance = sum(abs(left_value - right_value) for left_value, right_value in zip(left.values, right.values))
        score = 1.0 - (distance / left.topology.size)
        return NFPSimilarityResult(comparable=True, score=max(0.0, min(1.0, score)), reason=None)


class NFPWindowSimilarity:
    """Short temporal pattern resemblance across aligned compatible frames."""

    @staticmethod
    def compare(left: NFPWindow, right: NFPWindow) -> NFPSimilarityResult:
        if not isinstance(left, NFPWindow) or not isinstance(right, NFPWindow):
            raise TypeError("NFPWindowSimilarity.compare requires NFPWindow objects")
        if left.modality != right.modality:
            return NFPSimilarityResult(comparable=False, score=None, reason="different_modality")
        if left.topology != right.topology:
            return NFPSimilarityResult(comparable=False, score=None, reason="different_topology")
        if left.length != right.length:
            return NFPSimilarityResult(comparable=False, score=None, reason="different_frame_count")
        frame_scores = tuple(
            NFPFrameSimilarity.compare(left_frame, right_frame).score
            for left_frame, right_frame in zip(left.frames, right.frames)
        )
        if any(score is None for score in frame_scores):
            return NFPSimilarityResult(comparable=False, score=None, reason="frame_not_comparable")
        score = sum(score for score in frame_scores if score is not None) / left.length
        return NFPSimilarityResult(comparable=True, score=max(0.0, min(1.0, score)), reason=None)
