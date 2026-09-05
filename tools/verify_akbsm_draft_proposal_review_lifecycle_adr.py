from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_akbsm_draft_proposal_review_lifecycle.md"
DOC_REFERENCE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "adr_akbsm_first_enabled_draft_proposal_experiment.md",
    ROOT / "docs" / "design_akbsm_draft_association_proposal.md",
    ROOT / "docs" / "adr_akbsm_write_policy.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md",
)

LIFECYCLE_STATES = (
    "created",
    "review_pending",
    "accepted_for_observation",
    "deferred",
    "rejected",
    "expired",
)

FORBIDDEN_STATE_TERMS = (
    "committed",
    "applied",
    "persisted",
    "written",
    "saved",
    "accepted_for_write",
    "approved_for_akbsm",
)

NO_WRITE_TERMS = (
    "No lifecycle state may imply AKBSM mutation",
    "No lifecycle state may imply proposal commit",
    "No lifecycle state may allow permanent storage",
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

FORBIDDEN_TRANSITION_TERMS = (
    "any state -> commit/apply/save/write/persist/mutate",
)

STORAGE_TERMS = (
    "temporary ContextMemory metadata",
    "scenario/debug output",
    "Memory/AKBSM",
    "Memory/ExpSM",
    "semantic_core.json",
    "technical_feedback_patterns.json",
    "permanent proposal files",
)

DOC_REFERENCE_TERMS = (
    "adr_akbsm_draft_proposal_review_lifecycle.md",
    "lifecycle is design-only",
    "metadata-only",
    "accepted_for_observation",
    "not AKBSM write approval",
    "runtime behavior remains unchanged",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_akbsm_probe_draft_proposal_experiment.py",
    "tools/verify_akbsm_draft_proposal_disabled_scenarios.py",
    "tools/verify_akbsm_draft_proposal_scaffold.py",
    "tools/verify_akbsm_write_disabled_scenarios.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    adr_text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    doc_text = "\n".join(
        path.read_text(encoding="utf-8") for path in DOC_REFERENCE_PATHS if path.exists()
    )

    missing_states = _missing_terms(adr_text, LIFECYCLE_STATES)
    missing_forbidden_states = _missing_terms(adr_text, FORBIDDEN_STATE_TERMS)
    missing_no_write = _missing_terms(adr_text, NO_WRITE_TERMS)
    missing_allowed_transitions = _missing_terms(adr_text, ALLOWED_TRANSITIONS)
    missing_forbidden_transitions = _missing_terms(adr_text, FORBIDDEN_TRANSITION_TERMS)
    missing_storage = _missing_terms(adr_text, STORAGE_TERMS)
    missing_refs = _missing_terms(doc_text, DOC_REFERENCE_TERMS)
    forbidden_states_marked = _forbidden_states_are_marked(adr_text)
    safety_passed = _run_core_safety_verifiers()

    checks = {
        "ADR exists": ADR_PATH.exists(),
        "lifecycle states documented": not missing_states,
        "forbidden write-like states documented": not missing_forbidden_states,
        "forbidden write-like states marked forbidden": forbidden_states_marked,
        "no-write semantics documented": not missing_no_write,
        "allowed transitions documented": not missing_allowed_transitions,
        "forbidden transitions documented": not missing_forbidden_transitions,
        "storage policy documented": not missing_storage,
        "doc references present": not missing_refs,
        "existing safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("AKBSM draft proposal review lifecycle ADR verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    if missing_states:
        print(f"  missing lifecycle states: {', '.join(missing_states)}")
    if missing_forbidden_states:
        print(f"  missing forbidden state terms: {', '.join(missing_forbidden_states)}")
    if missing_no_write:
        print(f"  missing no-write terms: {', '.join(missing_no_write)}")
    if missing_allowed_transitions:
        print(f"  missing allowed transitions: {', '.join(missing_allowed_transitions)}")
    if missing_forbidden_transitions:
        print(f"  missing forbidden transitions: {', '.join(missing_forbidden_transitions)}")
    if missing_storage:
        print(f"  missing storage terms: {', '.join(missing_storage)}")
    if missing_refs:
        print(f"  missing doc reference terms: {', '.join(missing_refs)}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _missing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = text.lower()
    return [term for term in terms if term.lower() not in normalized]


def _forbidden_states_are_marked(text: str) -> bool:
    normalized = text.lower()
    forbidden_heading = normalized.find("forbidden write-like lifecycle state")
    if forbidden_heading == -1:
        return False
    section = normalized[forbidden_heading:]
    return all(term.lower() in section for term in FORBIDDEN_STATE_TERMS)


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
