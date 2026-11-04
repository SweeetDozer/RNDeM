from __future__ import annotations

import ast
import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
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
from clc.consolidation.expsm_commit_writer import ExpSMCommitWriter
from clc.consolidation.expsm_update_writer import ExpSMUpdateWriter
from clc.evaluation.value_feedback_update_writer import ValueFeedbackUpdateWriter
from clc.expsm.expsm_outcome_feedback import ExpSMOutcomeFeedback


WRITERS = {
    "NFPExpSMCreateWriter": "clc/experience/expsm_native_create.py",
    "NFPFeedbackApplyWriter": "clc/expsm/nfp_native_feedback_apply.py",
    "ExpSMCommitWriter": "clc/consolidation/expsm_commit_writer.py",
    "ExpSMUpdateWriter": "clc/consolidation/expsm_update_writer.py",
    "ValueFeedbackUpdateWriter": "clc/evaluation/value_feedback_update_writer.py",
    "ExpSMOutcomeFeedback": "clc/expsm/expsm_outcome_feedback.py",
    "ExpSMCRUD": "Memory/ExpSM/Exp_CRUD.py",
}

WRITER_MUTATION_METHODS = {
    "NFPExpSMCreateWriter": "create",
    "NFPFeedbackApplyWriter": "apply",
    "ExpSMCommitWriter": "run",
    "ExpSMUpdateWriter": "run",
    "ValueFeedbackUpdateWriter": "run",
    "ExpSMOutcomeFeedback": "run",
    "ExpSMCRUD": "create_experience",
}

PREFLIGHT_WRITERS = {
    "ExpSMCommitWriter",
    "ExpSMUpdateWriter",
    "ValueFeedbackUpdateWriter",
    "ExpSMOutcomeFeedback",
}

APPROVED_DRAFT_WRITE_HELPERS = {
    ("ExpSMCommitWriter", "_atomic_write_json"),
    ("ExpSMUpdateWriter", "_atomic_write_json"),
}

AUTHORITATIVE_ACCESS_CALLS = {
    "load_for_mutation_strict",
    "load_state_strict",
    "_load_expsm_store",
    "_load_data",
    "write_complete_store",
}


@dataclass(frozen=True)
class ASTAuditResult:
    writer_definitions: int
    mutation_paths: int
    direct_write_violations: tuple[str, ...]
    transaction_violations: tuple[str, ...]
    preflight_violations: tuple[str, ...]
    store_order_violations: tuple[str, ...]


def _call_name(node: ast.Call) -> str | None:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _contains_call(node: ast.AST, names: set[str]) -> bool:
    return any(
        isinstance(candidate, ast.Call) and _call_name(candidate) in names
        for candidate in ast.walk(node)
    )


def _mutation_with_index(method: ast.FunctionDef) -> int | None:
    for index, statement in enumerate(method.body):
        for candidate in ast.walk(statement):
            if not isinstance(candidate, (ast.With, ast.AsyncWith)):
                continue
            if any(_contains_call(item.context_expr, {"mutation"}) for item in candidate.items):
                return index
    return None


def _decorator_names(method: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in method.decorator_list:
        if isinstance(decorator, ast.Name):
            names.add(decorator.id)
        elif isinstance(decorator, ast.Attribute):
            names.add(decorator.attr)
    return names


def _low_level_write_calls(method: ast.FunctionDef) -> list[str]:
    calls: list[str] = []
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in {"replace", "rename"} and len(node.args) == 1:
            calls.append(name)
        elif name in {"write_text", "write_bytes"}:
            calls.append(name)
        elif name == "open" and node.args:
            mode_index = 0 if isinstance(node.func, ast.Attribute) else 1
            mode = node.args[mode_index] if len(node.args) > mode_index else None
            if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                if "w" in mode.value or "a" in mode.value:
                    calls.append("open_write")
        elif name == "open":
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    value = keyword.value.value
                    if isinstance(value, str) and ("w" in value or "a" in value):
                        calls.append("open_write")
    return calls


def _audit_writer_ast() -> ASTAuditResult:
    definitions = 0
    mutation_paths = 0
    direct_write_violations: list[str] = []
    transaction_violations: list[str] = []
    preflight_violations: list[str] = []
    store_order_violations: list[str] = []

    for class_name, relative in WRITERS.items():
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
        classes = [
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ]
        if len(classes) != 1:
            transaction_violations.append(f"{class_name}: expected one class definition")
            continue
        definitions += 1
        class_node = classes[0]
        methods = {
            node.name: node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        mutation_name = WRITER_MUTATION_METHODS[class_name]
        mutation_method = methods.get(mutation_name)
        if not isinstance(mutation_method, ast.FunctionDef):
            transaction_violations.append(f"{class_name}.{mutation_name}: missing method")
            continue

        boundary_index = _mutation_with_index(mutation_method)
        decorator_boundary = "authoritative_mutation" in _decorator_names(mutation_method)
        if boundary_index is None and not decorator_boundary:
            transaction_violations.append(f"{class_name}.{mutation_name}: no transaction boundary")
        else:
            mutation_paths += 1

        if class_name in PREFLIGHT_WRITERS:
            if boundary_index is None or boundary_index == 0:
                preflight_violations.append(f"{class_name}.{mutation_name}: no early preflight")
            else:
                preflight = mutation_method.body[:boundary_index]
                if not any(isinstance(statement, ast.If) for statement in preflight):
                    preflight_violations.append(f"{class_name}.{mutation_name}: preflight lacks early if")
                for statement in preflight:
                    if _contains_call(statement, AUTHORITATIVE_ACCESS_CALLS):
                        store_order_violations.append(
                            f"{class_name}.{mutation_name}: authoritative access before transaction"
                        )

        for method_name, method in methods.items():
            low_level = _low_level_write_calls(method)
            if not low_level:
                continue
            if (class_name, method_name) not in APPROVED_DRAFT_WRITE_HELPERS:
                direct_write_violations.append(
                    f"{class_name}.{method_name}: {','.join(sorted(low_level))}"
                )
                continue
            if not _contains_call(method, {"write_complete_store"}):
                direct_write_violations.append(
                    f"{class_name}.{method_name}: draft helper lacks authoritative delegation"
                )

    return ASTAuditResult(
        writer_definitions=definitions,
        mutation_paths=mutation_paths,
        direct_write_violations=tuple(direct_write_violations),
        transaction_violations=tuple(transaction_violations),
        preflight_violations=tuple(preflight_violations),
        store_order_violations=tuple(store_order_violations),
    )


class _ForbiddenTransaction:
    def __init__(self) -> None:
        self.entries = 0

    def mutation(self) -> object:
        self.entries += 1
        raise AssertionError("denied/no-work call entered ExpSM transaction")


class _NoValueReviews:
    def get_recent_value_feedback_reviews(self, limit: int) -> list[dict[str, object]]:
        del limit
        return []


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
            before = self.path.read_bytes()
            with self.assertRaises(ExpSMStoreInvalidError):
                transaction.load_state_strict()
            with transaction.mutation():
                with self.assertRaises(ExpSMStoreInvalidError):
                    transaction.load_for_mutation_strict()
            self.assertEqual(self.path.read_bytes(), before)

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

    def test_denied_and_no_work_writers_do_not_enter_transaction(self) -> None:
        production_store = ROOT / "Memory/ExpSM/ExpSM_data.json"
        production_lock = ROOT / "Memory/ExpSM/ExpSM_data.lock"
        self.assertFalse(production_lock.exists())
        before = production_store.read_bytes()

        commit = object.__new__(ExpSMCommitWriter)
        commit_transaction = _ForbiddenTransaction()
        commit.transaction = commit_transaction
        commit.memory_mutation_policy = SimpleNamespace(allow_expsm_commit=False)
        commit._has_recent_commit_decision = lambda tick, memory: True
        commit._policy_blocked_update = lambda *args: "commit_denied"
        self.assertEqual(
            commit.run(1, object(), object(), SimpleNamespace(mode="consolidation")),
            ["commit_denied"],
        )
        self.assertEqual(commit_transaction.entries, 0)

        update = object.__new__(ExpSMUpdateWriter)
        update_transaction = _ForbiddenTransaction()
        update.transaction = update_transaction
        update.memory_mutation_policy = SimpleNamespace(allow_expsm_update=False)
        update._has_recent_update_decision = lambda tick, memory: True
        update._policy_blocked_update = lambda *args: "update_denied"
        self.assertEqual(
            update.run(1, object(), object(), SimpleNamespace(mode="consolidation")),
            ["update_denied"],
        )
        self.assertEqual(update_transaction.entries, 0)

        value = object.__new__(ValueFeedbackUpdateWriter)
        value_transaction = _ForbiddenTransaction()
        value.transaction = value_transaction
        value.memory_mutation_policy = SimpleNamespace(allow_value_feedback_update=True)
        self.assertEqual(
            value.run(1, _NoValueReviews(), SimpleNamespace(mode="consolidation")),
            [],
        )
        self.assertEqual(value_transaction.entries, 0)

        outcome = object.__new__(ExpSMOutcomeFeedback)
        outcome_transaction = _ForbiddenTransaction()
        outcome.transaction = outcome_transaction
        outcome._has_feedback_work = lambda tick, memory: False
        self.assertEqual(
            outcome.run(1, object(), object(), SimpleNamespace(mode="active")),
            [],
        )
        self.assertEqual(outcome_transaction.entries, 0)

        self.assertEqual(production_store.read_bytes(), before)
        self.assertFalse(production_lock.exists())

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
        audit = _audit_writer_ast()
        self.assertEqual(audit.writer_definitions, len(WRITERS))
        self.assertEqual(audit.mutation_paths, len(WRITERS))
        self.assertEqual(audit.direct_write_violations, ())
        self.assertEqual(audit.transaction_violations, ())
        self.assertEqual(audit.preflight_violations, ())
        self.assertEqual(audit.store_order_violations, ())
        for class_name, relative in WRITERS.items():
            source = (ROOT / relative).read_text(encoding="utf-8")
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
    audit = _audit_writer_ast()
    print("PASS: ExpSM persistence Stage 1 dual-format and shared locking")
    print(f"writers={len(WRITERS)} stage2_enabled=false runtime_wiring=false")
    print(
        "ast_audit "
        f"writer_definitions={audit.writer_definitions} "
        f"mutation_paths={audit.mutation_paths} "
        f"direct_write_violations={len(audit.direct_write_violations)} "
        f"transaction_violations={len(audit.transaction_violations)} "
        f"preflight_violations={len(audit.preflight_violations)} "
        f"store_order_violations={len(audit.store_order_violations)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
