"""CRUD utilities for AKBSM NFP memory.

AKBSM stores node payloads as separate ``DB/<id>.nfp`` JSON files and stores
node edges in ``AKBSM_ne.json``.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "DB"
EDGE_FILE = BASE_DIR / "AKBSM_ne.json"


class AKBSMError(Exception):
    """Base error for AKBSM operations."""


class NFPNotFoundError(AKBSMError):
    """Raised when a requested NFP node does not exist."""


class EdgeNotFoundError(AKBSMError):
    """Raised when a requested edge does not exist."""


class AKBSMCRUD:
    """File-backed CRUD layer for AKBSM NFP nodes and edges."""

    def __init__(
        self,
        db_dir: str | Path = DB_DIR,
        edge_file: str | Path = EDGE_FILE,
    ) -> None:
        self.db_dir = Path(db_dir)
        self.edge_file = Path(edge_file)

    def list_nfp_ids(self) -> list[str]:
        """Return all NFP ids sorted numerically where possible."""
        if not self.db_dir.exists():
            return []

        ids = [path.stem for path in self.db_dir.glob("*.nfp")]
        return sorted(ids, key=self._sort_key)

    def create_nfp(
        self,
        nfp: list[Any],
        nfp_type: int | str,
        nfp_id: str | int | None = None,
    ) -> str:
        """Create one NFP file and return its id."""
        nfp_id = self._prepare_new_nfp_id(nfp_id)
        self._write_nfp_file(nfp_id, self._make_nfp_record(nfp, nfp_type))
        return nfp_id

    def read_nfp(self, nfp_id: str | int) -> dict[str, Any]:
        """Read one NFP file by id."""
        nfp_id = str(nfp_id)
        self._require_nfp(nfp_id)
        return self._read_json(self._nfp_path(nfp_id))

    def read_nfp_payload(self, nfp_id: str | int) -> list[Any]:
        """Read only the ``nfp`` payload from one NFP file."""
        return deepcopy(self.read_nfp(nfp_id)["nfp"])

    def update_nfp(
        self,
        nfp_id: str | int,
        nfp: list[Any] | None = None,
        nfp_type: int | str | None = None,
    ) -> dict[str, Any]:
        """Update one NFP file."""
        nfp_id = str(nfp_id)
        record = self.read_nfp(nfp_id)

        if nfp is not None:
            record["nfp"] = nfp
        if nfp_type is not None:
            record["type"] = str(nfp_type)

        self._write_nfp_file(nfp_id, record)
        return deepcopy(record)

    def delete_nfp(self, nfp_id: str | int, delete_edges: bool = True) -> dict[str, Any]:
        """Delete one NFP file and, by default, connected edges."""
        nfp_id = str(nfp_id)
        record = self.read_nfp(nfp_id)
        connected_edges = self.find_edges(from_id=nfp_id) | self.find_edges(to_id=nfp_id)

        if connected_edges and not delete_edges:
            raise ValueError(f"NFP {nfp_id!r} has connected edges.")

        self._nfp_path(nfp_id).unlink()

        if delete_edges:
            edges = self.load_edges()
            for edge_id in connected_edges:
                edges.pop(edge_id, None)
            self.save_edges(edges)

        return record

    def load_edges(self) -> dict[str, dict[str, Any]]:
        """Load the edge storage file."""
        if not self.edge_file.exists():
            return {}
        return self._read_json(self.edge_file)

    def save_edges(self, edges: dict[str, dict[str, Any]]) -> None:
        """Save the edge storage file."""
        self.edge_file.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(self.edge_file, edges)

    def list_edge_ids(self) -> list[str]:
        """Return all edge ids sorted numerically where possible."""
        return sorted(self.load_edges(), key=self._sort_key)

    def create_edge(
        self,
        from_id: str | int,
        edge_type: int | str,
        to_id: str | int,
        edge_id: str | int | None = None,
        confidence: float = 0.5,
        source: int = 1,
        status: int = 1,
        hits: int = 0,
        misses: int = 0,
    ) -> str:
        """Create an edge between existing NFP nodes and return its id."""
        from_id = str(from_id)
        to_id = str(to_id)
        edge_id = self._prepare_new_edge_id(edge_id)

        self._require_nfp(from_id)
        self._require_nfp(to_id)

        edges = self.load_edges()
        edges[edge_id] = {
            "from": from_id,
            "type": str(edge_type),
            "to": to_id,
            "confidence": confidence,
            "source": source,
            "status": status,
            "hits": hits,
            "misses": misses,
        }
        self.save_edges(edges)
        return edge_id

    def read_edge(self, edge_id: str | int) -> dict[str, Any]:
        """Read one edge by id."""
        edge_id = str(edge_id)
        edges = self.load_edges()
        if edge_id not in edges:
            raise EdgeNotFoundError(f"Edge with id {edge_id!r} was not found.")
        return deepcopy(edges[edge_id])

    def update_edge(self, edge_id: str | int, **fields: Any) -> dict[str, Any]:
        """Update fields of one edge."""
        edge_id = str(edge_id)
        edges = self.load_edges()

        if edge_id not in edges:
            raise EdgeNotFoundError(f"Edge with id {edge_id!r} was not found.")

        edge = deepcopy(edges[edge_id])
        edge.update(fields)

        if "from" in edge:
            edge["from"] = str(edge["from"])
            self._require_nfp(edge["from"])
        if "to" in edge:
            edge["to"] = str(edge["to"])
            self._require_nfp(edge["to"])
        if "type" in edge:
            edge["type"] = str(edge["type"])

        edges[edge_id] = edge
        self.save_edges(edges)
        return deepcopy(edge)

    def delete_edge(self, edge_id: str | int) -> dict[str, Any]:
        """Delete one edge by id."""
        edge_id = str(edge_id)
        edges = self.load_edges()

        if edge_id not in edges:
            raise EdgeNotFoundError(f"Edge with id {edge_id!r} was not found.")

        deleted_edge = edges.pop(edge_id)
        self.save_edges(edges)
        return deepcopy(deleted_edge)

    def find_edges(
        self,
        from_id: str | int | None = None,
        edge_type: int | str | None = None,
        to_id: str | int | None = None,
        source: int | None = None,
        status: int | None = None,
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
        for edge_id, edge in self.load_edges().items():
            if any(value is not None and edge.get(key) != value for key, value in filters.items()):
                continue
            matches[edge_id] = deepcopy(edge)
        return matches

    def record_edge_hit(self, edge_id: str | int) -> dict[str, Any]:
        """Increase edge hits by one."""
        return self._increment_edge_counter(edge_id, "hits")

    def record_edge_miss(self, edge_id: str | int) -> dict[str, Any]:
        """Increase edge misses by one."""
        return self._increment_edge_counter(edge_id, "misses")

    def _increment_edge_counter(self, edge_id: str | int, field: str) -> dict[str, Any]:
        edge = self.read_edge(edge_id)
        edge[field] = edge.get(field, 0) + 1
        return self.update_edge(edge_id, **edge)

    def _prepare_new_nfp_id(self, nfp_id: str | int | None) -> str:
        nfp_id = str(nfp_id) if nfp_id is not None else self._next_nfp_id()
        if self._nfp_path(nfp_id).exists():
            raise ValueError(f"NFP with id {nfp_id!r} already exists.")
        return nfp_id

    def _prepare_new_edge_id(self, edge_id: str | int | None) -> str:
        edges = self.load_edges()
        edge_id = str(edge_id) if edge_id is not None else self._next_id(edges)
        if edge_id in edges:
            raise ValueError(f"Edge with id {edge_id!r} already exists.")
        return edge_id

    def _next_nfp_id(self) -> str:
        return self._next_id({nfp_id: None for nfp_id in self.list_nfp_ids()})

    @staticmethod
    def _next_id(records: dict[str, Any]) -> str:
        used_ids = {int(record_id) for record_id in records if str(record_id).isdigit()}
        next_id = 1
        while next_id in used_ids:
            next_id += 1
        return str(next_id)

    def _nfp_path(self, nfp_id: str) -> Path:
        return self.db_dir / f"{nfp_id}.nfp"

    def _require_nfp(self, nfp_id: str) -> None:
        if not self._nfp_path(nfp_id).exists():
            raise NFPNotFoundError(f"NFP with id {nfp_id!r} was not found.")

    def _write_nfp_file(self, nfp_id: str, record: dict[str, Any]) -> None:
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self._nfp_path(nfp_id), record)

    @staticmethod
    def _make_nfp_record(nfp: list[Any], nfp_type: int | str) -> dict[str, Any]:
        return {
            "type": str(nfp_type),
            "nfp": nfp,
        }

    @staticmethod
    def _read_json(path: Path) -> Any:
        with path.open("r", encoding="utf-8-sig") as file:
            return json.load(file)

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")

    @staticmethod
    def _sort_key(value: str) -> tuple[int, int | str]:
        return (0, int(value)) if str(value).isdigit() else (1, value)


def _default_crud() -> AKBSMCRUD:
    return AKBSMCRUD(DB_DIR, EDGE_FILE)


def list_nfp_ids() -> list[str]:
    return _default_crud().list_nfp_ids()


def create_nfp(nfp: list[Any], nfp_type: int | str, nfp_id: str | int | None = None) -> str:
    return _default_crud().create_nfp(nfp, nfp_type, nfp_id)


def read_nfp(nfp_id: str | int) -> dict[str, Any]:
    return _default_crud().read_nfp(nfp_id)


def read_nfp_payload(nfp_id: str | int) -> list[Any]:
    return _default_crud().read_nfp_payload(nfp_id)


def update_nfp(
    nfp_id: str | int,
    nfp: list[Any] | None = None,
    nfp_type: int | str | None = None,
) -> dict[str, Any]:
    return _default_crud().update_nfp(nfp_id, nfp, nfp_type)


def delete_nfp(nfp_id: str | int, delete_edges: bool = True) -> dict[str, Any]:
    return _default_crud().delete_nfp(nfp_id, delete_edges)


def load_edges() -> dict[str, dict[str, Any]]:
    return _default_crud().load_edges()


def save_edges(edges: dict[str, dict[str, Any]]) -> None:
    _default_crud().save_edges(edges)


def list_edge_ids() -> list[str]:
    return _default_crud().list_edge_ids()


def create_edge(
    from_id: str | int,
    edge_type: int | str,
    to_id: str | int,
    edge_id: str | int | None = None,
    confidence: float = 0.5,
    source: int = 1,
    status: int = 1,
    hits: int = 0,
    misses: int = 0,
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
    )


def read_edge(edge_id: str | int) -> dict[str, Any]:
    return _default_crud().read_edge(edge_id)


def update_edge(edge_id: str | int, **fields: Any) -> dict[str, Any]:
    return _default_crud().update_edge(edge_id, **fields)


def delete_edge(edge_id: str | int) -> dict[str, Any]:
    return _default_crud().delete_edge(edge_id)


def find_edges(
    from_id: str | int | None = None,
    edge_type: int | str | None = None,
    to_id: str | int | None = None,
    source: int | None = None,
    status: int | None = None,
) -> dict[str, dict[str, Any]]:
    return _default_crud().find_edges(from_id, edge_type, to_id, source, status)


def record_edge_hit(edge_id: str | int) -> dict[str, Any]:
    return _default_crud().record_edge_hit(edge_id)


def record_edge_miss(edge_id: str | int) -> dict[str, Any]:
    return _default_crud().record_edge_miss(edge_id)
