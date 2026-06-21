import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from clc.context.window import ContextWindow
from clc.core.nfp import NFPFrame
from clc.core.pattern_registry import PatternRegistry
from clc.storage_models.pattern_store import PatternStore
from clc.storage_models.schemas import ExperienceMatch


class ExpSMAdapter:
    """Read-only adapter for experience/reflex records."""

    def __init__(self, data_path: Path, pattern_store: PatternStore, pattern_registry: PatternRegistry | None = None) -> None:
        self.data_path = data_path
        self.pattern_store = pattern_store
        self.pattern_registry = pattern_registry
        self.experiences: dict[str, dict[str, Any]] = {}
        self.reflexes: dict[str, dict[str, Any]] = {}
        self.warnings: list[str] = []
        self.reload_count = 0
        self.last_reload_tick: int | None = None
        self._warned_placeholders: set[str] = set()
        self.load()
        self._install_demo_fallback_records_if_needed()

    def reload(self, tick: int | None = None) -> None:
        self.experiences = {}
        self.reflexes = {}
        self.warnings = []
        self.load()
        self._install_demo_fallback_records_if_needed()
        self.reload_count += 1
        self.last_reload_tick = tick

    def load(self) -> None:
        if not self.data_path.exists():
            self.warnings.append(f"ExpSM data not found: {self.data_path}")
            return
        try:
            data = json.loads(self.data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.warnings.append(f"Could not load ExpSM data: {exc}")
            return
        if not isinstance(data, Mapping):
            self.warnings.append("ExpSM data has unsupported shape")
            return
        self.experiences = _record_map(data.get("experience", data.get("experiences", {})))
        self.reflexes = _record_map(data.get("reflexes", data.get("reflex", {})))
        self._scan_placeholders("experience", self.experiences)
        self._scan_placeholders("reflex", self.reflexes)

    def _install_demo_fallback_records_if_needed(self) -> None:
        pattern_ids = self.pattern_store.list_patterns()
        if not pattern_ids:
            return
        if not any(
            not _is_archived(record) and self._resolvable_refs(record.get("if", []), record_id)
            for record_id, record in self.experiences.items()
        ):
            target = pattern_ids[min(1, len(pattern_ids) - 1)]
            recommendation = self.pattern_registry.id("thought_increase_attention") if self.pattern_registry else target
            self.experiences["demo_experience_memory_match"] = {
                "if": [target],
                "then": [target],
                "result": [target],
                "recommendation": [recommendation],
                "confidence": 0.72,
                "priority": 0.55,
                "source": "demo_fallback",
                "status": "active",
            }
            self.warnings.append("Installed in-memory demo ExpSM experience fallback")
        if not any(
            not _is_archived(record) and self._resolvable_refs(record.get("if", []), record_id)
            for record_id, record in self.reflexes.items()
        ):
            target = pattern_ids[0]
            preserve = self.pattern_registry.id("thought_preserve_integrity") if self.pattern_registry else target
            reduce_load = self.pattern_registry.id("thought_reduce_load") if self.pattern_registry else target
            self.reflexes["demo_reflex_memory_match"] = {
                "if": [target],
                "then": [preserve],
                "result": [],
                "recommendation": [reduce_load],
                "confidence": 0.82,
                "priority": 1.0,
                "source": "demo_fallback",
                "status": "active",
            }
            self.warnings.append("Installed in-memory demo ExpSM reflex fallback")

    def list_experiences(self) -> list[dict[str, Any]]:
        return [dict(record, record_id=record_id) for record_id, record in self.experiences.items()]

    def list_reflexes(self) -> list[dict[str, Any]]:
        return [dict(record, record_id=record_id) for record_id, record in self.reflexes.items()]

    def match_experiences(self, frame_or_window: NFPFrame | ContextWindow, context_memory: Any = None, threshold: float = 0.4) -> list[ExperienceMatch]:
        return self._match_records("experience", self.experiences, frame_or_window, context_memory, threshold)

    def match_reflexes(self, frame_or_window: NFPFrame | ContextWindow, context_memory: Any = None, threshold: float = 0.4) -> list[ExperienceMatch]:
        return self._match_records("reflex", self.reflexes, frame_or_window, context_memory, threshold)

    def consume_warnings(self) -> list[str]:
        warnings = list(self.warnings)
        self.warnings.clear()
        return warnings

    def _match_records(self, record_type: str, records: dict[str, dict[str, Any]], frame_or_window: NFPFrame | ContextWindow, context_memory: Any, threshold: float) -> list[ExperienceMatch]:
        matches: list[ExperienceMatch] = []
        for record_id, record in records.items():
            if _is_archived(record):
                continue
            input_refs = self._resolvable_refs(record.get("if", []), record_id)
            if not input_refs:
                continue
            similarities = [self._similarity_to_ref(ref, frame_or_window, context_memory) for ref in input_refs]
            similarity = max(similarities) if similarities else 0.0
            confidence = _as_float(record.get("confidence", 0.0))
            score = similarity * confidence
            if score < threshold:
                continue
            priority_base = _as_float(record.get("priority", 0.5))
            priority = min(1.0, priority_base + (0.25 if record_type == "reflex" else 0.0))
            matches.append(
                ExperienceMatch(
                    record_id=str(record_id),
                    record_type=record_type,
                    similarity=round(similarity, 3),
                    confidence=confidence,
                    priority=round(priority, 3),
                    suggested_patterns=self._suggested_patterns(record),
                )
            )
        return sorted(matches, key=lambda match: (match.priority, match.similarity), reverse=True)

    def _similarity_to_ref(self, pattern_ref: str, frame_or_window: NFPFrame | ContextWindow, context_memory: Any) -> float:
        pattern_id = Path(pattern_ref).stem if pattern_ref.endswith(".nfp") else pattern_ref
        if pattern_id not in self.pattern_store.patterns:
            return 0.0
        if isinstance(frame_or_window, ContextWindow):
            if context_memory is None:
                return 0.0
            return self.pattern_store.similarity_to_window(pattern_id, frame_or_window, context_memory)
        return self.pattern_store.similarity_to_frame(pattern_id, frame_or_window)

    def _scan_placeholders(self, record_type: str, records: dict[str, dict[str, Any]]) -> None:
        for record_id, record in records.items():
            if _is_archived(record):
                continue
            for field in ("if", "then", "result", "recommendation"):
                if any(str(ref) == "NFP" for ref in _as_tuple(record.get(field, ()))):
                    warning = f"ExpSM {record_type} record {record_id} contains unresolved placeholder NFP"
                    if warning not in self._warned_placeholders:
                        self._warned_placeholders.add(warning)
                        self.warnings.append(warning)

    def _resolvable_refs(self, refs: Any, record_id: str) -> tuple[str, ...]:
        resolved: list[str] = []
        for ref in _as_tuple(refs):
            ref_text = str(ref)
            if ref_text == "NFP":
                warning = f"ExpSM record {record_id} contains unresolved placeholder NFP"
                if warning not in self._warned_placeholders:
                    self._warned_placeholders.add(warning)
                    self.warnings.append(warning)
                continue
            pattern_id = Path(ref_text).stem if ref_text.endswith(".nfp") else ref_text
            if pattern_id in self.pattern_store.patterns or pattern_id.startswith("pat_"):
                resolved.append(pattern_id)
        return tuple(resolved)

    def _suggested_patterns(self, record: dict[str, Any]) -> tuple[str, ...]:
        suggested: list[str] = []
        for field in ("then", "result", "recommendation"):
            for ref in _as_tuple(record.get(field, ())):
                ref_text = str(ref)
                if ref_text == "NFP":
                    continue
                pattern_id = Path(ref_text).stem if ref_text.endswith(".nfp") else ref_text
                suggested.append(pattern_id)
        return tuple(dict.fromkeys(suggested))


def _record_map(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, Mapping):
        return {str(key): dict(record) for key, record in value.items() if isinstance(record, Mapping)}
    if isinstance(value, list):
        return {str(index): dict(record) for index, record in enumerate(value) if isinstance(record, Mapping)}
    return {}


def _as_tuple(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _as_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _is_archived(record: dict[str, Any]) -> bool:
    return str(record.get("status", "")).lower() in {"archived", "deleted", "tombstone"}
