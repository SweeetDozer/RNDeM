from __future__ import annotations

import ast
import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.consolidation.expsm_store_transaction import (
    ExpSMEnvelopeV2WriteDisabledError,
    ExpSMStoreFormat,
    ExpSMStoreInvalidError,
    ExpSMStoreTransaction,
)


WRITERS = {
    "NFPExpSMCreateWriter": "clc/experience/expsm_native_create.py",
    "NFPFeedbackApplyWriter": "clc/expsm/nfp_native_feedback_apply.py",
    "ExpSMCommitWriter": "clc/consolidation/expsm_commit_writer.py",
    "ExpSMUpdateWriter": "clc/consolidation/expsm_update_writer.py",
    "ValueFeedbackUpdateWriter": "clc/evaluation/value_feedback_update_writer.py",
    "ExpSMOutcomeFeedback": "clc/expsm/expsm_outcome_feedback.py",
    "ExpSMCRUD": "Memory/ExpSM/Exp_CRUD.py",
}


def _legacy(records: dict[str, dict[str, object]] | None = None) -> dict[str, object]:
    normalized: dict[str, dict[str, object]] = {}
    for record_id, overrides in (records or {}).items():
        record: dict[str, object] = {
            "level": 2,
            "if": ["pat_0001"],
            "then": ["pat_0002"],
            "result": ["pat_0003"],
            "recommendation": ["pat_0002"],
            "confidence": 0.5,
            "repeatability": 0.5,
            "source": 7,
            "status": 2,
            "hits": 0,
            "misses": 0,
        }
        record.update(overrides)
        normalized[record_id] = record
    return {"experience": normalized, "reflexes": {}}


def _worker(path: str, record_id: str, field: str, start: object, result: object) -> None:
    transaction = ExpSMStoreTransaction(path)
    try:
        start.wait()
        with transaction.mutation():
            store = transaction.load_for_mutation_strict()
            record = dict(store["experience"][record_id])
            time.sleep(0.08)
            record[field] = int(record.get(field, 0)) + 1
            store["experience"] = dict(store["experience"])
            store["experience"][record_id] = record
            transaction.write_complete_store(store)
            transaction.load_strict()
        result.put(None)
    except Exception as exc:  # pragma: no cover - returned to parent process
        result.put(repr(exc))


class ExpSMStage1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ExpSM_data.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, data: dict[str, object]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _mutate(self, field: str = "hits") -> None:
        transaction = ExpSMStoreTransaction(self.path)
        with transaction.mutation():
            store = transaction.load_for_mutation_strict()
            record = dict(store["experience"]["42"])
            record[field] = int(record.get(field, 0)) + 1
            store["experience"] = dict(store["experience"])
            store["experience"]["42"] = record
            transaction.write_complete_store(store)
            transaction.load_strict()

    def test_dual_format_read_and_unknown_versions_fail_closed(self) -> None:
        legacy = _legacy({"42": {"hits": 1}})
        self._write(legacy)
        transaction = ExpSMStoreTransaction(self.path)
        state = transaction.load_state_strict()
        self.assertEqual(state.format_kind, ExpSMStoreFormat.LEGACY_UNVERSIONED)
        self.assertEqual(state.legacy_facade(), legacy)

        receipts = {"opaque": {"digest": "not-interpreted"}}
        envelope = {"store_schema_version": 2, **legacy, "native_feedback_receipts": receipts}
        self._write(envelope)
        state = transaction.load_state_strict()
        self.assertEqual(state.format_kind, ExpSMStoreFormat.ENVELOPE_V2)
        self.assertEqual(state.native_feedback_receipts, receipts)
        self.assertEqual(state.experience, legacy["experience"])

        for invalid in (
            {"store_schema_version": 3, **legacy, "native_feedback_receipts": {}},
            {"store_schema_version": 2, **legacy},
            {"store_schema_version": 2, **legacy, "native_feedback_receipts": []},
        ):
            self._write(invalid)
            with self.assertRaises(ExpSMStoreInvalidError):
                transaction.load_state_strict()

    def test_legacy_write_stays_legacy_and_v2_write_is_denied(self) -> None:
        self._write(_legacy({"42": {"hits": 0}}))
        self._mutate()
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["experience"]["42"]["hits"], 1)
        self.assertNotIn("store_schema_version", written)
        self.assertNotIn("native_feedback_receipts", written)

        envelope = {
            "store_schema_version": 2,
            **_legacy({"42": {"hits": 1}}),
            "native_feedback_receipts": {"opaque": {"keep": True}},
        }
        self._write(envelope)
        before = self.path.read_bytes()
        transaction = ExpSMStoreTransaction(self.path)
        with transaction.mutation():
            with self.assertRaises(ExpSMEnvelopeV2WriteDisabledError):
                transaction.load_for_mutation_strict()
        self.assertEqual(self.path.read_bytes(), before)

    def test_reentrant_lock_and_stable_sibling_inode(self) -> None:
        self._write(_legacy({"42": {"hits": 0}}))
        first = ExpSMStoreTransaction(self.path)
        second = ExpSMStoreTransaction(self.path)
        with first.mutation():
            store = first.load_strict()
            with second.mutation():
                nested = second.load_strict()
                self.assertEqual(nested, store)
        self._mutate()
        inode = first.lock_path.stat().st_ino
        self._mutate("misses")
        self.assertTrue(first.lock_path.exists())
        self.assertEqual(first.lock_path.stat().st_ino, inode)
        self.assertNotEqual(first.lock_path.resolve(), self.path.resolve())

    def test_lock_open_and_flock_fail_closed(self) -> None:
        self._write(_legacy({"42": {"hits": 0}}))
        before = self.path.read_bytes()
        transaction = ExpSMStoreTransaction(self.path)
        real_open = os.open

        def fail_lock_open(path: object, flags: int, mode: int = 0o777) -> int:
            if Path(path) == transaction.lock_path:
                raise OSError("injected lock open failure")
            return real_open(path, flags, mode)

        with patch("clc.consolidation.expsm_store_transaction.os.open", fail_lock_open):
            with self.assertRaises(OSError):
                with transaction.mutation():
                    pass
        self.assertEqual(self.path.read_bytes(), before)

        with patch("clc.consolidation.expsm_store_transaction.fcntl.flock", side_effect=OSError("injected flock failure")):
            with self.assertRaises(OSError):
                with transaction.mutation():
                    pass
        self.assertEqual(self.path.read_bytes(), before)

    def test_spawned_processes_preserve_same_and_different_record_updates(self) -> None:
        context = multiprocessing.get_context("spawn")
        for records, jobs, expected in (
            (
                {"42": {"hits": 0, "misses": 0}},
                (("42", "hits"), ("42", "misses")),
                {"42": {"hits": 1, "misses": 1}},
            ),
            (
                {"42": {"hits": 0}, "43": {"hits": 0}},
                (("42", "hits"), ("43", "hits")),
                {"42": {"hits": 1}, "43": {"hits": 1}},
            ),
        ):
            self._write(_legacy(records))
            start = context.Event()
            result = context.Queue()
            processes = [
                context.Process(target=_worker, args=(str(self.path), record_id, field, start, result))
                for record_id, field in jobs
            ]
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                process.join(10)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual([result.get(timeout=2) for _ in processes], [None, None])
            final = json.loads(self.path.read_text(encoding="utf-8"))["experience"]
            for record_id, fields in expected.items():
                for field, value in fields.items():
                    self.assertEqual(final[record_id][field], value)

    def test_writer_inventory_and_no_stage2_or_runtime_leakage(self) -> None:
        for class_name, relative in WRITERS.items():
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(f"class {class_name}", source)
            self.assertIn("ExpSMStoreTransaction", source)
            self.assertIn(".mutation()", source)
            self.assertNotIn("execution_occurrence_id", source)
            self.assertNotIn("ALREADY_APPLIED", source)
            self.assertNotIn("EVENT_CONFLICT", source)
        transaction_source = (ROOT / "clc/consolidation/expsm_store_transaction.py").read_text(encoding="utf-8")
        self.assertIn("fcntl.flock(descriptor, fcntl.LOCK_EX)", transaction_source)
        self.assertIn("ENVELOPE_V2_WRITE_NOT_ENABLED", transaction_source)
        runtime = (ROOT / "clc/runtime/clc_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("NFPFeedbackApplyWriter", runtime)

        scenario = json.loads((ROOT / "scenarios/expsm_persistence_stage1.json").read_text(encoding="utf-8"))
        self.assertTrue(scenario["expect"]["expsm_persistence_stage1"]["no_lost_update"])


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExpSMStage1Tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    print("PASS: ExpSM persistence Stage 1 dual-format and shared locking")
    print(f"writers={len(WRITERS)} stage2_enabled=false runtime_wiring=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
