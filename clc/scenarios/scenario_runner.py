from __future__ import annotations

from collections import Counter
from contextlib import redirect_stdout
from dataclasses import dataclass, field
import hashlib
import io
from pathlib import Path
import shutil
import tempfile
from typing import Any

from clc.context.context_retention_policy import ContextRetentionPolicy, SideListRetentionPolicy
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.evaluation.decision_cycle_history_view import DecisionCycleHistorySnapshot
from clc.evaluation.need_more_evidence_signal import NeedMoreEvidenceSignal
from clc.evaluation.policy_pressure import PolicyPressure
from clc.evaluation.policy_pressure_review import PolicyPressureReview
from clc.evaluation.reflection_candidate_builder import ReflectionCandidate
from clc.evaluation.reflection_review import ReflectionReview
from clc.runtime.clc_runtime import CLCRuntime
from clc.scenarios.scenario_loader import ScenarioFixture, ScenarioInput


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REAL_MEMORY_ROOT = PROJECT_ROOT / "Memory"


@dataclass(frozen=True)
class ScenarioRunResult:
    scenario_name: str
    marker_sequence: list[int]
    marker_counts: dict[int, int]
    required_markers_missing: list[int]
    forbidden_markers_present: list[int]
    order_violations: list[tuple[int, int]]
    memory_unchanged: bool
    passed: bool
    warnings: list[str] = field(default_factory=list)
    regression_summary: dict[str, Any] = field(default_factory=dict)
    min_event_count_met: bool = True
    retention_pruned_events: bool = False
    side_list_caps_respected: bool = True
    decision_cycle_history_snapshot: DecisionCycleHistorySnapshot | None = None
    reflection_candidates: list[ReflectionCandidate] = field(default_factory=list)
    need_more_evidence_signal: NeedMoreEvidenceSignal | None = None
    reflection_review: ReflectionReview | None = None
    policy_pressure: PolicyPressure | None = None
    policy_pressure_review: PolicyPressureReview | None = None
    reflection_expectation_violations: list[str] = field(default_factory=list)


def run_scenario_fixture(fixture: ScenarioFixture, *, memory_root: Path = REAL_MEMORY_ROOT) -> ScenarioRunResult:
    before_hashes = _real_memory_hashes()
    warnings: list[str] = []
    with tempfile.TemporaryDirectory(prefix=f"rndem_scenario_{fixture.name}_") as temp_dir:
        temp_memory = Path(temp_dir) / "Memory"
        shutil.copytree(memory_root, temp_memory)
        runtime = _runtime_for_fixture(fixture, temp_memory)
        _inject_synthetic_decision_cycle_summaries(runtime, fixture.synthetic_decision_cycle_summaries)
        max_ticks = int(fixture.runtime.get("max_ticks", max((item.tick for item in fixture.inputs), default=0)))
        with redirect_stdout(io.StringIO()):
            _run_inputs(runtime, fixture.inputs, max_ticks, warnings)
        marker_sequence = [event.marker.value for event in runtime.memory.events]
        marker_counts = dict(Counter(marker_sequence))
        required_missing = [marker for marker in fixture.expect.get("required_markers", []) if marker not in marker_counts]
        forbidden_present = [marker for marker in fixture.expect.get("forbidden_markers", []) if marker in marker_counts]
        order_violations = _order_violations(marker_sequence, fixture.expect.get("marker_order", []))
        min_event_count = int(fixture.expect.get("min_event_count", 0))
        min_event_count_met = len(marker_sequence) >= min_event_count
        retention_pruned = bool(runtime.memory.last_context_retention_result and runtime.memory.last_context_retention_result.pruned_count > 0)
        side_caps_ok = _side_list_caps_respected(runtime)
        history_snapshot = runtime.decision_cycle_history_view.snapshot()
        reflection_candidates = runtime.reflection_candidate_builder.recent_candidates(limit=8)
        need_more_evidence_signal = runtime.need_more_evidence_signal
        reflection_review = runtime.reflection_review
        policy_pressure = runtime.policy_pressure
        policy_pressure_review = runtime.policy_pressure_review
        regression_summary = _regression_summary(fixture, runtime, marker_sequence, marker_counts)
        reflection_violations = _reflection_expectation_violations(
            fixture.expect.get("reflection", {}),
            history_snapshot,
            reflection_candidates,
            need_more_evidence_signal,
            reflection_review,
            policy_pressure,
            policy_pressure_review,
        )
    after_hashes = _real_memory_hashes()
    memory_unchanged = before_hashes == after_hashes
    if fixture.expect.get("memory_unchanged", True) and not memory_unchanged:
        warnings.append("real Memory hashes changed")
    regression_summary["memory_safety"] = {
        "exp_sm_unchanged": before_hashes.get("expsm") == after_hashes.get("expsm"),
        "akbsm_unchanged": before_hashes.get("akbsm") == after_hashes.get("akbsm"),
        "semantic_core_unchanged": before_hashes.get("semantic_core") == after_hashes.get("semantic_core"),
        "technical_feedback_unchanged": before_hashes.get("technical_feedback") == after_hashes.get("technical_feedback"),
    }
    passed = not required_missing and not forbidden_present and not order_violations and memory_unchanged
    if not min_event_count_met:
        passed = False
        warnings.append(f"expected at least {min_event_count} events, observed {len(marker_sequence)}")
    if fixture.expect.get("retention_pruned_events") and not retention_pruned:
        passed = False
        warnings.append("expected context retention pruning did not occur")
    if fixture.expect.get("side_list_caps_respected") and not side_caps_ok:
        passed = False
        warnings.append("side-list caps were not respected")
    if reflection_violations:
        passed = False
        warnings.extend(reflection_violations)
    return ScenarioRunResult(
        scenario_name=fixture.name,
        marker_sequence=marker_sequence,
        marker_counts=marker_counts,
        required_markers_missing=required_missing,
        forbidden_markers_present=forbidden_present,
        order_violations=order_violations,
        memory_unchanged=memory_unchanged,
        passed=passed,
        warnings=warnings,
        regression_summary=regression_summary,
        min_event_count_met=min_event_count_met,
        retention_pruned_events=retention_pruned,
        side_list_caps_respected=side_caps_ok,
        decision_cycle_history_snapshot=history_snapshot,
        reflection_candidates=reflection_candidates,
        need_more_evidence_signal=need_more_evidence_signal,
        reflection_review=reflection_review,
        policy_pressure=policy_pressure,
        policy_pressure_review=policy_pressure_review,
        reflection_expectation_violations=reflection_violations,
    )


def _runtime_for_fixture(fixture: ScenarioFixture, temp_memory: Path) -> CLCRuntime:
    runtime_cfg = fixture.runtime
    context_policy = ContextRetentionPolicy(
        max_events=runtime_cfg.get("context_max_events", 5000),
        protected_recent_events=runtime_cfg.get("protected_recent_events", 200),
        enabled=runtime_cfg.get("context_retention_enabled", True),
    )
    side_policy = SideListRetentionPolicy(
        enabled=runtime_cfg.get("side_list_retention_enabled", True),
        default_max_entries=runtime_cfg.get("side_list_default_max_entries", 500),
    )
    return CLCRuntime(
        temp_memory,
        profile=runtime_cfg.get("profile", "safe_demo"),
        memory_is_temporary=bool(runtime_cfg.get("memory_is_temporary", True)),
        context_retention_policy=context_policy,
        side_list_retention_policy=side_policy,
    )


def _run_inputs(runtime: CLCRuntime, inputs: list[ScenarioInput], max_ticks: int, warnings: list[str]) -> None:
    by_tick: dict[int, list[ScenarioInput]] = {}
    for item in inputs:
        by_tick.setdefault(item.tick, []).append(item)
    for tick in range(0, max_ticks + 1):
        tick_inputs = by_tick.get(tick, [])
        if not tick_inputs:
            continue
        for item in tick_inputs:
            _apply_input(runtime, item, warnings)


def _apply_input(runtime: CLCRuntime, item: ScenarioInput, warnings: list[str]) -> None:
    if item.kind == "audio":
        frequencies = {int(key): float(value) for key, value in item.payload.get("frequencies", {}).items()}
        runtime.feed_audio(item.tick, frequencies)
        return
    if item.kind == "sensor":
        runtime.feed_sensor(
            item.tick,
            cpu_temp=float(item.payload.get("cpu_temp", 40.0)),
            memory_usage=float(item.payload.get("memory_usage", 0.2)),
            damage_flag=bool(item.payload.get("damage_flag", False)),
            resource_pressure=float(item.payload.get("resource_pressure", 0.0)),
        )
        return
    if item.kind == "image":
        runtime.feed_image(item.tick, item.payload.get("pixels", []))
        return
    if item.kind == "tick":
        runtime._run_tick(item.tick)
        return
    if item.kind == "synthetic_policy_pressure_review":
        runtime.policy_pressure = _synthetic_policy_pressure(runtime, item)
        runtime.policy_pressure_review = runtime.policy_pressure_review_builder.build(
            tick=item.tick,
            policy_pressure=runtime.policy_pressure,
        )
        return
    if item.kind == "module_update_burst":
        count = int(item.payload.get("count", 1))
        for index in range(count):
            runtime.ops_pool.push(
                ContextOperation(
                    runtime.id_gen.next("op"),
                    OperationMarker.MODULE_UPDATE,
                    item.tick + index,
                    item.source or "scenario_fixture",
                    None,
                    {"scenario": item.source, "index": index, "activation": item.activation},
                )
            )
        runtime.manager.apply_pending()
        return
    warnings.append(f"unsupported input kind at tick {item.tick}: {item.kind}")


def _inject_synthetic_decision_cycle_summaries(
    runtime: CLCRuntime,
    summaries: list[dict[str, Any]],
) -> None:
    for index, summary in enumerate(summaries, start=1):
        tick = int(summary.get("tick", 0))
        payload = _decision_cycle_summary_payload(runtime, summary, index)
        runtime.memory.add_event(
            ContextOperation(
                runtime.id_gen.next("op"),
                OperationMarker.DECISION_CYCLE_SUMMARY,
                tick,
                "scenario_synthetic_decision_cycle_summary",
                None,
                payload,
            )
        )


def _decision_cycle_summary_payload(
    runtime: CLCRuntime,
    summary: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    cycle_status = str(summary.get("cycle_status", "clean_selection"))
    cycle_confidence = str(summary.get("cycle_confidence", "medium"))
    flags = [str(flag) for flag in summary.get("flags", []) if flag]
    selected = dict(summary.get("selected", {})) if isinstance(summary.get("selected"), dict) else {}
    decision_summary = (
        dict(summary.get("decision_summary", {})) if isinstance(summary.get("decision_summary"), dict) else {}
    )
    guard_summary = dict(summary.get("guard_summary", {})) if isinstance(summary.get("guard_summary"), dict) else {}
    return {
        "decision_cycle_summary_id": summary.get(
            "decision_cycle_summary_id",
            f"scenario_decision_cycle_summary_{index:03d}",
        ),
        "summary_kind": runtime.pattern_registry.id("decision_cycle_summary"),
        "source_decision_id": summary.get("source_decision_id"),
        "source_decision_audit_id": summary.get("source_decision_audit_id"),
        "source_action_guard_audit_id": summary.get("source_action_guard_audit_id"),
        "system_mode_at_summary": summary.get("system_mode_at_summary", runtime.system_state.mode),
        "selected": selected,
        "decision_summary": decision_summary,
        "guard_summary": guard_summary,
        "cycle_summary": {
            "cycle_status": cycle_status,
            "cycle_status_pattern_id": _known_pattern_id(runtime, f"decision_cycle_{cycle_status}"),
            "cycle_confidence": cycle_confidence,
            "cycle_confidence_pattern_id": _known_pattern_id(
                runtime,
                f"decision_cycle_confidence_{cycle_confidence}",
            ),
            "flags": flags,
            "flag_pattern_ids": [
                pattern_id
                for flag in flags
                if (pattern_id := _known_pattern_id(runtime, f"decision_cycle_{flag}")) is not None
            ],
        },
        "memory_modified": False,
        "permanent_memory_modified": False,
        "expsm_modified": False,
        "akbsm_modified": False,
        "activation": float(summary.get("activation", 0.45)),
        "ttl": int(summary.get("ttl", 8)),
    }


def _known_pattern_id(runtime: CLCRuntime, debug_name: str) -> str | None:
    pattern_id = runtime.pattern_registry._name_to_id.get(debug_name)
    return str(pattern_id) if pattern_id else None


def _order_violations(marker_sequence: list[int], marker_order: list[list[int]]) -> list[tuple[int, int]]:
    violations: list[tuple[int, int]] = []
    for before, after in marker_order:
        try:
            before_index = marker_sequence.index(before)
            after_index = marker_sequence.index(after)
        except ValueError:
            continue
        if before_index >= after_index:
            violations.append((before, after))
    return violations


def _side_list_caps_respected(runtime: CLCRuntime) -> bool:
    policy = runtime.side_list_retention_policy
    result = runtime.memory.last_side_list_retention_result
    if result is None:
        return True
    for name, item in result.per_list.items():
        max_entries = policy.max_entries_for(name)
        if max_entries is not None and int(item.get("after") or 0) > max_entries:
            return False
    return True


def _reflection_expectation_violations(
    reflection_expect: object,
    history_snapshot: DecisionCycleHistorySnapshot | None,
    reflection_candidates: list[ReflectionCandidate],
    need_more_evidence_signal: NeedMoreEvidenceSignal | None,
    reflection_review: ReflectionReview | None,
    policy_pressure: PolicyPressure | None,
    policy_pressure_review: PolicyPressureReview | None,
) -> list[str]:
    if not reflection_expect:
        return []
    if not isinstance(reflection_expect, dict):
        return ["expect.reflection must be an object"]
    violations: list[str] = []
    actual_candidate_types = [candidate.reflection_type for candidate in reflection_candidates]
    checks = {
        "history_trend_label": history_snapshot.trend_label if history_snapshot is not None else None,
        "need_more_evidence_active": (
            need_more_evidence_signal.active if need_more_evidence_signal is not None else None
        ),
        "need_more_evidence_reason": need_more_evidence_signal.reason if need_more_evidence_signal is not None else None,
        "reflection_review_status": reflection_review.review_status if reflection_review is not None else None,
        "reflection_review_primary_issue": reflection_review.primary_issue if reflection_review is not None else None,
        "policy_pressure_type": policy_pressure.pressure_type if policy_pressure is not None else None,
        "policy_pressure_active": policy_pressure.active if policy_pressure is not None else None,
        "policy_pressure_recommended_future_operation": (
            policy_pressure.recommended_future_operation if policy_pressure is not None else None
        ),
        "policy_pressure_review_status": (
            policy_pressure_review.review_status if policy_pressure_review is not None else None
        ),
        "policy_pressure_review_primary_issue": (
            policy_pressure_review.primary_issue if policy_pressure_review is not None else None
        ),
        "policy_pressure_review_pressure_type": (
            policy_pressure_review.pressure_type if policy_pressure_review is not None else None
        ),
        "policy_pressure_review_active": (
            policy_pressure_review.pressure_active if policy_pressure_review is not None else None
        ),
        "policy_pressure_review_recommended_future_operation": (
            policy_pressure_review.recommended_future_operation if policy_pressure_review is not None else None
        ),
    }
    for key, actual in checks.items():
        if key in reflection_expect and reflection_expect[key] != actual:
            violations.append(f"reflection expectation failed: {key} expected {reflection_expect[key]!r}, got {actual!r}")
    expected_candidate_types = reflection_expect.get("candidate_types", [])
    if expected_candidate_types:
        if not isinstance(expected_candidate_types, list) or not all(isinstance(item, str) for item in expected_candidate_types):
            violations.append("reflection expectation failed: candidate_types must be list[str]")
        else:
            missing = [item for item in expected_candidate_types if item not in actual_candidate_types]
            if missing:
                violations.append(
                    f"reflection expectation failed: candidate_types missing {missing!r}, got {actual_candidate_types!r}"
                )
    return violations


def regression_summary_for_result(result: ScenarioRunResult) -> dict[str, Any]:
    return dict(result.regression_summary)


def _regression_summary(
    fixture: ScenarioFixture,
    runtime: CLCRuntime,
    marker_sequence: list[int],
    marker_counts: dict[int, int],
) -> dict[str, Any]:
    ticks = {event.tick for event in runtime.memory.events}
    return {
        "schema_version": 1,
        "scenario": fixture.name,
        "tick_count": len(ticks),
        "event_count": len(marker_sequence),
        "marker_sequence": list(marker_sequence),
        "marker_counts": {str(marker): marker_counts[marker] for marker in sorted(marker_counts)},
        "selected_decisions": _selected_decisions(runtime),
        "candidate_source_counts": _candidate_source_counts(runtime),
        "decision_audit_status_counts": _decision_audit_status_counts(runtime),
        "action_guard_status_counts": _action_guard_status_counts(runtime),
        "decision_cycle_summary_status_counts": _decision_cycle_summary_status_counts(runtime),
        "reflection_review_status_counts": _single_count(
            runtime.reflection_review.review_status if runtime.reflection_review is not None else None
        ),
        "policy_pressure_type_counts": _single_count(
            runtime.policy_pressure.pressure_type if runtime.policy_pressure is not None else None
        ),
        "policy_pressure_review_status_counts": _single_count(
            runtime.policy_pressure_review.review_status if runtime.policy_pressure_review is not None else None
        ),
        "need_more_evidence_active_count": (
            1 if runtime.need_more_evidence_signal is not None and runtime.need_more_evidence_signal.active else 0
        ),
        "retention_summary": _retention_summary(runtime),
        "side_list_counts": _side_list_counts(runtime),
        "memory_safety": {
            "exp_sm_unchanged": None,
            "akbsm_unchanged": None,
            "semantic_core_unchanged": None,
            "technical_feedback_unchanged": None,
        },
    }


def _selected_decisions(runtime: CLCRuntime) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for decision in runtime.memory.decisions:
        selected = _selected_candidate_snapshot(decision)
        action_pattern = str(decision.get("decision_pattern_id", ""))
        decisions.append(
            {
                "tick": int(decision.get("_event_tick", 0) or 0),
                "action_pattern": action_pattern,
                "candidate_score": _round_or_none(decision.get("candidate_score")),
                "source": _stable_source(selected.get("source") if selected else decision.get("source")),
                "guard_status": str(selected.get("guard_status", "")) if selected else "",
            }
        )
    return decisions


def _selected_candidate_snapshot(decision: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = decision.get("decision_candidate_audit_snapshot", ())
    if not isinstance(snapshot, (list, tuple)):
        return None
    for item in snapshot:
        if isinstance(item, dict) and item.get("selected"):
            return item
    return None


def _candidate_source_counts(runtime: CLCRuntime) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for decision in runtime.memory.decisions:
        snapshot = decision.get("decision_candidate_audit_snapshot", ())
        if not isinstance(snapshot, (list, tuple)):
            continue
        for item in snapshot:
            if isinstance(item, dict):
                counts[_stable_source(item.get("source"))] += 1
    return dict(sorted(counts.items()))


def _decision_audit_status_counts(runtime: CLCRuntime) -> dict[str, dict[str, int]]:
    confidence: Counter[str] = Counter()
    influence: Counter[str] = Counter()
    scope: Counter[str] = Counter()
    source_type: Counter[str] = Counter()
    for audit in runtime.memory.decision_audits:
        details = audit.get("audit", {})
        if isinstance(details, dict):
            confidence[str(details.get("audit_confidence", "unknown"))] += 1
            influence[str(details.get("value_influence", "unknown"))] += 1
            scope[str(details.get("value_scope", "unknown"))] += 1
            source_type[str(details.get("selected_source_type", "unknown"))] += 1
    return {
        "audit_confidence": dict(sorted(confidence.items())),
        "value_influence": dict(sorted(influence.items())),
        "value_scope": dict(sorted(scope.items())),
        "selected_source_type": dict(sorted(source_type.items())),
    }


def _action_guard_status_counts(runtime: CLCRuntime) -> dict[str, dict[str, int]]:
    effect: Counter[str] = Counter()
    severity: Counter[str] = Counter()
    for audit in runtime.memory.action_guard_audits:
        details = audit.get("summary", {})
        if isinstance(details, dict):
            effect[str(details.get("guard_effect", "unknown"))] += 1
            severity[str(details.get("severity", "unknown"))] += 1
    return {
        "guard_effect": dict(sorted(effect.items())),
        "severity": dict(sorted(severity.items())),
    }


def _decision_cycle_summary_status_counts(runtime: CLCRuntime) -> dict[str, dict[str, int]]:
    status: Counter[str] = Counter()
    confidence: Counter[str] = Counter()
    flags: Counter[str] = Counter()
    for summary in runtime.memory.decision_cycle_summaries:
        cycle = summary.get("cycle_summary", {})
        if isinstance(cycle, dict):
            status[str(cycle.get("cycle_status", "unknown"))] += 1
            confidence[str(cycle.get("cycle_confidence", "unknown"))] += 1
            raw_flags = cycle.get("flags", ())
            if isinstance(raw_flags, (list, tuple)):
                flags.update(str(flag) for flag in raw_flags)
    return {
        "cycle_status": dict(sorted(status.items())),
        "cycle_confidence": dict(sorted(confidence.items())),
        "flags": dict(sorted(flags.items())),
    }


def _single_count(value: str | None) -> dict[str, int]:
    if not value:
        return {}
    return {str(value): 1}


def _retention_summary(runtime: CLCRuntime) -> dict[str, Any]:
    result = runtime.memory.last_context_retention_result
    side_result = runtime.memory.last_side_list_retention_result
    return {
        "context": {
            "enabled": result.enabled if result is not None else None,
            "before": result.before_count if result is not None else None,
            "after": result.after_count if result is not None else None,
            "pruned": result.pruned_count if result is not None else None,
            "oldest_tick": result.oldest_remaining_tick if result is not None else None,
            "newest_tick": result.newest_remaining_tick if result is not None else None,
        },
        "side_lists": {
            "enabled": side_result.enabled if side_result is not None else None,
            "total_before": side_result.total_before if side_result is not None else None,
            "total_after": side_result.total_after if side_result is not None else None,
            "total_pruned": side_result.total_pruned if side_result is not None else None,
        },
    }


def _side_list_counts(runtime: CLCRuntime) -> dict[str, int]:
    names = (
        "decisions",
        "decision_audits",
        "action_guard_audits",
        "decision_cycle_summaries",
        "expsm_mechanism_searches",
        "target_satisfaction_observations",
        "value_feedback_candidates",
        "value_feedback_reviews",
    )
    return {name: len(getattr(runtime.memory, name)) for name in names}


def _stable_source(value: object) -> str:
    text = str(value or "")
    return text if text else "unknown"


def _round_or_none(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(float(value), 3)


def _synthetic_policy_pressure(runtime: CLCRuntime, item: ScenarioInput) -> PolicyPressure | None:
    payload = dict(item.payload)
    if payload.get("policy_pressure") is None:
        return None
    pressure = payload.get("policy_pressure", payload)
    if not isinstance(pressure, dict):
        return None
    pressure_type = str(pressure.get("pressure_type", "no_policy_pressure"))
    active = bool(pressure.get("active", pressure_type not in {"no_policy_pressure", "stability_pressure"}))
    severity = str(pressure.get("severity", "info"))
    confidence = float(pressure.get("confidence", 0.0))
    source_review_status = str(pressure.get("source_review_status", "synthetic_policy_pressure"))
    source_primary_issue = str(pressure.get("source_primary_issue", "none"))
    recommended_future_operation = str(
        pressure.get(
            "recommended_future_operation",
            _default_policy_pressure_future_operation(pressure_type),
        )
    )
    return PolicyPressure(
        pressure_id=str(pressure.get("pressure_id", runtime.id_gen.next("policy_pressure"))),
        tick=item.tick,
        active=active,
        pressure_type=pressure_type,
        severity=severity,
        confidence=confidence,
        source_review_status=source_review_status,
        source_primary_issue=source_primary_issue,
        recommended_future_operation=recommended_future_operation,
        apply_now=False,
        evidence={},
        tags=("policy_pressure", pressure_type, "scenario_synthetic"),
    )


def _default_policy_pressure_future_operation(pressure_type: str) -> str:
    return {
        "no_policy_pressure": "collect_initial_decision_history",
        "stability_pressure": "maintain_current_policy",
        "evidence_pressure": "collect_more_evidence",
        "uncertainty_pressure": "inspect_candidate_discrimination",
        "guard_pressure": "inspect_guard_policy_tension",
        "value_signal_pressure": "inspect_value_signal_coverage",
        "mixed_policy_pressure": "review_mixed_history",
    }.get(pressure_type, "review_mixed_history")


def _real_memory_hashes() -> dict[str, str | None]:
    return {
        "expsm": _hash_file(REAL_MEMORY_ROOT / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(REAL_MEMORY_ROOT / "AKBSM" / "AKBSM_ne.json"),
        "semantic_core": _hash_file(REAL_MEMORY_ROOT / "AKBSM" / "DB" / "semantic_core.json"),
        "technical_feedback": _hash_file(REAL_MEMORY_ROOT / "AKBSM" / "DB" / "technical_feedback_patterns.json"),
    }


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
