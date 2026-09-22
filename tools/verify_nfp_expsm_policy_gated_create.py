from __future__ import annotations

import ast
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.experience.expsm_native_create import (
    ExpSMAuthorityState,
    ExpSMCreateStatus,
    ExpSMRecoveryStatus,
    NFPExpSMCreateWriter,
    reconcile_expsm_readback_failure,
)
from clc.experience.expsm_representation import (
    ExpSMOperationalMetadataV1,
    ExpSMRecordAdapter,
    ExpSMRecordCreationRequest,
    NFPExpSMCreationMetadataV1,
    NFPNativeOperationalRecordV1,
    SerializedNFPActionV1,
    SerializedNFPContextV1,
    SerializedObservedEffectV1,
)
from clc.runtime.memory_mutation_policy import RuntimeProfile, policy_for_profile


PRODUCTION_FILES = (
    ROOT / "Memory" / "ExpSM" / "ExpSM_data.json",
    ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json",
)
EXPECTED_HASHES = (
    "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
)
SOURCE = ROOT / "clc" / "experience" / "expsm_native_create.py"


def _hashes() -> tuple[str, ...]:
    return tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in PRODUCTION_FILES)


def _request(request_id: str = "request:native-create") -> ExpSMRecordCreationRequest:
    return ExpSMRecordCreationRequest(
        request_id=request_id,
        context=SerializedNFPContextV1("visual", (3,), ((0.1, 0.5, 0.9), (0.8, 0.5, 0.4))),
        action=SerializedNFPActionV1("action", (2,), (0.0, 1.0)),
        effect=SerializedObservedEffectV1("visual", (3,), (-0.75, 0.0, 0.5)),
        requested_operational=ExpSMOperationalMetadataV1(),
        creation_metadata=NFPExpSMCreationMetadataV1(3, "proposal:native-create", 12),
    )


def _legacy(record_id: str) -> dict[str, object]:
    return {
        "if": [f"condition:{record_id}"], "then": [f"action:{record_id}"],
        "result": [f"result:{record_id}"], "recommendation": [f"recommendation:{record_id}"],
        "hits": 2, "misses": 1, "confidence": 0.7, "repeatability": 0.6,
        "status": 2,
    }


def _store(ids: tuple[str, ...] = ("1", "2", "7")) -> dict[str, object]:
    return {"experience": {record_id: _legacy(record_id) for record_id in ids}, "reflexes": {}}


class _UnsupportedRequest:
    record_kind = "nfp_native"
    representation_version = 999


class _MalformedRequest:
    record_kind = "nfp_native"
    representation_version = 1


class PolicyGatedNativeCreateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before_hashes = _hashes()
        if cls.before_hashes != EXPECTED_HASHES:
            raise AssertionError(f"unexpected production hashes: {cls.before_hashes}")

    @classmethod
    def tearDownClass(cls) -> None:
        if _hashes() != cls.before_hashes:
            raise AssertionError("native CREATE verifier mutated production Memory")

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ExpSM_data.json"
        self.path.write_text(json.dumps(_store(), indent=2) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _writer(self, profile: RuntimeProfile, hook=None) -> NFPExpSMCreateWriter:
        policy = policy_for_profile(profile, memory_root=self.path.parent, memory_is_temporary=True)
        return NFPExpSMCreateWriter(self.path, policy, failure_hook=hook)

    def test_policy_denials_validate_but_do_not_allocate_or_write(self) -> None:
        for profile in (RuntimeProfile.SAFE_DEMO, RuntimeProfile.DRAFT_ONLY):
            with self.subTest(profile=profile):
                before = self.path.read_bytes()
                result = self._writer(profile).create(_request())
                self.assertEqual(result.status, ExpSMCreateStatus.DENIED_BY_POLICY)
                self.assertIsNone(result.record_id)
                self.assertIsNone(result.attempted_record_id)
                self.assertEqual(self.path.read_bytes(), before)

    def test_authoritative_create_gap_legacy_preservation_and_fresh_parse(self) -> None:
        before = json.loads(self.path.read_text(encoding="utf-8"))["experience"]
        result = self._writer(RuntimeProfile.MUTATING_MEMORY).create(_request())
        self.assertEqual(result.status, ExpSMCreateStatus.CREATED)
        self.assertEqual(result.record_id, "8")
        self.assertEqual(result.record, _request().materialize_for_validation("8"))
        self.assertEqual(result.authority_state, ExpSMAuthorityState.CONFIRMED)
        after = json.loads(self.path.read_text(encoding="utf-8"))["experience"]
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertEqual(len(after), len(before) + 1)
        parsed = ExpSMRecordAdapter.parse("8", after["8"])
        self.assertIsInstance(parsed, NFPNativeOperationalRecordV1)
        self.assertEqual(parsed.record.creation_metadata.source_support_count, 3)
        self.assertEqual(parsed.record.operational, ExpSMOperationalMetadataV1())

    def test_same_request_twice_creates_distinct_records(self) -> None:
        writer = self._writer(RuntimeProfile.MUTATING_MEMORY)
        request = _request()
        first = writer.create(request)
        second = writer.create(request)
        self.assertEqual((first.record_id, second.record_id), ("8", "9"))
        self.assertEqual((first.status, second.status), (ExpSMCreateStatus.CREATED,) * 2)
        self.assertEqual(len(json.loads(self.path.read_text())["experience"]), 5)

    def test_invalid_unsupported_and_invalid_store_do_not_write(self) -> None:
        writer = self._writer(RuntimeProfile.MUTATING_MEMORY)
        before = self.path.read_bytes()
        self.assertEqual(writer.create(_UnsupportedRequest()).status, ExpSMCreateStatus.UNSUPPORTED_REPRESENTATION)
        self.assertEqual(writer.create(_MalformedRequest()).status, ExpSMCreateStatus.INVALID_REQUEST)
        self.assertEqual(self.path.read_bytes(), before)
        self.path.write_text('{"experience": [], "reflexes": {}}\n', encoding="utf-8")
        malformed = self.path.read_bytes()
        self.assertEqual(writer.create(_request()).status, ExpSMCreateStatus.STORE_INVALID)
        self.assertEqual(self.path.read_bytes(), malformed)

    def test_pre_replace_failure_preserves_exact_old_bytes_and_cleans_temp(self) -> None:
        before = self.path.read_bytes()
        observed_temp_names: list[str] = []

        def fail(stage: str) -> None:
            if stage == "pre_replace":
                siblings = list(self.path.parent.glob(f".{self.path.name}.*.tmp"))
                self.assertEqual(len(siblings), 1)
                self.assertNotEqual(siblings[0], self.path.with_name(self.path.name + ".tmp"))
                observed_temp_names.append(siblings[0].name)
                raise OSError("injected pre-replace failure")

        result = self._writer(RuntimeProfile.MUTATING_MEMORY, fail).create(_request())
        self.assertEqual(result.status, ExpSMCreateStatus.WRITE_FAILED)
        self.assertIsNone(result.record_id)
        self.assertIsNone(result.attempted_record_id)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(observed_temp_names), 1)
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*.tmp")), [])

    def test_post_replace_failure_and_read_only_recovery(self) -> None:
        def fail(stage: str) -> None:
            if stage == "post_replace_readback":
                raise OSError("injected readback failure")

        request = _request()
        result = self._writer(RuntimeProfile.MUTATING_MEMORY, fail).create(request)
        self.assertEqual(result.status, ExpSMCreateStatus.READBACK_FAILED)
        self.assertEqual(result.authority_state, ExpSMAuthorityState.INDETERMINATE_FROM_CALLER_PERSPECTIVE)
        self.assertEqual(result.attempted_record_id, "8")
        self.assertIsNone(result.record_id)
        self.assertIsNone(result.record)
        self.assertFalse(result.retry_safe)
        before_recovery = self.path.read_bytes()
        recovered = reconcile_expsm_readback_failure(self.path, "8", request)
        self.assertEqual(recovered.status, ExpSMRecoveryStatus.CONFIRMED_PERSISTED)
        self.assertEqual(recovered.record, request.materialize_for_validation("8"))
        self.assertEqual(self.path.read_bytes(), before_recovery)
        self.assertEqual(len(json.loads(self.path.read_text())["experience"]), 4)

    def test_absent_and_unresolved_recovery_do_not_write(self) -> None:
        request = _request()
        before = self.path.read_bytes()
        absent = reconcile_expsm_readback_failure(self.path, "8", request)
        self.assertEqual(absent.status, ExpSMRecoveryStatus.CONFIRMED_ABSENT)
        self.assertEqual(self.path.read_bytes(), before)
        conflicting = _store()
        conflicting["experience"]["8"] = _legacy("8")
        self.path.write_text(json.dumps(conflicting), encoding="utf-8")
        conflict_bytes = self.path.read_bytes()
        unresolved = reconcile_expsm_readback_failure(self.path, "8", request)
        self.assertEqual(unresolved.status, ExpSMRecoveryStatus.UNRESOLVED_OR_STORE_INVALID)
        self.assertEqual(self.path.read_bytes(), conflict_bytes)

    def test_source_is_isolated_and_recovery_has_no_create_call(self) -> None:
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        forbidden = {
            "SimilarityObserver", "Activation", "DecisionSelector", "Feedback",
            "CLCRuntime", "_run_tick", "AKBSM", "Chronicle",
        }
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse(forbidden & (names | attrs))
        recovery = next(
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "reconcile_expsm_readback_failure"
        )
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(recovery) if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        self.assertFalse({"create", "write_complete_store"} & calls)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PolicyGatedNativeCreateTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("PASS: policy-gated NFP-native ExpSM CREATE")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
