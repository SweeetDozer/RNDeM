"""CRUD utilities for ExpSM memory.

Data format:
{
    "reflexes": {
        "1": {
            "if": "INPUT DATA",
            "then": ["ACTION"]
        }
    },
    "experience": {
        "1": {
            "if": "INPUT DATA",
            "then": ["ACTION"],
            "repeatability": "high",
            "weight": 0.82,
            "hits": 14
        }
    }
}
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DATA_FILE = Path(__file__).with_name("ExpSM_data.json")
EXPERIENCE_WEIGHT_FROM_REFLEX = 0.95


class ExpSMError(Exception):
    """Base error for ExpSM CRUD operations."""


class ReflexNotFoundError(ExpSMError):
    """Raised when a requested reflex does not exist."""


class ExperienceNotFoundError(ExpSMError):
    """Raised when a requested experience does not exist."""


class ExpSMCRUD:
    """Small JSON-backed CRUD layer for reflexes and experience records."""

    def __init__(self, data_file: str | Path = DATA_FILE) -> None:
        self.data_file = Path(data_file)
        self.data: dict[str, Any] = self.load()

    def load(self) -> dict[str, Any]:
        """Load data from disk and normalize missing top-level keys."""
        if not self.data_file.exists():
            return {"reflexes": {}, "experience": {}}

        with self.data_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        data.setdefault("reflexes", {})
        data.setdefault("experience", {})
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

    def get_reflexes(self) -> dict[str, dict[str, Any]]:
        """Return a copy of all reflexes."""
        return deepcopy(self.data["reflexes"])

    def get_experience(self) -> dict[str, dict[str, Any]]:
        """Return a copy of all experience records."""
        return deepcopy(self.data["experience"])

    def create_reflex(self, condition: Any, actions: list[Any], reflex_id: str | None = None) -> str:
        """Create a reflex and return its id."""
        reflex_id = self._prepare_new_id("reflexes", reflex_id)
        self.data["reflexes"][reflex_id] = self._make_reflex(condition, actions)
        self.save()
        return reflex_id

    def read_reflex(self, reflex_id: str) -> dict[str, Any]:
        """Read one reflex by id."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)
        return deepcopy(self.data["reflexes"][reflex_id])

    def update_reflex(
        self,
        reflex_id: str,
        condition: Any | None = None,
        actions: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing reflex."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)

        if condition is not None:
            self.data["reflexes"][reflex_id]["if"] = condition
        if actions is not None:
            self.data["reflexes"][reflex_id]["then"] = actions

        self.save()
        return deepcopy(self.data["reflexes"][reflex_id])

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
    ) -> dict[str, dict[str, Any]]:
        """Find reflexes by condition and/or one action in the action list."""
        return self._find_records("reflexes", condition, action)

    def create_experience(
        self,
        condition: Any,
        actions: list[Any],
        repeatability: str,
        weight: float,
        hits: int = 0,
        experience_id: str | None = None,
    ) -> str:
        """Create an experience record and return its id."""
        experience_id = self._prepare_new_id("experience", experience_id)
        self.data["experience"][experience_id] = self._make_experience(
            condition,
            actions,
            repeatability,
            weight,
            hits,
        )
        self.save()
        return experience_id

    def read_experience(self, experience_id: str) -> dict[str, Any]:
        """Read one experience record by id."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)
        return deepcopy(self.data["experience"][experience_id])

    def update_experience(
        self,
        experience_id: str,
        condition: Any | None = None,
        actions: list[Any] | None = None,
        repeatability: str | None = None,
        weight: float | None = None,
        hits: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing experience record."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)

        record = self.data["experience"][experience_id]
        if condition is not None:
            record["if"] = condition
        if actions is not None:
            record["then"] = actions
        if repeatability is not None:
            record["repeatability"] = repeatability
        if weight is not None:
            record["weight"] = weight
        if hits is not None:
            record["hits"] = hits

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
        repeatability: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Find experience records by condition, action, and/or repeatability."""
        records = self._find_records("experience", condition, action)

        if repeatability is None:
            return records

        return {
            record_id: record
            for record_id, record in records.items()
            if record.get("repeatability") == repeatability
        }

    def reflex_to_experience(
        self,
        reflex_id: str,
        experience_id: str | None = None,
        repeatability: str = "high",
        hits: int = 0,
        delete_source: bool = False,
    ) -> str:
        """Copy or move a reflex into experience with default weight 0.95."""
        reflex_id = str(reflex_id)
        self._require_reflex(reflex_id)
        experience_id = self._prepare_target_id("experience", experience_id)

        reflex = self.data["reflexes"][reflex_id]
        self.data["experience"][experience_id] = self._make_experience(
            reflex["if"],
            reflex["then"],
            repeatability,
            EXPERIENCE_WEIGHT_FROM_REFLEX,
            hits,
        )

        if delete_source:
            self.data["reflexes"].pop(reflex_id)

        self.save()
        return experience_id

    def experience_to_reflex(
        self,
        experience_id: str,
        reflex_id: str | None = None,
        delete_source: bool = False,
    ) -> str:
        """Copy or move an experience record into reflexes, dropping extra fields."""
        experience_id = str(experience_id)
        self._require_experience(experience_id)
        reflex_id = self._prepare_target_id("reflexes", reflex_id)

        experience = self.data["experience"][experience_id]
        self.data["reflexes"][reflex_id] = self._make_reflex(
            experience["if"],
            experience["then"],
        )

        if delete_source:
            self.data["experience"].pop(experience_id)

        self.save()
        return reflex_id

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

    def _require_reflex(self, reflex_id: str) -> None:
        if reflex_id not in self.data["reflexes"]:
            raise ReflexNotFoundError(f"Reflex with id {reflex_id!r} was not found.")

    def _require_experience(self, experience_id: str) -> None:
        if experience_id not in self.data["experience"]:
            raise ExperienceNotFoundError(
                f"Experience with id {experience_id!r} was not found."
            )

    def _find_records(
        self,
        section: str,
        condition: Any | None = None,
        action: Any | None = None,
    ) -> dict[str, dict[str, Any]]:
        records = {}

        for record_id, record in self.data[section].items():
            if condition is not None and record.get("if") != condition:
                continue
            if action is not None and action not in record.get("then", []):
                continue

            records[record_id] = deepcopy(record)

        return records

    @staticmethod
    def _make_reflex(condition: Any, actions: list[Any]) -> dict[str, Any]:
        return {
            "if": condition,
            "then": actions,
        }

    @staticmethod
    def _make_experience(
        condition: Any,
        actions: list[Any],
        repeatability: str,
        weight: float,
        hits: int,
    ) -> dict[str, Any]:
        return {
            "if": condition,
            "then": actions,
            "repeatability": repeatability,
            "weight": weight,
            "hits": hits,
        }


def _default_crud() -> ExpSMCRUD:
    return ExpSMCRUD(DATA_FILE)


def load_data() -> dict[str, Any]:
    return _default_crud().get_all()


def create_reflex(condition: Any, actions: list[Any], reflex_id: str | None = None) -> str:
    return _default_crud().create_reflex(condition, actions, reflex_id)


def read_reflex(reflex_id: str) -> dict[str, Any]:
    return _default_crud().read_reflex(reflex_id)


def update_reflex(
    reflex_id: str,
    condition: Any | None = None,
    actions: list[Any] | None = None,
) -> dict[str, Any]:
    return _default_crud().update_reflex(reflex_id, condition, actions)


def delete_reflex(reflex_id: str) -> dict[str, Any]:
    return _default_crud().delete_reflex(reflex_id)


def find_reflexes(
    condition: Any | None = None,
    action: Any | None = None,
) -> dict[str, dict[str, Any]]:
    return _default_crud().find_reflexes(condition, action)


def create_experience(
    condition: Any,
    actions: list[Any],
    repeatability: str,
    weight: float,
    hits: int = 0,
    experience_id: str | None = None,
) -> str:
    return _default_crud().create_experience(
        condition,
        actions,
        repeatability,
        weight,
        hits,
        experience_id,
    )


def read_experience(experience_id: str) -> dict[str, Any]:
    return _default_crud().read_experience(experience_id)


def update_experience(
    experience_id: str,
    condition: Any | None = None,
    actions: list[Any] | None = None,
    repeatability: str | None = None,
    weight: float | None = None,
    hits: int | None = None,
) -> dict[str, Any]:
    return _default_crud().update_experience(
        experience_id,
        condition,
        actions,
        repeatability,
        weight,
        hits,
    )


def delete_experience(experience_id: str) -> dict[str, Any]:
    return _default_crud().delete_experience(experience_id)


def find_experience(
    condition: Any | None = None,
    action: Any | None = None,
    repeatability: str | None = None,
) -> dict[str, dict[str, Any]]:
    return _default_crud().find_experience(condition, action, repeatability)


def reflex_to_experience(
    reflex_id: str,
    experience_id: str | None = None,
    repeatability: str = "high",
    hits: int = 0,
    delete_source: bool = False,
) -> str:
    return _default_crud().reflex_to_experience(
        reflex_id,
        experience_id,
        repeatability,
        hits,
        delete_source,
    )


def experience_to_reflex(
    experience_id: str,
    reflex_id: str | None = None,
    delete_source: bool = False,
) -> str:
    return _default_crud().experience_to_reflex(experience_id, reflex_id, delete_source)
