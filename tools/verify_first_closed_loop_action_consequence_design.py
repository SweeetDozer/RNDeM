from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "design_first_closed_loop_action_consequence.md"
README_PATH = ROOT / "README.md"
CONTRACT_PATH = ROOT / "docs" / "natural_pattern_data_contract.md"
TRANSDUCTION_DESIGN_PATH = ROOT / "docs" / "design_first_natural_pattern_transduction.md"
ARCHITECTURE_PATH = ROOT / "docs" / "current_architecture_checkpoint.md"
HYGIENE_PATH = ROOT / "docs" / "project_hygiene_audit.md"
ACTUATION_ROOT = ROOT / "clc" / "actuation"

CORE_VERIFIERS = (
    "tools/verify_first_natural_pattern_transduction.py",
    "tools/verify_first_natural_pattern_transduction_design.py",
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
    readme = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else ""
    contract = CONTRACT_PATH.read_text(encoding="utf-8") if CONTRACT_PATH.exists() else ""
    transduction_design = TRANSDUCTION_DESIGN_PATH.read_text(encoding="utf-8") if TRANSDUCTION_DESIGN_PATH.exists() else ""
    architecture = ARCHITECTURE_PATH.read_text(encoding="utf-8") if ARCHITECTURE_PATH.exists() else ""
    hygiene = HYGIENE_PATH.read_text(encoding="utf-8") if HYGIENE_PATH.exists() else ""
    results = {
        "design document exists": DOC_PATH.exists(),
        "docs verifier only status": _has_all(
            text,
            (
                "Proposed post-v1.2 design only",
                "does not implement actuation",
                "does not modify `clc/patterns/`",
                "does not modify `clc/transduction/`",
                "does not wire anything into normal runtime or `_run_tick()`",
            ),
        ),
        "relationship to v1.1/v1.2 documented": _has_all(
            text,
            (
                "v1.1.0:",
                "NFP representation substrate",
                "v1.2.0:",
                "external world -> natural sensory NFP",
                "ACTION NFP -> external world -> subsequent sensory NFP",
                "not learned behavior",
                "not autonomous behavior",
            ),
        ),
        "canonical causal model": _has_all(
            text,
            (
                "sensory NFP at tick T",
                "ACTION NFPFrame at tick T",
                "action transduction",
                "actuator signal",
                "world transition T -> T+1",
                "sensor snapshot at T+1",
                "VISUAL EXTERNAL_SENSORY NFPFrame at T+1",
            ),
        ),
        "fundamental consequence rule": _has_all(
            text,
            (
                "An action does not know its consequence",
                "An actuator does not report semantic consequence truth",
                "The environment changes",
                "subsequent sensory/internal activation",
                "result.success",
                "result.failed",
                "result.collision",
                "result.reward",
                "-> None",
            ),
        ),
        "action frame timing model": _has_all(
            text,
            (
                "Use one `ACTION NFPFrame`",
                "transition T -> T+1",
                "`NFPFrame` is the current motor activation",
                "`NFPWindow` is temporal history/dynamics of motor activation",
                "one frame at a time",
                "Do not interpret a whole action window as one opaque semantic command",
            ),
        ),
        "ACTION_GENERATED requirement": _has_all(
            text,
            (
                "modality = ACTION",
                "origin = ACTION_GENERATED",
                "INTERNAL_REACTIVATION",
                "remembering an action",
                "!=",
                "performing an action",
                "ACTION + ACTION_GENERATED",
            ),
        ),
        "action topology numeric-only": _has_all(
            text,
            (
                "PatternTopology((2,))",
                "(channel_0_activation, channel_1_activation)",
                "0.0 .. 1.0",
                "move_left",
                "move_right",
                "direction",
                "command",
            ),
        ),
        "fixed physical wiring not semantic": _has_all(
            text,
            (
                "signed_drive = channel_1 - channel_0",
                "positive horizontal physical influence",
                "negative horizontal physical influence",
                "not semantic knowledge supplied to RNDeM",
                "motor activation",
                "muscle/actuator force",
                "receives no declaration",
            ),
        ),
        "ActionTransducer boundary": _has_all(
            text,
            (
                "ActionTransducer.transduce(action_frame) -> ActuatorSignal",
                "clc/actuation/",
                "accept only `ACTION` + `ACTION_GENERATED` `NFPFrame`",
                "validate expected actuator topology",
                "copy numeric activation values",
                "preserve active tick",
                "opaque signal identity/provenance",
                "semantic command",
            ),
        ),
        "ActuatorSignal numeric only": _has_all(
            text,
            (
                "immutable numeric-only boundary object",
                "values: tuple[float, ...]",
                "active_tick: int",
                "signal_id: int",
                "source_frame_ref: str",
                "expected_result",
                "success",
                "failure",
                "collision",
                "reward",
                "action NFP",
                "!= actuator signal",
                "!= world state transition",
            ),
        ),
        "opaque action provenance": _has_all(
            text,
            (
                "actuator provenance must identify occurrence rather than meaning",
                "action_frame:000123",
                "actuator_signal:000456",
                "move_right",
                "escape_wall",
                "go_to_target",
            ),
        ),
        "closed-loop world external": _has_all(
            text,
            (
                "scenario/test-only world",
                "hidden physical state",
                "Do not put this environment inside cognition",
                "SyntheticClosedLoopVisualWorld",
                "body_row",
                "body_column",
                "16x16 scalar field",
                "RNDeM receives only the numeric visual field",
            ),
        ),
        "world transition no semantic result": _has_all(
            text,
            (
                "world.apply_actuator_signal(signal)",
                "mutate external world state",
                "must not return semantic result information",
                "-> None",
                "may internally validate tick ordering",
                "may not send interpretation back to cognition",
            ),
        ),
        "strict tick causality": _has_all(
            text,
            (
                "tick T:",
                "ACTION frame generated for T",
                "world T -> T+1",
                "tick T+1:",
                "new sensor snapshot",
                "consequence sensory data",
                "action(T)",
                "consequence_observation(T+1)",
            ),
        ),
        "same action different world state": _has_all(
            text,
            (
                "Same Action, Different Consequences",
                "controllable excitation at interior position",
                "controllable excitation already at boundary",
                "identical ACTION activation",
                "environmental context differs",
                "ActuatorSignal is equivalent numerically",
                "No result flag is supplied",
                "action does not contain consequence truth",
            ),
        ),
        "boundary clamp without callback": _has_all(
            text,
            (
                "physical clamp prevents position change",
                "next visual NFP may remain unchanged",
                "blocked=True",
                "success=False",
                "collision=True",
                "action consequence depends on world state",
            ),
        ),
        "harness action source only": _has_all(
            text,
            (
                "The test harness supplies ACTION NFPFrames",
                "validates causal mechanics only",
                "does not yet represent learned/selected behavior",
                "replace the harness action source",
                "internal action generation/selection",
            ),
        ),
        "no semantic command helpers": _has_all(
            text,
            (
                "move_left()",
                "move_right()",
                "stand_still()",
                "outside RNDeM cognitive code",
                "must not attach semantic metadata to the frame",
                "numeric activation tuples",
            ),
        ),
        "sensory return path uses existing transduction": _has_all(
            text,
            (
                "SyntheticClosedLoopVisualWorld",
                "VisualFieldSnapshot",
                "existing VisualFieldTransducer",
                "VISUAL EXTERNAL_SENSORY NFPFrame",
                "consequence is the subsequent sensory state",
            ),
        ),
        "no direct action sensory shortcut": _has_all(
            text,
            (
                "ActionTransducer",
                "directly constructs VISUAL consequence frame",
                "ACTION NFP",
                "-> actuator",
                "-> world",
                "-> sensor snapshot",
                "-> sensory transduction",
                "-> VISUAL NFP",
            ),
        ),
        "no direct experience write": _has_all(
            text,
            (
                "ExpSM record",
                "AKBSM relation",
                "chronicle entry",
                "reward update",
                "confidence update",
                "later learning/evaluation layers",
                "physical causality only",
            ),
        ),
        "future scenario coverage": _has_all(
            text,
            (
                "ACTION + ACTION_GENERATED frame accepted by ActionTransducer",
                "non-ACTION modality rejected",
                "ACTION + INTERNAL_REACTIVATION rejected",
                "wrong action topology rejected",
                "world transition returns no semantic outcome",
                "same ACTION values at different ticks are distinct occurrences",
                "action at tick T affects sensory observation at T+1",
                "same action + different world state produces different sensory consequence",
                "no direct action->VISUAL NFP shortcut",
                "no _run_tick integration",
            ),
        ),
        "replay safety rule": _has_all(
            text,
            (
                "Replay-Safety Rule",
                "ACTION modality + INTERNAL_REACTIVATION",
                "Remembering/replaying an action must not physically execute it",
                "ACTION + ACTION_GENERATED",
            ),
        ),
        "deferred scope": _has_all(
            text,
            (
                "autonomous action selection",
                "DecisionSelector integration",
                "`_run_tick()` integration",
                "ExpSM learning",
                "AKBSM learning",
                "credit assignment",
                "reward",
                "pain",
                "collision sensing",
                "proprioception",
                "action-window execution",
                "real physical actuators",
            ),
        ),
        "safety boundary": _has_all(
            text,
            (
                "documentation and verifier only",
                "does not implement actuation",
                "does not create `clc/actuation/`",
                "does not modify Memory",
                "semantic_core.json",
                "technical_feedback_patterns.json",
            ),
        ),
        "README reference": "docs/design_first_closed_loop_action_consequence.md" in readme
        and "verify_first_closed_loop_action_consequence_design.py" in readme,
        "contract reference": _has_all(
            contract,
            (
                "first closed-loop action/consequence design",
                "ACTION activation",
                "subsequent sensory activation",
                "not autonomous action selection",
            ),
        ),
        "transduction design reference": "first closed-loop action/consequence design" in transduction_design,
        "architecture reference": "first closed-loop action/consequence design" in architecture
        and "tools/verify_first_closed_loop_action_consequence_design.py" in architecture,
        "hygiene reference": "tools/verify_first_closed_loop_action_consequence_design.py" in hygiene,
        "actuation source not implemented": not ACTUATION_ROOT.exists(),
        "no forbidden root files": all(not (ROOT / name).exists() for name in FORBIDDEN_FILES),
        "existing safety still passes": _run_core_verifiers(),
    }
    passed = all(results.values())
    print("First Closed-Loop Action Consequence design verification:")
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
