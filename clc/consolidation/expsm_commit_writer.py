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


class ExpSMCommitWriter:
    """Commits mature draft cards into ordinary ExpSM experience records."""

    module_name = "expsm_commit_writer"

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
        self.commit_action_id = pattern_registry.id("action_commit_memory_draft")
        self.commit_kind = pattern_registry.id("memory_committed")
        self.duplicate_skipped_id = pattern_registry.id("memory_commit_duplicate_skipped")
        self.failed_id = pattern_registry.id("memory_commit_failed")
        self._committed_draft_ids: set[str] = set()
        self._reported_duplicate_draft_ids: set[str] = set()

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
        if not self._has_recent_commit_decision(tick, memory):
            return []
        try:
            draft_store = self._load_draft_store()
            expsm_store = self._load_expsm_store()
        except ValueError as exc:
            return [self._module_update(tick, "expsm_commit_failed", self.failed_id, str(exc))]
        existing_by_signature = self._existing_experience_by_signature(expsm_store)
        operations: list[ContextOperation] = []
        draft_changed = False
        expsm_changed = False
        for draft in list(draft_store.get("drafts", ())):
            if not isinstance(draft, dict):
                continue
            draft_id = str(draft.get("draft_id", ""))
            if not draft_id or draft_id in self._committed_draft_ids:
                continue
            if draft.get("committed_experience_id") and draft.get("draft_status") != "draft_committed":
                draft["draft_status"] = "draft_committed"
                draft.setdefault(
                    "commit_result",
                    {
                        "marker": OperationMarker.MEMORY_COMMITTED.value,
                        "status": "repaired_committed_draft_status",
                    },
                )
                self._committed_draft_ids.add(draft_id)
                draft_changed = True
                continue
            valid, reason = self._validate_draft(draft)
            if not valid:
                if reason and draft.get("draft_status") == "draft_ready_to_commit":
                    operations.append(self._module_update(tick, "expsm_commit_failed", self.failed_id, f"{draft_id}: {reason}"))
                continue
            signature_key = _signature_key(draft.get("draft_signature"))
            duplicate_experience_id = existing_by_signature.get(signature_key)
            if duplicate_experience_id is not None:
                self._mark_draft_committed(draft, duplicate_experience_id, tick, duplicate=True)
                self._committed_draft_ids.add(draft_id)
                draft_changed = True
                if draft_id not in self._reported_duplicate_draft_ids:
                    self._reported_duplicate_draft_ids.add(draft_id)
                    operations.append(self._module_update(tick, "expsm_commit_duplicate_skipped", self.duplicate_skipped_id, draft_id))
                continue
            experience_id = self._next_experience_id(expsm_store)
            record = self._experience_record(draft, experience_id)
            expsm_store.setdefault("experience", {})[experience_id] = record
            existing_by_signature[signature_key] = experience_id
            self._mark_draft_committed(draft, experience_id, tick, duplicate=False)
            self._committed_draft_ids.add(draft_id)
            expsm_changed = True
            draft_changed = True
            operations.append(self._commit_operation(tick, draft, experience_id, record))
        if not expsm_changed and not draft_changed:
            return operations
        try:
            if expsm_changed:
                self._atomic_write_json(self.expsm_path, expsm_store)
            if draft_changed:
                self._atomic_write_json(self.draft_store_path, draft_store)
        except OSError as exc:
            return [self._module_update(tick, "expsm_commit_failed", self.failed_id, str(exc))]
        return operations

    def _has_recent_commit_decision(self, tick: int, memory: ContextMemory) -> bool:
        for decision in memory.get_recent_decisions(10):
            if tick - int(decision.get("_event_tick", tick)) > 4:
                continue
            if decision.get("decision_pattern_id") != self.commit_action_id:
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

    def _validate_draft(self, draft: dict[str, Any]) -> tuple[bool, str | None]:
        if draft.get("draft_status") != "draft_ready_to_commit":
            return False, "draft_not_ready"
        if draft.get("target") != "ExpSM":
            return False, "target_not_expsm"
        if draft.get("committed_experience_id"):
            return False, "already_committed"
        if not draft.get("draft_signature"):
            return False, "missing_draft_signature"
        if not draft.get("if_patterns"):
            return False, "missing_if_patterns"
        if not draft.get("then_patterns"):
            return False, "missing_then_patterns"
        if not draft.get("result_patterns") and not draft.get("outcome_patterns"):
            return False, "missing_result_patterns"
        review = draft.get("commit_review", {})
        if review.get("review_status") != "ready_to_commit":
            return False, "missing_ready_commit_review"
        if self._has_technical_if_patterns(draft):
            return False, "technical_if_patterns"
        return True, None

    def _has_technical_if_patterns(self, draft: dict[str, Any]) -> bool:
        return any(_is_technical(self.pattern_registry.debug_name(str(pattern))) for pattern in draft.get("if_patterns", ()))

    def _existing_experience_by_signature(self, expsm_store: dict[str, Any]) -> dict[tuple[Any, ...], str]:
        existing: dict[tuple[Any, ...], str] = {}
        for record_id, record in expsm_store.get("experience", {}).items():
            if not isinstance(record, dict):
                continue
            metadata = record.get("metadata", {})
            signature = metadata.get("draft_signature") if isinstance(metadata, dict) else None
            if signature:
                existing[_signature_key(signature)] = str(record_id)
        return existing

    def _next_experience_id(self, expsm_store: dict[str, Any]) -> str:
        max_id = 0
        for record_id in expsm_store.get("experience", {}).keys():
            try:
                max_id = max(max_id, int(record_id))
            except (TypeError, ValueError):
                continue
        return str(max_id + 1)

    def _experience_record(self, draft: dict[str, Any], experience_id: str) -> dict[str, Any]:
        metrics = draft.get("metrics", {})
        confidence = _clamp(float(metrics.get("avg_confidence", 0.0) or 0.0))
        seen_count = int(draft.get("seen_count", 1) or 1)
        support_count = int(metrics.get("support_count", 0) or 0)
        repeatability = _clamp(max(seen_count, support_count) / 5.0)
        result_patterns = list(draft.get("result_patterns", ())) or list(draft.get("outcome_patterns", ()))
        recommendation = list(draft.get("outcome_patterns", ())) or result_patterns
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return {
            "level": 3,
            "if": list(draft.get("if_patterns", ())),
            "then": list(draft.get("then_patterns", ())),
            "result": result_patterns,
            "recommendation": recommendation,
            "confidence": round(confidence, 3),
            "repeatability": round(repeatability, 3),
            "source": 6,
            "status": 2,
            "hits": 0,
            "misses": 0,
            "created_at_world": now,
            "updated_at_world": now,
            "metadata": {
                "created_by": "RNDeM_CLC_Prototype",
                "source": "memory_draft_commit",
                "source_draft_id": draft.get("draft_id"),
                "source_commit_review_id": draft.get("commit_review", {}).get("last_review_id"),
                "draft_signature": list(draft.get("draft_signature", ())),
                "seen_count": seen_count,
                "support_count": support_count,
                "avg_valence": float(metrics.get("avg_valence", 0.0) or 0.0),
                "avg_priority": float(metrics.get("avg_priority", 0.0) or 0.0),
                "if_patterns_scored": list(draft.get("if_patterns_scored", ())),
                "experience_id": experience_id,
            },
        }

    def _mark_draft_committed(self, draft: dict[str, Any], experience_id: str, tick: int, duplicate: bool) -> None:
        draft["draft_status"] = "draft_committed"
        draft["committed_experience_id"] = experience_id
        draft["committed_at_tick"] = tick
        draft["commit_result"] = {
            "marker": OperationMarker.MEMORY_COMMITTED.value,
            "status": "duplicate_existing_expsm_record" if duplicate else "committed_to_expsm",
        }

    def _commit_operation(self, tick: int, draft: dict[str, Any], experience_id: str, record: dict[str, Any]) -> ContextOperation:
        payload = {
            "memory_commit_id": self.id_gen.next("memory_commit"),
            "commit_kind": self.commit_kind,
            "target": "ExpSM",
            "experience_id": experience_id,
            "source_draft_id": draft.get("draft_id"),
            "source_commit_review_id": draft.get("commit_review", {}).get("last_review_id"),
            "draft_signature": list(draft.get("draft_signature", ())),
            "record_summary": {
                "if_count": len(record.get("if", ())),
                "then_count": len(record.get("then", ())),
                "result_count": len(record.get("result", ())),
                "recommendation_count": len(record.get("recommendation", ())),
                "confidence": record.get("confidence", 0.0),
                "repeatability": record.get("repeatability", 0.0),
            },
            "permanent_memory_modified": True,
            "draft_status": "draft_committed",
            "activation": 0.9,
            "ttl": 18,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.MEMORY_COMMITTED,
            tick,
            self.module_name,
            None,
            payload,
        )

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
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.MODULE_UPDATE,
            tick,
            self.module_name,
            None,
            payload,
        )


def _signature_key(signature: Any) -> tuple[Any, ...]:
    if isinstance(signature, dict):
        return tuple((key, _signature_key(value)) for key, value in sorted(signature.items()))
    if isinstance(signature, (list, tuple)):
        return tuple(_signature_key(value) for value in signature)
    return (signature,)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _is_technical(debug_name: str) -> bool:
    return debug_name.startswith(
        (
            "action_",
            "state_consolidation_",
            "state_pending_candidates_",
            "state_context_load_",
            "state_memory_candidate_",
            "system_mode_",
            "consolidation_",
            "memory_",
            "homeostasis_",
            "learnability_",
            "outcome_",
            "experience_",
        )
    )
