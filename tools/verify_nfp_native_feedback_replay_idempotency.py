#!/usr/bin/env python3
from __future__ import annotations

import json
import multiprocessing
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.expsm.nfp_native_feedback import NFPFeedbackEvaluationStatus
from clc.expsm.nfp_native_feedback_apply import (
    FeedbackEvidenceDigestV1,
    NativeFeedbackEventKeyV1,
    NFPFeedbackApplyRecoveryStatus,
    NFPFeedbackApplyStatus,
    NFPFeedbackApplyWriter,
    _evidence_digest_payload,
    _sha256_json,
    reconcile_nfp_feedback_readback_failure,
)
from clc.experience.expsm_native_create import ExpSMCreateStatus, NFPExpSMCreateWriter
from clc.consolidation.expsm_commit_writer import ExpSMCommitWriter
from clc.consolidation.expsm_store_transaction import ExpSMStoreTransaction
from clc.consolidation.expsm_update_writer import ExpSMUpdateWriter
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.value_feedback_update_writer import ValueFeedbackUpdateWriter
from clc.expsm.expsm_outcome_feedback import ExpSMOutcomeFeedback
from clc.field.active_context_field import ActiveContextField
from clc.expsm.nfp_operational_retrieval import (
    NFPExpSMRetrievalConfig,
    NFPExpSMRetrievalQuery,
    NFPExpSMRetriever,
)
from clc.runtime.memory_mutation_policy import RuntimeProfile, policy_for_profile
from clc.system.system_state import SystemState
from Memory.ExpSM.Exp_CRUD import ExpSMCRUD
from tools.verify_expsm_persistence_stage1 import _audit_writer_ast
from tools.verify_nfp_expsm_policy_gated_create import _request
from tools.verify_nfp_native_feedback_apply import _evidence, _record
from tools.verify_nfp_native_feedback_evaluation import _window
from tools.verify_value_feedback_update_writer import _demo_expsm_store, _ready_review


OCCURRENCE = "22222222-2222-4222-8222-222222222222"


def _apply_worker(path: str, occurrence: str, classification: str, start, results) -> None:
    try:
        store = json.loads(Path(path).read_text(encoding="utf-8"))
        record_data = store["experience"]["42"]
        from clc.experience.expsm_representation import ExpSMRecordAdapter, NFPNativeOperationalRecordV1

        parsed = ExpSMRecordAdapter.parse("42", record_data)
        assert isinstance(parsed, NFPNativeOperationalRecordV1)
        evidence = replace(
            _evidence(parsed.record, NFPFeedbackEvaluationStatus(classification)),
            execution_occurrence_id=occurrence,
        )
        writer = NFPFeedbackApplyWriter(
            path, policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True),
            now_provider=lambda: "2030-01-01T00:00:00Z",
        )
        start.wait()
        results.put(writer.apply(evidence).status.value)
    except Exception as exc:  # pragma: no cover - returned to parent
        results.put(f"error:{exc!r}")


class ReplayIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ExpSM_data.json"
        first = _record("42")
        second = _record("43")
        self.path.write_text(json.dumps({
            "experience": {"42": first.to_json_data(), "43": second.to_json_data()},
            "reflexes": {},
        }), encoding="utf-8")
        self.record = first
        self.writer = NFPFeedbackApplyWriter(
            self.path, policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True),
            now_provider=lambda: "2030-01-01T00:00:00Z",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def evidence(self, record=None, classification=NFPFeedbackEvaluationStatus.HIT):
        return replace(_evidence(record or self.record, classification), execution_occurrence_id=OCCURRENCE)

    def reset_store(self) -> None:
        self.path.write_text(json.dumps({
            "experience": {
                "42": _record("42").to_json_data(),
                "43": _record("43").to_json_data(),
            },
            "reflexes": {},
        }), encoding="utf-8")

    def seed_v2(self) -> dict[str, object]:
        self.reset_store()
        self.assertEqual(self.writer.apply(self.evidence()).status, NFPFeedbackApplyStatus.UPDATED)
        return json.loads(self.path.read_text(encoding="utf-8"))["native_feedback_receipts"]

    def v2_with_records(self, records: dict[str, object]) -> dict[str, object]:
        receipts = self.seed_v2()
        store = json.loads(self.path.read_text(encoding="utf-8"))
        store["experience"].update(records)
        self.path.write_text(json.dumps(store), encoding="utf-8")
        ExpSMStoreTransaction(self.path).load_state_strict()
        return receipts

    def writer_context(self):
        root = Path(self.temp.name)
        registry = PatternRegistry(root / "pattern_manifest.json")
        ids = IdGenerator()
        return registry, ids, ContextMemory(ids, registry)

    @staticmethod
    def add_decision(memory, ids, tick: int, pattern_id: str) -> None:
        memory.add_event(ContextOperation(
            ids.next("op"), OperationMarker.INTERNAL_DECISION, tick, "test", None,
            {"decision_pattern_id": pattern_id, "system_mode_at_selection": "consolidation"},
        ))

    def test_duplicate_survives_reopen_without_second_increment(self) -> None:
        first = self.writer.apply(self.evidence())
        after_first = self.path.read_bytes()
        reopened = NFPFeedbackApplyWriter(
            self.path, policy_for_profile(RuntimeProfile.SAFE_DEMO, memory_is_temporary=True),
        )
        duplicate = reopened.apply(self.evidence())
        self.assertEqual(first.status, NFPFeedbackApplyStatus.UPDATED)
        self.assertEqual(duplicate.status, NFPFeedbackApplyStatus.ALREADY_APPLIED)
        self.assertEqual(self.path.read_bytes(), after_first)
        store = json.loads(after_first)
        self.assertEqual(store["store_schema_version"], 2)
        self.assertEqual(store["experience"]["42"]["hits"], 4)
        self.assertEqual(len(store["native_feedback_receipts"]["by_event_key"]), 1)

    def test_identity_and_digest_versions_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            NativeFeedbackEventKeyV1("42", OCCURRENCE, 2)
        with self.assertRaises(ValueError):
            NativeFeedbackEventKeyV1("42", "not-a-uuid")
        with self.assertRaises(ValueError):
            FeedbackEvidenceDigestV1("not-a-digest")
        with self.assertRaises(ValueError):
            FeedbackEvidenceDigestV1("0" * 64, 2)

    def test_production_evidence_digest_is_deterministic_and_sensitive(self) -> None:
        evidence_a = self.evidence()
        evidence_b = replace(_evidence(_record("42"), NFPFeedbackEvaluationStatus.HIT),
                             execution_occurrence_id=OCCURRENCE)
        payload = _evidence_digest_payload(evidence_a)
        reordered_payload = dict(reversed(tuple(payload.items())))
        self.assertEqual(_sha256_json(payload), _sha256_json(reordered_payload))
        first = self.writer.apply(evidence_a)
        duplicate = self.writer.apply(evidence_b)
        self.assertEqual(duplicate.status, NFPFeedbackApplyStatus.ALREADY_APPLIED)
        self.assertEqual(first.evidence_digest, duplicate.evidence_digest)
        variants = (
            replace(evidence_b, agreement_threshold=0.5000001),
            replace(evidence_b, effect_similarity=0.9000001),
            replace(evidence_b, classification=NFPFeedbackEvaluationStatus.MISS),
            replace(evidence_b, predicted_effect=replace(evidence_b.predicted_effect, delta_values=(0.4, -0.4))),
            replace(evidence_b, actual_effect=replace(evidence_b.actual_effect, delta_values=(0.4, -0.4))),
            replace(evidence_b, target_core=replace(evidence_b.target_core, source_support_count=99)),
        )
        for variant in variants:
            result = self.writer.apply(variant)
            self.assertEqual(result.status, NFPFeedbackApplyStatus.EVENT_CONFLICT)
            self.assertNotEqual(result.evidence_digest, first.evidence_digest)

    def test_same_key_different_payload_conflicts_without_mutation(self) -> None:
        original = self.evidence()
        self.writer.apply(original)
        before = self.path.read_bytes()
        variants = (
            replace(original, agreement_threshold=0.5),
            replace(original, effect_similarity=0.9),
            replace(original, classification=NFPFeedbackEvaluationStatus.MISS),
            replace(original, predicted_effect=replace(original.predicted_effect, delta_values=(0.4, -0.4))),
            replace(original, actual_effect=replace(original.actual_effect, delta_values=(0.4, -0.4))),
            replace(original, target_core=replace(original.target_core, source_support_count=99)),
        )
        for variant in variants:
            with self.subTest(variant=variant):
                conflict = self.writer.apply(variant)
                self.assertEqual(conflict.status, NFPFeedbackApplyStatus.EVENT_CONFLICT)
                self.assertEqual(self.path.read_bytes(), before)

    def test_occurrence_cannot_be_attributed_to_another_source(self) -> None:
        self.writer.apply(self.evidence())
        before = self.path.read_bytes()
        other = _record("43")
        conflict = self.writer.apply(self.evidence(other))
        self.assertEqual(conflict.status, NFPFeedbackApplyStatus.EVENT_CONFLICT)
        self.assertEqual(self.path.read_bytes(), before)

    def test_different_occurrences_apply_independently_and_ledger_is_unbounded(self) -> None:
        for index in range(30):
            occurrence = f"{index + 1:08x}-1111-4111-8111-{index + 1:012x}"
            result = self.writer.apply(replace(self.evidence(), execution_occurrence_id=occurrence))
            self.assertEqual(result.status, NFPFeedbackApplyStatus.UPDATED)
        store = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(store["experience"]["42"]["hits"], 33)
        self.assertEqual(len(store["native_feedback_receipts"]["by_event_key"]), 30)

    def test_post_replace_lost_ack_retries_as_already_applied(self) -> None:
        def fail(stage: str) -> None:
            if stage == "post_replace_readback":
                raise OSError("injected lost acknowledgement")

        writer = NFPFeedbackApplyWriter(
            self.path, policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True),
            failure_hook=fail, now_provider=lambda: "2030-01-01T00:00:00Z",
        )
        failed = writer.apply(self.evidence())
        self.assertEqual(failed.status, NFPFeedbackApplyStatus.READBACK_FAILED)
        reconciled = reconcile_nfp_feedback_readback_failure(self.path, failed)
        self.assertEqual(reconciled.status, NFPFeedbackApplyRecoveryStatus.RECONCILED_APPLIED)
        retry = self.writer.apply(self.evidence())
        self.assertEqual(retry.status, NFPFeedbackApplyStatus.ALREADY_APPLIED)
        store = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(store["experience"]["42"]["hits"], 4)

    def test_pre_replace_failure_commits_neither_metrics_nor_receipt(self) -> None:
        before = self.path.read_bytes()

        def fail(stage: str) -> None:
            if stage == "pre_replace":
                raise OSError("injected pre-replace failure")

        writer = NFPFeedbackApplyWriter(
            self.path, policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True),
            failure_hook=fail,
        )
        self.assertEqual(writer.apply(self.evidence()).status, NFPFeedbackApplyStatus.WRITE_FAILED)
        self.assertEqual(self.path.read_bytes(), before)

        applied = self.writer.apply(self.evidence())
        self.assertEqual(applied.status, NFPFeedbackApplyStatus.UPDATED)
        after = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(after["experience"]["42"]["hits"], 4)
        self.assertEqual(len(after["native_feedback_receipts"]["by_event_key"]), 1)
        committed = self.path.read_bytes()
        self.assertEqual(self.writer.apply(self.evidence()).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)
        self.assertEqual(self.path.read_bytes(), committed)

    def test_historical_duplicate_survives_later_legitimate_update(self) -> None:
        event_a = self.evidence()
        self.assertEqual(self.writer.apply(event_a).status, NFPFeedbackApplyStatus.UPDATED)
        event_b = replace(event_a, execution_occurrence_id="33333333-3333-4333-8333-333333333333")
        self.assertEqual(self.writer.apply(event_b).status, NFPFeedbackApplyStatus.UPDATED)
        before_retry = self.path.read_bytes()
        self.assertEqual(self.writer.apply(event_a).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)
        self.assertEqual(self.path.read_bytes(), before_retry)
        store = json.loads(before_retry)
        self.assertEqual(store["experience"]["42"]["hits"], 5)
        self.assertEqual(len(store["native_feedback_receipts"]["by_event_key"]), 2)

    def test_malformed_and_future_receipt_versions_fail_closed(self) -> None:
        self.writer.apply(self.evidence())
        valid = json.loads(self.path.read_text(encoding="utf-8"))
        variants = []
        malformed = json.loads(json.dumps(valid))
        receipt = next(iter(malformed["native_feedback_receipts"]["by_event_key"].values()))
        receipt.pop("classification")
        variants.append(malformed)
        future = json.loads(json.dumps(valid))
        future["native_feedback_receipts"]["identity_version"] = 2
        variants.append(future)
        for candidate in variants:
            with self.subTest(candidate=candidate):
                self.path.write_text(json.dumps(candidate), encoding="utf-8")
                before = self.path.read_bytes()
                result = self.writer.apply(replace(
                    self.evidence(),
                    execution_occurrence_id="44444444-4444-4444-8444-444444444444",
                ))
                self.assertEqual(result.status, NFPFeedbackApplyStatus.STORE_INVALID)
                self.assertEqual(self.path.read_bytes(), before)

    def test_one_atomic_replace_and_zero_for_nonmutating_outcomes(self) -> None:
        real_replace = Path.replace
        replacements = 0

        def counted(source: Path, target: Path) -> Path:
            nonlocal replacements
            if Path(target) == self.path:
                replacements += 1
            return real_replace(source, target)

        with patch("pathlib.Path.replace", counted):
            self.assertEqual(self.writer.apply(self.evidence()).status, NFPFeedbackApplyStatus.UPDATED)
        self.assertEqual(replacements, 1)
        with patch("pathlib.Path.replace", counted):
            self.assertEqual(self.writer.apply(self.evidence()).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)
            conflict = replace(self.evidence(), classification=NFPFeedbackEvaluationStatus.MISS)
            self.assertEqual(self.writer.apply(conflict).status, NFPFeedbackApplyStatus.EVENT_CONFLICT)
        self.assertEqual(replacements, 1)

        self.reset_store()
        failing = NFPFeedbackApplyWriter(
            self.path,
            policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True),
            failure_hook=lambda stage: (_ for _ in ()).throw(OSError("pre-replace"))
            if stage == "pre_replace" else None,
        )
        with patch("pathlib.Path.replace", counted):
            self.assertEqual(failing.apply(self.evidence()).status, NFPFeedbackApplyStatus.WRITE_FAILED)
        self.assertEqual(replacements, 1)

    def test_v2_receipts_survive_other_authoritative_writer_families(self) -> None:
        def commit() -> None:
            receipts = self.v2_with_records({})
            registry, ids, memory = self.writer_context()
            draft_path = Path(self.temp.name) / "commit_drafts.json"
            draft_path.write_text(json.dumps({"drafts": [{
                "draft_id": "draft:commit", "draft_status": "draft_ready_to_commit",
                "target": "ExpSM", "draft_signature": ["if", "then", "result"],
                "if_patterns": [registry.id("state_integrity_preservation")],
                "then_patterns": [registry.id("action_preserve_integrity")],
                "result_patterns": [registry.id("state_integrity_preservation")],
                "seen_count": 3, "metrics": {"avg_confidence": 0.8, "support_count": 3},
                "commit_review": {"review_status": "ready_to_commit", "last_review_id": "review:commit"},
            }]}), encoding="utf-8")
            writer = ExpSMCommitWriter(ids, registry, draft_path, self.path,
                policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True))
            self.add_decision(memory, ids, 1, writer.commit_action_id)
            before = len(json.loads(self.path.read_text())["experience"])
            operations = writer.run(2, memory, ActiveContextField(), SystemState(mode="consolidation"))
            after = json.loads(self.path.read_text())
            self.assertTrue(any(op.marker == OperationMarker.MEMORY_COMMITTED for op in operations), operations)
            self.assertEqual(len(after["experience"]), before + 1)
            self.assert_v2_receipts(after, receipts)

        def update() -> None:
            base = _demo_expsm_store()["experience"]["2"]
            receipts = self.v2_with_records({"2": base})
            registry, ids, memory = self.writer_context()
            draft_path = Path(self.temp.name) / "update_drafts.json"
            draft_path.write_text(json.dumps({"drafts": [{
                "draft_id": "draft:update", "draft_status": "draft_committed",
                "committed_experience_id": "2", "seen_count": 5,
                "metrics": {"avg_confidence": 0.9, "support_count": 5},
                "post_commit": {"pending_expsm_update": True,
                    "update_status": "approved_pending_update_writer", "post_commit_seen_count": 2,
                    "update_review": {"review_status": "approved_for_expsm_update", "last_review_id": "review:update"}},
            }]}), encoding="utf-8")
            writer = ExpSMUpdateWriter(ids, registry, draft_path, self.path,
                policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True))
            self.add_decision(memory, ids, 1, writer.update_action_id)
            old_confidence = base["confidence"]
            operations = writer.run(2, memory, ActiveContextField(), SystemState(mode="consolidation"))
            after = json.loads(self.path.read_text())
            self.assertTrue(any(op.marker == OperationMarker.MEMORY_UPDATED for op in operations))
            self.assertNotEqual(after["experience"]["2"]["confidence"], old_confidence)
            self.assert_v2_receipts(after, receipts)

        def value() -> None:
            receipts = self.v2_with_records(_demo_expsm_store()["experience"])
            registry, ids, memory = self.writer_context()
            memory.add_event(ContextOperation(ids.next("op"), OperationMarker.VALUE_FEEDBACK_REVIEW,
                1, "test", None, _ready_review(registry)))
            writer = ValueFeedbackUpdateWriter(ids, registry, self.path,
                policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True))
            operations = writer.run(2, memory, SystemState(mode="consolidation"))
            after = json.loads(self.path.read_text())
            self.assertTrue(any(op.marker == OperationMarker.VALUE_FEEDBACK_UPDATED for op in operations))
            self.assertEqual(after["experience"]["2"]["value_feedback"]["positive_count"], 1)
            self.assert_v2_receipts(after, receipts)

        def outcome() -> None:
            registry, ids, memory = self.writer_context()
            target, action = registry.id("state_integrity_preservation"), registry.id("action_preserve_integrity")
            record = {"if": [registry.id("internal_tension")], "then": [action],
                "result": [target], "recommendation": [target], "confidence": 0.7,
                "repeatability": 0.6, "hits": 1, "misses": 0, "status": 2}
            receipts = self.v2_with_records({"1": record})
            decision_id = "decision:outcome"
            memory.add_event(ContextOperation(ids.next("op"), OperationMarker.INTERNAL_DECISION, 1, "test", None,
                {"decision_id": decision_id, "decision_pattern_id": action, "source": "expsm_mechanism_search",
                 "source_experience_id": "1", "source_mechanism_search_id": "search:1",
                 "source_target_pattern_id": target}))
            effect_id = ids.next("op")
            memory.add_event(ContextOperation(effect_id, OperationMarker.INTERNAL_ACTION_EFFECT, 2, "test", None,
                {"effect_id": effect_id, "source_decision_id": decision_id, "effect_pattern_id": target, "effect_kind": target}))
            memory.add_event(ContextOperation(ids.next("op"), OperationMarker.OUTCOME_EVALUATION, 3, "test", None,
                {"outcome_id": "outcome:1", "source_event_id": effect_id, "source_decision_id": decision_id,
                 "outcome_status": "confirmed", "outcome_pattern_id": target, "matched_patterns": [target]}))
            operations = ExpSMOutcomeFeedback(ids, registry, self.path).run(4, memory, ActiveContextField(), SystemState())
            after = json.loads(self.path.read_text())
            self.assertTrue(operations)
            self.assertEqual(after["experience"]["1"]["hits"], 2)
            self.assert_v2_receipts(after, receipts)

        commit(); update(); value(); outcome()

        receipt_before = self.seed_v2()

        writers = {
            "NFPExpSMCreateWriter": lambda: self.assertEqual(
                NFPExpSMCreateWriter(
                    self.path,
                    policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True),
                ).create(_request("request:v2-preservation")).status,
                ExpSMCreateStatus.CREATED,
            ),
            "NFPFeedbackApplyWriter": lambda: self.assertEqual(
                self.writer.apply(replace(
                    self.evidence(),
                    execution_occurrence_id="55555555-5555-4555-8555-555555555555",
                )).status,
                NFPFeedbackApplyStatus.UPDATED,
            ),
            "ExpSMCRUD": lambda: ExpSMCRUD(self.path).create_experience(
                ["a"], ["b"], ["c"], ["b"], experience_id="100"
            ),
        }
        for name, mutate in writers.items():
            with self.subTest(writer=name):
                receipt_before = self.seed_v2()
                before = json.loads(self.path.read_text(encoding="utf-8"))
                mutate()
                after = json.loads(self.path.read_text(encoding="utf-8"))
                self.assertEqual(after["store_schema_version"], 2)
                self.assertNotEqual(after["experience"], before["experience"])
                if name == "NFPFeedbackApplyWriter":
                    self.assertEqual(len(after["native_feedback_receipts"]["by_event_key"]), 2)
                    for key, receipt in receipt_before["by_event_key"].items():
                        self.assertEqual(after["native_feedback_receipts"]["by_event_key"][key], receipt)
                else:
                    self.assertEqual(after["native_feedback_receipts"], receipt_before)

        audit = _audit_writer_ast()
        self.assertEqual(audit.writer_definitions, 7)
        self.assertEqual(audit.mutation_paths, 7)
        self.assertEqual(audit.direct_write_violations, ())
        self.assertEqual(audit.transaction_violations, ())
        self.assertEqual(audit.store_order_violations, ())

    def assert_v2_receipts(self, store, receipts) -> None:
        self.assertEqual(store["store_schema_version"], 2)
        self.assertEqual(store["native_feedback_receipts"], receipts)

    def test_receipts_are_not_cognitive_retrieval_records(self) -> None:
        self.writer.apply(self.evidence())
        result = NFPExpSMRetriever(self.path).retrieve(
            NFPExpSMRetrievalQuery(_window("query", (0.2, 0.8), 4)),
            NFPExpSMRetrievalConfig(1.0),
        )
        self.assertEqual({candidate.source_experience_id for candidate in result.candidates}, {"42", "43"})

    def test_cross_process_duplicate_and_conflict_are_serialized(self) -> None:
        for classifications, expected in (
            (("hit", "hit"), {"updated", "already_applied"}),
            (("hit", "miss"), {"updated", "event_conflict"}),
        ):
            self.path.write_text(json.dumps({
                "experience": {
                    "42": _record("42").to_json_data(),
                    "43": _record("43").to_json_data(),
                },
                "reflexes": {},
            }), encoding="utf-8")
            context = multiprocessing.get_context("spawn")
            start = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_apply_worker,
                    args=(str(self.path), OCCURRENCE, classification, start, results),
                )
                for classification in classifications
            ]
            for process in processes:
                process.start()
            start.set()
            outcomes = {results.get(timeout=10) for _ in processes}
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(outcomes, expected)
            store = json.loads(self.path.read_text(encoding="utf-8"))
            self.assertEqual(
                store["experience"]["42"]["hits"] + store["experience"]["42"]["misses"], 6
            )
            self.assertEqual(len(store["native_feedback_receipts"]["by_event_key"]), 1)

    def test_scenario_declares_isolation_and_replay_contracts(self) -> None:
        scenario = json.loads(
            (ROOT / "scenarios/nfp_native_feedback_replay_idempotency.json").read_text(
                encoding="utf-8"
            )
        )
        contract = scenario["expect"]["nfp_native_feedback_replay_idempotency"]
        self.assertEqual(contract["stage"], 2)
        self.assertTrue(all(
            value is True for key, value in contract.items()
            if key not in {"stage", "runtime_wiring"}
        ))
        self.assertFalse(contract["runtime_wiring"])
        self.assertTrue(scenario["expect"]["memory_unchanged"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
