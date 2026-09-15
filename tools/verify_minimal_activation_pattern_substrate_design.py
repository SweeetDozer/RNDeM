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
                "Natural Pattern Data Contract defines what RNDeM considers",
                "fundamental data",
                "does not weaken the Natural Pattern Data Contract",
            ),
        ),
        "post-v1 isolated implementation status": _has_all(
            text,
            (
                "Post-v1 architecture/design document with isolated implementation complete",
                "implemented in `clc/patterns/`",
                "remains in-memory only and isolated",
            ),
        ),
        "common envelope plus modality topology": _has_all(
            text,
            (
                "Use a common pattern envelope with modality-specific topology",
                "Do not force all modalities to share the same geometric shape",
                "The common abstraction is the activation-pattern contract",
                "topology/shape belongs to the modality",
            ),
        ),
        "pattern envelope fields": _has_all(
            text,
            (
                "NFPFrame",
                "frame_id",
                "modality",
                "origin",
                "topology",
                "activation values",
                "active_tick",
                "provenance",
            ),
        ),
        "temporal hierarchy explicit": _has_all(
            text,
            (
                "NFPFrame",
                "NFPWindow",
                "NFPSequence",
                "This hierarchy is fundamental",
                "A frame represents instantaneous activation",
                "A window represents local temporal dynamics",
                "A sequence represents longer temporal behavior or process",
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
                "A reactivated visual frame remains VISUAL",
                "Its origin changes; its modality does not",
                "origin = INTERNAL_REACTIVATION",
                "provenance_ref = source frame ID",
            ),
        ),
        "internal replay not fresh evidence": _has_all(
            text,
            (
                "An internally reactivated pattern is not new environmental evidence",
                "must not by itself count as fresh external confirmation",
                "Repeated self-replay must not allow RNDeM to strengthen a belief",
                "must not generate a new environmental consequence",
            ),
        ),
        "single-modality activation pattern": _has_all(
            text,
            (
                "One `NFPFrame` represents one modality/domain occurrence at one active tick",
                "Do not create multimodal `NFPFrame` payloads",
                "Cross-modal binding belongs to a future episode/context/association layer",
            ),
        ),
        "moment may contain multiple modalities": _has_all(
            text,
            (
                "PatternMoment",
                "multimodal same-tick grouping",
                "is not an `NFPFrame`",
                "not semantic interpretation",
            ),
        ),
        "window and sequence are ordered temporal substrate": _has_all(
            text,
            (
                "NFPWindow",
                "NFPSequence",
                "start_tick",
                "end_tick",
                "length",
                "window_count",
                "not automatically an entity",
            ),
        ),
        "active tick temporal coordinate": _has_all(
            text,
            (
                "active_tick is the primary temporal coordinate",
                "Do not make wall-clock time fundamental",
                "Do not implement Heart integration",
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
                "does not contain its own consequence",
                "does not declare whether it succeeded",
            ),
        ),
        "similarity measurement not identity": _has_all(
            text,
            (
                "Similarity is a measurement boundary, not semantic identity",
                "Frame similarity measures instantaneous activation resemblance",
                "Window similarity measures short temporal-pattern resemblance",
                "They are not interchangeable",
                "same modality",
                "compatible/equal topology",
            ),
        ),
        "raw cross-modal similarity excluded": _has_all(
            text,
            (
                "Raw cross-modal similarity is rejected",
                "Cross-modal relationships belong to learned association/binding layers",
            ),
        ),
        "debug names non-semantic": _has_all(
            text,
            (
                "Optional debug labels are non-semantic metadata only",
                "debug_name=\"dog\"",
                "does not mean the frame is a dog",
                "No runtime logic may branch on debug labels",
            ),
        ),
        "occurrence identity differs from learned entity": _has_all(
            text,
            (
                "occurrence identity",
                "frame similarity",
                "window similarity",
                "stable learned entity identity",
                "same learned entity",
            ),
        ),
        "immutable first implementation": _has_all(
            text,
            (
                "`NFPFrame` is an immutable or effectively immutable occurrence-level activation",
                "The source frame remains immutable",
            ),
        ),
        "no persistence": _has_all(
            text,
            (
                "The minimal substrate remains in-memory only",
                "disk persistence",
                "long-term sequence storage",
            ),
        ),
        "no writes placement wiring": _has_all(
            text,
            (
                "AKBSM writes",
                "ExpSM writes",
                "ContextMemory placement",
                "Do not wire it into `_run_tick()`",
                "Initial validation uses isolated/scenario/test harnesses",
            ),
        ),
        "implementation scope bounded": _has_all(
            text,
            (
                "Define a minimal implementation-ready substrate for",
                "NFPFrame",
                "NFPWindow",
                "NFPSequence",
                "PatternModality",
                "PatternOrigin",
                "PatternTopology",
                "NFPFrameSimilarity",
                "NFPWindowSimilarity",
                "NFPReactivation",
                "clc/patterns/",
            ),
        ),
        "isolated scenarios documented": _has_all(
            text,
            (
                "scenarios/minimal_activation_pattern_substrate.json",
                "tools/verify_minimal_activation_pattern_substrate.py",
                "create VISUAL external NFPFrame",
                "NFPWindow accepts ordered same-modality compatible frames",
                "NFPSequence accepts ordered compatible windows",
                "different window lengths non-comparable",
                "external and internally replayed identical values remain epistemically distinct",
                "no `_run_tick()` integration",
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
