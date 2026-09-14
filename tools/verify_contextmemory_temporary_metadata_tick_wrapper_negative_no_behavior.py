from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.context_temporary_metadata import (
    CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY,
    ContextTemporaryMetadataPlacement,
)
from clc.runtime.context_temporary_metadata_diagnostics import (
    CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY,
)
from clc.runtime.context_temporary_metadata_observation import (
    CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY,
)
from clc.runtime.context_temporary_metadata_tick_diagnostics import (
    CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY,
    TemporaryMetadataTickDiagnosticWrapper,
    TemporaryMetadataTickDiagnosticWrapperResult,
    run_tick_with_temporary_metadata_diagnostics,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture
from tools import verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold as diagnostic_scaffold


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

MODULE_PATH = ROOT / "clc" / "runtime" / "context_temporary_metadata_tick_diagnostics.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = (
    ROOT / "scenarios" / "contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.json"
)
DEBUG_AUDIT_PATH = ROOT / "docs" / "debug_name_dependency_audit.json"

FORBIDDEN_COMMAND_KEYS = frozenset(
    ("commit", "apply", "save", "write", "persist", "mutate", "store", "enqueue", "flush", "sync")
)
FORBIDDEN_INSTRUCTION_FRAGMENTS = frozenset(
    (
        "behavior_instruction",
        "scoring_instruction",
        "guard_instruction",
        "mode_c_instruction",
        "policy_pressure_instruction",
    )
)
FORBIDDEN_WRAPPER_SYMBOLS = (
    "context_temporary_metadata_tick_diagnostics",
    "TemporaryMetadataTickDiagnosticSnapshot",
    "TemporaryMetadataTickDiagnosticWrapperResult",
    "TemporaryMetadataTickDiagnosticWrapper",
    "run_tick_with_temporary_metadata_diagnostics",
)
FORBIDDEN_WIRING_TARGETS = (
    ROOT / "clc" / "runtime" / "clc_runtime.py",
    ROOT / "clc" / "runtime" / "mode_c_advisory.py",
    ROOT / "clc" / "action",
    ROOT / "clc" / "consolidation",
    ROOT / "clc" / "evaluation",
    ROOT / "clc" / "experience",
    ROOT / "clc" / "system",
)
CORE_VERIFIERS = (
    "tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py",
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_negative_retention.py",
    "tools/verify_memory_mutation_policy.py",
)


def main() -> int:
    before = _real_hashes()
    inventory_before = _memory_inventory()
    enabled_result, enabled_recorder = _wrapped_result(diagnostics_enabled=True)
    disabled_result, disabled_recorder = _wrapped_result(diagnostics_enabled=False)
    optional_expired_result, _ = _wrapped_result(
        diagnostics_enabled=True,
        include_expired_diagnostics=True,
    )
    spec = _fixture_spec()
    results = {
        "negative/no-behavior tick wrapper fixture exists": SCENARIO_PATH.exists(),
        "tick wrapper scaffold module exists": MODULE_PATH.exists(),
        "missing tick diagnostic authority rejected": _case_missing_authority_rejected(),
        "unknown tick diagnostic authority rejected": _case_unknown_authority_rejected(),
        "placement authority rejected as tick diagnostic authority": _case_authority_rejected(
            CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY
        ),
        "observation authority rejected as tick diagnostic authority": _case_authority_rejected(
            CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY
        ),
        "runtime diagnostic authority rejected as tick diagnostic authority": _case_authority_rejected(
            CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY
        ),
        "tick diagnostic authority cannot place metadata": _case_tick_authority_cannot_place(),
        "tick diagnostic authority cannot authorize writes": _case_no_write_authority(enabled_result),
        "direct callable output equals wrapped behavior_output": _case_behavior_preserved(enabled_result),
        "diagnostics disabled preserves behavior_output": _case_disabled_preserves_behavior(disabled_result),
        "diagnostics enabled preserves behavior_output": _case_behavior_preserved(enabled_result),
        "tick callable args unchanged": enabled_recorder.get("args") == ("alpha", 7),
        "tick callable kwargs unchanged": enabled_recorder.get("kwargs") == {"mode": "safe", "enabled": True},
        "diagnostic data is not passed into tick callable": _case_no_diagnostic_data_passed(
            enabled_recorder
        )
        and _case_no_diagnostic_data_passed(disabled_recorder),
        "diagnostic snapshot is separate from behavior_output": _case_snapshot_separate(enabled_result),
        "diagnostic snapshot/report has no writer command fields": _case_no_writer_command_fields(
            enabled_result
        ),
        "diagnostic snapshot/report has no behavior/scoring/guard instruction fields": (
            _case_no_instruction_fields(enabled_result, ("behavior", "scoring", "guard"))
        ),
        "diagnostic snapshot/report has no Mode C/PolicyPressureReview instruction fields": (
            _case_no_instruction_fields(enabled_result, ("mode_c", "policy_pressure"))
        ),
        "expired metadata ignored as active": _case_expired_ignored_as_active(enabled_result),
        "optional expired diagnostics remain diagnostic-only": _case_expired_optional_only(
            optional_expired_result
        ),
        "AKBSM proposal metadata remains metadata-only": diagnostic_scaffold._case_akbsm_metadata_only(),
        "accepted_for_observation is not write approval": diagnostic_scaffold._case_state_no_write(
            "accepted_for_observation"
        ),
        "deferred is not pending commit": diagnostic_scaffold._case_state_no_write("deferred"),
        "rejected/expired do not authorize writes": diagnostic_scaffold._case_state_no_write(
            "rejected"
        )
        and diagnostic_scaffold._case_state_no_write("expired"),
        "proposal.commit_allowed remains False": diagnostic_scaffold._sample_proposal().commit_allowed
        is False,
        "wrapper is not imported/called by normal runtime": _case_no_wiring(),
        "wrapper is not imported/called by _run_tick": _case_run_tick_unchanged() and _case_no_wiring(),
        "wrapper is not imported/called by DecisionSelector": _case_no_wiring(),
        "wrapper is not imported/called by ActionScoring": _case_no_wiring(),
        "wrapper is not imported/called by ActionProposer": _case_no_wiring(),
        "wrapper is not imported/called by ModeActionGuard": _case_no_wiring(),
        "wrapper is not imported/called by Mode C": _case_no_wiring(),
        "wrapper is not imported/called by PolicyPressureReview": _case_no_wiring(),
        "wrapper is not imported/called by memory writers": _case_no_wiring(),
        "wrapper is not imported/called by AKBSM writers": _case_no_wiring(),
        "wrapper is not imported/called by ExpSM writers": _case_no_wiring(),
        "wrapper does not import CLCRuntime": _case_no_runtime_reference(),
        "wrapper does not import/call CLCRuntime._run_tick": _case_no_runtime_reference(),
        "no ContextMemoryManager import/call": _case_text_absent("ContextMemoryManager"),
        "no real ContextMemory reads/writes": _case_no_real_contextmemory_reference(),
        "no permanent proposal files": _case_no_permanent_proposal_files(inventory_before),
        "no permanent proposal queues": _case_no_permanent_queue_text(),
        "no Memory/AKBSM writes": _case_text_absent("Memory/AKBSM"),
        "no Memory/ExpSM writes": _case_text_absent("Memory/ExpSM"),
        "no semantic_core.json": _case_text_absent("semantic_core.json"),
        "no technical_feedback_patterns.json": _case_text_absent("technical_feedback_patterns.json"),
        "no default _run_tick path change": _case_run_tick_unchanged(),
        "tick phase order unchanged by this pass": _case_run_tick_unchanged(),
        "ContextMemoryManager.apply_pending timing unchanged by this pass": _case_run_tick_unchanged(),
        "no forbidden method names": _case_no_forbidden_methods(),
        "marker 36 absent": diagnostic_scaffold._case_marker_36_absent(),
        "debug-name high-risk findings remain 0": _case_debug_high_risk_zero(),
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario fixture metadata complete": _case_fixture_metadata_complete(spec),
        "core safety still passes": _run_core_verifiers(),
    }
    after = _real_hashes()
    results["Memory inventory unchanged"] = inventory_before == _memory_inventory()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("ContextMemory temporary metadata tick wrapper negative/no-behavior verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_missing_authority_rejected() -> bool:
    tick, _ = _tick_callable()
    return (
        TemporaryMetadataTickDiagnosticWrapper().run(
            tick,
            placement=diagnostic_scaffold._placement(),
            current_tick=4,
        )
        is None
    )


def _case_unknown_authority_rejected() -> bool:
    return _call_with_authority("unknown_tick_authority") is None


def _case_authority_rejected(authority: str) -> bool:
    return _call_with_authority(authority) is None


def _case_tick_authority_cannot_place() -> bool:
    result = ContextTemporaryMetadataPlacement().place_temporary_metadata(
        {"payload_id": "tick_diag_authority_cannot_place"},
        namespace="scenario",
        source="scenario_harness",
        authority=CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY,
        created_tick=1,
        ttl_ticks=3,
    )
    return not result.accepted and result.entry is None


def _case_no_write_authority(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None or result.diagnostic_snapshot is None:
        return False
    payload = result.as_payload()
    snapshot = result.diagnostic_snapshot.as_payload()
    report = snapshot["diagnostic_report"]
    view = report["view"]
    return all(
        item is False
        for item in (
            payload["write_authorized"],
            payload["pending_commit"],
            payload["akbsm_write_approved"],
            payload["expsm_write_approved"],
            snapshot["write_authorized"],
            snapshot["pending_commit"],
            snapshot["akbsm_write_approved"],
            snapshot["expsm_write_approved"],
            report["write_authorized"],
            report["pending_commit"],
            report["akbsm_write_approved"],
            report["expsm_write_approved"],
            view["write_authorized"],
            view["pending_commit"],
        )
    )


def _case_behavior_preserved(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    return result is not None and result.behavior_output == _direct_tick_output()


def _case_disabled_preserves_behavior(
    result: TemporaryMetadataTickDiagnosticWrapperResult | None,
) -> bool:
    return (
        result is not None
        and result.behavior_output == _direct_tick_output()
        and result.diagnostic_snapshot is None
        and result.diagnostics_enabled is False
    )


def _case_no_diagnostic_data_passed(recorder: dict[str, Any]) -> bool:
    flattened = _flatten(recorder)
    return not any(
        isinstance(item, str)
        and (
            "diagnostic" in item.lower()
            or "temporary_metadata" in item.lower()
            or "active_count" in item.lower()
        )
        for item in flattened
    )


def _case_snapshot_separate(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None or result.diagnostic_snapshot is None:
        return False
    behavior = result.behavior_output
    return (
        behavior == _direct_tick_output()
        and "diagnostic_snapshot" not in behavior
        and result.diagnostic_snapshot.as_payload()["diagnostic_report"]["view"]["active_count"] == 2
    )


def _case_no_writer_command_fields(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None:
        return False
    keys = _flatten_keys(result.as_payload())
    return not any(key.lower() in FORBIDDEN_COMMAND_KEYS for key in keys)


def _case_no_instruction_fields(
    result: TemporaryMetadataTickDiagnosticWrapperResult | None,
    fragments: tuple[str, ...],
) -> bool:
    if result is None:
        return False
    lowered = tuple(str(item).lower() for item in _flatten(result.as_payload()))
    selected_fragments = tuple(
        fragment
        for fragment in FORBIDDEN_INSTRUCTION_FRAGMENTS
        if any(fragment.startswith(prefix) for prefix in fragments)
    )
    return not any(
        fragment in item for item in lowered for fragment in selected_fragments
    )


def _case_expired_ignored_as_active(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None or result.diagnostic_snapshot is None:
        return False
    view = result.diagnostic_snapshot.as_payload()["diagnostic_report"]["view"]
    return view["active_count"] == 2 and view["expired_diagnostics_count"] == 0


def _case_expired_optional_only(
    result: TemporaryMetadataTickDiagnosticWrapperResult | None,
) -> bool:
    if result is None or result.diagnostic_snapshot is None:
        return False
    view = result.diagnostic_snapshot.as_payload()["diagnostic_report"]["view"]
    expired = view["expired_diagnostics"]
    return (
        view["active_count"] == 2
        and view["expired_diagnostics_count"] == 1
        and len(expired) == 1
        and expired[0]["expired"] is True
        and expired[0]["active"] is False
        and expired[0]["diagnostic_only"] is True
        and expired[0]["write_authorized"] is False
        and expired[0]["pending_commit"] is False
    )


def _case_no_wiring() -> bool:
    for target in FORBIDDEN_WIRING_TARGETS:
        paths = target.rglob("*.py") if target.is_dir() else (target,)
        for path in paths:
            if not path.exists() or path == MODULE_PATH:
                continue
            text = path.read_text(encoding="utf-8")
            if any(symbol in text for symbol in FORBIDDEN_WRAPPER_SYMBOLS):
                return False
    return True


def _case_no_runtime_reference() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    return "CLCRuntime" not in text and "_run_tick" not in text and "clc_runtime" not in text


def _case_text_absent(text: str) -> bool:
    return text not in MODULE_PATH.read_text(encoding="utf-8")


def _case_no_real_contextmemory_reference() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    return "clc.context.context_memory" not in text and "ContextMemory(" not in text


def _case_no_permanent_proposal_files(before_inventory: tuple[str, ...]) -> bool:
    after_inventory = _memory_inventory()
    return before_inventory == after_inventory and not any(
        "proposal" in path.lower() for path in after_inventory
    )


def _case_no_permanent_queue_text() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8").lower()
    return "permanent proposal queue" not in text and "proposal queue persistence" not in text


def _case_run_tick_unchanged() -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", "main...HEAD", "--", str(RUNTIME_PATH.relative_to(ROOT))],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def _case_no_forbidden_methods() -> bool:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.lower() in FORBIDDEN_COMMAND_KEYS:
                return False
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in FORBIDDEN_COMMAND_KEYS:
                return False
            if name.endswith(tuple(f".{item}" for item in FORBIDDEN_COMMAND_KEYS)):
                return False
    return True


def _case_debug_high_risk_zero() -> bool:
    if not DEBUG_AUDIT_PATH.exists():
        return False
    data = json.loads(DEBUG_AUDIT_PATH.read_text(encoding="utf-8"))
    findings = data.get("findings", [])
    return isinstance(findings, list) and not any(
        isinstance(item, dict) and item.get("risk") == "high" for item in findings
    )


def _case_fixture_runner_safe() -> bool:
    try:
        fixture = load_scenario(SCENARIO_PATH)
        result = run_scenario_fixture(fixture, memory_root=REAL_MEMORY_ROOT)
    except Exception:
        return False
    return result.passed and result.memory_unchanged and not result.marker_sequence


def _case_fixture_metadata_complete(spec: dict[str, Any]) -> bool:
    cases = spec.get("cases", {})
    return (
        spec.get("test_only") is True
        and spec.get("authority") == CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY
        and spec.get("runtime_diagnostic_authority")
        == CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY
        and spec.get("observation_authority")
        == CONTEXT_TEMPORARY_METADATA_OBSERVATION_TEST_SCENARIO_AUTHORITY
        and spec.get("placement_authority") == CONTEXT_TEMPORARY_METADATA_TEST_SCENARIO_AUTHORITY
        and spec.get("metadata_only") is True
        and spec.get("diagnostic_only") is True
        and spec.get("read_only") is True
        and spec.get("local_only") is True
        and spec.get("external_wrapper") is True
        and spec.get("normal_runtime_default") is False
        and spec.get("run_tick_default") is False
        and spec.get("tick_order_changed") is False
        and spec.get("apply_pending_timing_changed") is False
        and spec.get("contextmemory_manager_called") is False
        and spec.get("contextmemory_read") is False
        and spec.get("contextmemory_written") is False
        and spec.get("proposal_storage_added") is False
        and spec.get("review_record_persistence_added") is False
        and spec.get("permanent_files_created") is False
        and spec.get("permanent_queues_created") is False
        and isinstance(cases, dict)
        and all(cases.get(key) is True for key in _required_true_fixture_cases())
        and all(cases.get(key) is False for key in _required_false_fixture_cases())
    )


def _run_core_verifiers() -> bool:
    if os.environ.get("RNDEM_VERIFIER_SHALLOW") == "1":
        return True
    env = dict(os.environ)
    env["RNDEM_VERIFIER_SHALLOW"] = "1"
    for relative_path in CORE_VERIFIERS:
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=ROOT,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            return False
    return True


def _wrapped_result(
    *,
    diagnostics_enabled: bool,
    include_expired_diagnostics: bool = False,
) -> tuple[TemporaryMetadataTickDiagnosticWrapperResult | None, dict[str, Any]]:
    tick, recorder = _tick_callable()
    result = run_tick_with_temporary_metadata_diagnostics(
        tick,
        placement=diagnostic_scaffold._placement(),
        authority=CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY,
        current_tick=4,
        diagnostics_enabled=diagnostics_enabled,
        include_expired_diagnostics=include_expired_diagnostics,
        tick_args=("alpha", 7),
        tick_kwargs={"mode": "safe", "enabled": True},
    )
    return result, recorder


def _call_with_authority(authority: str) -> TemporaryMetadataTickDiagnosticWrapperResult | None:
    tick, _ = _tick_callable()
    return run_tick_with_temporary_metadata_diagnostics(
        tick,
        placement=diagnostic_scaffold._placement(),
        authority=authority,
        current_tick=4,
        tick_args=("alpha", 7),
        tick_kwargs={"mode": "safe", "enabled": True},
    )


def _tick_callable() -> tuple[Any, dict[str, Any]]:
    recorder: dict[str, Any] = {}

    def tick(*args: Any, **kwargs: Any) -> MappingProxyType[str, Any]:
        recorder["args"] = args
        recorder["kwargs"] = dict(kwargs)
        return _direct_tick_output()

    return tick, recorder


def _direct_tick_output() -> MappingProxyType[str, Any]:
    return MappingProxyType(
        {
            "selected_action": "action_preserve_integrity",
            "confidence": "medium",
            "status": "behavior_output",
        }
    )


def _fixture_spec() -> dict[str, Any]:
    if not SCENARIO_PATH.exists():
        return {}
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    expect = data.get("expect", {})
    if not isinstance(expect, dict):
        return {}
    spec = expect.get("contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior", {})
    return dict(spec) if isinstance(spec, dict) else {}


def _required_true_fixture_cases() -> tuple[str, ...]:
    return (
        "missing_tick_diagnostic_authority_rejected",
        "unknown_tick_diagnostic_authority_rejected",
        "placement_authority_rejected_as_tick_diagnostic_authority",
        "observation_authority_rejected_as_tick_diagnostic_authority",
        "runtime_diagnostic_authority_rejected_as_tick_diagnostic_authority",
        "tick_diagnostic_authority_cannot_place_metadata",
        "tick_diagnostic_authority_cannot_authorize_writes",
        "wrapped_behavior_output_equals_direct_callable_output",
        "diagnostics_disabled_output_equals_direct_callable_output",
        "diagnostics_enabled_output_equals_direct_callable_output",
        "tick_args_unchanged",
        "tick_kwargs_unchanged",
        "diagnostic_data_not_passed_into_callable",
        "diagnostic_snapshot_separate_from_behavior_output",
        "diagnostic_report_contains_no_writer_commands",
        "diagnostic_report_contains_no_behavior_scoring_guard_mode_policy_instructions",
        "active_metadata_visible_only_as_diagnostic_material",
        "expired_metadata_ignored_as_active",
        "expired_metadata_optional_diagnostics_stay_diagnostic_only",
        "akbsm_proposal_metadata_remains_metadata_only",
        "accepted_for_observation_remains_observation_only",
        "deferred_remains_non_commit",
        "rejected_expired_remain_non_authoritative",
        "proposal_commit_allowed_remains_false",
        "akbsm_write_forbidden",
        "expsm_write_forbidden",
        "marker_36_absent",
    )


def _required_false_fixture_cases() -> tuple[str, ...]:
    return (
        "normal_runtime_wrapper_calls",
        "_run_tick_wrapper_calls",
        "selector_scoring_proposer_guard_mode_policy_writer_calls",
        "real_contextmemory_reads",
        "real_contextmemory_writes",
        "proposal_storage_files_created",
        "permanent_proposal_queue_created",
        "review_record_persistence_added",
    )


def _flatten_keys(value: Any) -> tuple[str, ...]:
    if isinstance(value, MappingProxyType):
        return _flatten_keys(dict(value))
    if isinstance(value, dict):
        keys: list[str] = []
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_flatten_keys(item))
        return tuple(keys)
    if isinstance(value, (tuple, list, set)):
        keys = []
        for item in value:
            keys.extend(_flatten_keys(item))
        return tuple(keys)
    return ()


def _flatten(value: Any) -> tuple[Any, ...]:
    if isinstance(value, MappingProxyType):
        return _flatten(dict(value))
    if isinstance(value, dict):
        flattened: list[Any] = []
        for key, item in value.items():
            flattened.extend(_flatten(key))
            flattened.extend(_flatten(item))
        return tuple(flattened)
    if isinstance(value, (tuple, list, set)):
        flattened = []
        for item in value:
            flattened.extend(_flatten(item))
        return tuple(flattened)
    return (value,)


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def _memory_inventory() -> tuple[str, ...]:
    return tuple(
        sorted(str(path.relative_to(ROOT)) for path in (ROOT / "Memory").rglob("*") if path.is_file())
    )


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
