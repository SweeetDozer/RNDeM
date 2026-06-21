from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable

from clc.core.pattern_registry import PatternRegistry


DEFAULT_EXPSM_PATH = Path("Memory") / "ExpSM" / "ExpSM_data.json"


@dataclass
class ValueFeedbackRecordView:
    experience_id: str

    positive_count: int = 0
    negative_count: int = 0
    mixed_count: int = 0
    inconclusive_count: int = 0

    positive_strength_total: float = 0.0
    negative_strength_total: float = 0.0
    mixed_strength_total: float = 0.0

    positive_avg_strength: float = 0.0
    negative_avg_strength: float = 0.0
    mixed_avg_strength: float = 0.0

    value_balance: float = 0.0
    value_confidence: float = 0.0
    value_risk: float = 0.0

    linked_target_count: int = 0
    linked_target_patterns: list[str] = field(default_factory=list)
    target_kinds: list[str] = field(default_factory=list)
    target_roles: list[str] = field(default_factory=list)
    target_links: list[dict[str, Any]] = field(default_factory=list)

    last_review_id: str | None = None
    last_updated_tick: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "mixed_count": self.mixed_count,
            "inconclusive_count": self.inconclusive_count,
            "positive_strength_total": self.positive_strength_total,
            "negative_strength_total": self.negative_strength_total,
            "mixed_strength_total": self.mixed_strength_total,
            "positive_avg_strength": self.positive_avg_strength,
            "negative_avg_strength": self.negative_avg_strength,
            "mixed_avg_strength": self.mixed_avg_strength,
            "value_balance": self.value_balance,
            "value_confidence": self.value_confidence,
            "value_risk": self.value_risk,
            "linked_target_count": self.linked_target_count,
            "linked_target_patterns": list(self.linked_target_patterns),
            "target_kinds": list(self.target_kinds),
            "target_roles": list(self.target_roles),
            "target_links": [dict(link) for link in self.target_links],
            "last_review_id": self.last_review_id,
            "last_updated_tick": self.last_updated_tick,
        }


@dataclass
class ValueFeedbackTargetMatch:
    experience_id: str
    target_pattern_id: str | None = None

    match_kind: str = "unknown"
    match_score: float = 0.0
    value_direction: str | None = None

    value_balance: float = 0.0
    value_confidence: float = 0.0
    value_risk: float = 0.0

    positive_count: int = 0
    negative_count: int = 0
    positive_avg_strength: float = 0.0
    negative_avg_strength: float = 0.0

    matched_target_patterns: list[str] = field(default_factory=list)
    matched_target_kinds: list[str] = field(default_factory=list)
    matched_target_roles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "target_pattern_id": self.target_pattern_id,
            "match_kind": self.match_kind,
            "match_score": self.match_score,
            "value_direction": self.value_direction,
            "value_balance": self.value_balance,
            "value_confidence": self.value_confidence,
            "value_risk": self.value_risk,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "positive_avg_strength": self.positive_avg_strength,
            "negative_avg_strength": self.negative_avg_strength,
            "matched_target_patterns": list(self.matched_target_patterns),
            "matched_target_kinds": list(self.matched_target_kinds),
            "matched_target_roles": list(self.matched_target_roles),
        }


class ValueFeedbackMemoryView:
    """Read-only runtime overview of ExpSM value_feedback metadata."""

    def __init__(
        self,
        pattern_registry: PatternRegistry,
        expsm_path: str | Path = DEFAULT_EXPSM_PATH,
    ) -> None:
        self.pattern_registry = pattern_registry
        self.expsm_path = Path(expsm_path)
        self._records: dict[str, ValueFeedbackRecordView] = {}
        self._records_with_value_feedback = 0
        self.warnings: list[str] = []
        self.refresh()

    def refresh(self) -> None:
        self.warnings = []
        self._records = {}
        self._records_with_value_feedback = 0
        store = self._load_store()
        experiences = store.get("experience", {})
        if not isinstance(experiences, dict):
            return
        for experience_id, record in experiences.items():
            if not isinstance(record, dict) or _is_archived(record):
                continue
            has_value_feedback = isinstance(record.get("value_feedback"), dict)
            if has_value_feedback:
                self._records_with_value_feedback += 1
            self._records[str(experience_id)] = _build_record_view(str(experience_id), record)

    def get(self, experience_id: str) -> ValueFeedbackRecordView | None:
        return self._records.get(str(experience_id))

    def top_positive(self, n: int = 10) -> list[ValueFeedbackRecordView]:
        return sorted(
            self._records.values(),
            key=lambda record: (record.value_balance, record.positive_avg_strength, record.positive_count),
            reverse=True,
        )[:n]

    def top_negative(self, n: int = 10) -> list[ValueFeedbackRecordView]:
        return sorted(
            self._records.values(),
            key=lambda record: (record.value_risk, record.negative_avg_strength, record.negative_count),
            reverse=True,
        )[:n]

    def top_balanced(self, n: int = 10) -> list[ValueFeedbackRecordView]:
        return sorted(
            self._records.values(),
            key=lambda record: (record.value_confidence, -abs(record.value_balance)),
            reverse=True,
        )[:n]

    def find_by_target_pattern(
        self,
        target_pattern_id: str,
        *,
        direction: str | None = None,
        limit: int = 10,
    ) -> list[ValueFeedbackTargetMatch]:
        return self.find_by_target_patterns([target_pattern_id], direction=direction, limit=limit)

    def find_by_target_patterns(
        self,
        target_pattern_ids: Iterable[str],
        *,
        direction: str | None = None,
        limit: int = 10,
    ) -> list[ValueFeedbackTargetMatch]:
        direction_key = _normalize_direction(direction)
        matches = [
            match
            for record in self._records.values()
            if (match := _match_record(record, target_pattern_ids, direction_key, None, None)) is not None
        ]
        return _sort_matches(matches, direction_key)[: max(0, limit)]

    def find_risky_for_target(
        self,
        target_pattern_ids: Iterable[str],
        *,
        target_kind: str | None = None,
        target_roles: list[str] | None = None,
        limit: int = 10,
    ) -> list[ValueFeedbackTargetMatch]:
        matches = [
            match
            for record in self._records.values()
            if (match := _match_record(record, target_pattern_ids, "risky", target_kind, target_roles)) is not None
        ]
        return _sort_matches(matches, "risky")[: max(0, limit)]

    def find_helpful_for_target(
        self,
        target_pattern_ids: Iterable[str],
        *,
        target_kind: str | None = None,
        target_roles: list[str] | None = None,
        limit: int = 10,
    ) -> list[ValueFeedbackTargetMatch]:
        matches = [
            match
            for record in self._records.values()
            if (match := _match_record(record, target_pattern_ids, "positive", target_kind, target_roles)) is not None
        ]
        return _sort_matches(matches, "positive")[: max(0, limit)]

    def snapshot(self) -> dict[str, Any]:
        target_index = _target_index(self._records.values())
        return {
            "record_count": len(self._records),
            "records_with_value_feedback": self._records_with_value_feedback,
            "records": [record.to_dict() for record in sorted(self._records.values(), key=lambda item: item.experience_id)],
            "target_index": target_index,
        }

    def _load_store(self) -> dict[str, Any]:
        if not self.expsm_path.exists():
            self.warnings.append(f"ExpSM file missing: {self.expsm_path}")
            return {"experience": {}}
        try:
            data = json.loads(self.expsm_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.warnings.append(f"Could not read value feedback view from {self.expsm_path}: {exc}")
            return {"experience": {}}
        if not isinstance(data, dict):
            self.warnings.append(f"ExpSM file must contain a JSON object: {self.expsm_path}")
            return {"experience": {}}
        return data


def _build_record_view(experience_id: str, record: dict[str, Any]) -> ValueFeedbackRecordView:
    feedback = record.get("value_feedback", {})
    if not isinstance(feedback, dict):
        feedback = {}
    positive_count = _safe_int(feedback.get("positive_count"))
    negative_count = _safe_int(feedback.get("negative_count"))
    mixed_count = _safe_int(feedback.get("mixed_count"))
    inconclusive_count = _safe_int(feedback.get("inconclusive_count"))
    positive_total = _safe_float(feedback.get("positive_strength_total"))
    negative_total = _safe_float(feedback.get("negative_strength_total"))
    mixed_total = _safe_float(feedback.get("mixed_strength_total"))
    value_balance = _clamp_signed(positive_total - negative_total)
    total_count = positive_count + negative_count + mixed_count + inconclusive_count
    negative_avg = negative_total / max(negative_count, 1)
    target_patterns, target_kinds, target_roles, target_links = _target_link_summary(feedback.get("target_links", ()))
    return ValueFeedbackRecordView(
        experience_id=experience_id,
        positive_count=positive_count,
        negative_count=negative_count,
        mixed_count=mixed_count,
        inconclusive_count=inconclusive_count,
        positive_strength_total=round(positive_total, 3),
        negative_strength_total=round(negative_total, 3),
        mixed_strength_total=round(mixed_total, 3),
        positive_avg_strength=round(positive_total / max(positive_count, 1), 3),
        negative_avg_strength=round(negative_avg, 3),
        mixed_avg_strength=round(mixed_total / max(mixed_count, 1), 3),
        value_balance=round(value_balance, 3),
        value_confidence=round(_clamp(min(total_count / 8.0, 1.0) * (0.5 + abs(value_balance) * 0.5)), 3),
        value_risk=round(_clamp(negative_avg * 0.65 + min(negative_count / 5.0, 1.0) * 0.35), 3),
        linked_target_count=len(target_patterns),
        linked_target_patterns=target_patterns,
        target_kinds=target_kinds,
        target_roles=target_roles,
        target_links=target_links,
        last_review_id=_optional_str(feedback.get("last_review_id")),
        last_updated_tick=_optional_int(feedback.get("last_updated_tick")),
    )


def _target_link_summary(target_links: Any) -> tuple[list[str], list[str], list[str], list[dict[str, Any]]]:
    target_patterns: list[str] = []
    target_kinds: list[str] = []
    target_roles: list[str] = []
    normalized_links: list[dict[str, Any]] = []
    if not isinstance(target_links, list):
        return target_patterns, target_kinds, target_roles, normalized_links
    for link in target_links:
        if not isinstance(link, dict):
            continue
        normalized = _normalize_target_link(link)
        if len(normalized_links) < 32:
            normalized_links.append(normalized)
        _append_unique(target_patterns, normalized["target_pattern_id"], 32)
        _append_unique(target_kinds, normalized["target_kind"], 16)
        roles = link.get("target_role_names", ())
        if isinstance(roles, (list, tuple)):
            for role in roles:
                _append_unique(target_roles, str(role), 32)
    return target_patterns, target_kinds, target_roles, normalized_links


def _normalize_target_link(link: dict[str, Any]) -> dict[str, Any]:
    roles = link.get("target_role_names", ())
    if not isinstance(roles, (list, tuple)):
        roles = ()
    return {
        "target_pattern_id": str(link.get("target_pattern_id", "")),
        "target_kind": str(link.get("target_kind", "")),
        "target_role_names": [str(role) for role in roles if role],
        "value_direction": str(link.get("value_direction", "")),
        "candidate_strength": round(_safe_float(link.get("candidate_strength")), 3),
        "evidence_strength": round(_safe_float(link.get("evidence_strength")), 3),
        "satisfaction_status": str(link.get("satisfaction_status", "")),
        "recommended_future_operation": str(link.get("recommended_future_operation", "")),
    }


def _match_record(
    record: ValueFeedbackRecordView,
    target_pattern_ids: Iterable[str],
    direction: str,
    target_kind: str | None,
    target_roles: list[str] | None,
) -> ValueFeedbackTargetMatch | None:
    requested_ids = {str(pattern_id) for pattern_id in target_pattern_ids if pattern_id}
    requested_roles = [str(role) for role in (target_roles or []) if role]
    best: ValueFeedbackTargetMatch | None = None
    for link in record.target_links:
        relevance, exact, kind_match, role_overlap = _target_relevance(link, requested_ids, target_kind, requested_roles)
        if relevance <= 0.0:
            continue
        if not exact and target_kind is None and not requested_roles:
            continue
        helpful_score = _helpful_score(record, relevance)
        risky_score = _risky_score(record, relevance)
        mixed_score = _mixed_score(record, relevance)
        match = _match_for_direction(record, link, direction, helpful_score, risky_score, mixed_score)
        if match is None:
            continue
        match.matched_target_patterns = [link["target_pattern_id"]] if exact else []
        match.matched_target_kinds = [link["target_kind"]] if kind_match else []
        match.matched_target_roles = _matched_roles(link.get("target_role_names", []), requested_roles) if role_overlap > 0.0 else []
        if best is None or match.match_score > best.match_score:
            best = match
    if best is None and direction == "risky" and record.value_risk >= 0.65:
        return _generic_risky_match(record)
    return best


def _target_relevance(
    link: dict[str, Any],
    requested_ids: set[str],
    target_kind: str | None,
    requested_roles: list[str],
) -> tuple[float, bool, bool, float]:
    exact = bool(requested_ids and link.get("target_pattern_id") in requested_ids)
    kind_match = bool(target_kind and link.get("target_kind") == target_kind)
    role_overlap = _jaccard(link.get("target_role_names", []), requested_roles)
    relevance = exact * 0.65 + kind_match * 0.15 + role_overlap * 0.20
    return _clamp(relevance), exact, kind_match, role_overlap


def _match_for_direction(
    record: ValueFeedbackRecordView,
    link: dict[str, Any],
    direction: str,
    helpful_score: float,
    risky_score: float,
    mixed_score: float,
) -> ValueFeedbackTargetMatch | None:
    link_direction = str(link.get("value_direction", ""))
    if direction == "positive":
        if record.positive_count <= 0 and link_direction != "positive":
            return None
        return _target_match(record, link, "positive_target_match", helpful_score, "positive")
    if direction == "negative":
        if record.negative_count <= 0 and link_direction != "negative":
            return None
        return _target_match(record, link, "negative_target_match", risky_score, "negative")
    if direction == "risky":
        if record.value_risk <= 0.0 and record.negative_count <= 0:
            return None
        return _target_match(record, link, "risky_target_match", risky_score, "negative")
    if direction == "mixed":
        if record.mixed_count <= 0 and link_direction not in {"mixed", "mixed_or_unclear"}:
            return None
        return _target_match(record, link, "mixed_target_match", mixed_score, "mixed")
    score = max(helpful_score, risky_score, mixed_score)
    if score <= 0.0:
        return None
    if score == risky_score and (record.negative_count > 0 or record.value_risk > 0.0):
        return _target_match(record, link, "risky_target_match", score, "negative")
    if score == helpful_score and record.positive_count > 0:
        return _target_match(record, link, "positive_target_match", score, "positive")
    return _target_match(record, link, "mixed_target_match", score, "mixed")


def _target_match(
    record: ValueFeedbackRecordView,
    link: dict[str, Any],
    match_kind: str,
    match_score: float,
    value_direction: str,
) -> ValueFeedbackTargetMatch:
    return ValueFeedbackTargetMatch(
        experience_id=record.experience_id,
        target_pattern_id=link.get("target_pattern_id") or None,
        match_kind=match_kind,
        match_score=round(match_score, 3),
        value_direction=value_direction,
        value_balance=record.value_balance,
        value_confidence=record.value_confidence,
        value_risk=record.value_risk,
        positive_count=record.positive_count,
        negative_count=record.negative_count,
        positive_avg_strength=record.positive_avg_strength,
        negative_avg_strength=record.negative_avg_strength,
    )


def _generic_risky_match(record: ValueFeedbackRecordView) -> ValueFeedbackTargetMatch:
    score = _clamp(record.value_risk * 0.30 + max(-record.value_balance, 0.0) * 0.20 + record.negative_avg_strength * 0.15)
    return ValueFeedbackTargetMatch(
        experience_id=record.experience_id,
        match_kind="risky_target_match",
        match_score=round(score, 3),
        value_direction="negative",
        value_balance=record.value_balance,
        value_confidence=record.value_confidence,
        value_risk=record.value_risk,
        positive_count=record.positive_count,
        negative_count=record.negative_count,
        positive_avg_strength=record.positive_avg_strength,
        negative_avg_strength=record.negative_avg_strength,
    )


def _helpful_score(record: ValueFeedbackRecordView, relevance: float) -> float:
    return _clamp(
        relevance * 0.45
        + max(record.value_balance, 0.0) * 0.25
        + record.value_confidence * 0.15
        + record.positive_avg_strength * 0.15
    )


def _risky_score(record: ValueFeedbackRecordView, relevance: float) -> float:
    return _clamp(
        relevance * 0.35
        + record.value_risk * 0.30
        + max(-record.value_balance, 0.0) * 0.20
        + record.negative_avg_strength * 0.15
    )


def _mixed_score(record: ValueFeedbackRecordView, relevance: float) -> float:
    return _clamp(
        relevance * 0.40
        + (1.0 - abs(record.value_balance)) * 0.20
        + record.value_confidence * 0.20
        + record.mixed_avg_strength * 0.20
    )


def _sort_matches(matches: list[ValueFeedbackTargetMatch], direction: str) -> list[ValueFeedbackTargetMatch]:
    return sorted(matches, key=lambda match: match.match_score, reverse=True)


def _normalize_direction(direction: str | None) -> str:
    if direction in {"positive", "negative", "mixed", "risky", "any"}:
        return str(direction)
    return "any"


def _matched_roles(link_roles: list[str], requested_roles: list[str]) -> list[str]:
    requested = set(requested_roles)
    return [role for role in link_roles if role in requested]


def _jaccard(values: Iterable[str], target: Iterable[str]) -> float:
    source = {str(value) for value in values if value}
    target_set = {str(value) for value in target if value}
    if not source or not target_set:
        return 0.0
    return len(source & target_set) / len(source | target_set)


def _target_index(records: Iterable[ValueFeedbackRecordView]) -> dict[str, dict[str, list[str]]]:
    index: dict[str, dict[str, list[str]]] = {}
    for record in records:
        for link in record.target_links:
            target_id = str(link.get("target_pattern_id", ""))
            if not target_id:
                continue
            bucket = index.setdefault(target_id, {"positive_experience_ids": [], "negative_experience_ids": [], "mixed_experience_ids": []})
            direction = str(link.get("value_direction", ""))
            if direction == "positive" and record.experience_id not in bucket["positive_experience_ids"]:
                bucket["positive_experience_ids"].append(record.experience_id)
            elif direction == "negative" and record.experience_id not in bucket["negative_experience_ids"]:
                bucket["negative_experience_ids"].append(record.experience_id)
            elif record.experience_id not in bucket["mixed_experience_ids"]:
                bucket["mixed_experience_ids"].append(record.experience_id)
    return dict(list(index.items())[:32])


def _append_unique(values: list[str], value: str, limit: int) -> None:
    if not value or value in values or len(values) >= limit:
        return
    values.append(value)


def _is_archived(record: dict[str, Any]) -> bool:
    return bool(record.get("archived")) or str(record.get("status", "")).lower() == "archived"


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))
