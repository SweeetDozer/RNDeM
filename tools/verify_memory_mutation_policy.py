from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.value_feedback_update_writer import ValueFeedbackUpdateWriter
from clc.runtime.clc_runtime import CLCRuntime
from clc.runtime.memory_mutation_policy import RuntimeProfile, policy_for_profile
from clc.system.system_state import SystemState


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"


def main() -> int:
    before = _real_hashes()
    with tempfile.TemporaryDirectory(prefix="rndem_policy_verify_") as temp_dir:
        temp_root = Path(temp_dir)
        temp_memory = temp_root / "Memory"
        shutil.copytree(ROOT / "Memory", temp_memory)
        results = {
            "direct_runtime_safe_default": _case_direct_safe_default(before),
            "safe_demo_temp_behavior": _case_safe_demo_main(before),
            "draft_only_behavior": _case_draft_only(temp_memory),
            "mutating_memory_temp_fixture": _case_mutating_temp_fixture(temp_memory),
            "writer_gate_behavior": _case_writer_gates(temp_memory),
        }
    after = _real_hashes()
    results["real_expsm_hash_unchanged"] = after["expsm"] == before["expsm"] == EXP_HASH
    results["real_akbsm_hash_unchanged"] = after["akbsm"] == before["akbsm"] == AKB_HASH
    results["semantic_core_unchanged"] = after["semantic_core"] == before["semantic_core"]
    results["technical_feedback_unchanged"] = after["technical_feedback"] == before["technical_feedback"]

    print("Memory mutation policy verification:")
    for key, value in results.items():
        print(f"  {key}: {'yes' if value else 'no'}")
    passed = all(results.values())
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_direct_safe_default(before: dict[str, str | None]) -> bool:
    runtime = CLCRuntime(ROOT / "Memory")
    policy = runtime.memory_mutation_policy
    blocked = _blocked_runtime_writer_attempts(runtime)
    after = _real_hashes()
    return (
        policy.profile == RuntimeProfile.SAFE_DEMO
        and policy.allow_draft_writes is False
        and policy.allow_expsm_commit is False
        and policy.allow_expsm_update is False
        and policy.allow_value_feedback_update is False
        and policy.akbsm_draft_proposals_enabled is False
        and blocked
        and after["expsm"] == before["expsm"]
        and after["drafts"] == before["drafts"]
        and after["akbsm"] == before["akbsm"]
    )


def _case_safe_demo_main(before: dict[str, str | None]) -> bool:
    proc = subprocess.run([sys.executable, "-B", "main.py"], cwd=ROOT, text=True, capture_output=True)
    after = _real_hashes()
    return (
        proc.returncode == 0
        and "decision cycle summaries:" in proc.stdout
        and after["expsm"] == before["expsm"]
        and after["drafts"] == before["drafts"]
        and after["akbsm"] == before["akbsm"]
    )


def _case_draft_only(temp_memory: Path) -> bool:
    runtime = CLCRuntime(temp_memory, profile=RuntimeProfile.DRAFT_ONLY, memory_is_temporary=True)
    policy = runtime.memory_mutation_policy
    blocked = _blocked_runtime_writer_attempts(runtime, expected_blocked=("commit", "update", "value"))
    return (
        policy.allow_draft_writes is True
        and policy.allow_expsm_commit is False
        and policy.allow_expsm_update is False
        and policy.allow_value_feedback_update is False
        and policy.allow_akbsm_write is False
        and policy.akbsm_draft_proposals_enabled is False
        and blocked
    )


def _case_mutating_temp_fixture(temp_memory: Path) -> bool:
    expsm_path = temp_memory / "ExpSM" / "ExpSM_data.json"
    before_real = _real_hashes()
    before_temp = _hash_file(expsm_path)
    registry = PatternRegistry(temp_memory / "pattern_manifest.json")
    id_gen = IdGenerator()
    memory = ContextMemory(id_gen, registry)
    state = SystemState(mode="consolidation")
    policy = policy_for_profile(RuntimeProfile.MUTATING_MEMORY, memory_root=temp_memory, memory_is_temporary=True)
    writer = ValueFeedbackUpdateWriter(id_gen, registry, expsm_path, policy)
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.VALUE_FEEDBACK_REVIEW,
            1,
            "verify_memory_mutation_policy",
            None,
            _ready_value_review(registry),
        )
    )
    operations = writer.run(2, memory, state)
    after_temp = _hash_file(expsm_path)
    after_real = _real_hashes()
    return (
        policy.allow_value_feedback_update is True
        and policy.akbsm_draft_proposals_enabled is False
        and policy.allow_akbsm_write is False
        and any(operation.marker == OperationMarker.VALUE_FEEDBACK_UPDATED for operation in operations)
        and before_temp != after_temp
        and after_real == before_real
    )


def _case_writer_gates(temp_memory: Path) -> bool:
    runtime = CLCRuntime(temp_memory, profile=RuntimeProfile.SAFE_DEMO, memory_is_temporary=False)
    before = {
        "expsm": _hash_file(temp_memory / "ExpSM" / "ExpSM_data.json"),
        "drafts": _hash_file(temp_memory / "ExpSM" / "ExpSM_drafts.json"),
        "akbsm": _hash_file(temp_memory / "AKBSM" / "AKBSM_ne.json"),
    }
    blocked = _blocked_runtime_writer_attempts(runtime)
    after = {
        "expsm": _hash_file(temp_memory / "ExpSM" / "ExpSM_data.json"),
        "drafts": _hash_file(temp_memory / "ExpSM" / "ExpSM_drafts.json"),
        "akbsm": _hash_file(temp_memory / "AKBSM" / "AKBSM_ne.json"),
    }
    return blocked and before == after


def _blocked_runtime_writer_attempts(
    runtime: CLCRuntime,
    expected_blocked: tuple[str, ...] = ("draft", "commit", "update", "value"),
) -> bool:
    memory = ContextMemory(runtime.id_gen, runtime.pattern_registry)
    state = SystemState(mode="consolidation")
    state.runtime_profile = runtime.memory_mutation_policy.profile.value
    state.memory_mutation_policy = runtime.memory_mutation_policy.summary()
    tick = 100
    _add_decision(memory, runtime, tick, runtime.memory_draft_writer.store_action_id)
    memory.add_event(
        ContextOperation(
            runtime.id_gen.next("op"),
            OperationMarker.MEMORY_WRITE_REVIEW,
            tick,
            "verify_memory_mutation_policy",
            None,
            {
                "review_id": "review_policy_block",
                "review_status": "approved_for_expsm",
                "write_status": "approved_pending_writer",
            },
        )
    )
    draft_ops = runtime.memory_draft_writer.run(tick, memory, runtime.active_field, state)
    _add_decision(memory, runtime, tick + 1, runtime.expsm_commit_writer.commit_action_id)
    commit_ops = runtime.expsm_commit_writer.run(tick + 1, memory, runtime.active_field, state)
    _add_decision(memory, runtime, tick + 2, runtime.expsm_update_writer.update_action_id)
    update_ops = runtime.expsm_update_writer.run(tick + 2, memory, runtime.active_field, state)
    memory.add_event(
        ContextOperation(
            runtime.id_gen.next("op"),
            OperationMarker.VALUE_FEEDBACK_REVIEW,
            tick + 3,
            "verify_memory_mutation_policy",
            None,
            _ready_value_review(runtime.pattern_registry),
        )
    )
    value_ops = runtime.value_feedback_update_writer.run(tick + 4, memory, state)
    groups = {
        "draft": draft_ops,
        "commit": commit_ops,
        "update": update_ops,
        "value": value_ops,
    }
    for key in expected_blocked:
        if not _has_policy_block(groups[key]):
            return False
    return True


def _add_decision(memory: ContextMemory, runtime: CLCRuntime, tick: int, action_pattern_id: str) -> None:
    memory.add_event(
        ContextOperation(
            runtime.id_gen.next("op"),
            OperationMarker.INTERNAL_DECISION,
            tick,
            "verify_memory_mutation_policy",
            None,
            {
                "decision_id": runtime.id_gen.next("decision"),
                "decision_pattern_id": action_pattern_id,
                "system_mode_at_selection": "consolidation",
                "candidate_score": 0.9,
            },
        )
    )


def _has_policy_block(operations: list[ContextOperation]) -> bool:
    return any(
        operation.marker == OperationMarker.MODULE_UPDATE
        and operation.payload.get("blocked_by_policy") is True
        and operation.payload.get("write_allowed") is False
        for operation in operations
    )


def _ready_value_review(registry: PatternRegistry) -> dict[str, Any]:
    target_pattern = registry.id("evaluation_useful_target")
    return {
        "value_feedback_review_id": "policy_review_ready_001",
        "source_value_feedback_candidate_id": "candidate_policy_001",
        "source_target_satisfaction_id": "target_satisfaction_policy_001",
        "source_experience_id": "2",
        "source_mechanism_search_id": "mechanism_search_policy_001",
        "source_target_observation_id": "target_observation_policy_001",
        "target_pattern_id": target_pattern,
        "target_pattern_name": registry.debug_name(target_pattern),
        "target_kind": "useful_target",
        "target_role_names": ["useful_target"],
        "candidate_type": "value_positive_candidate",
        "value_direction": "positive",
        "candidate_strength": 0.84,
        "evidence_strength": 0.78,
        "satisfaction_status": "satisfied",
        "satisfaction_score": 0.72,
        "review_decision": "ready",
        "review_reason": "strong_positive_value_feedback",
        "recommended_future_operation": "increase_target_usefulness_link",
        "ready_for_future_application": True,
        "apply_now": False,
        "activation": 0.5,
        "ttl": 12,
    }


def _real_hashes() -> dict[str, str | None]:
    exp_path = ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"
    akb_path = ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"
    draft_path = ROOT / "Memory" / "ExpSM" / "ExpSM_drafts.json"
    exp = _read_json(exp_path)
    return {
        "expsm": _hash_file(exp_path),
        "akbsm": _hash_file(akb_path),
        "drafts": _hash_file(draft_path),
        "semantic_core": _hash_json(_slice_expsm(exp, ("if", "then", "result", "recommendation"))),
        "technical_feedback": _hash_json(_slice_expsm(exp, ("hits", "misses", "confidence", "repeatability"))),
    }


def _slice_expsm(store: dict[str, Any], keys: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {
        str(record_id): {key: record.get(key) for key in keys}
        for record_id, record in store.get("experience", {}).items()
        if isinstance(record, dict)
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _hash_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
