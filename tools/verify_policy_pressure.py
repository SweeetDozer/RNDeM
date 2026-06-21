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
from clc.evaluation.policy_pressure import PolicyPressureBuilder  # noqa: E402
from clc.evaluation.reflection_review import ReflectionReview  # noqa: E402
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
        "no review": _case_no_review(),
        "needs more evidence": _case_needs_more_evidence(),
        "uncertain recent behavior": _case_uncertain_recent_behavior(),
        "guard policy tension": _case_guard_policy_tension(),
        "weak value signal": _case_weak_value_signal(),
        "stable recent behavior": _case_stable_recent_behavior(),
        "recent bound": _case_recent_bound(),
        "runtime integration": _case_runtime_integration(),
        "disconnected behavior": _case_disconnected_behavior(),
        "real ExpSM unchanged": real_expsm_before == _hash_file(real_expsm_path),
        "real AKBSM unchanged": real_akbsm_before == _hash_file(real_akbsm_path),
    }
    passed = all(checks.values())
    print("Policy pressure verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_no_review() -> bool:
    pressure = PolicyPressureBuilder(IdGenerator()).build(tick=1, reflection_review=None)
    return (
        pressure.active is False
        and pressure.pressure_type == "no_policy_pressure"
        and pressure.severity == "info"
        and pressure.confidence == 0.0
        and pressure.apply_now is False
    )


def _case_needs_more_evidence() -> bool:
    pressure = PolicyPressureBuilder(IdGenerator()).build(
        tick=2,
        reflection_review=_review(
            review_status="needs_more_evidence",
            severity="medium",
            confidence=1.0,
            primary_issue="repeated_uncertain_selection",
            recommended_future_operation="collect_more_evidence",
        ),
    )
    return (
        pressure.active is True
        and pressure.pressure_type == "evidence_pressure"
        and pressure.severity == "medium"
        and pressure.confidence == 1.0
        and pressure.recommended_future_operation == "collect_more_evidence"
        and pressure.apply_now is False
    )


def _case_uncertain_recent_behavior() -> bool:
    pressure = PolicyPressureBuilder(IdGenerator()).build(
        tick=3,
        reflection_review=_review(review_status="uncertain_recent_behavior"),
    )
    return (
        pressure.active is True
        and pressure.pressure_type == "uncertainty_pressure"
        and pressure.recommended_future_operation == "inspect_candidate_discrimination"
    )


def _case_guard_policy_tension() -> bool:
    pressure = PolicyPressureBuilder(IdGenerator()).build(
        tick=4,
        reflection_review=_review(review_status="guard_policy_tension", severity="high"),
    )
    return (
        pressure.active is True
        and pressure.pressure_type == "guard_pressure"
        and pressure.severity == "high"
        and pressure.recommended_future_operation == "inspect_guard_policy_tension"
    )


def _case_weak_value_signal() -> bool:
    pressure = PolicyPressureBuilder(IdGenerator()).build(
        tick=5,
        reflection_review=_review(review_status="weak_value_signal"),
    )
    return (
        pressure.active is True
        and pressure.pressure_type == "value_signal_pressure"
        and pressure.recommended_future_operation == "inspect_value_signal_coverage"
    )


def _case_stable_recent_behavior() -> bool:
    pressure = PolicyPressureBuilder(IdGenerator()).build(
        tick=6,
        reflection_review=_review(
            review_status="stable_recent_behavior",
            severity="info",
            confidence=0.8,
            recommended_future_operation="maintain_current_policy",
        ),
    )
    return (
        pressure.active is False
        and pressure.pressure_type == "stability_pressure"
        and pressure.severity == "info"
        and pressure.confidence == 0.8
        and pressure.recommended_future_operation == "maintain_current_policy"
    )


def _case_recent_bound() -> bool:
    builder = PolicyPressureBuilder(IdGenerator(), max_recent_policy_pressures=4)
    for tick in range(1, 10):
        builder.build(tick=tick, reflection_review=None)
    recent = builder.recent_pressures(limit=10)
    return len(recent) == 4 and recent[0].tick == 6 and recent[-1].tick == 9


def _case_runtime_integration() -> bool:
    with tempfile.TemporaryDirectory(prefix="policy_pressure_runtime_") as temp_dir:
        memory_root = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", memory_root)
        runtime = CLCRuntime(memory_root, profile=RuntimeProfile.SAFE_DEMO, memory_is_temporary=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for tick, value in enumerate((0.2, 0.9, 0.25, 0.85), start=1):
                runtime.feed_audio(tick, {440: value, 880: 0.2, 1200: 0.1})
        return runtime.policy_pressure is not None and "policy pressure:" in output.getvalue()


def _case_disconnected_behavior() -> bool:
    forbidden = ("PolicyPressure", "PolicyPressureBuilder", "policy_pressure")
    for relative_path in DISCONNECTED_FILES:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            return False
    return True


def _review(
    *,
    review_status: str,
    severity: str = "medium",
    confidence: float = 0.6,
    primary_issue: str = "repeated_uncertain_selection",
    recommended_future_operation: str = "verify_future_operation",
) -> ReflectionReview:
    return ReflectionReview(
        review_id="reflection_review_001",
        tick=1,
        review_status=review_status,
        severity=severity,
        confidence=confidence,
        primary_issue=primary_issue,
        summary="verify summary",
        source_trend_label="verify_trend",
        need_more_evidence_active=review_status == "needs_more_evidence",
        source_reflection_types=(primary_issue,),
        recommended_future_operation=recommended_future_operation,
        apply_now=False,
        evidence={},
        tags=(review_status,),
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
