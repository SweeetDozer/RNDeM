from __future__ import annotations

import ast
import hashlib
import json
import math
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.experience.effects import ObservedEffect
from clc.experience.expsm_representation import (
    ExpSMOperationalMetadataV1,
    NFPExpSMCreationMetadataV1,
    NFPExpSMRecordV1,
    SerializedNFPActionV1,
    SerializedNFPContextV1,
    SerializedObservedEffectV1,
)
from clc.expsm.nfp_feedback_target import NFPFeedbackTargetCore
from clc.expsm.nfp_native_feedback import NFPFeedbackEvaluationStatus, NFPFeedbackEvidence
from clc.expsm.nfp_native_feedback_apply import (
    NFPFeedbackApplyRecoveryStatus,
    NFPFeedbackApplyStatus,
    NFPFeedbackApplyWriter,
    reconcile_nfp_feedback_readback_failure,
)
from clc.patterns import PatternModality, PatternTopology
from clc.runtime.memory_mutation_policy import RuntimeProfile, policy_for_profile


MEMORY_FILES = (
    ROOT / "Memory/ExpSM/ExpSM_data.json",
    ROOT / "Memory/AKBSM/AKBSM_ne.json",
)
EXPECTED_HASHES = (
    "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
)
FIXED_NOW = "2031-02-03T04:05:06Z"


def _hashes() -> tuple[str, ...]:
    return tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in MEMORY_FILES)


def _record(
    record_id: str = "42",
    *,
    context_values: tuple[float, ...] = (0.2, 0.8),
    action_values: tuple[float, ...] = (0.0, 1.0),
    effect_values: tuple[float, ...] = (0.5, -0.5),
    operational: ExpSMOperationalMetadataV1 | None = None,
    creation: NFPExpSMCreationMetadataV1 | None = None,
    status: int = 2,
    created: str = "2026-01-01T00:00:00Z",
    updated: str = "2026-01-01T00:00:01Z",
) -> NFPExpSMRecordV1:
    return NFPExpSMRecordV1(
        record_id,
        SerializedNFPContextV1("visual", (2,), (context_values,)),
        SerializedNFPActionV1("action", (2,), action_values),
        SerializedObservedEffectV1("visual", (2,), effect_values),
        operational or ExpSMOperationalMetadataV1(3, 2, 0.4, 0.3),
        creation or NFPExpSMCreationMetadataV1(3, "proposal:42", 7),
        status=status,
        created_at_world=created,
        updated_at_world=updated,
    )


def _evidence(
    record: NFPExpSMRecordV1,
    classification: NFPFeedbackEvaluationStatus,
) -> NFPFeedbackEvidence:
    return NFPFeedbackEvidence(
        record.record_id,
        NFPFeedbackTargetCore.from_record(record),
        "action:occurrence:1",
        11,
        record.effect,
        ObservedEffect(
            "effect:1",
            "transition:1",
            PatternModality.VISUAL,
            PatternTopology((2,)),
            record.effect.delta_values,
            "endpoint:before",
            "endpoint:after",
            11,
            12,
        ),
        1.0 if classification is NFPFeedbackEvaluationStatus.HIT else 0.25,
        0.75,
        classification,
    )


def _write_store(path: Path, records: tuple[NFPExpSMRecordV1, ...]) -> None:
    path.write_text(json.dumps({
        "experience": {record.record_id: record.to_json_data() for record in records},
        "reflexes": {},
    }, indent=2) + "\n", encoding="utf-8")


def _raw_store(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mutating_policy(directory: str):
    return policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_root=directory, memory_is_temporary=True)


def _expected_metrics(old: ExpSMOperationalMetadataV1, *, hit: bool) -> tuple[int, int, float, float]:
    hits = old.hits + int(hit)
    misses = old.misses + int(not hit)
    hit_strength = 0.60 * (1.0 - math.exp(-hits / 20.0))
    target_confidence = max(0.0, min(0.60, hit_strength * hits / max(1, hits + misses)))
    confidence = max(0.0, min(0.75, 0.75 * min(old.confidence, 0.75) + 0.25 * target_confidence))
    repeatability_target = 0.90 * (1.0 - math.exp(-(hits + misses) / 10.0))
    repeatability = max(0.0, min(0.90, max(old.repeatability * 0.85, repeatability_target)))
    return hits, misses, round(confidence, 3), round(repeatability, 3)


class NFPNativeFeedbackApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before_hashes = _hashes()
        if cls.before_hashes != EXPECTED_HASHES:
            raise AssertionError(f"unexpected production hashes: {cls.before_hashes}")

    @classmethod
    def tearDownClass(cls) -> None:
        if _hashes() != cls.before_hashes:
            raise AssertionError("native Feedback apply verifier mutated production Memory")

    def test_hit_updates_exact_metrics_and_preserves_immutable_core(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ExpSM_data.json"
            record = _record()
            _write_store(path, (record,))
            result = NFPFeedbackApplyWriter(
                path, _mutating_policy(directory), now_provider=lambda: FIXED_NOW,
            ).apply(_evidence(record, NFPFeedbackEvaluationStatus.HIT))
            self.assertEqual(result.status, NFPFeedbackApplyStatus.UPDATED)
            self.assertEqual(
                (result.record.operational.hits, result.record.operational.misses,
                 result.record.operational.confidence, result.record.operational.repeatability),
                _expected_metrics(record.operational, hit=True),
            )
            self.assertEqual(NFPFeedbackTargetCore.from_record(result.record), NFPFeedbackTargetCore.from_record(record))
            self.assertEqual((result.record.status, result.record.updated_at_world), (record.status, FIXED_NOW))

    def test_miss_updates_only_miss_and_uses_updated_counter_formulas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ExpSM_data.json"
            record = _record(operational=ExpSMOperationalMetadataV1(10, 4, 0.7, 0.55))
            _write_store(path, (record,))
            result = NFPFeedbackApplyWriter(
                path, _mutating_policy(directory), now_provider=lambda: FIXED_NOW,
            ).apply(_evidence(record, NFPFeedbackEvaluationStatus.MISS))
            self.assertEqual(result.status, NFPFeedbackApplyStatus.UPDATED)
            self.assertEqual(
                (result.record.operational.hits, result.record.operational.misses,
                 result.record.operational.confidence, result.record.operational.repeatability),
                _expected_metrics(record.operational, hit=False),
            )

    def test_policy_denials_preserve_exact_bytes(self) -> None:
        for profile in (RuntimeProfile.SAFE_DEMO, RuntimeProfile.DRAFT_ONLY):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "ExpSM_data.json"
                record = _record()
                _write_store(path, (record,))
                before = path.read_bytes()
                policy = policy_for_profile(profile, memory_root=directory, memory_is_temporary=True)
                result = NFPFeedbackApplyWriter(path, policy).apply(_evidence(record, NFPFeedbackEvaluationStatus.HIT))
                self.assertEqual(result.status, NFPFeedbackApplyStatus.DENIED_BY_POLICY)
                self.assertEqual(path.read_bytes(), before)

    def test_exact_id_same_content_and_similar_neighbors_remain_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ExpSM_data.json"
            target = _record("42")
            same = _record("43")
            similar = _record("87", context_values=(0.21, 0.79))
            _write_store(path, (target, same, similar))
            before = _raw_store(path)["experience"]
            result = NFPFeedbackApplyWriter(path, _mutating_policy(directory)).apply(
                _evidence(target, NFPFeedbackEvaluationStatus.HIT),
            )
            after = _raw_store(path)["experience"]
            self.assertEqual(result.status, NFPFeedbackApplyStatus.UPDATED)
            self.assertNotEqual(after["42"], before["42"])
            self.assertEqual(after["43"], before["43"])
            self.assertEqual(after["87"], before["87"])

    def test_structural_and_creation_changes_are_stale(self) -> None:
        base = _record()
        variants = (
            _record(context_values=(0.3, 0.7)),
            _record(action_values=(1.0, 0.0)),
            _record(effect_values=(-0.5, 0.5)),
            _record(creation=NFPExpSMCreationMetadataV1(4, "proposal:42", 7)),
            _record(creation=NFPExpSMCreationMetadataV1(3, "proposal:other", 7)),
            _record(creation=NFPExpSMCreationMetadataV1(3, "proposal:42", 8)),
            _record(created="2027-01-01T00:00:00Z"),
        )
        for variant in variants:
            with self.subTest(core=NFPFeedbackTargetCore.from_record(variant)), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "ExpSM_data.json"
                _write_store(path, (variant,))
                before = path.read_bytes()
                result = NFPFeedbackApplyWriter(path, _mutating_policy(directory)).apply(
                    _evidence(base, NFPFeedbackEvaluationStatus.HIT),
                )
                self.assertEqual(result.status, NFPFeedbackApplyStatus.STALE_OR_CHANGED_TARGET)
                self.assertEqual(path.read_bytes(), before)

    def test_operational_drift_uses_fresh_authoritative_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ExpSM_data.json"
            selected = _record()
            current = replace(
                selected,
                operational=ExpSMOperationalMetadataV1(10, 4, 0.7, 0.55),
                status=7,
                updated_at_world="2030-01-01T00:00:00Z",
            )
            _write_store(path, (current,))
            result = NFPFeedbackApplyWriter(path, _mutating_policy(directory)).apply(
                _evidence(selected, NFPFeedbackEvaluationStatus.HIT),
            )
            self.assertEqual(result.status, NFPFeedbackApplyStatus.UPDATED)
            self.assertEqual(result.record.status, 7)
            self.assertEqual(
                (result.record.operational.hits, result.record.operational.misses,
                 result.record.operational.confidence, result.record.operational.repeatability),
                _expected_metrics(current.operational, hit=True),
            )

    def test_missing_legacy_and_invalid_store_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ExpSM_data.json"
            record = _record()
            _write_store(path, ())
            writer = NFPFeedbackApplyWriter(path, _mutating_policy(directory))
            self.assertEqual(writer.apply(_evidence(record, NFPFeedbackEvaluationStatus.HIT)).status, NFPFeedbackApplyStatus.TARGET_NOT_FOUND)
            legacy = {"if": [], "then": [], "result": [], "recommendation": [], "hits": 0, "misses": 0, "confidence": 0.5, "repeatability": 0.5, "status": 2}
            path.write_text(json.dumps({"experience": {"42": legacy}, "reflexes": {}}))
            self.assertEqual(writer.apply(_evidence(record, NFPFeedbackEvaluationStatus.HIT)).status, NFPFeedbackApplyStatus.TARGET_NOT_NATIVE)
            path.write_text("not json")
            self.assertEqual(writer.apply(_evidence(record, NFPFeedbackEvaluationStatus.HIT)).status, NFPFeedbackApplyStatus.STORE_INVALID)

    def test_pre_replace_failure_preserves_authoritative_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ExpSM_data.json"
            record = _record()
            _write_store(path, (record,))
            before = path.read_bytes()
            def fail(stage: str) -> None:
                if stage == "pre_replace":
                    raise OSError("injected pre-replace failure")
            result = NFPFeedbackApplyWriter(path, _mutating_policy(directory), failure_hook=fail).apply(
                _evidence(record, NFPFeedbackEvaluationStatus.HIT),
            )
            self.assertEqual(result.status, NFPFeedbackApplyStatus.WRITE_FAILED)
            self.assertTrue(result.retry_safe)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(tuple(path.parent.glob(".*.tmp")))

    def test_readback_failure_is_indeterminate_and_reconciliation_does_not_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ExpSM_data.json"
            record = _record()
            _write_store(path, (record,))
            def fail(stage: str) -> None:
                if stage == "post_replace_readback":
                    raise OSError("injected post-replace readback failure")
            result = NFPFeedbackApplyWriter(path, _mutating_policy(directory), failure_hook=fail).apply(
                _evidence(record, NFPFeedbackEvaluationStatus.HIT),
            )
            self.assertEqual(result.status, NFPFeedbackApplyStatus.READBACK_FAILED)
            self.assertFalse(result.retry_safe)
            persisted_after_failure = path.read_bytes()
            recovery = reconcile_nfp_feedback_readback_failure(path, result)
            self.assertEqual(recovery.status, NFPFeedbackApplyRecoveryStatus.CONFIRMED_PERSISTED)
            self.assertEqual(path.read_bytes(), persisted_after_failure)
            self.assertEqual(recovery.record.operational.hits, record.operational.hits + 1)

    def test_mutation_authority_isolated_from_evaluation_execution_and_runtime(self) -> None:
        apply_source = (ROOT / "clc/expsm/nfp_native_feedback_apply.py").read_text()
        self.assertIn("MemoryMutationPolicy", apply_source)
        self.assertIn("ExpSMStoreTransaction", apply_source)
        forbidden = {"MemoryMutationPolicy", "ExpSMStoreTransaction", "NFPFeedbackApplyWriter"}
        for relative in (
            "clc/expsm/nfp_native_feedback.py",
            "clc/expsm/nfp_operational_retrieval.py",
            "clc/expsm/expsm_activation_module.py",
            "clc/action/decision_selector.py",
            "clc/actuation/remembered_action_execution.py",
        ):
            tree = ast.parse((ROOT / relative).read_text())
            names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            names |= {
                alias.name.split(".")[-1]
                for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            self.assertFalse(names & forbidden, f"{relative}: {names & forbidden}")
        runtime = (ROOT / "clc/runtime/clc_runtime.py").read_text()
        self.assertNotIn("NFPFeedbackApplyWriter", runtime)
        self.assertNotIn("reconcile_nfp_feedback_readback_failure", runtime)
        self.assertNotIn("AKBSM", apply_source)
        self.assertNotIn("Chronicle", apply_source)

    def test_scenario_contract(self) -> None:
        fixture = json.loads((ROOT / "scenarios/nfp_native_feedback_apply.json").read_text())
        cases = fixture["expect"]["nfp_native_feedback_apply"]["cases"]
        self.assertTrue(cases and all(cases.values()))
        self.assertFalse(fixture["expect"]["nfp_native_feedback_apply"]["durable_idempotency"])
        self.assertTrue(fixture["expect"]["memory_unchanged"])


def main() -> int:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(NFPNativeFeedbackApplyTests)
    )
    if not result.wasSuccessful():
        return 1
    print("PASS: policy-gated exact-record NFP-native Feedback apply")
    print("PASS: fresh counters, continuity, atomic failure, and read-only recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
