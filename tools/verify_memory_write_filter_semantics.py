from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.consolidation.memory_write_filters import is_memory_write_technical_pattern  # noqa: E402
from clc.core.pattern_registry import PatternRegistry  # noqa: E402


MANIFEST_PATH = ROOT / "Memory" / "pattern_manifest.json"
MIGRATED_FILES = (
    ROOT / "clc" / "consolidation" / "memory_write_filters.py",
    ROOT / "clc" / "consolidation" / "draft_commit_gate.py",
    ROOT / "clc" / "consolidation" / "expsm_commit_writer.py",
)


def main() -> int:
    registry = PatternRegistry(MANIFEST_PATH)
    technical_names = _existing(
        registry,
        (
            "memory_write_review",
            "memory_draft_written",
            "memory_draft_commit_review",
            "memory_committed",
            "committed_draft_observed",
            "expsm_update_review",
            "memory_updated",
            "value_feedback_review",
            "value_feedback_updated",
        ),
    )
    internal_names = _existing(
        registry,
        (
            "decision_audit_observed",
            "action_guard_audit_observed",
            "decision_cycle_summary",
            "module_update",
            "system_mode_change",
            "consolidation_pressure",
        ),
    )
    normal_names = _existing(
        registry,
        (
            "aud_freq_440",
            "action_preserve_integrity",
            "state_integrity_preservation",
            "prediction_future_state",
            "outcome_confirmed",
        ),
    )

    checks = {
        "technical metadata filtered": _all_filtered(registry, technical_names),
        "technical names tagged": _all_technical_metadata(registry, technical_names),
        "audit/system/internal filtered": _all_filtered(registry, internal_names),
        "normal material allowed": _none_filtered(registry, normal_names),
        "unknown safe": _unknown_safe(registry),
        "no debug_name semantic dependency": _no_debug_name_dependency(),
    }
    passed = all(checks.values())
    print("Memory-write filter semantics verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  technical examples: {', '.join(technical_names)}")
    print(f"  normal examples: {', '.join(normal_names)}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _existing(registry: PatternRegistry, names: tuple[str, ...]) -> list[str]:
    return [name for name in names if registry.has_name(name)]


def _all_filtered(registry: PatternRegistry, names: list[str]) -> bool:
    return bool(names) and all(is_memory_write_technical_pattern(registry, registry.id(name)) for name in names)


def _none_filtered(registry: PatternRegistry, names: list[str]) -> bool:
    return bool(names) and all(not is_memory_write_technical_pattern(registry, registry.id(name)) for name in names)


def _all_technical_metadata(registry: PatternRegistry, names: list[str]) -> bool:
    for name in names:
        pattern_id = registry.id(name)
        if not (
            registry.is_audit(pattern_id)
            or registry.is_non_learnable(pattern_id)
            or registry.is_internal_only(pattern_id)
            or registry.has_tag(pattern_id, "memory_write_technical")
        ):
            return False
    return bool(names)


def _unknown_safe(registry: PatternRegistry) -> bool:
    return (
        registry.semantic_class("missing") == "unknown"
        and registry.learnability("missing") == "unknown"
        and registry.tags("missing") == set()
        and not is_memory_write_technical_pattern(registry, "missing")
    )


def _no_debug_name_dependency() -> bool:
    return all("debug_name" not in path.read_text(encoding="utf-8") for path in MIGRATED_FILES)


if __name__ == "__main__":
    raise SystemExit(main())
