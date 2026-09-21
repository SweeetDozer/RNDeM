from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_NAME = "design_persistent_nfp_expsm_representation.md"
REFERENCES = (
    "README.md",
    "docs/natural_pattern_data_contract.md",
    "docs/design_short_memory_to_expsm_boundary.md",
    "docs/current_architecture_checkpoint.md",
    "docs/project_hygiene_audit.md",
)

# Documentation clauses only; no parser, adapter, request or writer is executed.
REQUIREMENTS = {
    "Current Persistent ExpSM Audit": (
        "Memory/ExpSM/ExpSM_data.json", "no file-level schema/version field",
        "IDs are external map keys", "Memory/ExpSM/Exp_CRUD.py",
        "clc/storage_models/expsm_adapter.py", "clc/expsm/expsm_similarity_observer.py",
        "clc/expsm/expsm_activation_module.py", "clc/expsm/expsm_mechanism_search.py",
        "clc/expsm/expsm_outcome_feedback.py", "clc/evaluation/value_feedback_memory_view.py",
        "clc/consolidation/expsm_commit_writer.py", "clc/consolidation/expsm_update_writer.py",
        "clc/evaluation/value_feedback_update_writer.py", "no authoritative persistent schema validator",
        "safe_demo", "draft_only", "mutating_memory", "not a universal filesystem sandbox",
    ),
    "Representation Decision": (
        "Compatibility decision B is preserved", "record_kind = \"nfp_native\"",
        "representation_version = 1", "classified explicitly as `legacy`",
        "Any partially tagged record is malformed", "field presence",
        "No file-level version is required for Stage 1", "Record-level discrimination is mandatory",
    ),
    "Serialized Cognitive Values": (
        "SerializedNFPFrameV1", "SerializedNFPWindowV1", "SerializedObservedEffectV1",
        "not arbitrary", "dataclasses.asdict()", "No pickle", "Python repr",
        "finite and in [0,1]", "[-1,1]", "Action modality must be ACTION",
        "No quantization", "JSON spelling is not record identity",
    ),
    "Field Decisions": (
        "frame_id/window_id/effect_id/evidence_id", "exclude from canonical pattern",
        "original active_tick/action_tick/observation_tick", "debug_name", "exclude",
        "hidden world state/semantic labels", "Do not persist all RecentCausalTransition objects",
        "source_support_count", "must not participate in pattern matching",
    ),
    "NFP-Native Record V1": (
        "NFPExpSMRecordV1", "context_pattern", "action_pattern", "effect_pattern",
        "hits", "misses", "confidence", "repeatability", "source_support_count",
        "legacy_crud_defaults_v1", "not an implemented formula",
        "source_support_count` never initializes hits", "future single authoritative writer",
        "never memory addresses/debug labels/content hashes", "global content deduplication is prohibited",
        "first real representative evidence",
    ),
    "Version-Aware Adapter And Load Validation": (
        "ExpSMRecordAdapter", "LegacyOperationalRecord", "NFPNativeOperationalRecordV1",
        "UnsupportedRecord", "MalformedRecord", "unknown version -> Unsupported",
        "Never downgrade", "nonnegative integer hits/misses", "Malformed NFP-native records",
        "Round trip", "fresh parse after original objects are discarded",
        "does not require Python object identity", "debug-name round trip",
    ),
    "Legacy Coexistence And Migration": (
        "Stage 0", "Stage 1", "Stage 2", "Stage 3",
        "never eagerly rewrite legacy records", "Do not alter their IDs",
        "Do not derive activations from debug names/semantic strings",
        "record remains legacy indefinitely", "neither rewritten nor reinterpreted",
    ),
    "Operational Comparability And Competition": (
        "Current SimilarityObserver", "typed comparator dispatch",
        "Legacy <-> NFP-native is non-comparable in V1", "Human labels/debug names are never a bridge",
        "Activation remains top-N", "Different recurring effects are not collapsed",
        "DecisionSelector remains the only operational selection stage",
        "No NFPDecisionSelector or ConsolidationSelector", "Feedback remains record-ID scoped",
        "No neighbor/group update", "no unused-record punishment",
    ),
    "Proposal To Creation Request": (
        "ExpSMRecordCreationRequest", "deterministic representation builder",
        "MemoryMutationPolicy", "Threshold and eviction trigger none",
        "no live NFP/effect/candidate/proposal/ShortMemory reference",
        "proposal valid; representation serializable; schema valid; review approved; policy permits; writer commits",
        "allow_expsm_commit=False", "Prefer a version-aware representation adapter",
        "writer implementation", "First implement representation, then mutation",
    ),
    "Required Future Scenarios": (
        "Full restart round trip", "unknown version fails unsupported",
        "Legacy L and native N coexist", "Equal serialized patterns under distinct record IDs",
        "hits/misses remain 0", "leaves ExpSM bytes unchanged",
        "SimilarityObserver typed boundary", "Activation top-N", "DecisionSelector",
        "No eager migration", "AKBSM/Chronicle writes", "`_run_tick` integration",
    ),
    "Deferred Scope And Safety": (
        "actual writer support", "schema migration execution", "initial confidence policy changes",
        "cross-representation learned similarity", "runtime wiring",
        "No ExpSM, AKBSM or Chronicle write is authorized",
    ),
}


def main() -> int:
    path = ROOT / "docs" / DOC_NAME
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    sections: dict[str, str] = {}
    preamble, _, _ = text.partition("\n## ")
    sections["Representation Decision"] = " ".join(preamble.split())
    for block in text.split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        normalized = " ".join(body.split())
        if title == "Representation Decision":
            sections[title] += " " + normalized
        else:
            sections[title] = normalized
    failures: list[str] = []
    for title, clauses in REQUIREMENTS.items():
        body = sections.get(title, "")
        for clause in clauses:
            if clause not in body:
                failures.append(f"{title}: missing {clause!r}")
    for relative in REFERENCES:
        reference = ROOT / relative
        if not reference.exists() or DOC_NAME not in reference.read_text(encoding="utf-8"):
            failures.append(f"missing design reference: {relative}")
    print("Persistent NFP-native ExpSM representation design verification:")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"PASS: {len(REQUIREMENTS)} design sections and {len(REFERENCES)} references")
    print("Documentation contract only; no persistent representation or write executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
