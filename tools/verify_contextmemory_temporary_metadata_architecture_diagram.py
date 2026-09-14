from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "contextmemory_temporary_metadata_architecture_diagram.md"

CORE_VERIFIERS = (
    "tools/verify_contextmemory_temporary_metadata_architecture_map.py",
    "tools/verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    lowered = text.lower()
    results = {
        "diagram document exists": DOC_PATH.exists(),
        "status/scope says visualization/checkpoint only": _has_all(
            lowered,
            (
                "visualization/checkpoint only",
                "does not introduce new runtime behavior",
                "scope",
            ),
        ),
        "main component ladder diagram exists": _has_all(
            text,
            (
                "## Main component ladder",
                "flowchart TD",
                "AKBSM proposal lifecycle metadata",
                "External tick diagnostic wrapper snapshot",
            ),
        ),
        "data flow diagram exists": _has_all(
            text,
            (
                "## Data flow diagram",
                "AKBSM proposal lifecycle metadata",
                "AKBSM proposal ContextMemory metadata payload",
                "generic local ContextTemporaryMetadataPlacement",
                "external tick diagnostic wrapper snapshot",
            ),
        ),
        "authority separation diagram exists": _has_all(
            text,
            (
                "## Authority separation diagram",
                "proposal lifecycle test/scenario authority",
                "temporary metadata placement authority",
                "runtime diagnostic authority",
                "tick diagnostic authority",
            ),
        ),
        "no-write boundary diagram exists": _has_all(
            text,
            (
                "## No-write boundary diagram",
                "Memory/AKBSM",
                "Memory/ExpSM",
                "semantic_core.json",
                "technical_feedback_patterns.json",
                "permanent proposal storage",
                "permanent proposal queue",
                "review record persistence",
            ),
        ),
        "no-behavior-influence boundary diagram exists": _has_all(
            text,
            (
                "## No-behavior-influence boundary diagram",
                "DecisionSelector",
                "ActionScoring",
                "ModeActionGuard",
                "ModeCMemoryGateAdvisoryProvider",
                "PolicyPressureReview",
                "normal behavior output path",
            ),
        ),
        "runtime/_run_tick boundary diagram exists": _has_all(
            text,
            (
                "## Runtime / _run_tick boundary diagram",
                "External tick diagnostic wrapper",
                "provided tick callable",
                "behavior_output unchanged",
                "diagnostic_snapshot separately",
            ),
        ),
        "safe stopping point documented": _has_all(
            lowered,
            (
                "## safe stopping point",
                "current safe stopping point: explicit/local/scaffold-only diagnostics up to an",
                "external tick wrapper",
                "without normal",
                "runtime wiring or `_run_tick()` modification",
            ),
        ),
        "forbidden paths documented": _has_all(
            text,
            (
                "## Forbidden paths",
                "no direct `_run_tick()` hook without separate ADR",
                "no default runtime diagnostic activation",
                "no real ContextMemory reads/writes without separate ADR",
                "no Mode C/PolicyPressureReview connection from this subsystem",
            ),
        ),
        "related documents listed": _has_all(
            text,
            (
                "## Related documents",
                "docs/contextmemory_temporary_metadata_architecture_map.md",
                "docs/adr_contextmemory_temporary_metadata_tick_diagnostic_visibility.md",
                "docs/current_architecture_checkpoint.md",
                "docs/post_v0_0_2_safety_architecture_checkpoint.md",
            ),
        ),
        "direct _run_tick hook remains deferred": "direct `_run_tick()` diagnostic hook remains deferred"
        in lowered,
        "external wrapper remains outside _run_tick": _has_all(
            lowered,
            (
                "external tick diagnostic wrapper",
                "does not call `clcruntime._run_tick` directly",
                "blocked",
            ),
        ),
        "no real ContextMemory placement claimed": "real ContextMemory placement is implemented"
        not in text
        and "does not authorize real ContextMemory reads/writes" in text,
        "no normal runtime default diagnostics claimed": "normal runtime default diagnostics exist"
        not in lowered
        and "not normal runtime default" in lowered,
        "no AKBSM write path claimed": "AKBSM write path is implemented" not in text
        and "akbsm writes remain blocked" in lowered,
        "no behavior/scoring/guard influence claimed": _has_all(
            lowered,
            (
                "does not authorize behavior/scoring/guard influence",
                "diagnostics are not input to these paths",
            ),
        ),
        "existing safety still passes": _run_core_verifiers(),
    }
    passed = all(results.values())
    print("ContextMemory temporary metadata architecture diagram verification:")
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
