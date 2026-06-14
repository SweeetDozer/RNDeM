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


MIN_READY_SEEN_COUNT = 2
MIN_READY_SUPPORT_COUNT = 2
MIN_READY_CONFIDENCE = 0.55
MIN_READY_VALENCE_ABS = 0.08
MIN_IF_PATTERN_SCORE = 0.25

REVIEWABLE_STATUSES = {"draft_pending_commit", "draft_wait_more_evidence", "draft_ready_to_commit"}
FINAL_STATUSES = {"draft_committed", "draft_rejected", "draft_archived"}


class DraftCommitGate:
    """Reviews draft memory cards for future permanent commit readiness."""

    module_name = "draft_commit_gate"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        draft_store_path: str | Path,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.draft_store_path = Path(draft_store_path)
        self.review_kind = pattern_registry.id("memory_draft_commit_review")
        self.status_patterns = {
            "ready_to_commit": pattern_registry.id("draft_commit_ready_to_commit"),
            "wait_more_evidence": pattern_registry.id("draft_commit_wait_more_evidence"),
            "rejected_low_quality": pattern_registry.id("draft_commit_rejected_low_quality"),
            "rejected_incomplete": pattern_registry.id("draft_commit_rejected_incomplete"),
            "rejected_no_relevant_context": pattern_registry.id("draft_commit_rejected_no_relevant_context"),
            "rejected_technical_context": pattern_registry.id("draft_commit_rejected_technical_context"),
            "archived_duplicate": pattern_registry.id("draft_commit_archived_duplicate"),
            "already_committed": pattern_registry.id("draft_commit_already_committed"),
        }
        self.reason_patterns = {
            "sufficient_evidence": pattern_registry.id("draft_commit_sufficient_evidence"),
            "high_confidence": pattern_registry.id("draft_commit_high_confidence"),
            "valid_context": pattern_registry.id("draft_commit_valid_context"),
            "valid_structure": pattern_registry.id("draft_commit_valid_structure"),
            "negative_experience_supported": pattern_registry.id("draft_commit_negative_experience_supported"),
            "needs_more_seen_count": pattern_registry.id("draft_commit_needs_more_seen_count"),
            "low_confidence": pattern_registry.id("draft_commit_low_confidence"),
            "low_value": pattern_registry.id("draft_commit_low_value"),
            "missing_if_patterns": pattern_registry.id("draft_commit_missing_if_patterns"),
            "missing_then_patterns": pattern_registry.id("draft_commit_missing_then_patterns"),
            "missing_result_patterns": pattern_registry.id("draft_commit_missing_result_patterns"),
            "technical_context": pattern_registry.id("draft_commit_technical_context"),
            "duplicate": pattern_registry.id("draft_commit_duplicate"),
        }
        self._reviewed_states: set[tuple[str, int, str]] = set()
        self._last_summary: dict[str, int] = {}

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
        try:
            store = self._load_store()
        except ValueError as exc:
            return [self._module_update(tick, f"draft_commit_gate_store_error: {exc}")]
        drafts = [draft for draft in store.get("drafts", ()) if isinstance(draft, dict)]
        duplicate_ids = self._duplicate_draft_ids(drafts)
        operations: list[ContextOperation] = []
        changed = False
        for draft in drafts:
            draft_id = str(draft.get("draft_id", ""))
            draft_status = str(draft.get("draft_status", "draft_pending_commit"))
            seen_count = int(draft.get("seen_count", 1) or 1)
            if not draft_id or draft_status in FINAL_STATUSES:
                continue
            if draft_status not in REVIEWABLE_STATUSES:
                continue
            review_key = (draft_id, seen_count, draft_status)
            if review_key in self._reviewed_states:
                continue
            self._reviewed_states.add(review_key)
            review = self._review_draft(tick, draft, draft_id in duplicate_ids)
            draft["draft_status"] = review["draft_status"]
            draft["commit_review"] = {
                "last_review_id": review["commit_review_id"],
                "last_review_tick": tick,
                "review_status": review["review_status"],
                "reasons": list(review["reasons"]),
                "decision_score": review["decision_score"],
            }
            changed = True
            operations.append(
                ContextOperation(
                    self.id_gen.next("op"),
                    OperationMarker.MEMORY_DRAFT_COMMIT_REVIEW,
                    tick,
                    self.module_name,
                    None,
                    review,
                )
            )
        if changed:
            self._save_store(store)
        self._last_summary = self._summary(store)
        return operations

    def debug_summary(self) -> dict[str, int]:
        return dict(self._last_summary)

    def _load_store(self) -> dict[str, Any]:
        if not self.draft_store_path.exists():
            return {"schema": "RNDeM_ExpSM_DraftStore_v1", "drafts": []}
        try:
            with self.draft_store_path.open("r", encoding="utf-8") as handle:
                store = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{self.draft_store_path} is not valid JSON: {exc}") from exc
        if not isinstance(store, dict):
            raise ValueError(f"{self.draft_store_path} must contain a JSON object")
        if not isinstance(store.get("drafts"), list):
            raise ValueError(f"{self.draft_store_path} must contain a drafts list")
        return store

    def _save_store(self, store: dict[str, Any]) -> None:
        self.draft_store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.draft_store_path.open("w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2)

    def _review_draft(self, tick: int, draft: dict[str, Any], duplicate: bool) -> dict[str, Any]:
        commit_review_id = self.id_gen.next("commit_review")
        valid, structure_reasons = self._validate_structure(draft)
        if duplicate:
            status = "archived_duplicate"
            draft_status = "draft_archived"
            reasons = [self.reason_patterns["duplicate"]]
        elif not valid:
            status = "rejected_incomplete"
            draft_status = "draft_rejected"
            reasons = structure_reasons
        elif self._has_technical_if_patterns(draft):
            status = "rejected_technical_context"
            draft_status = "draft_rejected"
            reasons = [self.reason_patterns["technical_context"]]
        elif not self._has_relevant_if_scores(draft):
            status = "rejected_no_relevant_context"
            draft_status = "draft_rejected"
            reasons = [self.reason_patterns["missing_if_patterns"]]
        else:
            status, draft_status, reasons = self._quality_decision(draft)
        score = self._decision_score(draft)
        return {
            "commit_review_id": commit_review_id,
            "review_kind": self.review_kind,
            "draft_id": draft.get("draft_id"),
            "draft_signature": list(draft.get("draft_signature", ())),
            "review_status": status,
            "review_status_pattern_id": self.status_patterns[status],
            "draft_status": draft_status,
            "decision_score": score,
            "reasons": reasons,
            "metrics": self._metrics_payload(draft),
            "target": draft.get("target", "ExpSM"),
            "permanent_memory_modified": False,
            "activation": max(0.35, min(1.0, score)),
            "ttl": 16,
        }

    def _quality_decision(self, draft: dict[str, Any]) -> tuple[str, str, list[str]]:
        metrics = draft.get("metrics", {})
        seen_count = int(draft.get("seen_count", 1) or 1)
        support_count = int(metrics.get("support_count", 0) or 0)
        avg_confidence = float(metrics.get("avg_confidence", 0.0) or 0.0)
        avg_valence = float(metrics.get("avg_valence", 0.0) or 0.0)
        avg_priority = float(metrics.get("avg_priority", 0.0) or 0.0)
        if avg_confidence < 0.35:
            return "rejected_low_quality", "draft_rejected", [self.reason_patterns["low_confidence"]]
        if abs(avg_valence) < 0.03 and avg_priority < 0.25:
            return "rejected_low_quality", "draft_rejected", [self.reason_patterns["low_value"]]
        if seen_count >= 1 and avg_confidence >= 0.9 and support_count >= 1:
            return (
                "ready_to_commit",
                "draft_ready_to_commit",
                [self.reason_patterns["high_confidence"], self.reason_patterns["valid_context"], self.reason_patterns["valid_structure"]],
            )
        if avg_valence <= -0.15 and avg_confidence >= 0.5 and seen_count >= 2:
            return (
                "ready_to_commit",
                "draft_ready_to_commit",
                [self.reason_patterns["negative_experience_supported"], self.reason_patterns["valid_context"], self.reason_patterns["valid_structure"]],
            )
        if (
            seen_count >= MIN_READY_SEEN_COUNT
            and support_count >= MIN_READY_SUPPORT_COUNT
            and avg_confidence >= MIN_READY_CONFIDENCE
            and abs(avg_valence) >= MIN_READY_VALENCE_ABS
        ):
            return (
                "ready_to_commit",
                "draft_ready_to_commit",
                [self.reason_patterns["sufficient_evidence"], self.reason_patterns["valid_context"], self.reason_patterns["valid_structure"]],
            )
        reasons = [self.reason_patterns["needs_more_seen_count"]]
        if avg_confidence < MIN_READY_CONFIDENCE:
            reasons.append(self.reason_patterns["low_confidence"])
        return "wait_more_evidence", "draft_wait_more_evidence", reasons

    def _validate_structure(self, draft: dict[str, Any]) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if not draft.get("if_patterns"):
            reasons.append(self.reason_patterns["missing_if_patterns"])
        if not draft.get("then_patterns"):
            reasons.append(self.reason_patterns["missing_then_patterns"])
        if not draft.get("result_patterns") and not draft.get("outcome_patterns"):
            reasons.append(self.reason_patterns["missing_result_patterns"])
        if not draft.get("draft_signature"):
            reasons.append(self.reason_patterns["duplicate"])
        if not isinstance(draft.get("metrics"), dict):
            reasons.append(self.reason_patterns["low_value"])
        if not draft.get("if_patterns_scored"):
            reasons.append(self.reason_patterns["missing_if_patterns"])
        return not reasons, reasons

    def _has_technical_if_patterns(self, draft: dict[str, Any]) -> bool:
        return any(_is_technical(self.pattern_registry.debug_name(str(pattern))) for pattern in draft.get("if_patterns", ()))

    def _has_relevant_if_scores(self, draft: dict[str, Any]) -> bool:
        scored = draft.get("if_patterns_scored", ())
        if not isinstance(scored, list):
            return False
        return any(
            isinstance(record, dict)
            and not record.get("rejected")
            and float(record.get("score", 0.0) or 0.0) >= MIN_IF_PATTERN_SCORE
            for record in scored
        )

    def _decision_score(self, draft: dict[str, Any]) -> float:
        metrics = draft.get("metrics", {})
        seen_count = min(1.0, int(draft.get("seen_count", 1) or 1) / max(1, MIN_READY_SEEN_COUNT))
        support = min(1.0, int(metrics.get("support_count", 0) or 0) / max(1, MIN_READY_SUPPORT_COUNT))
        confidence = float(metrics.get("avg_confidence", 0.0) or 0.0)
        valence = min(1.0, abs(float(metrics.get("avg_valence", 0.0) or 0.0)) / 0.5)
        return round(max(0.0, min(1.0, 0.3 * seen_count + 0.25 * support + 0.3 * confidence + 0.15 * valence)), 3)

    def _metrics_payload(self, draft: dict[str, Any]) -> dict[str, Any]:
        metrics = draft.get("metrics", {})
        return {
            "seen_count": int(draft.get("seen_count", 1) or 1),
            "support_count": int(metrics.get("support_count", 0) or 0),
            "avg_confidence": float(metrics.get("avg_confidence", 0.0) or 0.0),
            "avg_valence": float(metrics.get("avg_valence", 0.0) or 0.0),
            "avg_priority": float(metrics.get("avg_priority", 0.0) or 0.0),
        }

    def _duplicate_draft_ids(self, drafts: list[dict[str, Any]]) -> set[str]:
        best_by_signature: dict[str, tuple[str, int, float]] = {}
        duplicate_ids: set[str] = set()
        for draft in drafts:
            signature = json.dumps(draft.get("draft_signature"), sort_keys=True)
            draft_id = str(draft.get("draft_id", ""))
            seen_count = int(draft.get("seen_count", 1) or 1)
            confidence = float(draft.get("metrics", {}).get("avg_confidence", 0.0) or 0.0)
            current = (draft_id, seen_count, confidence)
            best = best_by_signature.get(signature)
            if best is None:
                best_by_signature[signature] = current
                continue
            if (seen_count, confidence) > (best[1], best[2]):
                duplicate_ids.add(best[0])
                best_by_signature[signature] = current
            else:
                duplicate_ids.add(draft_id)
        return duplicate_ids

    def _summary(self, store: dict[str, Any]) -> dict[str, int]:
        drafts = [draft for draft in store.get("drafts", ()) if isinstance(draft, dict)]
        return {
            "total_drafts": len(drafts),
            "ready_to_commit": sum(1 for draft in drafts if draft.get("draft_status") == "draft_ready_to_commit"),
            "wait_more_evidence": sum(1 for draft in drafts if draft.get("draft_status") == "draft_wait_more_evidence"),
            "rejected": sum(1 for draft in drafts if draft.get("draft_status") == "draft_rejected"),
            "archived": sum(1 for draft in drafts if draft.get("draft_status") == "draft_archived"),
        }

    def _module_update(self, tick: int, detail: str) -> ContextOperation:
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.MODULE_UPDATE,
            tick,
            self.module_name,
            None,
            {
                "module_update_id": self.id_gen.next("mod_update"),
                "module": self.module_name,
                "status": "draft_commit_gate_error",
                "detail": detail,
                "activation": 0.25,
                "ttl": 4,
            },
        )


def _is_technical(debug_name: str) -> bool:
    excluded_prefixes = (
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
    return debug_name.startswith(excluded_prefixes)
