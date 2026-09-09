from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_contextmemory_temporary_metadata_placement_api.md"
DOC_REFERENCE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "adr_akbsm_proposal_contextmemory_metadata_integration.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md",
    ROOT / "docs" / "design_akbsm_draft_proposal_review_lifecycle_implementation.md",
    ROOT / "docs" / "project_hygiene_audit.md",
)

STATUS_TERMS = (
    "This ADR is design-only",
    "No ContextMemory placement API is implemented by this pass",
    "No ContextMemory runtime code is changed by this pass",
    "No proposal metadata is written into ContextMemory by this pass",
    "No proposal storage is added by this pass",
    "No AKBSM write path is added by this pass",
)

NO_IMPLEMENTATION_TERMS = (
    "The first implementation must be scenario/test-only",
    "The API must not create permanent memory",
    "The API must not create proposal storage",
    "The API must not persist review records",
    "The API must not write AKBSM or ExpSM",
    "The API must not influence behavior/scoring/guards/Mode C",
)

FUTURE_API_TERMS = (
    "ContextTemporaryMetadataEntry",
    "ContextTemporaryMetadataPlacementResult",
    "ContextTemporaryMetadataPlacementPolicy",
    "place_temporary_metadata",
    "metadata payload plus namespace/source",
    "ttl_ticks",
    "expires_at_tick",
    "placement result metadata",
    "temporary ContextMemory metadata/side-list",
    "future implementation must remain deferred",
)

ALLOWED_METADATA_TERMS = (
    "source",
    "namespace",
    "temporary = true",
    "ttl_ticks",
    "expires_at_tick",
    "created_tick",
    "updated_tick",
    "payload kind",
    "payload reference/id metadata",
    "diagnostic notes",
    "proposal reference metadata",
    "lifecycle state",
    "transition result metadata",
    "review notes/reason",
    "temporary metadata marker",
)

FORBIDDEN_DATA_TERMS = (
    "full AKBSM association writes",
    "new relation types",
    "new concepts",
    "ExpSM records",
    "writer commands",
    "commit/apply/save/write/persist/mutate instructions",
    "behavior instructions",
    "scoring instructions",
    "guard instructions",
    "Mode C instructions",
    "PolicyPressureReview instructions",
)

FORBIDDEN_OPERATION_TERMS = (
    "permanent file write",
    "proposal queue persistence",
    "review record persistence",
    "AKBSM mutation",
    "ExpSM mutation",
    "normal runtime behavior influence",
    "DecisionSelector reads for behavior",
    "ActionScoring reads for scoring",
    "ModeActionGuard reads for guarding",
    "Mode C memory-gate influence",
)

AUTHORITY_TERMS = (
    "explicit scenario/test harness only",
    "normal runtime default path",
    "_run_tick()",
    "PolicyPressureReview",
    "Mode C",
    "ModeCMemoryGateAdvisoryProvider",
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
    "Temporary metadata must have TTL or `expires_at_tick`",
    "Expired metadata must be removable by temporary retention cleanup",
    "Expired metadata must not trigger writes",
    "Expired metadata must not trigger controller transitions",
    "Expired metadata must not become permanent memory",
    "Cleanup must not move metadata into AKBSM/ExpSM",
)

AKBSM_BOUNDARY_TERMS = (
    "ContextMemory metadata presence is not AKBSM write approval",
    "accepted_for_observation` remains observation-only",
    "deferred` is not pending commit",
    "Rejected/expired metadata cannot authorize writes",
    "integration boundary scaffold remains Shape B",
)

NO_WRITE_TERMS = (
    "scenario/test-only authority required",
    "metadata is temporary",
    "TTL/expiration required",
    "no permanent proposal files",
    "no permanent proposal queues",
    "no Memory/AKBSM writes",
    "no Memory/ExpSM writes",
    "no `semantic_core.json`",
    "no `technical_feedback_patterns.json`",
    "no normal runtime wiring",
    "no `_run_tick()` wiring",
    "no behavior/scoring/guard/Mode C/PolicyPressureReview influence",
    "no commit/apply/save/write/persist/mutate path",
    "marker 36 absent",
    "memory hashes unchanged",
)

FUTURE_SCENARIO_TERMS = (
    "scenario/test-only placement accepts temporary metadata with TTL",
    "missing authority is rejected",
    "unknown authority is rejected",
    "metadata without TTL is rejected",
    "write-like metadata is rejected",
    "AKBSM proposal metadata can be represented without write approval",
    "expired metadata is removable/ignored",
    "normal runtime does not place metadata by default",
    "no proposal storage files are created",
    "no permanent proposal queues are created",
    "AKBSM/ExpSM hashes remain unchanged",
)

FUTURE_VERIFIER_TERMS = (
    "verify_contextmemory_temporary_metadata_placement_api_adr.py",
    "verify_contextmemory_temporary_metadata_placement_scaffold.py",
    "verify_contextmemory_temporary_metadata_retention.py",
    "verify_akbsm_proposal_contextmemory_metadata_real_integration_scenarios.py",
)

REJECTED_TERMS = (
    "using existing ContextMemory primary data as proposal storage",
    "permanent proposal queue",
    "proposal metadata created by normal runtime by default",
    "proposal metadata read by DecisionSelector for behavior",
    "proposal metadata read by ActionScoring for scoring",
    "proposal metadata controlled by PolicyPressureReview",
    "proposal metadata controlled by Mode C",
    "accepted_for_observation` treated as write approval",
    "deferred` treated as pending commit",
    "storing full AKBSM associations as ContextMemory metadata",
    "adding storage before retention rules",
)

DOC_REFERENCE_TERMS = (
    "adr_contextmemory_temporary_metadata_placement_api.md",
    "verify_contextmemory_temporary_metadata_placement_api_adr.py",
    "temporary ContextMemory metadata placement API ADR exists",
    "API is not implemented yet",
    "current AKBSM proposal ContextMemory integration remains Shape B/deferred boundary",
    "real ContextMemory placement is still deferred",
    "no proposal storage exists",
    "no normal runtime wiring exists",
    "AKBSM writes remain blocked",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_adr.py",
    "tools/verify_akbsm_draft_proposal_transition_controller_scenarios.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    adr_text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    doc_text = "\n".join(
        path.read_text(encoding="utf-8") for path in DOC_REFERENCE_PATHS if path.exists()
    )

    missing_status = _missing_terms(adr_text, STATUS_TERMS)
    missing_no_implementation = _missing_terms(adr_text, NO_IMPLEMENTATION_TERMS)
    missing_future_api = _missing_terms(adr_text, FUTURE_API_TERMS)
    missing_allowed_metadata = _missing_terms(adr_text, ALLOWED_METADATA_TERMS)
    missing_forbidden_data = _missing_terms(adr_text, FORBIDDEN_DATA_TERMS)
    missing_forbidden_operations = _missing_terms(adr_text, FORBIDDEN_OPERATION_TERMS)
    missing_authority = _missing_terms(adr_text, AUTHORITY_TERMS)
    missing_retention = _missing_terms(adr_text, RETENTION_TERMS)
    missing_akbsm_boundaries = _missing_terms(adr_text, AKBSM_BOUNDARY_TERMS)
    missing_no_write = _missing_terms(adr_text, NO_WRITE_TERMS)
    missing_future_scenarios = _missing_terms(adr_text, FUTURE_SCENARIO_TERMS)
    missing_future_verifiers = _missing_terms(adr_text, FUTURE_VERIFIER_TERMS)
    missing_rejected = _missing_terms(adr_text, REJECTED_TERMS)
    missing_refs = _missing_terms(doc_text, DOC_REFERENCE_TERMS)
    safety_passed = _run_core_safety_verifiers()

    checks = {
        "ADR file exists": ADR_PATH.exists(),
        "design-only status documented": not missing_status,
        "no implementation claimed": not missing_no_implementation,
        "future API scope documented": not missing_future_api,
        "scenario/test-only authority documented": "explicit scenario/test harness only"
        in adr_text,
        "TTL/expiration requirement documented": not missing_retention,
        "allowed metadata documented": not missing_allowed_metadata,
        "forbidden data/operations documented": not missing_forbidden_data
        and not missing_forbidden_operations,
        "forbidden authorities documented": not missing_authority,
        "AKBSM proposal boundaries documented": not missing_akbsm_boundaries,
        "rejected alternatives documented": not missing_rejected,
        "no AKBSM write path introduced": not missing_no_write,
        "future scenarios documented": not missing_future_scenarios,
        "future verifiers documented": not missing_future_verifiers,
        "doc references present": not missing_refs,
        "existing safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("ContextMemory temporary metadata placement API ADR verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    _print_missing("missing status terms", missing_status)
    _print_missing("missing no-implementation terms", missing_no_implementation)
    _print_missing("missing future API terms", missing_future_api)
    _print_missing("missing allowed metadata terms", missing_allowed_metadata)
    _print_missing("missing forbidden data terms", missing_forbidden_data)
    _print_missing("missing forbidden operation terms", missing_forbidden_operations)
    _print_missing("missing authority terms", missing_authority)
    _print_missing("missing retention terms", missing_retention)
    _print_missing("missing AKBSM boundary terms", missing_akbsm_boundaries)
    _print_missing("missing no-write terms", missing_no_write)
    _print_missing("missing future scenario terms", missing_future_scenarios)
    _print_missing("missing future verifier terms", missing_future_verifiers)
    _print_missing("missing rejected alternatives", missing_rejected)
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
