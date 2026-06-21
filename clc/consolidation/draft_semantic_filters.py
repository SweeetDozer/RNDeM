from clc.core.pattern_registry import PatternRegistry


DRAFT_MATERIAL_CLASSES = {
    "input",
    "label",
    "prediction",
    "action",
    "effect",
    "outcome",
    "target",
    "evaluation",
    "expsm",
    "akbsm",
    "memory",
    "tone",
}
TECHNICAL_CLASSES = {"system", "debug", "retention"}
TECHNICAL_TAGS = {
    "audit",
    "internal",
    "memory_write_technical",
    "mode_management",
    "consolidation_internal",
    "maintenance",
    "homeostasis",
}
DRAFT_FAMILY_TAGS = {
    "draft_family_integrity",
    "draft_family_load",
    "draft_family_attention",
    "draft_family_inspection",
}


def is_draft_technical_noise(pattern_registry: PatternRegistry, pattern_id: str) -> bool:
    semantic_class = pattern_registry.semantic_class(pattern_id)
    tags = pattern_registry.tags(pattern_id)
    if pattern_registry.is_audit(pattern_id):
        return True
    if semantic_class in TECHNICAL_CLASSES:
        return True
    if tags.intersection(TECHNICAL_TAGS):
        return True
    return pattern_registry.is_non_learnable(pattern_id) and semantic_class not in DRAFT_MATERIAL_CLASSES


def is_draft_context_material(pattern_registry: PatternRegistry, pattern_id: str) -> bool:
    if is_draft_technical_noise(pattern_registry, pattern_id):
        return False
    return pattern_registry.semantic_class(pattern_id) in DRAFT_MATERIAL_CLASSES


def draft_core_families(pattern_registry: PatternRegistry, pattern_ids: list[str]) -> set[str]:
    families: set[str] = set()
    for pattern_id in pattern_ids:
        families.update(pattern_registry.tags(pattern_id).intersection(DRAFT_FAMILY_TAGS))
    return families


def matches_draft_core_family(pattern_registry: PatternRegistry, pattern_id: str, core_families: set[str]) -> bool:
    return bool(pattern_registry.tags(pattern_id).intersection(core_families))


def different_modality_without_link(pattern_registry: PatternRegistry, pattern_id: str, core_families: set[str]) -> bool:
    if "draft_family_integrity" in core_families and pattern_registry.has_tag(pattern_id, "visual_attention"):
        return True
    if "draft_family_load" in core_families and pattern_registry.has_tag(pattern_id, "visual_input"):
        return True
    return False


def competing_draft_family(pattern_registry: PatternRegistry, pattern_id: str, core_families: set[str]) -> bool:
    if "draft_family_integrity" in core_families and pattern_registry.has_tag(pattern_id, "draft_family_attention"):
        return True
    if "draft_family_attention" in core_families and pattern_registry.has_tag(pattern_id, "draft_family_integrity"):
        return True
    return False


def is_generic_draft_context(pattern_registry: PatternRegistry, pattern_id: str) -> bool:
    return pattern_registry.has_tag(pattern_id, "generic_draft_context")


def is_confirmed_outcome(pattern_registry: PatternRegistry, pattern_id: str) -> bool:
    return pattern_registry.has_tag(pattern_id, "confirmed_outcome")
