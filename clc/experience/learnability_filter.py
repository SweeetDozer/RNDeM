from typing import Any

from clc.core.pattern_registry import PatternRegistry
from clc.experience.causal_trace import CausalTrace


NON_LEARNABLE_CLASSES = {"audit", "system", "debug", "retention", "memory", "consolidation", "evaluation", "target", "akbsm", "expsm", "tone"}


class LearnabilityFilter:
    """Classifies whether a causal trace should become ordinary experience memory."""

    module_name = "learnability_filter"

    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.pattern_registry = pattern_registry
        self.reason_patterns = {
            "normal": pattern_registry.id("learnability_normal_action_effect"),
            "maintenance": pattern_registry.id("learnability_skip_maintenance"),
            "mode_management": pattern_registry.id("learnability_skip_mode_management"),
            "consolidation_internal": pattern_registry.id("learnability_skip_consolidation_internal"),
            "homeostasis": pattern_registry.id("learnability_skip_homeostasis"),
            "unknown": pattern_registry.id("learnability_unknown"),
            "skipped": pattern_registry.id("learnability_skipped"),
        }

    def classify_trace(self, trace: CausalTrace) -> dict[str, Any]:
        core_patterns = tuple(trace.decision_patterns + trace.effect_patterns + trace.predicted_patterns)
        if self._any_tag(core_patterns, "mode_management"):
            return self._classification("mode_management", False, "mode_management", 0.95)
        if self._any_tag(core_patterns, "homeostasis"):
            return self._classification("homeostasis", False, "homeostasis", 0.9)
        if self._any_tag(core_patterns, "maintenance"):
            return self._classification("maintenance", False, "maintenance", 0.9)
        if any(self._is_consolidation_internal(pattern_id) for pattern_id in core_patterns):
            return self._classification("consolidation_internal", False, "consolidation_internal", 0.95)

        if trace.decision_patterns or trace.effect_patterns:
            if self._all_tagged(trace.decision_patterns, "ordinary_action") and self._all_tagged(trace.effect_patterns, "ordinary_effect"):
                return self._classification("learnable", True, "normal", 0.85)
            return self._classification("unknown", False, "unknown", 0.55)

        if trace.predicted_patterns and not any(self._is_non_learnable(pattern_id) for pattern_id in trace.predicted_patterns):
            return self._classification("learnable", True, "normal", 0.6)

        return self._classification("unknown", False, "unknown", 0.5)

    def is_learnable(self, trace: CausalTrace) -> bool:
        return bool(self.classify_trace(trace)["learnable"])

    def _classification(self, category: str, learnable: bool, reason_key: str, confidence: float) -> dict[str, Any]:
        reason_patterns = [self.reason_patterns[reason_key]]
        if not learnable:
            reason_patterns.append(self.reason_patterns["skipped"])
        return {
            "category": category,
            "learnable": learnable,
            "reason_patterns": reason_patterns,
            "confidence": confidence,
        }

    def _any_tag(self, pattern_ids: tuple[str, ...], tag: str) -> bool:
        return any(self.pattern_registry.has_tag(pattern_id, tag) for pattern_id in pattern_ids)

    def _all_tagged(self, pattern_ids: tuple[str, ...], tag: str) -> bool:
        return all(self.pattern_registry.has_tag(pattern_id, tag) for pattern_id in pattern_ids)

    def _is_consolidation_internal(self, pattern_id: str) -> bool:
        return self.pattern_registry.has_tag(pattern_id, "consolidation_internal") or (
            self._is_non_learnable(pattern_id)
            and self.pattern_registry.semantic_class(pattern_id) in NON_LEARNABLE_CLASSES
        )

    def _is_non_learnable(self, pattern_id: str) -> bool:
        return (
            self.pattern_registry.is_non_learnable(pattern_id)
            or self.pattern_registry.is_audit(pattern_id)
            or self.pattern_registry.semantic_class(pattern_id) in {"system", "debug", "retention"}
        )
