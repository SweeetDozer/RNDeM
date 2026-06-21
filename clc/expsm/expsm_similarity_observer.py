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


MIN_SIMILARITY_SCORE = 0.45
MAX_GROUPS_PER_RUN = 5
EFFECTIVE_CONFIDENCE_CAP = 0.75


class ExpSMSimilarityObserver:
    """Observes similar permanent ExpSM experiences without modifying memory."""

    module_name = "expsm_similarity_observer"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        expsm_path: str | Path,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.expsm_path = Path(expsm_path)
        self.observation_kind = pattern_registry.id("expsm_similarity_observed")
        self._emitted_group_keys: set[tuple[str, ...]] = set()

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        del memory, active_field
        if system_state.mode != "consolidation":
            return []
        records = self._load_records()
        pair_scores = self._pair_scores(records)
        groups = self._groups(pair_scores)
        operations: list[ContextOperation] = []
        for group in groups[:MAX_GROUPS_PER_RUN]:
            record_ids = tuple(group["record_ids"])
            if record_ids in self._emitted_group_keys:
                continue
            self._emitted_group_keys.add(record_ids)
            payload = self._payload(group, records)
            operations.append(
                ContextOperation(
                    self.id_gen.next("op"),
                    OperationMarker.EXPSM_SIMILARITY_OBSERVED,
                    tick,
                    self.module_name,
                    None,
                    payload,
                )
            )
        return operations

    def _load_records(self) -> dict[str, dict[str, Any]]:
        if not self.expsm_path.exists():
            return {}
        try:
            data = json.loads(self.expsm_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        experiences = data.get("experience", {})
        if not isinstance(experiences, dict):
            return {}
        records: dict[str, dict[str, Any]] = {}
        for record_id, record in experiences.items():
            if not isinstance(record, dict) or _is_archived(record):
                continue
            if not _valid_core(record):
                continue
            records[str(record_id)] = record
        return records

    def _pair_scores(self, records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        record_ids = sorted(records)
        scores: list[dict[str, Any]] = []
        for index, a_id in enumerate(record_ids):
            for b_id in record_ids[index + 1:]:
                a = records[a_id]
                b = records[b_id]
                if_similarity = _jaccard(_pattern_set(a.get("if")), _pattern_set(b.get("if")))
                then_similarity = _jaccard(_pattern_set(a.get("then")), _pattern_set(b.get("then")))
                result_similarity = _jaccard(_pattern_set(a.get("result")), _pattern_set(b.get("result")))
                recommendation_similarity = _jaccard(_pattern_set(a.get("recommendation")), _pattern_set(b.get("recommendation")))
                similarity_score = (
                    if_similarity * 0.45
                    + then_similarity * 0.30
                    + result_similarity * 0.20
                    + recommendation_similarity * 0.05
                )
                if similarity_score < MIN_SIMILARITY_SCORE:
                    continue
                scores.append(
                    {
                        "a": a_id,
                        "b": b_id,
                        "similarity_score": round(similarity_score, 3),
                        "if_similarity": round(if_similarity, 3),
                        "then_similarity": round(then_similarity, 3),
                        "result_similarity": round(result_similarity, 3),
                        "recommendation_similarity": round(recommendation_similarity, 3),
                    }
                )
        return scores

    def _groups(self, pair_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
        adjacency: dict[str, set[str]] = {}
        for pair in pair_scores:
            adjacency.setdefault(pair["a"], set()).add(pair["b"])
            adjacency.setdefault(pair["b"], set()).add(pair["a"])
        visited: set[str] = set()
        groups: list[dict[str, Any]] = []
        for record_id in sorted(adjacency):
            if record_id in visited:
                continue
            stack = [record_id]
            component: set[str] = set()
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                stack.extend(sorted(adjacency.get(current, set()) - visited))
            if len(component) < 2:
                continue
            component_pairs = [
                pair
                for pair in pair_scores
                if pair["a"] in component and pair["b"] in component
            ]
            max_similarity = max(pair["similarity_score"] for pair in component_pairs)
            avg_similarity = sum(pair["similarity_score"] for pair in component_pairs) / len(component_pairs)
            groups.append(
                {
                    "record_ids": sorted(component),
                    "max_similarity_score": round(max_similarity, 3),
                    "avg_similarity_score": round(avg_similarity, 3),
                    "pair_scores": sorted(component_pairs, key=lambda pair: pair["similarity_score"], reverse=True),
                }
            )
        return sorted(groups, key=lambda group: group["max_similarity_score"], reverse=True)

    def _payload(self, group: dict[str, Any], records: dict[str, dict[str, Any]]) -> dict[str, Any]:
        record_ids = list(group["record_ids"])
        return {
            "similarity_observation_id": self.id_gen.next("expsm_similarity"),
            "observation_kind": self.observation_kind,
            "group_id": self.id_gen.next("expsm_sim_group"),
            "record_ids": record_ids,
            "group_size": len(record_ids),
            "max_similarity_score": group["max_similarity_score"],
            "avg_similarity_score": group["avg_similarity_score"],
            "pair_scores": group["pair_scores"],
            "records": [self._record_summary(record_id, records[record_id]) for record_id in record_ids],
            "future_competition_candidate": True,
            "memory_modified": False,
            "permanent_memory_modified": False,
            "activation": 0.65,
            "ttl": 20,
        }

    def _record_summary(self, record_id: str, record: dict[str, Any]) -> dict[str, Any]:
        hits = _as_int(record.get("hits"))
        misses = _as_int(record.get("misses"))
        confidence = _clamp(_as_float(record.get("confidence"), 0.5))
        repeatability = _clamp(_as_float(record.get("repeatability"), 0.5))
        viability = (hits + 1) / (hits + misses + 2)
        return {
            "experience_id": record_id,
            "confidence": round(confidence, 3),
            "effective_confidence": round(min(confidence, EFFECTIVE_CONFIDENCE_CAP), 3),
            "repeatability": round(repeatability, 3),
            "hits": hits,
            "misses": misses,
            "viability": round(viability, 3),
        }


def _valid_core(record: dict[str, Any]) -> bool:
    return all(_pattern_set(record.get(field)) for field in ("if", "then", "result"))


def _pattern_set(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple)):
        return set()
    return {str(item) for item in value if item and str(item) != "NFP"}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _is_archived(record: dict[str, Any]) -> bool:
    return str(record.get("status", "")).lower() in {"archived", "deleted", "tombstone"}


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
