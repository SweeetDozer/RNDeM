from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_contextmemory_temporary_metadata_runtime_observation.md"
DOC_REFERENCE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "adr_contextmemory_temporary_metadata_placement_api.md",
    ROOT / "docs" / "adr_akbsm_proposal_contextmemory_metadata_integration.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md",
    ROOT / "docs" / "project_hygiene_audit.md",
)

HEADINGS = (
    "# ADR: ContextMemory Temporary Metadata Runtime Observation",
    "Status",
    "Context",
    "Decision",
    "Observation-only principle",
    "Allowed future observation surface",
    "Forbidden runtime influence",
    "Authority and activation model",
    "TTL/expiration requirements",
    "AKBSM proposal metadata boundaries",
    "Runtime wiring boundaries",
    "Required future scenarios",
    "Required future verifiers",
    "Rejected alternatives",
    "Consequences",
    "Next steps",
)

STATUS_TERMS = (
    "This ADR is design-only",
    "No runtime observation is implemented by this pass",
    "No runtime source code is changed by this pass",
    "No `_run_tick()` wiring is added by this pass",
    "No `ContextMemoryManager` call is added by this pass",
    "No real ContextMemory write is added by this pass",
    "No proposal storage is added by this pass",
    "No behavior influence is added by this pass",
    "No AKBSM write path is added by this pass",
)

OBSERVATION_ONLY_TERMS = (
    "read-only diagnostic/observational material",
    "runtime can see/report temporary metadata exists",
    "does not mean runtime can decide differently",
    "score actions",
    "guard/block actions",
    "commit, apply, save, write, persist, mutate",
    "become AKBSM/ExpSM memory",
)

ALLOWED_SURFACE_TERMS = (
    "ContextTemporaryMetadataObservation",
    "ContextTemporaryMetadataObservationView",
    "ContextTemporaryMetadataObservationReport",
    "build_temporary_metadata_observation",
    "count active entries",
    "namespaces present",
    "payload kinds present",
    "active/expired status",
    "ttl_ticks",
    "expires_at_tick",
    "proposal lifecycle state metadata only",
    "transition result metadata only",
)

FORBIDDEN_CONTENT_TERMS = (
    "full AKBSM association writes",
    "new relation definitions",
    "new concepts to insert",
    "ExpSM records",
    "writer commands",
    "behavior instructions",
    "scoring instructions",
    "guard instructions",
    "Mode C instructions",
    "PolicyPressureReview instructions",
)

FORBIDDEN_INFLUENCE_TERMS = (
    "DecisionSelector",
    "ActionScoring",
    "ActionProposer",
    "ModeActionGuard",
    "Mode C",
    "ModeCMemoryGateAdvisoryProvider",
    "PolicyPressureReview",
    "ValueFeedback",
    "ExpSM writers/update paths",
    "memory writers",
    "AKBSM writers/save paths",
    "commit/apply/save/write/persist/mutate path",
)

AUTHORITY_TERMS = (
    "explicit scenario/test-only or diagnostic-only",
    "normal runtime default path must not automatically observe",
    "explicit observation authority or a diagnostic flag",
    "Observation authority is not placement authority",
    "Placement authority is not write authority",
    "Runtime observation authority is not AKBSM write authority",
)

TTL_TERMS = (
    "Runtime observation must ignore expired metadata",
    "must not revive expired metadata",
    "transition expired metadata",
    "promote expired metadata to permanent memory",
    "convert expired metadata into write approval",
    "Missing TTL",
    "invalid TTL",
    "missing expiration",
    "invalid expiration",
)

AKBSM_BOUNDARY_TERMS = (
    "ContextMemory metadata presence is not AKBSM write approval",
    "temporary placement result is not storage approval",
    "runtime observation result is not write approval",
    "accepted_for_observation` remains observation-only",
    "deferred` is not pending commit",
    "rejected` cannot authorize writes",
    "expired` cannot authorize writes",
    "proposal.commit_allowed` remains `False`",
)

RUNTIME_WIRING_TERMS = (
    "read-only and diagnostic-only",
    "must not change tick order",
    "must not move `ContextMemoryManager.apply_pending()` calls",
    "must not feed `DecisionSelector`",
    "must not alter behavior output",
    "verifier proving behavior output is unchanged",
)

FUTURE_SCENARIO_TERMS = (
    "observation sees active temporary metadata diagnostically",
    "observation ignores expired metadata",
    "missing authority is rejected",
    "unknown authority is rejected",
    "observation does not alter behavior output",
    "observation does not alter `DecisionSelector` inputs",
    "observation does not alter `ActionScoring` inputs",
    "observation does not alter `ModeActionGuard` inputs",
    "observation does not alter Mode C inputs",
    "observation does not call `PolicyPressureReview`",
    "observation does not create proposal storage",
    "observation does not create permanent proposal queues",
    "observation does not write Memory/AKBSM",
    "observation does not write Memory/ExpSM",
    "memory hashes remain unchanged",
)

FUTURE_VERIFIER_TERMS = (
    "verify_contextmemory_temporary_metadata_runtime_observation_adr.py",
    "verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py",
    "verify_contextmemory_temporary_metadata_runtime_observation_no_behavior_influence.py",
    "verify_akbsm_proposal_temporary_metadata_runtime_observation_scenarios.py",
    "read-only observation",
    "authority-gated observation",
    "expired metadata ignored",
    "no default behavior change",
    "no `semantic_core.json`",
    "no `technical_feedback_patterns.json`",
    "marker 36 absent",
    "hashes unchanged",
)

REJECTED_TERMS = (
    "runtime observation directly inside `DecisionSelector`",
    "runtime observation directly inside `ActionScoring`",
    "runtime observation directly inside `ActionProposer`",
    "runtime observation directly inside `ModeActionGuard`",
    "observation controlled by Mode C",
    "observation controlled by `PolicyPressureReview`",
    "observation treated as memory write approval",
    "accepted_for_observation` treated as AKBSM write approval",
    "deferred` treated as pending commit",
    "expired metadata revived by observation",
    "observation creating proposal storage",
    "observation creating permanent queues",
    "observation writing AKBSM",
    "observation writing ExpSM",
    "observation before no-behavior-influence scenarios",
)

DOC_REFERENCE_TERMS = (
    "adr_contextmemory_temporary_metadata_runtime_observation.md",
    "verify_contextmemory_temporary_metadata_runtime_observation_adr.py",
    "runtime observation ADR exists",
    "design-only",
    "read-only diagnostic",
    "no runtime observation is implemented",
    "no normal runtime wiring",
    "AKBSM writes remain blocked",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_contextmemory_temporary_metadata_negative_retention.py",
    "tools/verify_akbsm_proposal_temporary_metadata_placement_adapter.py",
    "tools/verify_contextmemory_temporary_metadata_placement_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_placement_api_adr.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    adr_text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    doc_text = "\n".join(
        path.read_text(encoding="utf-8") for path in DOC_REFERENCE_PATHS if path.exists()
    )

    missing_headings = _missing_headings(adr_text)
    missing_status = _missing_terms(adr_text, STATUS_TERMS)
    missing_observation = _missing_terms(adr_text, OBSERVATION_ONLY_TERMS)
    missing_surface = _missing_terms(adr_text, ALLOWED_SURFACE_TERMS)
    missing_forbidden_content = _missing_terms(adr_text, FORBIDDEN_CONTENT_TERMS)
    missing_forbidden_influence = _missing_terms(adr_text, FORBIDDEN_INFLUENCE_TERMS)
    missing_authority = _missing_terms(adr_text, AUTHORITY_TERMS)
    missing_ttl = _missing_terms(adr_text, TTL_TERMS)
    missing_akbsm = _missing_terms(adr_text, AKBSM_BOUNDARY_TERMS)
    missing_wiring = _missing_terms(adr_text, RUNTIME_WIRING_TERMS)
    missing_scenarios = _missing_terms(adr_text, FUTURE_SCENARIO_TERMS)
    missing_verifiers = _missing_terms(adr_text, FUTURE_VERIFIER_TERMS)
    missing_rejected = _missing_terms(adr_text, REJECTED_TERMS)
    missing_refs = _missing_terms(doc_text, DOC_REFERENCE_TERMS)
    safety_passed = _run_core_safety_verifiers()

    checks = {
        "ADR file exists": ADR_PATH.exists(),
        "exact required headings documented": not missing_headings,
        "design-only status documented": not missing_status,
        "no implementation claimed": not missing_status,
        "observation-only principle documented": not missing_observation,
        "allowed future observation surface documented": not missing_surface,
        "forbidden runtime influence documented": not missing_forbidden_content
        and not missing_forbidden_influence,
        "authority/activation model documented": not missing_authority,
        "TTL/expiration behavior documented": not missing_ttl,
        "AKBSM proposal boundaries documented": not missing_akbsm,
        "runtime wiring boundaries documented": not missing_wiring,
        "required future scenarios documented": not missing_scenarios,
        "required future verifiers documented": not missing_verifiers,
        "rejected alternatives documented": not missing_rejected,
        "doc references present": not missing_refs,
        "no AKBSM write path introduced": "No AKBSM write path is added by this pass"
        in adr_text
        and "AKBSM writes remain blocked" in adr_text,
        "existing safety still passes": safety_passed,
    }
    passed = all(checks.values())

    print("ContextMemory temporary metadata runtime observation ADR verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    _print_missing("missing headings", missing_headings)
    _print_missing("missing status terms", missing_status)
    _print_missing("missing observation-only terms", missing_observation)
    _print_missing("missing allowed surface terms", missing_surface)
    _print_missing("missing forbidden content terms", missing_forbidden_content)
    _print_missing("missing forbidden influence terms", missing_forbidden_influence)
    _print_missing("missing authority terms", missing_authority)
    _print_missing("missing TTL terms", missing_ttl)
    _print_missing("missing AKBSM boundary terms", missing_akbsm)
    _print_missing("missing runtime wiring terms", missing_wiring)
    _print_missing("missing future scenario terms", missing_scenarios)
    _print_missing("missing future verifier terms", missing_verifiers)
    _print_missing("missing rejected alternatives", missing_rejected)
    _print_missing("missing doc reference terms", missing_refs)
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _missing_headings(text: str) -> list[str]:
    lines = {line.strip().lstrip("#").strip() for line in text.splitlines()}
    return [heading for heading in HEADINGS if heading.lstrip("#").strip() not in lines]


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
