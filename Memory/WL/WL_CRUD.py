"""CRUD utilities for WL text memory."""

from __future__ import annotations

from pathlib import Path


DATA_FILE = Path(__file__).with_name("WL.txt")


class WLError(Exception):
    """Base error for WL CRUD operations."""


class WLCRUD:
    """Small text-file-backed CRUD layer for WL memory."""

    def __init__(self, data_file: str | Path = DATA_FILE) -> None:
        self.data_file = Path(data_file)

    def create(self, text: str, overwrite: bool = False) -> None:
        """Create the text file with content."""
        if self.data_file.exists() and not overwrite:
            raise FileExistsError(f"WL file already exists: {self.data_file}")

        self.write(text)

    def read(self) -> str:
        """Read all text."""
        if not self.data_file.exists():
            return ""

        return self.data_file.read_text(encoding="utf-8")

    def write(self, text: str) -> None:
        """Replace all text."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text(text, encoding="utf-8")

    def append(self, text: str) -> None:
        """Append text to the end of the file."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        with self.data_file.open("a", encoding="utf-8") as file:
            file.write(text)

    def read_lines(self, keepends: bool = False) -> list[str]:
        """Read text as a list of lines."""
        return self.read().splitlines(keepends=keepends)

    def append_line(self, line: str) -> None:
        """Append one line to the file."""
        current_text = self.read()
        prefix = "" if not current_text or current_text.endswith("\n") else "\n"
        self.append(f"{prefix}{line}\n")

    def clear(self) -> None:
        """Clear all text without deleting the file."""
        self.write("")


def _default_crud() -> WLCRUD:
    return WLCRUD(DATA_FILE)


def create(text: str, overwrite: bool = False) -> None:
    _default_crud().create(text, overwrite)


def read() -> str:
    return _default_crud().read()


def write(text: str) -> None:
    _default_crud().write(text)


def append(text: str) -> None:
    _default_crud().append(text)


def read_lines(keepends: bool = False) -> list[str]:
    return _default_crud().read_lines(keepends)


def append_line(line: str) -> None:
    _default_crud().append_line(line)


def clear() -> None:
    _default_crud().clear()
