from __future__ import annotations

import ast
import gc
import hashlib
import json
import math
import sys
import unittest
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.context.causal_transition import RecentCausalTransition
from clc.experience.evidence import ExperienceEvidence, ExperienceEvidenceFactory
from clc.experience.expsm_representation import (
    ExpSMOperationalMetadataV1,
    ExpSMRecordAdapter,
    ExpSMRecordCreationRequestBuilder,
    ExpSMRecordKind,
    MalformedRecord,
    NFPNativeOperationalRecordV1,
    NFPExpSMRecordV1,
    SerializedNFPActionV1,
    SerializedNFPContextV1,
    SerializedObservedEffectV1,
    UnsupportedRecord,
    canonical_json,
)
from clc.experience.grouping import ExperienceEvidenceGrouper, ExperienceGroupingConfig
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology


SOURCE = ROOT / "clc" / "experience" / "expsm_representation.py"
SCENARIO = ROOT / "scenarios" / "persistent_nfp_expsm_representation.json"
MEMORY_FILES = (
    ROOT / "Memory" / "ExpSM" / "ExpSM_data.json",
    ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json",
)
EXPECTED_HASHES = (
    "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
)
FORBIDDEN_IMPORT_PARTS = (
    "writer", "memory_mutation_policy", "similarity_observer", "activation",
    "decision_selector", "feedback", "clc_runtime",
)
FORBIDDEN_CALLS = {
    "ExpSMCommitWriter", "ExpSMUpdateWriter", "MemoryMutationPolicy",
    "DecisionSelector", "ExpSMActivationModule", "ExpSMOutcomeFeedback",
    "open", "write_text", "write_bytes", "dump", "_run_tick",
}


def _frame(identity: str, tick: int, values: tuple[float, ...], *, action: bool = False, debug: str = "debug") -> NFPFrame:
    return NFPFrame(
        identity,
        PatternModality.ACTION if action else PatternModality.VISUAL,
        PatternOrigin.ACTION_GENERATED if action else PatternOrigin.EXTERNAL_SENSORY,
        PatternTopology((len(values),)), values, tick,
        provenance_ref=f"occurrence:{identity}", debug_name=debug,
    )


def _transition(identity: str, *, tick: int = 2, debug: str = "debug") -> RecentCausalTransition:
    before = NFPWindow(
        f"before:{identity}",
        (_frame(f"{identity}:before:1", tick - 1, (0.1, 0.5, 0.9), debug=debug),
         _frame(f"{identity}:before:2", tick, (0.8, 0.5, 0.4), debug=debug)),
        provenance_ref=f"window:{identity}", debug_name=debug,
    )
    after = NFPWindow(
        f"after:{identity}",
        (_frame(f"{identity}:after:1", tick, (0.8, 0.5, 0.4), debug=debug),
         _frame(f"{identity}:after:2", tick + 1, (0.05, 0.5, 0.9), debug=debug)),
        provenance_ref=f"window-after:{identity}", debug_name=debug,
    )
    return RecentCausalTransition(
        f"transition:{identity}", before,
        _frame(f"{identity}:action", tick, (0.0, 1.0), action=True, debug=debug),
        after, tick, tick + 1,
    )


def _proposal_and_evidence() -> tuple[object, ExperienceEvidence]:
    grouper = ExperienceEvidenceGrouper(ExperienceGroupingConfig(1.0, 1.0, 1.0, 2))
    first = ExperienceEvidenceFactory.build(_transition("first", tick=2, debug="first debug"))
    second = ExperienceEvidenceFactory.build(_transition("second", tick=5, debug="second debug"))
    first_result = grouper.observe(first)
    grouper.observe(second)
    proposal = grouper.make_proposal(first_result.candidate_id or "", current_tick=9)
    if proposal is None:
        raise AssertionError("expected eligible proposal")
    return proposal, first


def _request():
    proposal, evidence = _proposal_and_evidence()
    return ExpSMRecordCreationRequestBuilder.build(
        proposal, evidence, request_id="request:restart-proof",
    )


def _hashes() -> tuple[str, ...]:
    return tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in MEMORY_FILES)


def _root_memory_files() -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(ROOT / "Memory")) for path in (ROOT / "Memory").rglob("*") if path.is_file()))


def _assert_json_primitives(test: unittest.TestCase, value: object) -> None:
    if isinstance(value, dict):
        test.assertTrue(all(isinstance(key, str) for key in value))
        for child in value.values():
            _assert_json_primitives(test, child)
        return
    if isinstance(value, list):
        for child in value:
            _assert_json_primitives(test, child)
        return
    test.assertIsInstance(value, (str, int, float, bool, type(None)))
    if isinstance(value, float):
        test.assertTrue(math.isfinite(value))


def _assert_no_live_cognitive_objects(test: unittest.TestCase, value: object) -> None:
    test.assertNotIsInstance(value, (NFPFrame, NFPWindow, ExperienceEvidence, RecentCausalTransition))
    if is_dataclass(value):
        for field in fields(value):
            _assert_no_live_cognitive_objects(test, getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for child in value:
            _assert_no_live_cognitive_objects(test, child)
    elif isinstance(value, dict):
        for child in value.values():
            _assert_no_live_cognitive_objects(test, child)


class PersistentNFPExpSMRepresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before_hashes = _hashes()
        cls.before_files = _root_memory_files()

    @classmethod
    def tearDownClass(cls) -> None:
        if _hashes() != cls.before_hashes or _root_memory_files() != cls.before_files:
            raise AssertionError("representation verification mutated Memory")

    def test_runtime_conversion_excludes_occurrence_identity(self) -> None:
        first = ExperienceEvidenceFactory.build(_transition("neutral-a", tick=2, debug="alpha"))
        second = ExperienceEvidenceFactory.build(_transition("neutral-b", tick=8, debug="beta"))
        self.assertEqual(SerializedNFPContextV1.from_window(first.context_window),
                         SerializedNFPContextV1.from_window(second.context_window))
        self.assertEqual(SerializedNFPActionV1.from_frame(first.action_frame),
                         SerializedNFPActionV1.from_frame(second.action_frame))
        self.assertEqual(SerializedObservedEffectV1.from_effect(first.observed_effect),
                         SerializedObservedEffectV1.from_effect(second.observed_effect))
        request_data = _request().to_json_data()
        text = canonical_json({
            "context": request_data["context_pattern"],
            "action": request_data["action_pattern"],
            "effect": request_data["effect_pattern"],
        })
        for omitted in ("frame_id", "active_tick", "origin", "provenance_ref", "debug_name", "effect_id"):
            self.assertNotIn(omitted, text)

    def test_request_is_frozen_json_safe_and_support_is_provenance_only(self) -> None:
        request = _request()
        data = request.to_json_data()
        _assert_json_primitives(self, data)
        _assert_no_live_cognitive_objects(self, request)
        self.assertNotIn("record_id", data)
        self.assertEqual(data["creation_metadata"]["source_support_count"], 2)
        self.assertEqual(data["requested_operational_metadata"], {
            "hits": 0, "misses": 0, "confidence": 0.5, "repeatability": 0.5,
        })
        self.assertEqual(canonical_json(data), canonical_json(json.loads(canonical_json(data))))
        with self.assertRaises(FrozenInstanceError):
            request.request_id = "changed"

    def test_fresh_object_round_trip_and_distinct_ids(self) -> None:
        request = _request()
        original = request.materialize_for_validation("41")
        encoded = canonical_json(original.to_json_data())
        original_data = original.to_json_data()
        del request, original
        gc.collect()
        fresh_data = json.loads(encoded)
        parsed = ExpSMRecordAdapter.parse("41", fresh_data)
        self.assertIsInstance(parsed, NFPNativeOperationalRecordV1)
        self.assertEqual(parsed.record.to_json_data(), original_data)
        self.assertEqual(parsed.record.effect.delta_values, (-0.75, 0.0, 0.5))
        other = ExpSMRecordAdapter.parse("42", fresh_data)
        self.assertIsInstance(other, NFPNativeOperationalRecordV1)
        self.assertEqual(parsed.record.context, other.record.context)
        self.assertNotEqual(parsed.record.record_id, other.record.record_id)

    def test_zero_effect_round_trip(self) -> None:
        request = _request()
        zero_effect = SerializedObservedEffectV1(
            request.effect.modality, request.effect.topology, (0.0, 0.0, 0.0),
        )
        record = NFPExpSMRecordV1(
            "7", request.context, request.action, zero_effect,
            request.requested_operational, request.creation_metadata,
        )
        parsed = ExpSMRecordAdapter.parse("7", json.loads(canonical_json(record.to_json_data())))
        self.assertEqual(parsed.record.effect.delta_values, (0.0, 0.0, 0.0))

    def test_legacy_and_native_coexist_without_migration(self) -> None:
        store = json.loads(MEMORY_FILES[0].read_text(encoding="utf-8"))
        legacy_raw = store["experience"]["2"]
        unchanged = canonical_json(legacy_raw)
        legacy = ExpSMRecordAdapter.parse("2", legacy_raw)
        native = ExpSMRecordAdapter.parse("9", _request().materialize_for_validation("9").to_json_data())
        self.assertEqual(legacy.kind, ExpSMRecordKind.LEGACY)
        self.assertEqual(native.kind, ExpSMRecordKind.NFP_NATIVE_V1)
        self.assertEqual(canonical_json(legacy_raw), unchanged)
        self.assertFalse(hasattr(legacy, "context"))

    def test_unsupported_and_malformed_dispatch(self) -> None:
        valid = _request().materialize_for_validation("11").to_json_data()
        unsupported = dict(valid, representation_version=999)
        self.assertIsInstance(ExpSMRecordAdapter.parse("11", unsupported), UnsupportedRecord)
        self.assertIsInstance(ExpSMRecordAdapter.parse("11", {"record_kind": "future", "representation_version": 1}), UnsupportedRecord)
        self.assertIsInstance(ExpSMRecordAdapter.parse("11", {"record_kind": "nfp_native"}), MalformedRecord)
        self.assertIsInstance(ExpSMRecordAdapter.parse("11", {"if": [], "then": []}), MalformedRecord)

    def test_malformed_native_values_fail_closed(self) -> None:
        base = _request().materialize_for_validation("12").to_json_data()
        mutations = []
        for value in (float("nan"), float("inf"), -0.01, 1.01):
            item = json.loads(json.dumps(base))
            item["context_pattern"]["frames"][0]["values"][0] = value
            mutations.append(item)
        for value in (-1.01, 1.01, float("nan"), float("inf")):
            item = json.loads(json.dumps(base))
            item["effect_pattern"]["delta_values"][0] = value
            mutations.append(item)
        mismatch = json.loads(json.dumps(base))
        mismatch["action_pattern"]["values"] = [0.0]
        mutations.append(mismatch)
        missing = json.loads(json.dumps(base))
        del missing["context_pattern"]
        mutations.append(missing)
        for item in mutations:
            with self.subTest(item=item):
                self.assertIsInstance(ExpSMRecordAdapter.parse("12", item), MalformedRecord)
        with self.assertRaises(ValueError):
            canonical_json({"bad": float("nan")})

    def test_builder_rejects_mismatched_evidence_and_preserves_explicit_counters(self) -> None:
        proposal, evidence = _proposal_and_evidence()
        wrong = ExperienceEvidenceFactory.build(_transition("wrong", tick=12))
        with self.assertRaises(ValueError):
            ExpSMRecordCreationRequestBuilder.build(proposal, wrong, request_id="wrong")
        operational = ExpSMOperationalMetadataV1(4, 3, 0.7, 0.6)
        request = ExpSMRecordCreationRequestBuilder.build(
            proposal, evidence, request_id="explicit", requested_operational=operational,
        )
        self.assertEqual(request.requested_operational, operational)
        self.assertEqual(request.creation_metadata.source_support_count, proposal.support_count)

    def test_source_has_no_write_or_runtime_authority(self) -> None:
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        imported = []
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
        self.assertFalse(any(part in name for name in imported for part in FORBIDDEN_IMPORT_PARTS))
        self.assertFalse(FORBIDDEN_CALLS.intersection(calls))
        self.assertNotIn("record_id", _request().to_json_data())

    def test_fixture_declares_required_isolation(self) -> None:
        fixture = json.loads(SCENARIO.read_text(encoding="utf-8"))
        section = fixture["expect"]["persistent_nfp_expsm_representation"]
        self.assertTrue(section["isolated"])
        self.assertFalse(section["runtime_wiring"])
        self.assertFalse(section["write_authority"])
        self.assertTrue(all(section["cases"].values()))


def main() -> int:
    if _hashes() != EXPECTED_HASHES:
        print("FAIL: unexpected starting Memory hashes")
        return 1
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PersistentNFPExpSMRepresentationTests)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    if result.wasSuccessful() and _hashes() == EXPECTED_HASHES:
        print("PASS: persistent NFP-native ExpSM representation")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
