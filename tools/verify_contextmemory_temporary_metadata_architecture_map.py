from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "contextmemory_temporary_metadata_architecture_map.md"

CORE_VERIFIERS = (
    "tools/verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py",
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_negative_retention.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    lowered = text.lower()
    results = {
        "architecture map exists": DOC_PATH.exists(),
        "status/scope says docs-only checkpoint": _has_all(
            lowered,
            (
                "architecture map/checkpoint",
                "does not introduce new runtime behavior",
                "scope",
            ),
        ),
        "v0.1.0 through v0.7.0 timeline exists": _has_all(
            text,
            (
                "v0.1.0",
                "v0.2.0",
                "v0.3.0",
                "v0.4.0",
                "v0.5.0",
                "v0.6.0",
                "v0.7.0",
                "eb7fd21",
            ),
        ),
        "component ladder exists": _has_all(
            text,
            (
                "## Component ladder",
                "AKBSM proposal creation / lifecycle / transition controller",
                "External tick wrapper negative/no-behavior coverage",
            ),
        ),
        "data flow map exists": _has_all(
            text,
            (
                "## Data flow map",
                "AKBSM proposal lifecycle metadata",
                "external tick diagnostic wrapper snapshot",
            ),
        ),
        "authority ladder exists": _has_all(
            text,
            (
                "## Authority ladder",
                "explicit_test_scenario_harness",
                "explicit_observation_diagnostic_harness",
                "explicit_runtime_diagnostic_harness",
                "explicit_tick_diagnostic_harness",
            ),
        ),
        "no-write boundaries documented": _has_all(
            lowered,
            (
                "## no-write boundaries",
                "contextmemory metadata presence is not akbsm write approval",
                "tick diagnostic snapshot is not write approval",
                "proposal.commit_allowed",
            ),
        ),
        "no-behavior-influence boundaries documented": _has_all(
            text,
            (
                "## No-behavior-influence boundaries",
                "DecisionSelector",
                "ActionScoring",
                "PolicyPressureReview",
                "normal behavior output path",
            ),
        ),
        "runtime/_run_tick boundaries documented": _has_all(
            text,
            (
                "## Runtime and _run_tick boundaries",
                "No component in this ladder modifies `_run_tick()`",
                "Direct `_run_tick()` diagnostic hook remains deferred",
            ),
        ),
        "what exists now documented": _has_all(
            text,
            (
                "## What exists now",
                "Shape B deferred ContextMemory metadata boundary",
                "External tick diagnostic wrapper",
            ),
        ),
        "what explicitly does not exist documented": _has_all(
            text,
            (
                "## What explicitly does not exist",
                "No real ContextMemory placement",
                "No `_run_tick()` diagnostic hook",
                "No AKBSM write path",
            ),
        ),
        "verifier coverage map documented": _has_all(
            text,
            (
                "## Verifier coverage map",
                "verify_akbsm_draft_proposal_transition_controller_scenarios.py",
                "verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py",
                "verify_debug_name_dependency_audit.py",
            ),
        ),
        "scenario coverage map documented": _has_all(
            text,
            (
                "## Scenario coverage map",
                "contextmemory_temporary_metadata_negative_retention_coverage.json",
                "contextmemory_temporary_metadata_runtime_observation_negative_no_behavior.json",
                "contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.json",
                "contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.json",
            ),
        ),
        "tag/checkpoint map documented": _has_all(text, ("## Tag/checkpoint map", "v0.7.0")),
        "current safe stopping point documented": _has_all(
            text,
            (
                "## Current safe stopping point",
                "explicit/local/scaffold-only diagnostics",
                "not `_run_tick()` wiring",
            ),
        ),
        "next possible branches documented": _has_all(
            text,
            (
                "## Next possible branches",
                "Stop here and keep diagnostics external",
                "Draft a separate ADR for direct `_run_tick()` diagnostic hook",
            ),
        ),
        "forbidden next steps documented": _has_all(
            text,
            (
                "## Forbidden next steps",
                "No direct `_run_tick()` hook without separate ADR",
                "No default runtime diagnostic activation",
                "No real ContextMemory reads/writes without separate ADR",
            ),
        ),
        "direct _run_tick hook remains deferred": "direct `_run_tick()` diagnostic hook remains deferred"
        in lowered,
        "no real ContextMemory placement claimed": "No real ContextMemory placement" in text
        and "real ContextMemory placement is implemented" not in text,
        "no AKBSM write path claimed": "No AKBSM write path" in text
        and "AKBSM write path is implemented" not in text,
        "existing safety still passes": _run_core_verifiers(),
    }
    passed = all(results.values())
    print("ContextMemory temporary metadata architecture map verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _has_all(text: str, needles: tuple[str, ...]) -> bool:
    return all(needle in text for needle in needles)


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
