import json
from pathlib import Path
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


ACTIVE_THRESHOLD = 0.25
MIN_MATCH_SCORE = 0.35
MAX_ACTIVATIONS_PER_TICK = 3
LEGACY_CONFIDENCE_SOFT_CAP = 0.75


class ExpSMActivationModule:
    """Activates permanent ExpSM experience records that match the active field."""

    module_name = "expsm_activation_module"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        expsm_path: str | Path,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.expsm_path = Path(expsm_path)
        self.activation_kind = pattern_registry.id("expsm_activation")

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        del memory
        if system_state.mode != "active":
            return []
        active_patterns = {
            pattern.pattern_id
            for pattern in active_field.get_patterns_above(ACTIVE_THRESHOLD)
        }
        if not active_patterns:
            return []
        store = self._load_store()
        matches = [
            match
            for record_id, record in store.get("experience", {}).items()
            if isinstance(record, dict)
            for match in (self._match_record(str(record_id), record, active_patterns),)
            if match is not None
        ]
        matches.sort(key=lambda item: item["activation"], reverse=True)
        return [
            ContextOperation(
                self.id_gen.next("op"),
                OperationMarker.EXPSM_ACTIVATION,
                tick,
                self.module_name,
                None,
                match,
            )
            for match in matches[:MAX_ACTIVATIONS_PER_TICK]
        ]

    def _load_store(self) -> dict[str, Any]:
        if not self.expsm_path.exists():
            return {"experience": {}, "reflexes": {}}
        try:
            with self.expsm_path.open("r", encoding="utf-8") as handle:
                store = json.load(handle)
        except json.JSONDecodeError:
            return {"experience": {}, "reflexes": {}}
        if not isinstance(store, dict):
            return {"experience": {}, "reflexes": {}}
        if not isinstance(store.get("experience"), dict):
            store["experience"] = {}
        return store

    def _match_record(self, record_id: str, record: dict[str, Any], active_patterns: set[str]) -> dict[str, Any] | None:
        if str(record.get("status", "")).lower() in {"archived", "deleted", "tombstone"}:
            return None
        record_if = {str(pattern_id) for pattern_id in record.get("if", ()) if pattern_id and str(pattern_id) != "NFP"}
        if not record_if:
            return None
        matched = sorted(record_if & active_patterns)
        if not matched:
            return None
        missing = sorted(record_if - active_patterns)
        coverage = len(matched) / max(1, len(record_if))
        raw_confidence = _clamp(float(record.get("confidence", 0.5) or 0.5))
        effective_confidence = min(raw_confidence, LEGACY_CONFIDENCE_SOFT_CAP)
        repeatability = _clamp(float(record.get("repeatability", 0.5) or 0.5))
        hits = int(record.get("hits", 0) or 0)
        misses = int(record.get("misses", 0) or 0)
        viability = _clamp((hits + 1) / (hits + misses + 2))
        activation_score = _clamp(
            coverage * 0.55
            + effective_confidence * 0.20
            + repeatability * 0.15
            + viability * 0.10
        )
        if activation_score < MIN_MATCH_SCORE:
            return None
        activation_id = self.id_gen.next("expsm_activation")
        return {
            "activation_id": activation_id,
            "activation_kind": self.activation_kind,
            "experience_id": record_id,
            "match_score": round(activation_score, 3),
            "coverage": round(coverage, 3),
            "matched_if_patterns": matched,
            "missing_if_patterns": missing,
            "then_patterns": _pattern_list(record, "then"),
            "result_patterns": _pattern_list(record, "result"),
            "recommendation_patterns": _pattern_list(record, "recommendation"),
            "confidence": round(effective_confidence, 3),
            "raw_confidence": round(raw_confidence, 3),
            "effective_confidence": round(effective_confidence, 3),
            "repeatability": round(repeatability, 3),
            "hits": hits,
            "misses": misses,
            "viability": round(viability, 3),
            "competition_trace": {
                "source": "expsm_activation",
                "experience_id": record_id,
                "activation_id": activation_id,
            },
            "activation": round(activation_score, 3),
            "ttl": 6,
        }


def _pattern_list(record: dict[str, Any], key: str) -> list[str]:
    values = record.get(key, ())
    if not isinstance(values, (list, tuple)):
        return []
    return [str(value) for value in values if value and str(value) != "NFP"]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
