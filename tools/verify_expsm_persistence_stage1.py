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

CRUD_DECORATED_MUTATION_METHODS = {
    "create_experience",
    "update_experience",
    "delete_experience",
    "create_reflex",
    "update_reflex",
    "delete_reflex",
    "experience_to_reflex",
    "reflex_to_experience",
    "record_experience_hit",
    "record_experience_miss",
    "record_reflex_hit",
    "record_reflex_miss",
}

CRUD_READ_ONLY_METHODS = {
    "load",
    "get_all",
    "get_experience",
    "get_reflexes",
    "read_experience",
    "find_experience",
    "read_reflex",
    "find_reflexes",
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
    decorator_helpers_resolved: int
    decorator_wrappers_audited: int
    decorator_boundaries_verified: int
    decorator_fresh_loads_verified: int
    decorator_orderings_verified: int
    crud_mutation_methods_audited: int
    crud_read_only_methods_excluded: int


@dataclass(frozen=True)
class DecoratorAuditResult:
    helpers_resolved: int
    wrappers_audited: int
    boundaries_verified: int
    fresh_loads_verified: int
    orderings_verified: int
    violations: tuple[str, ...]


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


def _is_self_transaction_call(node: ast.Call, method_name: str) -> bool:
    function = node.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr == method_name
        and isinstance(function.value, ast.Attribute)
        and function.value.attr == "transaction"
        and isinstance(function.value.value, ast.Name)
        and function.value.value.id == "self"
    )


def _matching_transaction_with(node: ast.AST) -> ast.With | None:
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.With):
            continue
        for item in candidate.items:
            expression = item.context_expr
            if isinstance(expression, ast.Call) and _is_self_transaction_call(expression, "mutation"):
                return candidate
    return None


def _statement_call_index(statements: list[ast.stmt], predicate: object) -> int | None:
    for index, statement in enumerate(statements):
        for candidate in ast.walk(statement):
            if isinstance(candidate, ast.Call) and predicate(candidate):
                return index
    return None


def _audit_authoritative_mutation_helper(tree: ast.Module) -> DecoratorAuditResult:
    violations: list[str] = []
    helpers = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "authoritative_mutation"
    ]
    if len(helpers) != 1:
        return DecoratorAuditResult(0, 0, 0, 0, 0, ("authoritative_mutation: expected one helper",))
    helper = helpers[0]
    helpers_resolved = 1
    if not helper.args.args:
        return DecoratorAuditResult(1, 0, 0, 0, 0, ("authoritative_mutation: missing method parameter",))
    original_name = helper.args.args[0].arg
    wrappers = [
        node for node in helper.body
        if isinstance(node, ast.FunctionDef) and node.name == "wrapped"
    ]
    if len(wrappers) != 1:
        return DecoratorAuditResult(1, 0, 0, 0, 0, ("authoritative_mutation: expected one wrapped function",))
    wrapper = wrappers[0]
    wrappers_audited = 1
    boundary = _matching_transaction_with(wrapper)
    if boundary is None:
        return DecoratorAuditResult(1, 1, 0, 0, 0, ("authoritative_mutation.wrapped: missing transaction boundary",))
    boundaries_verified = 1

    boundary_index = next(
        index for index, statement in enumerate(wrapper.body)
        if boundary is statement or boundary in tuple(ast.walk(statement))
    )
    before_boundary = wrapper.body[:boundary_index]
    if _statement_call_index(
        before_boundary,
        lambda call: _is_self_transaction_call(call, "load_for_mutation_strict"),
    ) is not None:
        violations.append("authoritative_mutation.wrapped: fresh load occurs before transaction")
    if _statement_call_index(
        before_boundary,
        lambda call: isinstance(call.func, ast.Name) and call.func.id == original_name,
    ) is not None:
        violations.append("authoritative_mutation.wrapped: original method called before transaction")

    fresh_index: int | None = None
    for index, statement in enumerate(boundary.body):
        for candidate in ast.walk(statement):
            if not isinstance(candidate, (ast.Assign, ast.AnnAssign)):
                continue
            value = candidate.value
            targets = candidate.targets if isinstance(candidate, ast.Assign) else [candidate.target]
            if not isinstance(value, ast.Call) or not _is_self_transaction_call(value, "load_for_mutation_strict"):
                continue
            if any(
                isinstance(target, ast.Attribute)
                and target.attr == "data"
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                for target in targets
            ):
                fresh_index = index
                break
        if fresh_index is not None:
            break
    fresh_loads_verified = 1 if fresh_index is not None else 0
    if fresh_index is None:
        violations.append("authoritative_mutation.wrapped: fresh load is not assigned to self.data inside transaction")

    original_index = _statement_call_index(
        boundary.body,
        lambda call: isinstance(call.func, ast.Name) and call.func.id == original_name,
    )
    if original_index is None:
        violations.append("authoritative_mutation.wrapped: original method is not called inside transaction")
    orderings_verified = 0
    if fresh_index is not None and original_index is not None:
        if fresh_index < original_index:
            orderings_verified = 1
        else:
            violations.append("authoritative_mutation.wrapped: original method is called before fresh load")

    returned_wrapped = any(
        isinstance(statement, ast.Return)
        and isinstance(statement.value, ast.Name)
        and statement.value.id == wrapper.name
        for statement in helper.body
    )
    if not returned_wrapped:
        violations.append("authoritative_mutation: audited wrapper is not returned")
    return DecoratorAuditResult(
        helpers_resolved,
        wrappers_audited,
        boundaries_verified,
        fresh_loads_verified,
        orderings_verified,
        tuple(violations),
    )


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
    decorator_helpers_resolved = 0
    decorator_wrappers_audited = 0
    decorator_boundaries_verified = 0
    decorator_fresh_loads_verified = 0
    decorator_orderings_verified = 0
    crud_mutation_methods_audited = 0
    crud_read_only_methods_excluded = 0

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
        decorator_boundary = False
        if class_name == "ExpSMCRUD":
            decorator_audit = _audit_authoritative_mutation_helper(tree)
            decorator_helpers_resolved += decorator_audit.helpers_resolved
            decorator_wrappers_audited += decorator_audit.wrappers_audited
            decorator_boundaries_verified += decorator_audit.boundaries_verified
            decorator_fresh_loads_verified += decorator_audit.fresh_loads_verified
            decorator_orderings_verified += decorator_audit.orderings_verified
            transaction_violations.extend(decorator_audit.violations)
            for name in CRUD_DECORATED_MUTATION_METHODS:
                method = methods.get(name)
                if not isinstance(method, ast.FunctionDef):
                    transaction_violations.append(f"ExpSMCRUD.{name}: missing mutation method")
                    continue
                if _decorator_names(method) != {"authoritative_mutation"}:
                    transaction_violations.append(f"ExpSMCRUD.{name}: exact decorator missing")
                    continue
                crud_mutation_methods_audited += 1
            save = methods.get("save")
            if not isinstance(save, ast.FunctionDef) or _mutation_with_index(save) is None:
                transaction_violations.append("ExpSMCRUD.save: direct transaction boundary missing")
            else:
                crud_mutation_methods_audited += 1
            for name in CRUD_READ_ONLY_METHODS:
                method = methods.get(name)
                if not isinstance(method, ast.FunctionDef):
                    transaction_violations.append(f"ExpSMCRUD.{name}: missing read-only method")
                    continue
                if "authoritative_mutation" in _decorator_names(method) or _mutation_with_index(method) is not None:
                    transaction_violations.append(f"ExpSMCRUD.{name}: read-only method enters mutation boundary")
                    continue
                crud_read_only_methods_excluded += 1
            decorator_boundary = (
                not decorator_audit.violations
                and crud_mutation_methods_audited == len(CRUD_DECORATED_MUTATION_METHODS) + 1
            )
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
        decorator_helpers_resolved=decorator_helpers_resolved,
        decorator_wrappers_audited=decorator_wrappers_audited,
        decorator_boundaries_verified=decorator_boundaries_verified,
        decorator_fresh_loads_verified=decorator_fresh_loads_verified,
        decorator_orderings_verified=decorator_orderings_verified,
        crud_mutation_methods_audited=crud_mutation_methods_audited,
        crud_read_only_methods_excluded=crud_read_only_methods_excluded,
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

    def test_crud_decorator_ast_rejects_broken_helper_ordering(self) -> None:
        snippets = {
            "no_transaction": """
def authoritative_mutation(method):
    def wrapped(self, *args, **kwargs):
        return method(self, *args, **kwargs)
    return wrapped
""",
            "no_fresh_load": """
def authoritative_mutation(method):
    def wrapped(self, *args, **kwargs):
        with self.transaction.mutation():
            return method(self, *args, **kwargs)
    return wrapped
""",
            "fresh_before_transaction": """
def authoritative_mutation(method):
    def wrapped(self, *args, **kwargs):
        self.data = self.transaction.load_for_mutation_strict()
        with self.transaction.mutation():
            return method(self, *args, **kwargs)
    return wrapped
""",
            "method_before_fresh": """
def authoritative_mutation(method):
    def wrapped(self, *args, **kwargs):
        with self.transaction.mutation():
            result = method(self, *args, **kwargs)
            self.data = self.transaction.load_for_mutation_strict()
            return result
    return wrapped
""",
        }
        for name, source in snippets.items():
            with self.subTest(name=name):
                audit = _audit_authoritative_mutation_helper(ast.parse(source))
                self.assertTrue(audit.violations)

        correct = ast.parse(
            """
def authoritative_mutation(method):
    def wrapped(self, *args, **kwargs):
        with self.transaction.mutation():
            self.data = self.transaction.load_for_mutation_strict()
            return method(self, *args, **kwargs)
    return wrapped
"""
        )
        audit = _audit_authoritative_mutation_helper(correct)
        self.assertEqual(audit.violations, ())
        self.assertEqual(audit.helpers_resolved, 1)
        self.assertEqual(audit.wrappers_audited, 1)
        self.assertEqual(audit.boundaries_verified, 1)
        self.assertEqual(audit.fresh_loads_verified, 1)
        self.assertEqual(audit.orderings_verified, 1)

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
        self.assertEqual(audit.decorator_helpers_resolved, 1)
        self.assertEqual(audit.decorator_wrappers_audited, 1)
        self.assertEqual(audit.decorator_boundaries_verified, 1)
        self.assertEqual(audit.decorator_fresh_loads_verified, 1)
        self.assertEqual(audit.decorator_orderings_verified, 1)
        self.assertEqual(
            audit.crud_mutation_methods_audited,
            len(CRUD_DECORATED_MUTATION_METHODS) + 1,
        )
        self.assertEqual(audit.crud_read_only_methods_excluded, len(CRUD_READ_ONLY_METHODS))
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
        f"store_order_violations={len(audit.store_order_violations)} "
        f"decorator_helpers_resolved={audit.decorator_helpers_resolved} "
        f"decorator_wrappers_audited={audit.decorator_wrappers_audited} "
        f"decorator_boundaries_verified={audit.decorator_boundaries_verified} "
        f"decorator_fresh_loads_verified={audit.decorator_fresh_loads_verified} "
        f"decorator_orderings_verified={audit.decorator_orderings_verified} "
        f"crud_mutation_methods_audited={audit.crud_mutation_methods_audited} "
        f"crud_read_only_methods_excluded={audit.crud_read_only_methods_excluded}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
