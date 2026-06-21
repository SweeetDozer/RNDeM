from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.core.pattern_registry import PatternRegistry  # noqa: E402
from clc.experience.causal_trace import CausalTrace  # noqa: E402
from clc.experience.learnability_filter import LearnabilityFilter  # noqa: E402


MANIFEST_PATH = PROJECT_ROOT / "Memory" / "pattern_manifest.json"

AUDIT_NAMES = (
    "decision_audit_observed",
    "decision_audit_clear_win",
    "action_guard_audit_observed",
    "action_guard_audit_blocked_high_score_candidate",
    "decision_cycle_summary",
    "decision_cycle_uncertain_selection",
)

INTERNAL_NAMES = (
    "consolidation_pressure",
    "system_mode_active",
    "homeostasis_update",
    "memory_write_review",
    "memory_draft_written",
    "memory_committed",
    "memory_updated",
    "expsm_update_review",
    "value_feedback_review",
    "value_feedback_updated",
)

OLD_NON_LEARNABLE_NAMES = AUDIT_NAMES + INTERNAL_NAMES + (
    "action_enter_consolidation_mode",
    "action_exit_consolidation_mode",
    "state_consolidation_mode_entered",
    "state_consolidation_mode_exited",
    "state_consolidation_processing",
    "state_pending_candidates_reviewed",
    "state_context_load_reduced",
    "state_memory_candidate_created",
    "action_commit_memory_draft",
    "action_review_committed_memory_update",
    "action_update_committed_expsm_record",
    "expsm_activation",
    "evaluation_signal",
    "akbsm_association_probe",
    "target_satisfaction_observer",
)


def main() -> int:
    registry = PatternRegistry(MANIFEST_PATH)
    learnability_filter = LearnabilityFilter(registry)

    audit_patterns_non_learnable = all(
        registry.is_audit(registry.id(name))
        and registry.is_non_learnable(registry.id(name))
        and learnability_filter.classify_trace(_trace(predicted=(registry.id(name),)))["learnable"] is False
        for name in AUDIT_NAMES
        if registry.has_name(name)
    )
    internal_patterns_non_learnable = all(
        registry.is_non_learnable(registry.id(name))
        and learnability_filter.classify_trace(_trace(predicted=(registry.id(name),)))["learnable"] is False
        for name in INTERNAL_NAMES
        if registry.has_name(name)
    )
    normal_action_effect_learnable = learnability_filter.classify_trace(
        _trace(decisions=("action_preserve_integrity",), effects=("state_integrity_preservation",), registry=registry)
    )["learnable"] is True
    normal_prediction_learnable = learnability_filter.classify_trace(
        _trace(predicted=("prediction_future_state",), registry=registry)
    )["learnable"] is True
    input_not_blanket_rejected = registry.learnability(registry.id("aud_freq_440")) == "normal" and not registry.is_non_learnable(registry.id("aud_freq_440"))
    unknown_defaults_safe = (
        registry.learnability("missing") == "unknown"
        and registry.semantic_class("missing") == "unknown"
        and not registry.is_non_learnable("missing")
        and learnability_filter.classify_trace(_trace(predicted=("missing",)))["learnable"] is True
    )
    old_names_covered = _old_names_covered(registry)
    no_debug_name_dependency = "debug_name" not in (PROJECT_ROOT / "clc" / "experience" / "learnability_filter.py").read_text(encoding="utf-8")

    checks = {
        "audit_patterns_non_learnable": audit_patterns_non_learnable,
        "internal_patterns_non_learnable": internal_patterns_non_learnable,
        "normal_action_effect_learnable": normal_action_effect_learnable,
        "normal_prediction_learnable": normal_prediction_learnable,
        "input_not_blanket_rejected": input_not_blanket_rejected,
        "unknown_defaults_safe": unknown_defaults_safe,
        "old_non_learnable_names_covered_by_metadata": old_names_covered,
        "no_debug_name_dependency": no_debug_name_dependency,
    }
    print("LearnabilityFilter semantic migration verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if all(checks.values()) else 'FAIL'}")
    return 0 if all(checks.values()) else 1


def _trace(
    *,
    decisions: tuple[str, ...] = (),
    effects: tuple[str, ...] = (),
    predicted: tuple[str, ...] = (),
    registry: PatternRegistry | None = None,
) -> CausalTrace:
    if registry is not None:
        decisions = tuple(registry.id(item) for item in decisions)
        effects = tuple(registry.id(item) for item in effects)
        predicted = tuple(registry.id(item) for item in predicted)
    return CausalTrace(
        source_outcome_id="verify_learnability",
        source_outcome_status="confirmed",
        decision_event_ids=(),
        effect_event_ids=(),
        prediction_event_ids=(),
        decision_patterns=decisions,
        effect_patterns=effects,
        predicted_patterns=predicted,
        outcome_patterns=(),
        context_label_event_ids=(),
        context_frame_ids=(),
        context_window_ids=(),
        context_active_patterns=(),
        context_prediction_event_ids=(),
    )


def _old_names_covered(registry: PatternRegistry) -> bool:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    semantics = data.get("semantics", {})
    for name in OLD_NON_LEARNABLE_NAMES:
        if not registry.has_name(name):
            continue
        pattern_id = registry.id(name)
        metadata = semantics.get(pattern_id, {})
        tags = set(metadata.get("tags", [])) if isinstance(metadata, dict) else set()
        if not (
            registry.is_non_learnable(pattern_id)
            or registry.is_audit(pattern_id)
            or registry.semantic_class(pattern_id) in {"system", "debug", "retention"}
            or "internal" in tags
        ):
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
