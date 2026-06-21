from __future__ import annotations

import hashlib
import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.evaluation.decision_cycle_history_view import DecisionCycleHistoryView  # noqa: E402
from clc.runtime.clc_runtime import CLCRuntime  # noqa: E402
from clc.runtime.memory_mutation_policy import RuntimeProfile  # noqa: E402


def main() -> int:
    real_expsm_path = ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"
    real_akbsm_path = ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"
    real_expsm_before = _hash_file(real_expsm_path)
    real_akbsm_before = _hash_file(real_akbsm_path)
    checks = {
        "no summaries": _case_no_summaries(),
        "mostly clean": _case_mostly_clean(),
        "uncertain history": _case_uncertain(),
        "guard constrained history": _case_guard_constrained(),
        "value influenced history": _case_value_influenced(),
        "window limit": _case_window_limit(),
        "runtime integration": _case_runtime_integration(),
        "real ExpSM unchanged": real_expsm_before == _hash_file(real_expsm_path),
        "real AKBSM unchanged": real_akbsm_before == _hash_file(real_akbsm_path),
    }
    passed = all(checks.values())
    print("Decision cycle history view verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_no_summaries() -> bool:
    snapshot = DecisionCycleHistoryView().refresh(tick=1, decision_cycle_summaries=[])
    return snapshot.observed_count == 0 and snapshot.trend_label == "no_data"


def _case_mostly_clean() -> bool:
    summaries = [_summary("clean_selection") for _ in range(12)] + [_summary("uncertain_selection") for _ in range(4)]
    snapshot = DecisionCycleHistoryView().refresh(tick=16, decision_cycle_summaries=summaries)
    return snapshot.trend_label == "mostly_clean" and snapshot.clean_count == 12 and snapshot.uncertain_count == 4


def _case_uncertain() -> bool:
    summaries = [_summary("clean_selection") for _ in range(6)] + [
        _summary("uncertain_selection", flags=["narrow_decision"]) for _ in range(5)
    ]
    snapshot = DecisionCycleHistoryView().refresh(tick=13, decision_cycle_summaries=summaries)
    return (
        snapshot.trend_label == "uncertain_recent_history"
        and snapshot.uncertain_count == 5
        and snapshot.flag_counts.get("narrow_decision") == 5
    )


def _case_guard_constrained() -> bool:
    summaries = [_summary("clean_selection") for _ in range(5)] + [
        _summary("guard_constrained_selection", flags=["guard_blocked_high_score"]) for _ in range(4)
    ] + [
        _summary("mixed_selection") for _ in range(4)
    ]
    snapshot = DecisionCycleHistoryView().refresh(tick=12, decision_cycle_summaries=summaries)
    return (
        snapshot.trend_label == "guard_constrained_recent_history"
        and snapshot.guard_constrained_count == 4
        and snapshot.flag_counts.get("guard_blocked_high_score") == 4
    )


def _case_value_influenced() -> bool:
    summaries = [_summary("clean_selection") for _ in range(5)] + [
        _summary("value_influenced_selection", value_influence="positive_bonus", flags=["value_promoted_selected"])
        for _ in range(4)
    ] + [
        _summary("mixed_selection") for _ in range(4)
    ]
    snapshot = DecisionCycleHistoryView().refresh(tick=12, decision_cycle_summaries=summaries)
    return snapshot.trend_label == "value_influenced_recent_history" and snapshot.value_influenced_count == 4


def _case_window_limit() -> bool:
    summaries = [_summary("uncertain_selection") for _ in range(5)] + [_summary("clean_selection") for _ in range(20)]
    snapshot = DecisionCycleHistoryView(window_size=20).refresh(tick=25, decision_cycle_summaries=summaries)
    return snapshot.observed_count == 20 and snapshot.clean_count == 20 and snapshot.uncertain_count == 0


def _case_runtime_integration() -> bool:
    with tempfile.TemporaryDirectory(prefix="decision_cycle_history_runtime_") as temp_dir:
        memory_root = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", memory_root)
        runtime = CLCRuntime(memory_root, profile=RuntimeProfile.SAFE_DEMO, memory_is_temporary=True)
        with contextlib.redirect_stdout(io.StringIO()):
            for tick, value in enumerate((0.2, 0.9, 0.25, 0.85), start=1):
                runtime.feed_audio(tick, {440: value, 880: 0.2, 1200: 0.1})
        snapshot = runtime.decision_cycle_history_view.snapshot()
        return snapshot is not None and snapshot.window_size == 20 and snapshot.observed_count >= 0


def _summary(
    status: str,
    *,
    confidence: str = "medium",
    flags: list[str] | None = None,
    source: str = "baseline/internal",
    value_influence: str = "none_or_tiny",
    guard_effect: str = "no_blocked_candidates",
    severity: str = "none",
) -> dict[str, object]:
    return {
        "selected": {"source": source},
        "decision_summary": {"value_influence": value_influence},
        "guard_summary": {"guard_effect": guard_effect, "severity": severity},
        "cycle_summary": {
            "cycle_status": status,
            "cycle_confidence": confidence,
            "flags": list(flags or []),
        },
    }


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
