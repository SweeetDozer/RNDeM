from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.action.action_candidate_field import ActionCandidateField
from clc.akbsm.akbsm_association_field import AKBSMAssociationField
from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.context.context_retention_policy import ContextRetentionPolicy, SideListRetentionPolicy
from clc.diagnostics.retention_diagnostics import RetentionDiagnostics, format_retention_metrics
from clc.evaluation.evaluation_field import EvaluationField
from clc.experience.experience_candidate_buffer import ExperienceCandidateBuffer
from clc.field.active_context_field import ActiveContextField


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"
SEMANTIC_CORE_HASH = "8b79266da35d3f96f3168e905ea8336e7ca734c3482df9ef9be6645b51051f72"
TECHNICAL_FEEDBACK_HASH = "95e2aeb4306dd96e062789bc06e2b0538931ff4caa4c8dc77c8564564021691c"


def main() -> int:
    before = _real_hashes()
    results = {
        "empty_minimal_runtime_state": _case_empty_minimal(),
        "synthetic_context_growth": _case_context_growth(),
        "field_counts": _case_field_counts(),
        "candidate_buffer_and_draft_counts": _case_candidate_buffer_and_drafts(),
        "retention_metrics_when_available": _case_retention_metrics(),
        "side_list_metrics_when_available": _case_side_list_metrics(),
        "side_list_retention_metrics_when_available": _case_side_list_retention_metrics(),
    }
    after = _real_hashes()
    results["real_expsm_hash_unchanged"] = after["expsm"] == before["expsm"] == EXP_HASH
    results["real_akbsm_hash_unchanged"] = after["akbsm"] == before["akbsm"] == AKB_HASH
    results["semantic_core_hash_unchanged"] = _optional_hash_unchanged(
        before["semantic_core"],
        after["semantic_core"],
        SEMANTIC_CORE_HASH,
    )
    results["technical_feedback_hash_unchanged"] = _optional_hash_unchanged(
        before["technical_feedback"],
        after["technical_feedback"],
        TECHNICAL_FEEDBACK_HASH,
    )

    print("Retention diagnostics verification:")
    for key, value in results.items():
        print(f"  {key}: {'yes' if value else 'no'}")
    passed = all(results.values())
    print("Sample debug output:")
    for line in format_retention_metrics(_sample_metrics()):
        print(f"  {line}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_empty_minimal() -> bool:
    memory, id_gen, registry = _memory()
    diagnostics = RetentionDiagnostics()
    metrics = diagnostics.collect(tick=0, memory=memory)
    return (
        metrics.context_event_count == 0
        and metrics.raw_frame_count == 0
        and metrics.window_count == 0
        and metrics.estimated_pressure == "low"
        and metrics.active_pattern_count is None
        and any("active patterns" in warning for warning in metrics.warnings)
        and id_gen is not None
        and registry is not None
    )


def _case_context_growth() -> bool:
    memory, id_gen, _registry = _memory()
    for tick in range(600):
        marker = OperationMarker.LABEL if tick % 2 else OperationMarker.MODULE_UPDATE
        memory.add_event(ContextOperation(id_gen.next("op"), marker, tick, "verify_retention_diagnostics", None, {"i": tick}))
    medium = RetentionDiagnostics().collect(tick=600, memory=memory)
    high_memory, high_id_gen, _ = _memory()
    for tick in range(2000):
        high_memory.add_event(
            ContextOperation(
                high_id_gen.next("op"),
                OperationMarker.MODULE_UPDATE,
                tick,
                "verify_retention_diagnostics",
                None,
                {"i": tick},
            )
        )
    high = RetentionDiagnostics().collect(tick=2000, memory=high_memory)
    return (
        medium.context_event_count == 600
        and medium.estimated_pressure == "medium"
        and medium.recent_marker_counts == {2: 100, 5: 100}
        and high.context_event_count == 2000
        and high.estimated_pressure == "high"
        and high.recent_marker_counts == {2: 200}
    )


def _case_field_counts() -> bool:
    _memory_obj, id_gen, _registry = _memory()
    active_field = ActiveContextField()
    active_field.activate("pat_a", 0.5, 1, "diagnostic")
    active_field.activate("pat_b", 0.6, 1, "diagnostic")
    action_field = ActionCandidateField(id_gen)
    action_field.propose("act_a", 0.5, 1, ttl=None)
    action_field.propose("act_b", 0.5, 1, ttl=None)
    action_field.propose("act_c", 0.5, 1, ttl=None)
    evaluation_field = EvaluationField()
    evaluation_field.update_pattern("pat_a", {"usefulness": 0.4}, source_id="src", scope="verify", activation=0.5, ttl=3, tick=1)
    evaluation_field.update_pattern("pat_b", {"need": 0.5}, source_id="src", scope="verify", activation=0.5, ttl=3, tick=1)
    association_field = AKBSMAssociationField()
    association_field.update_association("pat_a", "pat_b", relation_type="near", score=0.5, distance=1, path=None, source_probe_id="probe_1", target_kind=None, target_roles=[], activation=0.5, ttl=4, tick=1)
    association_field.update_association("pat_a", "pat_c", relation_type="near", score=0.5, distance=1, path=None, source_probe_id="probe_2", target_kind=None, target_roles=[], activation=0.5, ttl=4, tick=1)
    metrics = RetentionDiagnostics().collect(
        tick=1,
        active_field=active_field,
        action_candidate_field=action_field,
        evaluation_field=evaluation_field,
        akbsm_association_field=association_field,
    )
    return (
        metrics.active_pattern_count == 2
        and metrics.action_candidate_count == 3
        and metrics.evaluation_entry_count == 2
        and metrics.akbsm_association_entry_count == 2
    )


def _case_candidate_buffer_and_drafts() -> bool:
    memory, id_gen, registry = _memory()
    buffer = ExperienceCandidateBuffer(id_gen, registry)
    active_field = ActiveContextField()
    for idx in range(3):
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.EXPERIENCE_CANDIDATE,
                idx,
                "verify_retention_diagnostics",
                None,
                {
                    "candidate_id": f"cand_{idx}",
                    "candidate_status": "positive_candidate" if idx < 2 else "negative_candidate",
                    "confidence": 0.7,
                    "priority": 0.5,
                    "core_chain": {
                        "decision_patterns": ["decision_a"] if idx < 2 else ["decision_b"],
                        "effect_patterns": ["effect_a"],
                        "predicted_patterns": ["pred_a"],
                        "outcome_patterns": ["outcome_a"],
                    },
                },
            )
        )
    buffer.run(3, memory, active_field)
    with tempfile.TemporaryDirectory(prefix="rndem_retention_verify_") as temp_dir:
        draft_path = Path(temp_dir) / "ExpSM_drafts.json"
        draft_path.write_text(
            json.dumps(
                {
                    "schema": "RNDeM_ExpSM_DraftStore_v1",
                    "drafts": [
                        {"draft_id": "draft_1", "draft_status": "draft_pending_commit"},
                        {"draft_id": "draft_2", "draft_status": "draft_ready_to_commit"},
                        {"draft_id": "draft_3", "draft_status": "draft_pending_commit"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        metrics = RetentionDiagnostics(draft_path).collect(tick=4, experience_candidate_buffer=buffer)
    return (
        metrics.experience_candidate_group_count == 2
        and metrics.experience_candidate_total_count == 3
        and metrics.draft_total_count == 3
        and metrics.draft_status_counts == {"draft_pending_commit": 2, "draft_ready_to_commit": 1}
    )


def _case_retention_metrics() -> bool:
    memory, id_gen, _registry = _memory()
    for tick in range(12):
        memory.add_event(ContextOperation(id_gen.next("op"), OperationMarker.MODULE_UPDATE, tick, "verify", None, {}))
    result = memory.apply_retention(ContextRetentionPolicy(max_events=5, protected_recent_events=2))
    metrics = RetentionDiagnostics().collect(tick=12, memory=memory)
    rendered = "\n".join(format_retention_metrics(metrics))
    return (
        result.pruned_count == 7
        and metrics.context_event_count == 5
        and metrics.retention_enabled is True
        and metrics.retention_max_events == 5
        and metrics.last_retention_before_count == 12
        and metrics.last_retention_after_count == 5
        and metrics.last_retention_pruned_count == 7
        and "retention=enabled=true max_events=5 before=12 after=5 pruned=7" in rendered
    )


def _case_side_list_metrics() -> bool:
    memory, id_gen, _registry = _memory()
    memory.add_event(ContextOperation(id_gen.next("op"), OperationMarker.LABEL, 1, "verify", None, {"label_id": "label_1"}))
    memory.add_event(ContextOperation(id_gen.next("op"), OperationMarker.DECISION_AUDIT_OBSERVED, 2, "verify", None, {"audit_id": "audit_1"}))
    metrics = RetentionDiagnostics().collect(tick=2, memory=memory)
    return (
        metrics.side_list_counts["labels"] == 1
        and metrics.side_list_oldest_ticks["labels"] == 1
        and metrics.side_list_newest_ticks["decision_audits"] == 2
        and metrics.side_list_stale_counts["labels"] == 0
    )


def _case_side_list_retention_metrics() -> bool:
    memory, id_gen, _registry = _memory()
    for tick in range(10):
        memory.add_event(ContextOperation(id_gen.next("op"), OperationMarker.LABEL, tick, "verify", None, {"label_id": f"label_{tick}"}))
    result = memory.apply_side_list_retention(SideListRetentionPolicy(default_max_entries=4), oldest_event_tick=3)
    metrics = RetentionDiagnostics().collect(tick=10, memory=memory)
    labels = metrics.side_list_retention_per_list.get("labels", {})
    return (
        result.total_pruned == 6
        and metrics.side_list_retention_enabled is True
        and metrics.side_list_retention_total_before == result.total_before
        and metrics.side_list_retention_total_after == result.total_after
        and metrics.side_list_retention_total_pruned == result.total_pruned
        and labels.get("pruned_by_tick") == 3
        and labels.get("pruned_by_max_entries") == 3
    )


def _sample_metrics():
    memory, id_gen, registry = _memory()
    for tick in range(3):
        memory.add_event(ContextOperation(id_gen.next("op"), OperationMarker.MODULE_UPDATE, tick, "verify", None, {}))
    active_field = ActiveContextField()
    active_field.activate("pat_a", 0.5, 1, "diagnostic")
    action_field = ActionCandidateField(id_gen)
    action_field.propose("act_a", 0.5, 1, ttl=None)
    evaluation_field = EvaluationField()
    evaluation_field.update_pattern("pat_a", {"usefulness": 0.4}, source_id="src", scope="verify", activation=0.5, ttl=3, tick=1)
    association_field = AKBSMAssociationField()
    association_field.update_association("pat_a", "pat_b", relation_type="near", score=0.5, distance=1, path=None, source_probe_id="probe_1", target_kind=None, target_roles=[], activation=0.5, ttl=4, tick=1)
    buffer = ExperienceCandidateBuffer(id_gen, registry)
    return RetentionDiagnostics(ROOT / "Memory" / "ExpSM" / "ExpSM_drafts.json").collect(
        tick=3,
        memory=memory,
        active_field=active_field,
        action_candidate_field=action_field,
        evaluation_field=evaluation_field,
        akbsm_association_field=association_field,
        experience_candidate_buffer=buffer,
    )


def _memory() -> tuple[ContextMemory, IdGenerator, PatternRegistry]:
    id_gen = IdGenerator()
    registry = PatternRegistry(ROOT / "Memory" / "pattern_manifest.json")
    return ContextMemory(id_gen, registry), id_gen, registry


def _real_hashes() -> dict[str, str | None]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
        "semantic_core": _hash_file(ROOT / "Memory" / "AKBSM" / "DB" / "semantic_core.json"),
        "technical_feedback": _hash_file(ROOT / "Memory" / "AKBSM" / "DB" / "technical_feedback_patterns.json"),
    }


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _optional_hash_unchanged(before: str | None, after: str | None, expected: str) -> bool:
    if before is None and after is None:
        return True
    return before == after == expected


if __name__ == "__main__":
    raise SystemExit(main())
