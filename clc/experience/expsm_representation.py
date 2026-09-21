from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from clc.experience.effects import ObservedEffect
from clc.experience.evidence import ExperienceEvidence
from clc.experience.grouping import ExpSMConsolidationProposal
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternTopology


NFP_NATIVE_KIND = "nfp_native"
NFP_NATIVE_VERSION = 1
LEGACY_CRUD_DEFAULTS_PROFILE = "legacy_crud_defaults_v1"


def canonical_json(data: object) -> str:
    """Return deterministic strict JSON for already validated persistent data."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class SerializedNFPContextV1:
    modality: str
    topology: tuple[int, ...]
    frames: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        modality = _stable_modality(self.modality)
        topology = _stable_topology(self.topology)
        frames = tuple(tuple(_activation(value) for value in frame) for frame in self.frames)
        if not frames:
            raise ValueError("context requires at least one frame")
        if any(len(frame) != math.prod(topology) for frame in frames):
            raise ValueError("context frame length must equal topology size")
        object.__setattr__(self, "modality", modality)
        object.__setattr__(self, "topology", topology)
        object.__setattr__(self, "frames", frames)

    @classmethod
    def from_window(cls, window: NFPWindow) -> SerializedNFPContextV1:
        if not isinstance(window, NFPWindow):
            raise TypeError("context source must be NFPWindow")
        return cls(window.modality.value, window.topology.shape, tuple(frame.values for frame in window.frames))

    def to_json_data(self) -> dict[str, object]:
        return {
            "modality": self.modality,
            "topology": _topology_json(self.topology),
            "frames": [{"values": list(values)} for values in self.frames],
        }

    @classmethod
    def from_json_data(cls, data: object) -> SerializedNFPContextV1:
        mapping = _mapping(data, "context_pattern")
        frames = _sequence(mapping.get("frames"), "context_pattern.frames")
        return cls(
            _parse_modality(mapping.get("modality"), "context_pattern.modality"),
            _parse_topology(mapping.get("topology")),
            tuple(
                tuple(_sequence(_mapping(frame, "context frame").get("values"), "context frame values"))
                for frame in frames
            ),
        )


@dataclass(frozen=True)
class SerializedNFPActionV1:
    modality: str
    topology: tuple[int, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        modality = _stable_modality(self.modality)
        if modality != PatternModality.ACTION.value:
            raise ValueError("action modality must be ACTION")
        topology = _stable_topology(self.topology)
        values = tuple(_activation(value) for value in self.values)
        if len(values) != math.prod(topology):
            raise ValueError("action values length must equal topology size")
        object.__setattr__(self, "modality", modality)
        object.__setattr__(self, "topology", topology)
        object.__setattr__(self, "values", values)

    @classmethod
    def from_frame(cls, frame: NFPFrame) -> SerializedNFPActionV1:
        if not isinstance(frame, NFPFrame):
            raise TypeError("action source must be NFPFrame")
        return cls(frame.modality.value, frame.topology.shape, frame.values)

    def to_json_data(self) -> dict[str, object]:
        return {
            "modality": self.modality,
            "topology": _topology_json(self.topology),
            "values": list(self.values),
        }

    @classmethod
    def from_json_data(cls, data: object) -> SerializedNFPActionV1:
        mapping = _mapping(data, "action_pattern")
        return cls(
            _parse_modality(mapping.get("modality"), "action_pattern.modality"),
            _parse_topology(mapping.get("topology")),
            tuple(_sequence(mapping.get("values"), "action_pattern.values")),
        )


@dataclass(frozen=True)
class SerializedObservedEffectV1:
    modality: str
    topology: tuple[int, ...]
    delta_values: tuple[float, ...]

    def __post_init__(self) -> None:
        modality = _stable_modality(self.modality)
        topology = _stable_topology(self.topology)
        values = tuple(_effect_delta(value) for value in self.delta_values)
        if len(values) != math.prod(topology):
            raise ValueError("effect delta length must equal topology size")
        object.__setattr__(self, "modality", modality)
        object.__setattr__(self, "topology", topology)
        object.__setattr__(self, "delta_values", values)

    @classmethod
    def from_effect(cls, effect: ObservedEffect) -> SerializedObservedEffectV1:
        if not isinstance(effect, ObservedEffect):
            raise TypeError("effect source must be ObservedEffect")
        return cls(effect.modality.value, effect.topology.shape, effect.delta_values)

    def to_json_data(self) -> dict[str, object]:
        return {
            "modality": self.modality,
            "topology": _topology_json(self.topology),
            "delta_values": list(self.delta_values),
        }

    @classmethod
    def from_json_data(cls, data: object) -> SerializedObservedEffectV1:
        mapping = _mapping(data, "effect_pattern")
        return cls(
            _parse_modality(mapping.get("modality"), "effect_pattern.modality"),
            _parse_topology(mapping.get("topology")),
            tuple(_sequence(mapping.get("delta_values"), "effect_pattern.delta_values")),
        )


@dataclass(frozen=True)
class ExpSMOperationalMetadataV1:
    hits: int = 0
    misses: int = 0
    confidence: float = 0.5
    repeatability: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(self, "hits", _non_negative_int(self.hits, "hits"))
        object.__setattr__(self, "misses", _non_negative_int(self.misses, "misses"))
        object.__setattr__(self, "confidence", _unit_float(self.confidence, "confidence"))
        object.__setattr__(self, "repeatability", _unit_float(self.repeatability, "repeatability"))

    def to_json_data(self) -> dict[str, object]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "confidence": self.confidence,
            "repeatability": self.repeatability,
        }

    @classmethod
    def from_json_data(cls, data: Mapping[str, object]) -> ExpSMOperationalMetadataV1:
        return cls(data.get("hits"), data.get("misses"), data.get("confidence"), data.get("repeatability"))


@dataclass(frozen=True)
class NFPExpSMCreationMetadataV1:
    source_support_count: int
    source_proposal_id: str
    created_active_tick: int
    initialization_profile: str = LEGACY_CRUD_DEFAULTS_PROFILE

    def __post_init__(self) -> None:
        count = _positive_int(self.source_support_count, "source_support_count")
        proposal_id = _non_empty_string(self.source_proposal_id, "source_proposal_id")
        tick = _non_negative_int(self.created_active_tick, "created_active_tick")
        profile = _non_empty_string(self.initialization_profile, "initialization_profile")
        if profile != LEGACY_CRUD_DEFAULTS_PROFILE:
            raise ValueError("unsupported initialization_profile")
        object.__setattr__(self, "source_support_count", count)
        object.__setattr__(self, "source_proposal_id", proposal_id)
        object.__setattr__(self, "created_active_tick", tick)
        object.__setattr__(self, "initialization_profile", profile)

    def to_json_data(self) -> dict[str, object]:
        return {
            "source_support_count": self.source_support_count,
            "source_proposal_id": self.source_proposal_id,
            "created_active_tick": self.created_active_tick,
            "initialization_profile": self.initialization_profile,
        }

    @classmethod
    def from_json_data(cls, data: object) -> NFPExpSMCreationMetadataV1:
        mapping = _mapping(data, "creation_metadata")
        return cls(
            mapping.get("source_support_count"),
            mapping.get("source_proposal_id"),
            mapping.get("created_active_tick"),
            mapping.get("initialization_profile"),
        )


@dataclass(frozen=True)
class NFPExpSMRecordV1:
    record_id: str
    context: SerializedNFPContextV1
    action: SerializedNFPActionV1
    effect: SerializedObservedEffectV1
    operational: ExpSMOperationalMetadataV1
    creation_metadata: NFPExpSMCreationMetadataV1
    status: int = 2
    created_at_world: str | None = None
    updated_at_world: str | None = None

    def __post_init__(self) -> None:
        record_id = _numeric_record_id(self.record_id)
        _require_instance(self.context, SerializedNFPContextV1, "context")
        _require_instance(self.action, SerializedNFPActionV1, "action")
        _require_instance(self.effect, SerializedObservedEffectV1, "effect")
        _require_instance(self.operational, ExpSMOperationalMetadataV1, "operational")
        _require_instance(self.creation_metadata, NFPExpSMCreationMetadataV1, "creation_metadata")
        if self.context.modality != self.effect.modality or self.context.topology != self.effect.topology:
            raise ValueError("context and effect must share modality and topology")
        status = _non_negative_int(self.status, "status")
        for name in ("created_at_world", "updated_at_world"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_empty_string(value, name))
        object.__setattr__(self, "record_id", record_id)
        object.__setattr__(self, "status", status)

    @property
    def record_kind(self) -> str:
        return NFP_NATIVE_KIND

    @property
    def representation_version(self) -> int:
        return NFP_NATIVE_VERSION

    def to_json_data(self) -> dict[str, object]:
        data: dict[str, object] = {
            "record_kind": self.record_kind,
            "representation_version": self.representation_version,
            "context_pattern": self.context.to_json_data(),
            "action_pattern": self.action.to_json_data(),
            "effect_pattern": self.effect.to_json_data(),
            **self.operational.to_json_data(),
            "status": self.status,
            "creation_metadata": self.creation_metadata.to_json_data(),
        }
        if self.created_at_world is not None:
            data["created_at_world"] = self.created_at_world
        if self.updated_at_world is not None:
            data["updated_at_world"] = self.updated_at_world
        return data

    @classmethod
    def from_json_data(cls, record_id: object, data: object) -> NFPExpSMRecordV1:
        mapping = _mapping(data, "NFP-native record")
        if mapping.get("record_kind") != NFP_NATIVE_KIND:
            raise ValueError("record_kind must be nfp_native")
        if mapping.get("representation_version") != NFP_NATIVE_VERSION:
            raise ValueError("representation_version must be 1")
        return cls(
            record_id=str(record_id),
            context=SerializedNFPContextV1.from_json_data(mapping.get("context_pattern")),
            action=SerializedNFPActionV1.from_json_data(mapping.get("action_pattern")),
            effect=SerializedObservedEffectV1.from_json_data(mapping.get("effect_pattern")),
            operational=ExpSMOperationalMetadataV1.from_json_data(mapping),
            creation_metadata=NFPExpSMCreationMetadataV1.from_json_data(mapping.get("creation_metadata")),
            status=mapping.get("status"),
            created_at_world=mapping.get("created_at_world"),
            updated_at_world=mapping.get("updated_at_world"),
        )


@dataclass(frozen=True)
class ExpSMRecordCreationRequest:
    request_id: str
    context: SerializedNFPContextV1
    action: SerializedNFPActionV1
    effect: SerializedObservedEffectV1
    requested_operational: ExpSMOperationalMetadataV1
    creation_metadata: NFPExpSMCreationMetadataV1

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _non_empty_string(self.request_id, "request_id"))
        _require_instance(self.context, SerializedNFPContextV1, "context")
        _require_instance(self.action, SerializedNFPActionV1, "action")
        _require_instance(self.effect, SerializedObservedEffectV1, "effect")
        _require_instance(self.requested_operational, ExpSMOperationalMetadataV1, "requested_operational")
        _require_instance(self.creation_metadata, NFPExpSMCreationMetadataV1, "creation_metadata")
        if self.context.modality != self.effect.modality or self.context.topology != self.effect.topology:
            raise ValueError("context and effect must share modality and topology")

    @property
    def record_kind(self) -> str:
        return NFP_NATIVE_KIND

    @property
    def representation_version(self) -> int:
        return NFP_NATIVE_VERSION

    def to_json_data(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "record_kind": self.record_kind,
            "representation_version": self.representation_version,
            "context_pattern": self.context.to_json_data(),
            "action_pattern": self.action.to_json_data(),
            "effect_pattern": self.effect.to_json_data(),
            "requested_operational_metadata": self.requested_operational.to_json_data(),
            "creation_metadata": self.creation_metadata.to_json_data(),
        }

    def materialize_for_validation(self, record_id: str) -> NFPExpSMRecordV1:
        """Build a typed record for parser tests; this allocates or writes nothing."""
        return NFPExpSMRecordV1(
            record_id, self.context, self.action, self.effect,
            self.requested_operational, self.creation_metadata,
        )


class ExpSMRecordCreationRequestBuilder:
    """Pure explicit handoff from a proposal and its representative evidence."""

    @staticmethod
    def build(
        proposal: ExpSMConsolidationProposal,
        representative_evidence: ExperienceEvidence,
        *,
        request_id: str,
        requested_operational: ExpSMOperationalMetadataV1 | None = None,
    ) -> ExpSMRecordCreationRequest:
        if not isinstance(proposal, ExpSMConsolidationProposal):
            raise TypeError("proposal must be ExpSMConsolidationProposal")
        if not isinstance(representative_evidence, ExperienceEvidence):
            raise TypeError("representative_evidence must be ExperienceEvidence")
        if proposal.representative_evidence_id != representative_evidence.evidence_id:
            raise ValueError("proposal representative_evidence_id does not match evidence")
        if proposal.support_count != len(set(proposal.supporting_evidence_ids)):
            raise ValueError("proposal support_count must match unique supporting evidence IDs")
        operational = requested_operational or ExpSMOperationalMetadataV1()
        return ExpSMRecordCreationRequest(
            request_id=request_id,
            context=SerializedNFPContextV1.from_window(representative_evidence.context_window),
            action=SerializedNFPActionV1.from_frame(representative_evidence.action_frame),
            effect=SerializedObservedEffectV1.from_effect(representative_evidence.observed_effect),
            requested_operational=operational,
            creation_metadata=NFPExpSMCreationMetadataV1(
                proposal.support_count, proposal.proposal_id, proposal.created_active_tick,
            ),
        )


class ExpSMRecordKind(str, Enum):
    LEGACY = "legacy"
    NFP_NATIVE_V1 = "nfp_native_v1"
    MALFORMED = "malformed"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class LegacyOperationalRecord:
    record_id: str
    condition: tuple[object, ...]
    actions: tuple[object, ...]
    result: tuple[object, ...]
    recommendation: tuple[object, ...]
    operational: ExpSMOperationalMetadataV1
    kind: ExpSMRecordKind = ExpSMRecordKind.LEGACY


@dataclass(frozen=True)
class NFPNativeOperationalRecordV1:
    record: NFPExpSMRecordV1
    kind: ExpSMRecordKind = ExpSMRecordKind.NFP_NATIVE_V1


@dataclass(frozen=True)
class MalformedRecord:
    record_id: str
    errors: tuple[str, ...]
    kind: ExpSMRecordKind = ExpSMRecordKind.MALFORMED


@dataclass(frozen=True)
class UnsupportedRecord:
    record_id: str
    record_kind: object
    representation_version: object
    reason: str
    kind: ExpSMRecordKind = ExpSMRecordKind.UNSUPPORTED


class ExpSMRecordAdapter:
    """Isolated version-aware parser; it does not activate or mutate records."""

    @staticmethod
    def parse(record_id: object, raw: object) -> LegacyOperationalRecord | NFPNativeOperationalRecordV1 | MalformedRecord | UnsupportedRecord:
        try:
            normalized_id = _numeric_record_id(record_id)
        except (TypeError, ValueError) as exc:
            return MalformedRecord(str(record_id), (str(exc),))
        if not isinstance(raw, Mapping):
            return MalformedRecord(normalized_id, ("record must be a mapping",))
        has_kind = "record_kind" in raw
        has_version = "representation_version" in raw
        if has_kind != has_version:
            return MalformedRecord(normalized_id, ("record discriminator is incomplete",))
        if has_kind:
            kind = raw.get("record_kind")
            version = raw.get("representation_version")
            if kind != NFP_NATIVE_KIND:
                return UnsupportedRecord(normalized_id, kind, version, "unsupported record kind")
            if version != NFP_NATIVE_VERSION:
                return UnsupportedRecord(normalized_id, kind, version, "unsupported representation version")
            try:
                return NFPNativeOperationalRecordV1(NFPExpSMRecordV1.from_json_data(normalized_id, raw))
            except (TypeError, ValueError) as exc:
                return MalformedRecord(normalized_id, (str(exc),))
        try:
            required = tuple(tuple(_sequence(raw.get(name), f"legacy.{name}")) for name in ("if", "then", "result", "recommendation"))
            operational = ExpSMOperationalMetadataV1.from_json_data(raw)
            return LegacyOperationalRecord(normalized_id, *required, operational)
        except (TypeError, ValueError) as exc:
            return MalformedRecord(normalized_id, (str(exc),))


def _mapping(data: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return data


def _sequence(data: object, field_name: str) -> Sequence[object]:
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
        raise TypeError(f"{field_name} must be a sequence")
    return data


def _require_instance(value: object, expected: type, field_name: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{field_name} must be {expected.__name__}")


def _parse_modality(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    try:
        return PatternModality(value).value
    except ValueError as exc:
        raise ValueError(f"{field_name} is unsupported") from exc


def _parse_topology(data: object) -> tuple[int, ...]:
    mapping = _mapping(data, "topology")
    return _stable_topology(tuple(_sequence(mapping.get("shape"), "topology.shape")))


def _topology_json(topology: tuple[int, ...]) -> dict[str, object]:
    return {"shape": list(topology)}


def _stable_modality(value: object) -> str:
    raw = value.value if isinstance(value, PatternModality) else value
    return _parse_modality(raw, "modality")


def _stable_topology(value: object) -> tuple[int, ...]:
    raw = value.shape if isinstance(value, PatternTopology) else value
    values = tuple(_sequence(raw, "topology"))
    if not values:
        raise ValueError("topology must not be empty")
    if any(not isinstance(item, int) or isinstance(item, bool) for item in values):
        raise TypeError("topology dimensions must be integers")
    if any(item <= 0 for item in values):
        raise ValueError("topology dimensions must be positive")
    return values


def _number(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def _unit_float(value: object, field_name: str) -> float:
    result = _number(value, field_name)
    if result < 0.0 or result > 1.0:
        raise ValueError(f"{field_name} must be in [0.0, 1.0]")
    return result


def _activation(value: object) -> float:
    return _unit_float(value, "activation")


def _effect_delta(value: object) -> float:
    result = _number(value, "effect delta")
    if result < -1.0 or result > 1.0:
        raise ValueError("effect delta must be in [-1.0, 1.0]")
    return result


def _non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _positive_int(value: object, field_name: str) -> int:
    result = _non_negative_int(value, field_name)
    if result == 0:
        raise ValueError(f"{field_name} must be > 0")
    return result


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{field_name} must be non-empty")
    return result


def _numeric_record_id(value: object) -> str:
    record_id = _non_empty_string(str(value), "record_id")
    if not record_id.isdigit() or int(record_id) < 0:
        raise ValueError("record_id must be a non-negative numeric string")
    return record_id
