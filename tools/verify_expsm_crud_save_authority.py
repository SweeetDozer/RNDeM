"""RND-110/F01 behavioral regressions; every writable store is temporary."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Memory.ExpSM.Exp_CRUD import ExpSMCRUD, ExpSMStaleSnapshotError, ExpSMReceiptIntegrityError
from clc.consolidation.expsm_store_transaction import ExpSMStoreInvalidError
from clc.expsm.nfp_native_feedback import NFPFeedbackEvaluationStatus
from clc.expsm.nfp_native_feedback_apply import NFPFeedbackApplyStatus, NFPFeedbackApplyWriter
from clc.runtime.memory_mutation_policy import policy_for_profile
from tools.verify_nfp_native_feedback_apply import _evidence, _record

OCCURRENCE = "55555555-5555-4555-8555-555555555555"


class CRUDSaveAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rnd110_crud_")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ExpSM_data.json"
        self.path.write_text(json.dumps({"experience": {}, "reflexes": {}}))

    def create(self, crud, identity="1"):
        return crud.create_experience(["a"], ["b"], ["c"], ["b"], experience_id=identity)

    def seed_native(self):
        record = _record("42")
        self.path.write_text(json.dumps({"experience": {"42": record.to_json_data()}, "reflexes": {}}))
        writer = NFPFeedbackApplyWriter(self.path, policy_for_profile("mutating_memory"))
        evidence = replace(_evidence(record, NFPFeedbackEvaluationStatus.HIT), execution_occurrence_id=OCCURRENCE)
        return writer, evidence

    def assert_refused(self, crud, exception=ExpSMStaleSnapshotError):
        before = self.path.read_bytes()
        local = deepcopy(crud.data)
        baseline = crud._baseline
        with self.assertRaises(exception):
            crud.save()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(crud.data, local, "refusal must not discard caller edits")
        self.assertEqual(crud._baseline, baseline, "refusal must not renew the baseline")

    def donor_migration(self, evidence):
        """Generate valid receipts by real APPLY on a separate temporary store."""
        donor = Path(self.temp.name) / "donor.json"
        donor.write_bytes(self.path.read_bytes())
        writer = NFPFeedbackApplyWriter(donor, policy_for_profile("mutating_memory"))
        self.assertEqual(writer.apply(evidence).status, NFPFeedbackApplyStatus.UPDATED)
        return json.loads(donor.read_text())

    def test_legacy_receipt_import_refused_then_real_apply_is_new(self):
        writer, evidence = self.seed_native()
        a = ExpSMCRUD(self.path)
        original = deepcopy(a.data)
        candidate = self.donor_migration(evidence)
        a.data["store_schema_version"] = 2
        a.data["native_feedback_receipts"] = candidate["native_feedback_receipts"]
        self.assert_refused(a, ExpSMReceiptIntegrityError)
        # Refusal leaves the original baseline usable for normal local edits.
        a.data = original
        a.data["experience"]["42"]["admin_note"] = "reviewed"
        a.save()
        a.save()
        before = json.loads(self.path.read_text())
        self.assertNotIn("store_schema_version", before)
        self.assertEqual(writer.apply(evidence).status, NFPFeedbackApplyStatus.UPDATED)
        after = json.loads(self.path.read_text())
        self.assertEqual(after["store_schema_version"], 2)
        self.assertEqual(after["experience"]["42"]["hits"], before["experience"]["42"]["hits"] + 1)
        self.assertEqual(writer.apply(evidence).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)
        self.assertEqual(writer.apply(replace(evidence, classification=NFPFeedbackEvaluationStatus.MISS)).status,
                         NFPFeedbackApplyStatus.EVENT_CONFLICT)
        with self.assertRaises(ExpSMStaleSnapshotError):
            a.save()
        reopened = ExpSMCRUD(self.path)
        reopened.record_experience_hit("42")
        reopened.save()
        self.assertEqual(writer.apply(evidence).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)

    def test_legacy_empty_v2_migration_refused(self):
        _, evidence = self.seed_native()
        a = ExpSMCRUD(self.path)
        candidate = self.donor_migration(evidence)
        candidate["native_feedback_receipts"]["by_event_key"].clear()
        candidate["native_feedback_receipts"]["execution_occurrence_index"].clear()
        a.data = candidate
        self.assert_refused(a, ExpSMReceiptIntegrityError)

    def test_legacy_unversioned_receipt_field_refused(self):
        _, evidence = self.seed_native()
        a = ExpSMCRUD(self.path)
        a.data["native_feedback_receipts"] = self.donor_migration(evidence)["native_feedback_receipts"]
        self.assert_refused(a, ExpSMReceiptIntegrityError)

    def test_missing_store_cannot_create_receipts(self):
        _, evidence = self.seed_native()
        candidate = self.donor_migration(evidence)
        self.path.unlink()  # Only this test's temporary authoritative store.
        for versioned in (True, False):
            with self.subTest(versioned=versioned):
                self.path.unlink(missing_ok=True)
                a = ExpSMCRUD(self.path)
                a.data = deepcopy(candidate)
                if not versioned:
                    del a.data["store_schema_version"]
                local, baseline = deepcopy(a.data), a._baseline
                with self.assertRaises(ExpSMReceiptIntegrityError):
                    a.save()
                self.assertFalse(self.path.exists())
                self.assertEqual(a.data, local)
                self.assertEqual(a._baseline, baseline)
        fresh = ExpSMCRUD(self.path)
        self.create(fresh)
        self.assertNotIn("store_schema_version", json.loads(self.path.read_text()))

    def test_existing_v2_cannot_import_an_additional_receipt(self):
        writer, evidence = self.seed_native()
        self.assertEqual(writer.apply(evidence).status, NFPFeedbackApplyStatus.UPDATED)
        second = replace(evidence, execution_occurrence_id="66666666-6666-4666-8666-666666666666")
        a = ExpSMCRUD(self.path)
        a.data["native_feedback_receipts"] = self.donor_migration(second)["native_feedback_receipts"]
        self.assert_refused(a, ExpSMReceiptIntegrityError)
        self.assertEqual(writer.apply(second).status, NFPFeedbackApplyStatus.UPDATED)
        self.assertEqual(writer.apply(second).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)

    def test_stale_create_and_different_ids_conflict(self):
        a, b = ExpSMCRUD(self.path), ExpSMCRUD(self.path)
        a.data["experience"]["99"] = {"if": ["a"], "then": ["b"], "result": ["c"], "recommendation": ["b"], "hits": 0, "misses": 0, "confidence": .5, "repeatability": .5}
        self.create(b)
        self.assert_refused(a)
        self.assertIn("1", ExpSMCRUD(self.path).data["experience"])
        self.assertNotIn("99", ExpSMCRUD(self.path).data["experience"])

    def test_stale_update_conflicts(self):
        self.create(ExpSMCRUD(self.path))
        a, b = ExpSMCRUD(self.path), ExpSMCRUD(self.path)
        b.update_experience("1", confidence=.81)
        self.assert_refused(a)
        self.assertEqual(ExpSMCRUD(self.path).read_experience("1")["confidence"], .81)

    def test_stale_delete_cannot_resurrect_tombstone(self):
        self.create(ExpSMCRUD(self.path))
        a, b = ExpSMCRUD(self.path), ExpSMCRUD(self.path)
        b.delete_experience("1")
        self.assert_refused(a)
        self.assertEqual(ExpSMCRUD(self.path).read_experience("1")["status"], "archived")

    def test_fresh_save_and_successive_baseline_refresh(self):
        self.create(ExpSMCRUD(self.path))
        a = ExpSMCRUD(self.path)
        a.data["experience"]["1"]["confidence"] = .61
        a.save()
        a.data["experience"]["1"]["confidence"] = .72
        a.save()
        self.assertEqual(ExpSMCRUD(self.path).read_experience("1")["confidence"], .72)
        self.assertNotIn("store_schema_version", json.loads(self.path.read_text()))

    def test_baseline_independent_of_mutable_data(self):
        self.create(ExpSMCRUD(self.path))
        a, b = ExpSMCRUD(self.path), ExpSMCRUD(self.path)
        b.update_experience("1", confidence=.8)
        # Even replacing local data with the latest content cannot renew its loaded baseline.
        a.data = b.load()
        self.assert_refused(a)

    def test_load_only_does_not_rebase_unsaved_data(self):
        a, b = ExpSMCRUD(self.path), ExpSMCRUD(self.path)
        self.create(b)
        a.load()  # Existing read API returns a snapshot, does not replace/rebase a.data.
        self.assert_refused(a)
        reopened = ExpSMCRUD(self.path)
        reopened.save()
        self.assertIn("1", reopened.data["experience"])

    def test_stale_native_apply_preserves_receipt_and_replay(self):
        writer, evidence = self.seed_native()
        a = ExpSMCRUD(self.path)
        self.assertEqual(writer.apply(evidence).status, NFPFeedbackApplyStatus.UPDATED)
        self.assert_refused(a)
        before = self.path.read_bytes()
        self.assertEqual(writer.apply(evidence).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)
        changed = replace(evidence, classification=NFPFeedbackEvaluationStatus.MISS)
        self.assertEqual(writer.apply(changed).status, NFPFeedbackApplyStatus.EVENT_CONFLICT)
        self.assertEqual(self.path.read_bytes(), before)

    def test_stale_v2_preserves_later_receipt(self):
        writer, evidence = self.seed_native()
        writer.apply(evidence)
        a = ExpSMCRUD(self.path)
        second = replace(evidence, execution_occurrence_id="66666666-6666-4666-8666-666666666666")
        self.assertEqual(writer.apply(second).status, NFPFeedbackApplyStatus.UPDATED)
        self.assert_refused(a)
        self.assertEqual(len(json.loads(self.path.read_text())["native_feedback_receipts"]["by_event_key"]), 2)
        self.assertEqual(writer.apply(second).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)

    def test_fresh_receipt_tampering_refused(self):
        writer, evidence = self.seed_native()
        writer.apply(evidence)
        for variant in ("drop", "empty", "digest", "index", "timestamp", "version_type"):
            with self.subTest(variant=variant):
                a = ExpSMCRUD(self.path)
                ledger = a.data["native_feedback_receipts"]
                if variant == "drop":
                    del a.data["native_feedback_receipts"]
                elif variant == "empty":
                    ledger["by_event_key"].clear()
                    ledger["execution_occurrence_index"].clear()
                elif variant == "index":
                    ledger["execution_occurrence_index"].clear()
                else:
                    receipt = next(iter(ledger["by_event_key"].values()))
                    if variant == "digest":
                        receipt["evidence_digest"] = "0" * 64
                    elif variant == "timestamp":
                        receipt["applied_at_world"] = "2099-01-01T00:00:00Z"
                    else:
                        ledger["identity_version"] = True
                self.assert_refused(a, (ExpSMReceiptIntegrityError, ExpSMStoreInvalidError))

    def test_fresh_v2_save_preserves_ledger_and_extension_metadata(self):
        writer, evidence = self.seed_native()
        writer.apply(evidence)
        store = json.loads(self.path.read_text())
        store["extension"] = {"unknown_allowed": [1, "x"]}
        self.path.write_text(json.dumps(store))
        a = ExpSMCRUD(self.path)
        ledger = deepcopy(a.data["native_feedback_receipts"])
        a.data["experience"]["42"]["admin_note"] = "reviewed"
        a.save()
        after = json.loads(self.path.read_text())
        self.assertEqual(after["native_feedback_receipts"], ledger)
        self.assertEqual(after["extension"], store["extension"])
        self.assertEqual(after["store_schema_version"], 2)
        self.assertEqual(writer.apply(evidence).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)

    def test_fresh_v2_downgrade_refused(self):
        writer, evidence = self.seed_native()
        writer.apply(evidence)
        a = ExpSMCRUD(self.path)
        a.data = {"experience": a.data["experience"], "reflexes": {}}
        self.assert_refused(a, (ExpSMReceiptIntegrityError, ExpSMStoreInvalidError))

    def test_all_decorated_mutations_and_nested_locks(self):
        a, b = ExpSMCRUD(self.path), ExpSMCRUD(self.path)
        with a.transaction.mutation():
            self.create(b)  # a's original snapshot is stale; decorated operation must fresh-load.
            self.create(a, "2")
            a.update_experience("2", confidence=.9)
            a.record_experience_hit("2")
            a.record_experience_miss("2")
            reflex = a.experience_to_reflex("2", reflex_id="3", delete_source=True)
            a.update_reflex(reflex, confidence=.8)
            a.record_reflex_hit(reflex)
            a.record_reflex_miss(reflex)
            a.reflex_to_experience(reflex, experience_id="4", delete_source=True)
            a.create_reflex(["a"], ["b"], ["c"], ["b"], reflex_id="5")
            a.delete_reflex("5")
            a.delete_experience("1")
        c = ExpSMCRUD(self.path)
        self.assertEqual(set(c.data["experience"]), {"1", "2", "4"})
        self.assertEqual(c.read_experience("4")["hits"], 2)
        self.assertEqual(c.read_experience("4")["misses"], 2)
        self.assertEqual(c.read_reflex("5")["status"], "archived")
        a.save()  # successful decorated mutations renew the baseline.

    def test_v2_decorated_mutations_preserve_receipts(self):
        writer, evidence = self.seed_native()
        writer.apply(evidence)
        ledger = deepcopy(json.loads(self.path.read_text())["native_feedback_receipts"])
        a = ExpSMCRUD(self.path)
        self.create(a)
        a.update_experience("1", confidence=.9)
        a.record_experience_hit("1")
        a.record_experience_miss("1")
        a.experience_to_reflex("1", reflex_id="2", delete_source=True)
        a.update_reflex("2", confidence=.8)
        a.record_reflex_hit("2")
        a.record_reflex_miss("2")
        a.reflex_to_experience("2", experience_id="3", delete_source=True)
        a.create_reflex(["a"], ["b"], ["c"], ["b"], reflex_id="4")
        a.delete_reflex("4")
        a.delete_experience("3")
        a.save()
        self.assertEqual(json.loads(self.path.read_text())["native_feedback_receipts"], ledger)
        self.assertEqual(writer.apply(evidence).status, NFPFeedbackApplyStatus.ALREADY_APPLIED)

    def test_concurrent_public_saves_one_conflict_no_lost_success(self):
        barrier = threading.Barrier(2)
        def work(identity):
            a = ExpSMCRUD(self.path)
            a.data["experience"][identity] = {"if": [identity], "then": ["b"], "result": ["c"], "recommendation": ["b"], "hits": 0, "misses": 0, "confidence": .5, "repeatability": .5}
            barrier.wait(timeout=10)
            try:
                a.save()
                return identity, True
            except ExpSMStaleSnapshotError:
                return identity, False
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(work, ("1", "2")))
        accepted = {identity for identity, success in outcomes if success}
        self.assertEqual(len(accepted), 1)
        self.assertEqual(set(ExpSMCRUD(self.path).data["experience"]), accepted)

    def test_concurrent_decorated_updates_preserve_all_confirmed_changes(self):
        self.create(ExpSMCRUD(self.path))
        def work(_):
            a = ExpSMCRUD(self.path)
            for _ in range(8):
                a.record_experience_hit("1")
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(work, range(3)))
        self.assertEqual(ExpSMCRUD(self.path).read_experience("1")["hits"], 24)

    def test_pre_replace_failure_preserves_bytes_and_allows_retry(self):
        self.create(ExpSMCRUD(self.path))
        a = ExpSMCRUD(self.path)
        a.data["experience"]["1"]["confidence"] = .7
        before = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("pre-replace failure")):
            with self.assertRaises(OSError):
                a.save()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))
        a.save()
        self.assertEqual(ExpSMCRUD(self.path).read_experience("1")["confidence"], .7)

    def test_readback_failure_does_not_rebase_or_silently_retry(self):
        a = ExpSMCRUD(self.path)
        a.data["experience"]["1"] = {"if": ["a"], "then": ["b"], "result": ["c"], "recommendation": ["b"], "hits": 0, "misses": 0, "confidence": .5, "repeatability": .5}
        read = a.transaction.load_complete_strict
        calls = 0
        def fail_readback():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("post-replace readback unavailable")
            return read()
        with patch.object(a.transaction, "load_complete_strict", side_effect=fail_readback):
            with self.assertRaises(OSError):
                a.save()
        self.assertIn("1", json.loads(self.path.read_text())["experience"])
        self.assert_refused(a)
        ExpSMCRUD(self.path).save()  # reopen explicitly loads current authority.

    def test_invalid_local_candidate_fails_strict_validation(self):
        for versioned in (False, True):
            with self.subTest(versioned=versioned):
                if versioned:
                    writer, evidence = self.seed_native()
                    writer.apply(evidence)
                a = ExpSMCRUD(self.path)
                a.data = []
                self.assert_refused(a, ExpSMStoreInvalidError)

    def test_invalid_authoritative_store_fails_closed(self):
        a = ExpSMCRUD(self.path)
        self.path.write_text("not JSON")
        self.assert_refused(a, ExpSMStoreInvalidError)


if __name__ == "__main__":
    unittest.main()
