from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.core.pattern_registry import PatternRegistry  # noqa: E402


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
    before = {name: registry.id(name) for name in KNOWN_NAMES}
    reverse_ok = all(registry.debug_name(pattern_id) == name for name, pattern_id in before.items())
    registry.validate()

    with tempfile.TemporaryDirectory(prefix="pattern_registry_verify_") as temp_dir:
        temp_manifest = Path(temp_dir) / "pattern_manifest.json"
        shutil.copy2(manifest_path, temp_manifest)
        temp_registry = PatternRegistry(temp_manifest)
        temp_before = {name: temp_registry.id(name) for name in KNOWN_NAMES}
        inserted_id = temp_registry.register_if_missing("zz_verify_inserted_pattern")
        temp_reloaded = PatternRegistry(temp_manifest)
        temp_after = {name: temp_reloaded.id(name) for name in KNOWN_NAMES}
        inserted_stable = temp_reloaded.id("zz_verify_inserted_pattern") == inserted_id
        temp_reloaded.validate()

    known_ids_stable = before == {name: registry.id(name) for name in KNOWN_NAMES} and temp_before == temp_after
    result = bool(manifest_path.exists() and known_ids_stable and reverse_ok and inserted_stable)
    print("PatternRegistry stability verification:")
    print(f"  manifest exists: {'yes' if manifest_path.exists() else 'no'}")
    print(f"  known ids stable: {'yes' if known_ids_stable else 'no'}")
    print(f"  reverse mapping stable: {'yes' if reverse_ok else 'no'}")
    print("  validation: PASS")
    print(f"  result: {'PASS' if result else 'FAIL'}")
    if not result:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
