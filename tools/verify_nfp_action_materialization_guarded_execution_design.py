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
HARDENED_CONTRACTS = {
    "pre-action context capture": (
        "captures `before_context_at_T` as the exact current",
        "before any call to `world.apply_actuator_signal()`",
        "frozen immutable dataclasses",
        "retaining that exact reference is reference-safe",
        "same object used for post-execution pending causal tracking",
        "must never sense the mutated world or reread a replacement context",
        "selection_context_end_tick == before_context_at_T.end_tick",
    ),
    "pending-slot preflight": (
        "pending_causal_transition is None",
        "CAUSAL_SLOT_OCCUPIED",
        "no pending overwrite/new pending",
        "Before world mutation, a read-only slot preflight",
        "serialized and single-threaded",
        "no reservation or lock",
    ),
    "post-execution tracking failure": (
        "If post-world `observe_action_frame()` fails",
        "ACTION_EXECUTED_CAUSAL_TRACKING_FAILED",
        "execution remains true",
        "no pending/recent transition is claimed",
        "World success followed by tracking failure cannot become a not-executed status",
        "`ACTION_EXECUTED_OBSERVATION_PENDING` means pending creation succeeded",
    ),
    "no rollback or reapplication": (
        "no automatic rollback",
        "actuator-signal reapplication",
        "rematerialization, guard/transducer rerun, or remembered-action retry",
        "world apply count == 1",
        "no rollback or retry",
    ),
    "execution-boundary taxonomy": (
        "PRE-EXECUTION / NOT EXECUTED",
        "POST-EXECUTION / EXECUTED",
        "`WORLD_EXECUTION_FAILED` is pre-execution only",
    ),
    "future injected scenarios": (
        "injected post-world pending-creation failure",
        "identical object is reused for pending creation",
        "preserves the old pending",
        "creates no fake transition",
    ),
}
ALLOWED = {
    "README.md", "docs/design_nfp_action_materialization_guarded_execution.md",
    "docs/design_nfp_expsm_operational_retrieval.md",
    "docs/design_first_closed_loop_action_consequence.md",
    "docs/design_nfp_context_and_short_memory.md",
    "docs/current_architecture_checkpoint.md", "docs/project_hygiene_audit.md",
    "tools/verify_nfp_action_materialization_guarded_execution_design.py",
    "tools/verify_nfp_expsm_operational_retrieval_design.py",
    "clc/actuation/__init__.py",
    "clc/actuation/remembered_action_execution.py",
    "clc/system/mode_action_guard.py",
    "scenarios/nfp_remembered_action_guarded_execution.json",
    "tools/verify_nfp_remembered_action_guarded_execution.py",
    "docs/debug_name_dependency_audit.json",
    "tools/verify_first_closed_loop_action_consequence.py",
    "docs/design_nfp_native_feedback.md",
    "docs/design_nfp_expsm_mutation_path.md",
    "docs/design_persistent_nfp_expsm_representation.md",
    "tools/verify_nfp_native_feedback_design.py",
    "clc/expsm/nfp_feedback_target.py",
    "clc/expsm/nfp_native_feedback.py",
    "scenarios/nfp_native_feedback_evaluation.json",
    "tools/verify_nfp_native_feedback_evaluation.py",
    "clc/expsm/nfp_operational_retrieval.py",
    "clc/expsm/expsm_activation_module.py",
    "clc/action/decision_selector.py",
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
    for group, contracts in HARDENED_CONTRACTS.items():
        for contract in contracts:
            if " ".join(contract.split()) not in normalized:
                failures.append(f"missing {group} contract: {contract}")

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
    hardened_count = sum(len(contracts) for contracts in HARDENED_CONTRACTS.values())
    print(f"contracts={len(SECTIONS) + len(TERMS) + hardened_count} changed_files={len(_changed())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
