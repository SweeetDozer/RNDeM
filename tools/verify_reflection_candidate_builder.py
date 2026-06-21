from __future__ import annotations

import contextlib
import hashlib
import io
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.core.ids import IdGenerator  # noqa: E402
from clc.evaluation.decision_cycle_history_view import DecisionCycleHistorySnapshot  # noqa: E402
from clc.evaluation.reflection_candidate_builder import (  # noqa: E402
    MAX_REFLECTION_CANDIDATES_PER_TICK,
    ReflectionCandidateBuilder,
)
from clc.runtime.clc_runtime import CLCRuntime  # noqa: E402
from clc.runtime.memory_mutation_policy import RuntimeProfile  # noqa: E402


def main() -> int:
    real_expsm_path = ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"
    real_akbsm_path = ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"
    real_expsm_before = _hash_file(real_expsm_path)
    real_akbsm_before = _hash_file(real_akbsm_path)
    checks = {
        "no history": _case_no_history(),
        "insufficient history": _case_insufficient_history(),
        "repeated uncertain selection": _case_repeated_uncertain_selection(),
        "guard policy tension": _case_guard_policy_tension(),
        "weak value influence": _case_weak_value_influence(),
        "stable clean selection": _case_stable_clean_selection(),
        "mixed cycle history": _case_mixed_cycle_history(),
        "value layer active suppresses weak value": _case_value_layer_active(),
        "per tick bound": _case_per_tick_bound(),
        "recent bound": _case_recent_bound(),
        "runtime integration": _case_runtime_integration(),
        "real ExpSM unchanged": real_expsm_before == _hash_file(real_expsm_path),
        "real AKBSM unchanged": real_akbsm_before == _hash_file(real_akbsm_path),
    }
    passed = all(checks.values())
    print("Reflection candidate builder verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_no_history() -> bool:
    candidates = ReflectionCandidateBuilder(IdGenerator()).build(tick=1, history_snapshot=None)
    candidate = _first(candidates)
    return (
        candidate is not None
        and candidate.reflection_type == "no_decision_history"
        and candidate.severity == "info"
        and candidate.apply_now is False
        and candidate.evidence["observed_count"] == 0
    )


def _case_insufficient_history() -> bool:
    candidates = ReflectionCandidateBuilder(IdGenerator()).build(
        tick=2,
        history_snapshot=_snapshot(
            observed_count=3,
            clean_count=1,
            uncertain_count=2,
            trend_label="uncertain_recent_history",
        ),
    )
    return _has_candidate(candidates, "insufficient_decision_confidence", "low", "collect_more_evidence")


def _case_repeated_uncertain_selection() -> bool:
    candidates = ReflectionCandidateBuilder(IdGenerator()).build(
        tick=3,
        history_snapshot=_snapshot(
            observed_count=10,
            uncertain_count=7,
            trend_label="uncertain_recent_history",
        ),
    )
    return _has_candidate(
        candidates,
        "repeated_uncertain_selection",
        "medium",
        "inspect_candidate_discrimination",
    )


def _case_guard_policy_tension() -> bool:
    candidates = ReflectionCandidateBuilder(IdGenerator()).build(
        tick=4,
        history_snapshot=_snapshot(
            observed_count=10,
            guard_constrained_count=5,
            risky_or_constrained_count=2,
            trend_label="guard_constrained_recent_history",
        ),
    )
    return _has_candidate(candidates, "guard_policy_tension", "high", "inspect_guard_policy_tension")


def _case_weak_value_influence() -> bool:
    candidates = ReflectionCandidateBuilder(IdGenerator()).build(
        tick=5,
        history_snapshot=_snapshot(
            observed_count=8,
            clean_count=6,
            value_influenced_count=0,
            trend_label="mostly_clean",
        ),
    )
    return _has_candidate(candidates, "weak_value_influence", "low", "inspect_value_signal_coverage")


def _case_stable_clean_selection() -> bool:
    candidates = ReflectionCandidateBuilder(IdGenerator()).build(
        tick=6,
        history_snapshot=_snapshot(
            observed_count=10,
            clean_count=8,
            trend_label="mostly_clean",
        ),
    )
    return _has_candidate(candidates, "stable_clean_selection", "info", "maintain_current_policy")


def _case_mixed_cycle_history() -> bool:
    candidates = ReflectionCandidateBuilder(IdGenerator()).build(
        tick=7,
        history_snapshot=_snapshot(
            observed_count=10,
            clean_count=3,
            uncertain_count=2,
            guard_constrained_count=2,
            value_influenced_count=1,
            trend_label="mixed_recent_history",
        ),
    )
    return _has_candidate(candidates, "mixed_cycle_history", "low", "review_mixed_history")


def _case_value_layer_active() -> bool:
    candidates = ReflectionCandidateBuilder(IdGenerator()).build(
        tick=8,
        history_snapshot=_snapshot(
            observed_count=10,
            value_influenced_count=5,
            trend_label="value_influenced_recent_history",
        ),
    )
    return not any(candidate.reflection_type == "weak_value_influence" for candidate in candidates)


def _case_per_tick_bound() -> bool:
    candidates = ReflectionCandidateBuilder(IdGenerator(), min_observed_count=1).build(
        tick=9,
        history_snapshot=_snapshot(
            observed_count=20,
            clean_count=12,
            value_influenced_count=0,
            trend_label="mostly_clean",
        ),
    )
    return len(candidates) <= MAX_REFLECTION_CANDIDATES_PER_TICK


def _case_recent_bound() -> bool:
    builder = ReflectionCandidateBuilder(IdGenerator(), max_recent_reflection_candidates=4)
    for tick in range(1, 10):
        builder.build(tick=tick, history_snapshot=None)
    recent = builder.recent_candidates(limit=10)
    return len(recent) == 4 and recent[0].tick == 6 and recent[-1].tick == 9


def _case_runtime_integration() -> bool:
    with tempfile.TemporaryDirectory(prefix="reflection_candidate_runtime_") as temp_dir:
        memory_root = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", memory_root)
        runtime = CLCRuntime(memory_root, profile=RuntimeProfile.SAFE_DEMO, memory_is_temporary=True)
        with contextlib.redirect_stdout(io.StringIO()):
            for tick, value in enumerate((0.2, 0.9, 0.25, 0.85), start=1):
                runtime.feed_audio(tick, {440: value, 880: 0.2, 1200: 0.1})
        candidates = runtime.reflection_candidate_builder.recent_candidates(limit=8)
        return isinstance(candidates, list) and runtime.decision_cycle_history_view.snapshot() is not None


def _snapshot(
    *,
    observed_count: int,
    window_size: int = 20,
    clean_count: int = 0,
    uncertain_count: int = 0,
    guard_constrained_count: int = 0,
    risky_or_constrained_count: int = 0,
    value_influenced_count: int = 0,
    trend_label: str,
) -> DecisionCycleHistorySnapshot:
    status_counts = {}
    if clean_count:
        status_counts["clean_selection"] = clean_count
    if uncertain_count:
        status_counts["uncertain_selection"] = uncertain_count
    if guard_constrained_count:
        status_counts["guard_constrained_selection"] = guard_constrained_count
    return DecisionCycleHistorySnapshot(
        tick=1,
        window_size=window_size,
        observed_count=observed_count,
        status_counts=status_counts,
        confidence_counts={"medium": observed_count} if observed_count else {},
        flag_counts={},
        selected_source_counts={"baseline/internal": observed_count} if observed_count else {},
        value_influenced_count=value_influenced_count,
        guard_constrained_count=guard_constrained_count,
        uncertain_count=uncertain_count,
        risky_or_constrained_count=risky_or_constrained_count,
        clean_count=clean_count,
        dominant_status=next(iter(status_counts), None),
        dominant_confidence="medium" if observed_count else None,
        trend_label=trend_label,
    )


def _first(candidates: list[object]) -> object | None:
    return candidates[0] if candidates else None


def _has_candidate(
    candidates: list[object],
    reflection_type: str,
    severity: str,
    recommended_future_operation: str,
) -> bool:
    return any(
        getattr(candidate, "reflection_type", None) == reflection_type
        and getattr(candidate, "severity", None) == severity
        and getattr(candidate, "recommended_future_operation", None) == recommended_future_operation
        and getattr(candidate, "apply_now", None) is False
        for candidate in candidates
    )


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
