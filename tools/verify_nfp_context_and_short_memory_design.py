from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_NAME = "design_nfp_context_and_short_memory.md"
REFERENCES = (
    "README.md",
    "docs/natural_pattern_data_contract.md",
    "docs/design_first_closed_loop_action_consequence.md",
    "docs/current_architecture_checkpoint.md",
    "docs/project_hygiene_audit.md",
)

# Documentation contract checks do not prove future runtime behavior.
REQUIREMENTS = {
    "Existing ContextMemory Audit": (
        "clc/context/context_memory.py", "clc/context/context_memory_manager.py",
        "clc/context/context_ops_pool.py", "clc/context/context_retention_policy.py",
        "clc/core/nfp.py", "clc/runtime/context_temporary_metadata.py",
        "clc/field/active_context_field.py", "not only temporary metadata",
        "No NFP-native ShortMemory implementation was found",
    ),
    "Architecture Decision": (
        "Reuse/evolve ContextMemoryManager: yes",
        "No parallel duplicate ContextMemory architecture",
        "Context Memory = active present", "Short Memory = bounded recent past",
        "no separate ExperienceCapture memory subsystem",
        "ExperienceCaptureMemory", "ExperienceCaptureStore",
        "TransitionMemory", "EpisodeMemory",
        "not a parallel top-level manager",
        "shared module workspace is an exchange mechanism",
    ),
    "Active Present And Provenance": (
        "Presence does not imply", "External and internal material may coexist",
        "INTERNAL_REACTIVATION cannot satisfy an awaited external consequence",
        "NFPWindow is a pattern structure, not a memory layer",
        "Window overlap is allowed",
    ),
    "Pending Transition And Qualification": (
        "PendingCausalTransition is current-state data stored in Context Memory, not a memory subsystem",
        "expected_observation_tick = action_tick + 1",
        "before_sensory_window.end_tick <= action_tick",
        "strict immediate T -> T+1 model requires equality",
        "ACTION + INTERNAL_REACTIVATION cannot open an executable/pending transition",
        "every frame has origin EXTERNAL_SENSORY",
        "after_sensory_window.end_tick == expected_observation_tick",
        "at most one immediate pending transition", "never silently overwrite",
        "delayed credit assignment is deferred",
    ),
    "Lifecycle And Missing Evidence": (
        "transfers it once into Short Memory", "Context clears pending state",
        "bounded active-time deadline", "it does not mean action failed",
        "Do not fabricate a completed record",
    ),
    "Completed Transition And Short Memory": (
        "RecentCausalTransition is an immutable data record inside Short Memory",
        "before_sensory_window", "action_frame", "after_sensory_window",
        "action_tick", "observation_tick",
        "Before/action/after remain non-semantic raw material",
        "not proof that the action caused all differences",
        "Neither Context nor Short Memory may store hidden world state",
        "Human debug/semantic names do not define transition identity",
    ),
    "Retention And Permanent Memory Boundaries": (
        "deterministic active-time retention", "max_entries", "max_age_ticks",
        "no wall-clock aging", "Eviction does not imply consolidation",
        "No ExpSM write", "No AKBSM write", "No chronicle write",
    ),
    "Old Temporary Metadata Relationship": (
        "Old temporary metadata remains non-authoritative",
        "diagnostic/scaffold bounded",
        "metadata must never complete a pending transition",
    ),
    "Proposed Isolated Harness And Required Scenarios": (
        "No runtime wiring", "no _run_tick integration", "no permanent Memory writes",
        "Strong epistemic-integrity test", "Short unchanged",
        "Strong memory-layer test", "only in Context",
        "Short contains the completed raw transition",
    ),
    "Deferred Scope And Safety": (
        "delayed consequences", "credit assignment", "reward/pain evaluation",
        "success/failure evaluation", "ExpSM consolidation", "AKBSM consolidation",
        "chronicle consolidation", "long-term NFP persistence", "No runtime behavior",
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
        body = sections.get(title, "")
        for clause in clauses:
            if clause not in body:
                failures.append(f"{title}: missing {clause!r}")
    for relative in REFERENCES:
        reference = ROOT / relative
        if not reference.exists() or DOC_NAME not in reference.read_text(encoding="utf-8"):
            failures.append(f"missing design reference: {relative}")
    print("NFP Context and Short Memory design verification:")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"PASS: {len(REQUIREMENTS)} design sections and {len(REFERENCES)} references")
    print("Documentation contract only; future implementation scenarios remain required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
