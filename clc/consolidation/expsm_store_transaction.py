from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

class ExpSMStoreInvalidError(ValueError):
    """Raised when an authoritative ExpSM store is not safe to mutate."""


class ExpSMStoreTransaction:
    """Shared single-process mechanics for atomic ExpSM store replacement."""

    _locks_guard = threading.Lock()
    _locks: dict[Path, threading.RLock] = {}

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)
        resolved = self.store_path.resolve()
        with self._locks_guard:
            self._lock = self._locks.setdefault(resolved, threading.RLock())

    @contextmanager
    def mutation(self) -> Iterator[None]:
        """Hold the path-local lock across load, allocation and replacement."""
        with self._lock:
            yield

    def load_strict(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {"experience": {}, "reflexes": {}}
        try:
            with self.store_path.open("r", encoding="utf-8-sig") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ExpSMStoreInvalidError(f"invalid ExpSM JSON: {exc}") from exc
        return self.validate_store(raw)

    @staticmethod
    def validate_store(raw: object) -> dict[str, Any]:
        # Keep the NFP representation layer lazy for legacy runtime imports.
        from clc.experience.expsm_representation import (
            ExpSMRecordAdapter,
            MalformedRecord,
            UnsupportedRecord,
        )

        if not isinstance(raw, dict):
            raise ExpSMStoreInvalidError("ExpSM store must be a JSON object")
        for section in ("experience", "reflexes"):
            if section not in raw or not isinstance(raw[section], dict):
                raise ExpSMStoreInvalidError(f"ExpSM {section} section must be an object")
        for record_id, record in raw["experience"].items():
            if not isinstance(record_id, str) or not record_id.isdigit():
                raise ExpSMStoreInvalidError("ExpSM experience IDs must be numeric strings")
            if not isinstance(record, Mapping):
                raise ExpSMStoreInvalidError(f"experience {record_id} must be an object")
            parsed = ExpSMRecordAdapter.parse(record_id, record)
            if isinstance(parsed, (MalformedRecord, UnsupportedRecord)):
                raise ExpSMStoreInvalidError(f"experience {record_id} is invalid: {parsed}")
        for record_id, record in raw["reflexes"].items():
            if not isinstance(record_id, str) or not record_id.isdigit():
                raise ExpSMStoreInvalidError("ExpSM reflex IDs must be numeric strings")
            if not isinstance(record, Mapping):
                raise ExpSMStoreInvalidError(f"reflex {record_id} must be an object")
        return raw

    def write_complete_store(
        self,
        store: dict[str, Any],
        *,
        before_replace: Callable[[], None] | None = None,
    ) -> None:
        """Serialize to a unique sibling, fsync it, and atomically replace."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.store_path.parent,
                prefix=f".{self.store_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(store, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            if before_replace is not None:
                before_replace()
            temp_path.replace(self.store_path)
            temp_path = None
            self._fsync_parent_if_supported()
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _fsync_parent_if_supported(self) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(self.store_path.parent, flags)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            # Some filesystems/platforms do not support directory fsync.
            pass
        finally:
            os.close(descriptor)
