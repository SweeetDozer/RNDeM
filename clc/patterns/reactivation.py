from __future__ import annotations

from clc.patterns.model import ActivationPattern, PatternOrigin


class PatternReactivation:
    """Create internal reactivation occurrences without treating them as fresh evidence."""

    @staticmethod
    def reactivate(
        source_pattern: ActivationPattern,
        *,
        new_pattern_id: str,
        active_tick: int,
        debug_name: str | None = None,
    ) -> ActivationPattern:
        if not isinstance(source_pattern, ActivationPattern):
            raise TypeError("source_pattern must be an ActivationPattern")
        return ActivationPattern(
            pattern_id=new_pattern_id,
            modality=source_pattern.modality,
            origin=PatternOrigin.INTERNAL_REACTIVATION,
            topology=source_pattern.topology,
            values=source_pattern.values,
            active_tick=active_tick,
            provenance_ref=source_pattern.pattern_id,
            debug_name=debug_name,
        )
