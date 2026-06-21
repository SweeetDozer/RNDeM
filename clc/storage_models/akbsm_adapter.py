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

    def find_associations(
        self,
        source_pattern_id: str,
        *,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        relation_filter = {str(item) for item in relation_types} if relation_types else None
        source_pattern_id = str(source_pattern_id)
        queue: list[tuple[str, int, list[str], list[dict[str, Any]], float]] = [
            (source_pattern_id, 0, [source_pattern_id], [], 1.0)
        ]
        visited = {source_pattern_id}
        results: list[dict[str, Any]] = []
        while queue and len(results) < limit:
            node_id, depth, path, raw_links, path_score = queue.pop(0)
            if depth >= max_depth:
                continue
            for edge in self.get_edges_from(node_id):
                relation_type = str(edge.get("type", edge.get("relation_type", "")))
                if relation_filter is not None and relation_type not in relation_filter:
                    continue
                target = edge.get("to")
                if target is None:
                    continue
                target_id = str(target)
                weight = _as_float(edge.get("confidence", edge.get("weight", 0.0)))
                link = {
                    "from": str(edge.get("from", node_id)),
                    "to": target_id,
                    "relation_type": relation_type,
                    "weight": weight,
                }
                next_path = path + [target_id]
                next_links = raw_links + [link]
                next_score = max(0.0, min(1.0, path_score * (weight or 0.1)))
                results.append(
                    {
                        "pattern_id": target_id,
                        "distance": depth + 1,
                        "relation_type": relation_type,
                        "score": round(next_score, 3),
                        "path": next_path,
                        "raw_links": next_links,
                    }
                )
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append((target_id, depth + 1, next_path, next_links, next_score))
                if len(results) >= limit:
                    break
        return sorted(results, key=lambda item: (item["score"], -item["distance"]), reverse=True)[:limit]


def _as_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
