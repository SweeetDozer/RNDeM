from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "adr_contextmemory_temporary_metadata_tick_diagnostic_visibility.md"
DOC_REFERENCE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "adr_contextmemory_temporary_metadata_diagnostic_wiring.md",
    ROOT / "docs" / "adr_contextmemory_temporary_metadata_runtime_observation.md",
    ROOT / "docs" / "current_architecture_checkpoint.md",
    ROOT / "docs" / "post_v0_0_2_safety_architecture_checkpoint.md",
    ROOT / "docs" / "project_hygiene_audit.md",
)

HEADINGS = (
    "# ADR: ContextMemory Temporary Metadata Tick Diagnostic Visibility",
    "Status",
    "Context",
    "Decision",
    "Preferred design",
    "Deferred design",
    "Diagnostic-only tick visibility principle",
    "Allowed future visibility surfaces",
    "Forbidden tick/runtime paths",
    "Activation and authority model",
    "No-behavior-influence requirements",
    "Tick-order requirements",
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
    "No tick diagnostic visibility is implemented by this pass",
    "No runtime source code is changed by this pass",
    "No `_run_tick()` wiring is added by this pass",
    "No `ContextMemoryManager` call is added by this pass",
    "No real ContextMemory read/write is added by this pass",
    "No proposal storage is added by this pass",
    "No behavior influence is added by this pass",
    "No AKBSM write path is added by this pass",
)
DECISION_TERMS = (
    "The first future tick-facing diagnostic visibility should not modify",
    "explicit external diagnostic wrapper or diagnostic harness",
    "Any direct `_run_tick()` diagnostic hook is deferred",
    "post-behavior-output",
    "diagnostic-only",
    "disabled by default",
    "authority-gated",
    "proven no-behavior-influence",
)
PREFERRED_TERMS = (
    "TemporaryMetadataTickDiagnosticWrapper",
    "TemporaryMetadataTickDiagnosticSnapshot",
    "build_tick_diagnostic_snapshot",
    "run_tick_with_diagnostics",
    "explicit diagnostic harness only",
    "not normal runtime default",
    "does not modify `_run_tick()`",
    "collects diagnostics outside the tick decision path",
    "returns runtime behavior output unchanged",
    "returns diagnostic snapshot separately",
)
DEFERRED_TERMS = (
    "Direct `_run_tick()` diagnostic hook is deferred",
    "optional",
    "disabled by default",
    "explicit diagnostic authority only",
    "post-behavior-output only",
    "not before or between behavior phases",
    "not allowed to change tick result",
    "not allowed to change memory writes",
    "not allowed to change `apply_pending` timing",
    "not allowed to feed Mode C or `PolicyPressureReview`",
)
PRINCIPLE_TERMS = (
    "separate diagnostic snapshot about temporary metadata near a tick execution",
    "the tick can decide differently",
    "selector/scoring/proposer/guards can read diagnostics",
    "memory writers can read diagnostics",
    "`apply_pending` timing can change",
    "AKBSM/ExpSM can be updated",
    "temporary metadata becomes permanent memory",
    "diagnostics authorize writes",
)
SURFACE_TERMS = (
    "explicit external diagnostic wrapper",
    "explicit diagnostic harness",
    "manually requested tick diagnostic snapshot",
    "scenario/test-only diagnostic tick run",
    "tick number or diagnostic tick",
    "diagnostics enabled/disabled flag",
    "active temporary metadata count",
    "expired metadata count as diagnostics only",
    "diagnostic authority used",
)
FORBIDDEN_TERMS = (
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
    "default `_run_tick` path",
)
AUTHORITY_TERMS = (
    "Diagnostic authority is required",
    "Missing authority must be rejected",
    "Unknown authority must be rejected",
    "Placement authority is not tick diagnostic authority",
    "Observation authority is not tick diagnostic authority",
    "Runtime diagnostic authority is not tick diagnostic authority",
    "Tick diagnostic authority is not placement authority",
    "Tick diagnostic authority is not observation authority",
    "Tick diagnostic authority is not write authority",
    "Tick diagnostic authority is not AKBSM write authority",
    "Normal runtime default must not activate tick diagnostics automatically",
    "CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY",
)
NO_BEHAVIOR_TERMS = (
    "same input produces the same behavior output",
    "`DecisionSelector` inputs unchanged",
    "`ActionScoring` inputs unchanged",
    "`ActionProposer` inputs unchanged",
    "`ModeActionGuard` inputs unchanged",
    "Mode C inputs unchanged",
    "`PolicyPressureReview` inputs unchanged",
    "memory writer inputs unchanged",
    "AKBSM writer inputs unchanged",
    "ExpSM writer inputs unchanged",
    "`ContextMemoryManager.apply_pending()` timing unchanged",
    "tick phase order unchanged",
    "no additional Memory/AKBSM writes",
    "no additional Memory/ExpSM writes",
    "real memory hashes unchanged",
)
TICK_ORDER_TERMS = (
    "Future external wrapper must not modify tick order",
    "Future external wrapper must not move `apply_pending`",
    "Future external wrapper must not add diagnostics before selector/scoring/guard phases",
    "Future external wrapper must keep diagnostics separate from behavior output",
    "Direct `_run_tick()` diagnostic hook is deferred",
)
TTL_TERMS = (
    "Tick diagnostics must ignore expired metadata as active",
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
    "tick diagnostic snapshot is not write approval",
    "`accepted_for_observation` remains observation-only",
    "`deferred` is not pending commit",
    "Rejected metadata cannot authorize writes",
    "Expired metadata cannot authorize writes",
    "`proposal.commit_allowed` remains `False`",
    "AKBSM writes remain blocked",
)
SCENARIO_TERMS = (
    "external diagnostic wrapper can produce separate tick diagnostic snapshot",
    "missing tick diagnostic authority is rejected",
    "unknown tick diagnostic authority is rejected",
    "placement authority cannot request tick diagnostics",
    "observation authority cannot request tick diagnostics",
    "runtime diagnostic authority cannot request tick diagnostics",
    "tick diagnostic authority cannot place metadata",
    "tick diagnostic authority cannot authorize writes",
    "tick diagnostic snapshot sees active metadata only as diagnostic material",
    "tick diagnostic snapshot ignores expired metadata as active",
    "tick diagnostic snapshot is returned separately from behavior output",
    "behavior output is identical with diagnostics disabled and enabled",
    "`DecisionSelector` inputs unchanged",
    "`ContextMemoryManager.apply_pending` timing unchanged",
    "no proposal storage",
    "AKBSM/ExpSM hashes remain unchanged",
)
VERIFIER_TERMS = (
    "verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py",
    "verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py",
    "verify_contextmemory_temporary_metadata_tick_diagnostic_no_behavior_influence.py",
    "verify_contextmemory_temporary_metadata_tick_order_unchanged.py",
    "verify_akbsm_proposal_temporary_metadata_tick_diagnostic_scenarios.py",
    "tick diagnostic visibility is explicit",
    "tick diagnostic visibility is authority-gated",
    "default `_run_tick` path is unchanged",
    "tick phase order is unchanged",
    "`ContextMemoryManager.apply_pending` timing unchanged",
    "diagnostic snapshot is separate from behavior output",
    "behavior output unchanged with diagnostics disabled/enabled",
    "no `DecisionSelector` influence",
    "no AKBSM writer influence",
    "no commit/apply/save/write/persist/mutate path",
    "marker 36 absent",
    "memory hashes unchanged",
)
REJECTED_TERMS = (
    "wiring diagnostics directly into `_run_tick()` by default",
    "diagnostics before `DecisionSelector`",
    "diagnostics before `ActionScoring`",
    "diagnostics before `ActionProposer`",
    "diagnostics before `ModeActionGuard`",
    "diagnostics inside Mode C",
    "diagnostics inside `PolicyPressureReview`",
    "diagnostics inside memory writers",
    "diagnostics inside AKBSM writers",
    "diagnostics changing tick result",
    "diagnostics changing behavior output",
    "diagnostics moving `ContextMemoryManager.apply_pending()`",
    "diagnostics treated as write approval",
    "`accepted_for_observation` treated as AKBSM write approval",
    "`deferred` treated as pending commit",
    "expired metadata revived by tick diagnostics",
    "diagnostics creating proposal storage",
    "diagnostics creating permanent queues",
    "diagnostics writing AKBSM or ExpSM",
    "direct `_run_tick()` hook implemented before wrapper/no-behavior-influence checks",
)
DOC_REFERENCE_TERMS = (
    "adr_contextmemory_temporary_metadata_tick_diagnostic_visibility.md",
    "verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py",
    "tick diagnostic visibility ADR exists",
    "design-only",
    "preferred future shape is external diagnostic wrapper/harness",
    "direct `_run_tick()` diagnostic hook is deferred",
    "no runtime source code changed",
    "no `_run_tick()` wiring exists",
    "diagnostics remain unwired from behavior paths",
    "no real ContextMemory reads/writes exist",
    "AKBSM writes remain blocked",
)
CORE_VERIFIERS = (
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py",
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
        "preferred": _missing_terms(adr_text, PREFERRED_TERMS),
        "deferred": _missing_terms(adr_text, DEFERRED_TERMS),
        "principle": _missing_terms(adr_text, PRINCIPLE_TERMS),
        "surfaces": _missing_terms(adr_text, SURFACE_TERMS),
        "forbidden": _missing_terms(adr_text, FORBIDDEN_TERMS),
        "authority": _missing_terms(adr_text, AUTHORITY_TERMS),
        "no-behavior": _missing_terms(adr_text, NO_BEHAVIOR_TERMS),
        "tick-order": _missing_terms(adr_text, TICK_ORDER_TERMS),
        "TTL/expiration": _missing_terms(adr_text, TTL_TERMS),
        "AKBSM": _missing_terms(adr_text, AKBSM_TERMS),
        "future scenarios": _missing_terms(adr_text, SCENARIO_TERMS),
        "future verifiers": _missing_terms(adr_text, VERIFIER_TERMS),
        "rejected alternatives": _missing_terms(adr_text, REJECTED_TERMS),
        "doc references": _missing_terms(doc_text, DOC_REFERENCE_TERMS),
    }
    safety_passed = _run_core_verifiers()
    checks = {
        "ADR file exists": ADR_PATH.exists(),
        "exact required headings documented": not missing["headings"],
        "design-only status documented": not missing["status"],
        "no implementation claimed": not missing["status"],
        "preferred external diagnostic wrapper/harness documented": not missing["preferred"],
        "direct _run_tick hook deferred": not missing["deferred"],
        "diagnostic-only tick visibility principle documented": not missing["principle"],
        "allowed future visibility surfaces documented": not missing["surfaces"],
        "forbidden tick/runtime paths documented": not missing["forbidden"],
        "authority/activation model documented": not missing["authority"],
        "no-behavior-influence requirements documented": not missing["no-behavior"],
        "tick-order requirements documented": not missing["tick-order"],
        "TTL/expiration behavior documented": not missing["TTL/expiration"],
        "AKBSM proposal boundaries documented": not missing["AKBSM"],
        "required future scenarios documented": not missing["future scenarios"],
        "required future verifiers documented": not missing["future verifiers"],
        "rejected alternatives documented": not missing["rejected alternatives"],
        "doc references present": not missing["doc references"],
        "no AKBSM write path introduced": "AKBSM writes remain blocked" in adr_text,
        "existing safety still passes": safety_passed,
    }
    passed = all(checks.values())
    print("ContextMemory temporary metadata tick diagnostic visibility ADR verification:")
    for key, ok in checks.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    if not passed:
        for section, terms in missing.items():
            if terms:
                print(f"  missing {section}: {', '.join(terms)}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _missing_headings(text: str) -> tuple[str, ...]:
    return tuple(heading for heading in HEADINGS if heading not in text)


def _missing_terms(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term for term in terms if term not in text)


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
