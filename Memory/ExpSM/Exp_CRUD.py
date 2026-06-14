"""CRUD utilities for ExpSM memory with inline NFP patterns.

ExpSM id safety policy:
- permanent memory record ids must not be reused;
- archive/tombstone records instead of physical deletion;
- future semantic references must be validated before use;
- dependent records should be archived if a core dependency is broken.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DATA_FILE = Path(__file__).resolve().with_name("ExpSM_data.json")


class ExpSMError(Exception):
    """Base error for ExpSM operations."""


class ExperienceNotFoundError(ExpSMError):
    """Raised when a requested experience does not exist."""


class ReflexNotFoundError(ExpSMError):
    """Raised when a requested reflex does not exist."""


class ExpSMCRUD:
    """JSON-backed CRUD layer for experience and reflex records."""

    def __init__(self, data_file: str | Path = DATA_FILE) -> None:
        self.data_file = Path(data_file)
        self.data = self.load()

    def load(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Load ExpSM data from disk."""
        if not self.data_file.exists():
            return {"experience": {}, "reflexes": {}}

        with self.data_file.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)

        data.setdefault("experience", {})
        data.setdefault("reflexes", {})
        return data

    def save(self) -> None:
        """Save ExpSM data to disk."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        with self.data_file.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
            file.write("\n")

    def get_all(self) -> dict[str, Any]:
        """Return a copy of all ExpSM data."""
        return deepcopy(self.data)

    def get_experience(self) -> dict[str, dict[str, Any]]:
        """Return all experience records."""
        return deepcopy(self.data["experience"])

    def get_reflexes(self) -> dict[str, dict[str, Any]]:
        """Return all reflex records."""
        return deepcopy(self.data["reflexes"])

    def create_experience(
        self,
        condition: list[Any],
        actions: list[Any],
        result: list[Any],
        recommendation: list[Any],
        level: int = 2,
        confidence: float = 0.5,
        repeatability: float = 0.5,
        source: int = 7,
        status: int = 2,
        hits: int = 0,
        misses: int = 0,
        experience_id: str | int | None = None,
        created_at_world: str | None = None,
        updated_at_world: str | None = None,
    ) -> str:
        """Create an experience record and return its id."""
        experience_id = self._prepare_new_id("experience", experience_id)
        self.data["experience"][experience_id] = self._make_experience(
            condition,
            actions,
            result,
            recommendation,
            level,
            confidence,
            repeatability,
            source,
            status,
            hits,
            misses,
            created_at_world,
            updated_at_world,
        )
        self.save()
        return experience_id

    def read_experience(self, experience_id: str | int) -> dict[str, Any]:
        """Read one experience record by id."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)
        return deepcopy(self.data["experience"][experience_id])

    def update_experience(self, experience_id: str | int, **fields: Any) -> dict[str, Any]:
        """Update fields of one experience record."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)

        record = deepcopy(self.data["experience"][experience_id])
        record.update(fields)
        if "updated_at_world" not in fields:
            record["updated_at_world"] = self._now_world()

        self.data["experience"][experience_id] = record
        self.save()
        return deepcopy(record)

    def delete_experience(self, experience_id: str | int) -> dict[str, Any]:
        """Archive one experience record by id.

        Permanent ExpSM ids are never reused, so delete is a tombstone operation.
        """
        experience_id = str(experience_id)
        self._require_experience(experience_id)
        deleted_record = self.data["experience"][experience_id]
        deleted_record["status"] = "archived"
        deleted_record["archive_reason"] = deleted_record.get("archive_reason", "deleted_by_crud_tombstone")
        deleted_record["updated_at_world"] = self._now_world()
        self.save()
        return deepcopy(deleted_record)

    def find_experience(
        self,
        level: int | None = None,
        source: int | None = None,
        status: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Find experience records by numeric fields."""
        return self._find_records("experience", level=level, source=source, status=status)

    def create_reflex(
        self,
        condition: list[Any],
        actions: list[Any],
        result: list[Any],
        recommendation: list[Any],
        priority: int = 3,
        autonomy_level: int = 2,
        confidence: float = 0.5,
        repeatability: float = 0.5,
        source: int = 7,
        status: int = 1,
        hits: int = 0,
        misses: int = 0,
        created_from_experience: str | int | None = None,
        reflex_id: str | int | None = None,
        created_at_world: str | None = None,
        updated_at_world: str | None = None,
    ) -> str:
        """Create a reflex record and return its id."""
        reflex_id = self._prepare_new_id("reflexes", reflex_id)
        self.data["reflexes"][reflex_id] = self._make_reflex(
            condition,
            actions,
            result,
            recommendation,
            priority,
            autonomy_level,
            confidence,
            repeatability,
            source,
            status,
            hits,
            misses,
            None if created_from_experience is None else str(created_from_experience),
            created_at_world,
            updated_at_world,
        )
        self.save()
        return reflex_id

    def read_reflex(self, reflex_id: str | int) -> dict[str, Any]:
        """Read one reflex record by id."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)
        return deepcopy(self.data["reflexes"][reflex_id])

    def update_reflex(self, reflex_id: str | int, **fields: Any) -> dict[str, Any]:
        """Update fields of one reflex record."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)

        record = deepcopy(self.data["reflexes"][reflex_id])
        record.update(fields)
        if "created_from_experience" in record and record["created_from_experience"] is not None:
            record["created_from_experience"] = str(record["created_from_experience"])
        if "updated_at_world" not in fields:
            record["updated_at_world"] = self._now_world()

        self.data["reflexes"][reflex_id] = record
        self.save()
        return deepcopy(record)

    def delete_reflex(self, reflex_id: str | int) -> dict[str, Any]:
        """Archive one reflex record by id.

        Permanent ExpSM ids are never reused, so delete is a tombstone operation.
        """
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)
        deleted_record = self.data["reflexes"][reflex_id]
        deleted_record["status"] = "archived"
        deleted_record["archive_reason"] = deleted_record.get("archive_reason", "deleted_by_crud_tombstone")
        deleted_record["updated_at_world"] = self._now_world()
        self.save()
        return deepcopy(deleted_record)

    def find_reflexes(
        self,
        priority: int | None = None,
        source: int | None = None,
        status: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Find reflex records by numeric fields."""
        records = self._find_records("reflexes", source=source, status=status)
        if priority is None:
            return records
        return {
            record_id: record
            for record_id, record in records.items()
            if record.get("priority") == priority
        }

    def experience_to_reflex(
        self,
        experience_id: str | int,
        reflex_id: str | int | None = None,
        priority: int = 3,
        autonomy_level: int = 2,
        status: int = 1,
        delete_source: bool = False,
        **overrides: Any,
    ) -> str:
        """Copy or move an experience record into reflexes."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)
        reflex_id = self._prepare_target_id("reflexes", reflex_id)

        experience = self.data["experience"][experience_id]
        record = self._make_reflex(
            experience["if"],
            experience["then"],
            experience["result"],
            experience["recommendation"],
            priority,
            autonomy_level,
            experience.get("confidence", 0.5),
            experience.get("repeatability", 0.5),
            experience.get("source", 7),
            status,
            experience.get("hits", 0),
            experience.get("misses", 0),
            experience_id,
            self._now_world(),
            self._now_world(),
        )
        record.update(overrides)

        self.data["reflexes"][reflex_id] = record
        if delete_source:
            experience["status"] = "archived"
            experience["archive_reason"] = experience.get("archive_reason", "moved_to_reflex_tombstone")
            experience["updated_at_world"] = self._now_world()

        self.save()
        return reflex_id

    def reflex_to_experience(
        self,
        reflex_id: str | int,
        experience_id: str | int | None = None,
        level: int = 2,
        status: int = 2,
        delete_source: bool = False,
        **overrides: Any,
    ) -> str:
        """Copy or move a reflex record into experience."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)
        experience_id = self._prepare_target_id("experience", experience_id)

        reflex = self.data["reflexes"][reflex_id]
        record = self._make_experience(
            reflex["if"],
            reflex["then"],
            reflex["result"],
            reflex["recommendation"],
            level,
            reflex.get("confidence", 0.5),
            reflex.get("repeatability", 0.5),
            reflex.get("source", 7),
            status,
            reflex.get("hits", 0),
            reflex.get("misses", 0),
            self._now_world(),
            self._now_world(),
        )
        record.update(overrides)

        self.data["experience"][experience_id] = record
        if delete_source:
            reflex["status"] = "archived"
            reflex["archive_reason"] = reflex.get("archive_reason", "moved_to_experience_tombstone")
            reflex["updated_at_world"] = self._now_world()

        self.save()
        return experience_id

    def record_experience_hit(self, experience_id: str | int) -> dict[str, Any]:
        """Increase experience hits by one."""
        return self._increment_counter("experience", experience_id, "hits")

    def record_experience_miss(self, experience_id: str | int) -> dict[str, Any]:
        """Increase experience misses by one."""
        return self._increment_counter("experience", experience_id, "misses")

    def record_reflex_hit(self, reflex_id: str | int) -> dict[str, Any]:
        """Increase reflex hits by one."""
        return self._increment_counter("reflexes", reflex_id, "hits")

    def record_reflex_miss(self, reflex_id: str | int) -> dict[str, Any]:
        """Increase reflex misses by one."""
        return self._increment_counter("reflexes", reflex_id, "misses")

    def _increment_counter(self, section: str, record_id: str | int, field: str) -> dict[str, Any]:
        record_id = str(record_id)
        if section == "experience":
            self._require_experience(record_id)
        else:
            self._require_reflex(record_id)

        self.data[section][record_id][field] = self.data[section][record_id].get(field, 0) + 1
        self.data[section][record_id]["updated_at_world"] = self._now_world()
        self.save()
        return deepcopy(self.data[section][record_id])

    def _find_records(
        self,
        section: str,
        level: int | None = None,
        source: int | None = None,
        status: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        filters = {"level": level, "source": source, "status": status}
        matches = {}
        for record_id, record in self.data[section].items():
            if any(value is not None and record.get(key) != value for key, value in filters.items()):
                continue
            matches[record_id] = deepcopy(record)
        return matches

    def _prepare_new_id(self, section: str, record_id: str | int | None) -> str:
        record_id = str(record_id) if record_id is not None else self._next_id(section)
        if record_id in self.data[section]:
            raise ValueError(f"Record with id {record_id!r} already exists in {section!r}.")
        return record_id

    def _prepare_target_id(self, section: str, record_id: str | int | None) -> str:
        if record_id is None:
            return self._next_id(section)
        return str(record_id)

    def _next_id(self, section: str) -> str:
        used_ids = {
            int(record_id)
            for record_id in self.data[section]
            if str(record_id).isdigit()
        }
        return str(max(used_ids, default=0) + 1)

    def _require_experience(self, experience_id: str) -> None:
        if experience_id not in self.data["experience"]:
            raise ExperienceNotFoundError(
                f"Experience with id {experience_id!r} was not found."
            )

    def _require_reflex(self, reflex_id: str) -> None:
        if reflex_id not in self.data["reflexes"]:
            raise ReflexNotFoundError(f"Reflex with id {reflex_id!r} was not found.")

    @staticmethod
    def _make_experience(
        condition: list[Any],
        actions: list[Any],
        result: list[Any],
        recommendation: list[Any],
        level: int,
        confidence: float,
        repeatability: float,
        source: int,
        status: int,
        hits: int,
        misses: int,
        created_at_world: str | None,
        updated_at_world: str | None,
    ) -> dict[str, Any]:
        now = ExpSMCRUD._now_world()
        return {
            "level": level,
            "if": condition,
            "then": actions,
            "result": result,
            "recommendation": recommendation,
            "confidence": confidence,
            "repeatability": repeatability,
            "source": source,
            "status": status,
            "hits": hits,
            "misses": misses,
            "created_at_world": created_at_world or now,
            "updated_at_world": updated_at_world or now,
        }

    @staticmethod
    def _make_reflex(
        condition: list[Any],
        actions: list[Any],
        result: list[Any],
        recommendation: list[Any],
        priority: int,
        autonomy_level: int,
        confidence: float,
        repeatability: float,
        source: int,
        status: int,
        hits: int,
        misses: int,
        created_from_experience: str | None,
        created_at_world: str | None,
        updated_at_world: str | None,
    ) -> dict[str, Any]:
        now = ExpSMCRUD._now_world()
        return {
            "if": condition,
            "then": actions,
            "result": result,
            "recommendation": recommendation,
            "priority": priority,
            "autonomy_level": autonomy_level,
            "confidence": confidence,
            "repeatability": repeatability,
            "source": source,
            "status": status,
            "hits": hits,
            "misses": misses,
            "created_from_experience": created_from_experience,
            "created_at_world": created_at_world or now,
            "updated_at_world": updated_at_world or now,
        }

    @staticmethod
    def _now_world() -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_crud() -> ExpSMCRUD:
    return ExpSMCRUD(DATA_FILE)


def load_data() -> dict[str, Any]:
    return _default_crud().get_all()


def create_experience(
    condition: list[Any],
    actions: list[Any],
    result: list[Any],
    recommendation: list[Any],
    **fields: Any,
) -> str:
    return _default_crud().create_experience(
        condition,
        actions,
        result,
        recommendation,
        **fields,
    )


def read_experience(experience_id: str | int) -> dict[str, Any]:
    return _default_crud().read_experience(experience_id)


def update_experience(experience_id: str | int, **fields: Any) -> dict[str, Any]:
    return _default_crud().update_experience(experience_id, **fields)


def delete_experience(experience_id: str | int) -> dict[str, Any]:
    return _default_crud().delete_experience(experience_id)


def find_experience(
    level: int | None = None,
    source: int | None = None,
    status: int | None = None,
) -> dict[str, dict[str, Any]]:
    return _default_crud().find_experience(level, source, status)


def create_reflex(
    condition: list[Any],
    actions: list[Any],
    result: list[Any],
    recommendation: list[Any],
    **fields: Any,
) -> str:
    return _default_crud().create_reflex(condition, actions, result, recommendation, **fields)


def read_reflex(reflex_id: str | int) -> dict[str, Any]:
    return _default_crud().read_reflex(reflex_id)


def update_reflex(reflex_id: str | int, **fields: Any) -> dict[str, Any]:
    return _default_crud().update_reflex(reflex_id, **fields)


def delete_reflex(reflex_id: str | int) -> dict[str, Any]:
    return _default_crud().delete_reflex(reflex_id)


def find_reflexes(
    priority: int | None = None,
    source: int | None = None,
    status: int | None = None,
) -> dict[str, dict[str, Any]]:
    return _default_crud().find_reflexes(priority, source, status)


def experience_to_reflex(
    experience_id: str | int,
    reflex_id: str | int | None = None,
    priority: int = 3,
    autonomy_level: int = 2,
    status: int = 1,
    delete_source: bool = False,
    **overrides: Any,
) -> str:
    return _default_crud().experience_to_reflex(
        experience_id,
        reflex_id,
        priority,
        autonomy_level,
        status,
        delete_source,
        **overrides,
    )


def reflex_to_experience(
    reflex_id: str | int,
    experience_id: str | int | None = None,
    level: int = 2,
    status: int = 2,
    delete_source: bool = False,
    **overrides: Any,
) -> str:
    return _default_crud().reflex_to_experience(
        reflex_id,
        experience_id,
        level,
        status,
        delete_source,
        **overrides,
    )


def record_experience_hit(experience_id: str | int) -> dict[str, Any]:
    return _default_crud().record_experience_hit(experience_id)


def record_experience_miss(experience_id: str | int) -> dict[str, Any]:
    return _default_crud().record_experience_miss(experience_id)


def record_reflex_hit(reflex_id: str | int) -> dict[str, Any]:
    return _default_crud().record_reflex_hit(reflex_id)


def record_reflex_miss(reflex_id: str | int) -> dict[str, Any]:
    return _default_crud().record_reflex_miss(reflex_id)
