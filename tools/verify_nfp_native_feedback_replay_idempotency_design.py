from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design_nfp_native_feedback_replay_idempotency.md"

SECTIONS = (
    "## Current Duplicate-Application Failure",
    "## Execution Occurrence Identity Audit",
    "## Canonical Feedback Event Identity",
    "## Evidence Digest Semantics",
    "## Event-Key Vs Payload Distinction",
    "## Durable Receipt Semantics",
    "## Chosen Persistence Architecture",
    "## Atomic Record+Receipt Commit",
    "## Crash Matrix",
    "## READBACK_FAILED Retry/Reconciliation",
    "## Concurrency / Lock Scope",
    "## Event Conflict Semantics",
    "## Policy Interaction",
    "## TargetCore Interaction",
    "## Storage Growth",
    "## Backward Compatibility / Migration",
    "## Runtime Integration Gate",
)

CONTRACTS = (
    "durable at-most-once mutation per canonical Feedback event",
    "execution_occurrence_id",
    "UUIDv4",
    "feedback_event_identity_version = 1",
    "source_experience_id",
    "Event identity answers **which observation**",
    "FeedbackEvidenceDigestV1",
    "feedback_evidence_digest_version = 1",
    "same key + same digest -> `ALREADY_APPLIED`",
    "same key + different digest -> `EVENT_CONFLICT`",
    "same occurrence + different source -> `EVENT_CONFLICT`",
    "same atomic authoritative ExpSM envelope",
    '"store_schema_version": 2',
    '"native_feedback_receipts"',
    '"execution_occurrence_index"',
    "exact 17-field",
    "One candidate envelope contains both the updated record",
    "Atomic replacement permits only the complete before-state",
    "`RECONCILED_APPLIED`",
    "`RECONCILED_NOT_APPLIED`",
    "`RECONCILIATION_CONFLICT`",
    "`threading.RLock`",
    "`fcntl.flock(LOCK_EX)`",
    "same event, two threads",
    "same event, two processes",
    "persist no receipt",
    "Receipts do not replace TargetCore",
    "Receipt metadata is excluded from TargetCore",
    "retained without eviction",
    "`applied_feedback_keys[-24:]`",
    "Production Memory migration remains deferred",
    "automatic learning, or `_run_tick()` wiring",
)

ALLOWED = {
    "docs/design_nfp_native_feedback_replay_idempotency.md",
    "docs/design_nfp_native_feedback.md",
    "docs/current_architecture_checkpoint.md",
    "tools/verify_nfp_native_feedback_design.py",
    "tools/verify_nfp_action_materialization_guarded_execution_design.py",
    "tools/verify_nfp_expsm_operational_retrieval_design.py",
    "tools/verify_nfp_native_feedback_replay_idempotency_design.py",
}

V1_FIELDS = {
    "record_id", "record_kind", "representation_version", "context_pattern",
    "action_pattern", "effect_pattern", "source_support_count",
    "source_proposal_id", "created_active_tick", "initialization_profile",
    "status", "created_at_world", "updated_at_world", "hits", "misses",
    "confidence", "repeatability",
}


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _class_fields(source: str, class_name: str) -> set[str]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    return set()


def _changed() -> set[str]:
    diff = subprocess.run(
        ["git", "diff", "--name-only", "main"], cwd=ROOT,
        text=True, capture_output=True, check=True,
    ).stdout.splitlines()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT,
        text=True, capture_output=True, check=True,
    ).stdout.splitlines()
    return set(diff) | {line[3:] for line in status if len(line) > 3}


def main() -> int:
    failures: list[str] = []
    design = DESIGN.read_text(encoding="utf-8") if DESIGN.exists() else ""
    normalized = " ".join(design.split())
    for requirement in (*SECTIONS, *CONTRACTS):
        if " ".join(requirement.split()) not in normalized:
            failures.append(f"missing design contract: {requirement}")

    ids = _source("clc/core/ids.py")
    runtime = _source("clc/runtime/clc_runtime.py")
    manager = _source("clc/context/context_memory_manager.py")
    execution = _source("clc/actuation/remembered_action_execution.py")
    transition = _source("clc/context/causal_transition.py")
    feedback = _source("clc/expsm/nfp_native_feedback.py")
    apply = _source("clc/expsm/nfp_native_feedback_apply.py")
    representation = _source("clc/experience/expsm_representation.py")
    transaction = _source("clc/consolidation/expsm_store_transaction.py")
    legacy = _source("clc/expsm/expsm_outcome_feedback.py")
    policy = _source("clc/runtime/memory_mutation_policy.py")

    evidence_fields = _class_fields(feedback, "NFPFeedbackEvidence")
    expected_evidence = {
        "source_experience_id", "target_core", "action_frame_id", "action_tick",
        "predicted_effect", "actual_effect", "effect_similarity",
        "agreement_threshold", "classification",
    }
    if evidence_fields != expected_evidence:
        failures.append(f"Feedback evidence fields drifted: {sorted(evidence_fields)}")

    record_fields = _class_fields(representation, "NFPExpSMRecordV1")
    creation_fields = _class_fields(representation, "NFPExpSMCreationMetadataV1")
    operational_fields = _class_fields(representation, "ExpSMOperationalMetadataV1")
    actual_v1 = (
        (record_fields - {"context", "action", "effect", "operational", "creation_metadata"})
        | {"record_kind", "representation_version", "context_pattern", "action_pattern", "effect_pattern"}
        | creation_fields | operational_fields
    )
    if actual_v1 != V1_FIELDS:
        failures.append(f"NFP_NATIVE_V1 schema drifted: {sorted(actual_v1)}")

    facts = {
        "frame IDs are process-local counters": (
            "defaultdict(int)" in ids
            and 'return f"{prefix}_{self._counters[prefix]:03d}"' in ids
            and 'self.id_gen.next("remembered_action_frame")' in execution
        ),
        "runtime recreates ID generator": "self.id_gen = IdGenerator()" in runtime,
        "active tick state restarts": "self._nfp_current_tick = 0" in manager,
        "transition identity restarts": (
            "self._next_transition_id = 1" in manager
            and 'f"causal_transition:{self._next_transition_id:06d}"' in manager
        ),
        "transition carries frame and ticks": all(token in transition for token in (
            "transition_id: str", "action_frame: NFPFrame", "action_tick: int",
            "observation_tick: int",
        )),
        "evidence currently lacks occurrence UUID": "execution_occurrence_id" not in evidence_fields,
        "current apply has no durable receipt": (
            "native_feedback_receipts" not in apply
            and "ALREADY_APPLIED" not in apply
            and "EVENT_CONFLICT" not in apply
        ),
        "apply uses fresh strict transaction": (
            "with self.transaction.mutation():" in apply
            and "store = self.transaction.load_strict()" in apply
        ),
        "readback recovery is read-only": (
            "def reconcile_nfp_feedback_readback_failure" in apply
            and "CONFIRMED_PERSISTED" in apply
            and "CONFIRMED_NOT_APPLIED" in apply
        ),
        "transaction lock is process-local": (
            "threading.RLock" in transaction and "fcntl" not in transaction and "flock" not in transaction
        ),
        "transaction uses atomic complete replacement": all(token in transaction for token in (
            "NamedTemporaryFile", "json.dump(store", "os.fsync", "temp_path.replace(self.store_path)",
        )),
        "store validator requires named sections": all(token in transaction for token in (
            'for section in ("experience", "reflexes")', "return raw",
        )),
        "canonical JSON helper exists": all(token in representation for token in (
            "sort_keys=True", 'separators=(",", ":")', "allow_nan=False",
        )),
        "legacy replay history is bounded": (
            'metadata["applied_feedback_keys"] = applied[-24:]' in legacy
        ),
        "policy modes and update gate exist": all(token in policy for token in (
            'SAFE_DEMO = "safe_demo"', 'DRAFT_ONLY = "draft_only"',
            'MUTATING_MEMORY = "mutating_memory"', "allow_expsm_update",
        )),
        "runtime has no native Feedback wiring": "NFPFeedback" not in runtime,
    }
    failures.extend(f"source fact drifted: {name}" for name, ok in facts.items() if not ok)

    store = json.loads((ROOT / "Memory/ExpSM/ExpSM_data.json").read_text(encoding="utf-8"))
    if not isinstance(store, dict) or set(store) != {"experience", "reflexes"}:
        failures.append(f"current ExpSM envelope drifted: {list(store) if isinstance(store, dict) else type(store)}")

    # This pass must remain docs/verifier-only and may not implement any designed type or store field.
    production_changes = {
        path for path in _changed()
        if path.startswith("clc/") or path.startswith("Memory/") or path.startswith("scenarios/")
    }
    if production_changes:
        failures.append(f"design pass changed production scope: {sorted(production_changes)}")
    unexpected = _changed() - ALLOWED
    if unexpected:
        failures.append(f"unexpected changed files: {sorted(unexpected)}")

    if failures:
        print("FAIL: durable NFP-native Feedback replay/idempotency design")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: durable NFP-native Feedback replay/idempotency design")
    print(
        f"sections={len(SECTIONS)} contracts={len(CONTRACTS)} "
        f"source_facts={len(facts)} evidence_fields={len(evidence_fields)} v1_fields={len(actual_v1)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
