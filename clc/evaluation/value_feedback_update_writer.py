import json
from pathlib import Path
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.runtime.memory_mutation_policy import MemoryMutationPolicy, RuntimeProfile, policy_for_profile
from clc.system.system_state import SystemState


MIN_READY_STRENGTH = 0.70
MIN_READY_EVIDENCE = 0.60
MAX_TARGET_LINKS = 32
REQUIRED_FIELDS = (
    "value_feedback_review_id",
    "source_value_feedback_candidate_id",
    "source_target_satisfaction_id",
    "source_experience_id",
    "source_mechanism_search_id",
    "source_target_observation_id",
    "target_pattern_id",
    "target_kind",
    "target_role_names",
    "candidate_type",
    "value_direction",
    "candidate_strength",
    "evidence_strength",
    "satisfaction_status",
    "satisfaction_score",
    "review_decision",
    "review_reason",
    "recommended_future_operation",
    "ready_for_future_application",
    "apply_now",
)


class ValueFeedbackUpdateWriter:
    """Applies ready value feedback reviews only to ExpSM value metadata."""

    module_name = "value_feedback_update_writer"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        expsm_path: str | Path,
        memory_mutation_policy: MemoryMutationPolicy | None = None,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.expsm_path = Path(expsm_path)
        self.memory_mutation_policy = memory_mutation_policy or policy_for_profile(RuntimeProfile.MUTATING_MEMORY)
        self.update_kind = pattern_registry.id("value_feedback_updated")
        self._applied_review_ids: set[str] = set()

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        if system_state.mode != "consolidation":
            return []
        reviews = [
            review
            for review in memory.get_recent_value_feedback_reviews(16)
            if self._is_ready_review(review)
        ]
        if not reviews:
            return []
        if not self.memory_mutation_policy.allow_value_feedback_update:
            return [
                self._policy_blocked_update(
                    tick,
                    "value_feedback_update_blocked_by_policy",
                    "policy_disallows_value_feedback_update",
                )
            ]
        try:
            store = self._load_expsm_store()
        except ValueError as exc:
            return [self._module_update(tick, "value_feedback_update_failed", str(exc))]
        applied_ids = self._applied_review_ids | _applied_review_ids_from_store(store)
        newly_applied_ids: set[str] = set()
        operations: list[ContextOperation] = []
        changed = False
        for review in reviews:
            review_id = str(review.get("value_feedback_review_id", ""))
            if review_id in applied_ids:
                continue
            experience_id = str(review.get("source_experience_id", ""))
            record = store.get("experience", {}).get(experience_id)
            if not isinstance(record, dict):
                operations.append(self._module_update(tick, "value_feedback_update_failed", f"{experience_id}: missing_experience_record"))
                continue
            updated_fields = self._apply_value_feedback(record, review, tick)
            applied_ids.add(review_id)
            newly_applied_ids.add(review_id)
            changed = True
            operations.append(self._update_operation(tick, review, updated_fields))
        if changed:
            try:
                self._atomic_write_json(self.expsm_path, store)
            except OSError as exc:
                return [self._module_update(tick, "value_feedback_update_failed", str(exc))]
            self._applied_review_ids.update(newly_applied_ids)
        return operations

    def _is_ready_review(self, review: dict[str, Any]) -> bool:
        if not _has_required_fields(review):
            return False
        return (
            review.get("review_decision") == "ready"
            and review.get("ready_for_future_application") is True
            and review.get("apply_now") is False
            and bool(review.get("source_experience_id"))
            and _safe_float(review.get("candidate_strength")) >= MIN_READY_STRENGTH
            and _safe_float(review.get("evidence_strength")) >= MIN_READY_EVIDENCE
        )

    def _load_expsm_store(self) -> dict[str, Any]:
        if not self.expsm_path.exists():
            return {"experience": {}, "reflexes": {}}
        try:
            with self.expsm_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{self.expsm_path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{self.expsm_path} must contain a JSON object")
        if not isinstance(data.get("experience", {}), dict):
            data["experience"] = {}
        if not isinstance(data.get("reflexes", {}), dict):
            data["reflexes"] = {}
        return data

    def _atomic_write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        temp_path.replace(path)

    def _apply_value_feedback(self, record: dict[str, Any], review: dict[str, Any], tick: int) -> list[str]:
        value_feedback = _value_feedback_block(record.get("value_feedback"))
        direction = _direction_bucket(str(review.get("value_direction", "")), str(review.get("candidate_type", "")))
        strength = _safe_float(review.get("candidate_strength"))
        updated_fields = [
            f"value_feedback.{direction}_count",
            "value_feedback.target_links",
            "value_feedback.last_review_id",
        ]
        if direction != "inconclusive":
            updated_fields.insert(1, f"value_feedback.{direction}_strength_total")
        value_feedback[f"{direction}_count"] = int(value_feedback.get(f"{direction}_count", 0) or 0) + 1
        if direction in {"positive", "negative", "mixed"}:
            key = f"{direction}_strength_total"
            value_feedback[key] = round(float(value_feedback.get(key, 0.0) or 0.0) + strength, 3)
        review_id = str(review.get("value_feedback_review_id", ""))
        value_feedback["last_review_id"] = review_id
        value_feedback["last_candidate_id"] = str(review.get("source_value_feedback_candidate_id", ""))
        value_feedback["last_target_satisfaction_id"] = str(review.get("source_target_satisfaction_id", ""))
        value_feedback["last_updated_tick"] = tick
        links = list(value_feedback.get("target_links", ()))
        links.append(_target_link(review, tick))
        value_feedback["target_links"] = links[-MAX_TARGET_LINKS:]
        record["value_feedback"] = value_feedback
        return updated_fields

    def _update_operation(self, tick: int, review: dict[str, Any], updated_fields: list[str]) -> ContextOperation:
        payload = {
            "value_feedback_update_id": self.id_gen.next("value_feedback_update"),
            "update_kind": self.update_kind,
            "target": "ExpSM",
            "source_value_feedback_review_id": str(review.get("value_feedback_review_id", "")),
            "source_value_feedback_candidate_id": str(review.get("source_value_feedback_candidate_id", "")),
            "source_target_satisfaction_id": str(review.get("source_target_satisfaction_id", "")),
            "source_experience_id": str(review.get("source_experience_id", "")),
            "source_mechanism_search_id": str(review.get("source_mechanism_search_id", "")),
            "source_target_observation_id": str(review.get("source_target_observation_id", "")),
            "target_pattern_id": str(review.get("target_pattern_id", "")),
            "target_pattern_name": str(review.get("target_pattern_name") or self.pattern_registry.debug_name(str(review.get("target_pattern_id", "")))),
            "target_kind": str(review.get("target_kind", "")),
            "target_role_names": [str(role) for role in review.get("target_role_names", ())],
            "value_direction": str(review.get("value_direction", "")),
            "candidate_type": str(review.get("candidate_type", "")),
            "candidate_strength": round(_safe_float(review.get("candidate_strength")), 3),
            "evidence_strength": round(_safe_float(review.get("evidence_strength")), 3),
            "satisfaction_status": str(review.get("satisfaction_status", "")),
            "satisfaction_score": round(_safe_float(review.get("satisfaction_score")), 3),
            "recommended_future_operation": str(review.get("recommended_future_operation", "")),
            "updated_fields": updated_fields,
            "semantic_core_modified": False,
            "technical_feedback_modified": False,
            "memory_modified": True,
            "permanent_memory_modified": True,
            "expsm_modified": True,
            "akbsm_modified": False,
            "activation": 0.50,
            "ttl": 12,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.VALUE_FEEDBACK_UPDATED,
            tick,
            self.module_name,
            None,
            payload,
        )

    def _module_update(self, tick: int, status: str, detail: str) -> ContextOperation:
        payload = {
            "module_update_id": self.id_gen.next("mod_update"),
            "module": self.module_name,
            "status": status,
            "detail": detail,
            "activation": 0.35,
            "ttl": 6,
        }
        return ContextOperation(self.id_gen.next("op"), OperationMarker.MODULE_UPDATE, tick, self.module_name, None, payload)

    def _policy_blocked_update(self, tick: int, status: str, reason: str) -> ContextOperation:
        policy = self.memory_mutation_policy
        payload = {
            "module_update_id": self.id_gen.next("mod_update"),
            "module": self.module_name,
            "writer": self.__class__.__name__,
            "status": status,
            "reason": reason,
            "write_allowed": False,
            "blocked_by_policy": True,
            "runtime_profile": policy.profile.value,
            "memory_is_temporary": policy.memory_is_temporary,
            "policy": policy.summary(),
            "permanent_memory_modified": False,
            "activation": 0.35,
            "ttl": 6,
        }
        return ContextOperation(self.id_gen.next("op"), OperationMarker.MODULE_UPDATE, tick, self.module_name, None, payload)


def _value_feedback_block(value: Any) -> dict[str, Any]:
    block = dict(value) if isinstance(value, dict) else {}
    defaults = {
        "positive_count": 0,
        "negative_count": 0,
        "mixed_count": 0,
        "inconclusive_count": 0,
        "positive_strength_total": 0.0,
        "negative_strength_total": 0.0,
        "mixed_strength_total": 0.0,
        "last_review_id": None,
        "last_candidate_id": None,
        "last_target_satisfaction_id": None,
        "last_updated_tick": None,
        "target_links": [],
    }
    for key, value in defaults.items():
        if key not in block:
            block[key] = value
    if not isinstance(block.get("target_links"), list):
        block["target_links"] = []
    return block


def _target_link(review: dict[str, Any], tick: int) -> dict[str, Any]:
    return {
        "target_pattern_id": str(review.get("target_pattern_id", "")),
        "target_pattern_name": str(review.get("target_pattern_name", "")),
        "target_kind": str(review.get("target_kind", "")),
        "target_role_names": [str(role) for role in review.get("target_role_names", ())],
        "value_direction": str(review.get("value_direction", "")),
        "candidate_type": str(review.get("candidate_type", "")),
        "candidate_strength": round(_safe_float(review.get("candidate_strength")), 3),
        "evidence_strength": round(_safe_float(review.get("evidence_strength")), 3),
        "satisfaction_status": str(review.get("satisfaction_status", "")),
        "satisfaction_score": round(_safe_float(review.get("satisfaction_score")), 3),
        "mechanism_search_id": str(review.get("source_mechanism_search_id", "")),
        "target_satisfaction_id": str(review.get("source_target_satisfaction_id", "")),
        "value_feedback_candidate_id": str(review.get("source_value_feedback_candidate_id", "")),
        "value_feedback_review_id": str(review.get("value_feedback_review_id", "")),
        "recommended_future_operation": str(review.get("recommended_future_operation", "")),
        "updated_at_tick": tick,
    }


def _applied_review_ids_from_store(store: dict[str, Any]) -> set[str]:
    applied: set[str] = set()
    for record in store.get("experience", {}).values():
        if not isinstance(record, dict):
            continue
        value_feedback = record.get("value_feedback", {})
        if not isinstance(value_feedback, dict):
            continue
        for link in value_feedback.get("target_links", ()):
            if isinstance(link, dict) and link.get("value_feedback_review_id"):
                applied.add(str(link["value_feedback_review_id"]))
    return applied


def _direction_bucket(value_direction: str, candidate_type: str) -> str:
    if value_direction == "positive" or candidate_type == "value_positive_candidate":
        return "positive"
    if value_direction == "negative" or candidate_type == "value_negative_candidate":
        return "negative"
    if candidate_type == "value_inconclusive_candidate":
        return "inconclusive"
    return "mixed"


def _has_required_fields(review: dict[str, Any]) -> bool:
    for field in REQUIRED_FIELDS:
        value = review.get(field)
        if field == "apply_now":
            if value is not False:
                return False
            continue
        if field == "ready_for_future_application":
            if value is not True:
                return False
            continue
        if value is None or value == "":
            return False
        if isinstance(value, (list, tuple, set, dict)) and not value:
            return False
    return True


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
