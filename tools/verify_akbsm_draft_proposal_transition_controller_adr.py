from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_akbsm_draft_proposal_transition_controller_experiment.md"
DOC_REFERENCE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "adr_akbsm_draft_proposal_review_lifecycle.md",
    ROOT / "docs" / "design_akbsm_draft_proposal_review_lifecycle_implementation.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md",
)

STATUS_TERMS = (
    "design-only",
    "metadata-only transition controller scaffold is implemented",
    "No transition execution is implemented",
    "No proposal storage",
    "No AKBSM write path",
)

CONTROLLER_SHAPE_TERMS = (
    "AKBSMProposalReviewRecord",
    "AKBSMProposalTransitionResult",
    "new AKBSMProposalReviewRecord",
    "metadata",
    "test/scenario",
)

AUTHORITY_TERMS = (
    "explicit test/scenario harness only",
    "normal runtime default path",
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

FORBIDDEN_TRANSITIONS = (
    "any state -> commit",
    "any state -> apply",
    "any state -> save",
    "any state -> write",
    "any state -> persist",
    "any state -> mutate",
    "expired -> accepted_for_observation",
    "rejected -> accepted_for_observation",
)

STORAGE_TERMS = (
    "test-local controller return values only",
    "temporary ContextMemory metadata",
    "scenario/debug output",
    "Memory/AKBSM",
    "Memory/ExpSM",
    "semantic_core.json",
    "technical_feedback_patterns.json",
    "permanent proposal queues",
)

DOC_REFERENCE_TERMS = (
    "adr_akbsm_draft_proposal_transition_controller_experiment.md",
    "metadata-only transition controller scaffold",
    "transition execution is not implemented",
    "metadata-only and test/scenario-only",
    "test-local controller return values only",
    "AKBSM writes remain blocked",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_akbsm_draft_proposal_lifecycle_state_scaffold.py",
    "tools/verify_akbsm_draft_proposal_lifecycle_implementation_plan.py",
    "tools/verify_akbsm_draft_proposal_review_lifecycle_adr.py",
    "tools/verify_akbsm_probe_draft_proposal_experiment.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    adr_text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    doc_text = "\n".join(
        path.read_text(encoding="utf-8") for path in DOC_REFERENCE_PATHS if path.exists()
    )

    missing_status = _missing_terms(adr_text, STATUS_TERMS)
    missing_shape = _missing_terms(adr_text, CONTROLLER_SHAPE_TERMS)
    missing_authority = _missing_terms(adr_text, AUTHORITY_TERMS)
    missing_allowed = _missing_terms(adr_text, ALLOWED_TRANSITIONS)
    missing_forbidden = _missing_terms(adr_text, FORBIDDEN_TRANSITIONS)
    missing_storage = _missing_terms(adr_text, STORAGE_TERMS)
    missing_refs = _missing_terms(doc_text, DOC_REFERENCE_TERMS)
    safety_passed = _run_core_safety_verifiers()

    checks = {
        "ADR exists": ADR_PATH.exists(),
        "design-only status documented": not missing_status,
        "controller shape documented": not missing_shape,
        "allowed authority documented": not missing_authority,
        "allowed transitions documented": not missing_allowed,
        "forbidden transitions documented": not missing_forbidden,
        "storage policy documented": not missing_storage,
        "doc references present": not missing_refs,
        "existing safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("AKBSM draft proposal transition controller ADR verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_status:
        print(f"  missing status terms: {', '.join(missing_status)}")
    if missing_shape:
        print(f"  missing controller shape terms: {', '.join(missing_shape)}")
    if missing_authority:
        print(f"  missing authority terms: {', '.join(missing_authority)}")
    if missing_allowed:
        print(f"  missing allowed transitions: {', '.join(missing_allowed)}")
    if missing_forbidden:
        print(f"  missing forbidden transitions: {', '.join(missing_forbidden)}")
    if missing_storage:
        print(f"  missing storage terms: {', '.join(missing_storage)}")
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
