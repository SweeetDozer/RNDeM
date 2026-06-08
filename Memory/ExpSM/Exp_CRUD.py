"""CRUD utilities for ExpSM memory."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DATA_FILE = Path(__file__).with_name("ExpSM_data.json")


class ExpSMError(Exception):
    """Base error for ExpSM CRUD operations."""


class ReflexNotFoundError(ExpSMError):
    """Raised when a requested reflex does not exist."""


class ExperienceNotFoundError(ExpSMError):
    """Raised when a requested experience does not exist."""


class InvalidValueError(ExpSMError):
    """Raised when a value is not allowed by ExpSM_data.json."""


class ExpSMCRUD:
    """JSON-backed CRUD layer for experience records and reflexes."""

    def __init__(self, data_file: str | Path = DATA_FILE) -> None:
        self.data_file = Path(data_file)
        self.data: dict[str, Any] = self.load()

    def load(self) -> dict[str, Any]:
        """Load data from disk and normalize missing top-level keys."""
        if not self.data_file.exists():
            return {"meta": {}, "allowed_values": {}, "experience": {}, "reflexes": {}}

        with self.data_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        data.setdefault("meta", {})
        data.setdefault("allowed_values", {})
        data.setdefault("experience", {})
        data.setdefault("reflexes", {})
        return data

    def save(self) -> None:
        """Save current data to disk."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        with self.data_file.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
            file.write("\n")

    def get_all(self) -> dict[str, Any]:
        """Return a copy of all ExpSM data."""
        return deepcopy(self.data)

    def get_meta(self) -> dict[str, Any]:
        """Return ExpSM metadata."""
        return deepcopy(self.data["meta"])

    def get_allowed_values(self) -> dict[str, list[str]]:
        """Return configured allowed values."""
        return deepcopy(self.data["allowed_values"])

    def get_experience(self) -> dict[str, dict[str, Any]]:
        """Return all experience records."""
        return deepcopy(self.data["experience"])

    def get_reflexes(self) -> dict[str, dict[str, Any]]:
        """Return all reflexes."""
        return deepcopy(self.data["reflexes"])

    def create_experience(
        self,
        condition: Any,
        actions: list[Any],
        result: Any,
        recommendation: Any,
        level: str = "medium",
        confidence: float = 0.5,
        repeatability: float = 0.5,
        source: str = "unknown",
        status: str = "hypothesis",
        hits: int = 0,
        misses: int = 0,
        experience_id: str | None = None,
        created_at_world: str | None = None,
        updated_at_world: str | None = None,
        **extra_fields: Any,
    ) -> str:
        """Create an experience record and return its id."""
        experience_id = self._prepare_new_id("experience", experience_id)
        record = self._make_experience(
            condition=condition,
            actions=actions,
            result=result,
            recommendation=recommendation,
            level=level,
            confidence=confidence,
            repeatability=repeatability,
            source=source,
            status=status,
            hits=hits,
            misses=misses,
            created_at_world=created_at_world,
            updated_at_world=updated_at_world,
        )
        record.update(extra_fields)

        self._validate_experience(record)
        self.data["experience"][experience_id] = record
        self.save()
        return experience_id

    def read_experience(self, experience_id: str) -> dict[str, Any]:
        """Read one experience record by id."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)
        return deepcopy(self.data["experience"][experience_id])

    def update_experience(self, experience_id: str, **fields: Any) -> dict[str, Any]:
        """Update fields of an existing experience record."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)

        record = deepcopy(self.data["experience"][experience_id])
        record.update(fields)
        record.setdefault("updated_at_world", self._now_world())
        if "updated_at_world" not in fields:
            record["updated_at_world"] = self._now_world()

        self._validate_experience(record)
        self.data["experience"][experience_id] = record
        self.save()
        return deepcopy(record)

    def delete_experience(self, experience_id: str) -> dict[str, Any]:
        """Delete an experience record by id."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)
        deleted_experience = self.data["experience"].pop(experience_id)
        self.save()
        return deepcopy(deleted_experience)

    def find_experience(
        self,
        condition: Any | None = None,
        action: Any | None = None,
        level: str | None = None,
        source: str | None = None,
        status: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Find experience records matching provided filters."""
        return self._find_records("experience", condition, action, level, source, status)

    def create_reflex(
        self,
        condition: Any,
        actions: list[Any],
        result: Any,
        recommendation: Any,
        priority: str = "normal",
        autonomy_level: int = 2,
        confidence: float = 0.5,
        repeatability: float = 0.5,
        source: str = "unknown",
        status: str = "active",
        hits: int = 0,
        misses: int = 0,
        created_from_experience: str | None = None,
        reflex_id: str | None = None,
        created_at_world: str | None = None,
        updated_at_world: str | None = None,
        **extra_fields: Any,
    ) -> str:
        """Create a reflex and return its id."""
        reflex_id = self._prepare_new_id("reflexes", reflex_id)
        record = self._make_reflex(
            condition=condition,
            actions=actions,
            result=result,
            recommendation=recommendation,
            priority=priority,
            autonomy_level=autonomy_level,
            confidence=confidence,
            repeatability=repeatability,
            source=source,
            status=status,
            hits=hits,
            misses=misses,
            created_from_experience=created_from_experience,
            created_at_world=created_at_world,
            updated_at_world=updated_at_world,
        )
        record.update(extra_fields)

        self._validate_reflex(record)
        self.data["reflexes"][reflex_id] = record
        self.save()
        return reflex_id

    def read_reflex(self, reflex_id: str) -> dict[str, Any]:
        """Read one reflex by id."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)
        return deepcopy(self.data["reflexes"][reflex_id])

    def update_reflex(self, reflex_id: str, **fields: Any) -> dict[str, Any]:
        """Update fields of an existing reflex."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)

        record = deepcopy(self.data["reflexes"][reflex_id])
        record.update(fields)
        if "updated_at_world" not in fields:
            record["updated_at_world"] = self._now_world()

        self._validate_reflex(record)
        self.data["reflexes"][reflex_id] = record
        self.save()
        return deepcopy(record)

    def delete_reflex(self, reflex_id: str) -> dict[str, Any]:
        """Delete a reflex by id."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)
        deleted_reflex = self.data["reflexes"].pop(reflex_id)
        self.save()
        return deepcopy(deleted_reflex)

    def find_reflexes(
        self,
        condition: Any | None = None,
        action: Any | None = None,
        priority: str | None = None,
        source: str | None = None,
        status: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Find reflexes matching provided filters."""
        records = self._find_records("reflexes", condition, action, None, source, status)
        if priority is None:
            return records

        return {
            record_id: record
            for record_id, record in records.items()
            if record.get("priority") == priority
        }

    def reflex_to_experience(
        self,
        reflex_id: str,
        experience_id: str | None = None,
        delete_source: bool = False,
        **overrides: Any,
    ) -> str:
        """Copy or move a reflex into experience, dropping reflex-only fields."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)
        experience_id = self._prepare_target_id("experience", experience_id)

        reflex = self.data["reflexes"][reflex_id]
        record = self._make_experience(
            condition=reflex["if"],
            actions=reflex["then"],
            result=reflex.get("result"),
            recommendation=reflex.get("recommendation"),
            level=self._priority_to_level(reflex.get("priority")),
            confidence=reflex.get("confidence", 0.5),
            repeatability=reflex.get("repeatability", 0.5),
            source=reflex.get("source", "unknown"),
            status=reflex.get("status", "hypothesis"),
            hits=reflex.get("hits", 0),
            misses=reflex.get("misses", 0),
            created_at_world=self._now_world(),
            updated_at_world=self._now_world(),
        )
        record.update(overrides)

        self._validate_experience(record)
        self.data["experience"][experience_id] = record

        if delete_source:
            self.data["reflexes"].pop(reflex_id)

        self.save()
        return experience_id

    def experience_to_reflex(
        self,
        experience_id: str,
        reflex_id: str | None = None,
        delete_source: bool = False,
        priority: str = "normal",
        autonomy_level: int = 2,
        **overrides: Any,
    ) -> str:
        """Copy or move an experience record into reflexes."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)
        reflex_id = self._prepare_target_id("reflexes", reflex_id)

        experience = self.data["experience"][experience_id]
        record = self._make_reflex(
            condition=experience["if"],
            actions=experience["then"],
            result=experience.get("result"),
            recommendation=experience.get("recommendation"),
            priority=priority,
            autonomy_level=autonomy_level,
            confidence=experience.get("confidence", 0.5),
            repeatability=experience.get("repeatability", 0.5),
            source=experience.get("source", "unknown"),
            status=experience.get("status", "active"),
            hits=experience.get("hits", 0),
            misses=experience.get("misses", 0),
            created_from_experience=experience_id,
            created_at_world=self._now_world(),
            updated_at_world=self._now_world(),
        )
        record.update(overrides)

        self._validate_reflex(record)
        self.data["reflexes"][reflex_id] = record

        if delete_source:
            self.data["experience"].pop(experience_id)

        self.save()
        return reflex_id

    def record_experience_hit(self, experience_id: str) -> dict[str, Any]:
        """Increase experience hits by one."""
        return self._increment_counter("experience", experience_id, "hits")

    def record_experience_miss(self, experience_id: str) -> dict[str, Any]:
        """Increase experience misses by one."""
        return self._increment_counter("experience", experience_id, "misses")

    def record_reflex_hit(self, reflex_id: str) -> dict[str, Any]:
        """Increase reflex hits by one."""
        return self._increment_counter("reflexes", reflex_id, "hits")

    def record_reflex_miss(self, reflex_id: str) -> dict[str, Any]:
        """Increase reflex misses by one."""
        return self._increment_counter("reflexes", reflex_id, "misses")

    def _increment_counter(self, section: str, record_id: str, field: str) -> dict[str, Any]:
        record_id = str(record_id)
        if section == "experience":
            self._require_experience(record_id)
        else:
            self._require_reflex(record_id)

        self.data[section][record_id][field] = self.data[section][record_id].get(field, 0) + 1
        self.data[section][record_id]["updated_at_world"] = self._now_world()
        self.save()
        return deepcopy(self.data[section][record_id])

    def _prepare_new_id(self, section: str, record_id: str | None) -> str:
        record_id = str(record_id) if record_id is not None else self._next_id(section)

        if record_id in self.data[section]:
            raise ValueError(f"Record with id {record_id!r} already exists in {section!r}.")

        return record_id

    def _prepare_target_id(self, section: str, record_id: str | None) -> str:
        if record_id is None:
            return self._next_id(section)
        return str(record_id)

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

    def _require_experience(self, experience_id: str) -> None:
        if experience_id not in self.data["experience"]:
            raise ExperienceNotFoundError(
                f"Experience with id {experience_id!r} was not found."
            )

    def _require_reflex(self, reflex_id: str) -> None:
        if reflex_id not in self.data["reflexes"]:
            raise ReflexNotFoundError(f"Reflex with id {reflex_id!r} was not found.")

    def _find_records(
        self,
        section: str,
        condition: Any | None,
        action: Any | None,
        level: str | None,
        source: str | None,
        status: str | None,
    ) -> dict[str, dict[str, Any]]:
        matches = {}
        for record_id, record in self.data[section].items():
            if condition is not None and record.get("if") != condition:
                continue
            if action is not None and action not in record.get("then", []):
                continue
            if level is not None and record.get("level") != level:
                continue
            if source is not None and record.get("source") != source:
                continue
            if status is not None and record.get("status") != status:
                continue
            matches[record_id] = deepcopy(record)

        return matches

    def _validate_experience(self, record: dict[str, Any]) -> None:
        self._validate_allowed("experience_level", record.get("level"))
        self._validate_allowed("source", record.get("source"))
        self._validate_allowed("status", record.get("status"))

    def _validate_reflex(self, record: dict[str, Any]) -> None:
        self._validate_allowed("priority", record.get("priority"))
        self._validate_allowed("source", record.get("source"))
        self._validate_allowed("status", record.get("status"))

    def _validate_allowed(self, name: str, value: Any) -> None:
        allowed = self.data["allowed_values"].get(name)
        if allowed and value not in allowed:
            raise InvalidValueError(f"{value!r} is not allowed for {name!r}.")

    @staticmethod
    def _make_experience(
        condition: Any,
        actions: list[Any],
        result: Any,
        recommendation: Any,
        level: str,
        confidence: float,
        repeatability: float,
        source: str,
        status: str,
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
        condition: Any,
        actions: list[Any],
        result: Any,
        recommendation: Any,
        priority: str,
        autonomy_level: int,
        confidence: float,
        repeatability: float,
        source: str,
        status: str,
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
    def _priority_to_level(priority: Any) -> str:
        if priority == "low":
            return "low"
        if priority in {"high", "critical"}:
            return "high"
        return "medium"

    @staticmethod
    def _now_world() -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_crud() -> ExpSMCRUD:
    return ExpSMCRUD(DATA_FILE)


def load_data() -> dict[str, Any]:
    return _default_crud().get_all()


def create_experience(
    condition: Any,
    actions: list[Any],
    result: Any,
    recommendation: Any,
    **fields: Any,
) -> str:
    return _default_crud().create_experience(condition, actions, result, recommendation, **fields)


def read_experience(experience_id: str) -> dict[str, Any]:
    return _default_crud().read_experience(experience_id)


def update_experience(experience_id: str, **fields: Any) -> dict[str, Any]:
    return _default_crud().update_experience(experience_id, **fields)


def delete_experience(experience_id: str) -> dict[str, Any]:
    return _default_crud().delete_experience(experience_id)


def find_experience(
    condition: Any | None = None,
    action: Any | None = None,
    level: str | None = None,
    source: str | None = None,
    status: str | None = None,
) -> dict[str, dict[str, Any]]:
    return _default_crud().find_experience(condition, action, level, source, status)


def create_reflex(
    condition: Any,
    actions: list[Any],
    result: Any,
    recommendation: Any,
    **fields: Any,
) -> str:
    return _default_crud().create_reflex(condition, actions, result, recommendation, **fields)


def read_reflex(reflex_id: str) -> dict[str, Any]:
    return _default_crud().read_reflex(reflex_id)


def update_reflex(reflex_id: str, **fields: Any) -> dict[str, Any]:
    return _default_crud().update_reflex(reflex_id, **fields)


def delete_reflex(reflex_id: str) -> dict[str, Any]:
    return _default_crud().delete_reflex(reflex_id)


def find_reflexes(
    condition: Any | None = None,
    action: Any | None = None,
    priority: str | None = None,
    source: str | None = None,
    status: str | None = None,
) -> dict[str, dict[str, Any]]:
    return _default_crud().find_reflexes(condition, action, priority, source, status)


def reflex_to_experience(
    reflex_id: str,
    experience_id: str | None = None,
    delete_source: bool = False,
    **overrides: Any,
) -> str:
    return _default_crud().reflex_to_experience(
        reflex_id,
        experience_id,
        delete_source,
        **overrides,
    )


def experience_to_reflex(
    experience_id: str,
    reflex_id: str | None = None,
    delete_source: bool = False,
    priority: str = "normal",
    autonomy_level: int = 2,
    **overrides: Any,
) -> str:
    return _default_crud().experience_to_reflex(
        experience_id,
        reflex_id,
        delete_source,
        priority,
        autonomy_level,
        **overrides,
    )


def record_experience_hit(experience_id: str) -> dict[str, Any]:
    return _default_crud().record_experience_hit(experience_id)


def record_experience_miss(experience_id: str) -> dict[str, Any]:
    return _default_crud().record_experience_miss(experience_id)


def record_reflex_hit(reflex_id: str) -> dict[str, Any]:
    return _default_crud().record_reflex_hit(reflex_id)


def record_reflex_miss(reflex_id: str) -> dict[str, Any]:
    return _default_crud().record_reflex_miss(reflex_id)
