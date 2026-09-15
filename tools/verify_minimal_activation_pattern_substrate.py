from __future__ import annotations

import ast
import hashlib
import json
import math
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.patterns import (  # noqa: E402
    ActivationPattern,
    PatternFrame,
    PatternModality,
    PatternOrigin,
    PatternReactivation,
    PatternSimilarity,
    PatternTopology,
    PatternTrace,
)


PATTERN_ROOT = PROJECT_ROOT / "clc" / "patterns"
RUNTIME_ROOT = PROJECT_ROOT / "clc" / "runtime"
SCENARIO_PATH = PROJECT_ROOT / "scenarios" / "minimal_activation_pattern_substrate.json"

EXPECTED_MEMORY_HASHES = {
    PROJECT_ROOT / "Memory" / "ExpSM" / "ExpSM_data.json": "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e",
    PROJECT_ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json": "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd",
}

EXPECTED_MODALITIES = {
    "visual",
    "audio",
    "internal",
    "pain_damage",
    "reward_success",
    "action",
}
EXPECTED_ORIGINS = {
    "external_sensory",
    "internal_state",
    "internal_reactivation",
    "action_generated",
}
EXPECTED_SCENARIO_CASES = {
    "create_external_visual_pattern",
    "create_external_audio_pattern",
    "create_internal_state_pattern",
    "create_pain_damage_pattern",
    "create_reward_success_pattern",
    "create_action_pattern",
    "reject_empty_topology",
    "reject_zero_negative_topology_dimensions",
    "reject_values_length_topology_mismatch",
    "reject_values_outside_range",
    "reject_nan_inf_values",
    "frame_contains_visual_audio_internal_same_tick",
    "frame_rejects_wrong_tick_pattern",
    "frame_rejects_duplicate_occurrence_id",
    "trace_preserves_tick_ordering",
    "trace_exposes_start_tick_end_tick",
    "identical_same_modality_topology_similarity_1",
    "different_same_modality_topology_similarity_in_range",
    "different_topology_non_comparable",
    "different_modality_non_comparable",
    "reactivation_preserves_modality",
    "reactivation_preserves_topology",
    "reactivation_preserves_values",
    "reactivation_creates_new_pattern_id",
    "reactivation_changes_active_tick",
    "reactivation_sets_internal_reactivation",
    "reactivation_records_source_provenance",
    "source_occurrence_remains_unchanged",
    "external_and_identical_replay_have_different_origin",
    "debug_name_does_not_affect_similarity",
    "debug_name_does_not_define_identity",
    "action_pattern_contains_no_consequence_truth",
    "no_akbsm_write_occurs",
    "no_expsm_write_occurs",
    "no_contextmemory_placement_occurs",
}
FORBIDDEN_IMPORTS = {
    "clc.runtime",
    "clc.action",
    "clc.evaluation",
    "clc.context",
    "clc.akbsm",
    "clc.expsm",
    "clc.consolidation",
    "Memory",
}
FORBIDDEN_CODE_TOKENS = {
    "CLCRuntime",
    "DecisionSelector",
    "ActionScoring",
    "ActionProposer",
    "ModeActionGuard",
    "PolicyPressureReview",
    "ContextMemoryManager",
    "AKBSM",
    "ExpSM",
    "semantic_core.json",
    "technical_feedback_patterns.json",
}


def main() -> int:
    checks = {
        "PatternModality values exist": _pattern_modality_values,
        "PatternOrigin values exist": _pattern_origin_values,
        "PatternTopology validation works": _topology_validation,
        "ActivationPattern validation works": _activation_validation,
        "objects are immutable": _immutability,
        "PatternFrame invariants work": _frame_invariants,
        "PatternTrace ordering works": _trace_ordering,
        "similarity algorithm is deterministic": _similarity,
        "reactivation preserves provenance and origin boundary": _reactivation,
        "debug names do not affect identity or similarity": _debug_names_non_semantic,
        "ACTION carries no consequence field": _action_has_no_consequence_field,
        "package imports stay isolated": _package_imports_stay_isolated,
        "runtime does not import clc.patterns": _runtime_does_not_import_patterns,
        "no run_tick integration exists": _no_run_tick_integration,
        "no persistence or memory write references": _no_persistence_or_memory_writes,
        "scenario fixture has expected coverage": _scenario_fixture,
        "real Memory hashes unchanged": _memory_hashes_unchanged,
    }

    passed = True
    for label, check in checks.items():
        try:
            ok, detail = check()
        except Exception as exc:  # noqa: BLE001 - verifier reports compact failures.
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        print(f"{'PASS' if ok else 'FAIL'}: {label}" + (f" ({detail})" if detail else ""))
        passed = passed and ok
    return 0 if passed else 1


def _pattern_modality_values() -> tuple[bool, str]:
    values = {item.value for item in PatternModality}
    return values == EXPECTED_MODALITIES, str(sorted(values))


def _pattern_origin_values() -> tuple[bool, str]:
    values = {item.value for item in PatternOrigin}
    return values == EXPECTED_ORIGINS, str(sorted(values))


def _topology_validation() -> tuple[bool, str]:
    topology = PatternTopology((4, 4))
    checks = [
        topology.size == 16,
        _raises(lambda: PatternTopology(()), ValueError),
        _raises(lambda: PatternTopology((0,)), ValueError),
        _raises(lambda: PatternTopology((-1, 2)), ValueError),
    ]
    return all(checks), f"size={topology.size}"


def _activation_validation() -> tuple[bool, str]:
    topology = PatternTopology((2,))
    pattern = ActivationPattern(
        pattern_id="visual-1",
        modality=PatternModality.VISUAL,
        origin=PatternOrigin.EXTERNAL_SENSORY,
        topology=topology,
        values=(0.0, 1.0),
        active_tick=1,
        debug_name="dog",
    )
    checks = [
        pattern.pattern_id == "visual-1",
        _raises(lambda: ActivationPattern("", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.0, 1.0), 1), ValueError),
        _raises(lambda: ActivationPattern("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.0,), 1), ValueError),
        _raises(lambda: ActivationPattern("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (-0.1, 0.0), 1), ValueError),
        _raises(lambda: ActivationPattern("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (math.nan, 0.0), 1), ValueError),
        _raises(lambda: ActivationPattern("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (math.inf, 0.0), 1), ValueError),
        _raises(lambda: ActivationPattern("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.0, 1.0), -1), ValueError),
    ]
    return all(checks), "validated range/length/tick"


def _immutability() -> tuple[bool, str]:
    pattern = _pattern("immutable", PatternModality.INTERNAL, PatternOrigin.INTERNAL_STATE, (0.5,), 2)
    frame = PatternFrame(active_tick=2, patterns=(pattern,))
    trace = PatternTrace(trace_id="trace-immutable", frames=(frame,))
    checks = [
        _raises(lambda: setattr(pattern, "active_tick", 3), FrozenInstanceError),
        _raises(lambda: setattr(frame, "active_tick", 3), FrozenInstanceError),
        _raises(lambda: setattr(trace, "trace_id", "other"), FrozenInstanceError),
    ]
    return all(checks), "frozen dataclasses"


def _frame_invariants() -> tuple[bool, str]:
    visual = _pattern("visual", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.1, 0.2), 4)
    audio = _pattern("audio", PatternModality.AUDIO, PatternOrigin.EXTERNAL_SENSORY, (0.3, 0.4), 4)
    internal = _pattern("internal", PatternModality.INTERNAL, PatternOrigin.INTERNAL_STATE, (0.5, 0.6), 4)
    frame = PatternFrame(active_tick=4, patterns=(visual, audio, internal))
    wrong_tick = _pattern("wrong", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.1, 0.2), 5)
    duplicate_id = _pattern("visual", PatternModality.AUDIO, PatternOrigin.EXTERNAL_SENSORY, (0.3, 0.4), 4)
    checks = [
        len(frame.patterns) == 3,
        _raises(lambda: PatternFrame(active_tick=4, patterns=(wrong_tick,)), ValueError),
        _raises(lambda: PatternFrame(active_tick=4, patterns=(visual, duplicate_id)), ValueError),
    ]
    return all(checks), "multi-modality same tick"


def _trace_ordering() -> tuple[bool, str]:
    frame_1 = PatternFrame(active_tick=1, patterns=(_pattern("p1", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.1,), 1),))
    frame_2 = PatternFrame(active_tick=3, patterns=(_pattern("p2", PatternModality.AUDIO, PatternOrigin.EXTERNAL_SENSORY, (0.2,), 3),))
    trace = PatternTrace(trace_id="trace-1", frames=(frame_1, frame_2))
    duplicate_tick = PatternFrame(active_tick=3, patterns=(_pattern("p3", PatternModality.INTERNAL, PatternOrigin.INTERNAL_STATE, (0.3,), 3),))
    checks = [
        trace.start_tick == 1,
        trace.end_tick == 3,
        _raises(lambda: PatternTrace(trace_id="trace-bad", frames=(frame_2, frame_1)), ValueError),
        _raises(lambda: PatternTrace(trace_id="trace-dup", frames=(frame_2, duplicate_tick)), ValueError),
    ]
    return all(checks), f"{trace.start_tick}->{trace.end_tick}"


def _similarity() -> tuple[bool, str]:
    left = _pattern("left", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.0, 1.0), 8)
    same = _pattern("same", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.0, 1.0), 9)
    different = _pattern("different", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (1.0, 0.0), 9)
    audio = _pattern("audio", PatternModality.AUDIO, PatternOrigin.EXTERNAL_SENSORY, (0.0, 1.0), 9)
    other_topology = ActivationPattern("topology", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, PatternTopology((1,)), (0.0,), 9)
    result_1 = PatternSimilarity.compare(left, same)
    result_2 = PatternSimilarity.compare(left, same)
    result_3 = PatternSimilarity.compare(left, different)
    cross_modal = PatternSimilarity.compare(left, audio)
    cross_topology = PatternSimilarity.compare(left, other_topology)
    checks = [
        result_1 == result_2,
        result_1.comparable and result_1.score == 1.0 and result_1.reason is None,
        result_3.comparable and result_3.score is not None and 0.0 <= result_3.score <= 1.0,
        cross_modal == PatternSimilarity(False, None, "different_modality"),
        cross_topology == PatternSimilarity(False, None, "different_topology"),
    ]
    return all(checks), f"identical={result_1.score}, different={result_3.score}"


def _reactivation() -> tuple[bool, str]:
    source = _pattern("source", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.2, 0.8), 10)
    replay = PatternReactivation.reactivate(source, new_pattern_id="replay", active_tick=12, debug_name="remembered")
    checks = [
        replay.pattern_id == "replay",
        replay.pattern_id != source.pattern_id,
        replay.active_tick == 12,
        replay.active_tick != source.active_tick,
        replay.modality == source.modality,
        replay.topology == source.topology,
        replay.values == source.values,
        replay.origin == PatternOrigin.INTERNAL_REACTIVATION,
        replay.provenance_ref == source.pattern_id,
        source.origin == PatternOrigin.EXTERNAL_SENSORY,
        replay.origin != source.origin,
    ]
    return all(checks), f"{source.origin.value}->{replay.origin.value}"


def _debug_names_non_semantic() -> tuple[bool, str]:
    topology = PatternTopology((2,))
    left = ActivationPattern("left", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.25, 0.75), 1, debug_name="dog")
    right = ActivationPattern("right", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.25, 0.75), 1, debug_name="cat")
    similarity = PatternSimilarity.compare(left, right)
    checks = [
        left.pattern_id != right.pattern_id,
        left.debug_name != right.debug_name,
        similarity.comparable,
        similarity.score == 1.0,
    ]
    return all(checks), "debug_name ignored by identity/similarity"


def _action_has_no_consequence_field() -> tuple[bool, str]:
    action = _pattern("action", PatternModality.ACTION, PatternOrigin.ACTION_GENERATED, (0.1, 0.9), 7)
    forbidden_fields = {"success", "failure", "consequence", "reward", "world_result"}
    actual_fields = set(action.__dataclass_fields__)
    return not (actual_fields & forbidden_fields), str(sorted(actual_fields))


def _package_imports_stay_isolated() -> tuple[bool, str]:
    offenders: list[str] = []
    for path in sorted(PATTERN_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden_import(alias.name):
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _is_forbidden_import(module):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")
    return not offenders, "; ".join(offenders)


def _runtime_does_not_import_patterns() -> tuple[bool, str]:
    offenders = _files_containing(RUNTIME_ROOT, "clc.patterns")
    return not offenders, _format_paths(offenders)


def _no_run_tick_integration() -> tuple[bool, str]:
    runtime_path = RUNTIME_ROOT / "clc_runtime.py"
    text = runtime_path.read_text(encoding="utf-8")
    return "clc.patterns" not in text and "ActivationPattern" not in text, "clc_runtime.py untouched by patterns"


def _no_persistence_or_memory_writes() -> tuple[bool, str]:
    offenders: list[str] = []
    for path in sorted(PATTERN_ROOT.glob("*.py")):
        text = _code_text_without_docstrings(path)
        for token in FORBIDDEN_CODE_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} references {token}")
        if "open(" in text or ".write(" in text or ".read_text(" in text or ".write_text(" in text:
            offenders.append(f"{path.relative_to(PROJECT_ROOT)} has file IO")
    return not offenders, "; ".join(offenders)


def _scenario_fixture() -> tuple[bool, str]:
    if not SCENARIO_PATH.exists():
        return False, "missing fixture"
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    section = data.get("expect", {}).get("minimal_activation_pattern_substrate", {})
    cases = section.get("cases", {})
    missing = sorted(case for case in EXPECTED_SCENARIO_CASES if cases.get(case) is not True)
    boundaries = [
        section.get("isolated") is True,
        section.get("in_memory_only") is True,
        section.get("runtime_wiring") is False,
        section.get("run_tick_integration") is False,
        section.get("akbsm_writes") is False,
        section.get("expsm_writes") is False,
        section.get("contextmemory_placement") is False,
    ]
    ok = not missing and all(boundaries)
    return ok, f"missing={missing}" if missing else "coverage present"


def _memory_hashes_unchanged() -> tuple[bool, str]:
    mismatches: list[str] = []
    for path, expected_hash in EXPECTED_MEMORY_HASHES.items():
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            mismatches.append(f"{path.relative_to(PROJECT_ROOT)}={actual_hash}")
    return not mismatches, "; ".join(mismatches)


def _pattern(
    pattern_id: str,
    modality: PatternModality,
    origin: PatternOrigin,
    values: tuple[float, ...],
    active_tick: int,
) -> ActivationPattern:
    return ActivationPattern(
        pattern_id=pattern_id,
        modality=modality,
        origin=origin,
        topology=PatternTopology((len(values),)),
        values=values,
        active_tick=active_tick,
    )


def _raises(call: Callable[[], object], expected: type[BaseException]) -> bool:
    try:
        call()
    except expected:
        return True
    return False


def _is_forbidden_import(module_name: str) -> bool:
    return any(module_name == forbidden or module_name.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_IMPORTS)


def _files_containing(root: Path, needle: str) -> list[Path]:
    return [path for path in sorted(root.glob("*.py")) if needle in path.read_text(encoding="utf-8")]


def _format_paths(paths: list[Path]) -> str:
    return ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in paths)


def _code_text_without_docstrings(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                node.body[0] = ast.Pass()
    return ast.unparse(tree)


if __name__ == "__main__":
    raise SystemExit(main())
