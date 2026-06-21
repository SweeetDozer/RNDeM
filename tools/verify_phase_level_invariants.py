from __future__ import annotations

import ast
from contextlib import redirect_stdout
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.core.markers import OperationMarker  # noqa: E402
from clc.runtime.clc_runtime import CLCRuntime  # noqa: E402
from clc.runtime.runtime_phase_map import RUNTIME_PHASE_MAP  # noqa: E402
from tools.verify_run_tick_phase_split_boundaries import DOCUMENTED_APPLY_PENDING_COUNT  # noqa: E402


RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
REAL_MEMORY_ROOT = ROOT / "Memory"

EXPECTED_PHASE_HELPERS = (
    "_phase_00_input_commit",
    "_phase_01_primary_updates",
    "_phase_02_field_activation_and_consolidation_pressure",
    "_phase_03_action_proposal_and_selection",
    "_phase_04_decision_audit_and_effects",
    "_phase_05_mode_consolidation_memory_chain",
    "_phase_06_outcome_evaluation_akbsm_mechanism",
    "_phase_07_value_feedback",
    "_phase_08_neuromodulation_projection",
    "_phase_09_final_field_refresh",
    "_phase_10_runtime_observation_views",
    "_phase_11_debug_output",
)

BEHAVIOR_MODULES = (
    "clc/action/action_proposer.py",
    "clc/action/action_scoring.py",
    "clc/action/decision_selector.py",
    "clc/system/mode_action_guard.py",
    "clc/consolidation/memory_write_review_module.py",
    "clc/consolidation/memory_draft_writer.py",
    "clc/consolidation/draft_commit_gate.py",
    "clc/consolidation/expsm_commit_writer.py",
    "clc/consolidation/expsm_update_writer.py",
    "clc/evaluation/value_feedback_update_writer.py",
    "clc/field/field_updater.py",
    "clc/neuromodulation/neuromodulation_module.py",
)

FORBIDDEN_OBSERVATION_MODULES = {
    "clc.evaluation.decision_cycle_history_view",
    "clc.evaluation.reflection_candidate_builder",
    "clc.evaluation.need_more_evidence_signal",
    "clc.evaluation.reflection_review",
    "clc.evaluation.policy_pressure",
    "clc.evaluation.policy_pressure_review",
}

FORBIDDEN_OBSERVATION_NAMES = {
    "DecisionCycleHistoryView",
    "DecisionCycleHistorySnapshot",
    "ReflectionCandidate",
    "ReflectionCandidateBuilder",
    "NeedMoreEvidenceSignal",
    "NeedMoreEvidenceSignalBuilder",
    "ReflectionReview",
    "ReflectionReviewBuilder",
    "PolicyPressure",
    "PolicyPressureBuilder",
    "PolicyPressureReview",
    "PolicyPressureReviewBuilder",
    "decision_cycle_history_view",
    "reflection_candidate_builder",
    "need_more_evidence_signal",
    "reflection_review",
    "policy_pressure",
    "policy_pressure_review",
}

KEY_VERIFIERS = (
    "tools/verify_policy_pressure_influence_boundary.py",
    "tools/verify_real_input_scenarios.py",
    "tools/verify_scenario_fixtures.py",
)


def main() -> int:
    runtime_tree = ast.parse(RUNTIME_PATH.read_text(encoding="utf-8"), filename=str(RUNTIME_PATH))
    phase_order = _run_tick_phase_order(runtime_tree)
    apply_pending_count = _apply_pending_count()
    helper_apply_pending_count = _helper_apply_pending_count(runtime_tree)
    selector_before_mechanism_source = _selector_before_mechanism_in_source(runtime_tree)
    selector_before_mechanism_map = _selector_before_mechanism_in_phase_map()
    mechanism_next_tick_material = _mechanism_search_after_selection_probe()
    observation_isolated, isolation_findings = _reflection_pressure_isolated()
    marker_36_absent, marker_36_findings = _marker_36_absent_from_implementation()
    key_verifiers_pass = _run_key_verifiers()

    checks = {
        "helper phases present": _helpers_present(),
        "phase order": phase_order == list(EXPECTED_PHASE_HELPERS),
        "apply_pending count": apply_pending_count == DOCUMENTED_APPLY_PENDING_COUNT,
        "apply_pending inside phase helpers": helper_apply_pending_count > 0,
        "DecisionSelector before ExpSMMechanismSearch": (
            selector_before_mechanism_source and selector_before_mechanism_map
        ),
        "mechanism-search candidates are next-tick material": mechanism_next_tick_material,
        "reflection/pressure phase after behavior": _reflection_phase_after_behavior(phase_order),
        "reflection/pressure isolated": observation_isolated,
        "marker 36 absent": marker_36_absent,
        "real-input and scenario fixtures pass": key_verifiers_pass,
    }
    passed = all(checks.values())

    print("Phase-level invariant verification:")
    for label, ok in checks.items():
        if label == "apply_pending count":
            print(f"  {label}: {apply_pending_count} {'PASS' if ok else 'FAIL'}")
        else:
            print(f"  {label}: {'yes' if ok else 'no'}")
    print(f"  helper apply_pending count: {helper_apply_pending_count}")
    if phase_order != list(EXPECTED_PHASE_HELPERS):
        print(f"  observed phase order: {phase_order}")
    for finding in isolation_findings:
        print(f"  isolation finding: {finding}")
    for finding in marker_36_findings:
        print(f"  marker 36 finding: {finding}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _helpers_present() -> bool:
    return all(hasattr(CLCRuntime, helper) for helper in EXPECTED_PHASE_HELPERS)


def _run_tick_phase_order(tree: ast.AST) -> list[str]:
    run_tick = _method_def(tree, "_run_tick")
    if run_tick is None:
        return []
    phase_calls: list[str] = []
    for node in ast.walk(run_tick):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr.startswith("_phase_"):
            phase_calls.append(func.attr)
    return phase_calls


def _apply_pending_count() -> int:
    return RUNTIME_PATH.read_text(encoding="utf-8").count("apply_pending(")


def _helper_apply_pending_count(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("_phase_"):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr == "apply_pending":
                    count += 1
    return count


def _selector_before_mechanism_in_source(tree: ast.AST) -> bool:
    selector_method = _method_def(tree, "_phase_03_action_proposal_and_selection")
    mechanism_method = _method_def(tree, "_phase_06_outcome_evaluation_akbsm_mechanism")
    if selector_method is None or mechanism_method is None:
        return False
    selector_select_line = _first_attribute_line(selector_method, "decision_selector", "select")
    mechanism_run_line = _first_attribute_line(mechanism_method, "expsm_mechanism_search", "run")
    if selector_select_line is None or mechanism_run_line is None:
        return False
    return selector_method.lineno < mechanism_method.lineno and selector_select_line < mechanism_run_line


def _selector_before_mechanism_in_phase_map() -> bool:
    selector_phase = _phase_id_for_module("DecisionSelector")
    mechanism_phase = _phase_id_for_module("ExpSMMechanismSearch")
    if selector_phase is None or mechanism_phase is None:
        return False
    return int(selector_phase) < int(mechanism_phase)


def _mechanism_search_after_selection_probe() -> bool:
    with tempfile.TemporaryDirectory(prefix="rndem_phase_invariant_") as temp_dir:
        temp_memory = Path(temp_dir) / "Memory"
        shutil.copytree(REAL_MEMORY_ROOT, temp_memory)
        runtime = CLCRuntime(temp_memory, profile="safe_demo", memory_is_temporary=True)
        with redirect_stdout(io.StringIO()):
            for tick in range(1, 7):
                activation = 0.9 if tick % 2 == 0 else 0.2
                runtime.feed_audio(tick, {440: activation, 880: 0.2, 1200: 0.1})
        events_by_tick: dict[int, list[OperationMarker]] = {}
        for event in runtime.memory.events:
            events_by_tick.setdefault(event.tick, []).append(event.marker)
        observed_tick = False
        for markers in events_by_tick.values():
            if OperationMarker.INTERNAL_DECISION not in markers or OperationMarker.EXPSM_MECHANISM_SEARCH not in markers:
                continue
            observed_tick = True
            decision_index = markers.index(OperationMarker.INTERNAL_DECISION)
            mechanism_index = markers.index(OperationMarker.EXPSM_MECHANISM_SEARCH)
            if decision_index >= mechanism_index:
                return False
        return observed_tick


def _reflection_phase_after_behavior(phase_order: list[str]) -> bool:
    try:
        reflection_index = phase_order.index("_phase_10_runtime_observation_views")
    except ValueError:
        return False
    behavior_phases = (
        "_phase_03_action_proposal_and_selection",
        "_phase_04_decision_audit_and_effects",
        "_phase_05_mode_consolidation_memory_chain",
        "_phase_06_outcome_evaluation_akbsm_mechanism",
        "_phase_07_value_feedback",
        "_phase_08_neuromodulation_projection",
        "_phase_09_final_field_refresh",
    )
    return all(phase_order.index(phase) < reflection_index for phase in behavior_phases if phase in phase_order)


def _reflection_pressure_isolated() -> tuple[bool, list[str]]:
    findings: list[str] = []
    for relative_path in BEHAVIOR_MODULES:
        path = ROOT / relative_path
        if not path.exists():
            findings.append(f"missing behavior module: {relative_path}")
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        except SyntaxError as exc:
            findings.append(f"{relative_path}:{exc.lineno or 0}: syntax: {exc.msg}")
            continue
        findings.extend(_observation_references(tree, relative_path))
    return not findings, findings


def _observation_references(tree: ast.AST, relative_path: str) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_OBSERVATION_MODULES:
                    findings.append(f"{relative_path}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = _absolute_import_module(node)
            if module in FORBIDDEN_OBSERVATION_MODULES:
                findings.append(f"{relative_path}:{node.lineno}: import-from {module}")
            for alias in node.names:
                if alias.name in FORBIDDEN_OBSERVATION_NAMES:
                    findings.append(f"{relative_path}:{node.lineno}: import-name {alias.name}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_OBSERVATION_NAMES:
                findings.append(f"{relative_path}:{node.lineno}: name {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_OBSERVATION_NAMES:
                findings.append(f"{relative_path}:{node.lineno}: attribute {node.attr}")
    return findings


def _marker_36_absent_from_implementation() -> tuple[bool, list[str]]:
    findings: list[str] = []
    marker_number = "36"
    strict_patterns = (
        "MARKER_" + marker_number,
        "OperationMarker." + marker_number,
        "OperationMarker(" + marker_number,
    )
    paths = [ROOT / "main.py"]
    paths.extend(path for path in (ROOT / "clc").rglob("*.py") if path.is_file())
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in strict_patterns):
            findings.append(str(path.relative_to(ROOT)))
    return not findings, findings


def _run_key_verifiers() -> bool:
    for relative_path in KEY_VERIFIERS:
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(result.stdout)
            return False
    return True


def _method_def(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _first_attribute_line(node: ast.AST, owner_name: str, attr_name: str) -> int | None:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if not isinstance(func, ast.Attribute) or func.attr != attr_name:
            continue
        value = func.value
        if isinstance(value, ast.Attribute) and value.attr == owner_name:
            return child.lineno
    return None


def _phase_id_for_module(module_name: str) -> str | None:
    for entry in RUNTIME_PHASE_MAP:
        if module_name in entry.modules:
            return entry.phase_id
    return None


def _absolute_import_module(node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    if not node.module:
        return ""
    return "." * node.level + node.module


if __name__ == "__main__":
    raise SystemExit(main())
