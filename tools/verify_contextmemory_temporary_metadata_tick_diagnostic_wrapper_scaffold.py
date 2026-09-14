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
    TemporaryMetadataTickDiagnosticSnapshot,
    TemporaryMetadataTickDiagnosticWrapper,
    TemporaryMetadataTickDiagnosticWrapperResult,
    run_tick_with_temporary_metadata_diagnostics,
)
from clc.scenarios.scenario_loader import load_scenario
from clc.scenarios.scenario_runner import REAL_MEMORY_ROOT, run_scenario_fixture
from tools import verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold as scaffold


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

MODULE_PATH = ROOT / "clc" / "runtime" / "context_temporary_metadata_tick_diagnostics.py"
RUNTIME_PATH = ROOT / "clc" / "runtime" / "clc_runtime.py"
SCENARIO_PATH = (
    ROOT / "scenarios" / "contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.json"
)

FORBIDDEN_METHOD_NAMES = frozenset(
    ("commit", "apply", "save", "write", "persist", "mutate", "store", "enqueue", "flush", "sync")
)
FORBIDDEN_CALL_NAMES = frozenset(
    (
        "open",
        "mkdir",
        "replace",
        "unlink",
        "dump",
        "dumps",
        "add_event",
        "add_frame",
        "apply_retention",
        "apply_side_list_retention",
        "apply_pending",
        "commit",
        "apply",
        "save",
        "write",
        "persist",
        "mutate",
        "store",
        "enqueue",
        "flush",
        "sync",
    )
)
FORBIDDEN_EXECUTABLE_KEYS = frozenset(
    ("commit", "apply", "save", "write", "persist", "mutate", "store", "enqueue", "flush", "sync")
)
FORBIDDEN_INSTRUCTION_FRAGMENTS = frozenset(
    ("behavior_instruction", "scoring_instruction", "guard_instruction", "mode_c_instruction", "policy_pressure_instruction")
)
FORBIDDEN_RUNTIME_WIRING_SYMBOLS = (
    "context_temporary_metadata_tick_diagnostics",
    "TemporaryMetadataTickDiagnosticSnapshot",
    "TemporaryMetadataTickDiagnosticWrapperResult",
    "TemporaryMetadataTickDiagnosticWrapper",
    "run_tick_with_temporary_metadata_diagnostics",
)
FORBIDDEN_RUNTIME_WIRING_TARGETS = (
    ROOT / "clc" / "runtime" / "clc_runtime.py",
    ROOT / "clc" / "runtime" / "mode_c_advisory.py",
    ROOT / "clc" / "consolidation",
    ROOT / "clc" / "action",
    ROOT / "clc" / "evaluation",
    ROOT / "clc" / "system",
)
CORE_VERIFIERS = (
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
    result, recorder = _wrapped_result(diagnostics_enabled=True)
    disabled, disabled_recorder = _wrapped_result(diagnostics_enabled=False)
    spec = _fixture_spec()
    results = {
        "tick diagnostic wrapper module exists": MODULE_PATH.exists(),
        "wrapper result/snapshot objects exist": _case_objects_exist(result),
        "explicit wrapper API exists": callable(run_tick_with_temporary_metadata_diagnostics),
        "explicit tick diagnostic authority is required": result is not None,
        "missing authority rejected": _case_missing_authority_rejected(),
        "unknown authority rejected": _case_unknown_authority_rejected(),
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
        "tick diagnostic authority cannot authorize writes": _case_no_write_authority(result),
        "wrapper uses existing diagnostic scaffold": _case_uses_existing_diagnostic_scaffold(),
        "wrapper is read-only": _case_read_only(result),
        "wrapper is metadata-only": _case_metadata_only(result),
        "wrapper is external to _run_tick": _case_external_to_run_tick(),
        "wrapper does not import/call CLCRuntime._run_tick directly": _case_no_direct_runtime_reference(),
        "wrapped behavior output equals direct tick callable output": _case_behavior_output_preserved(result),
        "tick callable receives unchanged args/kwargs": _case_tick_args_unchanged(recorder),
        "diagnostics are separate from behavior output": _case_diagnostics_separate(result),
        "diagnostics disabled preserves behavior output": _case_disabled_preserves_behavior(disabled),
        "diagnostics enabled preserves behavior output": _case_behavior_output_preserved(result),
        "diagnostic data is not passed into tick callable": _case_diagnostic_data_not_passed(recorder)
        and _case_diagnostic_data_not_passed(disabled_recorder),
        "expired metadata ignored as active": _case_expired_ignored_as_active(result),
        "expired metadata only appears in optional diagnostics": _case_expired_optional_only(),
        "AKBSM proposal metadata remains metadata-only": scaffold._case_akbsm_metadata_only(),
        "accepted_for_observation is not write approval": scaffold._case_state_no_write("accepted_for_observation"),
        "deferred is not pending commit": scaffold._case_state_no_write("deferred"),
        "rejected/expired do not authorize writes": scaffold._case_state_no_write("rejected")
        and scaffold._case_state_no_write("expired"),
        "proposal.commit_allowed remains False": scaffold._sample_proposal().commit_allowed is False,
        "diagnostic snapshot/report has no writer command fields": _case_no_writer_command_fields(result),
        "diagnostic snapshot/report has no behavior/scoring/guard instruction fields": _case_no_instruction_fields(result),
        "scenario fixture exists": SCENARIO_PATH.exists(),
        "scenario fixture runner safe": _case_fixture_runner_safe(),
        "scenario fixture metadata complete": _case_fixture_metadata_complete(spec),
        "wrapper is not imported/called by normal runtime": _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by _run_tick": _case_run_tick_unchanged()
        and _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by DecisionSelector": _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by ActionScoring": _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by ActionProposer": _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by ModeActionGuard": _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by Mode C": _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by PolicyPressureReview": _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by memory writers": _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by AKBSM writers": _case_no_normal_runtime_wiring(),
        "wrapper is not imported/called by ExpSM writers": _case_no_normal_runtime_wiring(),
        "no ContextMemoryManager import/call": _case_no_contextmemory_manager_reference(),
        "no real ContextMemory reads/writes": _case_no_real_contextmemory_reference(),
        "no permanent proposal files": _case_no_permanent_proposal_files(inventory_before),
        "no permanent proposal queues": _case_no_permanent_queue_text(),
        "no Memory/AKBSM writes": _case_no_memory_file_terms("Memory/AKBSM"),
        "no Memory/ExpSM writes": _case_no_memory_file_terms("Memory/ExpSM"),
        "no semantic_core.json": _case_no_memory_file_terms("semantic_core.json"),
        "no technical_feedback_patterns.json": _case_no_memory_file_terms("technical_feedback_patterns.json"),
        "no default _run_tick path change": _case_run_tick_unchanged(),
        "tick phase order unchanged by this pass": _case_run_tick_unchanged(),
        "ContextMemoryManager.apply_pending timing unchanged by this pass": _case_run_tick_unchanged(),
        "no forbidden method names": _case_no_forbidden_methods(),
        "marker 36 absent": scaffold._case_marker_36_absent(),
        "core safety still passes": _run_core_verifiers(),
    }
    after = _real_hashes()
    results["Memory inventory unchanged"] = inventory_before == _memory_inventory()
    results["real ExpSM unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real AKBSM unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("ContextMemory temporary metadata tick diagnostic wrapper scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print("  no-behavior-influence proof: included in this scaffold verifier")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_objects_exist(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    return (
        TemporaryMetadataTickDiagnosticSnapshot.__name__ == "TemporaryMetadataTickDiagnosticSnapshot"
        and TemporaryMetadataTickDiagnosticWrapperResult.__name__
        == "TemporaryMetadataTickDiagnosticWrapperResult"
        and TemporaryMetadataTickDiagnosticWrapper.__name__ == "TemporaryMetadataTickDiagnosticWrapper"
        and isinstance(result, TemporaryMetadataTickDiagnosticWrapperResult)
        and isinstance(result.diagnostic_snapshot, TemporaryMetadataTickDiagnosticSnapshot)
    )


def _case_missing_authority_rejected() -> bool:
    return TemporaryMetadataTickDiagnosticWrapper().run(
        _tick_callable()[0],
        placement=scaffold._placement(),
        current_tick=4,
    ) is None


def _case_unknown_authority_rejected() -> bool:
    return _call_with_authority("normal_runtime") is None


def _case_authority_rejected(authority: str) -> bool:
    return _call_with_authority(authority) is None


def _case_tick_authority_cannot_place() -> bool:
    result = ContextTemporaryMetadataPlacement().place_temporary_metadata(
        {"payload_id": "tick_diag_auth_cannot_place"},
        namespace="scenario",
        source="scenario_harness",
        authority=CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY,
        created_tick=1,
        ttl_ticks=3,
    )
    return not result.accepted and result.entry is None


def _case_no_write_authority(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None:
        return False
    payload = result.as_payload()
    snapshot = payload["diagnostic_snapshot"]
    return (
        payload["write_authorized"] is False
        and payload["pending_commit"] is False
        and payload["akbsm_write_approved"] is False
        and payload["expsm_write_approved"] is False
        and snapshot["write_authorized"] is False
        and snapshot["diagnostic_report"]["write_authorized"] is False
    )


def _case_uses_existing_diagnostic_scaffold() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    return (
        "build_runtime_temporary_metadata_diagnostics" in text
        and "CONTEXT_TEMPORARY_METADATA_RUNTIME_DIAGNOSTIC_AUTHORITY" in text
    )


def _case_read_only(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None:
        return False
    payload = result.as_payload()
    return (
        payload["read_only"] is True
        and payload["contextmemory_read"] is False
        and payload["contextmemory_written"] is False
        and payload["contextmemory_manager_called"] is False
        and payload["normal_runtime_default"] is False
        and payload["run_tick_default"] is False
    )


def _case_metadata_only(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None or result.diagnostic_snapshot is None:
        return False
    payload = result.as_payload()
    snapshot = payload["diagnostic_snapshot"]
    report = snapshot["diagnostic_report"]
    return (
        payload["metadata_only"] is True
        and payload["diagnostic_only"] is True
        and snapshot["metadata_only"] is True
        and snapshot["diagnostic_only"] is True
        and report["metadata_only"] is True
        and report["diagnostic_only"] is True
        and report["view"]["active_count"] == 2
        and report["view"]["namespaces_present"] == ("akbsm_proposal_review", "scenario")
    )


def _case_external_to_run_tick() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    return "_run_tick" not in text and "CLCRuntime" not in text


def _case_no_direct_runtime_reference() -> bool:
    text = MODULE_PATH.read_text(encoding="utf-8")
    return "CLCRuntime" not in text and "_run_tick" not in text and "clc_runtime" not in text


def _case_behavior_output_preserved(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    return result is not None and result.behavior_output == _direct_tick_output()


def _case_tick_args_unchanged(recorder: dict[str, Any]) -> bool:
    return recorder == {"args": ("alpha", 7), "kwargs": {"mode": "safe", "enabled": True}}


def _case_diagnostics_separate(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    return (
        result is not None
        and result.diagnostic_snapshot is not None
        and result.behavior_output == _direct_tick_output()
        and result.diagnostic_snapshot.as_payload()["diagnostic_report"]["view"]["active_count"] == 2
        and "diagnostic_snapshot" not in result.behavior_output
    )


def _case_disabled_preserves_behavior(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    return (
        result is not None
        and result.behavior_output == _direct_tick_output()
        and result.diagnostic_snapshot is None
        and result.diagnostics_enabled is False
    )


def _case_diagnostic_data_not_passed(recorder: dict[str, Any]) -> bool:
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


def _case_expired_ignored_as_active(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None or result.diagnostic_snapshot is None:
        return False
    view = result.diagnostic_snapshot.as_payload()["diagnostic_report"]["view"]
    return view["active_count"] == 2 and view["expired_diagnostics_count"] == 0


def _case_expired_optional_only() -> bool:
    tick_callable, _ = _tick_callable()
    result = run_tick_with_temporary_metadata_diagnostics(
        tick_callable,
        placement=scaffold._placement(),
        authority=CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY,
        current_tick=4,
        include_expired_diagnostics=True,
        tick_args=("alpha", 7),
        tick_kwargs={"mode": "safe", "enabled": True},
    )
    if result is None or result.diagnostic_snapshot is None:
        return False
    view = result.diagnostic_snapshot.as_payload()["diagnostic_report"]["view"]
    expired = view["expired_diagnostics"]
    return (
        view["active_count"] == 2
        and view["expired_diagnostics_count"] == 1
        and expired[0]["expired"] is True
        and expired[0]["active"] is False
        and expired[0]["diagnostic_only"] is True
        and expired[0]["write_authorized"] is False
    )


def _case_no_writer_command_fields(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None:
        return False
    keys = _flatten_keys(result.as_payload())
    return not any(key in FORBIDDEN_EXECUTABLE_KEYS for key in keys)


def _case_no_instruction_fields(result: TemporaryMetadataTickDiagnosticWrapperResult | None) -> bool:
    if result is None:
        return False
    flattened = _flatten(result.as_payload())
    return not any(
        isinstance(item, str)
        and any(fragment in item.lower() for fragment in FORBIDDEN_INSTRUCTION_FRAGMENTS)
        for item in flattened
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
        and cases.get("external_wrapper_separate_snapshot") is True
        and cases.get("missing_authority_rejected") is True
        and cases.get("unknown_authority_rejected") is True
        and cases.get("placement_authority_rejected") is True
        and cases.get("observation_authority_rejected") is True
        and cases.get("runtime_diagnostic_authority_rejected") is True
        and cases.get("tick_authority_cannot_place_metadata") is True
        and cases.get("tick_authority_cannot_authorize_writes") is True
        and cases.get("behavior_output_equals_direct_tick_output") is True
        and cases.get("tick_callable_args_kwargs_unchanged") is True
        and cases.get("diagnostic_snapshot_separate_from_behavior_output") is True
        and cases.get("diagnostics_disabled_preserves_behavior_output") is True
        and cases.get("diagnostics_enabled_preserves_behavior_output") is True
        and cases.get("diagnostic_data_not_passed_into_tick_callable") is True
        and cases.get("active_metadata_diagnostic_only") is True
        and cases.get("expired_metadata_ignored_as_active") is True
        and cases.get("expired_metadata_optional_diagnostics_only") is True
        and cases.get("normal_runtime_wrapper_call") is False
        and cases.get("run_tick_wrapper_call") is False
        and cases.get("selector_scoring_proposer_guard_mode_policy_writer_calls") is False
        and cases.get("real_contextmemory_read") is False
        and cases.get("real_contextmemory_write") is False
        and cases.get("proposal_storage_files_created") is False
        and cases.get("permanent_proposal_queue_created") is False
        and cases.get("review_record_persistence_added") is False
        and cases.get("akbsm_write_forbidden") is True
        and cases.get("expsm_write_forbidden") is True
        and cases.get("marker_36_absent") is True
    )


def _case_no_contextmemory_manager_reference() -> bool:
    return "ContextMemoryManager" not in MODULE_PATH.read_text(encoding="utf-8")


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


def _case_no_memory_file_terms(term: str) -> bool:
    return term not in MODULE_PATH.read_text(encoding="utf-8")


def _case_no_normal_runtime_wiring() -> bool:
    for target in FORBIDDEN_RUNTIME_WIRING_TARGETS:
        paths = target.rglob("*.py") if target.is_dir() else (target,)
        for path in paths:
            if not path.exists() or path == MODULE_PATH:
                continue
            text = path.read_text(encoding="utf-8")
            if any(symbol in text for symbol in FORBIDDEN_RUNTIME_WIRING_SYMBOLS):
                return False
    return True


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
            if node.name.lower() in FORBIDDEN_METHOD_NAMES:
                return False
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in FORBIDDEN_CALL_NAMES:
                return False
            if call_name.endswith(tuple(f".{name}" for name in FORBIDDEN_CALL_NAMES)):
                return False
    return True


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
    *, diagnostics_enabled: bool
) -> tuple[TemporaryMetadataTickDiagnosticWrapperResult | None, dict[str, Any]]:
    tick_callable, recorder = _tick_callable()
    result = run_tick_with_temporary_metadata_diagnostics(
        tick_callable,
        placement=scaffold._placement(),
        authority=CONTEXT_TEMPORARY_METADATA_TICK_DIAGNOSTIC_AUTHORITY,
        current_tick=4,
        diagnostics_enabled=diagnostics_enabled,
        tick_args=("alpha", 7),
        tick_kwargs={"mode": "safe", "enabled": True},
    )
    return result, recorder


def _call_with_authority(authority: str) -> TemporaryMetadataTickDiagnosticWrapperResult | None:
    tick_callable, _ = _tick_callable()
    return run_tick_with_temporary_metadata_diagnostics(
        tick_callable,
        placement=scaffold._placement(),
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
    spec = expect.get("contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold", {})
    return dict(spec) if isinstance(spec, dict) else {}


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
