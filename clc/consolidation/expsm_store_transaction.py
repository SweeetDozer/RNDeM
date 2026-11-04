from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator


class ExpSMStoreInvalidError(ValueError):
    """Raised when an authoritative ExpSM store is not safe to mutate."""


class ExpSMEnvelopeV2WriteDisabledError(ExpSMStoreInvalidError):
    """Stage 1 can read envelope v2 but cannot write or downgrade it."""


class ExpSMStoreFormat(str, Enum):
    LEGACY_UNVERSIONED = "legacy_unversioned"
    ENVELOPE_V2 = "envelope_v2"


@dataclass(frozen=True)
class ExpSMStoreState:
    """Normalized ExpSM content independent of its on-disk envelope."""

    format_kind: ExpSMStoreFormat
    experience: dict[str, Any]
    reflexes: dict[str, Any]
    native_feedback_receipts: dict[str, Any] | None = None
    envelope_metadata: dict[str, Any] = field(default_factory=dict)

    def legacy_facade(self) -> dict[str, Any]:
        return {"experience": dict(self.experience), "reflexes": dict(self.reflexes)}


@dataclass
class _PathLockCoordinator:
    rlock: threading.RLock = field(default_factory=threading.RLock)
    local: threading.local = field(default_factory=threading.local)


class ExpSMStoreTransaction:
    """Shared Linux/Fedora locking and atomic ExpSM replacement mechanics."""

    _locks_guard = threading.Lock()
    _coordinators: dict[Path, _PathLockCoordinator] = {}

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)
        self.resolved_store_path = self.store_path.resolve()
        self.lock_path = self.store_path.with_suffix(".lock")
        with self._locks_guard:
            self._coordinator = self._coordinators.setdefault(
                self.resolved_store_path, _PathLockCoordinator()
            )

    @contextmanager
    def mutation(self) -> Iterator[None]:
        """Hold one reentrant path lock and one outermost stable-file flock."""
        coordinator = self._coordinator
        with coordinator.rlock:
            depth = int(getattr(coordinator.local, "depth", 0))
            if depth == 0:
                descriptor: int | None = None
                try:
                    self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                    descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                except OSError:
                    if descriptor is not None:
                        os.close(descriptor)
                    raise
                coordinator.local.descriptor = descriptor
                coordinator.local.source_format = None
            coordinator.local.depth = depth + 1
            try:
                yield
            finally:
                remaining = int(coordinator.local.depth) - 1
                coordinator.local.depth = remaining
                if remaining == 0:
                    descriptor = coordinator.local.descriptor
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    finally:
                        os.close(descriptor)
                        coordinator.local.descriptor = None
                        coordinator.local.source_format = None

    def load_state_strict(self) -> ExpSMStoreState:
        if not self.store_path.exists():
            state = ExpSMStoreState(ExpSMStoreFormat.LEGACY_UNVERSIONED, {}, {})
        else:
            try:
                with self.store_path.open("r", encoding="utf-8-sig") as handle:
                    raw = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                raise ExpSMStoreInvalidError(f"invalid ExpSM JSON: {exc}") from exc
            state = self.normalize_store(raw)
        if self._mutation_active():
            self._coordinator.local.source_format = state.format_kind
        return state

    def load_strict(self) -> dict[str, Any]:
        return self.load_state_strict().legacy_facade()

    def load_for_mutation_strict(self) -> dict[str, Any]:
        """Fresh-load a writable Stage-1 source after both writer locks."""
        if not self._mutation_active():
            raise RuntimeError("ExpSM mutation loads require mutation()")
        state = self.load_state_strict()
        if state.format_kind is ExpSMStoreFormat.ENVELOPE_V2:
            raise ExpSMEnvelopeV2WriteDisabledError("ENVELOPE_V2_WRITE_NOT_ENABLED")
        return state.legacy_facade()

    @classmethod
    def normalize_store(cls, raw: object) -> ExpSMStoreState:
        if not isinstance(raw, dict):
            raise ExpSMStoreInvalidError("ExpSM store must be a JSON object")
        if "store_schema_version" not in raw:
            validated = cls.validate_store(raw)
            return ExpSMStoreState(
                ExpSMStoreFormat.LEGACY_UNVERSIONED,
                dict(validated["experience"]),
                dict(validated["reflexes"]),
            )
        if raw.get("store_schema_version") != 2:
            raise ExpSMStoreInvalidError("unsupported ExpSM store_schema_version")
        required = {
            "store_schema_version", "experience", "reflexes", "native_feedback_receipts"
        }
        if not required.issubset(raw):
            raise ExpSMStoreInvalidError("ExpSM envelope v2 is missing required keys")
        receipts = raw["native_feedback_receipts"]
        if not isinstance(receipts, dict):
            raise ExpSMStoreInvalidError("native_feedback_receipts must be an object")
        cls._validate_record_sections(raw)
        metadata = {key: value for key, value in raw.items() if key not in required}
        return ExpSMStoreState(
            ExpSMStoreFormat.ENVELOPE_V2,
            dict(raw["experience"]),
            dict(raw["reflexes"]),
            native_feedback_receipts=dict(receipts),
            envelope_metadata=metadata,
        )

    @classmethod
    def validate_store(cls, raw: object) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ExpSMStoreInvalidError("ExpSM store must be a JSON object")
        if "store_schema_version" in raw:
            raise ExpSMStoreInvalidError("versioned ExpSM envelopes require normalized parsing")
        cls._validate_record_sections(raw)
        return raw

    @staticmethod
    def _validate_record_sections(raw: Mapping[str, Any]) -> None:
        from clc.experience.expsm_representation import (
            ExpSMRecordAdapter,
            MalformedRecord,
            UnsupportedRecord,
        )

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

    def write_complete_store(
        self,
        store: dict[str, Any],
        *,
        before_replace: Callable[[], None] | None = None,
    ) -> None:
        """Write current legacy format while the shared writer locks are held."""
        if not self._mutation_active():
            raise RuntimeError("ExpSM authoritative writes require mutation()")
        if self._coordinator.local.source_format is ExpSMStoreFormat.ENVELOPE_V2:
            raise ExpSMEnvelopeV2WriteDisabledError("ENVELOPE_V2_WRITE_NOT_ENABLED")
        self.validate_store(store)
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

    def _mutation_active(self) -> bool:
        return int(getattr(self._coordinator.local, "depth", 0)) > 0

    def _fsync_parent_if_supported(self) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(self.store_path.parent, flags)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)
