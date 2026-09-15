from __future__ import annotations

from clc.patterns.model import NFPFrame, PatternOrigin


class NFPReactivation:
    """Create internal frame reactivations without treating them as fresh evidence."""

    @staticmethod
    def reactivate_frame(
        source_frame: NFPFrame,
        *,
        new_frame_id: str,
        active_tick: int,
        debug_name: str | None = None,
    ) -> NFPFrame:
        if not isinstance(source_frame, NFPFrame):
            raise TypeError("source_frame must be an NFPFrame")
        return NFPFrame(
            frame_id=new_frame_id,
            modality=source_frame.modality,
            origin=PatternOrigin.INTERNAL_REACTIVATION,
            topology=source_frame.topology,
            values=source_frame.values,
            active_tick=active_tick,
            provenance_ref=source_frame.frame_id,
            debug_name=debug_name,
        )
