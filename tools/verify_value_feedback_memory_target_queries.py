from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.value_feedback_memory_view import ValueFeedbackMemoryView


REAL_EXPSM = PROJECT_ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"


def main() -> int:
    real_hash_before = _sha256(REAL_EXPSM)
    with tempfile.TemporaryDirectory(prefix="rndem_value_feedback_target_queries_") as temp_dir:
        temp_root = Path(temp_dir)
        registry = PatternRegistry(temp_root / "Memory" / "pattern_manifest.json")
        target_a = registry.id("state_integrity_preservation")
        target_b = registry.id("state_load_reduced")
        target_soft = registry.id("state_attention_increased")
        unrelated = registry.id("evaluation_avoidance_target")
        expsm_path = temp_root / "Memory" / "ExpSM" / "ExpSM_data.json"
        expsm_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(expsm_path, _demo_store(target_a, target_b, target_soft, unrelated))
        view = ValueFeedbackMemoryView(registry, expsm_path)

        helpful_a = view.find_helpful_for_target([target_a])
        risky_a = view.find_risky_for_target([target_a])
        helpful_unrelated = view.find_helpful_for_target([unrelated])
        exact_soft_absent = view.find_helpful_for_target([target_a], limit=10)
        soft_matches = view.find_helpful_for_target(
            [target_a],
            target_kind="positive_target",
            target_roles=["needed_target", "safety_target"],
            limit=10,
        )
        mixed_any = view.find_by_target_pattern(target_a, direction="mixed")

        exact_positive_ok = (
            bool(helpful_a)
            and helpful_a[0].experience_id == "exp_positive_a"
            and helpful_a[0].match_score > 0.0
            and helpful_a[0].value_direction == "positive"
        )
        exact_negative_ok = (
            bool(risky_a)
            and risky_a[0].experience_id == "exp_negative_a"
            and risky_a[0].match_score > 0.0
            and risky_a[0].value_direction == "negative"
        )
        unrelated_ok = all(match.experience_id not in {"exp_positive_a", "exp_negative_a", "exp_mixed_a"} for match in helpful_unrelated)
        exact_only_no_soft = all(match.experience_id != "exp_soft_kind_role" for match in exact_soft_absent)
        soft_ok = any(
            match.experience_id == "exp_soft_kind_role"
            and match.match_score > 0.0
            and not match.matched_target_patterns
            and match.matched_target_kinds
            and match.matched_target_roles
            for match in soft_matches
        )
        mixed_sort_ok = (
            bool(helpful_a)
            and bool(risky_a)
            and bool(mixed_any)
            and helpful_a[0].experience_id == "exp_positive_a"
            and risky_a[0].experience_id == "exp_negative_a"
            and helpful_a[0].match_score > next(match.match_score for match in mixed_any if match.experience_id == "exp_mixed_a")
            and risky_a[0].match_score > next(match.match_score for match in mixed_any if match.experience_id == "exp_mixed_a")
        )
        snapshot = view.snapshot()
        snapshot_index_ok = target_a in snapshot.get("target_index", {})
    real_unchanged = real_hash_before == _sha256(REAL_EXPSM)
    passed = (
        exact_positive_ok
        and exact_negative_ok
        and unrelated_ok
        and exact_only_no_soft
        and soft_ok
        and mixed_sort_ok
        and snapshot_index_ok
        and real_unchanged
    )
    print("Value feedback memory target query verification:")
    print(f"  exact positive target: {'yes' if exact_positive_ok else 'no'}")
    print(f"  exact negative/risky target: {'yes' if exact_negative_ok else 'no'}")
    print(f"  unrelated target no false match: {'yes' if unrelated_ok else 'no'}")
    print(f"  role/kind soft match: {'yes' if soft_ok and exact_only_no_soft else 'no'}")
    print(f"  mixed below strong helpful/risky: {'yes' if mixed_sort_ok else 'no'}")
    print(f"  snapshot target index: {'yes' if snapshot_index_ok else 'no'}")
    print(f"  real ExpSM unchanged: {'yes' if real_unchanged else 'no'}")
    if helpful_a:
        print(f"  helpful example: {helpful_a[0].experience_id} score={helpful_a[0].match_score}")
    if risky_a:
        print(f"  risky example: {risky_a[0].experience_id} score={risky_a[0].match_score}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _demo_store(target_a: str, target_b: str, target_soft: str, unrelated: str) -> dict[str, Any]:
    return {
        "experience": {
            "exp_positive_a": _record(
                positive_count=3,
                negative_count=0,
                mixed_count=0,
                positive_total=2.55,
                negative_total=0.0,
                mixed_total=0.0,
                target_pattern=target_a,
                direction="positive",
                kind="positive_target",
                roles=["needed_target", "safety_target"],
            ),
            "exp_negative_a": _record(
                positive_count=0,
                negative_count=3,
                mixed_count=0,
                positive_total=0.0,
                negative_total=2.4,
                mixed_total=0.0,
                target_pattern=target_a,
                direction="negative",
                kind="positive_target",
                roles=["needed_target", "safety_target"],
            ),
            "exp_mixed_a": _record(
                positive_count=0,
                negative_count=0,
                mixed_count=2,
                positive_total=0.0,
                negative_total=0.0,
                mixed_total=0.8,
                target_pattern=target_a,
                direction="mixed_or_unclear",
                kind="positive_target",
                roles=["needed_target"],
            ),
            "exp_positive_unrelated": _record(
                positive_count=3,
                negative_count=0,
                mixed_count=0,
                positive_total=2.4,
                negative_total=0.0,
                mixed_total=0.0,
                target_pattern=target_b,
                direction="positive",
                kind="positive_target",
                roles=["needed_target"],
            ),
            "exp_soft_kind_role": _record(
                positive_count=2,
                negative_count=0,
                mixed_count=0,
                positive_total=1.4,
                negative_total=0.0,
                mixed_total=0.0,
                target_pattern=target_soft,
                direction="positive",
                kind="positive_target",
                roles=["needed_target", "safety_target"],
            ),
            "exp_unrelated": _record(
                positive_count=2,
                negative_count=0,
                mixed_count=0,
                positive_total=1.6,
                negative_total=0.0,
                mixed_total=0.0,
                target_pattern=unrelated,
                direction="positive",
                kind="avoidance_target",
                roles=["avoidance_target"],
            ),
        },
        "reflexes": {},
    }


def _record(
    *,
    positive_count: int,
    negative_count: int,
    mixed_count: int,
    positive_total: float,
    negative_total: float,
    mixed_total: float,
    target_pattern: str,
    direction: str,
    kind: str,
    roles: list[str],
) -> dict[str, Any]:
    return {
        "if": ["pat_if"],
        "then": ["pat_then"],
        "result": ["pat_result"],
        "recommendation": ["pat_recommend"],
        "value_feedback": {
            "positive_count": positive_count,
            "negative_count": negative_count,
            "mixed_count": mixed_count,
            "inconclusive_count": 0,
            "positive_strength_total": positive_total,
            "negative_strength_total": negative_total,
            "mixed_strength_total": mixed_total,
            "last_review_id": f"review_{direction}_{target_pattern}",
            "last_updated_tick": 5,
            "target_links": [
                {
                    "target_pattern_id": target_pattern,
                    "target_kind": kind,
                    "target_role_names": roles,
                    "value_direction": direction,
                    "candidate_strength": max(positive_total, negative_total, mixed_total) / max(positive_count + negative_count + mixed_count, 1),
                    "evidence_strength": 0.75,
                    "satisfaction_status": "satisfied" if direction == "positive" else "worsened",
                    "recommended_future_operation": "increase_value_confidence"
                    if direction == "positive"
                    else "increase_avoidance_warning",
                }
            ],
        },
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
