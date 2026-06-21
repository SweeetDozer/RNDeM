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
from clc.evaluation.need_more_evidence_signal import NeedMoreEvidenceSignal  # noqa: E402
from clc.evaluation.reflection_candidate_builder import ReflectionCandidate  # noqa: E402
from clc.evaluation.reflection_review import ReflectionReviewBuilder  # noqa: E402
from clc.runtime.clc_runtime import CLCRuntime  # noqa: E402
from clc.runtime.memory_mutation_policy import RuntimeProfile  # noqa: E402


DISCONNECTED_FILES = (
    "clc/action/decision_selector.py",
    "clc/action/action_proposer.py",
    "clc/system/mode_action_guard.py",
    "clc/consolidation/memory_draft_writer.py",
    "clc/consolidation/draft_commit_gate.py",
    "clc/consolidation/expsm_commit_writer.py",
    "clc/consolidation/expsm_update_writer.py",
    "clc/evaluation/value_feedback_update_writer.py",
    "clc/field/field_updater.py",
    "clc/neuromodulation/neuromodulation_module.py",
)


def main() -> int:
    real_expsm_path = ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"
    real_akbsm_path = ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"
    real_expsm_before = _hash_file(real_expsm_path)
    real_akbsm_before = _hash_file(real_akbsm_path)
    checks = {
        "no data": _case_no_data(),
        "need more evidence dominates": _case_need_more_evidence_dominates(),
        "mostly clean": _case_mostly_clean(),
        "guard tension": _case_guard_tension(),
        "weak value signal": _case_weak_value_signal(),
        "mixed state": _case_mixed_state(),
        "recent bound": _case_recent_bound(),
        "runtime integration": _case_runtime_integration(),
        "disconnected behavior": _case_disconnected_behavior(),
        "real ExpSM unchanged": real_expsm_before == _hash_file(real_expsm_path),
        "real AKBSM unchanged": real_akbsm_before == _hash_file(real_akbsm_path),
    }
    passed = all(checks.values())
    print("Reflection review verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_no_data() -> bool:
    review = ReflectionReviewBuilder(IdGenerator()).build(
        tick=1,
        history_snapshot=None,
        reflection_candidates=[],
        need_more_evidence_signal=None,
    )
    return (
        review.review_status == "no_reflection_data"
        and review.severity == "info"
        and review.primary_issue == "no_decision_history"
        and review.apply_now is False
    )


def _case_need_more_evidence_dominates() -> bool:
    review = ReflectionReviewBuilder(IdGenerator()).build(
        tick=2,
        history_snapshot=_snapshot("uncertain_recent_history", observed_count=20, uncertain_count=12),
        reflection_candidates=[_candidate("guard_policy_tension", "high", 0.9)],
        need_more_evidence_signal=_signal(
            active=True,
            severity="medium",
            confidence=1.0,
            reason="repeated_uncertain_selection",
            recommended_future_operation="collect_more_evidence",
        ),
    )
    return (
        review.review_status == "needs_more_evidence"
        and review.primary_issue == "repeated_uncertain_selection"
        and review.recommended_future_operation == "collect_more_evidence"
    )


def _case_mostly_clean() -> bool:
    review = ReflectionReviewBuilder(IdGenerator()).build(
        tick=3,
        history_snapshot=_snapshot("mostly_clean", observed_count=10, clean_count=8),
        reflection_candidates=[_candidate("stable_clean_selection", "info", 0.8)],
        need_more_evidence_signal=_signal(active=False),
    )
    return (
        review.review_status == "stable_recent_behavior"
        and review.severity == "info"
        and review.recommended_future_operation == "maintain_current_policy"
    )


def _case_guard_tension() -> bool:
    review = ReflectionReviewBuilder(IdGenerator()).build(
        tick=4,
        history_snapshot=_snapshot("guard_constrained_recent_history", observed_count=10, guard_constrained_count=5),
        reflection_candidates=[_candidate("guard_policy_tension", "medium", 0.7)],
        need_more_evidence_signal=None,
    )
    return (
        review.review_status == "guard_policy_tension"
        and review.primary_issue == "guard_policy_tension"
        and review.recommended_future_operation == "inspect_guard_policy_tension"
    )


def _case_weak_value_signal() -> bool:
    review = ReflectionReviewBuilder(IdGenerator()).build(
        tick=5,
        history_snapshot=_snapshot("mostly_clean", observed_count=10, clean_count=7),
        reflection_candidates=[_candidate("weak_value_influence", "low", 0.8)],
        need_more_evidence_signal=_signal(active=False),
    )
    return (
        review.review_status == "weak_value_signal"
        and review.primary_issue == "weak_value_influence"
        and review.recommended_future_operation == "inspect_value_signal_coverage"
    )


def _case_mixed_state() -> bool:
    review = ReflectionReviewBuilder(IdGenerator()).build(
        tick=6,
        history_snapshot=_snapshot("mixed_recent_history", observed_count=10),
        reflection_candidates=[],
        need_more_evidence_signal=_signal(active=False),
    )
    return review.review_status == "mixed_reflection_state" and review.primary_issue == "mixed_cycle_history"


def _case_recent_bound() -> bool:
    builder = ReflectionReviewBuilder(IdGenerator(), max_recent_reflection_reviews=4)
    for tick in range(1, 10):
        builder.build(
            tick=tick,
            history_snapshot=None,
            reflection_candidates=[],
            need_more_evidence_signal=None,
        )
    recent = builder.recent_reviews(limit=10)
    return len(recent) == 4 and recent[0].tick == 6 and recent[-1].tick == 9


def _case_runtime_integration() -> bool:
    with tempfile.TemporaryDirectory(prefix="reflection_review_runtime_") as temp_dir:
        memory_root = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", memory_root)
        runtime = CLCRuntime(memory_root, profile=RuntimeProfile.SAFE_DEMO, memory_is_temporary=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for tick, value in enumerate((0.2, 0.9, 0.25, 0.85), start=1):
                runtime.feed_audio(tick, {440: value, 880: 0.2, 1200: 0.1})
        return runtime.reflection_review is not None and "reflection review:" in output.getvalue()


def _case_disconnected_behavior() -> bool:
    forbidden = ("ReflectionReview", "ReflectionReviewBuilder", "reflection_review")
    for relative_path in DISCONNECTED_FILES:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            return False
    return True


def _snapshot(
    trend_label: str,
    *,
    observed_count: int,
    window_size: int = 20,
    clean_count: int = 0,
    uncertain_count: int = 0,
    guard_constrained_count: int = 0,
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
        value_influenced_count=0,
        guard_constrained_count=guard_constrained_count,
        uncertain_count=uncertain_count,
        risky_or_constrained_count=0,
        clean_count=clean_count,
        dominant_status=next(iter(status_counts), None),
        dominant_confidence="medium" if observed_count else None,
        trend_label=trend_label,
    )


def _candidate(reflection_type: str, severity: str, confidence: float) -> ReflectionCandidate:
    return ReflectionCandidate(
        reflection_candidate_id=f"{reflection_type}_001",
        tick=1,
        reflection_type=reflection_type,
        severity=severity,
        confidence=confidence,
        source="decision_cycle_history_view",
        source_trend_label="verify_trend",
        evidence={"observed_count": 1},
        recommended_future_operation="verify_future_operation",
        apply_now=False,
        tags=(reflection_type,),
    )


def _signal(
    *,
    active: bool,
    severity: str = "info",
    confidence: float = 0.0,
    reason: str = "no_evidence_gap_detected",
    recommended_future_operation: str = "maintain_current_policy",
) -> NeedMoreEvidenceSignal:
    return NeedMoreEvidenceSignal(
        signal_id="need_more_evidence_signal_001",
        tick=1,
        active=active,
        severity=severity,
        confidence=confidence,
        reason=reason,
        source_reflection_types=(reason,) if active else (),
        recommended_future_operation=recommended_future_operation,
        evidence={},
        apply_now=False,
        tags=(reason,),
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
