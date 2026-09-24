from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design_nfp_action_materialization_guarded_execution.md"
GUARD = ROOT / "clc/system/mode_action_guard.py"
TRANSDUCER = ROOT / "clc/actuation/motor.py"
CONTEXT = ROOT / "clc/context/context_memory_manager.py"
SELECTED = ROOT / "clc/expsm/nfp_operational_retrieval.py"

SECTIONS = (
    "## Current Action-Path Audit", "## Actual ModeActionGuard Audit",
    "## Actual ActionTransducer Audit", "## Actual ContextMemory Causality Audit",
    "## Selection Freshness Contract", "## Materialization Model",
    "## Persistent Validation And Actuator Compatibility",
    "## Guarded Execution Ordering", "## Observation And Pending Semantics",
    "## Predicted Effect And Actual Consequence", "## Execution Result Model",
    "## Deferred Feedback Handoff", "## Required Isolated Scenarios",
    "## Runtime And Authority Boundaries",
)
TERMS = (
    "remembered ACTION structure != historical ACTION occurrence",
    "SelectedNFPExpSMExperience", "selection_context_end_tick",
    "STALE_SELECTION", "automatic re-retrieval", "NFPActionOccurrenceMaterializer",
    "MaterializedNFPActionIntent", "ACTION_GENERATED", "source_experience_id",
    "not derived from `source_experience_id`", "leaves frame provenance unset",
    "PatternTopology((2,))", "never resized, truncated, padded, remapped",
    "typed extension of the existing guard architecture", "GUARD_DENIED",
    "TRANSDUCTION_REJECTED", "acceptance/external-execution boundary",
    "only after normal return confirms external execution",
    "ACTION_EXECUTED_OBSERVATION_PENDING", "expire_pending_if_overdue()",
    "world snapshot -> `VisualFieldTransducer`", "Stored predicted effect != actual consequence",
    "cannot modify ACTION", "PendingCausalTransition -> RecentCausalTransition",
    "Feedback evaluation", "writes no ExpSM, AKBSM", "does not change `_run_tick()`",
    "never call execution automatically",
)
ALLOWED = {
    "README.md", "docs/design_nfp_action_materialization_guarded_execution.md",
    "docs/design_nfp_expsm_operational_retrieval.md",
    "docs/design_first_closed_loop_action_consequence.md",
    "docs/design_nfp_context_and_short_memory.md",
    "docs/current_architecture_checkpoint.md", "docs/project_hygiene_audit.md",
    "tools/verify_nfp_action_materialization_guarded_execution_design.py",
    "tools/verify_nfp_expsm_operational_retrieval_design.py",
}


def _changed() -> set[str]:
    diff = subprocess.run(["git", "diff", "--name-only", "main"], cwd=ROOT,
                          text=True, capture_output=True, check=True).stdout.splitlines()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            text=True, capture_output=True, check=True).stdout.splitlines()
    return set(diff) | {line[3:] for line in status if len(line) > 3}


def _class_has_method(path: Path, class_name: str, method: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(isinstance(node, ast.ClassDef) and node.name == class_name and
               any(isinstance(item, ast.FunctionDef) and item.name == method for item in node.body)
               for node in tree.body)


def main() -> int:
    failures: list[str] = []
    text = DESIGN.read_text(encoding="utf-8") if DESIGN.exists() else ""
    normalized = " ".join(text.split())
    for required in (*SECTIONS, *TERMS):
        if " ".join(required.split()) not in normalized:
            failures.append(f"missing design contract: {required}")

    guard = GUARD.read_text(encoding="utf-8")
    transducer = TRANSDUCER.read_text(encoding="utf-8")
    context = CONTEXT.read_text(encoding="utf-8")
    facts = {
        "guard pattern ID": "def is_allowed(self, action_pattern_id: str" in guard,
        "guard ActionCandidate": "candidate: ActionCandidate" in guard,
        "transducer frame": "def transduce(self, action_frame: NFPFrame)" in transducer,
        "transducer modality": "PatternModality.ACTION" in transducer,
        "transducer origin": "PatternOrigin.ACTION_GENERATED" in transducer,
        "transducer topology": "ACTION_MOTOR_TOPOLOGY = PatternTopology((2,))" in transducer,
        "pending open": "def observe_action_frame" in context,
        "pending completion": "RecentCausalTransition(" in context,
        "pending expiry": "def expire_pending_if_overdue" in context,
        "selected remains data": not any(_class_has_method(
            SELECTED, "SelectedNFPExpSMExperience", method
        ) for method in ("execute", "act", "send_to_world")),
    }
    failures.extend(f"audited source fact drifted: {name}" for name, ok in facts.items() if not ok)
    unexpected = sorted(_changed() - ALLOWED)
    if unexpected:
        failures.append(f"unexpected changed files: {unexpected}")

    if failures:
        print("FAIL: NFP remembered-action guarded-execution design")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: NFP remembered-action guarded-execution design")
    print(f"contracts={len(SECTIONS) + len(TERMS)} changed_files={len(_changed())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
