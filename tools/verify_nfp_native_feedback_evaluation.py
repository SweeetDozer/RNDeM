from __future__ import annotations

import ast
import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import fields, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.actuation import (
    NFPRememberedActionExecutionCoordinator,
    NFPRememberedActionExecutionResult,
    SelectedNFPExecutionRequest,
)
from clc.actuation.remembered_action_execution import NFPRememberedActionExecutionStatus as ExecutionStatus
from clc.action.decision_selector import DecisionSelector
from clc.context.causal_transition import RecentCausalTransition
from clc.context.context_memory import ContextMemory
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.context_ops_pool import ContextOpsPool
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
from clc.expsm.nfp_feedback_target import NFPFeedbackTargetCore
from clc.expsm.nfp_native_feedback import (
    NFPFeedbackEvaluationConfig,
    NFPFeedbackEvaluationStatus as FeedbackStatus,
    NativePredictedObservedEffectComparator,
    evaluate_native_feedback,
)
from clc.expsm.nfp_operational_retrieval import (
    NFPExpSMRetrievalConfig,
    NFPExpSMRetrievalQuery,
    NFPExpSMRetriever,
    SelectedNFPExpSMExperience,
)
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState
from clc.transduction import VisualFieldTransducer
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld


MEMORY_FILES = (
    ROOT / "Memory/ExpSM/ExpSM_data.json",
    ROOT / "Memory/AKBSM/AKBSM_ne.json",
)
EXPECTED_HASHES = (
    "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
)
PRODUCTION_SOURCES = (
    ROOT / "clc/expsm/nfp_feedback_target.py",
    ROOT / "clc/expsm/nfp_native_feedback.py",
    ROOT / "clc/expsm/nfp_operational_retrieval.py",
    ROOT / "clc/expsm/expsm_activation_module.py",
    ROOT / "clc/action/decision_selector.py",
    ROOT / "clc/actuation/remembered_action_execution.py",
)


def _hashes() -> tuple[str, ...]:
    return tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in MEMORY_FILES)


def _context(value: float = 0.2) -> SerializedNFPContextV1:
    return SerializedNFPContextV1("visual", (2,), ((value, 1.0 - value),))


def _record(
    *, context: SerializedNFPContextV1 | None = None,
    action: tuple[float, ...] = (0.0, 1.0),
    effect: tuple[float, ...] = (0.5, -0.5),
    creation: NFPExpSMCreationMetadataV1 | None = None,
    operational: ExpSMOperationalMetadataV1 | None = None,
    status: int = 2,
    created: str | None = "2026-01-01T00:00:00Z",
    updated: str | None = "2026-01-01T00:00:01Z",
) -> NFPExpSMRecordV1:
    return NFPExpSMRecordV1(
        "42", context or _context(), SerializedNFPActionV1("action", (2,), action),
        SerializedObservedEffectV1("visual", (2,), effect),
        operational or ExpSMOperationalMetadataV1(2, 1, 0.6, 0.5),
        creation or NFPExpSMCreationMetadataV1(3, "proposal:42", 7),
        status=status, created_at_world=created, updated_at_world=updated,
    )


def _window(identity: str, values: tuple[float, ...], tick: int) -> NFPWindow:
    return NFPWindow(identity, (NFPFrame(
        f"{identity}:frame", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY,
        PatternTopology((2,)), values, tick,
    ),))


def _transition(
    *, action_id: str = "action:1", action_tick: int = 4,
    before: tuple[float, ...] = (0.2, 0.8), after: tuple[float, ...] = (0.7, 0.3),
) -> RecentCausalTransition:
    action = NFPFrame(
        action_id, PatternModality.ACTION, PatternOrigin.ACTION_GENERATED,
        PatternTopology((2,)), (0.0, 1.0), action_tick,
    )
    return RecentCausalTransition(
        f"transition:{action_id}", _window("before", before, action_tick), action,
        _window("after", after, action_tick + 1), action_tick, action_tick + 1,
    )


def _execution(
    core: NFPFeedbackTargetCore, transition: RecentCausalTransition,
    *, status: ExecutionStatus = ExecutionStatus.EXECUTED_AND_OBSERVED,
    predicted: SerializedObservedEffectV1 | None = None,
) -> NFPRememberedActionExecutionResult:
    return NFPRememberedActionExecutionResult(
        status=status,
        source_experience_id="42",
        action_frame=transition.action_frame,
        predicted_effect=predicted or core.effect,
        recent_transition=transition if status is ExecutionStatus.EXECUTED_AND_OBSERVED else None,
        target_core=core,
    )


class NFPNativeFeedbackEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before_hashes = _hashes()
        if cls.before_hashes != EXPECTED_HASHES:
            raise AssertionError(f"unexpected production hashes: {cls.before_hashes}")

    @classmethod
    def tearDownClass(cls) -> None:
        if _hashes() != cls.before_hashes:
            raise AssertionError("native Feedback evaluation mutated production Memory")

    def test_target_core_exact_schema_exclusions_and_round_trip(self) -> None:
        record = _record()
        core = NFPFeedbackTargetCore.from_record(record)
        self.assertEqual(
            tuple(field.name for field in fields(core)),
            ("record_kind", "representation_version", "context", "action", "effect",
             "source_support_count", "source_proposal_id", "created_active_tick",
             "initialization_profile", "created_at_world"),
        )
        for excluded in ("record_id", "status", "updated_at_world", "hits", "misses", "confidence", "repeatability"):
            self.assertFalse(hasattr(core, excluded), excluded)
        parsed = NFPExpSMRecordV1.from_json_data(record.record_id, json.loads(json.dumps(record.to_json_data())))
        self.assertEqual(NFPFeedbackTargetCore.from_record(parsed), core)

    def test_mutable_metadata_is_excluded_and_immutable_fields_change_equality(self) -> None:
        base = _record()
        core = NFPFeedbackTargetCore.from_record(base)
        mutable = _record(
            operational=ExpSMOperationalMetadataV1(20, 30, 0.1, 0.9), status=7,
            updated="2030-02-03T04:05:06Z",
        )
        self.assertEqual(NFPFeedbackTargetCore.from_record(mutable), core)
        variants = (
            _record(context=_context(0.3)),
            _record(action=(1.0, 0.0)),
            _record(effect=(-0.5, 0.5)),
            _record(creation=NFPExpSMCreationMetadataV1(4, "proposal:42", 7)),
            _record(creation=NFPExpSMCreationMetadataV1(3, "proposal:other", 7)),
            _record(creation=NFPExpSMCreationMetadataV1(3, "proposal:42", 8)),
            _record(created="2027-01-01T00:00:00Z"),
        )
        self.assertTrue(all(NFPFeedbackTargetCore.from_record(item) != core for item in variants))
        self.assertNotEqual(replace(core, initialization_profile="future_profile"), core)
        with self.assertRaises(ValueError):
            NFPExpSMCreationMetadataV1(3, "proposal:42", 7, "future_profile")

    def test_real_record_candidate_activation_selection_propagation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "ExpSM_data.json"
            manifest = Path(directory) / "manifest.json"
            record = _record(effect=(0.5, -0.5))
            store.write_text(json.dumps({"experience": {"42": record.to_json_data()}, "reflexes": {}}))
            query = _window("query", (0.2, 0.8), 4)
            candidate = NFPExpSMRetriever(store).retrieve(
                NFPExpSMRetrievalQuery(query), NFPExpSMRetrievalConfig(1.0),
            ).candidates[0]
            activated = ExpSMActivationModule(
                IdGenerator(), PatternRegistry(manifest), store,
            ).activate_native((candidate,))[0]
            selected = DecisionSelector(IdGenerator()).select_native((activated,))
            assert selected is not None
            self.assertEqual(candidate.source_experience_id, "42")
            self.assertIs(activated.target_core, candidate.target_core)
            self.assertIs(selected.target_core, candidate.target_core)
            self.assertEqual(selected.activation, activated.activation)

    def test_real_execution_propagates_core_without_changing_physics(self) -> None:
        core = NFPFeedbackTargetCore.from_record(_record(effect=(0.0,) * 2))
        changed_metadata = replace(
            core, source_support_count=99, source_proposal_id="proposal:inert",
            created_active_tick=999, created_at_world="2040-01-01T00:00:00Z",
        )
        outcomes = []
        with tempfile.TemporaryDirectory() as directory:
            registry = PatternRegistry(Path(directory) / "manifest.json")
            for index, target_core in enumerate((core, changed_metadata), start=1):
                world = SyntheticClosedLoopVisualWorld(shape=(4, 4), initial_tick=3)
                manager = ContextMemoryManager(ContextMemory(IdGenerator(), registry), ContextOpsPool())
                before_frame = VisualFieldTransducer().transduce(
                    world.snapshot(), frame_id=f"before:{index}",
                )
                manager.observe_external_sensory_window(NFPWindow(f"window:{index}", (before_frame,)))
                selected = SelectedNFPExpSMExperience(
                    f"selection:{index}", f"activation:{index}", f"candidate:{index}", "42",
                    1.0, 1.0, SerializedNFPActionV1("action", (2,), (0.0, 1.0)),
                    target_core.effect, 0.6, 0.5, 0.75, target_core,
                )
                result = NFPRememberedActionExecutionCoordinator(
                    IdGenerator(), ModeActionGuard(registry),
                ).execute(
                    SelectedNFPExecutionRequest(selected, 3), context_manager=manager,
                    world=world, system_state=SystemState(),
                )
                self.assertIs(result.target_core, target_core)
                outcomes.append((result.action_frame.values, result.actuator_signal.values, world.hidden_position))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_perfect_threshold_miss_and_signed_comparison(self) -> None:
        core = NFPFeedbackTargetCore.from_record(_record())
        transition = _transition()
        execution = _execution(core, transition)
        hit = evaluate_native_feedback(execution, transition, NFPFeedbackEvaluationConfig(1.0))
        self.assertEqual((hit.status, hit.effect_similarity), (FeedbackStatus.HIT, 1.0))
        self.assertIs(hit.evidence.target_core, core)
        threshold = evaluate_native_feedback(execution, transition, NFPFeedbackEvaluationConfig(1.0))
        self.assertEqual(threshold.status, FeedbackStatus.HIT)
        opposite = _transition(after=(0.0, 1.0))
        opposite_execution = _execution(core, opposite)
        disagreement = evaluate_native_feedback(
            opposite_execution, opposite, NFPFeedbackEvaluationConfig(0.8),
        )
        self.assertEqual(disagreement.status, FeedbackStatus.MISS)
        self.assertLess(disagreement.effect_similarity or 1.0, 0.8)

    def test_below_threshold_comparable_is_miss(self) -> None:
        core = NFPFeedbackTargetCore.from_record(_record())
        transition = _transition(after=(0.2, 0.8))
        result = evaluate_native_feedback(_execution(core, transition), transition, NFPFeedbackEvaluationConfig(0.9))
        self.assertEqual(result.status, FeedbackStatus.MISS)
        self.assertIsNotNone(result.evidence)

    def test_effect_comparison_preserves_channel_order(self) -> None:
        core = NFPFeedbackTargetCore.from_record(_record(effect=(0.75, -0.25)))
        transition = _transition(before=(0.5, 0.0), after=(0.25, 0.75))
        result = evaluate_native_feedback(
            _execution(core, transition), transition, NFPFeedbackEvaluationConfig(0.75),
        )
        self.assertEqual(
            result.effect_similarity, 0.5,
            "equal value multisets in different channels must not be perfect agreement",
        )
        self.assertEqual(result.status, FeedbackStatus.MISS)

    def test_incomparable_effects_are_not_misses(self) -> None:
        actual = evaluate_native_feedback
        core = NFPFeedbackTargetCore.from_record(_record())
        transition = _transition()
        modality_core = replace(core, effect=SerializedObservedEffectV1("audio", (2,), (0.5, -0.5)))
        modality = actual(_execution(modality_core, transition), transition, NFPFeedbackEvaluationConfig(0.5))
        self.assertEqual(modality.status, FeedbackStatus.INCOMPARABLE_EFFECT)
        self.assertIsNone(modality.effect_similarity)
        topology_core = replace(core, effect=SerializedObservedEffectV1("visual", (1, 2), (0.5, -0.5)))
        topology = actual(_execution(topology_core, transition), transition, NFPFeedbackEvaluationConfig(0.5))
        self.assertEqual(topology.status, FeedbackStatus.INCOMPARABLE_EFFECT)

    def test_transition_identity_and_prediction_consistency(self) -> None:
        core = NFPFeedbackTargetCore.from_record(_record())
        transition = _transition()
        other = _transition(action_id="action:other")
        mismatch = evaluate_native_feedback(_execution(core, transition), other, NFPFeedbackEvaluationConfig(0.5))
        self.assertEqual(mismatch.status, FeedbackStatus.TRANSITION_MISMATCH)
        self.assertIsNone(mismatch.evidence)
        conflicting = SerializedObservedEffectV1("visual", (2,), (0.0, 0.0))
        invalid = evaluate_native_feedback(
            _execution(core, transition, predicted=conflicting), transition, NFPFeedbackEvaluationConfig(0.5),
        )
        self.assertEqual(invalid.status, FeedbackStatus.INVALID_PREDICTION)

    def test_same_source_experience_different_execution_transition_mismatches(self) -> None:
        core = NFPFeedbackTargetCore.from_record(_record())
        transition_a = _transition(action_id="action:a", action_tick=4)
        transition_b = _transition(action_id="action:b", action_tick=6)
        execution_a = _execution(core, transition_a)
        execution_b = _execution(core, transition_b)

        self.assertEqual(execution_a.source_experience_id, execution_b.source_experience_id)
        self.assertNotEqual(execution_a.action_frame.frame_id, execution_b.action_frame.frame_id)
        self.assertNotEqual(execution_a.action_frame.active_tick, execution_b.action_frame.active_tick)

        crossed = evaluate_native_feedback(
            execution_a, transition_b, NFPFeedbackEvaluationConfig(0.5),
        )
        self.assertEqual(crossed.status, FeedbackStatus.TRANSITION_MISMATCH)
        self.assertIsNone(crossed.evidence)

        positive_control = evaluate_native_feedback(
            execution_b, transition_b, NFPFeedbackEvaluationConfig(0.5),
        )
        self.assertEqual(positive_control.status, FeedbackStatus.HIT)

    def test_no_evidence_execution_statuses(self) -> None:
        core = NFPFeedbackTargetCore.from_record(_record())
        transition = _transition()
        for status in (ExecutionStatus.GUARD_DENIED, ExecutionStatus.STALE_SELECTION, ExecutionStatus.WORLD_EXECUTION_FAILED):
            result = evaluate_native_feedback(_execution(core, transition, status=status), None, NFPFeedbackEvaluationConfig(0.5))
            self.assertEqual(result.status, FeedbackStatus.NOT_ELIGIBLE_EXECUTION)
            self.assertIsNone(result.evidence)
        tracking = evaluate_native_feedback(
            _execution(core, transition, status=ExecutionStatus.ACTION_EXECUTED_CAUSAL_TRACKING_FAILED),
            None, NFPFeedbackEvaluationConfig(0.5),
        )
        self.assertEqual(tracking.status, FeedbackStatus.CAUSAL_TRACKING_UNAVAILABLE)
        pending_execution = _execution(core, transition, status=ExecutionStatus.ACTION_EXECUTED_OBSERVATION_PENDING)
        pending = evaluate_native_feedback(pending_execution, None, NFPFeedbackEvaluationConfig(0.5))
        self.assertEqual(pending.status, FeedbackStatus.OBSERVATION_PENDING)
        completed = evaluate_native_feedback(pending_execution, transition, NFPFeedbackEvaluationConfig(0.5))
        self.assertEqual(completed.status, FeedbackStatus.HIT)

    def test_target_metadata_is_inert_to_effect_comparison(self) -> None:
        core = NFPFeedbackTargetCore.from_record(_record())
        changed_metadata = replace(
            core, source_support_count=99, source_proposal_id="proposal:inert",
            created_active_tick=999, created_at_world="2040-01-01T00:00:00Z",
        )
        transition = _transition()
        one = evaluate_native_feedback(_execution(core, transition), transition, NFPFeedbackEvaluationConfig(0.5))
        two = evaluate_native_feedback(_execution(changed_metadata, transition), transition, NFPFeedbackEvaluationConfig(0.5))
        self.assertEqual((one.status, one.effect_similarity), (two.status, two.effect_similarity))

    def test_ast_has_no_mutation_or_runtime_authority(self) -> None:
        forbidden = {
            "MemoryMutationPolicy", "ExpSMCommitWriter", "ExpSMUpdateWriter",
            "ExpSMStoreTransaction", "CLCRuntime", "_run_tick", "apply_native_feedback",
            "AKBSM", "Chronicle",
        }
        for source in PRODUCTION_SOURCES:
            tree = ast.parse(source.read_text(encoding="utf-8"))
            names = {
                alias.name.split(".")[-1]
                for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            names |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            self.assertFalse(names & forbidden, f"{source}: {names & forbidden}")
        runtime = (ROOT / "clc/runtime/clc_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("NFPFeedbackEvaluator", runtime)
        self.assertNotIn("evaluate_native_feedback", runtime)

    def test_scenario_contract(self) -> None:
        fixture = json.loads((ROOT / "scenarios/nfp_native_feedback_evaluation.json").read_text())
        cases = fixture["expect"]["nfp_native_feedback_evaluation"]["cases"]
        self.assertTrue(cases and all(cases.values()))
        self.assertTrue(fixture["expect"]["memory_unchanged"])


def main() -> int:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(NFPNativeFeedbackEvaluationTests)
    )
    if not result.wasSuccessful():
        return 1
    print("PASS: NFP-native Feedback continuity and pure evaluation")
    print("PASS: exact TargetCore propagation, signed comparison, and mutation isolation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
