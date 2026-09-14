from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "v1_readiness_criteria.md"

CORE_VERIFIERS = (
    "tools/verify_contextmemory_temporary_metadata_architecture_diagram.py",
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
        "v1 readiness document exists": DOC_PATH.exists(),
        "status/scope says readiness criteria only": _has_all(
            lowered,
            (
                "readiness criteria for `v1.0.0`",
                "does not introduce runtime behavior",
                "scope",
                "release-boundary document",
            ),
        ),
        "meaning of v1.0.0 documented": _has_all(
            text,
            (
                "`v1.0.0` means a stable safety-bounded RNDeM CLC prototype checkpoint",
                "`v1.0.0` freezes the current safe architecture boundaries for review",
                "stop, review the full architecture",
            ),
        ),
        "what v1.0.0 is not documented": _has_all(
            text,
            (
                "`v1.0.0` is not AGI",
                "`v1.0.0` is not autonomous self-modification",
                "`v1.0.0` is not permission for AKBSM writes",
                "`v1.0.0` is not permission for real ContextMemory placement",
                "`v1.0.0` is not permission for direct `_run_tick()` diagnostic hook",
            ),
        ),
        "current baseline documented": _has_all(
            text,
            (
                "fbef338 docs: visualize temporary metadata diagnostic architecture",
                "Latest tag: `v0.8.0`",
                "Post-`v0.8.0` visualization document is merged",
            ),
        ),
        "required architecture state documented": _has_all(
            text,
            (
                "`_run_tick()` remains mechanically split and behavior-stable",
                "`DecisionSelector` remains before `ExpSMMechanismSearch`",
                "AKBSM writes remain blocked",
                "Direct `_run_tick()` diagnostic hook remains deferred",
            ),
        ),
        "required safety boundaries documented": _has_all(
            text,
            (
                "No runtime default diagnostic activation",
                "No direct `_run_tick()` diagnostic hook",
                "No real ContextMemory reads/writes",
                "No Memory/AKBSM writes",
                "No marker 36",
            ),
        ),
        "required verifier coverage documented": _has_all(
            text,
            (
                "memory mutation policy verifiers",
                "external tick wrapper negative/no-behavior verifier",
                "architecture map verifier",
                "architecture diagram verifier",
                "scenario fixture verifier",
                "`main.py` smoke run",
            ),
        ),
        "required scenario coverage documented": _has_all(
            text,
            (
                "real-input audio/sensor/value/guard regression fixtures",
                "AKBSM write-disabled fixtures",
                "ContextMemory temporary metadata negative/retention fixtures",
                "external tick wrapper negative/no-behavior fixtures",
            ),
        ),
        "required memory invariants documented": _has_all(
            text,
            (
                "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
                "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
                "cannot be tagged if these hashes change unexpectedly",
            ),
        ),
        "required runtime invariants documented": _has_all(
            text,
            (
                "`apply_pending` count remains 62",
                "marker 36 remains absent",
                "`legacy_semantic_decision` remains 0",
                "`semantic_decision_needs_migration` remains 0",
                "`unknown_runtime_logic` remains 0",
                "`ambiguous_runtime_logic` remains 1",
                "debug-name high-risk findings remain 0",
            ),
        ),
        "required documentation documented": _has_all(
            text,
            (
                "## Required documentation",
                "docs/current_architecture_checkpoint.md",
                "docs/contextmemory_temporary_metadata_architecture_map.md",
                "docs/v1_readiness_criteria.md",
            ),
        ),
        "required release validation documented": _has_all(
            text,
            (
                "## Required release validation",
                "python tools/verify_v1_readiness_criteria.py",
                "python tools/verify_contextmemory_temporary_metadata_architecture_diagram.py",
                "python tools/verify_scenario_fixtures.py",
                "python -B main.py",
            ),
        ),
        "allowed pre-v1 work documented": _has_all(
            text,
            (
                "## Allowed pre-v1 work",
                "docs cleanup",
                "release checklist verifier",
                "final safety checkpoint documentation",
            ),
        ),
        "forbidden pre-v1 work documented": _has_all(
            text,
            (
                "## Forbidden pre-v1 work",
                "direct `_run_tick()` hook",
                "real ContextMemory placement",
                "AKBSM writes",
                "memory hash changes",
            ),
        ),
        "v1.0.0 release checklist documented": _has_all(
            text,
            (
                "## v1.0.0 release checklist",
                "architecture map exists",
                "architecture diagram exists",
                "v1 readiness criteria exists",
                "v1 tag points at reviewed main",
            ),
        ),
        "post-v1 review plan documented": _has_all(
            text,
            (
                "## Post-v1 review plan",
                "After `v1.0.0` is tagged, stop feature work",
                "Review what remains forbidden",
                "Decide next roadmap only after that review",
            ),
        ),
        "open questions after v1 documented": _has_all(
            text,
            (
                "## Open questions after v1.0.0",
                "Should temporary metadata stay permanently external/scaffold-only?",
                "Is any direct `_run_tick()` diagnostic hook justified after review?",
            ),
        ),
        "v1 does not claim AGI": "not AGI" in text and "is AGI" not in text,
        "v1 does not authorize _run_tick hook": "does not authorize `_run_tick()` wiring" in text
        and "permission for direct `_run_tick()` diagnostic hook" in text,
        "v1 does not authorize real ContextMemory placement": "does not authorize real ContextMemory reads/writes"
        in text
        and "not permission for real ContextMemory placement" in text,
        "v1 does not authorize AKBSM/ExpSM writes": "does not authorize AKBSM/ExpSM writes"
        in text
        and "not permission for AKBSM writes" in text,
        "v1 does not authorize behavior/scoring/guard influence": (
            "does not authorize behavior/scoring/guard influence" in text
            and "not permission for behavior/scoring/guard influence" in text
        ),
        "existing safety still passes": _run_core_verifiers(),
    }
    passed = all(results.values())
    print("v1.0.0 readiness criteria verification:")
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
