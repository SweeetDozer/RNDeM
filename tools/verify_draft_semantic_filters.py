from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.consolidation.draft_context_relevance_scorer import DraftContextRelevanceScorer  # noqa: E402
from clc.consolidation.draft_input_context_enricher import DraftInputContextEnricher  # noqa: E402
from clc.consolidation.draft_semantic_filters import (  # noqa: E402
    draft_core_families,
    is_draft_context_material,
    is_draft_technical_noise,
)
from clc.context.context_memory import ContextMemory  # noqa: E402
from clc.core.ids import IdGenerator  # noqa: E402
from clc.core.pattern_registry import PatternRegistry  # noqa: E402
from clc.field.active_context_field import ActiveContextField  # noqa: E402


MANIFEST_PATH = ROOT / "Memory" / "pattern_manifest.json"
MIGRATED_FILES = (
    ROOT / "clc" / "consolidation" / "draft_input_context_enricher.py",
    ROOT / "clc" / "consolidation" / "draft_context_relevance_scorer.py",
)


def main() -> int:
    registry = PatternRegistry(MANIFEST_PATH)
    useful_names = _existing(
        registry,
        (
            "aud_freq_440",
            "action_preserve_integrity",
            "state_integrity_preservation",
            "prediction_future_state",
            "outcome_confirmed",
        ),
    )
    technical_names = _existing(
        registry,
        (
            "decision_audit_observed",
            "action_guard_audit_observed",
            "decision_cycle_summary",
            "module_update",
            "system_mode_change",
            "consolidation_pressure",
            "memory_write_review",
            "memory_draft_written",
            "memory_updated",
            "value_feedback_review",
            "value_feedback_updated",
        ),
    )
    id_gen = IdGenerator()
    memory = ContextMemory(id_gen, registry)
    active_field = ActiveContextField()
    enricher = DraftInputContextEnricher(registry)
    scorer = DraftContextRelevanceScorer(registry)
    review_payload = {
        "core_chain": {
            "decision_patterns": [registry.id("action_preserve_integrity")],
            "effect_patterns": [registry.id("state_integrity_preservation")],
            "predicted_patterns": [registry.id("prediction_future_state")],
            "outcome_patterns": [registry.id("outcome_confirmed")],
        }
    }
    records = scorer.score_if_patterns([registry.id(name) for name in useful_names + technical_names], review_payload, memory, active_field)
    by_pattern = {record["pattern"]: record for record in records}
    positive_names = ("action_preserve_integrity", "state_integrity_preservation", "prediction_future_state")

    checks = {
        "useful_material_allowed": all(is_draft_context_material(registry, registry.id(name)) for name in useful_names),
        "useful_not_rejected_by_scorer": all(not by_pattern[registry.id(name)].get("rejected") for name in useful_names),
        "useful_positive_when_evidenced": all(by_pattern[registry.id(name)]["score"] > 0.0 for name in positive_names),
        "technical_noise_detected": all(is_draft_technical_noise(registry, registry.id(name)) for name in technical_names),
        "technical_rejected_by_scorer": all(by_pattern[registry.id(name)].get("rejected") for name in technical_names),
        "enricher_uses_semantic_filter": _enricher_filter_ok(enricher, registry, useful_names, technical_names),
        "prefix_semantics_mapped": _prefix_semantics_mapped(registry),
        "unknown_safe": _unknown_safe(registry),
        "no_debug_name_semantic_dependency": _no_debug_name_dependency(),
    }
    passed = all(checks.values())
    print("Draft semantic filters verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  useful examples: {', '.join(useful_names)}")
    print(f"  technical examples: {', '.join(technical_names)}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _existing(registry: PatternRegistry, names: tuple[str, ...]) -> list[str]:
    return [name for name in names if registry.has_name(name)]


def _enricher_filter_ok(
    enricher: DraftInputContextEnricher,
    registry: PatternRegistry,
    useful_names: list[str],
    technical_names: list[str],
) -> bool:
    return all(enricher._is_context_pattern(registry.id(name)) for name in useful_names) and all(
        not enricher._is_context_pattern(registry.id(name)) for name in technical_names
    )


def _prefix_semantics_mapped(registry: PatternRegistry) -> bool:
    action_id = registry.id("action_preserve_integrity")
    prediction_id = registry.id("prediction_future_state")
    outcome_id = registry.id("outcome_confirmed")
    evaluation_id = registry.id("evaluation_signal")
    target_id = registry.id("target_satisfaction_observer")
    expsm_id = registry.id("expsm_mechanism_search")
    akbsm_id = registry.id("akbsm_association_probe")
    core_families = draft_core_families(registry, [action_id, registry.id("state_integrity_preservation")])
    return (
        registry.semantic_class(action_id) == "action"
        and registry.semantic_class(prediction_id) == "prediction"
        and registry.semantic_class(outcome_id) == "outcome"
        and registry.semantic_class(evaluation_id) == "evaluation"
        and registry.semantic_class(target_id) == "target"
        and registry.semantic_class(expsm_id) == "expsm"
        and registry.semantic_class(akbsm_id) == "akbsm"
        and "draft_family_integrity" in core_families
    )


def _unknown_safe(registry: PatternRegistry) -> bool:
    return (
        registry.semantic_class("missing") == "unknown"
        and registry.learnability("missing") == "unknown"
        and registry.tags("missing") == set()
        and not is_draft_technical_noise(registry, "missing")
        and not is_draft_context_material(registry, "missing")
    )


def _no_debug_name_dependency() -> bool:
    return all("debug_name" not in path.read_text(encoding="utf-8") for path in MIGRATED_FILES)


if __name__ == "__main__":
    raise SystemExit(main())
