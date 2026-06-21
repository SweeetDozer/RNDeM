import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from clc.context.window import ContextWindow
from clc.core.activation_ids import aud_activation_id, img_activation_id, sen_activation_id
from clc.core.nfp import NFPFrame
from clc.core.pattern_registry import PatternRegistry
from clc.storage_models.schemas import PatternMatch


class PatternStore:
    """Read-only NFP pattern store for Memory/AKBSM/DB.

    The archive contains experimental .nfp shapes. The parser extracts a stable
    activation-id set from known JSON shapes and falls back to path-based ids for
    nested numeric NFP matrices.
    """

    def __init__(self, db_path: Path, pattern_registry: PatternRegistry | None = None) -> None:
        self.db_path = db_path
        self.pattern_registry = pattern_registry
        self.patterns: dict[str, dict[str, Any]] = {}
        self.pattern_refs: dict[str, str] = {}
        self.activation_sets: dict[str, set[str]] = {}
        self.activation_values: dict[str, dict[str, float]] = {}
        self.warnings: list[str] = []
        self.load()

    def load(self) -> None:
        if not self.db_path.exists():
            self.warnings.append(f"Pattern DB not found: {self.db_path}")
            return
        file_paths = sorted(self.db_path.glob("*.nfp"))
        if self.pattern_registry is None:
            for file_path in file_paths:
                self._load_file(file_path)
            return
        with self.pattern_registry.bulk_update():
            for file_path in file_paths:
                self._load_file(file_path)

    def _load_file(self, file_path: Path) -> None:
        pattern_id = file_path.stem
        try:
            data = json.loads(file_path.read_text(encoding="utf-8-sig"))
            values = self._extract_activation_values(data, pattern_id)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self.warnings.append(f"Skipped {file_path.name}: {exc}")
            return
        self.patterns[pattern_id] = data
        self.pattern_refs[pattern_id] = file_path.as_posix()
        self.activation_values[pattern_id] = values
        self.activation_sets[pattern_id] = {key for key, value in values.items() if value > 0.0}

    def list_patterns(self) -> list[str]:
        return sorted(self.patterns)

    def add_pattern(self, pattern_id: str, activations: dict[str, float], pattern_ref: str = "fallback://memory") -> None:
        self.patterns[pattern_id] = {"activations": dict(activations)}
        self.pattern_refs[pattern_id] = pattern_ref
        self.activation_values[pattern_id] = dict(activations)
        self.activation_sets[pattern_id] = {key for key, value in activations.items() if value > 0.0}

    def load_pattern(self, pattern_id: str) -> dict[str, Any]:
        return self.patterns[pattern_id]

    def get_pattern_ref(self, pattern_id: str) -> str:
        return self.pattern_refs[pattern_id]

    def similarity_to_frame(self, pattern_id: str, frame: NFPFrame) -> float:
        return self._similarity(self.activation_values.get(pattern_id, {}), dict(frame.activations))

    def similarity_to_window(self, pattern_id: str, window: ContextWindow, context_memory: Any) -> float:
        return self._similarity(self.activation_values.get(pattern_id, {}), self._window_activation_values(window, context_memory))

    def find_similar_to_frame(self, frame: NFPFrame, threshold: float = 0.5) -> list[PatternMatch]:
        matches = [
            PatternMatch(pattern_id, self.similarity_to_frame(pattern_id, frame), self.pattern_refs[pattern_id])
            for pattern_id in self.list_patterns()
        ]
        return sorted([match for match in matches if match.similarity >= threshold], key=lambda match: match.similarity, reverse=True)

    def find_similar_to_window(self, window: ContextWindow, context_memory: Any, threshold: float = 0.5) -> list[PatternMatch]:
        matches = [
            PatternMatch(pattern_id, self.similarity_to_window(pattern_id, window, context_memory), self.pattern_refs[pattern_id])
            for pattern_id in self.list_patterns()
        ]
        return sorted([match for match in matches if match.similarity >= threshold], key=lambda match: match.similarity, reverse=True)

    def _window_activation_values(self, window: ContextWindow, context_memory: Any) -> dict[str, float]:
        frame_ids = set(window.frame_ids)
        values: dict[str, float] = {}
        for frame in context_memory.all_frames():
            if frame.frame_id not in frame_ids:
                continue
            for activation_id, activation in frame.activations.items():
                values[activation_id] = max(values.get(activation_id, 0.0), float(activation))
        return values

    def _extract_activation_values(self, data: Any, pattern_id: str) -> dict[str, float]:
        if isinstance(data, Mapping):
            if "activations" in data:
                return self._parse_activations(data["activations"], pattern_id)
            if "img" in data:
                return self._parse_image_matrix(data["img"], pattern_id)
            if "aud" in data:
                return self._parse_audio_sequence(data["aud"], pattern_id)
            if "sen" in data:
                return self._parse_sensor_values(data["sen"])
            if "frames" in data and isinstance(data["frames"], Iterable):
                merged: dict[str, float] = {}
                for index, frame in enumerate(data["frames"]):
                    frame_values = self._extract_activation_values(frame, f"{pattern_id}_f{index}")
                    for activation_id, value in frame_values.items():
                        merged[activation_id] = max(merged.get(activation_id, 0.0), value)
                return merged
            if "nfp" in data:
                if str(data.get("type")) == "1":
                    return self._parse_image_matrix(data["nfp"], pattern_id)
                if str(data.get("type")) == "2":
                    return self._parse_audio_sequence(data["nfp"], pattern_id)
                return self._parse_nfp_blob(data["nfp"], pattern_id)
            return self._parse_activations(data, pattern_id)
        return self._parse_nfp_blob(data, pattern_id)

    def _parse_activations(self, activations: Any, pattern_id: str) -> dict[str, float]:
        if isinstance(activations, Mapping):
            return {self._normalize_activation_id(str(key)): _as_activation(value) for key, value in activations.items()}
        if isinstance(activations, list):
            values: dict[str, float] = {}
            for index, item in enumerate(activations):
                if isinstance(item, Mapping):
                    for key, value in item.items():
                        values[self._normalize_activation_id(str(key))] = _as_activation(value)
                elif isinstance(item, (list, tuple)) and len(item) == 2 and not isinstance(item[0], (list, tuple, dict)):
                    values[self._normalize_activation_id(str(item[0]))] = _as_activation(item[1])
                else:
                    values.update(self._parse_nfp_blob(item, f"{pattern_id}_{index}"))
            return values
        return {}

    def _parse_nfp_blob(self, blob: Any, pattern_id: str) -> dict[str, float]:
        values: dict[str, float] = {}

        def walk(node: Any, path: tuple[int, ...]) -> None:
            if isinstance(node, Mapping):
                for key, value in node.items():
                    values[self._normalize_activation_id(str(key))] = _as_activation(value)
                return
            if isinstance(node, list):
                if node and all(isinstance(item, (int, float)) for item in node):
                    activation_id = f"nfp:{pattern_id}:{'.'.join(str(part) for part in path)}"
                    values[activation_id] = sum(float(item) for item in node) / (len(node) * 255.0)
                    return
                for index, item in enumerate(node):
                    walk(item, path + (index,))

        walk(blob, ())
        return values

    def _parse_image_matrix(self, matrix: Any, pattern_id: str) -> dict[str, float]:
        values: dict[str, float] = {}
        channels = ("r", "g", "b", "m")
        if not isinstance(matrix, list):
            return values
        for y, row in enumerate(matrix):
            if not isinstance(row, list):
                continue
            for x, pixel in enumerate(row):
                if isinstance(pixel, Mapping):
                    for channel, value in pixel.items():
                        values[self._normalize_activation_id(img_activation_id(x, y, str(channel)))] = _as_activation(value)
                elif isinstance(pixel, list):
                    for channel, value in zip(channels, pixel):
                        values[self._normalize_activation_id(img_activation_id(x, y, channel))] = _as_activation(value)
                elif isinstance(pixel, (int, float)):
                    values[self._normalize_activation_id(img_activation_id(x, y, "v"))] = _as_activation(pixel)
        if not values:
            self.warnings.append(f"Pattern {pattern_id} image-like NFP had no parseable pixels")
        return values

    def _parse_audio_sequence(self, sequence: Any, pattern_id: str) -> dict[str, float]:
        values: dict[str, float] = {}
        if not isinstance(sequence, list):
            return values
        for index, item in enumerate(sequence):
            if isinstance(item, Mapping):
                for freq, value in item.items():
                    values[self._normalize_activation_id(aud_activation_id(freq))] = _as_activation(value)
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                values[self._normalize_activation_id(aud_activation_id(item[0]))] = _as_activation(item[1])
            elif isinstance(item, (int, float)):
                values[self._normalize_activation_id(aud_activation_id(index))] = _as_activation(item)
        if not values:
            self.warnings.append(f"Pattern {pattern_id} audio-like NFP had no parseable bins")
        return values

    def _parse_sensor_values(self, sensor_values: Any) -> dict[str, float]:
        if not isinstance(sensor_values, Mapping):
            return {}
        return {self._normalize_activation_id(sen_activation_id(str(key))): _as_activation(value) for key, value in sensor_values.items()}

    def _normalize_activation_id(self, activation_id: str) -> str:
        normalized = activation_id
        if _looks_like_number(activation_id):
            normalized = aud_activation_id(activation_id)
        if self.pattern_registry is None:
            return normalized
        return self.pattern_registry.id(normalized)

    def _similarity(self, stored_values: dict[str, float], input_values: dict[str, float]) -> float:
        stored_ids = {key for key, value in stored_values.items() if value > 0.0}
        input_ids = {key for key, value in input_values.items() if value > 0.0}
        if not stored_ids or not input_ids:
            return 0.0
        intersection = stored_ids.intersection(input_ids)
        union = stored_ids.union(input_ids)
        jaccard = len(intersection) / len(union)
        containment = len(intersection) / len(input_ids)
        if not intersection:
            return 0.0
        value_score = sum(min(stored_values[key], input_values[key]) / max(stored_values[key], input_values[key], 0.0001) for key in intersection) / len(intersection)
        shape_score = max(jaccard, containment)
        return round(shape_score * value_score, 3)


def _as_activation(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if numeric > 1.0:
        numeric = numeric / 255.0
    return max(0.0, min(1.0, numeric))


def _looks_like_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False
