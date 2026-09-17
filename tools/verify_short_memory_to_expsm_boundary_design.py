from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_NAME = "design_short_memory_to_expsm_boundary.md"
REFERENCES = (
    "README.md",
    "docs/natural_pattern_data_contract.md",
    "docs/design_nfp_context_and_short_memory.md",
    "docs/current_architecture_checkpoint.md",
    "docs/project_hygiene_audit.md",
)

# This checks the documented boundary, not an unimplemented runtime contract.
REQUIREMENTS = {
    "Existing ExpSM Audit": (
        "Memory/ExpSM/Exp_CRUD.py", "clc/storage_models/expsm_adapter.py",
        "clc/expsm/expsm_similarity_observer.py", "top-N, N=3",
        "clc/action/decision_selector.py", "clc/expsm/expsm_outcome_feedback.py",
        "clc/consolidation/expsm_commit_writer.py",
        "clc/consolidation/expsm_update_writer.py",
        "clc/expsm/expsm_mechanism_search.py",
        "map keys are record IDs", "hits, misses",
        "target = .60 * (1 - exp(-h / 20)) * h / max(1, h+m)",
        "new_confidence = clamp(.75 * min(old_confidence, .75) + .25 * target, 0, .75)",
        "safe_demo", "draft_only", "mutating_memory",
        "not themselves guarded", "fallback",
    ),
    "Representation Decision": (
        "Decision B", "controlled extension/migration",
        "SimilarityObserver is not directly reusable",
        "Activation returns top-N; DecisionSelector selects one",
        "not a parallel selector", "No migration or adapter is implemented",
    ),
    "Distinct Stages": (
        "RecentCausalTransition != ObservedEffect != ExperienceEvidence != ExpSMConsolidationCandidate != active ExpSM record",
        "One occurrence never automatically becomes learned operational memory",
        "Eviction never triggers consolidation",
    ),
    "ObservedEffect And Extraction": (
        "immutable ObservedEffect", "effect_id, source_transition_id",
        "delta_values", "before_endpoint_ref", "after_endpoint_ref",
        "ObservedEffect is not NFPFrame", "not semantic evaluation",
        "[0,1]", "[-1,1]", "final frame of each window",
        "same modality, equal topology, same activation length",
        "EXTERNAL_SENSORY", "delta[i] = after_endpoint.values[i] - before_endpoint.values[i]",
        "Do not subtract whole overlapping windows",
        "Zero-delta effect is valid", "NOT failure, blocked, bad",
    ),
    "ExperienceEvidence": (
        "immutable fields: evidence_id, source_transition_id, context_window",
        "context_window = transition.before_sensory_window",
        "action_frame = transition.action_frame",
        "observed_effect.source_transition_id = transition.transition_id",
        "no hit, miss, success, failure, reward, utility or confidence",
        "must not inflate support",
    ),
    "Three Independent Similarities": (
        "Context similarity uses NFPWindowSimilarity",
        "Action similarity uses NFPFrameSimilarity", "ACTION frames",
        "effect_similarity = 1.0 - mean(abs(delta_a[i] - delta_b[i])) / 2.0",
        "comparable = False", "not implemented here",
        "Similar context != same entity", "similar action != same action occurrence",
        "similar effect != identical world meaning",
    ),
    "Grouping And Candidates": (
        "ExperienceEvidenceGrouper is non-authoritative in-memory",
        "context threshold AND action threshold AND effect threshold",
        "explicit configuration", "No weighted mega-score",
        "divergent effects retains separate groups/candidates",
        "Different context must not merge", "different action must not merge",
        "one real supporting evidence item", "No averaged synthetic sensory NFP",
        "supporting_evidence_ids", "first_observation_tick", "last_observation_tick",
        "support_count != hits; support_count != confidence",
        "Reaching min_support never auto-writes ExpSM",
    ),
    "Proposal And Feedback Separation": (
        "ExpSMConsolidationProposal", "source_evidence_ids, created_active_tick",
        "Non-authoritative, non-persistent by default, not active ExpSM",
        "PATH A: observational consolidation", "PATH B: selected/actually used",
        "ShortMemory evidence does not mutate existing ExpSM records",
        "Unused similar ExpSM records are not punished",
        "Candidate B support=2; Candidate C support=1. NOT B hits=2, misses=1",
        "leave R.hits, R.misses and R.confidence unchanged",
        "That is not ShortMemory consolidation",
    ),
    "Persistence And Memory Boundaries": (
        "NFP persistence/serialization is unresolved", "versioned serialized",
        "Do not dump arbitrary Python/dataclass structures into JSON",
        "Never persist Python object id, process-local memory address, live object reference or ShortMemory container reference",
        "No ExpSM writes", "No AKBSM writes", "ExpSM candidate != AKBSM fact",
        "No Chronicle/Letopis writes", "No root Memory mutation",
        "separate from raw ShortMemory retention",
    ),
    "Isolated Implementation And Future Scenarios": (
        "No _run_tick integration", "ShortMemory.remember()", "ShortMemory.prune()",
        "No ExpSM writer", "Required future executable scenarios",
        "effect is not NFPFrame", "min_support does not auto-write",
        "Unused similar R retains hits/misses/confidence",
    ),
    "Deferred Scope": (
        "Actual ExpSM writer", "schema migration", "initial confidence",
        "credit assignment", "delayed effects", "multi-action chains",
        "automatic background consolidation", "sleep/offline consolidation",
    ),
}


def main() -> int:
    path = ROOT / "docs" / DOC_NAME
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    sections = {}
    for block in text.split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        sections[title] = " ".join(body.split())
    failures = []
    for title, clauses in REQUIREMENTS.items():
        for clause in clauses:
            if clause not in sections.get(title, ""):
                failures.append(f"{title}: missing {clause!r}")
    for relative in REFERENCES:
        reference = ROOT / relative
        if not reference.exists() or DOC_NAME not in reference.read_text(encoding="utf-8"):
            failures.append(f"missing design reference: {relative}")
    print("ShortMemory to ExpSM boundary design verification:")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"PASS: {len(REQUIREMENTS)} design sections and {len(REFERENCES)} references")
    print("Documentation contract only; no effect extraction, grouping or writes executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
