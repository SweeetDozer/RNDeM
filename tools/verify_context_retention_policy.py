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
from clc.context.context_retention_policy import ContextRetentionPolicy
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.runtime.clc_runtime import CLCRuntime


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"


def main() -> int:
    before = _real_hashes()
    results = {
        "disabled_policy_does_not_prune": _case_disabled_policy(),
        "max_events_prunes_oldest": _case_max_events_prunes_oldest(),
        "no_pruning_under_limit": _case_no_pruning_under_limit(),
        "invalid_policy_rejected": _case_invalid_policy_rejected(),
        "runtime_applies_retention_centrally": _case_runtime_applies_retention(),
        "recent_audit_summary_flow_survives": _case_recent_audit_summary_flow(),
    }
    after = _real_hashes()
    results["real_expsm_hash_unchanged"] = after["expsm"] == before["expsm"] == EXP_HASH
    results["real_akbsm_hash_unchanged"] = after["akbsm"] == before["akbsm"] == AKB_HASH
    results["semantic_core_unchanged"] = after["semantic_core"] == before["semantic_core"]
    results["technical_feedback_unchanged"] = after["technical_feedback"] == before["technical_feedback"]

    print("Context retention policy verification:")
    for key, value in results.items():
        print(f"  {key}: {'yes' if value else 'no'}")
    sample = _sample_retention_result()
    print("Sample retention result:")
    print(
        f"  enabled={str(sample.enabled).lower()} max_events={sample.max_events} "
        f"before={sample.before_count} after={sample.after_count} pruned={sample.pruned_count} "
        f"oldest_tick={sample.oldest_remaining_tick} newest_tick={sample.newest_remaining_tick}"
    )
    passed = all(results.values())
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_disabled_policy() -> bool:
    memory, _id_gen, _registry = _memory_with_events(100)
    result = memory.apply_retention(ContextRetentionPolicy(enabled=False, max_events=10))
    return result.before_count == 100 and result.after_count == 100 and result.pruned_count == 0 and len(memory.events) == 100


def _case_max_events_prunes_oldest() -> bool:
    memory, _id_gen, _registry = _memory_with_events(100)
    result = memory.apply_retention(ContextRetentionPolicy(enabled=True, max_events=30, protected_recent_events=10))
    ticks = [event.tick for event in memory.events]
    op_ids = [event.op_id for event in memory.events]
    return (
        result.before_count == 100
        and result.after_count == 30
        and result.pruned_count == 70
        and ticks[0] == 70
        and ticks[-1] == 99
        and op_ids[0] == "op_070"
        and op_ids[-1] == "op_099"
        and ticks == sorted(ticks)
    )


def _case_no_pruning_under_limit() -> bool:
    memory, _id_gen, _registry = _memory_with_events(20)
    result = memory.apply_retention(ContextRetentionPolicy(enabled=True, max_events=30, protected_recent_events=10))
    return result.before_count == 20 and result.after_count == 20 and result.pruned_count == 0 and len(memory.events) == 20


def _case_invalid_policy_rejected() -> bool:
    invalid_cases = [
        {"max_events": 0},
        {"max_events": 10, "protected_recent_events": 20},
        {"protected_recent_events": -1},
    ]
    for kwargs in invalid_cases:
        try:
            ContextRetentionPolicy(**kwargs)
        except ValueError:
            continue
        return False
    return True


def _case_runtime_applies_retention() -> bool:
    before = _real_hashes()
    with tempfile.TemporaryDirectory(prefix="rndem_context_retention_") as temp_dir:
        temp_memory = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", temp_memory)
        runtime = CLCRuntime(
            temp_memory,
            memory_is_temporary=True,
            context_retention_policy=ContextRetentionPolicy(max_events=50, protected_recent_events=10),
        )
        _run_audio_ticks(runtime, range(1, 10))
        result = runtime.memory.last_context_retention_result
        ok = result is not None and len(runtime.memory.events) <= 50 and result.after_count <= 50
    return ok and _real_hashes() == before


def _case_recent_audit_summary_flow() -> bool:
    with tempfile.TemporaryDirectory(prefix="rndem_context_retention_flow_") as temp_dir:
        temp_memory = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", temp_memory)
        runtime = CLCRuntime(
            temp_memory,
            memory_is_temporary=True,
            context_retention_policy=ContextRetentionPolicy(max_events=200, protected_recent_events=100),
        )
        _run_audio_ticks(runtime, range(1, 8))
        markers = {event.marker.value for event in runtime.memory.events}
        recent_counts = {}
        for event in runtime.memory.events[-200:]:
            recent_counts[event.marker.value] = recent_counts.get(event.marker.value, 0) + 1
        return {33, 34, 35}.issubset(markers) and all(recent_counts.get(marker, 0) > 0 for marker in (33, 34, 35))


def _sample_retention_result():
    memory, _id_gen, _registry = _memory_with_events(12)
    return memory.apply_retention(ContextRetentionPolicy(max_events=5, protected_recent_events=2))


def _memory_with_events(count: int) -> tuple[ContextMemory, IdGenerator, PatternRegistry]:
    memory, id_gen, registry = _memory()
    for index in range(count):
        memory.add_event(
            ContextOperation(
                f"op_{index:03d}",
                OperationMarker.MODULE_UPDATE,
                index,
                "verify_context_retention_policy",
                None,
                {"index": index},
            )
        )
    return memory, id_gen, registry


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
