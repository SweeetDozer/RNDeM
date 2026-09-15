from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "design_minimal_activation_pattern_substrate.md"
CONTRACT_PATH = ROOT / "docs" / "natural_pattern_data_contract.md"
RUNTIME_ROOT = ROOT / "clc" / "runtime"

CORE_VERIFIERS = (
    "tools/verify_natural_pattern_data_contract.py",
    "tools/verify_memory_mutation_policy.py",
    "tools/verify_debug_name_dependency_audit.py",
)

FORBIDDEN_FILES = (
    "semantic_core.json",
    "technical_feedback_patterns.json",
)


def main() -> int:
    text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    lowered = text.lower()
    results = {
        "design document exists": DOC_PATH.exists(),
        "natural contract remains source": CONTRACT_PATH.exists()
        and _has_all(
            text,
            (
                "Natural Pattern Data Contract defines what RNDeM considers fundamental data",
                "does not weaken the Natural Pattern Data Contract",
            ),
        ),
        "post-v1 docs-only status": _has_all(
            text,
            (
                "Post-v1 architecture/design document",
                "docs/verifier only",
                "does not implement runtime pattern classes",
            ),
        ),
        "common envelope plus modality topology": _has_all(
            text,
            (
                "Use a common pattern envelope with modality-specific topology",
                "Do not force all modalities to share the same geometric shape",
                "The common abstraction is the activation-pattern contract",
                "The topology/shape belongs to the modality",
            ),
        ),
        "pattern envelope fields": _has_all(
            text,
            (
                "ActivationPattern",
                "modality",
                "origin",
                "topology",
                "activation values",
                "active-time metadata",
                "provenance",
            ),
        ),
        "modality origin distinction": _has_all(
            text,
            (
                "VISUAL",
                "AUDIO",
                "INTERNAL",
                "PAIN_DAMAGE",
                "REWARD_SUCCESS",
                "ACTION",
                "EXTERNAL_SENSORY",
                "INTERNAL_STATE",
                "INTERNAL_REACTIVATION",
                "ACTION_GENERATED",
                "Do not conflate modality and origin",
            ),
        ),
        "reactivation preserves modality changes origin": _has_all(
            text,
            (
                "A reactivated visual pattern remains VISUAL",
                "Its origin changes; its modality does not",
                "origin = INTERNAL_REACTIVATION",
                "source_ref = P / trace",
            ),
        ),
        "internal replay not fresh evidence": _has_all(
            text,
            (
                "An internally reactivated pattern is not new environmental evidence",
                "must not by itself count as fresh external confirmation",
                "Repeated self-replay must not allow RNDeM to strengthen a belief",
                "must not generate a new environmental consequence record",
            ),
        ),
        "single-modality activation pattern": _has_all(
            text,
            (
                "One ActivationPattern represents one modality/domain occurrence",
                "Do not create multimodal ActivationPattern payloads",
                "Cross-modal binding belongs to a future episode/context/association layer",
            ),
        ),
        "frame may contain multiple modalities": _has_all(
            text,
            (
                "PatternFrame is a collection",
                "one logical active-time slice",
                "A frame may contain multiple modalities simultaneously",
                "The patterns remain distinct",
            ),
        ),
        "trace is ordered active-time substrate": _has_all(
            text,
            (
                "PatternTrace is a bounded ordered trace",
                "start_tick",
                "end_tick",
                "not automatically AKBSM knowledge",
                "substrate material that later systems may consume",
            ),
        ),
        "active tick temporal coordinate": _has_all(
            text,
            (
                "active_tick is the primary temporal coordinate",
                "Do not make wall-clock time fundamental",
                "Do not implement Heart integration in this pass",
            ),
        ),
        "action is activation pattern": _has_all(
            text,
            (
                "ACTION is a normal activation modality/domain",
                "does not contain its own consequence",
                "does not declare whether it succeeded",
                "does not directly write ExpSM",
            ),
        ),
        "consequences arrive later": _has_all(
            text,
            (
                "Consequences arrive later through sensory/internal patterns",
                "action function",
                "return value treated as truth",
            ),
        ),
        "similarity measurement not identity": _has_all(
            text,
            (
                "PatternSimilarity is a measurement boundary, not semantic identity",
                "same modality",
                "compatible topology",
                "Similarity must not automatically create AKBSM relations",
                "Return a similarity score as a measurement, not truth",
            ),
        ),
        "raw cross-modal similarity excluded": _has_all(
            text,
            (
                "Do not directly compare raw VISUAL values with raw AUDIO values",
                "Raw cross-modal similarity is not part of the minimal substrate",
                "Cross-modal relationships belong to learned association/binding layers",
            ),
        ),
        "debug names non-semantic": _has_all(
            text,
            (
                "Optional debug labels may be allowed as non-semantic metadata only",
                "debug_name=\"dog\"",
                "does not mean the pattern is a dog",
                "No runtime logic may branch on debug labels",
            ),
        ),
        "occurrence identity differs from learned entity": _has_all(
            text,
            (
                "occurrence identity",
                "pattern similarity",
                "stable learned entity identity",
                "does not mean that two different occurrences with similar values are already the same learned entity",
            ),
        ),
        "immutable first implementation": _has_all(
            text,
            (
                "immutable/frozen pattern/frame objects",
                "New sensory state should create new occurrences",
                "historical occurrence identity should remain stable",
                "provenance should remain auditable",
            ),
        ),
        "no persistence": _has_all(
            text,
            (
                "The minimal substrate remains in-memory only",
                "disk persistence",
                "long-term trace storage",
            ),
        ),
        "no writes placement wiring": _has_all(
            text,
            (
                "AKBSM writes",
                "ExpSM writes",
                "ContextMemory placement",
                "Do not wire it into `_run_tick()`",
                "Initial validation should use isolated/scenario/test harnesses",
            ),
        ),
        "next implementation scope bounded": _has_all(
            text,
            (
                "The next implementation pass should implement only",
                "PatternModality",
                "PatternOrigin",
                "PatternTopology",
                "ActivationPattern",
                "PatternFrame",
                "PatternTrace",
                "PatternSimilarity",
                "PatternReactivation",
                "clc/patterns/",
            ),
        ),
        "future scenarios documented": _has_all(
            text,
            (
                "create visual external pattern",
                "frame contains multiple distinct modalities",
                "raw cross-modality similarity is rejected",
                "reactivation creates new occurrence identity",
                "identical external/replayed values remain epistemically distinct",
                "no AKBSM/ExpSM/ContextMemory writes occur",
            ),
        ),
        "deferred scope documented": _has_all(
            text,
            (
                "camera transduction",
                "microphone transduction",
                "cross-modal episode binding",
                "internal replay scheduling",
                "AKBSM pattern-node mapping",
                "ExpSM pattern serialization",
                "AKBSM revision thresholds",
            ),
        ),
        "no forbidden root files": all(not (ROOT / name).exists() for name in FORBIDDEN_FILES),
        "runtime source not part of this design verifier": RUNTIME_ROOT.exists(),
        "existing safety still passes": _run_core_verifiers(),
    }
    passed = all(results.values())
    print("Minimal Activation Pattern Substrate design verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _has_all(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return all(needle.lower() in lowered for needle in needles)


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
