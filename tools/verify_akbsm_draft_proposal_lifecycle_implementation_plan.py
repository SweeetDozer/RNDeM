from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "docs" / "design_akbsm_draft_proposal_review_lifecycle_implementation.md"
DOC_REFERENCE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "adr_akbsm_draft_proposal_review_lifecycle.md",
    ROOT / "docs" / "adr_akbsm_first_enabled_draft_proposal_experiment.md",
    ROOT / "docs" / "design_akbsm_draft_association_proposal.md",
    ROOT / "docs" / "adr_akbsm_write_policy.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md",
)

STATUS_TERMS = (
    "implementation plan only",
    "Runtime lifecycle implementation is limited to a metadata-only",
    "No proposal storage",
    "No AKBSM write path",
)

COMPONENT_TERMS = (
    "AKBSMProposalLifecycleState",
    "AKBSMProposalReviewRecord",
    "AKBSMProposalReviewController",
    "AKBSMProposalTransitionResult",
)

ALLOWED_TRANSITIONS = (
    "created -> review_pending",
    "review_pending -> accepted_for_observation",
    "review_pending -> deferred",
    "review_pending -> rejected",
    "review_pending -> expired",
    "accepted_for_observation -> expired",
    "deferred -> review_pending",
    "deferred -> expired",
    "rejected -> expired",
)

FORBIDDEN_AUTHORITY_TERMS = (
    "PolicyPressureReview",
    "Mode C",
    "DecisionSelector",
    "ActionScoring",
    "ActionProposer",
    "ModeActionGuard",
    "ValueFeedback",
    "ExpSM writers",
    "memory writers",
    "AKBSM writers",
    "normal runtime default path",
)

STORAGE_TERMS = (
    "test-local provider/controller return values",
    "temporary ContextMemory metadata",
    "scenario/debug output",
    "Memory/AKBSM",
    "Memory/ExpSM",
    "semantic_core.json",
    "technical_feedback_patterns.json",
    "permanent proposal queue",
)

SEQUENCE_TERMS = (
    "metadata-only lifecycle state/record",
    "allowed transition table",
    "scenario fixtures",
    "expiration verifier",
)

DOC_REFERENCE_TERMS = (
    "design_akbsm_draft_proposal_review_lifecycle_implementation.md",
    "lifecycle implementation is limited to",
    "metadata-only and scenario/test-only",
    "test-local provider/controller return values",
    "no storage/writes/commit path exists yet",
    "AKBSM writes remain blocked",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_akbsm_draft_proposal_review_lifecycle_adr.py",
    "tools/verify_akbsm_probe_draft_proposal_experiment.py",
    "tools/verify_akbsm_draft_proposal_disabled_scenarios.py",
    "tools/verify_akbsm_draft_proposal_scaffold.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    plan_text = PLAN_PATH.read_text(encoding="utf-8") if PLAN_PATH.exists() else ""
    doc_text = "\n".join(
        path.read_text(encoding="utf-8") for path in DOC_REFERENCE_PATHS if path.exists()
    )

    missing_status = _missing_terms(plan_text, STATUS_TERMS)
    missing_components = _missing_terms(plan_text, COMPONENT_TERMS)
    missing_transitions = _missing_terms(plan_text, ALLOWED_TRANSITIONS)
    missing_authorities = _missing_terms(plan_text, FORBIDDEN_AUTHORITY_TERMS)
    missing_storage = _missing_terms(plan_text, STORAGE_TERMS)
    missing_sequence = _missing_terms(plan_text, SEQUENCE_TERMS)
    missing_refs = _missing_terms(doc_text, DOC_REFERENCE_TERMS)
    safety_passed = _run_core_safety_verifiers()

    checks = {
        "design plan exists": PLAN_PATH.exists(),
        "design-only status documented": not missing_status,
        "proposed components documented": not missing_components,
        "allowed transitions documented": not missing_transitions,
        "forbidden authorities documented": not missing_authorities,
        "storage policy documented": not missing_storage,
        "implementation sequence documented": not missing_sequence,
        "doc references present": not missing_refs,
        "existing safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("AKBSM draft proposal lifecycle implementation plan verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_status:
        print(f"  missing status terms: {', '.join(missing_status)}")
    if missing_components:
        print(f"  missing component terms: {', '.join(missing_components)}")
    if missing_transitions:
        print(f"  missing allowed transitions: {', '.join(missing_transitions)}")
    if missing_authorities:
        print(f"  missing forbidden authority terms: {', '.join(missing_authorities)}")
    if missing_storage:
        print(f"  missing storage terms: {', '.join(missing_storage)}")
    if missing_sequence:
        print(f"  missing implementation sequence terms: {', '.join(missing_sequence)}")
    if missing_refs:
        print(f"  missing doc reference terms: {', '.join(missing_refs)}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _missing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = text.lower()
    return [term for term in terms if term.lower() not in normalized]


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
