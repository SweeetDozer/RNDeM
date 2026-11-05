#!/usr/bin/env python3
from __future__ import annotations

import json
import multiprocessing
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

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
    reconcile_nfp_feedback_readback_failure,
)
from clc.experience.expsm_native_create import ExpSMCreateStatus, NFPExpSMCreateWriter
from clc.expsm.nfp_operational_retrieval import (
    NFPExpSMRetrievalConfig,
    NFPExpSMRetrievalQuery,
    NFPExpSMRetriever,
)
from clc.runtime.memory_mutation_policy import RuntimeProfile, policy_for_profile
from Memory.ExpSM.Exp_CRUD import ExpSMCRUD
from tools.verify_expsm_persistence_stage1 import _audit_writer_ast
from tools.verify_nfp_expsm_policy_gated_create import _request
from tools.verify_nfp_native_feedback_apply import _evidence, _record
from tools.verify_nfp_native_feedback_evaluation import _window


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

    def test_v2_receipts_survive_other_authoritative_writer_families(self) -> None:
        self.writer.apply(self.evidence())
        receipt_before = json.loads(self.path.read_text(encoding="utf-8"))["native_feedback_receipts"]
        create = NFPExpSMCreateWriter(
            self.path,
            policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_is_temporary=True),
        ).create(_request("request:v2-preservation"))
        self.assertEqual(create.status, ExpSMCreateStatus.CREATED)
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["native_feedback_receipts"],
            receipt_before,
        )
        crud = ExpSMCRUD(self.path)
        crud.create_experience(["a"], ["b"], ["c"], ["b"], experience_id="100")
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["native_feedback_receipts"],
            receipt_before,
        )

        audit = _audit_writer_ast()
        self.assertEqual(audit.writer_definitions, 7)
        self.assertEqual(audit.mutation_paths, 7)
        self.assertEqual(audit.direct_write_violations, ())
        self.assertEqual(audit.transaction_violations, ())
        self.assertEqual(audit.store_order_violations, ())

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
