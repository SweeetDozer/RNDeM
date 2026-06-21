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


MIN_POST_COMMIT_SEEN_COUNT = 2
MIN_UPDATE_CONFIDENCE_DELTA = 0.05
MIN_UPDATE_REPEATABILITY_DELTA = 0.10
MIN_NEW_IF_PATTERN_SCORE = 0.35


class ExpSMUpdateReviewGate:
    """Reviews committed draft evidence for a future ExpSM update writer."""

    module_name = "expsm_update_review_gate"
    schema = "RNDeM_ExpSM_DraftStore_v1"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        draft_store_path: str | Path,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.draft_store_path = Path(draft_store_path)
        self.review_kind = pattern_registry.id("expsm_update_review")
        self.status_ids = {
            "approved_for_expsm_update": pattern_registry.id("expsm_update_approved_for_update"),
            "wait_more_post_commit_evidence": pattern_registry.id("expsm_update_wait_more_evidence"),
            "rejected_no_significant_delta": pattern_registry.id("expsm_update_rejected_no_significant_delta"),
            "rejected_invalid_committed_draft": pattern_registry.id("expsm_update_rejected_invalid_committed_draft"),
            "rejected_missing_commit_snapshot": pattern_registry.id("expsm_update_rejected_missing_commit_snapshot"),
            "already_update_reviewed": pattern_registry.id("expsm_update_review"),
        }
        self.reason_ids = {
            "post_commit_evidence": pattern_registry.id("expsm_update_post_commit_evidence"),
            "confidence_improved": pattern_registry.id("expsm_update_confidence_improved"),
            "repeatability_improved": pattern_registry.id("expsm_update_repeatability_improved"),
            "new_relevant_context": pattern_registry.id("expsm_update_new_relevant_context"),
            "no_significant_delta": pattern_registry.id("expsm_update_no_significant_delta"),
            "invalid_structure": pattern_registry.id("expsm_update_invalid_structure"),
            "missing_commit_snapshot": pattern_registry.id("expsm_update_rejected_missing_commit_snapshot"),
        }
        self._reviewed_draft_ids: set[str] = set()

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        if system_state.mode != "consolidation":
            return []
        try:
            store = self._load_store()
        except ValueError as exc:
            return [self._module_update(tick, f"expsm_update_review_store_error: {exc}")]

        changed = False
        operations: list[ContextOperation] = []
        for draft in store.get("drafts", ()):
            if not isinstance(draft, dict):
                continue
            draft_id = str(draft.get("draft_id", ""))
            if not draft_id or draft_id in self._reviewed_draft_ids:
                continue
            post_commit = draft.get("post_commit")
            if draft.get("draft_status") != "draft_committed" or not isinstance(post_commit, dict):
                continue
            if not post_commit.get("pending_expsm_update"):
                continue
            if not draft.get("committed_experience_id"):
                review = self._review_result("rejected_invalid_committed_draft", 0.0, ["invalid_structure"], {})
            else:
                review = self._review_draft(draft)
            update_review_id = self.id_gen.next("expsm_update_review")
            self._apply_review(draft, post_commit, update_review_id, tick, review)
            changed = True
            self._reviewed_draft_ids.add(draft_id)
            operations.append(self._review_operation(tick, draft, update_review_id, review))

        if changed:
            self._save_store(store)
        return operations

    def _load_store(self) -> dict[str, Any]:
        if not self.draft_store_path.exists():
            return {"schema": self.schema, "drafts": []}
        try:
            with self.draft_store_path.open("r", encoding="utf-8") as handle:
                store = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{self.draft_store_path} is not valid JSON: {exc}") from exc
        if not isinstance(store, dict):
            raise ValueError(f"{self.draft_store_path} must contain a JSON object")
        if store.get("schema") != self.schema:
            raise ValueError(f"{self.draft_store_path} has unsupported schema: {store.get('schema')}")
        if not isinstance(store.get("drafts"), list):
            raise ValueError(f"{self.draft_store_path} must contain a drafts list")
        return store

    def _save_store(self, store: dict[str, Any]) -> None:
        self.draft_store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.draft_store_path.open("w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2)

    def _review_draft(self, draft: dict[str, Any]) -> dict[str, Any]:
        if not self._has_valid_structure(draft):
            return self._review_result("rejected_invalid_committed_draft", 0.0, ["invalid_structure"], {})
        snapshot = draft.get("commit_snapshot")
        if not isinstance(snapshot, dict):
            return self._review_result("rejected_missing_commit_snapshot", 0.0, ["missing_commit_snapshot"], {})

        post_commit = draft.get("post_commit", {})
        post_commit_seen_count = int(post_commit.get("post_commit_seen_count", 0) or 0)
        metrics = draft.get("metrics", {})
        snapshot_metrics = snapshot.get("metrics", {})
        current_seen = int(draft.get("seen_count", 0) or 0)
        snapshot_seen = int(snapshot.get("seen_count", 0) or 0)
        confidence_delta = round(float(metrics.get("avg_confidence", 0.0)) - float(snapshot_metrics.get("avg_confidence", 0.0)), 3)
        seen_delta = current_seen - snapshot_seen
        repeatability_delta = round((seen_delta / max(1, snapshot_seen)), 3)
        new_relevant = self._new_relevant_if_patterns(draft, snapshot)
        deltas = {
            "post_commit_seen_count": post_commit_seen_count,
            "seen_delta": seen_delta,
            "confidence_delta": confidence_delta,
            "repeatability_delta": repeatability_delta,
            "new_relevant_if_patterns": new_relevant,
        }
        reasons: list[str] = []
        if post_commit_seen_count >= MIN_POST_COMMIT_SEEN_COUNT:
            reasons.append("post_commit_evidence")
        if confidence_delta >= MIN_UPDATE_CONFIDENCE_DELTA:
            reasons.append("confidence_improved")
        if seen_delta >= 2 or repeatability_delta >= MIN_UPDATE_REPEATABILITY_DELTA:
            reasons.append("repeatability_improved")
        if new_relevant:
            reasons.append("new_relevant_context")
        score = _clamp(
            min(post_commit_seen_count * 0.15, 0.45)
            + max(0.0, confidence_delta) * 2.0
            + max(0.0, seen_delta) * 0.05
            + (0.15 if new_relevant else 0.0)
        )
        if reasons and (
            post_commit_seen_count >= MIN_POST_COMMIT_SEEN_COUNT
            or confidence_delta >= MIN_UPDATE_CONFIDENCE_DELTA
            or seen_delta >= 2
            or new_relevant
        ):
            return self._review_result("approved_for_expsm_update", score, reasons, deltas)
        if post_commit_seen_count >= MIN_POST_COMMIT_SEEN_COUNT:
            return self._review_result("rejected_no_significant_delta", score, ["no_significant_delta"], deltas)
        return self._review_result("wait_more_post_commit_evidence", score, ["post_commit_evidence"], deltas)

    def _has_valid_structure(self, draft: dict[str, Any]) -> bool:
        if not draft.get("committed_experience_id") or not draft.get("draft_signature"):
            return False
        if not isinstance(draft.get("metrics"), dict) or not draft.get("metrics"):
            return False
        if not draft.get("if_patterns") or not draft.get("then_patterns"):
            return False
        return bool(draft.get("result_patterns") or draft.get("outcome_patterns"))

    def _new_relevant_if_patterns(self, draft: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
        snapshot_patterns = set(snapshot.get("if_patterns", ()))
        new_patterns: list[str] = []
        for record in draft.get("if_patterns_scored", ()):
            if not isinstance(record, dict):
                continue
            pattern_id = record.get("pattern")
            if not pattern_id or pattern_id in snapshot_patterns:
                continue
            if float(record.get("score", 0.0)) >= MIN_NEW_IF_PATTERN_SCORE:
                new_patterns.append(str(pattern_id))
        return new_patterns

    def _review_result(self, status: str, score: float, reason_keys: list[str], deltas: dict[str, Any]) -> dict[str, Any]:
        if status == "approved_for_expsm_update":
            update_status = "approved_pending_update_writer"
        elif status == "wait_more_post_commit_evidence":
            update_status = "wait_more_post_commit_evidence"
        elif status == "rejected_no_significant_delta":
            update_status = "rejected_no_significant_delta"
        else:
            update_status = status
        return {
            "review_status": status,
            "update_status": update_status,
            "decision_score": round(_clamp(score), 3),
            "reason_keys": reason_keys,
            "reasons": [self.reason_ids[key] for key in reason_keys if key in self.reason_ids],
            "deltas": deltas,
        }

    def _apply_review(
        self,
        draft: dict[str, Any],
        post_commit: dict[str, Any],
        update_review_id: str,
        tick: int,
        review: dict[str, Any],
    ) -> None:
        post_commit["update_review"] = {
            "last_review_id": update_review_id,
            "last_review_tick": tick,
            "review_status": review["review_status"],
            "decision_score": review["decision_score"],
            "reasons": list(review["reasons"]),
        }
        if review["review_status"] == "rejected_no_significant_delta":
            post_commit["pending_expsm_update"] = False
        else:
            post_commit["pending_expsm_update"] = True
        post_commit["update_status"] = review["update_status"]
        draft["post_commit"] = post_commit
        draft["draft_status"] = "draft_committed"

    def _review_operation(
        self,
        tick: int,
        draft: dict[str, Any],
        update_review_id: str,
        review: dict[str, Any],
    ) -> ContextOperation:
        payload = {
            "update_review_id": update_review_id,
            "review_kind": self.review_kind,
            "draft_id": draft.get("draft_id"),
            "committed_experience_id": draft.get("committed_experience_id"),
            "review_status": review["review_status"],
            "review_status_pattern_id": self.status_ids.get(review["review_status"], self.review_kind),
            "update_status": review["update_status"],
            "decision_score": review["decision_score"],
            "reasons": list(review["reasons"]),
            "deltas": dict(review["deltas"]),
            "permanent_memory_modified": False,
            "activation": 0.75,
            "ttl": 14,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.EXPSM_UPDATE_REVIEW,
            tick,
            self.module_name,
            None,
            payload,
        )

    def _module_update(self, tick: int, detail: str) -> ContextOperation:
        payload = {
            "module_update_id": self.id_gen.next("mod_update"),
            "module": self.module_name,
            "status": "expsm_update_review_error",
            "detail": detail,
            "activation": 0.35,
            "ttl": 6,
        }
        return ContextOperation(self.id_gen.next("op"), OperationMarker.MODULE_UPDATE, tick, self.module_name, None, payload)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
