from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "design_first_natural_pattern_transduction.md"
CONTRACT_PATH = ROOT / "docs" / "natural_pattern_data_contract.md"
SUBSTRATE_PATH = ROOT / "docs" / "design_minimal_activation_pattern_substrate.md"
PATTERNS_ROOT = ROOT / "clc" / "patterns"
TRANSDUCTION_ROOT = ROOT / "clc" / "transduction"
SCENARIO_SUPPORT_ROOT = ROOT / "scenarios" / "support"

CORE_VERIFIERS = (
    "tools/verify_minimal_activation_pattern_substrate.py",
    "tools/verify_minimal_activation_pattern_substrate_design.py",
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
    results = {
        "design document exists": DOC_PATH.exists(),
        "post-v1.1 design-only status": _has_all(
            text,
            (
                "Proposed post-v1.1 design",
                "docs/verifier only",
                "does not implement a transduction layer",
                "does not modify `clc/patterns/`",
                "does not wire anything into normal runtime or `_run_tick()`",
            ),
        ),
        "architecture relationship documented": _has_all(
            text,
            (
                "Natural Pattern Data Contract defines what fundamental data is",
                "NFP substrate `v1.1.0` defines Frame/Window/Sequence representation",
                "First Natural Pattern Transduction defines how an external world first creates",
                "EXTERNAL_SENSORY",
                "NFPFrame",
            ),
        ),
        "synthetic environment external to cognition": _has_all(
            text,
            (
                "synthetic world is engineered by us",
                "natural from RNDeM's perspective",
                "RNDeM receives only the sensory activation caused by the environment",
                "RNDeM does not receive the human semantic description",
                "The cognitive substrate receives only activation",
            ),
        ),
        "environment sensor nfp boundaries explicit": _has_all(
            text,
            (
                "world state",
                "agent sensory state",
                "environment state",
                "sensor snapshot",
                "NFPFrame",
                "!=",
            ),
        ),
        "initial visual field numeric small": _has_all(
            text,
            (
                "minimal visual scalar-field environment",
                "16 x 16",
                "spatial field",
                "0.0 .. 1.0",
                "SyntheticVisualField",
                "values = numeric field only",
            ),
        ),
        "hidden truth not exposed": _has_all(
            text,
            (
                "test harness",
                "RNDeM does not",
                "direction=\"right\"",
                "class=\"moving_dot\"",
                "The only sensory consequence is the changing visual field",
            ),
        ),
        "sensor snapshot label-free": _has_all(
            text,
            (
                "shape",
                "numeric field values",
                "sensor tick / active tick",
                "opaque source identity",
                "No semantic labels",
                "snapshot is not yet an NFP",
            ),
        ),
        "visual transducer creates visual external frame": _has_all(
            text,
            (
                "VisualFieldTransducer.transduce",
                "PatternTopology(shape)",
                "NFPFrame.values",
                "row-major",
                "modality = VISUAL",
                "origin = EXTERNAL_SENSORY",
                "active_tick = snapshot active tick",
                "must not alias mutable environment storage",
            ),
        ),
        "simple transduction purpose documented": _has_all(
            text,
            (
                "not intended to model a biological retina",
                "world physics/state",
                "sensory measurement",
                "neural-style activation representation",
                "receptive fields",
                "sensor noise",
                "retina-like local preprocessing",
            ),
        ),
        "no semantic preprocessing": _has_all(
            text,
            (
                "must not perform",
                "classification",
                "segmentation into named objects",
                "object identity extraction",
                "OCR",
                "direction labels",
                "motion labels",
                "human-readable interpretation",
            ),
        ),
        "label leakage rule": _has_all(
            text,
            (
                "Human/debug metadata that does not change the sensory field must not change",
                "stimulus A",
                "stimulus B",
                "topology",
                "activation values",
                "modality",
                "similarity",
                "hidden debug description = \"moves right\"",
                "hidden debug description = \"banana\"",
                "transduced NFP topology/values must be identical",
            ),
        ),
        "opaque provenance rule": _has_all(
            text,
            (
                "Provenance may identify the sensory occurrence/source boundary",
                "must not smuggle semantic truth",
                "sensor_snapshot:000123",
                "dog_at_x5_y3",
                "moving_point_right",
                "red_ball",
            ),
        ),
        "active time preserved": _has_all(
            text,
            (
                "existing RNDeM active-tick semantics",
                "world.step(active_tick)",
                "sensor snapshot and `NFPFrame` preserve that active tick",
                "Do not make wall-clock time fundamental",
            ),
        ),
        "window assembler non-semantic": _has_all(
            text,
            (
                "NFPWindowAssembler",
                "does not perform recognition",
                "groups ordered compatible frames",
                "window_size configurable",
                "same modality required",
                "same topology required",
                "strictly increasing active ticks",
                "Do not add semantic event boundaries",
            ),
        ),
        "window captures temporal change": _has_all(
            text,
            (
                "No individual frame contains \"motion\"",
                "The temporal change exists in",
                "NFPWindow(frame1, frame2, frame3)",
                "must not write motion, direction, object, or velocity",
            ),
        ),
        "sequence deferred": _has_all(
            text,
            (
                "Do not require the first source implementation to create long `NFPSequence`",
                "environment",
                "NFPFrame",
                "NFPWindow",
                "Sequence construction may come later",
                "Do not add sequence semantics",
            ),
        ),
        "no direct memory authority": _has_all(
            text,
            (
                "write AKBSM",
                "write ExpSM",
                "write chronicle",
                "place real ContextMemory",
                "change confidence",
                "assert facts",
                "create learned entities",
            ),
        ),
        "no runtime wiring": _has_all(
            text,
            (
                "CLCRuntime",
                "`_run_tick()`",
                "DecisionSelector",
                "ActionProposer",
                "ActionScoring",
                "ModeActionGuard",
                "PolicyPressureReview",
                "standalone harness",
            ),
        ),
        "future implementation locations only": _has_all(
            text,
            (
                "clc/transduction/",
                "visual.py",
                "windowing.py",
                "scenarios/support/synthetic_visual_world.py",
                "external test environment",
                "not part of RNDeM cognition",
                "Do not implement these files in this pass",
            ),
        ),
        "future types documented": _has_all(
            text,
            (
                "VisualFieldSnapshot",
                "VisualFieldTransducer",
                "NFPWindowAssembler",
                "SyntheticVisualWorld",
            ),
        ),
        "next-pass coverage documented": _has_all(
            text,
            (
                "static 16x16 field produces VISUAL EXTERNAL_SENSORY NFPFrame",
                "frame topology matches field shape",
                "transduction copies data rather than aliasing mutable world storage",
                "provenance is opaque/non-semantic",
                "different hidden/debug labels with identical physical field produce identical activation values",
                "window contains no semantic motion/direction label",
                "no AKBSM writes",
                "no ExpSM writes",
                "no ContextMemory placement",
                "no runtime wiring",
            ),
        ),
        "environment authority rule": _has_all(
            text,
            (
                "sensor/transducer observes the environment",
                "does not ask the environment what the stimulus \"means\"",
                "action",
                "environment changes",
                "sensor state changes",
                "NFP changes",
            ),
        ),
        "deferred scope documented": _has_all(
            text,
            (
                "camera hardware",
                "microphone hardware",
                "OpenCV",
                "real image files as cognitive input",
                "audio files as semantic input",
                "retina simulation",
                "multi-channel color vision",
                "object segmentation",
                "semantic recognition",
                "cross-modal binding",
                "audio transduction",
                "prediction",
                "replay scheduling",
                "AKBSM mapping",
                "ExpSM serialization",
                "ContextMemory placement",
                "`_run_tick()` integration",
            ),
        ),
        "safety boundary": _has_all(
            text,
            (
                "does not implement the transduction layer",
                "does not add files under `clc/transduction/`",
                "does not create `semantic_core.json`",
                "technical_feedback_patterns.json",
                "Do not tag or merge from this design pass",
            ),
        ),
        "source files not implemented": not TRANSDUCTION_ROOT.exists() and not SCENARIO_SUPPORT_ROOT.exists(),
        "existing pattern substrate untouched by verifier": PATTERNS_ROOT.exists(),
        "contract and substrate docs exist": CONTRACT_PATH.exists() and SUBSTRATE_PATH.exists(),
        "no forbidden root files": all(not (ROOT / name).exists() for name in FORBIDDEN_FILES),
        "existing safety still passes": _run_core_verifiers(),
    }
    passed = all(results.values())
    print("First Natural Pattern Transduction design verification:")
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
