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
    "## Execution-Status / Occurrence-ID Matrix",
    "## Canonical Feedback Event Identity",
    "## Evidence Digest Semantics",
    "## Event-Key Vs Payload Distinction",
    "## Durable Receipt Semantics",
    "## Chosen Persistence Architecture",
    "## Atomic Record+Receipt Commit",
    "## Crash Matrix",
    "## READBACK_FAILED Retry/Reconciliation",
    "## Concurrency / Lock Scope",
    "## Authoritative ExpSM Writer Inventory",
    "## Two-Stage Writer / Format Migration",
    "## Event Conflict Semantics",
    "## Policy Interaction",
    "## TargetCore Interaction",
    "## Storage Growth",
    "## Backward Compatibility / Migration",
    "## Durable Duplicate Protection Vs Pending-Event Durability",
    "## Runtime Integration Gate",
)

CONTRACTS = (
    "durable at-most-once mutation per canonical Feedback event",
    "execution_occurrence_id",
    "UUIDv4",
    "created exactly when the fresh current ACTION occurrence is successfully materialized",
    "execution **attempt**",
    "The ID is not proof that the world was changed",
    "Failures before successful materialization have no occurrence ID",
    "world.apply_actuator_signal()",
    "never regenerated at world execution, observation, evaluation, apply, reconciliation, or retry",
    "feedback_event_identity_version = 1",
    "source_experience_id",
    "Event identity answers **which observation**",
    "FeedbackEvidenceDigestV1",
    "feedback_evidence_digest_version = 1",
    "same key + same digest -> `ALREADY_APPLIED`",
    "`updated_at_world` remain byte/value unchanged",
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
    "`Memory/ExpSM/ExpSM_data.lock`",
    "never on the replaceable data file inode",
    "Linux/Fedora scoped",
    "no RLock-only fallback",
    "same event, two threads",
    "same event, two processes",
    "persist no receipt",
    "Receipts do not replace TargetCore",
    "Receipt metadata is excluded from TargetCore",
    "retained without eviction",
    "`applied_feedback_keys[-24:]`",
    "Production Memory migration remains deferred",
    "Stage 1 - persistence infrastructure compatibility",
    "Stage 2 - envelope v2 and durable receipts",
    "all authoritative writes remain in the current unversioned",
    "downgrading it or serializing only familiar record sections is prohibited",
    "stale S0-derived candidate as S2 and erase B",
    "unapplied event may be lost",
    "A receipt ledger is not a pending-event queue",
    "pre-apply event loss is acceptable or requires a durable outbox",
    "generated exactly once",
    "never call the clock again",
    "automatic learning, or `_run_tick()` wiring",
)

EXECUTION_STATUSES = (
    "STALE_SELECTION", "INVALID_SELECTED_EXPERIENCE", "CAUSAL_SLOT_OCCUPIED",
    "ACTUATOR_INCOMPATIBLE", "GUARD_DENIED", "TRANSDUCTION_REJECTED",
    "WORLD_EXECUTION_FAILED", "ACTION_EXECUTED_CAUSAL_TRACKING_FAILED",
    "ACTION_EXECUTED_OBSERVATION_PENDING", "EXECUTED_AND_OBSERVED",
)

STATUS_ROWS = (
    "| `STALE_SELECTION` | No | No | No | No |",
    "| `INVALID_SELECTED_EXPERIENCE` | No | No | No | No |",
    "| `CAUSAL_SLOT_OCCUPIED` | No | No | No | No |",
    "| `ACTUATOR_INCOMPATIBLE` | Yes | Yes, same attempt UUID | No | No |",
    "| `GUARD_DENIED` | Yes | Yes, same attempt UUID | No | No |",
    "| `TRANSDUCTION_REJECTED` | Yes | Yes, same attempt UUID | No | No |",
    "| `WORLD_EXECUTION_FAILED` | Yes | Yes, same attempt UUID | No successful execution | No |",
    "| `ACTION_EXECUTED_CAUSAL_TRACKING_FAILED` | Yes | Yes, fixed physical UUID | Yes | No grounded observation, so no |",
    "| `ACTION_EXECUTED_OBSERVATION_PENDING` | Yes | Yes, fixed physical UUID | Yes | Not yet; only after a matching completed transition |",
    "| `EXECUTED_AND_OBSERVED` | Yes | Yes, fixed physical UUID | Yes | Yes, subject to valid evaluator evidence |",
)

CRASH_POINTS = (
    "Before transaction begins",
    "After in-process RLock acquisition",
    "After interprocess flock acquisition",
    "After fresh authoritative read",
    "After receipt lookup confirms absent",
    "After target lookup / representation validation",
    "After TargetCore validation",
    "After policy validation",
    "After fresh operational metrics read",
    "After intended record + receipt constructed",
    "During temp-file write",
    "After file flush, before file fsync",
    "After file fsync, before atomic replace",
    "Immediately before atomic replace",
    "Immediately after atomic replace",
    "After replace, before directory fsync",
    "After best-effort directory fsync, before readback",
    "During readback",
    "After successful readback",
    "After result construction, before caller receives it",
)

MATRIX_COLUMNS = (
    "Crash point", "Authoritative record", "Authoritative receipt",
    "Mutation may already be authoritative?", "Blind mutation retry safe?",
    "Reconciliation required?", "Later retry behavior",
    "Visible result / uncertainty",
)

WRITER_INVENTORY = {
    "NFPExpSMCreateWriter": ("clc/experience/expsm_native_create.py", "write_complete_store"),
    "NFPFeedbackApplyWriter": ("clc/expsm/nfp_native_feedback_apply.py", "write_complete_store"),
    "ExpSMCommitWriter": ("clc/consolidation/expsm_commit_writer.py", "write_complete_store"),
    "ExpSMUpdateWriter": ("clc/consolidation/expsm_update_writer.py", "temp_path.replace(path)"),
    "ValueFeedbackUpdateWriter": ("clc/evaluation/value_feedback_update_writer.py", "self.transaction.write_complete_store(data)"),
    "ExpSMOutcomeFeedback": ("clc/expsm/expsm_outcome_feedback.py", "self.transaction.write_complete_store(data)"),
    "ExpSMCRUD": ("Memory/ExpSM/Exp_CRUD.py", "self.transaction.write_complete_store(self.data)"),
}

ALLOWED = {
    "docs/RND-015_legacy_native_joint_checkpoint.md",
    "tools/legacy_native_joint_checkpoint.py",
    "tools/verify_legacy_native_joint_checkpoint.py",
    "clc/runtime/native_bounded_delivery.py",
    "docs/RND-014_native_bounded_delivery.md",
    "tools/verify_native_bounded_delivery.py",
    # RND-013: approved exact Heart B2 integration paths.
    "clc/runtime/heart.py",
    "clc/runtime/synthetic_time_adapter.py",
    "clc/runtime/native_heart_session.py",
    "tools/verify_native_heart_b2.py",
    "docs/RND-013_native_heart_b2.md",
    "scenarios/support/synthetic_closed_loop_visual_world.py",
    # RND-011: reconcile ShortMemory assertions with existing Stage-2 contracts.
    "tools/verify_nfp_context_short_memory.py",
    "docs/RND-011_short_memory_contract_reconciliation.md",
    # RND-110/F01: public CRUD save regression coverage and audit/remediation.
    "tools/verify_expsm_crud_save_authority.py",
    "docs/RND-110_memory_write_authority_audit.md",
    "docs/design_nfp_native_feedback_replay_idempotency.md",
    "docs/design_nfp_native_feedback.md",
    "docs/current_architecture_checkpoint.md",
    "docs/debug_name_dependency_audit.json",
    "docs/debug_name_dependency_audit.md",
    "tools/verify_nfp_native_feedback_design.py",
    "tools/verify_nfp_action_materialization_guarded_execution_design.py",
    "tools/verify_nfp_expsm_operational_retrieval_design.py",
    "tools/verify_nfp_native_feedback_replay_idempotency_design.py",
    "README.md",
    "docs/design_nfp_expsm_mutation_path.md",
    "docs/design_persistent_nfp_expsm_representation.md",
    "docs/project_hygiene_audit.md",
    "clc/consolidation/expsm_store_transaction.py",
    "clc/consolidation/expsm_commit_writer.py",
    "clc/consolidation/expsm_update_writer.py",
    "clc/evaluation/value_feedback_update_writer.py",
    "clc/experience/expsm_native_create.py",
    "clc/expsm/expsm_outcome_feedback.py",
    "clc/expsm/nfp_native_feedback_apply.py",
    "Memory/ExpSM/Exp_CRUD.py",
    "scenarios/expsm_persistence_stage1.json",
    "tools/verify_expsm_persistence_stage1.py",
    "tools/verify_expsm_mechanism_action_source.py",
    "tools/verify_value_feedback_memory_view.py",
    "clc/actuation/remembered_action_execution.py",
    "clc/context/causal_transition.py",
    "clc/context/context_memory_manager.py",
    "clc/expsm/nfp_native_feedback.py",
    "scenarios/nfp_native_feedback_replay_idempotency.json",
    "tools/verify_nfp_native_feedback_apply.py",
    "tools/verify_nfp_native_feedback_evaluation.py",
    "tools/verify_nfp_native_feedback_replay_idempotency.py",
    "tools/verify_nfp_remembered_action_guarded_execution.py",
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
    for status in EXECUTION_STATUSES:
        if f"`{status}`" not in design:
            failures.append(f"execution-status matrix missing: {status}")
    for row in STATUS_ROWS:
        if row not in design:
            failures.append(f"execution-status matrix semantics drifted: {row}")
    for point in CRASH_POINTS:
        if point not in design:
            failures.append(f"crash matrix missing point: {point}")
            continue
        matrix_row = next((line for line in design.splitlines() if line.startswith(f"| {point} |")), "")
        if len(matrix_row.strip().strip("|").split("|")) != len(MATRIX_COLUMNS):
            failures.append(f"crash matrix row has wrong dimension count: {point}")
    for column in MATRIX_COLUMNS:
        if column not in design:
            failures.append(f"crash matrix missing dimension: {column}")
    lock_order = (
        "acquire the existing process-wide/path-local in-process `RLock`",
        "open the stable sibling lock file",
        "acquire `fcntl.flock(lock_fd, LOCK_EX)`",
        "fresh-read",
        "release flock",
        "close the lock file",
        "release the in-process `RLock`",
    )
    positions = [design.find(term) for term in lock_order]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        failures.append("canonical lock acquisition/release order is missing or inconsistent")
    for writer in WRITER_INVENTORY:
        if f"`{writer}`" not in design and writer != "ExpSMCRUD":
            failures.append(f"writer migration inventory missing: {writer}")
        if writer == "ExpSMCRUD" and "ExpSMCRUD" not in design:
            failures.append("writer migration inventory missing: ExpSMCRUD")

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
        "agreement_threshold", "classification", "execution_occurrence_id",
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
        "all guarded execution statuses audited": all(
            f"{status} =" in execution for status in EXECUTION_STATUSES
        ),
        "evidence carries occurrence UUID": "execution_occurrence_id" in evidence_fields,
        "apply has durable replay semantics": (
            "native_feedback_receipts" in apply
            and "ALREADY_APPLIED" in apply
            and "EVENT_CONFLICT" in apply
        ),
        "apply uses fresh strict transaction": (
            "with self.transaction.mutation():" in apply
            and "store = self.transaction.load_for_mutation_strict()" in apply
        ),
        "readback recovery is read-only": (
            "def reconcile_nfp_feedback_readback_failure" in apply
            and "CONFIRMED_PERSISTED" in apply
            and "CONFIRMED_NOT_APPLIED" in apply
        ),
        "Stage-1 transaction has shared process and stable-file locks": (
            "threading.RLock" in transaction
            and "fcntl.flock(descriptor, fcntl.LOCK_EX)" in transaction
            and 'self.lock_path = self.store_path.with_suffix(".lock")' in transaction
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
    for writer, (relative, write_marker) in WRITER_INVENTORY.items():
        writer_source = _source(relative)
        facts[f"authoritative writer exists: {writer}"] = (
            f"class {writer}" in writer_source and write_marker in writer_source
        )
    failures.extend(f"source fact drifted: {name}" for name, ok in facts.items() if not ok)

    store = json.loads((ROOT / "Memory/ExpSM/ExpSM_data.json").read_text(encoding="utf-8"))
    if not isinstance(store, dict) or set(store) != {"experience", "reflexes"}:
        failures.append(f"current ExpSM envelope drifted: {list(store) if isinstance(store, dict) else type(store)}")

    # Stage 2 must be explicit and remain isolated from automatic runtime wiring.
    if "execution_occurrence_id" not in execution or "execution_occurrence_id" not in transition:
        failures.append("Stage-2 occurrence identity is not propagated through execution/causality")
    if "ALREADY_APPLIED" not in apply or "EVENT_CONFLICT" not in apply:
        failures.append("Stage-2 replay result statuses are absent")
    if "NFPFeedbackApplyWriter" in runtime:
        failures.append("Stage-2 apply leaked into automatic runtime wiring")
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
