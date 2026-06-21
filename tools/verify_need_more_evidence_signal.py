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
from clc.evaluation.need_more_evidence_signal import NeedMoreEvidenceSignalBuilder  # noqa: E402
from clc.evaluation.reflection_candidate_builder import ReflectionCandidate  # noqa: E402
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
        "no reflection candidates": _case_no_reflection_candidates(),
        "repeated uncertain selection": _case_repeated_uncertain_selection(),
        "insufficient decision confidence": _case_insufficient_decision_confidence(),
        "stable clean selection": _case_stable_clean_selection(),
        "priority selection": _case_priority_selection(),
        "guard policy tension": _case_guard_policy_tension(),
        "weak value warning inactive": _case_weak_value_warning_inactive(),
        "recent bound": _case_recent_bound(),
        "runtime integration": _case_runtime_integration(),
        "disconnected behavior": _case_disconnected_behavior(),
        "real ExpSM unchanged": real_expsm_before == _hash_file(real_expsm_path),
        "real AKBSM unchanged": real_akbsm_before == _hash_file(real_akbsm_path),
    }
    passed = all(checks.values())
    print("Need more evidence signal verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_no_reflection_candidates() -> bool:
    signal = NeedMoreEvidenceSignalBuilder(IdGenerator()).build(tick=1, reflection_candidates=[])
    return (
        signal.active is False
        and signal.severity == "info"
        and signal.reason == "no_evidence_gap_detected"
        and signal.apply_now is False
    )


def _case_repeated_uncertain_selection() -> bool:
    signal = NeedMoreEvidenceSignalBuilder(IdGenerator()).build(
        tick=2,
        reflection_candidates=[_candidate("repeated_uncertain_selection", "medium", 1.0)],
    )
    return (
        signal.active is True
        and signal.severity == "medium"
        and signal.reason == "repeated_uncertain_selection"
        and signal.recommended_future_operation == "collect_more_evidence"
        and signal.confidence == 1.0
        and signal.apply_now is False
    )


def _case_insufficient_decision_confidence() -> bool:
    signal = NeedMoreEvidenceSignalBuilder(IdGenerator()).build(
        tick=3,
        reflection_candidates=[_candidate("insufficient_decision_confidence", "low", 0.2)],
    )
    return (
        signal.active is True
        and signal.severity == "low"
        and signal.reason == "insufficient_decision_confidence"
        and signal.recommended_future_operation == "collect_more_evidence"
    )


def _case_stable_clean_selection() -> bool:
    signal = NeedMoreEvidenceSignalBuilder(IdGenerator()).build(
        tick=4,
        reflection_candidates=[_candidate("stable_clean_selection", "info", 1.0)],
    )
    return (
        signal.active is False
        and signal.reason == "no_evidence_gap_detected"
        and signal.recommended_future_operation == "maintain_current_policy"
    )


def _case_priority_selection() -> bool:
    signal = NeedMoreEvidenceSignalBuilder(IdGenerator()).build(
        tick=5,
        reflection_candidates=[
            _candidate("weak_value_influence", "low", 0.8),
            _candidate("repeated_uncertain_selection", "medium", 0.9),
            _candidate("guard_policy_tension", "medium", 0.95),
        ],
    )
    return signal.active is True and signal.reason == "repeated_uncertain_selection"


def _case_guard_policy_tension() -> bool:
    signal = NeedMoreEvidenceSignalBuilder(IdGenerator()).build(
        tick=6,
        reflection_candidates=[_candidate("guard_policy_tension", "medium", 0.7)],
    )
    return (
        signal.active is True
        and signal.reason == "guard_policy_tension"
        and signal.recommended_future_operation == "inspect_guard_policy_tension"
    )


def _case_weak_value_warning_inactive() -> bool:
    signal = NeedMoreEvidenceSignalBuilder(IdGenerator()).build(
        tick=7,
        reflection_candidates=[_candidate("weak_value_influence", "low", 0.9)],
    )
    return (
        signal.active is False
        and signal.reason == "no_evidence_gap_detected"
        and signal.evidence["warning_reflection_types"] == ["weak_value_influence"]
    )


def _case_recent_bound() -> bool:
    builder = NeedMoreEvidenceSignalBuilder(IdGenerator(), max_recent_need_more_evidence_signals=4)
    for tick in range(1, 10):
        builder.build(tick=tick, reflection_candidates=[])
    recent = builder.recent_signals(limit=10)
    return len(recent) == 4 and recent[0].tick == 6 and recent[-1].tick == 9


def _case_runtime_integration() -> bool:
    with tempfile.TemporaryDirectory(prefix="need_more_evidence_runtime_") as temp_dir:
        memory_root = Path(temp_dir) / "Memory"
        shutil.copytree(ROOT / "Memory", memory_root)
        runtime = CLCRuntime(memory_root, profile=RuntimeProfile.SAFE_DEMO, memory_is_temporary=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for tick, value in enumerate((0.2, 0.9, 0.25, 0.85), start=1):
                runtime.feed_audio(tick, {440: value, 880: 0.2, 1200: 0.1})
        signal = runtime.need_more_evidence_signal
        return signal is not None and "need more evidence signal:" in output.getvalue()


def _case_disconnected_behavior() -> bool:
    forbidden = ("NeedMoreEvidenceSignal", "NeedMoreEvidenceSignalBuilder", "need_more_evidence")
    for relative_path in DISCONNECTED_FILES:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            return False
    return True


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
