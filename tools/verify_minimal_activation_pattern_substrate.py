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
    NFPFrame,
    NFPFrameSimilarity,
    NFPReactivation,
    NFPSequence,
    NFPWindow,
    NFPWindowSimilarity,
    PatternModality,
    PatternMoment,
    PatternOrigin,
    PatternTopology,
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
    "create_visual_external_nfp_frame",
    "create_audio_external_nfp_frame",
    "create_internal_frame",
    "create_action_frame",
    "nfp_frame_validation",
    "nfp_window_accepts_ordered_same_modality_compatible_frames",
    "nfp_window_rejects_mixed_modalities",
    "nfp_window_rejects_incompatible_topology",
    "nfp_window_rejects_duplicate_frame_ids",
    "nfp_window_rejects_unordered_ticks",
    "nfp_window_exposes_modality_topology_start_end_length",
    "nfp_sequence_accepts_ordered_compatible_windows",
    "nfp_sequence_rejects_mixed_modality",
    "nfp_sequence_rejects_incompatible_topology",
    "nfp_sequence_exposes_start_end_window_count",
    "frame_similarity_identical_1",
    "frame_similarity_differing_activation_in_range",
    "cross_modal_frame_comparison_non_comparable",
    "topology_mismatch_non_comparable",
    "identical_windows_1",
    "different_compatible_windows_deterministic_score",
    "different_window_lengths_non_comparable",
    "reactivation_creates_new_nfp_frame",
    "reactivation_preserves_modality_topology_values",
    "reactivation_origin_internal_reactivation",
    "external_and_replayed_identical_values_epistemically_distinct",
    "debug_name_does_not_affect_similarity",
    "no_akbsm_writes",
    "no_expsm_writes",
    "no_contextmemory_writes",
    "no_run_tick_integration",
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
        "NFPFrame exists": _nfp_frame_exists,
        "NFPWindow exists": _nfp_window_exists,
        "NFPSequence exists": _nfp_sequence_exists,
        "Frame/Window/Sequence hierarchy is explicit": _hierarchy_is_explicit,
        "Window is not merely an alias for Sequence": _window_not_sequence_alias,
        "PatternTopology validation works": _topology_validation,
        "NFPFrame validation works": _frame_validation,
        "objects are immutable": _immutability,
        "single frame is single-modality": _single_frame_is_single_modality,
        "PatternMoment separates multimodal same-tick grouping": _pattern_moment_is_not_nfp_frame,
        "NFPWindow invariants work": _window_invariants,
        "NFPSequence invariants work": _sequence_invariants,
        "frame similarity works": _frame_similarity,
        "window similarity works": _window_similarity,
        "raw cross-modal similarity rejected": _cross_modal_similarity_rejected,
        "reactivation provenance/origin works": _reactivation,
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


def _nfp_frame_exists() -> tuple[bool, str]:
    return isinstance(_frame("frame", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.5,), 1), NFPFrame), "NFPFrame"


def _nfp_window_exists() -> tuple[bool, str]:
    window = _window("window", 1, (0.1, 0.2))
    return isinstance(window, NFPWindow), "NFPWindow"


def _nfp_sequence_exists() -> tuple[bool, str]:
    sequence = NFPSequence(sequence_id="sequence", windows=(_window("window", 1, (0.1, 0.2)),))
    return isinstance(sequence, NFPSequence), "NFPSequence"


def _hierarchy_is_explicit() -> tuple[bool, str]:
    frame = _frame("frame", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.5,), 1)
    window = NFPWindow(window_id="window", frames=(frame,))
    sequence = NFPSequence(sequence_id="sequence", windows=(window,))
    checks = [
        isinstance(frame, NFPFrame),
        isinstance(window, NFPWindow),
        isinstance(sequence, NFPSequence),
        window.frames == (frame,),
        sequence.windows == (window,),
    ]
    return all(checks), "NFPFrame -> NFPWindow -> NFPSequence"


def _window_not_sequence_alias() -> tuple[bool, str]:
    return NFPWindow is not NFPSequence and NFPWindow.__name__ != NFPSequence.__name__, f"{NFPWindow.__name__}/{NFPSequence.__name__}"


def _topology_validation() -> tuple[bool, str]:
    topology = PatternTopology((4, 4))
    checks = [
        topology.size == 16,
        _raises(lambda: PatternTopology(()), ValueError),
        _raises(lambda: PatternTopology((0,)), ValueError),
        _raises(lambda: PatternTopology((-1, 2)), ValueError),
    ]
    return all(checks), f"size={topology.size}"


def _frame_validation() -> tuple[bool, str]:
    topology = PatternTopology((2,))
    frame = NFPFrame(
        frame_id="visual-1",
        modality=PatternModality.VISUAL,
        origin=PatternOrigin.EXTERNAL_SENSORY,
        topology=topology,
        values=(0.0, 1.0),
        active_tick=1,
        debug_name="dog",
    )
    checks = [
        frame.frame_id == "visual-1",
        _raises(lambda: NFPFrame("", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.0, 1.0), 1), ValueError),
        _raises(lambda: NFPFrame("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.0,), 1), ValueError),
        _raises(lambda: NFPFrame("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (-0.1, 0.0), 1), ValueError),
        _raises(lambda: NFPFrame("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (math.nan, 0.0), 1), ValueError),
        _raises(lambda: NFPFrame("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (math.inf, 0.0), 1), ValueError),
        _raises(lambda: NFPFrame("bad", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.0, 1.0), -1), ValueError),
    ]
    return all(checks), "validated range/length/tick"


def _immutability() -> tuple[bool, str]:
    frame = _frame("immutable", PatternModality.INTERNAL, PatternOrigin.INTERNAL_STATE, (0.5,), 2)
    window = NFPWindow(window_id="window-immutable", frames=(frame,))
    sequence = NFPSequence(sequence_id="sequence-immutable", windows=(window,))
    checks = [
        _raises(lambda: setattr(frame, "active_tick", 3), FrozenInstanceError),
        _raises(lambda: setattr(window, "window_id", "other"), FrozenInstanceError),
        _raises(lambda: setattr(sequence, "sequence_id", "other"), FrozenInstanceError),
    ]
    return all(checks), "frozen dataclasses"


def _single_frame_is_single_modality() -> tuple[bool, str]:
    fields = set(NFPFrame.__dataclass_fields__)
    checks = [
        "modality" in fields,
        "frames" not in fields,
        "windows" not in fields,
        "values" in fields,
    ]
    return all(checks), str(sorted(fields))


def _pattern_moment_is_not_nfp_frame() -> tuple[bool, str]:
    visual = _frame("visual", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.1,), 4)
    audio = _frame("audio", PatternModality.AUDIO, PatternOrigin.EXTERNAL_SENSORY, (0.2,), 4)
    moment = PatternMoment(active_tick=4, frames=(visual, audio))
    checks = [
        isinstance(moment, PatternMoment),
        not isinstance(moment, NFPFrame),
        len(moment.frames) == 2,
        _raises(lambda: PatternMoment(active_tick=5, frames=(visual,)), ValueError),
    ]
    return all(checks), "PatternMoment groups same-tick frames"


def _window_invariants() -> tuple[bool, str]:
    frames = (
        _frame("w1", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.1, 0.2), 10),
        _frame("w2", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.2, 0.3), 11),
        _frame("w3", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.3, 0.4), 12),
    )
    window = NFPWindow(window_id="window", frames=frames)
    mixed = _frame("audio", PatternModality.AUDIO, PatternOrigin.EXTERNAL_SENSORY, (0.2, 0.3), 11)
    topology_mismatch = NFPFrame("topology", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, PatternTopology((1,)), (0.2,), 11)
    duplicate = _frame("w1", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.2, 0.3), 11)
    unordered = (
        _frame("late", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.1, 0.2), 12),
        _frame("early", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.2, 0.3), 11),
    )
    checks = [
        window.modality == PatternModality.VISUAL,
        window.topology == frames[0].topology,
        window.start_tick == 10,
        window.end_tick == 12,
        window.length == 3,
        _raises(lambda: NFPWindow("", frames), ValueError),
        _raises(lambda: NFPWindow("empty", ()), ValueError),
        _raises(lambda: NFPWindow("mixed", (frames[0], mixed)), ValueError),
        _raises(lambda: NFPWindow("topology", (frames[0], topology_mismatch)), ValueError),
        _raises(lambda: NFPWindow("duplicate", (frames[0], duplicate)), ValueError),
        _raises(lambda: NFPWindow("unordered", unordered), ValueError),
    ]
    return all(checks), f"{window.start_tick}->{window.end_tick}, length={window.length}"


def _sequence_invariants() -> tuple[bool, str]:
    window_1 = _window("window-1", 1, (0.1, 0.2))
    window_2 = _window("window-2", 3, (0.2, 0.3))
    sequence = NFPSequence(sequence_id="sequence", windows=(window_1, window_2))
    audio_window = _window("audio-window", 5, (0.1, 0.2), modality=PatternModality.AUDIO)
    topology_window = NFPWindow(
        window_id="topology-window",
        frames=(
            NFPFrame("topology-1", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, PatternTopology((1,)), (0.1,), 5),
        ),
    )
    checks = [
        sequence.modality == PatternModality.VISUAL,
        sequence.topology == window_1.topology,
        sequence.start_tick == 1,
        sequence.end_tick == 3,
        sequence.window_count == 2,
        _raises(lambda: NFPSequence("", (window_1,)), ValueError),
        _raises(lambda: NFPSequence("empty", ()), ValueError),
        _raises(lambda: NFPSequence("mixed", (window_1, audio_window)), ValueError),
        _raises(lambda: NFPSequence("topology", (window_1, topology_window)), ValueError),
        _raises(lambda: NFPSequence("unordered", (window_2, window_1)), ValueError),
    ]
    return all(checks), f"{sequence.start_tick}->{sequence.end_tick}, windows={sequence.window_count}"


def _frame_similarity() -> tuple[bool, str]:
    left = _frame("left", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.0, 1.0), 8)
    same = _frame("same", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.0, 1.0), 9)
    different = _frame("different", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (1.0, 0.0), 9)
    result_1 = NFPFrameSimilarity.compare(left, same)
    result_2 = NFPFrameSimilarity.compare(left, same)
    result_3 = NFPFrameSimilarity.compare(left, different)
    checks = [
        result_1 == result_2,
        result_1.comparable and result_1.score == 1.0 and result_1.reason is None,
        result_3.comparable and result_3.score is not None and 0.0 <= result_3.score <= 1.0,
    ]
    return all(checks), f"identical={result_1.score}, different={result_3.score}"


def _window_similarity() -> tuple[bool, str]:
    left = _window("left-window", 10, (0.0, 1.0), (0.2, 0.8))
    same = _window("same-window", 20, (0.0, 1.0), (0.2, 0.8))
    different = _window("different-window", 20, (1.0, 0.0), (0.2, 0.6))
    shorter = _window("shorter-window", 20, (0.0, 1.0))
    result_1 = NFPWindowSimilarity.compare(left, same)
    result_2 = NFPWindowSimilarity.compare(left, different)
    result_3 = NFPWindowSimilarity.compare(left, different)
    length_mismatch = NFPWindowSimilarity.compare(left, shorter)
    checks = [
        result_1.comparable and result_1.score == 1.0,
        result_2 == result_3,
        result_2.comparable and result_2.score is not None and 0.0 <= result_2.score <= 1.0,
        length_mismatch.comparable is False,
        length_mismatch.reason == "different_frame_count",
    ]
    return all(checks), f"identical={result_1.score}, different={result_2.score}"


def _cross_modal_similarity_rejected() -> tuple[bool, str]:
    visual = _frame("visual", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.0, 1.0), 1)
    audio = _frame("audio", PatternModality.AUDIO, PatternOrigin.EXTERNAL_SENSORY, (0.0, 1.0), 1)
    other_topology = NFPFrame("topology", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, PatternTopology((1,)), (0.0,), 1)
    cross_modal = NFPFrameSimilarity.compare(visual, audio)
    cross_topology = NFPFrameSimilarity.compare(visual, other_topology)
    checks = [
        cross_modal.comparable is False and cross_modal.score is None and cross_modal.reason == "different_modality",
        cross_topology.comparable is False and cross_topology.score is None and cross_topology.reason == "different_topology",
    ]
    return all(checks), f"{cross_modal.reason}/{cross_topology.reason}"


def _reactivation() -> tuple[bool, str]:
    source = _frame("source", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, (0.2, 0.8), 10)
    replay = NFPReactivation.reactivate_frame(source, new_frame_id="replay", active_tick=12, debug_name="remembered")
    checks = [
        isinstance(replay, NFPFrame),
        replay.frame_id == "replay",
        replay.frame_id != source.frame_id,
        replay.active_tick == 12,
        replay.active_tick != source.active_tick,
        replay.modality == source.modality,
        replay.topology == source.topology,
        replay.values == source.values,
        replay.origin == PatternOrigin.INTERNAL_REACTIVATION,
        replay.provenance_ref == source.frame_id,
        source.origin == PatternOrigin.EXTERNAL_SENSORY,
        replay.origin != source.origin,
    ]
    return all(checks), f"{source.origin.value}->{replay.origin.value}"


def _debug_names_non_semantic() -> tuple[bool, str]:
    topology = PatternTopology((2,))
    left = NFPFrame("left", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.25, 0.75), 1, debug_name="dog")
    right = NFPFrame("right", PatternModality.VISUAL, PatternOrigin.EXTERNAL_SENSORY, topology, (0.25, 0.75), 1, debug_name="cat")
    similarity = NFPFrameSimilarity.compare(left, right)
    checks = [
        left.frame_id != right.frame_id,
        left.debug_name != right.debug_name,
        similarity.comparable,
        similarity.score == 1.0,
    ]
    return all(checks), "debug_name ignored by identity/similarity"


def _action_has_no_consequence_field() -> tuple[bool, str]:
    action = _frame("action", PatternModality.ACTION, PatternOrigin.ACTION_GENERATED, (0.1, 0.9), 7)
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
    pattern_tokens = ("clc.patterns", "NFPFrame", "NFPWindow", "NFPSequence", "ActivationPattern")
    return not any(token in text for token in pattern_tokens), "clc_runtime.py untouched by patterns"


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
    hierarchy = section.get("hierarchy") == ["NFPFrame", "NFPWindow", "NFPSequence"]
    boundaries = [
        hierarchy,
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


def _frame(
    frame_id: str,
    modality: PatternModality,
    origin: PatternOrigin,
    values: tuple[float, ...],
    active_tick: int,
) -> NFPFrame:
    return NFPFrame(
        frame_id=frame_id,
        modality=modality,
        origin=origin,
        topology=PatternTopology((len(values),)),
        values=values,
        active_tick=active_tick,
    )


def _window(
    window_id: str,
    start_tick: int,
    *values_by_frame: tuple[float, ...],
    modality: PatternModality = PatternModality.VISUAL,
) -> NFPWindow:
    frames = tuple(
        _frame(f"{window_id}-frame-{index}", modality, PatternOrigin.EXTERNAL_SENSORY, values, start_tick + index)
        for index, values in enumerate(values_by_frame)
    )
    return NFPWindow(window_id=window_id, frames=frames)


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
