from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.context.context_memory import ContextMemory
from clc.context.context_retention_policy import ContextRetentionPolicy, SideListRetentionPolicy
from clc.context.window import ContextWindow
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.diagnostics.retention_diagnostics import RetentionDiagnostics
from clc.runtime.clc_runtime import CLCRuntime


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"


def main() -> int:
    before = _real_hashes()
    results = {
        "disabled_policy_does_not_prune": _case_disabled_policy(),
        "prunes_older_than_oldest_event": _case_prune_by_oldest_event(),
        "max_length_cap": _case_max_length_cap(),
        "combined_tick_and_max_pruning": _case_combined_tick_and_max(),
        "windows_pruned_by_to_tick": _case_windows_pruning(),
        "unknown_tick_entries_kept_by_default": _case_unknown_ticks_kept(),
        "runtime_applies_event_then_side_list_retention": _case_runtime_order_and_bounds(),
        "recent_audit_summary_flow_survives": _case_recent_audit_summary_flow(),
    }
    after = _real_hashes()
    results["real_expsm_hash_unchanged"] = after["expsm"] == before["expsm"] == EXP_HASH
    results["real_akbsm_hash_unchanged"] = after["akbsm"] == before["akbsm"] == AKB_HASH
    results["semantic_core_unchanged"] = after["semantic_core"] == before["semantic_core"]
    results["technical_feedback_unchanged"] = after["technical_feedback"] == before["technical_feedback"]

    print("Context side-list retention policy verification:")
    for key, value in results.items():
        print(f"  {key}: {'yes' if value else 'no'}")
    sample = _sample_result()
    print("Sample side-list retention result:")
    print(
        f"  enabled={str(sample.enabled).lower()} oldest_event_tick={sample.oldest_event_tick} "
        f"before={sample.total_before} after={sample.total_after} pruned={sample.total_pruned}"
    )
    labels = sample.per_list.get("labels", {})
    print(
        f"  labels before={labels.get('before')} after={labels.get('after')} "
        f"pruned_by_tick={labels.get('pruned_by_tick')} pruned_by_max={labels.get('pruned_by_max_entries')}"
    )
    passed = all(results.values())
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_disabled_policy() -> bool:
    memory, id_gen, _registry = _memory()
    _add_labels(memory, id_gen, 0, 99)
    result = memory.apply_side_list_retention(SideListRetentionPolicy(enabled=False, default_max_entries=10), oldest_event_tick=70)
    return result.total_before == result.total_after and result.total_pruned == 0 and len(memory.labels) == 100


def _case_prune_by_oldest_event() -> bool:
    memory, id_gen, _registry = _memory()
    _add_labels(memory, id_gen, 0, 99)
    event_result = memory.apply_retention(ContextRetentionPolicy(max_events=30, protected_recent_events=10))
    result = memory.apply_side_list_retention(SideListRetentionPolicy(default_max_entries=None), oldest_event_tick=event_result.oldest_remaining_tick)
    return (
        event_result.oldest_remaining_tick == 70
        and [item["_event_tick"] for item in memory.labels] == list(range(70, 100))
        and result.per_list["labels"]["pruned_by_tick"] == 70
        and result.per_list["labels"]["pruned_by_max_entries"] == 0
    )


def _case_max_length_cap() -> bool:
    memory, id_gen, _registry = _memory()
    _add_labels(memory, id_gen, 0, 999)
    result = memory.apply_side_list_retention(SideListRetentionPolicy(default_max_entries=100), oldest_event_tick=None)
    return (
        len(memory.labels) == 100
        and [item["_event_tick"] for item in memory.labels] == list(range(900, 1000))
        and result.per_list["labels"]["pruned_by_tick"] == 0
        and result.per_list["labels"]["pruned_by_max_entries"] == 900
    )


def _case_combined_tick_and_max() -> bool:
    memory, id_gen, _registry = _memory()
    _add_labels(memory, id_gen, 0, 999)
    result = memory.apply_side_list_retention(SideListRetentionPolicy(default_max_entries=100), oldest_event_tick=500)
    return (
        [item["_event_tick"] for item in memory.labels] == list(range(900, 1000))
        and result.per_list["labels"]["pruned_by_tick"] == 500
        and result.per_list["labels"]["pruned_by_max_entries"] == 400
    )


def _case_windows_pruning() -> bool:
    memory, _id_gen, _registry = _memory()
    memory.windows.extend(
        [
            ContextWindow("win_a", 0, 10, ()),
            ContextWindow("win_b", 60, 80, ()),
            ContextWindow("win_c", 90, 100, ()),
        ]
    )
    result = memory.apply_side_list_retention(SideListRetentionPolicy(default_max_entries=None), oldest_event_tick=70)
    return (
        [window.window_id for window in memory.windows] == ["win_b", "win_c"]
        and result.per_list["windows"]["pruned_by_tick"] == 1
        and result.per_list["windows"]["oldest_tick_after"] == 60
        and result.per_list["windows"]["newest_tick_after"] == 100
    )


def _case_unknown_ticks_kept() -> bool:
    memory, _id_gen, _registry = _memory()
    memory.labels.append({"label_id": "unknown_tick_label"})
    result = memory.apply_side_list_retention(SideListRetentionPolicy(default_max_entries=10), oldest_event_tick=70)
    return (
        len(memory.labels) == 1
        and result.total_pruned == 0
        and result.per_list["labels"]["unknown_tick_entries_before"] == 1
        and any("labels kept 1 entries without diagnostic ticks" in warning for warning in result.warnings)
    )


def _case_runtime_order_and_bounds() -> bool:
    before = _real_hashes()
    with tempfile.TemporaryDirectory(prefix="rndem_side_retention_") as temp_dir:
        temp_memory = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", temp_memory)
        runtime = CLCRuntime(
            temp_memory,
            memory_is_temporary=True,
            context_retention_policy=ContextRetentionPolicy(max_events=50, protected_recent_events=10),
            side_list_retention_policy=SideListRetentionPolicy(default_max_entries=30),
        )
        _run_audio_ticks(runtime, range(1, 10))
        metrics = RetentionDiagnostics().collect(tick=10, memory=runtime.memory)
        stale_values = [
            value
            for value in metrics.side_list_stale_counts.values()
            if value is not None
        ]
        bounded_counts = all(count <= 30 for count in metrics.side_list_counts.values())
        ok = len(runtime.memory.events) <= 50 and bounded_counts and all(value == 0 for value in stale_values)
    return ok and _real_hashes() == before


def _case_recent_audit_summary_flow() -> bool:
    with tempfile.TemporaryDirectory(prefix="rndem_side_retention_flow_") as temp_dir:
        temp_memory = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", temp_memory)
        runtime = CLCRuntime(
            temp_memory,
            memory_is_temporary=True,
            context_retention_policy=ContextRetentionPolicy(max_events=200, protected_recent_events=100),
            side_list_retention_policy=SideListRetentionPolicy(default_max_entries=50),
        )
        _run_audio_ticks(runtime, range(1, 8))
        markers = {event.marker.value for event in runtime.memory.events}
        return (
            {33, 34, 35}.issubset(markers)
            and bool(runtime.memory.get_recent_decision_audits(4))
            and bool(runtime.memory.get_recent_action_guard_audits(4))
            and bool(runtime.memory.get_recent_decision_cycle_summaries(4))
        )


def _sample_result():
    memory, id_gen, _registry = _memory()
    _add_labels(memory, id_gen, 0, 20)
    return memory.apply_side_list_retention(SideListRetentionPolicy(default_max_entries=5), oldest_event_tick=10)


def _add_labels(memory: ContextMemory, id_gen: IdGenerator, start: int, end: int) -> None:
    for tick in range(start, end + 1):
        memory.add_event(
            ContextOperation(
                id_gen.next("op"),
                OperationMarker.LABEL,
                tick,
                "verify_context_side_list_retention_policy",
                None,
                {"label_id": f"label_{tick}", "tick": tick},
            )
        )


def _memory() -> tuple[ContextMemory, IdGenerator, PatternRegistry]:
    id_gen = IdGenerator()
    registry = PatternRegistry(ROOT / "Memory" / "pattern_manifest.json")
    return ContextMemory(id_gen, registry), id_gen, registry


def _run_audio_ticks(runtime: CLCRuntime, ticks) -> None:
    with redirect_stdout(io.StringIO()):
        for tick in ticks:
            runtime.feed_audio(tick, {440: 0.9 if tick % 2 == 0 else 0.2, 880: 0.2, 1200: 0.1})


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
