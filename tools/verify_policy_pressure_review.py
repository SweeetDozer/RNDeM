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
from clc.evaluation.policy_pressure import PolicyPressure  # noqa: E402
from clc.evaluation.policy_pressure_review import PolicyPressureReviewBuilder  # noqa: E402
from clc.runtime.clc_runtime import CLCRuntime  # noqa: E402
from clc.runtime.memory_mutation_policy import RuntimeProfile  # noqa: E402


DISCONNECTED_FILES = (
    "clc/action/decision_selector.py",
    "clc/action/action_proposer.py",
    "clc/action/action_scoring.py",
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
        "no pressure": _case_no_pressure(),
        "evidence pressure": _case_evidence_pressure(),
        "guard pressure": _case_guard_pressure(),
        "value signal pressure": _case_value_signal_pressure(),
        "stability pressure": _case_stability_pressure(),
        "mixed pressure": _case_mixed_pressure(),
        "recent bound": _case_recent_bound(),
        "runtime integration": _case_runtime_integration(),
        "disconnected behavior": _case_disconnected_behavior(),
        "real ExpSM unchanged": real_expsm_before == _hash_file(real_expsm_path),
        "real AKBSM unchanged": real_akbsm_before == _hash_file(real_akbsm_path),
    }
    passed = all(checks.values())
    print("Policy pressure review verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_no_pressure() -> bool:
    review = PolicyPressureReviewBuilder(IdGenerator()).build(tick=1, policy_pressure=None)
    return (
        review.review_status == "no_pressure_data"
        and review.severity == "info"
        and review.confidence == 0.0
        and review.pressure_type == "no_policy_pressure"
        and review.pressure_active is False
        and review.apply_now is False
    )


def _case_evidence_pressure() -> bool:
    review = PolicyPressureReviewBuilder(IdGenerator()).build(
        tick=2,
        policy_pressure=_pressure(
            pressure_type="evidence_pressure",
            active=True,
            severity="medium",
            confidence=1.0,
            source_primary_issue="repeated_uncertain_selection",
            recommended_future_operation="collect_more_evidence",
        ),
    )
    return (
        review.review_status == "evidence_pressure_review"
        and review.primary_issue == "repeated_uncertain_selection"
        and review.recommended_future_operation == "collect_more_evidence"
        and review.apply_now is False
    )


def _case_guard_pressure() -> bool:
    review = PolicyPressureReviewBuilder(IdGenerator()).build(
        tick=3,
        policy_pressure=_pressure(pressure_type="guard_pressure", active=True, source_primary_issue="other"),
    )
    return (
        review.review_status == "guard_pressure_review"
        and review.primary_issue == "guard_policy_tension"
        and review.recommended_future_operation == "inspect_guard_policy_tension"
    )


def _case_value_signal_pressure() -> bool:
    review = PolicyPressureReviewBuilder(IdGenerator()).build(
        tick=4,
        policy_pressure=_pressure(pressure_type="value_signal_pressure", active=True, source_primary_issue="other"),
    )
    return (
        review.review_status == "value_signal_pressure_review"
        and review.primary_issue == "weak_value_influence"
        and review.recommended_future_operation == "inspect_value_signal_coverage"
    )


def _case_stability_pressure() -> bool:
    review = PolicyPressureReviewBuilder(IdGenerator()).build(
        tick=5,
        policy_pressure=_pressure(
            pressure_type="stability_pressure",
            active=False,
            severity="info",
            confidence=0.8,
            source_primary_issue="stable_recent_behavior",
            recommended_future_operation="maintain_current_policy",
        ),
    )
    return (
        review.review_status == "stability_pressure_review"
        and review.pressure_active is False
        and review.recommended_future_operation == "maintain_current_policy"
        and review.apply_now is False
    )


def _case_mixed_pressure() -> bool:
    review = PolicyPressureReviewBuilder(IdGenerator()).build(
        tick=6,
        policy_pressure=_pressure(pressure_type="mixed_policy_pressure", active=True),
    )
    return (
        review.review_status == "mixed_pressure_review"
        and review.primary_issue == "mixed_cycle_history"
        and review.recommended_future_operation == "review_mixed_history"
    )


def _case_recent_bound() -> bool:
    builder = PolicyPressureReviewBuilder(IdGenerator(), max_recent_policy_pressure_reviews=4)
    for tick in range(1, 10):
        builder.build(tick=tick, policy_pressure=None)
    recent = builder.recent_reviews(limit=10)
    return len(recent) == 4 and recent[0].tick == 6 and recent[-1].tick == 9


def _case_runtime_integration() -> bool:
    with tempfile.TemporaryDirectory(prefix="policy_pressure_review_runtime_") as temp_dir:
        memory_root = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", memory_root)
        runtime = CLCRuntime(memory_root, profile=RuntimeProfile.SAFE_DEMO, memory_is_temporary=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for tick, value in enumerate((0.2, 0.9, 0.25, 0.85), start=1):
                runtime.feed_audio(tick, {440: value, 880: 0.2, 1200: 0.1})
        return runtime.policy_pressure_review is not None and "policy pressure review:" in output.getvalue()


def _case_disconnected_behavior() -> bool:
    forbidden = ("PolicyPressureReview", "PolicyPressureReviewBuilder", "policy_pressure_review")
    for relative_path in DISCONNECTED_FILES:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            return False
    return True


def _pressure(
    *,
    pressure_type: str,
    active: bool,
    severity: str = "low",
    confidence: float = 0.6,
    source_review_status: str = "verify_review",
    source_primary_issue: str = "mixed_cycle_history",
    recommended_future_operation: str = "review_mixed_history",
) -> PolicyPressure:
    return PolicyPressure(
        pressure_id="policy_pressure_001",
        tick=1,
        active=active,
        pressure_type=pressure_type,
        severity=severity,
        confidence=confidence,
        source_review_status=source_review_status,
        source_primary_issue=source_primary_issue,
        recommended_future_operation=recommended_future_operation,
        apply_now=False,
        evidence={},
        tags=(pressure_type,),
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
