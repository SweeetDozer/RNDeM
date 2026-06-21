from __future__ import annotations

import shutil
from pathlib import Path
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.action.action_candidate_field import ActionCandidateField  # noqa: E402
from clc.action.action_proposer import ActionProposer  # noqa: E402
from clc.context.context_memory import ContextMemory  # noqa: E402
from clc.core.ids import IdGenerator  # noqa: E402
from clc.core.markers import OperationMarker  # noqa: E402
from clc.core.operations import ContextOperation  # noqa: E402
from clc.core.pattern_registry import PatternRegistry  # noqa: E402
from clc.field.active_context_field import ActiveContextField  # noqa: E402
from clc.system.system_state import SystemState  # noqa: E402


MANIFEST_PATH = PROJECT_ROOT / "Memory" / "pattern_manifest.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="action_proposer_semantics_") as temp_dir:
        temp_manifest = Path(temp_dir) / "pattern_manifest.json"
        shutil.copy2(MANIFEST_PATH, temp_manifest)
        registry = PatternRegistry(temp_manifest)
        action_pattern = registry.id("action_preserve_integrity")
        non_action_pattern = registry.register_if_missing("probe_candidate_without_action_semantics")
        proposer = ActionProposer(registry)

        action_candidate_ok = _produces_candidate(registry, proposer, action_pattern)
        non_action_candidate_ok = not _produces_candidate(registry, proposer, non_action_pattern)
        no_debug_fallback_ok = not proposer._is_action_pattern(non_action_pattern)
        unknown_safe_ok = not proposer._is_action_pattern("missing_pattern_id")
        registry_api_ok = registry.is_action(action_pattern) and not registry.is_action(non_action_pattern)

    checks = {
        "action_tag_produces_candidate": action_candidate_ok,
        "non_action_tag_does_not_create_candidate": non_action_candidate_ok,
        "no_debug_name_fallback_for_non_action": no_debug_fallback_ok,
        "unknown_pattern_not_action": unknown_safe_ok,
        "registry_action_api_used": registry_api_ok,
    }
    print("ActionProposer semantic tag verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if all(checks.values()) else 'FAIL'}")
    return 0 if all(checks.values()) else 1


def _produces_candidate(registry: PatternRegistry, proposer: ActionProposer, pattern_id: str) -> bool:
    id_gen = IdGenerator()
    memory = ContextMemory(id_gen, registry)
    candidate_field = ActionCandidateField(id_gen)
    memory.add_event(
        ContextOperation(
            id_gen.next("op"),
            OperationMarker.EXPSM_MECHANISM_SEARCH,
            1,
            "verify_action_proposer_semantic_tags",
            None,
            {
                "mechanism_search_id": id_gen.next("expsm_mechanism_search"),
                "source_target_observation_id": "target_verify",
                "target_pattern_id": registry.id("outcome_confirmed"),
                "target_kind": "positive_target",
                "target_role_names": ["needed_target"],
                "target_score": 0.8,
                "mechanisms": [
                    {
                        "experience_id": "semantic_verify_experience",
                        "then_patterns": [pattern_id],
                        "mechanism_score": 0.8,
                        "value_adjusted_score": 0.8,
                        "viability": 0.9,
                        "effective_confidence": 0.8,
                        "repeatability": 0.7,
                        "mechanism_purpose": "obtain_target",
                    }
                ],
            },
        )
    )
    proposer.propose(1, memory, ActiveContextField(), candidate_field, SystemState())
    candidates = candidate_field.get_top_candidates()
    return any(
        candidate.pattern_id == pattern_id
        and candidate.source_metadata.get("source") == "expsm_mechanism_search"
        for candidate in candidates
    )


if __name__ == "__main__":
    raise SystemExit(main())
