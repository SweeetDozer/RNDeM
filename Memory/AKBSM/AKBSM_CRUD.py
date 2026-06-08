"""CRUD utilities for AKBSM graph memory.

Data format:
{
    "nodes": {
        "1": {"data": "Cup of tea"}
    },
    "edges": [
        {"from": "1", "type": "1", "to": "2"}
    ]
}
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DATA_FILE = Path(__file__).with_name("AKBSM_data.json")


class AKBSMError(Exception):
    """Base error for AKBSM CRUD operations."""


class NodeNotFoundError(AKBSMError):
    """Raised when a requested node does not exist."""


class EdgeNotFoundError(AKBSMError):
    """Raised when a requested edge does not exist."""


class AKBSMCRUD:
    """Small JSON-backed CRUD layer for AKBSM nodes and edges."""

    def __init__(self, data_file: str | Path = DATA_FILE) -> None:
        self.data_file = Path(data_file)
        self.data: dict[str, Any] = self.load()

    def load(self) -> dict[str, Any]:
        """Load data from disk and normalize missing top-level keys."""
        if not self.data_file.exists():
            return {"nodes": {}, "edges": []}

        with self.data_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        data.setdefault("nodes", {})
        data.setdefault("edges", [])
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

    def get_nodes(self) -> dict[str, dict[str, Any]]:
        """Return a copy of all nodes."""
        return deepcopy(self.data["nodes"])

    def get_edges(self) -> list[dict[str, str]]:
        """Return a copy of all edges."""
        return deepcopy(self.data["edges"])

    def create_node(self, data: Any, node_id: str | None = None) -> str:
        """Create a node and return its id."""
        node_id = str(node_id) if node_id is not None else self._next_node_id()

        if node_id in self.data["nodes"]:
            raise ValueError(f"Node with id {node_id!r} already exists.")

        self.data["nodes"][node_id] = {"data": data}
        self.save()
        return node_id

    def read_node(self, node_id: str) -> dict[str, Any]:
        """Read one node by id."""
        node_id = str(node_id)
        self._require_node(node_id)
        return deepcopy(self.data["nodes"][node_id])

    def update_node(self, node_id: str, data: Any) -> dict[str, Any]:
        """Replace the data payload of an existing node."""
        node_id = str(node_id)
        self._require_node(node_id)

        self.data["nodes"][node_id]["data"] = data
        self.save()
        return deepcopy(self.data["nodes"][node_id])

    def delete_node(self, node_id: str, delete_edges: bool = True) -> dict[str, Any]:
        """Delete a node and, by default, every edge connected to it."""
        node_id = str(node_id)
        self._require_node(node_id)

        if not delete_edges and self.find_edges(from_id=node_id) + self.find_edges(to_id=node_id):
            raise ValueError(f"Node {node_id!r} has connected edges.")

        deleted_node = self.data["nodes"].pop(node_id)

        if delete_edges:
            self.data["edges"] = [
                edge
                for edge in self.data["edges"]
                if edge["from"] != node_id and edge["to"] != node_id
            ]

        self.save()
        return deepcopy(deleted_node)

    def create_edge(self, from_id: str, edge_type: str, to_id: str) -> dict[str, str]:
        """Create an edge between two existing nodes."""
        from_id = str(from_id)
        edge_type = str(edge_type)
        to_id = str(to_id)

        self._require_node(from_id)
        self._require_node(to_id)

        edge = {"from": from_id, "type": edge_type, "to": to_id}
        self.data["edges"].append(edge)
        self.save()
        return deepcopy(edge)

    def read_edge(self, index: int) -> dict[str, str]:
        """Read one edge by list index."""
        self._require_edge_index(index)
        return deepcopy(self.data["edges"][index])

    def update_edge(
        self,
        index: int,
        from_id: str | None = None,
        edge_type: str | None = None,
        to_id: str | None = None,
    ) -> dict[str, str]:
        """Update an edge by list index."""
        self._require_edge_index(index)

        edge = self.data["edges"][index]
        new_from_id = edge["from"] if from_id is None else str(from_id)
        new_type = edge["type"] if edge_type is None else str(edge_type)
        new_to_id = edge["to"] if to_id is None else str(to_id)

        self._require_node(new_from_id)
        self._require_node(new_to_id)

        edge.update({"from": new_from_id, "type": new_type, "to": new_to_id})
        self.save()
        return deepcopy(edge)

    def delete_edge(self, index: int) -> dict[str, str]:
        """Delete an edge by list index."""
        self._require_edge_index(index)
        deleted_edge = self.data["edges"].pop(index)
        self.save()
        return deepcopy(deleted_edge)

    def find_edges(
        self,
        from_id: str | None = None,
        edge_type: str | None = None,
        to_id: str | None = None,
    ) -> list[dict[str, str]]:
        """Find edges matching any provided filters."""
        from_id = None if from_id is None else str(from_id)
        edge_type = None if edge_type is None else str(edge_type)
        to_id = None if to_id is None else str(to_id)

        edges = []
        for index, edge in enumerate(self.data["edges"]):
            if from_id is not None and edge["from"] != from_id:
                continue
            if edge_type is not None and edge["type"] != edge_type:
                continue
            if to_id is not None and edge["to"] != to_id:
                continue

            edge_with_index = deepcopy(edge)
            edge_with_index["index"] = index
            edges.append(edge_with_index)

        return edges

    def _next_node_id(self) -> str:
        used_ids = {
            int(node_id)
            for node_id in self.data["nodes"]
            if str(node_id).isdigit()
        }

        next_id = 1
        while next_id in used_ids:
            next_id += 1

        return str(next_id)

    def _require_node(self, node_id: str) -> None:
        if node_id not in self.data["nodes"]:
            raise NodeNotFoundError(f"Node with id {node_id!r} was not found.")

    def _require_edge_index(self, index: int) -> None:
        if index < 0 or index >= len(self.data["edges"]):
            raise EdgeNotFoundError(f"Edge with index {index} was not found.")


def _default_crud() -> AKBSMCRUD:
    return AKBSMCRUD(DATA_FILE)


def load_data() -> dict[str, Any]:
    return _default_crud().get_all()


def create_node(data: Any, node_id: str | None = None) -> str:
    return _default_crud().create_node(data, node_id)


def read_node(node_id: str) -> dict[str, Any]:
    return _default_crud().read_node(node_id)


def update_node(node_id: str, data: Any) -> dict[str, Any]:
    return _default_crud().update_node(node_id, data)


def delete_node(node_id: str, delete_edges: bool = True) -> dict[str, Any]:
    return _default_crud().delete_node(node_id, delete_edges)


def create_edge(from_id: str, edge_type: str, to_id: str) -> dict[str, str]:
    return _default_crud().create_edge(from_id, edge_type, to_id)


def read_edge(index: int) -> dict[str, str]:
    return _default_crud().read_edge(index)


def update_edge(
    index: int,
    from_id: str | None = None,
    edge_type: str | None = None,
    to_id: str | None = None,
) -> dict[str, str]:
    return _default_crud().update_edge(index, from_id, edge_type, to_id)


def delete_edge(index: int) -> dict[str, str]:
    return _default_crud().delete_edge(index)


def find_edges(
    from_id: str | None = None,
    edge_type: str | None = None,
    to_id: str | None = None,
) -> list[dict[str, str]]:
    return _default_crud().find_edges(from_id, edge_type, to_id)
