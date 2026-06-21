from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.core.pattern_registry import infer_pattern_semantics  # noqa: E402


MANIFEST_PATH = PROJECT_ROOT / "Memory" / "pattern_manifest.json"


def main() -> int:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ids = data.get("ids", {})
    if not isinstance(ids, dict):
        raise ValueError("pattern manifest ids must be an object")
    existing_semantics = data.get("semantics", {})
    if existing_semantics is None:
        existing_semantics = {}
    if not isinstance(existing_semantics, dict):
        raise ValueError("pattern manifest semantics must be an object when present")

    before_ids = dict(ids)
    before_patterns = dict(data.get("patterns", {}))
    before_next = data.get("next_pattern_number")
    semantics: dict[str, dict[str, object]] = {}
    changed = False
    enriched = 0
    for pattern_id, name in ids.items():
        inferred = infer_pattern_semantics(str(name))
        current = existing_semantics.get(pattern_id)
        if current != inferred:
            changed = True
        if not isinstance(current, dict):
            enriched += 1
        semantics[str(pattern_id)] = inferred

    data["semantics"] = semantics
    if before_ids != data.get("ids") or before_patterns != data.get("patterns") or before_next != data.get("next_pattern_number"):
        raise RuntimeError("semantic enrichment attempted to change ids, names, or next_pattern_number")

    if changed:
        MANIFEST_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    class_counts = Counter(item["semantic_class"] for item in semantics.values())
    tag_counts = Counter(tag for item in semantics.values() for tag in item["tags"])
    learnability_counts = Counter(item["learnability"] for item in semantics.values())
    print("Pattern semantic enrichment:")
    print(f"  manifest: {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  patterns: {len(ids)}")
    print(f"  enriched_missing: {enriched}")
    print(f"  changed: {'yes' if changed else 'no'}")
    print(f"  semantic_class_counts: {dict(sorted(class_counts.items()))}")
    print(f"  tag_counts: {dict(sorted(tag_counts.items()))}")
    print(f"  learnability_counts: {dict(sorted(learnability_counts.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
