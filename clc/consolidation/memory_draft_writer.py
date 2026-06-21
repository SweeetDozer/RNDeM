import json
import re
from pathlib import Path
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.consolidation.draft_context_relevance_scorer import (
    MAX_FINAL_IF_PATTERNS,
    MIN_RELEVANCE_SCORE,
    DraftContextRelevanceScorer,
)
from clc.consolidation.draft_input_context_enricher import DraftInputContextEnricher
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.runtime.memory_mutation_policy import MemoryMutationPolicy, RuntimeProfile, policy_for_profile
from clc.system.system_state import SystemState


FINAL_DRAFT_STATUSES = {"draft_committed", "draft_rejected", "draft_archived"}


class MemoryDraftWriter:
    """Writes approved memory-write reviews to a safe draft store only."""

    module_name = "memory_draft_writer"
    schema = "RNDeM_ExpSM_DraftStore_v1"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        draft_store_path: str | Path,
        memory_mutation_policy: MemoryMutationPolicy | None = None,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.draft_store_path = Path(draft_store_path)
        self.memory_mutation_policy = memory_mutation_policy or policy_for_profile(RuntimeProfile.MUTATING_MEMORY)
        self.store_action_id = pattern_registry.id("action_store_memory_candidate")
        self.draft_kind = pattern_registry.id("memory_draft_written")
        self.pending_commit_id = pattern_registry.id("memory_draft_pending_commit")
        self.exp_sm_id = pattern_registry.id("memory_draft_exp_sm")
        self.success_id = pattern_registry.id("memory_draft_write_success")
        self.duplicate_skipped_id = pattern_registry.id("memory_draft_write_duplicate_skipped")
        self.failed_id = pattern_registry.id("memory_draft_write_failed")
        self.created_id = pattern_registry.id("memory_draft_created")
        self.merged_id = pattern_registry.id("memory_draft_merged")
        self.strengthened_id = pattern_registry.id("memory_draft_strengthened")
        self.duplicate_merged_id = pattern_registry.id("memory_draft_duplicate_merged")
        self.committed_observation_kind = pattern_registry.id("committed_draft_observed")
        self.committed_strengthened_id = pattern_registry.id("committed_draft_strengthened")
        self.committed_pending_update_id = pattern_registry.id("committed_draft_pending_expsm_update")
        self.merge_skipped_rejected_id = pattern_registry.id("committed_draft_merge_skipped_rejected")
        self.merge_skipped_archived_id = pattern_registry.id("committed_draft_merge_skipped_archived")
        self.context_enricher = DraftInputContextEnricher(pattern_registry)
        self.relevance_scorer = DraftContextRelevanceScorer(pattern_registry)
        self._written_review_ids: set[str] = set()
        self._reported_duplicate_review_ids: set[str] = set()
        self._reported_failure_ticks: set[int] = set()
        self._reported_invalid_review_ids: set[tuple[str, str]] = set()
        self._prime_id_counters_from_existing_drafts()

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        if system_state.mode != "consolidation":
            return []
        if not self._has_recent_store_decision(tick, memory):
            return []
        reviews = [
            review
            for review in memory.get_recent_memory_write_reviews(16)
            if review.get("review_status") == "approved_for_expsm"
            and review.get("write_status") == "approved_pending_writer"
        ]
        if not reviews:
            return []
        if not self.memory_mutation_policy.allow_draft_writes:
            return [
                self._policy_blocked_update(
                    tick,
                    "draft_write_blocked_by_policy",
                    "policy_disallows_draft_writes",
                )
            ]
        try:
            store = self._load_store()
        except ValueError as exc:
            if tick in self._reported_failure_ticks:
                return []
            self._reported_failure_ticks.add(tick)
            return [self._module_update(tick, "draft_store_malformed", self.failed_id, str(exc))]
        self._upgrade_store_for_matching(store, tick)
        existing_review_ids = self._existing_review_ids(store)
        self._coalesce_duplicate_drafts(store, tick)
        drafts_by_signature = self._drafts_by_signature(store)
        operations: list[ContextOperation] = []
        for review in reviews:
            review_id = review.get("review_id")
            if not review_id:
                continue
            if review_id in self._written_review_ids:
                continue
            if review_id in existing_review_ids:
                self._written_review_ids.add(review_id)
                if review_id not in self._reported_duplicate_review_ids:
                    self._reported_duplicate_review_ids.add(review_id)
                    operations.append(self._module_update(tick, "duplicate_skipped", self.duplicate_skipped_id, review_id))
                continue
            draft = self._draft_from_review(tick, review, memory, active_field)
            valid, reason = self._validate_draft_record(draft)
            if not valid:
                operations.extend(self._skip_invalid_draft(tick, review, reason or "invalid_draft"))
                continue
            signature_key = _signature_key(draft.get("draft_signature"))
            existing = drafts_by_signature.get(signature_key)
            write_kind = "draft_created"
            written_draft = draft
            if existing is not None:
                existing_status = existing.get("draft_status")
                if existing_status == "draft_committed":
                    self._merge_committed_draft_observation(existing, draft, tick)
                    self._save_store(store)
                    self._written_review_ids.add(review_id)
                    existing_review_ids.add(review_id)
                    operations.append(self._committed_draft_observed_operation(tick, existing, review))
                    continue
                if existing_status in {"draft_rejected", "draft_archived"}:
                    self._written_review_ids.add(review_id)
                    existing_review_ids.add(review_id)
                    status = f"committed_draft_merge_skipped_{existing_status.removeprefix('draft_')}"
                    status_id = self.merge_skipped_rejected_id if existing_status == "draft_rejected" else self.merge_skipped_archived_id
                    detail = f"draft_id={existing.get('draft_id')} review_id={review_id}"
                    operations.append(self._module_update(tick, status, status_id, detail))
                    continue
                self._merge_draft(existing, draft, tick)
                write_kind = "draft_merged"
                written_draft = existing
            else:
                store["drafts"].append(draft)
                drafts_by_signature[signature_key] = draft
            self._save_store(store)
            self._written_review_ids.add(review_id)
            existing_review_ids.add(review_id)
            operations.append(self._draft_written_operation(tick, written_draft, write_kind, review))
        return operations

    def _has_recent_store_decision(self, tick: int, memory: ContextMemory) -> bool:
        for decision in memory.get_recent_decisions(10):
            if tick - int(decision.get("_event_tick", tick)) > 4:
                continue
            if decision.get("decision_pattern_id") != self.store_action_id:
                continue
            if decision.get("system_mode_at_selection") != "consolidation":
                continue
            return True
        return False

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
        drafts = store.get("drafts")
        if not isinstance(drafts, list):
            raise ValueError(f"{self.draft_store_path} must contain a drafts list")
        return store

    def _save_store(self, store: dict[str, Any]) -> None:
        self.draft_store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.draft_store_path.open("w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2)

    def _draft_from_review(
        self,
        tick: int,
        review: dict[str, Any],
        memory: ContextMemory,
        active_field: ActiveContextField,
    ) -> dict[str, Any]:
        core_chain = dict(review.get("core_chain", {}))
        context = self.context_enricher.build_if_patterns(review, memory, active_field)
        scored_if_patterns = self.relevance_scorer.score_if_patterns(context.if_patterns, review, memory, active_field)
        final_if_patterns = [
            record["pattern"]
            for record in scored_if_patterns
            if not record.get("rejected") and record.get("score", 0.0) >= MIN_RELEVANCE_SCORE
        ][:MAX_FINAL_IF_PATTERNS]
        then_patterns = self._pattern_list(core_chain, "decision_patterns")
        result_patterns = self._pattern_list(core_chain, "effect_patterns")
        outcome_patterns = self._pattern_list(core_chain, "outcome_patterns")
        predicted_patterns = self._pattern_list(core_chain, "predicted_patterns")
        avg_valence = float(review.get("avg_valence", 0.0))
        context_enrichment = context.as_metadata()
        context_enrichment.update(
            {
                "candidate_if_pattern_count": len(context.if_patterns),
                "final_if_pattern_count": len(final_if_patterns),
                "filtered_out_count": context.filtered_out_count + max(0, len(context.if_patterns) - len(final_if_patterns)),
                "min_relevance_score": MIN_RELEVANCE_SCORE,
                "relevance_scoring_used": True,
            }
        )
        context_enrichment.pop("if_pattern_count", None)
        draft_signature = _draft_signature(
            review.get("suggested_target", "ExpSM"),
            review.get("core_signature", ()),
            final_if_patterns,
            then_patterns,
            result_patterns,
            outcome_patterns,
        )
        return {
            "draft_id": self.id_gen.next("mem_draft"),
            "created_tick": tick,
            "draft_status": "draft_pending_commit",
            "target": review.get("suggested_target", "ExpSM"),
            "source_review_id": review.get("review_id"),
            "source_consolidation_candidate_id": review.get("source_consolidation_candidate_id"),
            "source_group_id": review.get("source_group_id"),
            "source_review_ids": _unique([review.get("review_id")]),
            "source_group_ids": _unique([review.get("source_group_id")]),
            "source_consolidation_candidate_ids": _unique([review.get("source_consolidation_candidate_id")]),
            "core_signature": list(review.get("core_signature", ())),
            "draft_signature": draft_signature,
            "seen_count": 1,
            "first_seen_tick": tick,
            "last_seen_tick": tick,
            "merge_status": "new",
            "if_patterns": final_if_patterns,
            "if_patterns_scored": scored_if_patterns,
            "then_patterns": then_patterns,
            "result_patterns": result_patterns,
            "outcome_patterns": outcome_patterns,
            "core_chain": {
                "decision_patterns": then_patterns,
                "effect_patterns": result_patterns,
                "predicted_patterns": predicted_patterns,
                "outcome_patterns": outcome_patterns,
            },
            "context_enrichment": context_enrichment,
            "metrics": {
                "support_count": int(review.get("support_count", 0)),
                "avg_confidence": float(review.get("avg_confidence", 0.0)),
                "avg_valence": avg_valence,
                "avg_priority": float(review.get("avg_priority", 0.0)),
            },
            "tone_result": {"valence": avg_valence},
            "review": {
                "review_status": review.get("review_status"),
                "decision_score": float(review.get("decision_score", 0.0)),
                "reasons": list(review.get("reasons", ())),
            },
            "write_safety": {
                "permanent_memory_modified": False,
                "draft_only": True,
            },
        }

    def _validate_draft_record(self, draft: dict[str, Any]) -> tuple[bool, str | None]:
        if not draft.get("draft_signature"):
            return False, "missing_draft_signature"
        if not isinstance(draft.get("source_review_ids"), list):
            return False, "invalid_source_review_ids"
        if int(draft.get("seen_count", 0)) < 1:
            return False, "invalid_seen_count"
        if not draft.get("if_patterns"):
            scored = draft.get("if_patterns_scored", ())
            if scored:
                return False, "no_relevant_if_patterns"
            return False, "no_valid_input_context"
        if not any(record.get("score", 0.0) >= MIN_RELEVANCE_SCORE for record in draft.get("if_patterns_scored", ()) if not record.get("rejected")):
            return False, "no_relevant_if_patterns"
        core_chain = draft.get("core_chain", {})
        if not draft.get("then_patterns") and not core_chain.get("predicted_patterns"):
            return False, "missing_then_or_prediction_patterns"
        if not draft.get("result_patterns") and not draft.get("outcome_patterns"):
            return False, "missing_result_or_outcome_patterns"
        write_safety = draft.get("write_safety", {})
        if write_safety.get("permanent_memory_modified") is not False:
            return False, "unsafe_permanent_memory_flag"
        return True, None

    def _pattern_list(self, source: dict[str, Any], key: str) -> list[str]:
        values = source.get(key, ())
        if not isinstance(values, (list, tuple)):
            return []
        return [str(value) for value in values if value]

    def _existing_review_ids(self, store: dict[str, Any]) -> set[str]:
        review_ids: set[str] = set()
        for draft in store.get("drafts", ()):
            if not isinstance(draft, dict):
                continue
            if draft.get("source_review_id"):
                review_ids.add(str(draft.get("source_review_id")))
            for review_id in draft.get("source_review_ids", ()):
                if review_id:
                    review_ids.add(str(review_id))
        return review_ids

    def _prime_id_counters_from_existing_drafts(self) -> None:
        try:
            store = self._load_store()
        except ValueError:
            return
        max_review = 0
        max_draft = 0
        for draft in store.get("drafts", ()):
            if not isinstance(draft, dict):
                continue
            max_review = max(max_review, _numeric_suffix(draft.get("source_review_id"), "mem_review"))
            max_draft = max(max_draft, _numeric_suffix(draft.get("draft_id"), "mem_draft"))
        for _ in range(max_review):
            self.id_gen.next("mem_review")
        for _ in range(max_draft):
            self.id_gen.next("mem_draft")

    def _draft_written_operation(
        self,
        tick: int,
        draft: dict[str, Any],
        write_kind: str,
        source_review: dict[str, Any],
    ) -> ContextOperation:
        payload = {
            "draft_write_id": self.id_gen.next("draft_write"),
            "draft_kind": self.draft_kind,
            "write_kind": write_kind,
            "draft_id": draft.get("draft_id"),
            "draft_path": str(self.draft_store_path),
            "source_review_id": source_review.get("review_id") or draft.get("source_review_id"),
            "source_group_id": source_review.get("source_group_id") or draft.get("source_group_id"),
            "target": draft.get("target", "ExpSM"),
            "draft_status": draft.get("draft_status", "draft_pending_commit"),
            "seen_count": draft.get("seen_count", 1),
            "permanent_memory_modified": False,
            "if_patterns": list(draft.get("if_patterns", ())),
            "then_patterns": list(draft.get("then_patterns", ())),
            "result_patterns": list(draft.get("result_patterns", ())),
            "outcome_patterns": list(draft.get("outcome_patterns", ())),
            "if_patterns_scored": list(draft.get("if_patterns_scored", ())),
            "context_enrichment": {
                "if_pattern_count": draft.get("context_enrichment", {}).get("final_if_pattern_count", 0),
                "candidate_if_pattern_count": draft.get("context_enrichment", {}).get("candidate_if_pattern_count", 0),
                "final_if_pattern_count": draft.get("context_enrichment", {}).get("final_if_pattern_count", 0),
                "filtered_out_count": draft.get("context_enrichment", {}).get("filtered_out_count", 0),
                "fallback_used": draft.get("context_enrichment", {}).get("fallback_used", False),
                "relevance_scoring_used": True,
            },
            "activation": 0.8,
            "ttl": 12,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.MEMORY_DRAFT_WRITTEN,
            tick,
            self.module_name,
            None,
            payload,
        )

    def _committed_draft_observed_operation(
        self,
        tick: int,
        draft: dict[str, Any],
        source_review: dict[str, Any],
    ) -> ContextOperation:
        post_commit = draft.get("post_commit", {})
        payload = {
            "observation_id": self.id_gen.next("committed_observation"),
            "observation_kind": self.committed_observation_kind,
            "draft_id": draft.get("draft_id"),
            "committed_experience_id": draft.get("committed_experience_id"),
            "source_review_id": source_review.get("review_id"),
            "source_group_id": source_review.get("source_group_id"),
            "seen_count": draft.get("seen_count", 1),
            "post_commit_seen_count": post_commit.get("post_commit_seen_count", 0),
            "pending_expsm_update": bool(post_commit.get("pending_expsm_update", True)),
            "update_reason": post_commit.get("update_reason", "committed_draft_strengthened"),
            "permanent_memory_modified": False,
            "activation": 0.75,
            "ttl": 12,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.COMMITTED_DRAFT_OBSERVED,
            tick,
            self.module_name,
            None,
            payload,
        )

    def _upgrade_store_for_matching(self, store: dict[str, Any], tick: int) -> None:
        for draft in store.get("drafts", ()):
            if isinstance(draft, dict):
                self._upgrade_draft_record(draft, tick)

    def _upgrade_draft_record(self, draft: dict[str, Any], tick: int) -> None:
        source_review_id = draft.get("source_review_id")
        source_group_id = draft.get("source_group_id")
        source_candidate_id = draft.get("source_consolidation_candidate_id")
        draft.setdefault("source_review_ids", _unique([source_review_id]))
        draft.setdefault("source_group_ids", _unique([source_group_id]))
        draft.setdefault("source_consolidation_candidate_ids", _unique([source_candidate_id]))
        draft.setdefault("seen_count", max(1, len(draft.get("source_review_ids", ()))))
        created_tick = int(draft.get("created_tick", tick if tick is not None else 0) or 0)
        draft.setdefault("first_seen_tick", created_tick)
        draft.setdefault("last_seen_tick", created_tick)
        draft.setdefault("merge_status", "legacy")
        draft.setdefault(
            "draft_signature",
            _draft_signature(
                draft.get("target", "ExpSM"),
                draft.get("core_signature", ()),
                draft.get("if_patterns", ()),
                draft.get("then_patterns", ()),
                draft.get("result_patterns", ()),
                draft.get("outcome_patterns", ()),
            ),
        )

    def _drafts_by_signature(self, store: dict[str, Any]) -> dict[tuple[Any, ...], dict[str, Any]]:
        drafts_by_signature: dict[tuple[Any, ...], dict[str, Any]] = {}
        for draft in store.get("drafts", ()):
            if not isinstance(draft, dict):
                continue
            key = _signature_key(draft.get("draft_signature"))
            if key and key not in drafts_by_signature:
                drafts_by_signature[key] = draft
        return drafts_by_signature

    def _coalesce_duplicate_drafts(self, store: dict[str, Any], tick: int) -> None:
        unique_drafts: list[dict[str, Any]] = []
        drafts_by_signature: dict[tuple[Any, ...], dict[str, Any]] = {}
        for draft in store.get("drafts", ()):
            if not isinstance(draft, dict):
                continue
            key = _signature_key(draft.get("draft_signature"))
            existing = drafts_by_signature.get(key)
            if existing is None:
                drafts_by_signature[key] = draft
                unique_drafts.append(draft)
                continue
            self._merge_draft(existing, draft, tick)
        store["drafts"] = unique_drafts

    def _merge_draft(self, existing: dict[str, Any], candidate: dict[str, Any], tick: int) -> None:
        old_seen_count = max(1, int(existing.get("seen_count", 1)))
        new_seen_count = old_seen_count + 1
        for singular_key, plural_key in (
            ("source_review_id", "source_review_ids"),
            ("source_group_id", "source_group_ids"),
            ("source_consolidation_candidate_id", "source_consolidation_candidate_ids"),
        ):
            existing[singular_key] = candidate.get(singular_key) or existing.get(singular_key)
            existing[plural_key] = _unique(list(existing.get(plural_key, ())) + list(candidate.get(plural_key, ())))
        existing["seen_count"] = new_seen_count
        existing["first_seen_tick"] = int(existing.get("first_seen_tick", candidate.get("first_seen_tick", tick)) or tick)
        existing["last_seen_tick"] = tick
        existing["merge_status"] = "merged"
        existing["last_update_kind"] = "merged_review"
        if existing.get("draft_status") not in FINAL_DRAFT_STATUSES:
            existing["draft_status"] = "draft_pending_commit"
        existing["metrics"] = _merge_metrics(existing.get("metrics", {}), candidate.get("metrics", {}), old_seen_count, new_seen_count)
        merged_scored = _merge_scored_if_patterns(
            existing.get("if_patterns_scored", ()),
            candidate.get("if_patterns_scored", ()),
        )
        if merged_scored:
            existing["if_patterns_scored"] = merged_scored
            existing["if_patterns"] = _final_if_patterns(merged_scored)
        else:
            existing["if_patterns"] = _unique(list(existing.get("if_patterns", ())) + list(candidate.get("if_patterns", ())))[:MAX_FINAL_IF_PATTERNS]
        existing["context_enrichment"] = _merge_context_enrichment(
            existing.get("context_enrichment", {}),
            candidate.get("context_enrichment", {}),
            len(existing["if_patterns"]),
        )
        existing["review"] = candidate.get("review", existing.get("review", {}))
        existing["tone_result"] = candidate.get("tone_result", existing.get("tone_result", {}))

    def _merge_committed_draft_observation(self, existing: dict[str, Any], candidate: dict[str, Any], tick: int) -> None:
        if "commit_snapshot" not in existing:
            existing["commit_snapshot"] = {
                "seen_count": existing.get("seen_count", 1),
                "metrics": dict(existing.get("metrics", {})),
                "if_patterns": list(existing.get("if_patterns", ())),
                "then_patterns": list(existing.get("then_patterns", ())),
                "result_patterns": list(existing.get("result_patterns", ())),
                "outcome_patterns": list(existing.get("outcome_patterns", ())),
            }
        committed_experience_id = existing.get("committed_experience_id")
        committed_at_tick = existing.get("committed_at_tick")
        commit_result = existing.get("commit_result")
        self._merge_draft(existing, candidate, tick)
        existing["draft_status"] = "draft_committed"
        existing["committed_experience_id"] = committed_experience_id
        existing["committed_at_tick"] = committed_at_tick
        existing["commit_result"] = commit_result
        existing["last_update_kind"] = "post_commit_observation"
        post_commit = dict(existing.get("post_commit", {}))
        post_commit["post_commit_seen_count"] = int(post_commit.get("post_commit_seen_count", 0)) + 1
        post_commit.setdefault("first_post_commit_seen_tick", tick)
        post_commit["last_post_commit_seen_tick"] = tick
        if post_commit.get("last_applied_update_review_id"):
            post_commit["pending_expsm_update"] = False
            post_commit["update_status"] = "updated_in_expsm"
            post_commit["update_reason"] = "committed_draft_strengthened_after_update"
        else:
            post_commit["pending_expsm_update"] = True
            post_commit["update_reason"] = "committed_draft_strengthened"
        existing["post_commit"] = post_commit

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

    def _skip_invalid_draft(self, tick: int, review: dict[str, Any], reason: str) -> list[ContextOperation]:
        review_id = str(review.get("review_id", ""))
        report_key = (review_id, reason)
        if report_key in self._reported_invalid_review_ids:
            return []
        self._reported_invalid_review_ids.add(report_key)
        payload = {
            "module_update_id": self.id_gen.next("mod_update"),
            "module": self.module_name,
            "event": _skip_event(reason),
            "status": "skipped",
            "status_pattern_id": self.failed_id,
            "source_review_id": review_id,
            "reason": reason,
            "activation": 0.35,
            "ttl": 6,
        }
        return [
            ContextOperation(
                self.id_gen.next("op"),
                OperationMarker.MODULE_UPDATE,
                tick,
                self.module_name,
                None,
                payload,
            )
        ]


def _numeric_suffix(value: Any, prefix: str) -> int:
    if not isinstance(value, str):
        return 0
    match = re.fullmatch(rf"{re.escape(prefix)}_(\d+)", value)
    if match is None:
        return 0
    return int(match.group(1))


def _skip_event(reason: str) -> str:
    if reason == "no_valid_input_context":
        return "draft_skipped_empty_if_patterns"
    if reason == "no_relevant_if_patterns":
        return "draft_skipped_no_relevant_if_patterns"
    return "draft_skipped_invalid_record"


def _draft_signature(
    target: Any,
    core_signature: Any,
    if_patterns: Any,
    then_patterns: Any,
    result_patterns: Any,
    outcome_patterns: Any,
) -> list[Any]:
    if core_signature:
        return ["core", str(target), _jsonable(core_signature)]
    return [
        "fallback",
        str(target),
        sorted(str(pattern) for pattern in then_patterns or () if pattern),
        sorted(str(pattern) for pattern in result_patterns or () if pattern),
        sorted(str(pattern) for pattern in outcome_patterns or () if pattern),
        sorted(str(pattern) for pattern in if_patterns or () if pattern),
    ]


def _signature_key(signature: Any) -> tuple[Any, ...]:
    return _tuple_key(signature)


def _tuple_key(value: Any) -> tuple[Any, ...]:
    if isinstance(value, dict):
        return tuple((key, _tuple_key(item)) for key, item in sorted(value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_tuple_key(item) for item in value)
    return (value,)


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _merge_metrics(
    old_metrics: dict[str, Any],
    new_metrics: dict[str, Any],
    old_seen_count: int,
    new_seen_count: int,
) -> dict[str, Any]:
    merged = dict(old_metrics)
    for key in ("avg_confidence", "avg_valence", "avg_priority"):
        old_value = float(old_metrics.get(key, 0.0))
        new_value = float(new_metrics.get(key, 0.0))
        merged[key] = round(((old_value * old_seen_count) + new_value) / new_seen_count, 3)
    old_support = int(old_metrics.get("support_count", 0))
    new_support = int(new_metrics.get("support_count", 0))
    merged["support_count"] = max(old_support, new_support, new_seen_count)
    confidence_values = [
        float(value)
        for value in (
            old_metrics.get("min_confidence"),
            old_metrics.get("max_confidence"),
            old_metrics.get("avg_confidence"),
            new_metrics.get("avg_confidence"),
        )
        if value is not None
    ]
    if confidence_values:
        merged["min_confidence"] = round(min(confidence_values), 3)
        merged["max_confidence"] = round(max(confidence_values), 3)
    return merged


def _merge_scored_if_patterns(old_scored: Any, new_scored: Any) -> list[dict[str, Any]]:
    by_pattern: dict[str, dict[str, Any]] = {}
    for record in list(old_scored or ()) + list(new_scored or ()):
        if not isinstance(record, dict) or not record.get("pattern"):
            continue
        pattern_id = str(record["pattern"])
        existing = by_pattern.get(pattern_id)
        if existing is None:
            by_pattern[pattern_id] = {
                "pattern": pattern_id,
                "score": float(record.get("score", 0.0)),
                "sources": list(record.get("sources", ())),
                "reasons": list(record.get("reasons", ())),
                "seen_count": int(record.get("seen_count", 1)),
                **({"rejected": True} if record.get("rejected") else {}),
            }
            continue
        existing["score"] = round(max(float(existing.get("score", 0.0)), float(record.get("score", 0.0))), 3)
        existing["sources"] = _unique(list(existing.get("sources", ())) + list(record.get("sources", ())))
        existing["reasons"] = _unique(list(existing.get("reasons", ())) + list(record.get("reasons", ())))
        existing["seen_count"] = int(existing.get("seen_count", 1)) + int(record.get("seen_count", 1))
        if record.get("rejected"):
            existing["rejected"] = True
    return sorted(by_pattern.values(), key=lambda item: float(item.get("score", 0.0)), reverse=True)


def _final_if_patterns(scored: Any) -> list[str]:
    patterns: list[str] = []
    for record in sorted(scored or (), key=lambda item: float(item.get("score", 0.0)), reverse=True):
        if record.get("rejected"):
            continue
        if float(record.get("score", 0.0)) < MIN_RELEVANCE_SCORE:
            continue
        patterns.append(str(record.get("pattern")))
        if len(patterns) >= MAX_FINAL_IF_PATTERNS:
            break
    return patterns


def _merge_context_enrichment(old_context: dict[str, Any], new_context: dict[str, Any], final_if_pattern_count: int) -> dict[str, Any]:
    merged = dict(old_context)
    merged["candidate_if_pattern_count"] = max(
        int(old_context.get("candidate_if_pattern_count", old_context.get("if_pattern_count", 0)) or 0),
        int(new_context.get("candidate_if_pattern_count", new_context.get("if_pattern_count", 0)) or 0),
    )
    merged["final_if_pattern_count"] = final_if_pattern_count
    merged["filtered_out_count"] = int(old_context.get("filtered_out_count", 0) or 0) + int(new_context.get("filtered_out_count", 0) or 0)
    merged["min_relevance_score"] = MIN_RELEVANCE_SCORE
    merged["fallback_used"] = bool(old_context.get("fallback_used")) or bool(new_context.get("fallback_used"))
    merged["relevance_scoring_used"] = True
    return merged


def _unique(values: list[Any]) -> list[str]:
    return [str(value) for value in dict.fromkeys(values) if value]
