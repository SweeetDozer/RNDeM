"""Isolated natural activation-pattern substrate."""

from clc.patterns.model import (
    NFPFrame,
    NFPSequence,
    NFPWindow,
    PatternModality,
    PatternMoment,
    PatternOrigin,
    PatternTopology,
)
from clc.patterns.reactivation import NFPReactivation
from clc.patterns.similarity import NFPFrameSimilarity, NFPSimilarityResult, NFPWindowSimilarity

__all__ = [
    "NFPFrame",
    "NFPFrameSimilarity",
    "NFPReactivation",
    "NFPSimilarityResult",
    "NFPSequence",
    "NFPWindow",
    "NFPWindowSimilarity",
    "PatternModality",
    "PatternMoment",
    "PatternOrigin",
    "PatternTopology",
]
