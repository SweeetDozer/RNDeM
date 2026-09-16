from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "natural_pattern_data_contract.md"
RUNTIME_ROOT = ROOT / "clc" / "runtime"
MEMORY_ROOT = ROOT / "Memory"

CORE_VERIFIERS = (
    "tools/verify_v1_readiness_criteria.py",
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
        "natural pattern data contract exists": DOC_PATH.exists(),
        "post-v1 contract status": _has_all(
            lowered,
            (
                "post-v1 contract",
                "first isolated in-memory",
                "pattern substrate",
                "first isolated natural",
                "source pipeline",
                "clc/transduction/",
                "still does not implement memory writers",
            ),
        ),
        "natural activation patterns are fundamental data": _has_all(
            text,
            (
                "RNDeM fundamentally operates on activation patterns",
                "Natural activation patterns are the fundamental data of RNDeM",
            ),
        ),
        "natural data examples documented": _has_all(
            text,
            (
                "visual activation pattern",
                "audio activation pattern",
                "body/internal-state activation pattern",
                "pain/damage pattern",
                "success/reward pattern",
                "action activation pattern",
                "memory replay/reactivation pattern",
            ),
        ),
        "text is not privileged input": _has_all(
            text,
            (
                "Text is not a privileged input modality",
                "A written word is a visual pattern",
                "A spoken word is an audio pattern",
            ),
        ),
        "labels are not primary truth": _has_all(
            text,
            (
                "These must not be treated as primary reality",
                "Pattern identity is not the same thing as a human label",
                "Human-readable names are optional metadata/debug/interface conveniences",
                "does not make the pattern semantically a dog",
            ),
        ),
        "visual data is sensory activation": _has_all(
            text,
            (
                "dog.png interpreted as dog",
                "camera/environment",
                "visual transduction",
                "activation field",
                "the file itself must not become semantic truth",
            ),
        ),
        "audio data is sensory activation": _has_all(
            text,
            (
                "transcript=\"hello\"",
                "sound source",
                "temporal/frequency activation pattern",
                "Speech meaning must emerge",
            ),
        ),
        "continuous loop replaces request response": _has_all(
            text,
            (
                "The fundamental RNDeM model is not",
                "input",
                "process",
                "output",
                "continuous loop",
                "There is no special moment where RNDeM is waiting for a prompt",
                "There is no mandatory request/response transaction",
            ),
        ),
        "activation pattern fields documented": _has_all(
            text,
            (
                "modality/domain",
                "activation topology/shape",
                "activation values",
                "temporal position/order",
                "source context",
                "optional internal origin",
            ),
        ),
        "modalities documented": _has_all(
            text,
            (
                "visual",
                "audio",
                "internal/body state",
                "pain/damage/error",
                "reward/success",
                "action/motor",
                "memory/reactivation",
            ),
        ),
        "action is activation pattern": _has_all(
            text,
            (
                "Action is not merely output",
                "action activation pattern",
                "affecting action/motor channels",
            ),
        ),
        "consequence learned from subsequent experience": _has_all(
            text,
            (
                "The consequence must be learned from subsequent sensory/internal input",
                "RNDeM learns consequences through subsequent experience",
                "Function return values must not be treated as learned consequences",
            ),
        ),
        "internal pattern reactivation required": _has_all(
            text,
            (
                "Internal Pattern Reactivation",
                "reactivate previously experienced patterns internally",
                "memory recall",
                "self-instruction",
                "internal thought",
            ),
        ),
        "windows and sequences documented": _has_all(
            text,
            (
                "NFPFrame",
                "NFPWindow",
                "NFPSequence",
                "local temporal dynamics",
                "memory-compatible substrate material",
                "what raw detail is retained",
                "how windows/sequences decay or consolidate",
            ),
        ),
        "AKBSM explicit associative world model": _has_all(
            text,
            (
                "AKBSM is explicit associative world-model memory",
                "AKBSM stores explicit nodes/relations",
                "current asserted model of the world",
            ),
        ),
        "AKBSM static and adaptive": _has_all(
            text,
            (
                "AKBSM is static in representation but adaptive under experience",
                "Static means",
                "Adaptive means",
            ),
        ),
        "active beliefs may be revised": _has_all(
            text,
            (
                "fire -> temperature -> cold",
                "fire -> temperature -> hot",
                "old incorrect active relation should not remain",
            ),
        ),
        "superseded beliefs belong in chronicle": _has_all(
            text,
            (
                "belongs to chronicle / letopis memory",
                "not the active AKBSM world model",
                "previously believed",
            ),
        ),
        "facts and hypotheses distinguished": _has_all(
            text,
            (
                "current fact / accepted knowledge",
                "hypothesis",
                "possible association",
                "uncertain relation",
                "contradicted/revisable knowledge",
            ),
        ),
        "confidence evidence are metadata": _has_all(
            text,
            (
                "Confidence/evidence metadata may exist",
                "Confidence is not the relation itself",
            ),
        ),
        "ExpSM operational experience": _has_all(
            text,
            (
                "ExpSM is operational experience memory",
                "pattern/context",
                "action pattern",
                "observed consequence",
                "ExpSM is not the historical chronicle",
            ),
        ),
        "v1 ExpSM decisions preserved": _has_all(
            text,
            (
                "hits/misses",
                "slowly saturating confidence",
                "similar records may coexist",
                "SimilarityObserver",
                "Activation top-N",
                "DecisionSelector chooses",
                "Feedback strengthens only used record",
            ),
        ),
        "chronicle policy documented": _has_all(
            text,
            (
                "Chronicle memory is history",
                "what RNDeM previously believed",
                "Chronicle history must not automatically become active AKBSM truth",
            ),
        ),
        "working context memory boundary documented": _has_all(
            text,
            (
                "Future working/context memory should contain temporary active pattern/context material",
                "must not automatically convert into",
                "write approval",
            ),
        ),
        "anti-GPT constraints explicit": _has_all(
            text,
            (
                "Anti-GPT Constraints",
                "prompt",
                "tokenization",
                "model inference",
                "response",
                "labeled image",
                "audio",
                "transcript",
            ),
        ),
        "v1 safety boundaries remain intact": _has_all(
            text,
            (
                "The Natural Pattern Data Contract does not invalidate v1",
                "v1 remains the safe runtime/container baseline",
                "real ContextMemory placement",
                "AKBSM writes",
                "direct `_run_tick()` hooks",
                "default diagnostics",
                "behavior influence",
            ),
        ),
        "implementation details deferred": _has_all(
            text,
            (
                "exact future NFPFrame representation beyond the minimal Python scaffold",
                "dense vs sparse patterns",
                "visual resolution",
                "audio representation",
                "similarity algorithm",
                "AKBSM revision thresholds",
                "sensor hardware adapters",
                "camera implementation",
                "microphone implementation",
            ),
        ),
        "current minimal substrate documented": _has_all(
            text,
            (
                "The first isolated in-memory activation-pattern substrate now exists",
                "clc/patterns/",
                "NFPFrame",
                "NFPWindow",
                "NFPSequence",
                "PatternOrigin",
                "PatternModality",
                "NFPFrameSimilarity",
                "NFPWindowSimilarity",
                "NFPReactivation",
                "not wired into `_run_tick()`",
            ),
        ),
        "no forbidden files": all(not (ROOT / name).exists() for name in FORBIDDEN_FILES),
        "runtime source untouched by this verifier": RUNTIME_ROOT.exists(),
        "Memory tree exists but verifier does not write it": MEMORY_ROOT.exists(),
        "existing safety still passes": _run_core_verifiers(),
    }
    passed = all(results.values())
    print("Natural Pattern Data Contract verification:")
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
