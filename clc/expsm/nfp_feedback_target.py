from __future__ import annotations

from dataclasses import dataclass

from clc.experience.expsm_representation import (
    NFPExpSMRecordV1,
    SerializedNFPActionV1,
    SerializedNFPContextV1,
    SerializedObservedEffectV1,
)


@dataclass(frozen=True)
class NFPFeedbackTargetCore:
    """Transient immutable continuity snapshot of one native V1 record."""

    record_kind: str
    representation_version: int
    context: SerializedNFPContextV1
    action: SerializedNFPActionV1
    effect: SerializedObservedEffectV1
    source_support_count: int
    source_proposal_id: str
    created_active_tick: int
    initialization_profile: str
    created_at_world: str | None

    @classmethod
    def from_record(cls, record: NFPExpSMRecordV1) -> NFPFeedbackTargetCore:
        if not isinstance(record, NFPExpSMRecordV1):
            raise TypeError("target core source must be NFPExpSMRecordV1")
        creation = record.creation_metadata
        return cls(
            record_kind=record.record_kind,
            representation_version=record.representation_version,
            context=record.context,
            action=record.action,
            effect=record.effect,
            source_support_count=creation.source_support_count,
            source_proposal_id=creation.source_proposal_id,
            created_active_tick=creation.created_active_tick,
            initialization_profile=creation.initialization_profile,
            created_at_world=record.created_at_world,
        )
