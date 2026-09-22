from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design_nfp_expsm_mutation_path.md"
REFERENCES = (
    ROOT / "README.md",
    ROOT / "docs" / "design_persistent_nfp_expsm_representation.md",
    ROOT / "docs" / "design_short_memory_to_expsm_boundary.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "project_hygiene_audit.md",
)


REQUIREMENTS = {
    "current writer and policy audit": (
        "## Actual Current Writer And Store Audit",
        "`ExpSMCommitWriter` owns runtime legacy ID allocation",
        "There is no lock, process-wide",
        "`Path.replace`",
        "no file or directory fsync",
        "`Memory/ExpSM/Exp_CRUD.py` independently",
        "## Actual Mutation-Policy And Draft Audit",
        "`safe_demo`",
        "`draft_only`",
        "`mutating_memory`",
        "The existing legacy draft subsystem remains unchanged",
    ),
    "authority and validation separation": (
        "## Authority Separation",
        "request creation != permission",
        "persistence mechanism != operational activation",
        "## Request Validation Boundary",
        "before policy evaluation",
        "Schema validation and policy authorization are distinct",
        "no final record_id",
        "Unknown representation versions never reach mutation",
    ),
    "canonical writer and legacy preservation": (
        "## Canonical Writer Extension",
        "Choose option C",
        "common ExpSM store transaction",
        "not a parallel writer/database",
        "Legacy `ExpSMCommitWriter` remains canonical",
        "Native CREATE is the only new mutation",
    ),
    "identity and materialization": (
        "## Writer-Owned ID And Materialization",
        "max(numeric experience IDs) + 1",
        "Given IDs 1, 2 and 7, the new ID",
        "`request_id != record_id`",
        "two IDs and two records",
        "not a dedupe key",
        "never searches SimilarityObserver",
    ),
    "counter and provenance separation": (
        "hits=0, misses=0, confidence=.5",
        "`source_support_count` remains creation provenance",
        "never hits",
        "immutable creation history",
    ),
    "mixed store and migration": (
        "## Mixed Store And Compatibility",
        "existing top-level `experience` map beside legacy",
        "No eager migration",
        "Legacy records remain",
        "No separate native list",
        "STORE_INVALID",
    ),
    "atomic failure decision": (
        "## Atomicity And Failure Safety",
        "unique sibling temp",
        "`os.fsync`",
        "`os.replace`",
        "old destination",
        "controlled replace/write failure test",
        "Do not route native creation through direct `ExpSMCRUD.save()`",
    ),
    "result model and denial": (
        "## Mutation Result Model",
        "CREATED",
        "DENIED_BY_POLICY",
        "INVALID_REQUEST",
        "UNSUPPORTED_REPRESENTATION",
        "STORE_INVALID",
        "WRITE_FAILED",
        "READBACK_FAILED",
        "Only confirmed `CREATED` returns ID and record",
    ),
    "post-replace readback recovery": (
        "`WRITE_FAILED` and `READBACK_FAILED` belong to opposite sides",
        "READBACK_FAILED:** atomic replace completed successfully",
        "INDETERMINATE_FROM_CALLER_PERSPECTIVE",
        "may already exist authoritatively on disk",
        "not equivalent to \"nothing was written\"",
        "MUST NOT automatically retry",
        "retry could allocate a second writer-owned ID",
        "attempted_record_id",
        "never substituted for `record_id`",
        "## READBACK_FAILED Recovery",
        "reopen the target ExpSM store through a fresh read path",
        "CONFIRMED_PERSISTED",
        "CONFIRMED_ABSENT",
        "UNRESOLVED_OR_STORE_INVALID",
        "recovery/reconciliation state, not a transactional rollback state",
        "must not resubmit or create a second record",
    ),
    "strong isolated scenarios": (
        "## Required Isolated Scenarios",
        "**Safe mode:**",
        "**Draft mode:**",
        "**Authoritative create:**",
        "**Legacy preservation:**",
        "**ID gap:**",
        "**Malformed/unsupported:**",
        "**Write failure:**",
        "**Forced post-replace readback failure:**",
        "**READBACK_FAILED recovery:**",
        "**Readback/restart:**",
        "temporary directory and copied",
    ),
    "behavior and memory isolation": (
        "## Operational And Memory Boundaries",
        "SimilarityObserver is unchanged",
        "Activation top-N receives no native candidate",
        "DecisionSelector sees no new action",
        "Feedback performs no native update",
        "`_run_tick()` remain",
        "No AKBSM or Chronicle write",
    ),
    "deferred and next implementation": (
        "## First Implementation And Deferred Scope",
        "typed request validator",
        "policy-gated create orchestration",
        "writer-owned ID",
        "temporary-store atomic failure tests",
        "normal runtime wiring",
        "cross-process locking",
    ),
}


def main() -> int:
    failures: list[str] = []
    if not DESIGN.exists():
        print(f"FAIL: missing {DESIGN.relative_to(ROOT)}")
        return 1
    text = DESIGN.read_text(encoding="utf-8")
    normalized = " ".join(text.lower().split())
    for label, clauses in REQUIREMENTS.items():
        missing = [clause for clause in clauses if " ".join(clause.lower().split()) not in normalized]
        if missing:
            failures.append(f"{label}: missing {missing}")
    for path in REFERENCES:
        if not path.exists():
            failures.append(f"missing reference file {path.relative_to(ROOT)}")
            continue
        reference = path.read_text(encoding="utf-8")
        if "design_nfp_expsm_mutation_path.md" not in reference:
            failures.append(f"{path.relative_to(ROOT)} does not reference mutation design")
    if failures:
        print("Policy-gated NFP-native ExpSM mutation design verification:")
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Policy-gated NFP-native ExpSM mutation design verification:")
    print(f"PASS: {len(REQUIREMENTS)} design sections and {len(REFERENCES)} references")
    print("Documentation contract only; no writer, policy, runtime, or Memory mutation implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
