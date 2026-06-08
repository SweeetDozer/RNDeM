"""CRUD utilities for AKBSM graph memory."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DATA_FILE = Path(__file__).with_name("AKBSM_data.json")


class AKBSMError(Exception):
    """Base error for AKBSM CRUD operations."""


class NodeNotFoundError(AKBSMError):
    """Raised when a requested node does not exist."""


class EdgeNotFoundError(AKBSMError):
    """Raised when a requested edge does not exist."""


class InvalidValueError(AKBSMError):
    """Raised when a value is not allowed by AKBSM_data.json."""


class AKBSMCRUD:
    """JSON-backed CRUD layer for AKBSM nodes and typed edges."""

    def __init__(self, data_file: str | Path = DATA_FILE) -> None:
        self.data_file = Path(data_file)
        self.data: dict[str, Any] = self.load()

    def load(self) -> dict[str, Any]:
        """Load data from disk and normalize missing top-level keys."""
        if not self.data_file.exists():
            return {"meta": {}, "allowed_values": {}, "nodes": {}, "edges": {}}

        with self.data_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        data.setdefault("meta", {})
        data.setdefault("allowed_values", {})
        data.setdefault("nodes", {})
        data.setdefault("edges", {})
        return data

    def save(self) -> None:
        """Save current data to disk."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        with self.data_file.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
            file.write("\n")

    def get_all(self) -> dict[str, Any]:
        """Return a copy of all AKBSM data."""
        return deepcopy(self.data)

    def get_meta(self) -> dict[str, Any]:
        """Return AKBSM metadata."""
        return deepcopy(self.data["meta"])

    def get_allowed_values(self) -> dict[str, list[str]]:
        """Return configured allowed values."""
        return deepcopy(self.data["allowed_values"])

    def get_nodes(self) -> dict[str, dict[str, Any]]:
        """Return all nodes."""
        return deepcopy(self.data["nodes"])

    def get_edges(self) -> dict[str, dict[str, Any]]:
        """Return all edges."""
        return deepcopy(self.data["edges"])

    def create_node(
        self,
        data: Any,
        node_id: str | None = None,
        created_at_world: str | None = None,
        **extra_fields: Any,
    ) -> str:
        """Create a node and return its id."""
        node_id = self._prepare_new_id("nodes", node_id)
        node = {
            "data": data,
            "created_at_world": created_at_world or self._now_world(),
        }
        node.update(extra_fields)

        self.data["nodes"][node_id] = node
        self.save()
        return node_id

    def read_node(self, node_id: str) -> dict[str, Any]:
        """Read one node by id."""
        node_id = str(node_id)
        self._require_node(node_id)
        return deepcopy(self.data["nodes"][node_id])

    def update_node(
        self,
        node_id: str,
        data: Any | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """Update fields of an existing node."""
        node_id = str(node_id)
        self._require_node(node_id)

        if data is not None:
            self.data["nodes"][node_id]["data"] = data
        self.data["nodes"][node_id].update(fields)

        self.save()
        return deepcopy(self.data["nodes"][node_id])

    def delete_node(self, node_id: str, delete_edges: bool = True) -> dict[str, Any]:
        """Delete a node and, by default, every connected edge."""
        node_id = str(node_id)
        self._require_node(node_id)

        connected_edges = self.find_edges(from_id=node_id) | self.find_edges(to_id=node_id)
        if connected_edges and not delete_edges:
            raise ValueError(f"Node {node_id!r} has connected edges.")

        deleted_node = self.data["nodes"].pop(node_id)

        if delete_edges:
            for edge_id in connected_edges:
                self.data["edges"].pop(edge_id)

        self.save()
        return deepcopy(deleted_node)

    def create_edge(
        self,
        from_id: str,
        edge_type: str,
        to_id: str,
        edge_id: str | None = None,
        confidence: float = 0.5,
        source: str = "unknown",
        status: str = "hypothesis",
        hits: int = 0,
        misses: int = 0,
        **extra_fields: Any,
    ) -> str:
        """Create an edge between two existing nodes and return its id."""
        from_id = str(from_id)
        edge_type = str(edge_type)
        to_id = str(to_id)
        edge_id = self._prepare_new_id("edges", edge_id)

        self._require_node(from_id)
        self._require_node(to_id)
        self._validate_allowed("edge_source", source)
        self._validate_allowed("edge_status", status)

        edge = {
            "from": from_id,
            "type": edge_type,
            "to": to_id,
            "confidence": confidence,
            "source": source,
            "status": status,
            "hits": hits,
            "misses": misses,
        }
        edge.update(extra_fields)

        self.data["edges"][edge_id] = edge
        self.save()
        return edge_id

    def read_edge(self, edge_id: str) -> dict[str, Any]:
        """Read one edge by id."""
        edge_id = str(edge_id)
        self._require_edge(edge_id)
        return deepcopy(self.data["edges"][edge_id])

    def update_edge(self, edge_id: str, **fields: Any) -> dict[str, Any]:
        """Update fields of an existing edge."""
        edge_id = str(edge_id)
        self._require_edge(edge_id)

        candidate = deepcopy(self.data["edges"][edge_id])
        candidate.update({key: str(value) if key in {"from", "type", "to"} else value for key, value in fields.items()})

        self._require_node(candidate["from"])
        self._require_node(candidate["to"])
        self._validate_allowed("edge_source", candidate.get("source"))
        self._validate_allowed("edge_status", candidate.get("status"))

        self.data["edges"][edge_id] = candidate
        self.save()
        return deepcopy(candidate)

    def delete_edge(self, edge_id: str) -> dict[str, Any]:
        """Delete an edge by id."""
        edge_id = str(edge_id)
        self._require_edge(edge_id)
        deleted_edge = self.data["edges"].pop(edge_id)
        self.save()
        return deepcopy(deleted_edge)

    def find_edges(
        self,
        from_id: str | None = None,
        edge_type: str | None = None,
        to_id: str | None = None,
        source: str | None = None,
        status: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Find edges matching provided filters."""
        filters = {
            "from": None if from_id is None else str(from_id),
            "type": None if edge_type is None else str(edge_type),
            "to": None if to_id is None else str(to_id),
            "source": source,
            "status": status,
        }

        matches = {}
        for edge_id, edge in self.data["edges"].items():
            if any(value is not None and edge.get(key) != value for key, value in filters.items()):
                continue
            matches[edge_id] = deepcopy(edge)

        return matches

    def record_edge_hit(self, edge_id: str) -> dict[str, Any]:
        """Increase edge hits by one."""
        edge_id = str(edge_id)
        self._require_edge(edge_id)
        self.data["edges"][edge_id]["hits"] = self.data["edges"][edge_id].get("hits", 0) + 1
        self.save()
        return deepcopy(self.data["edges"][edge_id])

    def record_edge_miss(self, edge_id: str) -> dict[str, Any]:
        """Increase edge misses by one."""
        edge_id = str(edge_id)
        self._require_edge(edge_id)
        self.data["edges"][edge_id]["misses"] = self.data["edges"][edge_id].get("misses", 0) + 1
        self.save()
        return deepcopy(self.data["edges"][edge_id])

    def _prepare_new_id(self, section: str, record_id: str | None) -> str:
        record_id = str(record_id) if record_id is not None else self._next_id(section)

        if record_id in self.data[section]:
            raise ValueError(f"Record with id {record_id!r} already exists in {section!r}.")

        return record_id

    def _next_id(self, section: str) -> str:
        used_ids = {
            int(record_id)
            for record_id in self.data[section]
            if str(record_id).isdigit()
        }

        next_id = 1
        while next_id in used_ids:
            next_id += 1

        return str(next_id)

    def _require_node(self, node_id: str) -> None:
        if node_id not in self.data["nodes"]:
            raise NodeNotFoundError(f"Node with id {node_id!r} was not found.")

    def _require_edge(self, edge_id: str) -> None:
        if edge_id not in self.data["edges"]:
            raise EdgeNotFoundError(f"Edge with id {edge_id!r} was not found.")

    def _validate_allowed(self, name: str, value: Any) -> None:
        allowed = self.data["allowed_values"].get(name)
        if allowed and value not in allowed:
            raise InvalidValueError(f"{value!r} is not allowed for {name!r}.")

    @staticmethod
    def _now_world() -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_crud() -> AKBSMCRUD:
    return AKBSMCRUD(DATA_FILE)


def load_data() -> dict[str, Any]:
    return _default_crud().get_all()


def create_node(
    data: Any,
    node_id: str | None = None,
    created_at_world: str | None = None,
    **extra_fields: Any,
) -> str:
    return _default_crud().create_node(data, node_id, created_at_world, **extra_fields)


def read_node(node_id: str) -> dict[str, Any]:
    return _default_crud().read_node(node_id)


def update_node(node_id: str, data: Any | None = None, **fields: Any) -> dict[str, Any]:
    return _default_crud().update_node(node_id, data, **fields)


def delete_node(node_id: str, delete_edges: bool = True) -> dict[str, Any]:
    return _default_crud().delete_node(node_id, delete_edges)


def create_edge(
    from_id: str,
    edge_type: str,
    to_id: str,
    edge_id: str | None = None,
    confidence: float = 0.5,
    source: str = "unknown",
    status: str = "hypothesis",
    hits: int = 0,
    misses: int = 0,
    **extra_fields: Any,
) -> str:
    return _default_crud().create_edge(
        from_id,
        edge_type,
        to_id,
        edge_id,
        confidence,
        source,
        status,
        hits,
        misses,
        **extra_fields,
    )


def read_edge(edge_id: str) -> dict[str, Any]:
    return _default_crud().read_edge(edge_id)


def update_edge(edge_id: str, **fields: Any) -> dict[str, Any]:
    return _default_crud().update_edge(edge_id, **fields)


def delete_edge(edge_id: str) -> dict[str, Any]:
    return _default_crud().delete_edge(edge_id)


def find_edges(
    from_id: str | None = None,
    edge_type: str | None = None,
    to_id: str | None = None,
    source: str | None = None,
    status: str | None = None,
) -> dict[str, dict[str, Any]]:
    return _default_crud().find_edges(from_id, edge_type, to_id, source, status)


def record_edge_hit(edge_id: str) -> dict[str, Any]:
    return _default_crud().record_edge_hit(edge_id)


def record_edge_miss(edge_id: str) -> dict[str, Any]:
    return _default_crud().record_edge_miss(edge_id)
