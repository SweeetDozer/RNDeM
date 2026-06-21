"""Stable runtime source identifiers for action candidates.

These labels describe candidate provenance. They are not PatternRegistry debug
names and should not be interpreted as pattern semantics.
"""

from collections.abc import Mapping


SOURCE_EXPSM_ACTIVATION = "expsm_activation"
SOURCE_EXPSM_MECHANISM_SEARCH = "expsm_mechanism_search"


def candidate_source(metadata: Mapping[str, object]) -> str | None:
    source = metadata.get("source")
    return str(source) if source is not None else None


def is_expsm_activation_source(metadata: Mapping[str, object]) -> bool:
    return candidate_source(metadata) == SOURCE_EXPSM_ACTIVATION


def is_expsm_mechanism_search_source(metadata: Mapping[str, object]) -> bool:
    return candidate_source(metadata) == SOURCE_EXPSM_MECHANISM_SEARCH
