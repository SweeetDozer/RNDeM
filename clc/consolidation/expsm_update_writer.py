import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


class ExpSMUpdateWriter:
    """Applies approved post-commit evidence to existing ExpSM experience metadata."""

    module_name = "expsm_update_writer"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        draft_store_path: str | Path,
        expsm_path: str | Path,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.draft_store_path = Path(draft_store_path)
        self.expsm_path = Path(expsm_path)
        self.update_action_id = pattern_registry.id("action_update_committed_expsm_record")
        self.update_kind = pattern_registry.id("memory_updated")
        self.duplicate_skipped_id = pattern_registry.id("memory_update_duplicate_skipped")
        self.failed_id = pattern_registry.id("memory_update_failed")
        self._applied_review_ids: set[str] = set()
        self._reported_duplicate_review_ids: set[str] = set()

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        del active_field
        if system_state.mode != "consolidation":
            return []
        if not self._has_recent_update_decision(tick, memory):
            return []
        try:
            draft_store = self._load_draft_store()
            expsm_store = self._load_expsm_store()
        except ValueError as exc:
            return [self._module_update(tick, "memory_update_failed", self.failed_id, str(exc))]

        operations: list[ContextOperation] = []
        draft_changed = False
        expsm_changed = False
        for draft in draft_store.get("drafts", ()):
            if not isinstance(draft, dict):
                continue
            valid, reason = self._is_update_ready_draft(draft)
            if not valid:
                continue
            post_commit = draft["post_commit"]
            update_review = post_commit["update_review"]
            update_review_id = str(update_review.get("last_review_id", ""))
            if not update_review_id:
                continue
            if update_review_id in self._applied_review_ids or post_commit.get("last_applied_update_review_id") == update_review_id:
                if post_commit.get("pending_expsm_update") or post_commit.get("update_status") != "updated_in_expsm":
                    post_commit["pending_expsm_update"] = False
                    post_commit["update_status"] = "updated_in_expsm"
                    draft["post_commit"] = post_commit
                    draft["draft_status"] = "draft_committed"
                    draft_changed = True
                if update_review_id not in self._reported_duplicate_review_ids:
                    self._reported_duplicate_review_ids.add(update_review_id)
                    operations.append(self._module_update(tick, "memory_update_duplicate_skipped", self.duplicate_skipped_id, update_review_id))
                continue
            experience_id = str(draft.get("committed_experience_id"))
            record = expsm_store.get("experience", {}).get(experience_id)
            if not isinstance(record, dict):
                operations.append(self._module_update(tick, "memory_update_failed", self.failed_id, f"{experience_id}: missing_experience_record"))
                continue

            update_metrics = self._apply_record_update(record, draft, update_review_id, tick)
            self._mark_draft_updated(draft, update_review_id, tick, experience_id)
            self._applied_review_ids.add(update_review_id)
            expsm_changed = True
            draft_changed = True
            operations.append(self._memory_update_operation(tick, draft, experience_id, update_review_id, update_metrics))

        if not expsm_changed and not draft_changed:
            return operations
        try:
            if expsm_changed:
                self._atomic_write_json(self.expsm_path, expsm_store)
            if draft_changed:
                self._atomic_write_json(self.draft_store_path, draft_store)
        except OSError as exc:
            return [self._module_update(tick, "memory_update_failed", self.failed_id, str(exc))]
        return operations

    def _has_recent_update_decision(self, tick: int, memory: ContextMemory) -> bool:
        for decision in memory.get_recent_decisions(10):
            if tick - int(decision.get("_event_tick", tick)) > 4:
                continue
            if decision.get("decision_pattern_id") != self.update_action_id:
                continue
            if decision.get("system_mode_at_selection") != "consolidation":
                continue
            return True
        return False

    def _load_draft_store(self) -> dict[str, Any]:
        if not self.draft_store_path.exists():
            return {"schema": "RNDeM_ExpSM_DraftStore_v1", "drafts": []}
        return self._load_json_object(self.draft_store_path)

    def _load_expsm_store(self) -> dict[str, Any]:
        if not self.expsm_path.exists():
            return {"experience": {}, "reflexes": {}}
        store = self._load_json_object(self.expsm_path)
        if not isinstance(store.get("experience", {}), dict):
            store["experience"] = {}
        if not isinstance(store.get("reflexes", {}), dict):
            store["reflexes"] = {}
        return store

    def _load_json_object(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a JSON object")
        return data

    def _atomic_write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        temp_path.replace(path)

    def _is_update_ready_draft(self, draft: dict[str, Any]) -> tuple[bool, str | None]:
        if draft.get("draft_status") != "draft_committed":
            return False, "draft_not_committed"
        if not draft.get("committed_experience_id"):
            return False, "missing_committed_experience_id"
        post_commit = draft.get("post_commit")
        if not isinstance(post_commit, dict) or not post_commit.get("pending_expsm_update"):
            return False, "no_pending_update"
        if post_commit.get("update_status") != "approved_pending_update_writer":
            return False, "update_not_approved"
        update_review = post_commit.get("update_review")
        if not isinstance(update_review, dict):
            return False, "missing_update_review"
        if update_review.get("review_status") != "approved_for_expsm_update":
            return False, "review_not_approved"
        if post_commit.get("last_applied_update_review_id") == update_review.get("last_review_id"):
            return False, "already_applied"
        return True, None

    def _apply_record_update(
        self,
        record: dict[str, Any],
        draft: dict[str, Any],
        update_review_id: str,
        tick: int,
    ) -> dict[str, Any]:
        metrics = draft.get("metrics", {})
        seen_count = int(draft.get("seen_count", 0) or 0)
        support_count = int(metrics.get("support_count", 0) or 0)
        post_commit_seen_count = int(draft.get("post_commit", {}).get("post_commit_seen_count", 0) or 0)
        old_confidence = float(record.get("confidence", 0.0) or 0.0)
        old_repeatability = float(record.get("repeatability", 0.0) or 0.0)
        draft_confidence = float(metrics.get("avg_confidence", 0.0) or 0.0)
        new_confidence = _clamp((old_confidence * 0.65) + (draft_confidence * 0.35))
        evidence_strength = _clamp(max(seen_count, support_count) / 5.0)
        new_repeatability = _clamp(max(old_repeatability, evidence_strength))
        record["confidence"] = round(new_confidence, 3)
        record["repeatability"] = round(new_repeatability, 3)
        record["updated_at_world"] = _now_iso()
        metadata = dict(record.get("metadata", {})) if isinstance(record.get("metadata"), dict) else {}
        metadata["seen_count"] = seen_count
        metadata["support_count"] = support_count
        metadata["avg_confidence"] = draft_confidence
        metadata["avg_valence"] = float(metrics.get("avg_valence", 0.0) or 0.0)
        metadata["avg_priority"] = float(metrics.get("avg_priority", 0.0) or 0.0)
        metadata["if_patterns_scored"] = _merge_scored_patterns(metadata.get("if_patterns_scored", ()), draft.get("if_patterns_scored", ()))
        metadata["last_post_commit_update_tick"] = tick
        metadata["last_update_review_id"] = update_review_id
        metadata["update_count"] = int(metadata.get("update_count", 0) or 0) + 1
        metadata["post_commit_seen_count_total"] = int(metadata.get("post_commit_seen_count_total", 0) or 0) + post_commit_seen_count
        metadata["source_review_ids"] = _unique(list(metadata.get("source_review_ids", ())) + list(draft.get("source_review_ids", ())))
        metadata["source_group_ids"] = _unique(list(metadata.get("source_group_ids", ())) + list(draft.get("source_group_ids", ())))
        metadata["source_consolidation_candidate_ids"] = _unique(
            list(metadata.get("source_consolidation_candidate_ids", ())) + list(draft.get("source_consolidation_candidate_ids", ()))
        )
        record["metadata"] = metadata
        return {
            "old_confidence": round(old_confidence, 3),
            "new_confidence": round(new_confidence, 3),
            "old_repeatability": round(old_repeatability, 3),
            "new_repeatability": round(new_repeatability, 3),
            "seen_count": seen_count,
            "post_commit_seen_count": post_commit_seen_count,
        }

    def _mark_draft_updated(self, draft: dict[str, Any], update_review_id: str, tick: int, experience_id: str) -> None:
        post_commit = dict(draft.get("post_commit", {}))
        post_commit["pending_expsm_update"] = False
        post_commit["update_status"] = "updated_in_expsm"
        post_commit["last_applied_update_review_id"] = update_review_id
        post_commit["last_applied_update_tick"] = tick
        post_commit["last_updated_experience_id"] = experience_id
        draft["post_commit"] = post_commit
        draft["draft_status"] = "draft_committed"

    def _memory_update_operation(
        self,
        tick: int,
        draft: dict[str, Any],
        experience_id: str,
        update_review_id: str,
        metrics: dict[str, Any],
    ) -> ContextOperation:
        payload = {
            "memory_update_id": self.id_gen.next("memory_update"),
            "update_kind": self.update_kind,
            "target": "ExpSM",
            "experience_id": experience_id,
            "source_draft_id": draft.get("draft_id"),
            "source_update_review_id": update_review_id,
            "update_mode": "metadata_only",
            "updated_fields": ["confidence", "repeatability", "metadata", "updated_at_world"],
            "semantic_core_modified": False,
            "new_record_created": False,
            "reflexes_modified": False,
            "akbsm_modified": False,
            "metrics": metrics,
            "permanent_memory_modified": True,
            "activation": 0.85,
            "ttl": 18,
        }
        return ContextOperation(self.id_gen.next("op"), OperationMarker.MEMORY_UPDATED, tick, self.module_name, None, payload)

    def _module_update(self, tick: int, status: str, status_pattern_id: str, detail: str) -> ContextOperation:
        payload = {
            "module_update_id": self.id_gen.next("mod_update"),
            "module": self.module_name,
            "status": status,
            "status_pattern_id": status_pattern_id,
            "detail": detail,
            "activation": 0.35,
            "ttl": 6,
        }
        return ContextOperation(self.id_gen.next("op"), OperationMarker.MODULE_UPDATE, tick, self.module_name, None, payload)


def _merge_scored_patterns(existing: Any, incoming: Any) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in list(existing or ()) + list(incoming or ()):
        if not isinstance(record, dict) or not record.get("pattern"):
            continue
        pattern = str(record["pattern"])
        current = merged.setdefault(pattern, {"pattern": pattern, "score": 0.0, "sources": [], "reasons": [], "seen_count": 0})
        current["score"] = max(float(current.get("score", 0.0) or 0.0), float(record.get("score", 0.0) or 0.0))
        current["sources"] = _unique(list(current.get("sources", ())) + list(record.get("sources", ())))
        current["reasons"] = _unique(list(current.get("reasons", ())) + list(record.get("reasons", ())))
        current["seen_count"] = max(int(current.get("seen_count", 0) or 0), int(record.get("seen_count", 0) or 0))
    return sorted(merged.values(), key=lambda item: (-float(item.get("score", 0.0)), item.get("pattern", "")))


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value is None or value in result:
            continue
        result.append(value)
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
