from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.core.pattern_registry import ALLOWED_LEARNABILITY_VALUES, ALLOWED_SEMANTIC_CLASSES, PatternRegistry  # noqa: E402


KNOWN_NAMES = (
    "action_preserve_integrity",
    "expsm_activation",
    "expsm_feedback",
    "expsm_competition_observed",
    "memory_updated",
)


def main() -> int:
    manifest_path = PROJECT_ROOT / "Memory" / "pattern_manifest.json"
    registry = PatternRegistry(manifest_path)
    manifest_data = _load_manifest(manifest_path)
    before_ids = dict(manifest_data["ids"])
    before_patterns = dict(manifest_data["patterns"])
    before_next = manifest_data["next_pattern_number"]
    before = {name: registry.id(name) for name in KNOWN_NAMES}
    reverse_ok = all(registry.debug_name(pattern_id) == name for name, pattern_id in before.items())
    registry.validate()
    after_manifest_data = _load_manifest(manifest_path)
    ids_unchanged = before_ids == after_manifest_data["ids"]
    names_unchanged = before_patterns == after_manifest_data["patterns"]
    next_unchanged = before_next == after_manifest_data["next_pattern_number"]
    semantic_fields_valid = _semantic_fields_valid(after_manifest_data)

    with tempfile.TemporaryDirectory(prefix="pattern_registry_verify_") as temp_dir:
        temp_manifest = Path(temp_dir) / "pattern_manifest.json"
        shutil.copy2(manifest_path, temp_manifest)
        temp_registry = PatternRegistry(temp_manifest)
        temp_next_before = _load_manifest(temp_manifest)["next_pattern_number"]
        temp_before = {name: temp_registry.id(name) for name in KNOWN_NAMES}
        inserted_id = temp_registry.register_if_missing("zz_verify_inserted_pattern")
        temp_reloaded = PatternRegistry(temp_manifest)
        temp_next_after = _load_manifest(temp_manifest)["next_pattern_number"]
        temp_after = {name: temp_reloaded.id(name) for name in KNOWN_NAMES}
        inserted_stable = temp_reloaded.id("zz_verify_inserted_pattern") == inserted_id
        next_increased_for_insert = temp_next_after == temp_next_before + 1
        temp_reloaded.validate()

    known_ids_stable = before == {name: registry.id(name) for name in KNOWN_NAMES} and temp_before == temp_after
    result = bool(
        manifest_path.exists()
        and known_ids_stable
        and reverse_ok
        and inserted_stable
        and next_increased_for_insert
        and ids_unchanged
        and names_unchanged
        and next_unchanged
        and semantic_fields_valid
    )
    print("PatternRegistry stability verification:")
    print(f"  manifest exists: {'yes' if manifest_path.exists() else 'no'}")
    print(f"  known ids stable: {'yes' if known_ids_stable else 'no'}")
    print(f"  reverse mapping stable: {'yes' if reverse_ok else 'no'}")
    print(f"  ids unchanged during validation: {'yes' if ids_unchanged else 'no'}")
    print(f"  names unchanged during validation: {'yes' if names_unchanged else 'no'}")
    print(f"  next_pattern_number unchanged without insert: {'yes' if next_unchanged else 'no'}")
    print(f"  next_pattern_number advanced only on insert: {'yes' if next_increased_for_insert else 'no'}")
    print(f"  semantic fields valid: {'yes' if semantic_fields_valid else 'no'}")
    print("  validation: PASS")
    print(f"  result: {'PASS' if result else 'FAIL'}")
    if not result:
        return 1
    return 0


def _load_manifest(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _semantic_fields_valid(data: dict) -> bool:
    semantics = data.get("semantics", {})
    ids = data.get("ids", {})
    if not isinstance(semantics, dict) or set(semantics) != set(ids):
        return False
    for metadata in semantics.values():
        if not isinstance(metadata, dict):
            return False
        if metadata.get("semantic_class") not in ALLOWED_SEMANTIC_CLASSES:
            return False
        if metadata.get("learnability") not in ALLOWED_LEARNABILITY_VALUES:
            return False
        tags = metadata.get("tags")
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
