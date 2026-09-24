from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design_nfp_native_feedback.md"
FEEDBACK = ROOT / "clc/expsm/expsm_outcome_feedback.py"
EFFECTS = ROOT / "clc/experience/effects.py"
REPRESENTATION = ROOT / "clc/experience/expsm_representation.py"
POLICY = ROOT / "clc/runtime/memory_mutation_policy.py"
TRANSACTION = ROOT / "clc/consolidation/expsm_store_transaction.py"
EXECUTION = ROOT / "clc/actuation/remembered_action_execution.py"
TRANSITION = ROOT / "clc/context/causal_transition.py"
LEGACY_CRUD = ROOT / "Memory/ExpSM/Exp_CRUD.py"

SECTIONS = (
    "## Current Legacy Feedback Audit", "## Observed Effect Audit",
    "## Direct Structural Comparator", "## Evaluation Result Model",
    "## Persistent V1 Field Audit", "## NFPFeedbackTargetCore Exact Schema",
    "## TargetCore Origin, Propagation, And Lifetime",
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
    "source_experience_id` answers **which record was selected",
    "TargetCore never replaces or duplicates the record ID",
    "C2 == C", "transient / ephemeral", "cognitively inert",
    "not a new ExpSM persisted schema field", "does not affect context similarity",
    "-> NFP retrieval candidate", "-> selected native result",
    "-> remembered-action execution result", "-> native Feedback evidence",
    "-> fresh authoritative apply read of record R",
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

V1_FIELDS = {
    "record_id", "record_kind", "representation_version", "context_pattern",
    "action_pattern", "effect_pattern", "source_support_count",
    "source_proposal_id", "created_active_tick", "initialization_profile",
    "status", "created_at_world", "updated_at_world", "hits", "misses",
    "confidence", "repeatability",
}
TARGET_CORE_INCLUDED = {
    "record_kind", "representation_version", "context_pattern", "action_pattern",
    "effect_pattern", "source_support_count", "source_proposal_id",
    "created_active_tick", "initialization_profile", "created_at_world",
}
TARGET_CORE_EXCLUDED = V1_FIELDS - TARGET_CORE_INCLUDED
TARGET_CONTRACTS = {
    "TargetCore origin": (
        "constructed during retrieval/candidate creation",
        "same fresh authoritative `NFPExpSMRecordV1`",
        "not constructed from selected ACTION alone",
    ),
    "TargetCore propagation record-to-candidate": (
        "-> NFP retrieval candidate (source_experience_id=R, target_core=C)",
    ),
    "TargetCore propagation candidate-to-selection": (
        "-> selected native result (source_experience_id=R, target_core=C)",
    ),
    "TargetCore propagation selection-to-execution": (
        "-> remembered-action execution result (source_experience_id=R, target_core=C)",
    ),
    "TargetCore propagation execution-to-evidence": (
        "-> native Feedback evidence (source_experience_id=R, target_core=C)",
    ),
    "TargetCore propagation evidence-to-apply": (
        "-> fresh authoritative apply read of record R (derive C2; compare C2 == C)",
    ),
    "TargetCore no downstream reconstruction": (
        "MUST NOT reconstruct TargetCore from ACTION, predicted effect, record ID, or execution frame",
    ),
    "TargetCore lifetime": (
        "transient / ephemeral", "not a new ExpSM persisted schema field",
        "authoritative retrieval read -> selection -> execution -> explicit Feedback apply",
    ),
    "TargetCore cognitive inertness": (
        "context similarity", "Activation", "top-N", "DecisionSelector scoring",
        "guard decisions", "world physics", "predicted/actual comparison score",
    ),
    "TargetCore exact comparison": (
        "exact typed structural equality", "C2 == C", "There is no tolerance",
    ),
    "TargetCore status decision": ("`status` from TargetCore", "EXCLUDES `status`"),
    "TargetCore created_at_world decision": ("`created_at_world`", "so it is INCLUDED"),
}


def class_fields(tree: ast.Module, name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return {
                item.target.id for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    return set()


def field_audit(text: str) -> dict[str, str]:
    start = "<!-- NFP_V1_FIELD_AUDIT_START -->"
    end = "<!-- NFP_V1_FIELD_AUDIT_END -->"
    if start not in text or end not in text:
        return {}
    block = text.split(start, 1)[1].split(end, 1)[0]
    rows: dict[str, str] = {}
    for line in block.splitlines():
        if not line.startswith("| `"):
            continue
        field = line.split("`", 2)[1]
        if field in rows:
            rows[field] = "DUPLICATE"
        else:
            rows[field] = line
    return rows


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
    for contract, required_terms in TARGET_CONTRACTS.items():
        missing = [term for term in required_terms if " ".join(term.split()) not in normalized]
        if missing:
            failures.append(f"{contract} missing: {missing}")

    representation = REPRESENTATION.read_text(encoding="utf-8")
    representation_tree = ast.parse(representation)
    actual_record_fields = class_fields(representation_tree, "NFPExpSMRecordV1")
    actual_creation_fields = class_fields(representation_tree, "NFPExpSMCreationMetadataV1")
    actual_operational_fields = class_fields(representation_tree, "ExpSMOperationalMetadataV1")
    actual_v1_fields = (
        (actual_record_fields - {"context", "action", "effect", "operational", "creation_metadata"})
        | {"context_pattern", "action_pattern", "effect_pattern", "record_kind", "representation_version"}
        | actual_creation_fields | actual_operational_fields
    )
    if actual_v1_fields != V1_FIELDS:
        failures.append(
            "current V1 schema drifted: expected "
            f"{sorted(V1_FIELDS)}, found {sorted(actual_v1_fields)}"
        )
    rows = field_audit(text)
    if set(rows) != actual_v1_fields:
        failures.append(
            "persistent V1 field audit mismatch: "
            f"missing={sorted(actual_v1_fields - set(rows))} "
            f"extra={sorted(set(rows) - actual_v1_fields)}"
        )
    for field in sorted(actual_v1_fields):
        row = rows.get(field, "")
        if row == "DUPLICATE":
            failures.append(f"persistent V1 field audit duplicates {field}")
        decision = "INCLUDED" if field in TARGET_CORE_INCLUDED else "EXCLUDED"
        if row and f"| {decision} |" not in row:
            failures.append(f"TargetCore contract missing decision for {field}: expected {decision}")

    feedback = FEEDBACK.read_text(encoding="utf-8")
    effects = EFFECTS.read_text(encoding="utf-8")
    policy = POLICY.read_text(encoding="utf-8")
    transaction = TRANSACTION.read_text(encoding="utf-8")
    execution = EXECUTION.read_text(encoding="utf-8")
    transition = TRANSITION.read_text(encoding="utf-8")
    legacy_crud = LEGACY_CRUD.read_text(encoding="utf-8")
    facts = {
        "legacy semantic statuses": all(token in feedback for token in
            ('"confirmed"', '"partially_confirmed"', '"failed"', '"expired"')),
        "legacy exact target": 'experience_id = str(' in feedback and 'experiences.get(experience_id)' in feedback,
        "legacy hit/miss increments": 'new_hits = old_hits + (1 if status in {"hit", "partial_hit"}' in feedback
            and 'new_misses = old_misses + (1 if status == "miss"' in feedback,
        "post-increment confidence sequencing": "_confidence_from_simple_feedback(new_hits, new_misses)" in feedback,
        "post-increment repeatability sequencing": "evidence_total = new_hits + new_misses" in feedback,
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
        "V1 serializer keys": all(token in representation for token in (
            '"record_kind": self.record_kind', '"representation_version": self.representation_version',
            '"context_pattern": self.context.to_json_data()', '"action_pattern": self.action.to_json_data()',
            '"effect_pattern": self.effect.to_json_data()', '"status": self.status',
            '"created_at_world"', '"updated_at_world"')),
        "V1 exact operational fields": actual_operational_fields == {"hits", "misses", "confidence", "repeatability"},
        "V1 exact creation fields": actual_creation_fields == {
            "source_support_count", "source_proposal_id", "created_active_tick", "initialization_profile"},
        "legacy lifecycle status mutation": '["status"] = "archived"' in legacy_crud,
        "legacy updated timestamp mutation": '["updated_at_world"] = self._now_world()' in legacy_crud,
        "legacy creation timestamp initialization": '"created_at_world": created_at_world or now' in legacy_crud,
        "legacy feedback writes exact operational fields": all(
            f'record["{field}"]' in feedback
            for field in ("hits", "misses", "confidence", "repeatability")
        ),
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
    print(
        f"contracts={len(SECTIONS) + len(TERMS)} source_facts={len(facts)} "
        f"v1_fields={len(actual_v1_fields)} target_core_fields={len(TARGET_CORE_INCLUDED)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
