from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_contextmemory_temporary_metadata_diagnostic_wiring.md"
DOC_REFERENCE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "adr_contextmemory_temporary_metadata_runtime_observation.md",
    ROOT / "docs" / "adr_contextmemory_temporary_metadata_placement_api.md",
    ROOT / "docs" / "adr_akbsm_proposal_contextmemory_metadata_integration.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md",
    ROOT / "docs" / "project_hygiene_audit.md",
)

HEADINGS = (
    "# ADR: ContextMemory Temporary Metadata Diagnostic Runtime Wiring",
    "Status",
    "Context",
    "Decision",
    "Diagnostic-only wiring principle",
    "Allowed future wiring surface",
    "Forbidden runtime paths",
    "Authority and activation model",
    "No-behavior-influence requirements",
    "TTL and expiration requirements",
    "AKBSM proposal metadata boundaries",
    "Required future scenarios",
    "Required future verifiers",
    "Rejected alternatives",
    "Consequences",
    "Next steps",
)

STATUS_TERMS = (
    "This ADR is design-only",
    "No diagnostic runtime wiring is implemented by this pass",
    "No runtime source code is changed by this pass",
    "No `_run_tick()` wiring is added by this pass",
    "No `ContextMemoryManager` call is added by this pass",
    "No real ContextMemory read/write is added by this pass",
    "No proposal storage is added by this pass",
    "No behavior influence is added by this pass",
    "No AKBSM write path is added by this pass",
)

DECISION_TERMS = (
    "first future runtime-facing observation wiring must be diagnostic-only",
    "explicit diagnostic surface",
    "must not run automatically in the normal tick path by default",
    "must not feed `DecisionSelector`",
    "must not change behavior output",
    "must not create or imply write approval",
    "must not create persistent storage or queues",
)

PRINCIPLE_TERMS = (
    "runtime can produce a report that temporary metadata exists",
    "decisions can change",
    "scores can change",
    "guards can change",
    "actions can change",
    "memory writes can occur",
    "AKBSM/ExpSM can be updated",
    "temporary metadata becomes permanent memory",
)

SURFACE_TERMS = (
    "RuntimeTemporaryMetadataDiagnosticReport",
    "RuntimeTemporaryMetadataDiagnosticView",
    "RuntimeTemporaryMetadataObservationDiagnosticProvider",
    "build_runtime_temporary_metadata_diagnostics",
    "explicit diagnostic command/harness",
    "explicit runtime diagnostic method",
    "scenario/test-only diagnostic run",
    "manually requested diagnostic report",
    "outside `_run_tick()`",
    "reads only local `ContextTemporaryMetadataPlacement`",
    "active temporary metadata count",
    "expired metadata count as diagnostics only",
    "observer authority used",
)

FORBIDDEN_PATH_TERMS = (
    "_run_tick()",
    "DecisionSelector",
    "ActionScoring",
    "ActionProposer",
    "ModeActionGuard",
    "Mode C",
    "ModeCMemoryGateAdvisoryProvider",
    "PolicyPressureReview",
    "ValueFeedback",
    "ExpSM commit/update paths",
    "MemoryDraftWriter",
    "ExpSMCommitWriter",
    "ExpSMUpdateWriter",
    "ValueFeedbackUpdateWriter",
    "AKBSM writers/save paths",
    "ContextMemoryManager.apply_pending()",
    "normal behavior output path",
)

AUTHORITY_TERMS = (
    "Diagnostic observation authority is required",
    "Missing authority must be rejected",
    "Unknown authority must be rejected",
    "Placement authority is not observation authority",
    "Observation authority is not placement authority",
    "Diagnostic observation authority is not write authority",
    "Diagnostic observation authority is not AKBSM write authority",
    "Normal runtime default path must not activate diagnostics automatically",
    "CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY",
)

NO_BEHAVIOR_TERMS = (
    "same scenario input produces same behavior output",
    "DecisionSelector` inputs unchanged",
    "ActionScoring` inputs unchanged",
    "ActionProposer` inputs unchanged",
    "ModeActionGuard` inputs unchanged",
    "Mode C inputs unchanged",
    "PolicyPressureReview` inputs unchanged",
    "memory writer inputs unchanged",
    "AKBSM writer inputs unchanged",
    "ExpSM writer inputs unchanged",
    "no additional Memory/AKBSM writes",
    "no additional Memory/ExpSM writes",
)

TTL_TERMS = (
    "Diagnostic wiring must ignore expired metadata as active",
    "Expired metadata may appear only in explicit expired diagnostics",
    "Expired metadata must not be revived",
    "Expired metadata must not trigger transitions",
    "Expired metadata must not become permanent memory",
    "Expired metadata must not become write approval",
)

AKBSM_TERMS = (
    "ContextMemory metadata presence is not AKBSM write approval",
    "temporary placement result is not storage approval",
    "observation result is not write approval",
    "diagnostic runtime report is not write approval",
    "accepted_for_observation` remains observation-only",
    "deferred` is not pending commit",
    "Rejected metadata cannot authorize writes",
    "Expired metadata cannot authorize writes",
    "proposal.commit_allowed` remains `False`",
    "AKBSM writes remain blocked",
)

SCENARIO_TERMS = (
    "diagnostic report can be requested explicitly under diagnostic authority",
    "missing diagnostic authority is rejected",
    "unknown diagnostic authority is rejected",
    "placement authority cannot request runtime diagnostics",
    "diagnostic authority cannot place metadata",
    "diagnostic authority cannot authorize writes",
    "diagnostic report sees active metadata only as diagnostic material",
    "diagnostic report ignores expired metadata as active",
    "diagnostic report does not alter behavior output",
    "diagnostic report does not alter `DecisionSelector` inputs",
    "diagnostic report does not create proposal storage",
    "diagnostic report does not write Memory/AKBSM",
    "AKBSM/ExpSM hashes remain unchanged",
)

VERIFIER_TERMS = (
    "verify_contextmemory_temporary_metadata_diagnostic_wiring_adr.py",
    "verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py",
    "verify_contextmemory_temporary_metadata_diagnostic_wiring_no_behavior_influence.py",
    "verify_akbsm_proposal_temporary_metadata_diagnostic_wiring_scenarios.py",
    "diagnostic wiring is explicit",
    "diagnostic wiring is authority-gated",
    "diagnostic wiring is not normal runtime default",
    "diagnostic wiring is not `_run_tick()` default",
    "diagnostic wiring is read-only",
    "diagnostic report is metadata-only",
    "expired metadata is ignored as active",
    "no `DecisionSelector` influence",
    "no AKBSM writer influence",
    "no commit/apply/save/write/persist/mutate path",
    "marker 36 absent",
    "memory hashes unchanged",
)

REJECTED_TERMS = (
    "wiring observer directly into `_run_tick()` by default",
    "wiring observer into `DecisionSelector`",
    "wiring observer into `ActionScoring`",
    "wiring observer into `ActionProposer`",
    "wiring observer into `ModeActionGuard`",
    "wiring observer into Mode C",
    "wiring observer into `PolicyPressureReview`",
    "wiring observer into memory writers",
    "wiring observer into AKBSM writers",
    "diagnostic report treated as write approval",
    "accepted_for_observation` treated as AKBSM write approval",
    "deferred` treated as pending commit",
    "expired metadata revived by diagnostics",
    "diagnostics creating proposal storage",
    "diagnostics creating permanent queues",
    "diagnostics writing AKBSM or ExpSM",
    "diagnostics implemented before no-behavior-influence checks",
)

DOC_REFERENCE_TERMS = (
    "adr_contextmemory_temporary_metadata_diagnostic_wiring.md",
    "verify_contextmemory_temporary_metadata_diagnostic_wiring_adr.py",
    "diagnostic runtime wiring ADR exists",
    "design-only",
    "diagnostic runtime wiring is not implemented yet",
    "no `_run_tick()` wiring exists",
    "observer remains unwired from behavior paths",
    "no real ContextMemory reads/writes exist",
    "AKBSM writes remain blocked",
)

CORE_VERIFIERS = (
    "tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_runtime_observation_adr.py",
    "tools/verify_contextmemory_temporary_metadata_negative_retention.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    adr_text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    doc_text = "\n".join(
        path.read_text(encoding="utf-8") for path in DOC_REFERENCE_PATHS if path.exists()
    )
    missing = {
        "headings": _missing_headings(adr_text),
        "status": _missing_terms(adr_text, STATUS_TERMS),
        "decision": _missing_terms(adr_text, DECISION_TERMS),
        "principle": _missing_terms(adr_text, PRINCIPLE_TERMS),
        "surface": _missing_terms(adr_text, SURFACE_TERMS),
        "forbidden paths": _missing_terms(adr_text, FORBIDDEN_PATH_TERMS),
        "authority": _missing_terms(adr_text, AUTHORITY_TERMS),
        "no-behavior": _missing_terms(adr_text, NO_BEHAVIOR_TERMS),
        "TTL/expiration": _missing_terms(adr_text, TTL_TERMS),
        "AKBSM boundaries": _missing_terms(adr_text, AKBSM_TERMS),
        "future scenarios": _missing_terms(adr_text, SCENARIO_TERMS),
        "future verifiers": _missing_terms(adr_text, VERIFIER_TERMS),
        "rejected alternatives": _missing_terms(adr_text, REJECTED_TERMS),
        "doc references": _missing_terms(doc_text, DOC_REFERENCE_TERMS),
    }
    safety_passed = _run_core_verifiers()
    checks = {
        "ADR file exists": ADR_PATH.exists(),
        "design-only status documented": not missing["status"],
        "no implementation claimed": not missing["status"],
        "diagnostic-only wiring principle documented": not missing["principle"],
        "allowed future wiring surface documented": not missing["surface"],
        "forbidden runtime paths documented": not missing["forbidden paths"],
        "authority/activation model documented": not missing["authority"],
        "no-behavior-influence requirements documented": not missing["no-behavior"],
        "TTL/expiration behavior documented": not missing["TTL/expiration"],
        "AKBSM proposal boundaries documented": not missing["AKBSM boundaries"],
        "required future scenarios documented": not missing["future scenarios"],
        "required future verifiers documented": not missing["future verifiers"],
        "rejected alternatives documented": not missing["rejected alternatives"],
        "doc references present": not missing["doc references"],
        "no AKBSM write path introduced": "No AKBSM write path is added by this pass"
        in adr_text
        and "AKBSM writes remain blocked" in adr_text,
        "existing safety still passes": safety_passed,
    }
    checks["exact required headings documented"] = not missing["headings"]
    checks["future decision documented"] = not missing["decision"]
    passed = all(checks.values())

    print("ContextMemory temporary metadata diagnostic wiring ADR verification:")
    for key, ok in checks.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    for label, terms in missing.items():
        _print_missing(f"missing {label}", terms)
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


def _run_core_verifiers() -> bool:
    if os.environ.get("RNDEM_VERIFIER_SHALLOW") == "1":
        return True
    env = dict(os.environ)
    env["RNDEM_VERIFIER_SHALLOW"] = "1"
    for relative_path in CORE_VERIFIERS:
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
