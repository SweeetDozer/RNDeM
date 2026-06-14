import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from clc.storage_models.schemas import PatternMatch, RelatedPattern


class AKBSMAdapter:
    """Read-only adapter for the AKBSM associative graph."""

    def __init__(self, edge_path: Path) -> None:
        self.edge_path = edge_path
        self.edges: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.load()

    def load(self) -> None:
        if not self.edge_path.exists():
            self.warnings.append(f"AKBSM edges not found: {self.edge_path}")
            return
        try:
            data = json.loads(self.edge_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.warnings.append(f"Could not load AKBSM edges: {exc}")
            return
        edge_data = data.get("edges", data) if isinstance(data, Mapping) else data
        if isinstance(edge_data, Mapping):
            iterable = edge_data.items()
        elif isinstance(edge_data, list):
            iterable = enumerate(edge_data)
        else:
            self.warnings.append("AKBSM edge file has unsupported shape")
            return
        for edge_id, edge in iterable:
            if not isinstance(edge, Mapping):
                continue
            record = dict(edge)
            record.setdefault("edge_id", str(edge_id))
            self.edges.append(record)

    def list_edges(self) -> list[dict[str, Any]]:
        return list(self.edges)

    def get_edges_from(self, node_id: str) -> list[dict[str, Any]]:
        return [edge for edge in self.edges if str(edge.get("from")) == str(node_id)]

    def get_edges_to(self, node_id: str) -> list[dict[str, Any]]:
        return [edge for edge in self.edges if str(edge.get("to")) == str(node_id)]

    def get_related_patterns(self, pattern_id: str) -> list[RelatedPattern]:
        related: list[RelatedPattern] = []
        for edge in self.get_edges_from(pattern_id):
            target = edge.get("to")
            if target is None:
                continue
            related.append(
                RelatedPattern(
                    pattern_id=str(target),
                    relation_type=str(edge.get("type", "")),
                    confidence=_as_float(edge.get("confidence", 0.0)),
                    source_edge_id=str(edge.get("edge_id")) if edge.get("edge_id") is not None else None,
                )
            )
        return related

    def find_related_from_matches(self, matches: list[PatternMatch]) -> list[RelatedPattern]:
        related: list[RelatedPattern] = []
        seen: set[tuple[str, str, str | None]] = set()
        for match in matches:
            for item in self.get_related_patterns(match.pattern_id):
                key = (item.pattern_id, item.relation_type, item.source_edge_id)
                if key not in seen:
                    seen.add(key)
                    related.append(item)
        return sorted(related, key=lambda item: item.confidence, reverse=True)


def _as_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
