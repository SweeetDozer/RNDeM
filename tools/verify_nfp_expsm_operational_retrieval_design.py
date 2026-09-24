from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design_nfp_expsm_operational_retrieval.md"
SIMILARITY = ROOT / "clc" / "expsm" / "expsm_similarity_observer.py"
ACTIVATION = ROOT / "clc" / "expsm" / "expsm_activation_module.py"
NFP_SIMILARITY = ROOT / "clc" / "patterns" / "similarity.py"
SELECTOR = ROOT / "clc" / "action" / "decision_selector.py"
PROPOSER = ROOT / "clc" / "action" / "action_proposer.py"
FEEDBACK = ROOT / "clc" / "expsm" / "expsm_outcome_feedback.py"


REQUIRED_SECTIONS = (
    "## Actual SimilarityObserver Audit",
    "## Actual NFP Similarity Audit",
    "## Actual Activation And Top-N Audit",
    "## Actual Action Candidate And Scoring Audit",
    "## Actual DecisionSelector Audit",
    "## Current Selected-Record And Feedback Identity Flow",
    "## Retrieval Semantics",
    "## Retrieval Query And Authority",
    "## Live/Persistent Comparator",
    "## Read-Only Retriever And Store Policy",
    "## Retrieval Result And Candidate Contracts",
    "## SimilarityObserver Extension Decision",
    "## Activation Compatibility Decision",
    "## DecisionSelector Compatibility Decision",
    "## Action And Effect Boundaries",
    "## Read-Only And Runtime Boundaries",
    "## Required Isolated Scenarios",
)

CONTRACT_GROUPS = {
    "similarity architecture": (
        "same `ExpSMSimilarityObserver` stage",
        "legacy pair threshold `.45`",
        "different four-field Jaccard quantity",
        "NFPWindowSimilarity.compare(A, B).score",
        "comparable=False, score=None",
        "different_frame_count",
    ),
    "retrieval semantics": (
        "current context only",
        "Stored ACTION is not a query key",
        "Stored effect is not a query key",
        "prediction/consequence metadata",
        "PatternOrigin.EXTERNAL_SENSORY",
        "INTERNAL_REACTIVATION",
        "query authority gate",
        "never creates fake historical",
        "valid legacy: recognized, supported, non-comparable",
        "UNSUPPORTED_MEMORY_PRESENT",
    ),
    "Activation mapping": (
        "native Activation coverage := context_similarity",
        "coverage = context_similarity",
        "coverage      * 0.55",
        "confidence    * 0.20",
        "repeatability * 0.15",
        "viability     * 0.10",
        "viability = (hits + 1) / (hits + misses + 2)",
        "excludes ACTION similarity, effect similarity, effect magnitude",
        "`source_support_count`, and creation provenance",
        "top-N = 3",
    ),
    "identity semantics": (
        "Candidate/pattern identity is not persistent ExpSM record identity",
        "persistent NFP-native record_id",
        "retrieval candidate source_experience_id or typed equivalent",
        "-> Activation candidate",
        "-> DecisionSelector input",
        "-> selected operational-experience result",
        "persistent source ID survives every step unchanged",
        "different persistent `record_id` produces distinct retrieval candidates",
        "no content deduplication, context deduplication",
        "action deduplication, effect deduplication, or candidate collapsing",
        "Multiple similar NFP-native records may coexist in Activation competition",
        "not merged into an averaged or representative memory",
    ),
    "DecisionSelector boundary": (
        "existing `DecisionSelector`",
        "SelectedNFPExpSMExperience",
        "record_id (exact persistent identity)",
    ),
    "Feedback deferral": (
        "Feedback remains deferred",
        "native Feedback mutation is deferred",
        "future native Feedback updates only the selected/used persistent record",
        "Content lookup, similarity-neighbor lookup, group feedback, and all-top-N feedback are forbidden",
        "top-N but not selected record receives no miss increment merely because it lost selection",
        "Selection alone is not behavioral feedback",
    ),
    "read-only authority": (
        "strictly `read -> parse -> compare -> rank -> select`",
        "never `mutate -> commit -> update`",
        "must not import or call `MemoryMutationPolicy`",
        "`ExpSMCommitWriter`, `ExpSMUpdateWriter`, `ExpSMStoreTransaction`",
        "future real retrieval verifier must AST/import/call-audit",
        "does not claim to audit retrieval source that does not yet exist",
    ),
    "future guard obligation": (
        "Action materialization is deferred",
        "future materialized executable ACTION must",
        "appropriate action guard before world execution",
        "retrieval or selection must not bypass guard semantics",
        "does not participate in context similarity, retrieval candidate production, or Activation scoring",
        "does not alter context retrieval similarity",
    ),
    "runtime isolation": (
        "no `_run_tick()`",
        "no AKBSM or",
        "Chronicle/Letopis",
    ),
}

REQUIRED_REFERENCES = (
    "clc/expsm/expsm_similarity_observer.py",
    "NFPWindowSimilarity",
    "ExpSMActivationModule",
    "ActionProposer._propose_expsm_actions()",
    "action_scoring.score_breakdown()",
    "DecisionSelector.select()",
    "ModeActionGuard",
    "ExpSMOutcomeFeedback",
    "ExpSMRecordAdapter",
)


def _constant(path: Path, name: str) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"missing constant {name} in {path}")


def _changed_files() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "main"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    paths = {line for line in result.stdout.splitlines() if line}
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    paths.update(line[3:] for line in status.stdout.splitlines() if len(line) > 3)
    return tuple(sorted(paths))


def main() -> int:
    failures: list[str] = []
    text = DESIGN.read_text(encoding="utf-8") if DESIGN.exists() else ""
    lower = " ".join(text.lower().split())

    for section in REQUIRED_SECTIONS:
        if section not in text:
            failures.append(f"missing section: {section}")
    contract_count = 0
    for group, terms in CONTRACT_GROUPS.items():
        for term in terms:
            contract_count += 1
            if " ".join(term.lower().split()) not in lower:
                failures.append(f"missing {group} contract: {term}")
    for reference in REQUIRED_REFERENCES:
        if reference not in text:
            failures.append(f"missing factual reference: {reference}")

    facts = {
        "similarity_threshold": _constant(SIMILARITY, "MIN_SIMILARITY_SCORE") == 0.45,
        "similarity_group_cap": _constant(SIMILARITY, "MAX_GROUPS_PER_RUN") == 5,
        "activation_threshold": _constant(ACTIVATION, "ACTIVE_THRESHOLD") == 0.25,
        "activation_match_threshold": _constant(ACTIVATION, "MIN_MATCH_SCORE") == 0.35,
        "activation_top_n": _constant(ACTIVATION, "MAX_ACTIVATIONS_PER_TICK") == 3,
        "selector_snapshot_cap": _constant(SELECTOR, "MAX_DECISION_AUDIT_CANDIDATES") == 9,
    }
    for name, passed in facts.items():
        if not passed:
            failures.append(f"current source fact drifted: {name}")

    source_contracts = {
        "legacy_similarity_fields": all(
            token in SIMILARITY.read_text(encoding="utf-8")
            for token in ("if_similarity * 0.45", "then_similarity * 0.30", "result_similarity * 0.20", "recommendation_similarity * 0.05")
        ),
        "native_similarity_noncomparable": all(
            token in NFP_SIMILARITY.read_text(encoding="utf-8")
            for token in ("different_modality", "different_topology", "different_frame_count")
        ),
        "activation_formula": all(
            token in ACTIVATION.read_text(encoding="utf-8")
            for token in ("coverage * 0.55", "effective_confidence * 0.20", "repeatability * 0.15", "viability * 0.10")
        ),
        "selector_identity": all(
            token in SELECTOR.read_text(encoding="utf-8")
            for token in ("source_experience_id", "source_activation_id", "expsm_candidate_snapshot")
        ),
        "proposer_requires_then_patterns": "activation.get(\"then_patterns\"" in PROPOSER.read_text(encoding="utf-8"),
        "feedback_uses_exact_identity": all(
            token in FEEDBACK.read_text(encoding="utf-8")
            for token in ("source_experience_id", "source_activation_id", "experience_id")
        ),
    }
    for name, passed in source_contracts.items():
        if not passed:
            failures.append(f"source contract not proven: {name}")

    changed = _changed_files()
    allowed = {
        "README.md",
        "docs/design_nfp_expsm_operational_retrieval.md",
        "docs/design_persistent_nfp_expsm_representation.md",
        "docs/design_nfp_expsm_mutation_path.md",
        "docs/design_short_memory_to_expsm_boundary.md",
        "docs/current_architecture_checkpoint.md",
        "docs/debug_name_dependency_audit.json",
        "docs/debug_name_dependency_audit.md",
        "docs/project_hygiene_audit.md",
        "tools/verify_nfp_expsm_operational_retrieval_design.py",
        "clc/action/decision_selector.py",
        "clc/expsm/expsm_activation_module.py",
        "clc/expsm/expsm_similarity_observer.py",
        "clc/expsm/nfp_operational_retrieval.py",
        "scenarios/nfp_expsm_operational_retrieval.json",
        "tools/verify_nfp_expsm_operational_retrieval.py",
        "docs/design_nfp_action_materialization_guarded_execution.md",
        "docs/design_first_closed_loop_action_consequence.md",
        "docs/design_nfp_context_and_short_memory.md",
        "tools/verify_nfp_action_materialization_guarded_execution_design.py",
        "clc/actuation/__init__.py",
        "clc/actuation/remembered_action_execution.py",
        "clc/system/mode_action_guard.py",
        "scenarios/nfp_remembered_action_guarded_execution.json",
        "tools/verify_nfp_remembered_action_guarded_execution.py",
        "tools/verify_first_closed_loop_action_consequence.py",
    }
    unexpected = sorted(set(changed) - allowed)
    if unexpected:
        failures.append(f"unexpected design-pass files: {unexpected}")

    if failures:
        print("NFP-native ExpSM operational retrieval design verification: FAIL")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("NFP-native ExpSM operational retrieval design verification:")
    print(f"PASS: {len(REQUIRED_SECTIONS)} design sections, {contract_count} grouped contracts, and {len(REQUIRED_REFERENCES)} source references")
    print("PASS: current SimilarityObserver, Activation/top-N, DecisionSelector, and feedback identity facts")
    print("Design boundary verified; isolated retrieval is allowed, with no runtime wiring, action execution, feedback mutation, or memory write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
