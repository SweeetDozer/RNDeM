from __future__ import annotations

import ast
import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.action.decision_selector import DecisionSelector
from clc.core.ids import IdGenerator
from clc.core.pattern_registry import PatternRegistry
from clc.experience.expsm_representation import (
    ExpSMOperationalMetadataV1,
    NFPExpSMCreationMetadataV1,
    NFPExpSMRecordV1,
    SerializedNFPActionV1,
    SerializedNFPContextV1,
    SerializedObservedEffectV1,
)
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.expsm_similarity_observer import ExpSMSimilarityObserver
from clc.expsm.nfp_operational_retrieval import (
    LivePersistentNFPContextSimilarity,
    NFPExpSMRetrievalConfig,
    NFPExpSMRetrievalQuery,
    NFPExpSMRetrievalStatus,
    NFPExpSMRetriever,
)
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology
from clc.patterns.similarity import NFPWindowSimilarity


PRODUCTION_FILES = (
    ROOT / "Memory" / "ExpSM" / "ExpSM_data.json",
    ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json",
)
EXPECTED_HASHES = (
    "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
)
RETRIEVAL_SOURCE = ROOT / "clc" / "expsm" / "nfp_operational_retrieval.py"
EXTENSION_METHODS = {
    ROOT / "clc" / "expsm" / "expsm_similarity_observer.py": "retrieve_native",
    ROOT / "clc" / "expsm" / "expsm_activation_module.py": "activate_native",
    ROOT / "clc" / "action" / "decision_selector.py": "select_native",
}


def _hashes() -> tuple[str, ...]:
    return tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in PRODUCTION_FILES)


def _window(
    values: tuple[tuple[float, ...], ...],
    *,
    identity: str = "query",
    modality: PatternModality = PatternModality.VISUAL,
    origin: PatternOrigin = PatternOrigin.EXTERNAL_SENSORY,
    topology: tuple[int, ...] = (2,),
) -> NFPWindow:
    frames = tuple(
        NFPFrame(
            f"{identity}:{index}", modality, origin, PatternTopology(topology), frame_values,
            index + 10, provenance_ref=f"provenance:{identity}:{index}", debug_name=f"debug:{identity}:{index}",
        )
        for index, frame_values in enumerate(values)
    )
    return NFPWindow(identity, frames, provenance_ref=f"window:{identity}", debug_name=identity)


def _record(
    record_id: str,
    context: SerializedNFPContextV1,
    *,
    action: tuple[float, ...] = (0.0, 1.0),
    effect: tuple[float, ...] = (0.2, -0.1),
    confidence: float = 0.6,
    repeatability: float = 0.4,
    hits: int = 2,
    misses: int = 1,
) -> dict[str, object]:
    return NFPExpSMRecordV1(
        record_id,
        context,
        SerializedNFPActionV1("action", (2,), action),
        SerializedObservedEffectV1(context.modality, context.topology, effect),
        ExpSMOperationalMetadataV1(hits, misses, confidence, repeatability),
        NFPExpSMCreationMetadataV1(2, f"proposal:{record_id}", 7),
    ).to_json_data()


def _legacy() -> dict[str, object]:
    return {
        "if": ["pat_0001"], "then": ["pat_0002"], "result": ["pat_0003"],
        "recommendation": ["pat_0004"], "hits": 1, "misses": 0,
        "confidence": 0.6, "repeatability": 0.5, "status": 2,
    }


def _write_store(path: Path, experiences: dict[str, object]) -> bytes:
    data = json.dumps({"experience": experiences, "reflexes": {}}, sort_keys=True).encode()
    path.write_bytes(data)
    return data


class NFPOperationalRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before_hashes = _hashes()
        if cls.before_hashes != EXPECTED_HASHES:
            raise AssertionError(f"unexpected production hashes: {cls.before_hashes}")

    @classmethod
    def tearDownClass(cls) -> None:
        if _hashes() != cls.before_hashes:
            raise AssertionError("retrieval verifier mutated production Memory")

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ExpSM_data.json"
        self.manifest = Path(self.temp.name) / "pattern_manifest.json"
        self.query_window = _window(((0.1, 0.9), (0.8, 0.2)))
        self.context = SerializedNFPContextV1.from_window(self.query_window)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _observer(self) -> ExpSMSimilarityObserver:
        return ExpSMSimilarityObserver(IdGenerator(), PatternRegistry(self.manifest), self.path)

    def test_similarity_parity_noncomparability_and_occurrence_neutrality(self) -> None:
        other = _window(((0.2, 0.8), (0.7, 0.3)), identity="other")
        runtime = NFPWindowSimilarity.compare(self.query_window, other)
        persistent = LivePersistentNFPContextSimilarity.compare(
            self.query_window, SerializedNFPContextV1.from_window(other),
        )
        self.assertTrue(runtime.comparable and persistent.comparable)
        self.assertTrue(math.isclose(runtime.score or 0.0, persistent.score or 0.0))
        neutral = _window(((0.1, 0.9), (0.8, 0.2)), identity="different-occurrence")
        self.assertEqual(LivePersistentNFPContextSimilarity.compare(neutral, self.context).score, 1.0)
        cases = (
            SerializedNFPContextV1("audio", (2,), self.context.frames),
            SerializedNFPContextV1("visual", (1, 2), self.context.frames),
            SerializedNFPContextV1("visual", (2,), (self.context.frames[0],)),
        )
        self.assertEqual(
            [LivePersistentNFPContextSimilarity.compare(self.query_window, value).reason for value in cases],
            ["different_modality", "different_topology", "different_frame_count"],
        )
        self.assertTrue(all(LivePersistentNFPContextSimilarity.compare(self.query_window, value).score is None for value in cases))

    def test_authority_context_only_coexistence_and_read_only_store(self) -> None:
        dissimilar = SerializedNFPContextV1("visual", (2,), ((1.0, 0.0), (0.0, 1.0)))
        before = _write_store(self.path, {
            "1": _legacy(),
            "2": _record("2", self.context, action=(0.0, 1.0), effect=(0.2, -0.1)),
            "3": _record("3", self.context, action=(1.0, 0.0), effect=(-0.2, 0.1)),
            "4": _record("4", self.context, action=(0.0, 1.0), effect=(-0.4, 0.4)),
            "5": _record("5", self.context, action=(0.0, 1.0), effect=(0.2, -0.1)),
            "6": _record("6", dissimilar, action=(0.0, 1.0), effect=(0.2, -0.1)),
        })
        result = self._observer().retrieve_native(
            NFPExpSMRetrievalQuery(self.query_window), NFPExpSMRetrievalConfig(0.9),
        )
        self.assertEqual(result.status, NFPExpSMRetrievalStatus.OK)
        self.assertEqual(result.legacy_records_seen, 1)
        self.assertEqual([candidate.source_experience_id for candidate in result.candidates], ["2", "3", "4", "5"])
        self.assertEqual(len({candidate.candidate_id for candidate in result.candidates}), 4)
        self.assertTrue(all(candidate.candidate_id != candidate.source_experience_id for candidate in result.candidates))
        self.assertEqual(self.path.read_bytes(), before)

        internal = _window(
            ((0.1, 0.9), (0.8, 0.2)), identity="internal", origin=PatternOrigin.INTERNAL_REACTIVATION,
        )
        rejected = NFPExpSMRetriever(self.path).retrieve(
            NFPExpSMRetrievalQuery(internal), NFPExpSMRetrievalConfig(0.0),
        )
        self.assertEqual(rejected.status, NFPExpSMRetrievalStatus.INVALID_QUERY)

    def test_activation_formula_top_n_identity_and_selector(self) -> None:
        _write_store(self.path, {
            str(index): _record(str(index), self.context, action=(index % 2, (index + 1) % 2))
            for index in range(1, 5)
        })
        id_gen = IdGenerator()
        observer = ExpSMSimilarityObserver(id_gen, PatternRegistry(self.manifest), self.path)
        retrieved = observer.retrieve_native(
            NFPExpSMRetrievalQuery(self.query_window), NFPExpSMRetrievalConfig(0.5),
        )
        activation = ExpSMActivationModule(id_gen, PatternRegistry(self.manifest), self.path)
        top = activation.activate_native(retrieved.candidates)
        self.assertEqual(len(top), 3)
        expected_viability = (2 + 1) / (2 + 1 + 2)
        expected = 1.0 * 0.55 + 0.6 * 0.20 + 0.4 * 0.15 + expected_viability * 0.10
        self.assertTrue(all(math.isclose(candidate.activation, expected) for candidate in top))
        self.assertTrue(all(candidate.context_similarity == 1.0 for candidate in top))
        self.assertTrue(all(candidate.activation_id != candidate.source_experience_id for candidate in top))
        selected = DecisionSelector(id_gen).select_native(top)
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.source_experience_id, top[0].source_experience_id)
        self.assertEqual(selected.action, top[0].action)
        self.assertEqual(selected.effect, top[0].effect)
        self.assertNotEqual(selected.selection_id, selected.source_experience_id)

    def test_fail_closed_and_empty_semantics(self) -> None:
        query = NFPExpSMRetrievalQuery(self.query_window)
        config = NFPExpSMRetrievalConfig(0.9)
        _write_store(self.path, {"1": {"record_kind": "future", "representation_version": 2}})
        self.assertEqual(NFPExpSMRetriever(self.path).retrieve(query, config).status,
                         NFPExpSMRetrievalStatus.UNSUPPORTED_MEMORY_PRESENT)
        _write_store(self.path, {"1": {"record_kind": "nfp_native"}})
        self.assertEqual(NFPExpSMRetriever(self.path).retrieve(query, config).status,
                         NFPExpSMRetrievalStatus.STORE_INVALID)
        incompatible = SerializedNFPContextV1("audio", (2,), self.context.frames)
        _write_store(self.path, {"1": _record("1", incompatible, effect=(0.1, -0.1))})
        self.assertEqual(NFPExpSMRetriever(self.path).retrieve(query, config).status,
                         NFPExpSMRetrievalStatus.NO_COMPARABLE_RECORDS)
        below = SerializedNFPContextV1("visual", (2,), ((0.0, 1.0), (0.7, 0.3)))
        _write_store(self.path, {"1": _record("1", below)})
        result = NFPExpSMRetriever(self.path).retrieve(query, NFPExpSMRetrievalConfig(0.99))
        self.assertEqual(result.status, NFPExpSMRetrievalStatus.NO_COMPARABLE_RECORDS)
        self.assertEqual(result.reason, "below_native_threshold")

    def test_production_ast_has_no_mutation_execution_feedback_or_runtime_authority(self) -> None:
        forbidden_names = {
            "MemoryMutationPolicy", "NFPExpSMCreateWriter", "ExpSMCommitWriter",
            "ExpSMUpdateWriter", "ExpSMStoreTransaction", "ExpSMOutcomeFeedback",
            "ActionTransducer", "ModeActionGuard", "CLCRuntime", "_run_tick",
        }
        audited: list[tuple[Path, ast.AST]] = [
            (RETRIEVAL_SOURCE, ast.parse(RETRIEVAL_SOURCE.read_text(encoding="utf-8"))),
        ]
        for source, method_name in EXTENSION_METHODS.items():
            tree = ast.parse(source.read_text(encoding="utf-8"))
            method = next(
                node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name
            )
            audited.append((source, method))
        for source, tree in audited:
            imported = {
                alias.name.split(".")[-1]
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            calls = {
                node.func.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            self.assertFalse((imported | calls) & forbidden_names, source)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NFPOperationalRetrievalTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    print("PASS: isolated NFP-native ExpSM operational retrieval")
    print("PASS: read-only authority, identity propagation, top-N, and selection boundaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
