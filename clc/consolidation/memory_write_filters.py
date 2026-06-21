from clc.core.pattern_registry import PatternRegistry


MATERIAL_CLASSES = {"input", "action", "effect", "outcome", "prediction", "target", "evaluation", "expsm", "akbsm"}
TECHNICAL_CLASSES = {"system", "debug", "retention"}
TECHNICAL_TAGS = {
    "audit",
    "internal",
    "memory_write_review",
    "memory_draft_written",
    "memory_draft_commit_review",
    "memory_committed",
    "committed_draft_observed",
    "expsm_update_review",
    "memory_updated",
    "value_feedback_review",
    "value_feedback_updated",
    "module_update",
    "system_mode_change",
    "consolidation_pressure",
    "retention",
    "memory_write_technical",
}


def is_memory_write_technical_pattern(pattern_registry: PatternRegistry, pattern_id: str) -> bool:
    semantic_class = pattern_registry.semantic_class(pattern_id)
    tags = pattern_registry.tags(pattern_id)
    if pattern_registry.is_audit(pattern_id):
        return True
    if pattern_registry.is_internal_only(pattern_id) and semantic_class not in MATERIAL_CLASSES:
        return True
    if pattern_registry.is_non_learnable(pattern_id) and semantic_class not in MATERIAL_CLASSES:
        return True
    if semantic_class in TECHNICAL_CLASSES:
        return True
    return bool(tags.intersection(TECHNICAL_TAGS))
