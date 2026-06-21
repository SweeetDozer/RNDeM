from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.context.context_retention_policy import SIDE_LIST_NAMES


RECENT_EVENT_WINDOW = 200
LOW_PRESSURE_LIMIT = 500
MEDIUM_PRESSURE_LIMIT = 2000
@dataclass(frozen=True)
class RetentionMetrics:
    tick: int
    context_event_count: int | None
    raw_frame_count: int | None
    window_count: int | None
    active_pattern_count: int | None
    action_candidate_count: int | None
    evaluation_entry_count: int | None
    akbsm_association_entry_count: int | None
    experience_candidate_group_count: int | None
    experience_candidate_total_count: int | None
    draft_total_count: int | None
    draft_status_counts: dict[str, int] = field(default_factory=dict)
    recent_marker_counts: dict[int | str, int] = field(default_factory=dict)
    retention_enabled: bool | None = None
    retention_max_events: int | None = None
    last_retention_pruned_count: int | None = None
    last_retention_before_count: int | None = None
    last_retention_after_count: int | None = None
    oldest_event_tick: int | None = None
    newest_event_tick: int | None = None
    side_list_counts: dict[str, int] = field(default_factory=dict)
    side_list_oldest_ticks: dict[str, int | None] = field(default_factory=dict)
    side_list_newest_ticks: dict[str, int | None] = field(default_factory=dict)
    side_list_stale_counts: dict[str, int | None] = field(default_factory=dict)
    side_list_warnings: list[str] = field(default_factory=list)
    side_list_retention_enabled: bool | None = None
    side_list_retention_total_before: int | None = None
    side_list_retention_total_after: int | None = None
    side_list_retention_total_pruned: int | None = None
    side_list_retention_per_list: dict[str, dict[str, int | None]] = field(default_factory=dict)
    side_list_retention_warnings: list[str] = field(default_factory=list)
    estimated_pressure: str = "unknown"
    warnings: list[str] = field(default_factory=list)


class RetentionDiagnostics:
    """Read-only counters for runtime retention/growth audit output."""

    def __init__(self, draft_store_path: str | Path | None = None) -> None:
        self.draft_store_path = Path(draft_store_path) if draft_store_path is not None else None

    def collect(
        self,
        *,
        tick: int,
        memory: ContextMemory | None = None,
        active_field: object | None = None,
        action_candidate_field: object | None = None,
        evaluation_field: object | None = None,
        akbsm_association_field: object | None = None,
        experience_candidate_buffer: object | None = None,
        draft_store_path: str | Path | None = None,
    ) -> RetentionMetrics:
        warnings: list[str] = []
        context_event_count = _count_sequence(memory, "events", warnings, "context events")
        raw_frame_count = _count_sequence(memory, "raw_frames", warnings, "raw frames")
        window_count = _count_sequence(memory, "windows", warnings, "context windows")
        draft_total_count, draft_status_counts = self._draft_counts(draft_store_path, warnings)
        retention = getattr(memory, "last_context_retention_result", None) if memory is not None else None
        side_retention = getattr(memory, "last_side_list_retention_result", None) if memory is not None else None
        oldest_event_tick, newest_event_tick = _event_tick_bounds(memory, warnings)
        side_lists = _side_list_metrics(memory, oldest_event_tick)
        return RetentionMetrics(
            tick=tick,
            context_event_count=context_event_count,
            raw_frame_count=raw_frame_count,
            window_count=window_count,
            active_pattern_count=_count_mapping(active_field, "_patterns", warnings, "active patterns"),
            action_candidate_count=_count_mapping(action_candidate_field, "_candidates", warnings, "action candidates"),
            evaluation_entry_count=_count_mapping(evaluation_field, "_entries", warnings, "evaluation entries"),
            akbsm_association_entry_count=_count_mapping(akbsm_association_field, "_entries", warnings, "AKBSM association entries"),
            experience_candidate_group_count=_candidate_group_count(experience_candidate_buffer, warnings),
            experience_candidate_total_count=_candidate_total_count(experience_candidate_buffer, warnings),
            draft_total_count=draft_total_count,
            draft_status_counts=draft_status_counts,
            recent_marker_counts=_recent_marker_counts(memory, warnings),
            retention_enabled=getattr(retention, "enabled", None),
            retention_max_events=getattr(retention, "max_events", None),
            last_retention_pruned_count=getattr(retention, "pruned_count", None),
            last_retention_before_count=getattr(retention, "before_count", None),
            last_retention_after_count=getattr(retention, "after_count", None),
            oldest_event_tick=oldest_event_tick,
            newest_event_tick=newest_event_tick,
            side_list_counts=side_lists["counts"],
            side_list_oldest_ticks=side_lists["oldest"],
            side_list_newest_ticks=side_lists["newest"],
            side_list_stale_counts=side_lists["stale"],
            side_list_warnings=side_lists["warnings"],
            side_list_retention_enabled=getattr(side_retention, "enabled", None),
            side_list_retention_total_before=getattr(side_retention, "total_before", None),
            side_list_retention_total_after=getattr(side_retention, "total_after", None),
            side_list_retention_total_pruned=getattr(side_retention, "total_pruned", None),
            side_list_retention_per_list=getattr(side_retention, "per_list", {}) or {},
            side_list_retention_warnings=getattr(side_retention, "warnings", []) or [],
            estimated_pressure=_pressure(context_event_count),
            warnings=warnings,
        )

    def _draft_counts(
        self,
        draft_store_path: str | Path | None,
        warnings: list[str],
    ) -> tuple[int | None, dict[str, int]]:
        path = Path(draft_store_path) if draft_store_path is not None else self.draft_store_path
        if path is None:
            warnings.append("draft store path is not available")
            return None, {}
        if not path.exists():
            return 0, {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                store = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"draft store could not be read: {exc}")
            return None, {}
        drafts = store.get("drafts") if isinstance(store, dict) else None
        if not isinstance(drafts, list):
            warnings.append("draft store does not expose a drafts list")
            return None, {}
        statuses = Counter(
            str(draft.get("draft_status") or draft.get("status") or "unknown")
            for draft in drafts
            if isinstance(draft, dict)
        )
        return len([draft for draft in drafts if isinstance(draft, dict)]), dict(sorted(statuses.items()))


def format_retention_metrics(metrics: RetentionMetrics) -> list[str]:
    statuses = _format_statuses(metrics.draft_status_counts)
    lines = [
        "retention diagnostics:",
        f"  context_events={_display(metrics.context_event_count)} raw_frames={_display(metrics.raw_frame_count)} windows={_display(metrics.window_count)}",
        f"  active_patterns={_display(metrics.active_pattern_count)}",
        f"  action_candidates={_display(metrics.action_candidate_count)}",
        f"  evaluation_entries={_display(metrics.evaluation_entry_count)}",
        f"  akbsm_associations={_display(metrics.akbsm_association_entry_count)}",
        (
            "  candidate_groups="
            f"{_display(metrics.experience_candidate_group_count)} "
            f"total_candidates={_display(metrics.experience_candidate_total_count)}"
        ),
        f"  drafts={_display(metrics.draft_total_count)} statuses={statuses}",
        (
            "  retention="
            f"enabled={_display_bool(metrics.retention_enabled)} "
            f"max_events={_display(metrics.retention_max_events)} "
            f"before={_display(metrics.last_retention_before_count)} "
            f"after={_display(metrics.last_retention_after_count)} "
            f"pruned={_display(metrics.last_retention_pruned_count)}"
        ),
        f"  recent_markers={_format_statuses(metrics.recent_marker_counts)}",
        f"  pressure={metrics.estimated_pressure}",
    ]
    if metrics.warnings:
        lines.append(f"  warnings={'; '.join(metrics.warnings)}")
    return lines


def format_side_list_retention_metrics(metrics: RetentionMetrics, limit: int = 12) -> list[str]:
    rows = []
    for name, count in metrics.side_list_counts.items():
        stale = metrics.side_list_stale_counts.get(name)
        if count <= 0 and not stale:
            continue
        rows.append((name, count, stale if stale is not None else -1))
    rows.sort(key=lambda item: (item[2], item[1], item[0]), reverse=True)
    lines = ["side-list retention diagnostics:"]
    if metrics.side_list_retention_enabled is not None:
        lines.append(
            "  retention="
            f"enabled={_display_bool(metrics.side_list_retention_enabled)} "
            f"total_before={_display(metrics.side_list_retention_total_before)} "
            f"total_after={_display(metrics.side_list_retention_total_after)} "
            f"pruned={_display(metrics.side_list_retention_total_pruned)}"
        )
        pruned_items = [
            (name, item)
            for name, item in metrics.side_list_retention_per_list.items()
            if int(item.get("pruned_by_tick") or 0) or int(item.get("pruned_by_max_entries") or 0)
        ]
        for name, item in pruned_items[:4]:
            lines.append(
                f"  retention {name} before={_display(item.get('before'))} after={_display(item.get('after'))} "
                f"pruned_by_tick={_display(item.get('pruned_by_tick'))} "
                f"pruned_by_max={_display(item.get('pruned_by_max_entries'))}"
            )
    if not rows:
        if metrics.side_list_retention_enabled is None:
            lines.append("  none")
    else:
        for name, count, _stale_sort in rows[:limit]:
            lines.append(
                f"  {name} count={count} "
                f"oldest={_display(metrics.side_list_oldest_ticks.get(name))} "
                f"newest={_display(metrics.side_list_newest_ticks.get(name))} "
                f"stale={_display(metrics.side_list_stale_counts.get(name))}"
            )
    if metrics.side_list_warnings:
        lines.append(f"  warnings={'; '.join(metrics.side_list_warnings[:6])}")
    if metrics.side_list_retention_warnings:
        lines.append(f"  retention_warnings={'; '.join(metrics.side_list_retention_warnings[:6])}")
    return lines


def _count_sequence(obj: object | None, attr: str, warnings: list[str], label: str) -> int | None:
    if obj is None or not hasattr(obj, attr):
        _warn(warnings, f"{label} are not available")
        return None
    value = getattr(obj, attr)
    if not hasattr(value, "__len__"):
        _warn(warnings, f"{label} are not countable")
        return None
    return len(value)


def _count_mapping(obj: object | None, attr: str, warnings: list[str], label: str) -> int | None:
    return _count_sequence(obj, attr, warnings, label)


def _candidate_groups(buffer: object | None, warnings: list[str]) -> list[object] | None:
    if buffer is None or not hasattr(buffer, "_groups_by_signature"):
        _warn(warnings, "experience candidate buffer groups are not available")
        return None
    groups = getattr(buffer, "_groups_by_signature")
    if not hasattr(groups, "values"):
        _warn(warnings, "experience candidate buffer groups are not a mapping")
        return None
    return list(groups.values())


def _candidate_group_count(buffer: object | None, warnings: list[str]) -> int | None:
    groups = _candidate_groups(buffer, warnings)
    if groups is None:
        return None
    return len(groups)


def _candidate_total_count(buffer: object | None, warnings: list[str]) -> int | None:
    groups = _candidate_groups(buffer, warnings)
    if groups is None:
        return None
    total = 0
    for group in groups:
        candidate_ids = getattr(group, "candidate_ids", None)
        if not hasattr(candidate_ids, "__len__"):
            _warn(warnings, "experience candidate group candidate_ids are not countable")
            return None
        total += len(candidate_ids)
    return total


def _recent_marker_counts(memory: ContextMemory | None, warnings: list[str]) -> dict[int | str, int]:
    if memory is None or not hasattr(memory, "events"):
        _warn(warnings, "recent marker counts are not available")
        return {}
    events = getattr(memory, "events")
    if not isinstance(events, list):
        _warn(warnings, "recent marker counts source is not a list")
        return {}
    counts: Counter[int | str] = Counter()
    for event in events[-RECENT_EVENT_WINDOW:]:
        marker = getattr(event, "marker", None)
        marker_value = getattr(marker, "value", None)
        counts[marker_value if marker_value is not None else str(marker)] += 1
    return dict(sorted(counts.items(), key=lambda item: str(item[0])))


def _event_tick_bounds(memory: ContextMemory | None, warnings: list[str]) -> tuple[int | None, int | None]:
    if memory is None or not hasattr(memory, "events"):
        _warn(warnings, "event tick bounds are not available")
        return None, None
    events = getattr(memory, "events")
    if not isinstance(events, list) or not events:
        return None, None
    ticks = [getattr(event, "tick", None) for event in events]
    known_ticks = [tick for tick in ticks if isinstance(tick, int)]
    if len(known_ticks) != len(events):
        _warn(warnings, "some events do not expose integer ticks")
    if not known_ticks:
        return None, None
    return min(known_ticks), max(known_ticks)


def _side_list_metrics(memory: ContextMemory | None, oldest_event_tick: int | None) -> dict[str, Any]:
    counts: dict[str, int] = {}
    oldest: dict[str, int | None] = {}
    newest: dict[str, int | None] = {}
    stale: dict[str, int | None] = {}
    warnings: list[str] = []
    if memory is None:
        return {"counts": counts, "oldest": oldest, "newest": newest, "stale": stale, "warnings": ["ContextMemory is not available"]}
    for name in SIDE_LIST_NAMES:
        if not hasattr(memory, name):
            warnings.append(f"{name} side list is not available")
            continue
        value = getattr(memory, name)
        if not isinstance(value, list):
            warnings.append(f"{name} side list is not a list")
            continue
        counts[name] = len(value)
        entry_bounds = [_entry_tick_bounds(entry) for entry in value]
        known_bounds = [bounds for bounds in entry_bounds if bounds[0] is not None and bounds[1] is not None]
        unknown_count = len(entry_bounds) - len(known_bounds)
        oldest[name] = min(bounds[0] for bounds in known_bounds) if known_bounds else None
        newest[name] = max(bounds[1] for bounds in known_bounds) if known_bounds else None
        if unknown_count:
            warnings.append(f"{name} has {unknown_count} entries without diagnostic ticks")
            stale[name] = None
        elif oldest_event_tick is None:
            stale[name] = None
        else:
            stale[name] = sum(1 for oldest_tick, _newest_tick in known_bounds if oldest_tick is not None and oldest_tick < oldest_event_tick)
    return {"counts": counts, "oldest": oldest, "newest": newest, "stale": stale, "warnings": warnings}


def _entry_tick_bounds(entry: object) -> tuple[int | None, int | None]:
    if isinstance(entry, Mapping):
        from_tick = entry.get("from_tick")
        to_tick = entry.get("to_tick")
        if isinstance(from_tick, int) and isinstance(to_tick, int):
            return from_tick, to_tick
        for key in ("_event_tick", "tick", "from_tick"):
            value = entry.get(key)
            if isinstance(value, int):
                return value, value
        return None, None
    value = getattr(entry, "tick", None)
    if isinstance(value, int):
        return value, value
    from_tick = getattr(entry, "from_tick", None)
    to_tick = getattr(entry, "to_tick", None)
    if isinstance(from_tick, int) and isinstance(to_tick, int):
        return from_tick, to_tick
    if isinstance(from_tick, int):
        return from_tick, from_tick
    return None, None


def _pressure(context_event_count: int | None) -> str:
    if context_event_count is None:
        return "unknown"
    if context_event_count < LOW_PRESSURE_LIMIT:
        return "low"
    if context_event_count < MEDIUM_PRESSURE_LIMIT:
        return "medium"
    return "high"


def _format_statuses(values: dict[int | str, int]) -> str:
    if not values:
        return "{}"
    return "{" + ", ".join(f"{key}:{value}" for key, value in values.items()) + "}"


def _display(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def _display_bool(value: bool | None) -> str:
    return "unknown" if value is None else str(value).lower()


def _warn(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)
