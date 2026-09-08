from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_akbsm_proposal_contextmemory_metadata_integration.md"
DOC_REFERENCE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md",
    ROOT / "docs" / "adr_akbsm_draft_proposal_transition_controller_experiment.md",
    ROOT / "docs" / "design_akbsm_draft_proposal_review_lifecycle_implementation.md",
)

STATUS_TERMS = (
    "This ADR is design-only",
    "No ContextMemory integration is implemented by this pass",
    "No proposal storage is added by this pass",
    "No review record persistence is added by this pass",
    "No AKBSM write path is added by this pass",
)

NO_IMPLEMENTATION_TERMS = (
    "must not run in normal runtime by default",
    "must not persist proposals",
    "must not persist review records",
    "must not create permanent proposal queues",
    "must not write AKBSM or ExpSM",
)

TEMPORARY_SCOPE_TERMS = (
    "temporary metadata copies of AKBSM proposal review records",
    "scenario/test-only",
    "ContextMemory metadata only, not primary memory data",
    "temporary side-list or metadata bucket",
)

ALLOWED_SHAPE_TERMS = (
    "proposal id/reference metadata",
    "lifecycle state",
    "created_tick",
    "updated_tick",
    "ttl_ticks",
    "expires_at_tick",
    "review_reason",
    "review_notes",
    "transition_history metadata",
    "controller result metadata",
    "source = akbsm_proposal_lifecycle",
    "temporary = true",
)

FORBIDDEN_DATA_TERMS = (
    "full permanent AKBSM association writes",
    "new relation types",
    "new concepts",
    "ExpSM records",
    "writer commands",
    "commit/apply/save/write/persist/mutate instructions",
    "behavior/scoring/guard instructions",
    "Mode C instructions",
    "PolicyPressureReview instructions",
)

AUTHORITY_TERMS = (
    "explicit scenario/test harness only",
    "normal runtime default path",
    "_run_tick()",
    "PolicyPressureReview",
    "Mode C",
    "DecisionSelector",
    "ActionScoring",
    "ActionProposer",
    "ModeActionGuard",
    "ValueFeedback",
    "ExpSM writers/update paths",
    "memory writers",
    "AKBSM writers/save paths",
)

RETENTION_TERMS = (
    "TTL/expiration semantics",
    "Expired metadata must be removable by normal temporary retention cleanup",
    "Expired metadata must not trigger AKBSM writes",
    "Expired metadata must not trigger controller transitions",
    "Expired metadata must not become permanent memory",
)

REJECTED_TERMS = (
    "permanent proposal queue",
    "ContextMemory metadata created by normal runtime by default",
    "ContextMemory metadata treated as write approval",
    "accepted_for_observation` triggering AKBSM writes",
    "deferred` treated as pending commit",
    "PolicyPressureReview-controlled ContextMemory metadata",
    "Mode C-controlled ContextMemory metadata",
    "DecisionSelector/ActionScoring reading proposal metadata for behavior",
    "storing full AKBSM associations in ContextMemory",
)

NO_WRITE_TERMS = (
    "no permanent proposal files",
    "no Memory/AKBSM writes",
    "no Memory/ExpSM writes",
    "no `semantic_core.json`",
    "no `technical_feedback_patterns.json`",
    "no controller normal-runtime wiring",
    "no `_run_tick()` wiring",
    "no commit/apply/save/write/persist/mutate path",
    "marker 36 absent",
    "memory hashes unchanged",
)

FUTURE_COVERAGE_TERMS = (
    "scenario-only proposal review record can be represented as temporary",
    "ContextMemory metadata",
    "metadata contains lifecycle state and TTL",
    "metadata does not contain write/commit/persist instructions",
    "accepted_for_observation` metadata does not authorize AKBSM write",
    "expired metadata is removed or ignored by retention",
    "normal runtime does not create ContextMemory proposal metadata by default",
    "controller scenarios still pass",
    "memory mutation policy still blocks AKBSM writes",
    "verify_akbsm_proposal_contextmemory_metadata_scaffold.py",
    "verify_akbsm_proposal_contextmemory_metadata_scenarios.py",
)

DOC_REFERENCE_TERMS = (
    "adr_akbsm_proposal_contextmemory_metadata_integration.md",
    "temporary ContextMemory metadata",
    "scenario/test-only",
    "no proposal storage",
    "No ContextMemory integration is implemented",
    "AKBSM writes remain blocked",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scaffold.py",
    "tools/verify_akbsm_draft_proposal_lifecycle_state_scaffold.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    adr_text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    doc_text = "\n".join(
        path.read_text(encoding="utf-8") for path in DOC_REFERENCE_PATHS if path.exists()
    )

    missing_status = _missing_terms(adr_text, STATUS_TERMS)
    missing_no_implementation = _missing_terms(adr_text, NO_IMPLEMENTATION_TERMS)
    missing_temporary_scope = _missing_terms(adr_text, TEMPORARY_SCOPE_TERMS)
    missing_shape = _missing_terms(adr_text, ALLOWED_SHAPE_TERMS)
    missing_forbidden_data = _missing_terms(adr_text, FORBIDDEN_DATA_TERMS)
    missing_authority = _missing_terms(adr_text, AUTHORITY_TERMS)
    missing_retention = _missing_terms(adr_text, RETENTION_TERMS)
    missing_rejected = _missing_terms(adr_text, REJECTED_TERMS)
    missing_no_write = _missing_terms(adr_text, NO_WRITE_TERMS)
    missing_future_coverage = _missing_terms(adr_text, FUTURE_COVERAGE_TERMS)
    missing_refs = _missing_terms(doc_text, DOC_REFERENCE_TERMS)
    safety_passed = _run_core_safety_verifiers()

    checks = {
        "ADR exists": ADR_PATH.exists(),
        "design-only status documented": not missing_status,
        "no implementation is claimed": not missing_no_implementation,
        "temporary ContextMemory metadata scope documented": not missing_temporary_scope,
        "scenario/test-only authority documented": "explicit scenario/test harness only"
        in adr_text,
        "allowed metadata shape documented": not missing_shape,
        "forbidden data/instructions documented": not missing_forbidden_data,
        "forbidden authorities documented": not missing_authority,
        "retention/TTL requirement documented": not missing_retention,
        "rejected alternatives documented": not missing_rejected,
        "no AKBSM write path introduced": not missing_no_write,
        "future scenario/verifier coverage documented": not missing_future_coverage,
        "doc references present": not missing_refs,
        "existing safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("AKBSM proposal ContextMemory metadata ADR verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    _print_missing("missing status terms", missing_status)
    _print_missing("missing no-implementation terms", missing_no_implementation)
    _print_missing("missing temporary scope terms", missing_temporary_scope)
    _print_missing("missing allowed shape terms", missing_shape)
    _print_missing("missing forbidden data terms", missing_forbidden_data)
    _print_missing("missing authority terms", missing_authority)
    _print_missing("missing retention terms", missing_retention)
    _print_missing("missing rejected alternatives", missing_rejected)
    _print_missing("missing no-write terms", missing_no_write)
    _print_missing("missing future coverage terms", missing_future_coverage)
    _print_missing("missing doc reference terms", missing_refs)
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _missing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = text.lower()
    return [term for term in terms if term.lower() not in normalized]


def _print_missing(label: str, missing: list[str]) -> None:
    if missing:
        print(f"  {label}: {', '.join(missing)}")


def _run_core_safety_verifiers() -> bool:
    if os.environ.get("RNDEM_VERIFIER_SHALLOW") == "1":
        return True
    env = dict(os.environ)
    env["RNDEM_VERIFIER_SHALLOW"] = "1"
    for relative_path in CORE_SAFETY_VERIFIERS:
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=ROOT,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
