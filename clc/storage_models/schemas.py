from dataclasses import dataclass


@dataclass(frozen=True)
class PatternMatch:
    pattern_id: str
    similarity: float
    pattern_ref: str


@dataclass(frozen=True)
class RelatedPattern:
    pattern_id: str
    relation_type: str
    confidence: float
    source_edge_id: str | None = None


@dataclass(frozen=True)
class ExperienceMatch:
    record_id: str
    record_type: str
    similarity: float
    confidence: float
    priority: float
    suggested_patterns: tuple[str, ...]
