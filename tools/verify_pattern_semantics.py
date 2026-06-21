from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.core.pattern_registry import ALLOWED_LEARNABILITY_VALUES, ALLOWED_SEMANTIC_CLASSES, PatternRegistry  # noqa: E402


MANIFEST_PATH = PROJECT_ROOT / "Memory" / "pattern_manifest.json"


def main() -> int:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    registry = PatternRegistry(MANIFEST_PATH)
    ids = data.get("ids", {})
    semantics = data.get("semantics", {})

    fields_present = _fields_present(ids, semantics)
    fields_valid = _fields_valid(semantics)
    action_ok = _known_name(registry, "action_preserve_integrity", "is_action")
    decision_audit_ok = _known_name(registry, "decision_audit_observed", "is_audit")
    guard_audit_ok = _known_name(registry, "action_guard_audit_observed", "is_audit")
    cycle_audit_ok = _known_name(registry, "decision_cycle_summary", "is_audit")
    missing_defaults_ok = (
        registry.semantic_class("missing") == "unknown"
        and registry.learnability("missing") == "unknown"
        and registry.tags("missing") == set()
        and not registry.is_action("missing")
        and not registry.is_audit("missing")
        and not registry.is_non_learnable("missing")
    )
    debug_name_ok = registry.debug_name(registry.id("action_preserve_integrity")) == "action_preserve_integrity"
    ids_stable = all(registry.debug_name(pattern_id) == name for pattern_id, name in ids.items())

    checks = {
        "manifest_semantic_fields_present": fields_present,
        "manifest_semantic_fields_valid": fields_valid,
        "known_action_is_action": action_ok,
        "decision_audit_is_audit": decision_audit_ok,
        "guard_audit_is_audit": guard_audit_ok,
        "decision_cycle_is_audit": cycle_audit_ok,
        "unknown_defaults_safe": missing_defaults_ok,
        "debug_name_preserved": debug_name_ok,
        "ids_names_stable": ids_stable,
    }
    print("Pattern semantics verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if all(checks.values()) else 'FAIL'}")
    return 0 if all(checks.values()) else 1


def _fields_present(ids: object, semantics: object) -> bool:
    if not isinstance(ids, dict) or not isinstance(semantics, dict):
        return False
    if set(ids) != set(semantics):
        return False
    return all(
        isinstance(metadata, dict)
        and "semantic_class" in metadata
        and "tags" in metadata
        and "learnability" in metadata
        for metadata in semantics.values()
    )


def _fields_valid(semantics: object) -> bool:
    if not isinstance(semantics, dict):
        return False
    for metadata in semantics.values():
        if not isinstance(metadata, dict):
            return False
        tags = metadata.get("tags")
        if metadata.get("semantic_class") not in ALLOWED_SEMANTIC_CLASSES:
            return False
        if metadata.get("learnability") not in ALLOWED_LEARNABILITY_VALUES:
            return False
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            return False
    return True


def _known_name(registry: PatternRegistry, name: str, check: str) -> bool:
    if not registry.has_name(name):
        return True
    pattern_id = registry.id(name)
    if check == "is_action":
        return registry.is_action(pattern_id)
    if check == "is_audit":
        return registry.is_audit(pattern_id)
    return False


if __name__ == "__main__":
    raise SystemExit(main())
