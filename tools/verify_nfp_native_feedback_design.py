from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design_nfp_native_feedback.md"
FEEDBACK = ROOT / "clc/expsm/expsm_outcome_feedback.py"
EFFECTS = ROOT / "clc/experience/effects.py"
POLICY = ROOT / "clc/runtime/memory_mutation_policy.py"
TRANSACTION = ROOT / "clc/consolidation/expsm_store_transaction.py"
EXECUTION = ROOT / "clc/actuation/remembered_action_execution.py"
TRANSITION = ROOT / "clc/context/causal_transition.py"

SECTIONS = (
    "## Current Legacy Feedback Audit", "## Observed Effect Audit",
    "## Direct Structural Comparator", "## Evaluation Result Model",
    "## Exact Target And Fresh Read", "## Native Operational Update",
    "## Policy And Transaction Boundary", "## Replay Decision And Concurrency Scope",
    "## Required Isolated Scenarios", "## Authority Boundary",
)
TERMS = (
    "prediction reliability", "not NFP prediction-reliability semantics",
    "source_experience_id", "Similar neighbors, top-N losers",
    "ObservedEffectExtractor.extract(transition)", "after_i - before_i", "[-1,1]",
    "effect_similarity = 1 - mean_abs_error / 2", "native_effect_agreement_threshold",
    "score equal to the threshold is a HIT", "INCOMPARABLE_EFFECT",
    "TRANSITION_MISMATCH", "OBSERVATION_PENDING", "CAUSAL_TRACKING_UNAVAILABLE",
    "HIT  -> hits + 1; misses unchanged", "MISS -> misses + 1; hits unchanged",
    "Viability remains derived", "evaluation never writes", "freshly load",
    "ExpSMRecordAdapter", "STALE_OR_CHANGED_TARGET", "allow_expsm_update",
    "safe_demo", "draft_only", "mutating_memory", "ExpSMStoreTransaction",
    "NFPFeedbackTargetCore", "current `SelectedNFPExpSMExperience` does not carry serialized context",
    "Without this handoff, native apply must remain unavailable",
    "WRITE_FAILED", "READBACK_FAILED", "no blind retry", "CONFIRMED_PERSISTED",
    "CONFIRMED_ABSENT", "UNRESOLVED_OR_STORE_INVALID", "serialized single application",
    "no claim of crash-safe idempotency", "BLOCKS `_run_tick()`",
    "INTERNAL_REACTIVATION", "No replay field is silently added",
)
ALLOWED = {
    "README.md", "docs/design_nfp_native_feedback.md",
    "docs/design_nfp_action_materialization_guarded_execution.md",
    "docs/design_nfp_expsm_operational_retrieval.md",
    "docs/design_persistent_nfp_expsm_representation.md",
    "docs/design_nfp_expsm_mutation_path.md",
    "docs/current_architecture_checkpoint.md", "docs/project_hygiene_audit.md",
    "tools/verify_nfp_native_feedback_design.py",
    "tools/verify_nfp_action_materialization_guarded_execution_design.py",
    "tools/verify_nfp_expsm_operational_retrieval_design.py",
}


def changed() -> set[str]:
    diff = subprocess.run(["git", "diff", "--name-only", "main"], cwd=ROOT,
                          text=True, capture_output=True, check=True).stdout.splitlines()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            text=True, capture_output=True, check=True).stdout.splitlines()
    return set(diff) | {line[3:] for line in status if len(line) > 3}


def main() -> int:
    failures: list[str] = []
    text = DESIGN.read_text(encoding="utf-8") if DESIGN.exists() else ""
    normalized = " ".join(text.split())
    for required in (*SECTIONS, *TERMS):
        if " ".join(required.split()) not in normalized:
            failures.append(f"missing design contract: {required}")

    feedback = FEEDBACK.read_text(encoding="utf-8")
    effects = EFFECTS.read_text(encoding="utf-8")
    policy = POLICY.read_text(encoding="utf-8")
    transaction = TRANSACTION.read_text(encoding="utf-8")
    execution = EXECUTION.read_text(encoding="utf-8")
    transition = TRANSITION.read_text(encoding="utf-8")
    facts = {
        "legacy semantic statuses": all(token in feedback for token in
            ('"confirmed"', '"partially_confirmed"', '"failed"', '"expired"')),
        "legacy exact target": 'experience_id = str(' in feedback and 'experiences.get(experience_id)' in feedback,
        "legacy hit/miss increments": 'new_hits = old_hits + (1 if status in {"hit", "partial_hit"}' in feedback
            and 'new_misses = old_misses + (1 if status == "miss"' in feedback,
        "confidence constants": all(token in feedback for token in
            ("FEEDBACK_CONFIDENCE_CAP = 0.60", "HIT_SATURATION = 20.0",
             "CONFIDENCE_SMOOTHING_OLD = 0.75", "CONFIDENCE_SMOOTHING_NEW = 0.25",
             "LEGACY_CONFIDENCE_SOFT_CAP = 0.75")),
        "repeatability constants": "REPEATABILITY_CAP = 0.90" in feedback
            and "REPEATABILITY_SATURATION = 10.0" in feedback,
        "bounded replay": "applied_feedback_keys" in feedback and "applied[-24:]" in feedback,
        "effect extraction": "after_value - before_value" in effects,
        "effect bounds": "value < -1.0 or value > 1.0" in effects,
        "effect similarity": "1.0 - (distance / len(left.delta_values)) / 2.0" in effects,
        "strict t plus one": "observation_tick != self.action_tick + 1" in effects,
        "policy modes": all(token in policy for token in
            ('SAFE_DEMO = "safe_demo"', 'DRAFT_ONLY = "draft_only"',
             'MUTATING_MEMORY = "mutating_memory"')),
        "update policy only mutating": policy.count("allow_expsm_update=False") >= 2
            and "allow_expsm_update=True" in policy,
        "atomic replace": "NamedTemporaryFile" in transaction and "os.fsync" in transaction
            and "temp_path.replace(self.store_path)" in transaction,
        "execution statuses": all(token in execution for token in
            ("EXECUTED_AND_OBSERVED", "ACTION_EXECUTED_CAUSAL_TRACKING_FAILED",
             "ACTION_EXECUTED_OBSERVATION_PENDING", "GUARD_DENIED")),
        "transition action identity": "action_frame: NFPFrame" in transition
            and "self.action_frame.active_tick != self.action_tick" in transition,
        "no implementation": not (ROOT / "clc/expsm/nfp_native_feedback.py").exists(),
        "runtime unchanged": "NFPFeedback" not in (ROOT / "clc/runtime/clc_runtime.py").read_text(encoding="utf-8"),
    }
    failures.extend(f"current source fact drifted: {name}" for name, ok in facts.items() if not ok)
    unexpected = sorted(changed() - ALLOWED)
    if unexpected:
        failures.append(f"unexpected changed files: {unexpected}")
    if failures:
        print("FAIL: NFP-native Feedback design")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: NFP-native Feedback design")
    print(f"contracts={len(SECTIONS) + len(TERMS)} source_facts={len(facts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
