from __future__ import annotations

import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.context.context_memory import ContextMemory
from clc.context.context_retention_policy import ContextRetentionPolicy
from clc.context.window import ContextWindow
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.nfp import NFPFrame
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.diagnostics.retention_diagnostics import RetentionDiagnostics, format_side_list_retention_metrics


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"


def main() -> int:
    before = _real_hashes()
    results = {
        "discovers_side_lists": _case_discover_side_lists(),
        "synthetic_side_list_counts": _case_synthetic_counts(),
        "stale_side_list_detection": _case_stale_detection(),
        "unknown_tick_handled": _case_unknown_tick(),
    }
    after = _real_hashes()
    results["real_expsm_hash_unchanged"] = after["expsm"] == before["expsm"] == EXP_HASH
    results["real_akbsm_hash_unchanged"] = after["akbsm"] == before["akbsm"] == AKB_HASH
    results["semantic_core_unchanged"] = after["semantic_core"] == before["semantic_core"]
    results["technical_feedback_unchanged"] = after["technical_feedback"] == before["technical_feedback"]

    print("Context side-list retention diagnostics verification:")
    for key, value in results.items():
        print(f"  {key}: {'yes' if value else 'no'}")
    print("Sample side-list diagnostics:")
    for line in format_side_list_retention_metrics(_sample_metrics(), limit=6):
        print(f"  {line}")
    passed = all(results.values())
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_discover_side_lists() -> bool:
    memory, _id_gen, _registry = _memory()
    metrics = RetentionDiagnostics().collect(tick=0, memory=memory)
    expected = {"labels", "decision_audits", "action_guard_audits", "decision_cycle_summaries", "raw_frames", "windows"}
    return expected.issubset(metrics.side_list_counts) and all(metrics.side_list_counts[name] == 0 for name in expected)


def _case_synthetic_counts() -> bool:
    memory, id_gen, _registry = _memory()
    _add_events(memory, id_gen, OperationMarker.LABEL, 10, 12)
    _add_events(memory, id_gen, OperationMarker.DECISION_AUDIT_OBSERVED, 20, 22)
    _add_events(memory, id_gen, OperationMarker.DECISION_CYCLE_SUMMARY, 30, 31)
    memory.add_frame(NFPFrame("frame_raw_1", 40, "external", "verify", {}))
    memory.add_frame(NFPFrame("frame_raw_2", 41, "external", "verify", {}))
    memory.windows.append(ContextWindow("win_1", 40, 41, ("frame_raw_1", "frame_raw_2")))
    metrics = RetentionDiagnostics().collect(tick=42, memory=memory)
    return (
        metrics.side_list_counts["labels"] == 3
        and metrics.side_list_oldest_ticks["labels"] == 10
        and metrics.side_list_newest_ticks["labels"] == 12
        and metrics.side_list_counts["decision_audits"] == 3
        and metrics.side_list_oldest_ticks["decision_audits"] == 20
        and metrics.side_list_newest_ticks["decision_audits"] == 22
        and metrics.side_list_counts["decision_cycle_summaries"] == 2
        and metrics.side_list_counts["raw_frames"] == 2
        and metrics.side_list_oldest_ticks["raw_frames"] == 40
        and metrics.side_list_newest_ticks["windows"] == 41
    )


def _case_stale_detection() -> bool:
    memory, id_gen, _registry = _memory()
    _add_events(memory, id_gen, OperationMarker.LABEL, 0, 99)
    before_side_count = len(memory.labels)
    result = memory.apply_retention(ContextRetentionPolicy(max_events=30, protected_recent_events=10))
    metrics = RetentionDiagnostics().collect(tick=100, memory=memory)
    return (
        result.oldest_remaining_tick == 70
        and len(memory.events) == 30
        and len(memory.labels) == before_side_count == 100
        and metrics.oldest_event_tick == 70
        and metrics.newest_event_tick == 99
        and metrics.side_list_counts["labels"] == 100
        and metrics.side_list_stale_counts["labels"] == 70
        and metrics.side_list_oldest_ticks["labels"] == 0
        and metrics.side_list_newest_ticks["labels"] == 99
    )


def _case_unknown_tick() -> bool:
    memory, _id_gen, _registry = _memory()
    memory.labels.append({"label_id": "label_without_tick"})
    metrics = RetentionDiagnostics().collect(tick=1, memory=memory)
    return (
        metrics.side_list_counts["labels"] == 1
        and metrics.side_list_oldest_ticks["labels"] is None
        and metrics.side_list_stale_counts["labels"] is None
        and any("labels has 1 entries without diagnostic ticks" in warning for warning in metrics.side_list_warnings)
    )


def _sample_metrics():
    memory, id_gen, _registry = _memory()
    _add_events(memory, id_gen, OperationMarker.LABEL, 0, 9)
    _add_events(memory, id_gen, OperationMarker.DECISION_AUDIT_OBSERVED, 6, 9)
    memory.apply_retention(ContextRetentionPolicy(max_events=5, protected_recent_events=2))
    return RetentionDiagnostics().collect(tick=10, memory=memory)


def _add_events(memory: ContextMemory, id_gen: IdGenerator, marker: OperationMarker, start: int, end: int) -> None:
    for tick in range(start, end + 1):
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                marker,
                tick,
                "verify_context_side_list_retention_diagnostics",
                None,
                {"tick": tick, "marker": marker.name},
            )
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


if __name__ == "__main__":
    raise SystemExit(main())
