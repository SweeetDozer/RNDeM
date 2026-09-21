from __future__ import annotations

import ast
import hashlib
import json
import sys
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.context.causal_transition import RecentCausalTransition
from clc.experience.effects import ObservedEffect, ObservedEffectExtractor, ObservedEffectSimilarity
from clc.experience.evidence import ExperienceEvidence, ExperienceEvidenceComparison, ExperienceEvidenceFactory
from clc.experience.grouping import (
    ExperienceEvidenceGrouper,
    ExperienceGroupingConfig,
    ExpSMConsolidationCandidate,
    ExpSMConsolidationProposal,
    GroupingStatus,
)
from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin, PatternTopology


SOURCE_FILES = (
    ROOT / "clc" / "experience" / "effects.py",
    ROOT / "clc" / "experience" / "evidence.py",
    ROOT / "clc" / "experience" / "grouping.py",
)
SCENARIO = ROOT / "scenarios" / "short_memory_expsm_evaluation.json"
EXPECTED_HASHES = {
    ROOT / "Memory" / "ExpSM" / "ExpSM_data.json": "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json": "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "clc.expsm", "clc.consolidation", "clc.action", "clc.runtime",
    "clc.evaluation", "clc.storage_models", "Memory",
)
FORBIDDEN_CALL_NAMES = {
    "ExpSMCommitWriter", "ExpSMUpdateWriter", "MemoryMutationWriter",
    "DecisionSelector", "ExpSMActivationModule", "ExpSMOutcomeFeedback",
    "increment_experience_hits", "increment_experience_misses", "_run_tick",
    "open", "write_text", "write_bytes", "dump", "dumps",
}
EXPECTED_CASES = {
    "observed_effect_extraction_signed_delta_and_zero",
    "effect_is_not_nfp_and_uses_endpoints_only",
    "effect_similarity_and_topology_compatibility",
    "experience_evidence_invariants",
    "context_action_effect_dimensions_are_independent",
    "matching_evidence_groups_with_unique_support",
    "divergent_effects_create_separate_candidates",
    "different_context_creates_separate_candidate",
    "different_action_creates_separate_candidate",
    "duplicate_evidence_is_idempotent",
    "ambiguous_grouping_does_not_mutate",
    "representative_is_real_first_evidence",
    "proposal_requires_explicit_eligible_request",
    "proposal_is_transient_and_non_authoritative",
    "support_is_not_hits_misses_or_confidence",
    "similar_active_expsm_record_is_unchanged",
    "debug_names_and_hidden_world_state_do_not_participate",
    "no_feedback_similarity_observer_activation_selector_or_writer_calls",
    "no_memory_akbsm_chronicle_or_runtime_writes",
}


def frame(
    frame_id: str, tick: int, values: tuple[float, ...], *, action: bool = False,
    debug_name: str | None = None,
) -> NFPFrame:
    return NFPFrame(
        frame_id,
        PatternModality.ACTION if action else PatternModality.VISUAL,
        PatternOrigin.ACTION_GENERATED if action else PatternOrigin.EXTERNAL_SENSORY,
        PatternTopology((len(values),)), values, tick,
        provenance_ref=f"occurrence:{frame_id}", debug_name=debug_name,
    )


def transition(
    identity: str,
    *,
    context_start: tuple[float, ...] = (0.2, 0.4, 0.6),
    before_endpoint: tuple[float, ...] = (0.4, 0.4, 0.4),
    action_values: tuple[float, ...] = (0.0, 1.0),
    after_endpoint: tuple[float, ...] = (0.6, 0.3, 0.4),
    action_tick: int = 2,
    debug_name: str | None = None,
) -> RecentCausalTransition:
    before = NFPWindow(
        f"before:{identity}",
        (frame(f"sensory:{identity}:1", action_tick - 1, context_start, debug_name=debug_name),
         frame(f"sensory:{identity}:2", action_tick, before_endpoint, debug_name=debug_name)),
        debug_name=debug_name,
    )
    after = NFPWindow(
        f"after:{identity}",
        (frame(f"sensory:{identity}:shared", action_tick, before_endpoint, debug_name=debug_name),
         frame(f"sensory:{identity}:3", action_tick + 1, after_endpoint, debug_name=debug_name)),
        debug_name=debug_name,
    )
    return RecentCausalTransition(
        f"transition:{identity}", before,
        frame(f"action:{identity}", action_tick, action_values, action=True, debug_name=debug_name),
        after, action_tick, action_tick + 1,
    )


def evidence(identity: str, **kwargs: object) -> ExperienceEvidence:
    return ExperienceEvidenceFactory.build(transition(identity, **kwargs))


def config(*, threshold: float = 0.9, min_support: int = 3) -> ExperienceGroupingConfig:
    return ExperienceGroupingConfig(threshold, threshold, threshold, min_support)


class ShortMemoryExpSMEvaluationTests(unittest.TestCase):
    def test_effect_validation_immutability_and_signed_arithmetic(self) -> None:
        item = evidence("signed", before_endpoint=(0.2, 0.8, 0.5), after_endpoint=(0.9, 0.1, 0.5))
        self.assertEqual(item.observed_effect.delta_values, (0.7, -0.7000000000000001, 0.0))
        self.assertNotIsInstance(item.observed_effect, (NFPFrame, NFPWindow))
        with self.assertRaises(FrozenInstanceError):
            item.observed_effect.action_tick = 8
        for changes in (
            {"effect_id": ""}, {"source_transition_id": ""}, {"delta_values": (0.0,)},
            {"delta_values": (1.1, 0.0, 0.0)}, {"delta_values": (float("nan"), 0.0, 0.0)},
            {"action_tick": -1}, {"observation_tick": item.action_tick + 2},
        ):
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                replace(item.observed_effect, **changes)

    def test_endpoint_only_and_zero_effect(self) -> None:
        zero = evidence("zero", before_endpoint=(0.3, 0.7), context_start=(0.0, 1.0),
                        after_endpoint=(0.3, 0.7))
        changed_history = evidence("zero-other-history", before_endpoint=(0.3, 0.7),
                                   context_start=(1.0, 0.0), after_endpoint=(0.3, 0.7))
        self.assertEqual(zero.observed_effect.delta_values, (0.0, 0.0))
        self.assertEqual(zero.observed_effect.delta_values, changed_history.observed_effect.delta_values)
        group = ExperienceEvidenceGrouper(config(threshold=1.0, min_support=2))
        self.assertEqual(group.observe(zero).status, GroupingStatus.CREATED)
        # Context remains independent, so changed shared history does not join at threshold 1.
        self.assertEqual(group.observe(changed_history).status, GroupingStatus.CREATED)

    def test_effect_similarity(self) -> None:
        base = evidence("base").observed_effect
        self.assertEqual(ObservedEffectSimilarity.compare(base, base).score, 1.0)
        zero = replace(base, effect_id="zero", delta_values=(0.0, 0.0, 0.0))
        self.assertEqual(ObservedEffectSimilarity.compare(zero, zero).score, 1.0)
        low = replace(base, effect_id="low", delta_values=(-1.0, -1.0, -1.0))
        high = replace(base, effect_id="high", delta_values=(1.0, 1.0, 1.0))
        self.assertEqual(ObservedEffectSimilarity.compare(low, high).score, 0.0)
        other_topology = ObservedEffect(
            "other", "transition:other", PatternModality.VISUAL, PatternTopology((1,)),
            (0.0,), "before", "after", 2, 3,
        )
        result = ObservedEffectSimilarity.compare(base, other_topology)
        self.assertFalse(result.comparable)
        self.assertIsNone(result.score)

    def test_evidence_invariants_and_dimension_reuse(self) -> None:
        first = evidence("e1")
        second = evidence("e2", after_endpoint=(0.61, 0.31, 0.4))
        comparison = ExperienceEvidenceComparison.compare(first, second)
        self.assertTrue(comparison.context_comparable)
        self.assertEqual(comparison.context_similarity, 1.0)
        self.assertEqual(comparison.action_similarity, 1.0)
        self.assertAlmostEqual(comparison.effect_similarity or 0.0, 0.9966666666666667)
        self.assertIs(first.context_window, first.context_window)
        self.assertFalse({"hits", "misses", "confidence", "success", "reward", "utility", "support_count"}
                         & {field.name for field in fields(ExperienceEvidence)})
        with self.assertRaises(FrozenInstanceError):
            first.observation_tick = 99
        for changes in (
            {"source_transition_id": "other"}, {"action_tick": 1}, {"observation_tick": 4},
            {"observed_effect": replace(first.observed_effect, action_tick=1, observation_tick=2)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(first, **changes)

    def test_matching_duplicate_and_real_representative(self) -> None:
        group = ExperienceEvidenceGrouper(config())
        first = evidence("match-1")
        second = evidence("match-2", after_endpoint=(0.61, 0.3, 0.4), action_tick=4)
        created = group.observe(first)
        added = group.observe(second)
        duplicate = group.observe(second)
        candidate = group.candidates[0]
        self.assertEqual((created.status, added.status, duplicate.status),
                         (GroupingStatus.CREATED, GroupingStatus.ADDED, GroupingStatus.DUPLICATE))
        self.assertEqual(candidate.support_count, 2)
        self.assertEqual(candidate.support_count, len(set(candidate.supporting_evidence_ids)))
        self.assertIs(candidate.representative_evidence, first)
        self.assertIsNone(group.make_proposal(candidate.candidate_id, current_tick=8))

    def test_divergent_context_and_action_each_split(self) -> None:
        base = evidence("base-split")
        similar = evidence("similar", after_endpoint=(0.61, 0.3, 0.4), action_tick=4)
        divergent = evidence("divergent", after_endpoint=(0.0, 1.0, 0.0), action_tick=6)
        group = ExperienceEvidenceGrouper(config(threshold=0.9))
        group.observe(base)
        group.observe(similar)
        group.observe(divergent)
        self.assertEqual([item.support_count for item in group.candidates], [2, 1])
        self.assertFalse({"hits", "misses", "confidence"} & {field.name for field in fields(ExpSMConsolidationCandidate)})

        context_group = ExperienceEvidenceGrouper(config(threshold=0.9))
        context_group.observe(base)
        context_group.observe(evidence("different-context", context_start=(1.0, 1.0, 1.0),
                                       before_endpoint=(1.0, 1.0, 1.0),
                                       after_endpoint=(1.0, 0.9, 1.0), action_tick=8))
        self.assertEqual(len(context_group.candidates), 2)

        action_group = ExperienceEvidenceGrouper(config(threshold=0.9))
        action_group.observe(base)
        action_group.observe(evidence("different-action", action_values=(1.0, 0.0), action_tick=8))
        self.assertEqual(len(action_group.candidates), 2)

    def test_ambiguous_grouping_is_non_mutating(self) -> None:
        group = ExperienceEvidenceGrouper(config(threshold=0.7))
        group.observe(evidence("amb-low", before_endpoint=(0.5,), context_start=(0.5,),
                               action_values=(0.5,), after_endpoint=(0.0,)))
        group.observe(evidence("amb-high", before_endpoint=(0.5,), context_start=(0.5,),
                               action_values=(0.5,), after_endpoint=(1.0,), action_tick=4))
        before = group.candidates
        result = group.observe(evidence("amb-middle", before_endpoint=(0.5,), context_start=(0.5,),
                                        action_values=(0.5,), after_endpoint=(0.5,), action_tick=6))
        self.assertEqual(result.status, GroupingStatus.AMBIGUOUS)
        self.assertEqual(len(result.eligible_candidate_ids), 2)
        self.assertEqual(group.candidates, before)

    def test_explicit_proposal_only_after_min_support(self) -> None:
        group = ExperienceEvidenceGrouper(config(min_support=3))
        evidence_items = [evidence(f"proposal-{index}", action_tick=2 * index + 2) for index in range(3)]
        candidate_id = group.observe(evidence_items[0]).candidate_id
        group.observe(evidence_items[1])
        self.assertIsNone(group.make_proposal(candidate_id or "", current_tick=10))
        group.observe(evidence_items[2])
        proposal = group.make_proposal(candidate_id or "", current_tick=11)
        self.assertIsInstance(proposal, ExpSMConsolidationProposal)
        self.assertEqual(proposal.support_count, 3)
        self.assertEqual(proposal.representative_evidence_id, evidence_items[0].evidence_id)
        self.assertEqual(proposal.created_active_tick, 11)
        with self.assertRaises(FrozenInstanceError):
            proposal.support_count = 4

    def test_debug_names_do_not_change_evaluation(self) -> None:
        left = evidence("debug", debug_name="move_right_success")
        right = ExperienceEvidenceFactory.build(replace(
            transition("debug", debug_name="wall_hit_failure"),
            before_sensory_window=replace(
                transition("debug", debug_name="wall_hit_failure").before_sensory_window,
                debug_name="other",
            ),
        ))
        self.assertEqual(left.observed_effect, right.observed_effect)
        self.assertEqual(ExperienceEvidenceComparison.compare(left, right),
                         ExperienceEvidenceComparison.compare(left, left))

    def test_active_expsm_shaped_record_is_untouched(self) -> None:
        active_record = {"id": "R", "hits": 7, "misses": 2, "confidence": 0.63,
                         "repeatability": 0.5, "if": ["pat_1"], "then": ["pat_2"]}
        before = json.loads(json.dumps(active_record))
        group = ExperienceEvidenceGrouper(config())
        group.observe(evidence("record-similar"))
        self.assertEqual(active_record, before)


def structural_safety() -> tuple[bool, str]:
    violations: list[str] = []
    for path in SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                imported = []
            for name in imported:
                if name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    violations.append(f"{path.name}: forbidden import {name}")
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else ""
                )
                if name in FORBIDDEN_CALL_NAMES:
                    violations.append(f"{path.name}: forbidden call {name}")
    runtime_source = (ROOT / "clc" / "runtime" / "clc_runtime.py").read_text(encoding="utf-8")
    for module_name in ("clc.experience.effects", "clc.experience.evidence", "clc.experience.grouping"):
        if module_name in runtime_source:
            violations.append(f"runtime imports {module_name}")
    return not violations, "; ".join(violations)


def fixture_contract() -> tuple[bool, str]:
    data = json.loads(SCENARIO.read_text(encoding="utf-8"))
    boundary = data.get("expect", {}).get("short_memory_expsm_evaluation", {})
    actual = {name for name, enabled in boundary.get("cases", {}).items() if enabled is True}
    missing = EXPECTED_CASES - actual
    ok = not missing and boundary.get("runtime_wiring") is False and boundary.get("permanent_writes") is False
    return ok, f"missing={sorted(missing)}" if missing else ""


def memory_hashes() -> tuple[bool, str]:
    actual = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in EXPECTED_HASHES}
    mismatches = [f"{path.name}: {actual[path]}" for path, expected in EXPECTED_HASHES.items() if actual[path] != expected]
    return not mismatches, "; ".join(mismatches)


def main() -> int:
    before_ok, before_detail = memory_hashes()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ShortMemoryExpSMEvaluationTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    checks = {
        "real implementation scenarios": (result.wasSuccessful(), f"tests={result.testsRun}"),
        "production structural isolation": structural_safety(),
        "scenario fixture contract": fixture_contract(),
        "real Memory hashes before": (before_ok, before_detail),
        "real Memory hashes after": memory_hashes(),
    }
    passed = True
    for label, (ok, detail) in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {label}" + (f" ({detail})" if detail else ""))
        passed = passed and ok
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
