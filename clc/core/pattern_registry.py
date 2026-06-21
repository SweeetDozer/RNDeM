from dataclasses import dataclass, field
from contextlib import contextmanager
import json
from pathlib import Path
import re
from typing import Any


MANIFEST_SCHEMA_VERSION = 1
DEFAULT_MANIFEST_PATH = Path("Memory") / "pattern_manifest.json"
PATTERN_ID_RE = re.compile(r"^pat_(\d{4,})$")
ALLOWED_SEMANTIC_CLASSES = {
    "input",
    "label",
    "prediction",
    "action",
    "decision",
    "effect",
    "outcome",
    "memory",
    "consolidation",
    "evaluation",
    "target",
    "akbsm",
    "expsm",
    "audit",
    "system",
    "tone",
    "retention",
    "debug",
    "unknown",
}
ALLOWED_LEARNABILITY_VALUES = {"normal", "non_learnable", "internal_only", "unknown"}


@dataclass
class PatternRegistry:
    """Stable mapping between internal pattern ids and human debug names."""

    manifest_path: Path | str = DEFAULT_MANIFEST_PATH
    _name_to_id: dict[str, str] = field(default_factory=dict, init=False)
    _id_to_name: dict[str, str] = field(default_factory=dict, init=False)
    _semantics_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _next_pattern_number: int = field(default=1, init=False)
    _bulk_depth: int = field(default=0, init=False)
    _dirty: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.manifest_path = Path(self.manifest_path)
        created_or_extended = self._load_manifest()
        for name in DEFAULT_PATTERN_NAMES:
            if name not in self._name_to_id:
                self._register_new(name)
                created_or_extended = True
        self.validate()
        if created_or_extended:
            self.save()

    @property
    def pattern_count(self) -> int:
        return len(self._name_to_id)

    @property
    def next_pattern_number(self) -> int:
        return self._next_pattern_number

    def register(self, debug_name: str) -> str:
        return self.register_if_missing(debug_name)

    def register_if_missing(self, name: str) -> str:
        if name in self._name_to_id:
            return self._name_to_id[name]
        pattern_id = self._register_new(name)
        if self._bulk_depth == 0:
            self.validate()
        self._mark_dirty()
        return pattern_id

    def id(self, debug_name: str) -> str:
        return self.register_if_missing(debug_name)

    def name(self, pattern_id: str) -> str:
        return self._id_to_name.get(pattern_id, pattern_id)

    def debug_name(self, pattern_id: str) -> str:
        return self.name(pattern_id)

    def semantic_class(self, pattern_id: str) -> str:
        metadata = self._semantics_by_id.get(pattern_id)
        if not isinstance(metadata, dict):
            return "unknown"
        semantic_class = metadata.get("semantic_class")
        return str(semantic_class) if semantic_class in ALLOWED_SEMANTIC_CLASSES else "unknown"

    def tags(self, pattern_id: str) -> set[str]:
        metadata = self._semantics_by_id.get(pattern_id)
        if not isinstance(metadata, dict):
            return set()
        tags = metadata.get("tags", [])
        if not isinstance(tags, list):
            return set()
        return {str(tag) for tag in tags if isinstance(tag, str) and tag}

    def has_tag(self, pattern_id: str, tag: str) -> bool:
        return tag in self.tags(pattern_id)

    def is_action(self, pattern_id: str) -> bool:
        return self.semantic_class(pattern_id) == "action" or self.has_tag(pattern_id, "action")

    def is_memory(self, pattern_id: str) -> bool:
        return self.semantic_class(pattern_id) == "memory" or self.has_tag(pattern_id, "memory")

    def is_audit(self, pattern_id: str) -> bool:
        return self.semantic_class(pattern_id) == "audit" or self.has_tag(pattern_id, "audit")

    def learnability(self, pattern_id: str) -> str:
        metadata = self._semantics_by_id.get(pattern_id)
        if not isinstance(metadata, dict):
            return "unknown"
        learnability = metadata.get("learnability")
        return str(learnability) if learnability in ALLOWED_LEARNABILITY_VALUES else "unknown"

    def is_internal_only(self, pattern_id: str) -> bool:
        return self.learnability(pattern_id) == "internal_only" or self.has_tag(pattern_id, "internal")

    def is_non_learnable(self, pattern_id: str) -> bool:
        return self.learnability(pattern_id) in {"non_learnable", "internal_only"} or self.has_tag(pattern_id, "non_learnable")

    def has_name(self, name: str) -> bool:
        return name in self._name_to_id

    def has_id(self, pattern_id: str) -> bool:
        return pattern_id in self._id_to_name

    def validate(self) -> None:
        _validate_manifest_data(
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "next_pattern_number": self._next_pattern_number,
                "patterns": self._name_to_id,
                "ids": self._id_to_name,
                "semantics": self._semantics_by_id,
            },
            self.manifest_path,
        )

    def save(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "next_pattern_number": self._next_pattern_number,
            "patterns": dict(sorted(self._name_to_id.items())),
            "ids": dict(sorted(self._id_to_name.items())),
            "semantics": {pattern_id: self._semantics_by_id[pattern_id] for pattern_id in sorted(self._semantics_by_id)},
        }
        tmp_path = self.manifest_path.with_name(f"{self.manifest_path.name}.tmp")
        tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(self.manifest_path)
        self._dirty = False

    @contextmanager
    def bulk_update(self):
        self._bulk_depth += 1
        try:
            yield self
        finally:
            self._bulk_depth -= 1
            if self._bulk_depth == 0 and self._dirty:
                self.validate()
                self.save()

    def _load_manifest(self) -> bool:
        if not self.manifest_path.exists():
            self._name_to_id = {}
            self._id_to_name = {}
            self._semantics_by_id = {}
            self._next_pattern_number = 1
            return True
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid PatternRegistry manifest {self.manifest_path}: {exc}") from exc
        _validate_manifest_data(data, self.manifest_path)
        self._name_to_id = {str(name): str(pattern_id) for name, pattern_id in data["patterns"].items()}
        self._id_to_name = {str(pattern_id): str(name) for pattern_id, name in data["ids"].items()}
        self._semantics_by_id = _load_semantics(data, self._id_to_name)
        self._next_pattern_number = int(data["next_pattern_number"])
        return False

    def _register_new(self, name: str) -> str:
        if not name:
            raise ValueError("PatternRegistry cannot register an empty pattern name")
        while True:
            pattern_id = f"pat_{self._next_pattern_number:04d}"
            self._next_pattern_number += 1
            if pattern_id not in self._id_to_name:
                break
        self._name_to_id[name] = pattern_id
        self._id_to_name[pattern_id] = name
        self._semantics_by_id[pattern_id] = infer_pattern_semantics(name)
        return pattern_id

    def _mark_dirty(self) -> None:
        self._dirty = True
        if self._bulk_depth == 0:
            self.save()


def _validate_manifest_data(data: Any, path: Path) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"PatternRegistry manifest {path} must be a JSON object")
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"PatternRegistry manifest {path} has unsupported schema_version={data.get('schema_version')}"
        )
    patterns = data.get("patterns")
    ids = data.get("ids")
    if not isinstance(patterns, dict) or not isinstance(ids, dict):
        raise ValueError(f"PatternRegistry manifest {path} must contain object fields 'patterns' and 'ids'")
    normalized_patterns: dict[str, str] = {}
    normalized_ids: dict[str, str] = {}
    for name, pattern_id in patterns.items():
        name = str(name)
        pattern_id = str(pattern_id)
        if not name:
            raise ValueError(f"PatternRegistry manifest {path} contains an empty pattern name")
        if not PATTERN_ID_RE.match(pattern_id):
            raise ValueError(f"PatternRegistry manifest {path} contains invalid pattern id {pattern_id!r}")
        if name in normalized_patterns:
            raise ValueError(f"PatternRegistry manifest {path} contains duplicate pattern name {name!r}")
        if pattern_id in normalized_ids:
            raise ValueError(f"PatternRegistry manifest {path} maps id {pattern_id!r} to multiple names")
        normalized_patterns[name] = pattern_id
        normalized_ids[pattern_id] = name
    provided_ids = {str(pattern_id): str(name) for pattern_id, name in ids.items()}
    if normalized_ids != provided_ids:
        raise ValueError(f"PatternRegistry manifest {path} has inconsistent 'patterns' and 'ids' mappings")
    max_number = 0
    for pattern_id in normalized_ids:
        match = PATTERN_ID_RE.match(pattern_id)
        if match is None:
            raise ValueError(f"PatternRegistry manifest {path} contains invalid pattern id {pattern_id!r}")
        max_number = max(max_number, int(match.group(1)))
    try:
        next_pattern_number = int(data.get("next_pattern_number"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"PatternRegistry manifest {path} has invalid next_pattern_number") from exc
    if next_pattern_number <= max_number:
        raise ValueError(
            f"PatternRegistry manifest {path} next_pattern_number={next_pattern_number} "
            f"must be greater than max existing id number {max_number}"
        )
    semantics = data.get("semantics", {})
    if semantics is not None and not isinstance(semantics, dict):
        raise ValueError(f"PatternRegistry manifest {path} field 'semantics' must be an object when present")
    for pattern_id, metadata in (semantics or {}).items():
        pattern_id = str(pattern_id)
        if pattern_id not in normalized_ids:
            raise ValueError(f"PatternRegistry manifest {path} contains semantics for unknown id {pattern_id!r}")
        _validate_semantic_metadata(metadata, path, pattern_id)


def _load_semantics(data: dict[str, Any], id_to_name: dict[str, str]) -> dict[str, dict[str, Any]]:
    raw_semantics = data.get("semantics", {})
    if not isinstance(raw_semantics, dict):
        raw_semantics = {}
    semantics: dict[str, dict[str, Any]] = {}
    for pattern_id, name in id_to_name.items():
        metadata = raw_semantics.get(pattern_id)
        if isinstance(metadata, dict):
            semantics[pattern_id] = _normalized_semantic_metadata(metadata)
        else:
            semantics[pattern_id] = infer_pattern_semantics(name)
    return semantics


def _validate_semantic_metadata(metadata: Any, path: Path, pattern_id: str) -> None:
    if not isinstance(metadata, dict):
        raise ValueError(f"PatternRegistry manifest {path} semantics[{pattern_id!r}] must be an object")
    normalized = _normalized_semantic_metadata(metadata)
    if normalized["semantic_class"] not in ALLOWED_SEMANTIC_CLASSES:
        raise ValueError(f"PatternRegistry manifest {path} semantics[{pattern_id!r}].semantic_class is invalid")
    if normalized["learnability"] not in ALLOWED_LEARNABILITY_VALUES:
        raise ValueError(f"PatternRegistry manifest {path} semantics[{pattern_id!r}].learnability is invalid")
    if not isinstance(metadata.get("tags"), list) or not all(isinstance(tag, str) for tag in metadata.get("tags", [])):
        raise ValueError(f"PatternRegistry manifest {path} semantics[{pattern_id!r}].tags must be list[str]")


def _normalized_semantic_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    semantic_class = metadata.get("semantic_class")
    if semantic_class not in ALLOWED_SEMANTIC_CLASSES:
        semantic_class = "unknown"
    tags = metadata.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    learnability = metadata.get("learnability")
    if learnability not in ALLOWED_LEARNABILITY_VALUES:
        learnability = "unknown"
    return {
        "semantic_class": semantic_class,
        "tags": sorted({tag for tag in tags if isinstance(tag, str) and tag}),
        "learnability": learnability,
    }


def infer_pattern_semantics(name: str) -> dict[str, Any]:
    semantic_class = "unknown"
    tags: set[str] = set()
    learnability = "unknown"
    ordinary_actions = {
        "action_increase_attention",
        "action_preserve_integrity",
        "action_reduce_load",
        "action_wait_more_data",
        "action_continue_observation",
        "action_inspect_pattern",
        "action_generate_more_thought",
    }
    ordinary_effects = {
        "state_attention_increased",
        "state_integrity_preservation",
        "state_load_reduced",
        "state_observation_continues",
        "state_pattern_inspection",
        "state_waiting_for_more_data",
        "state_more_thought_requested",
    }
    mode_management = {
        "action_enter_consolidation_mode",
        "action_exit_consolidation_mode",
        "state_consolidation_mode_entered",
        "state_consolidation_mode_exited",
        "system_mode_active",
        "system_mode_consolidation",
        "system_mode_recovery",
    }
    consolidation_internal = {
        "state_consolidation_processing",
        "state_pending_candidates_reviewed",
        "state_context_load_reduced",
        "state_memory_candidate_created",
        "action_commit_memory_draft",
        "state_memory_draft_commit_requested",
        "committed_draft_observed",
        "committed_draft_strengthened",
        "committed_draft_pending_expsm_update",
        "action_review_committed_memory_update",
        "state_committed_memory_update_review_requested",
        "action_update_committed_expsm_record",
        "state_committed_expsm_update_requested",
        "state_memory_updated",
        "state_memory_update_failed",
    }
    maintenance = {
        "consolidation_pressure",
        "consolidation_pressure_low",
        "consolidation_pressure_medium",
        "consolidation_pressure_high",
    }
    memory_write_tags = {
        "memory_write_review": "memory_write_review",
        "memory_draft_written": "memory_draft_written",
        "memory_draft_commit_review": "memory_draft_commit_review",
        "memory_committed": "memory_committed",
        "committed_draft_observed": "committed_draft_observed",
        "expsm_update_review": "expsm_update_review",
        "memory_updated": "memory_updated",
        "value_feedback_review": "value_feedback_review",
        "value_feedback_updated": "value_feedback_updated",
        "module_update": "module_update",
        "system_mode_change": "system_mode_change",
    }
    draft_family_tags = {
        "action_preserve_integrity": {"draft_family_integrity"},
        "state_integrity_preservation": {"draft_family_integrity"},
        "tone_stability_low": {"draft_family_integrity"},
        "tone_integrity_low": {"draft_family_integrity"},
        "tone_risk_sensitivity_high": {"draft_family_integrity"},
        "internal_instability": {"draft_family_integrity"},
        "internal_preserve_integrity": {"draft_family_integrity"},
        "experienced_risk_pattern": {"draft_family_integrity"},
        "internal_state_risk": {"draft_family_integrity"},
        "sen_integrity_warning": {"draft_family_integrity"},
        "sen_resource_pressure": {"draft_family_integrity", "draft_family_load"},
        "action_reduce_load": {"draft_family_load"},
        "state_load_reduced": {"draft_family_load"},
        "tone_fatigue_high": {"draft_family_load"},
        "tone_tension_high": {"draft_family_load"},
        "sen_memory_pressure": {"draft_family_load"},
        "action_increase_attention": {"draft_family_attention"},
        "state_attention_increased": {"draft_family_attention"},
        "periodic_audio_pattern": {"draft_family_attention"},
        "novel_activation_pattern": {"draft_family_attention", "draft_family_inspection"},
        "prediction_future_state": {"draft_family_attention"},
        "internal_attention_audio": {"draft_family_attention"},
        "internal_attention_visual": {"draft_family_attention", "visual_attention"},
        "label_novelty": {"draft_family_attention", "draft_family_inspection"},
        "label_risk": {"draft_family_attention"},
        "action_inspect_pattern": {"draft_family_inspection"},
        "state_pattern_inspection": {"draft_family_inspection"},
        "known_memory_pattern": {"draft_family_inspection"},
        "related_memory_pattern": {"draft_family_inspection"},
    }

    if "decision_audit" in name:
        semantic_class = "audit"
        tags.update({"audit", "decision_audit"})
    elif "action_guard_audit" in name:
        semantic_class = "audit"
        tags.update({"audit", "guard_audit"})
    elif "decision_cycle" in name:
        semantic_class = "audit"
        tags.update({"audit", "cycle_summary"})
    elif name.startswith(("aud_", "img_", "sen_")):
        semantic_class = "input"
        tags.add("input")
        if name.startswith("aud_"):
            tags.add("audio_input")
        elif name.startswith("img_"):
            tags.add("visual_input")
        elif name.startswith("sen_"):
            tags.add("sensor_input")
    elif name.startswith("action_"):
        semantic_class = "action"
        tags.update({"action", "runtime"})
        learnability = "normal"
        if name in ordinary_actions:
            tags.add("ordinary_action")
    elif name.startswith("label_") or name.endswith("_pattern") or "label" in name:
        semantic_class = "label"
        tags.add("label")
    elif name.startswith("prediction_") or name.startswith("future_") or "prediction" in name:
        semantic_class = "prediction"
        tags.add("prediction")
    elif name.startswith("state_"):
        semantic_class = "effect"
        tags.add("effect")
        if name in ordinary_effects:
            tags.add("ordinary_effect")
    elif name.startswith("outcome_"):
        semantic_class = "outcome"
        tags.add("outcome")
    elif name.startswith("memory_") or name.startswith("draft_commit") or name.startswith("committed_draft"):
        semantic_class = "memory"
        tags.add("memory")
    elif name.startswith("consolidation_"):
        semantic_class = "consolidation"
        tags.add("consolidation")
    elif name.startswith("evaluation_") or name.startswith("value_") or "value_feedback" in name:
        semantic_class = "evaluation"
        tags.add("evaluation")
        if "value_feedback" in name or name.startswith("value_"):
            tags.add("value_feedback")
    elif name.startswith("akbsm_"):
        semantic_class = "akbsm"
        tags.update({"akbsm", "association"})
    elif name.startswith("expsm_"):
        semantic_class = "expsm"
        tags.add("expsm")
        if "mechanism" in name:
            tags.add("mechanism")
    elif name.startswith("target_") or "target_" in name:
        semantic_class = "target"
        tags.add("target")
    elif name.startswith("system_"):
        semantic_class = "system"
        tags.add("system")
    elif name.startswith("tone_") or name.startswith("high_") or name.startswith("homeostasis_"):
        semantic_class = "tone"
        tags.add("tone")
        if name.startswith("homeostasis_"):
            tags.add("internal")
    elif "retention" in name:
        semantic_class = "retention"
        tags.add("retention")
    elif name.startswith("debug_"):
        semantic_class = "debug"
        tags.add("debug")
    elif name.startswith("internal_") or name.startswith("thought_") or name.startswith("learnability_"):
        semantic_class = "system"
        tags.add("internal")

    if name in mode_management:
        tags.update({"mode_management", "non_learnable", "internal"})
        learnability = "internal_only"
    if name in consolidation_internal:
        tags.update({"consolidation_internal", "non_learnable", "internal"})
        learnability = "internal_only"
    if name in maintenance:
        tags.update({"maintenance", "non_learnable", "internal"})
        learnability = "internal_only"
    if name in memory_write_tags:
        tags.update({"memory_write_technical", memory_write_tags[name]})
    if name in draft_family_tags:
        tags.update(draft_family_tags[name])
    if name in {"internal_learning_candidate", "prediction_future_state"}:
        tags.add("generic_draft_context")
    if name == "outcome_confirmed":
        tags.add("confirmed_outcome")
    if name.startswith("homeostasis_"):
        tags.update({"homeostasis", "non_learnable", "internal"})
        learnability = "internal_only"

    if semantic_class in {"audit", "memory", "consolidation", "evaluation", "target", "akbsm", "expsm", "system", "tone", "retention", "debug"}:
        tags.add("non_learnable")
        if learnability == "unknown":
            learnability = "internal_only"
    elif learnability == "unknown" and semantic_class in {"input", "label", "prediction", "effect", "outcome"}:
        learnability = "normal"

    return {
        "semantic_class": semantic_class,
        "tags": sorted(tags),
        "learnability": learnability,
    }


DEFAULT_PATTERN_NAMES = (
    "aud_freq_440",
    "aud_freq_880",
    "aud_freq_1200",
    "img_x0_y0_r",
    "img_x0_y0_g",
    "img_x0_y0_b",
    "img_x1_y0_r",
    "img_x1_y0_g",
    "img_x1_y0_b",
    "img_x0_y1_r",
    "img_x0_y1_g",
    "img_x0_y1_b",
    "img_x1_y1_r",
    "img_x1_y1_g",
    "img_x1_y1_b",
    "sen_cpu_temp_high",
    "sen_memory_pressure",
    "sen_integrity_warning",
    "sen_resource_pressure",
    "periodic_audio_pattern",
    "novel_activation_pattern",
    "experienced_risk_pattern",
    "internal_state_risk",
    "label_risk",
    "label_novelty",
    "known_memory_pattern",
    "contradiction_pattern",
    "future_state",
    "prediction_future_state",
    "internal_attention_audio",
    "internal_tension",
    "internal_instability",
    "internal_preserve_integrity",
    "internal_learning_candidate",
    "internal_attention_visual",
    "thought_need_more_data",
    "thought_increase_attention",
    "thought_inspect_pattern",
    "thought_store_candidate",
    "thought_preserve_integrity",
    "thought_reduce_load",
    "tone_tension",
    "tone_curiosity",
    "tone_risk_sensitivity",
    "tone_integrity_low",
    "tone_fatigue",
    "action_wait_more_data",
    "action_increase_attention",
    "action_inspect_pattern",
    "action_store_memory_candidate",
    "action_reduce_load",
    "action_preserve_integrity",
    "action_continue_observation",
    "action_generate_more_thought",
    "state_waiting_for_more_data",
    "state_attention_increased",
    "state_pattern_inspection",
    "state_memory_candidate_created",
    "state_load_reduced",
    "state_integrity_preservation",
    "state_observation_continues",
    "state_more_thought_requested",
    "outcome_confirmed",
    "outcome_partially_confirmed",
    "outcome_failed",
    "outcome_expired",
    "outcome_inconclusive",
    "homeostasis_update",
    "homeostasis_tension_relief",
    "homeostasis_risk_normalization",
    "homeostasis_reduce_load_pressure",
    "homeostasis_pain_recovery",
    "homeostasis_satisfaction_decay",
    "homeostasis_stability_recovery",
    "homeostasis_curiosity_regulation",
    "homeostasis_preserve_integrity_pressure",
    "experience_candidate",
    "experience_positive_candidate",
    "experience_negative_candidate",
    "experience_weak_candidate",
    "experience_pending_consolidation",
    "consolidation_candidate",
    "consolidation_candidate_ready",
    "consolidation_positive_candidate",
    "consolidation_negative_candidate",
    "consolidation_pending_memory_write",
    "consolidation_pressure",
    "consolidation_pressure_low",
    "consolidation_pressure_medium",
    "consolidation_pressure_high",
    "system_mode_active",
    "system_mode_consolidation",
    "system_mode_recovery",
    "action_enter_consolidation_mode",
    "action_exit_consolidation_mode",
    "state_consolidation_mode_entered",
    "state_consolidation_mode_exited",
    "state_consolidation_processing",
    "state_context_load_reduced",
    "state_pending_candidates_reviewed",
    "learnability_normal_action_effect",
    "learnability_skip_maintenance",
    "learnability_skip_mode_management",
    "learnability_skip_consolidation_internal",
    "learnability_skip_homeostasis",
    "learnability_unknown",
    "learnability_skipped",
    "memory_write_review",
    "memory_review_approved_for_expsm",
    "memory_review_needs_more_support",
    "memory_review_rejected_duplicate",
    "memory_review_rejected_incomplete_core",
    "memory_review_rejected_low_value",
    "memory_review_rejected_unstable",
    "memory_review_sufficient_support",
    "memory_review_high_confidence",
    "memory_review_positive_valence",
    "memory_review_negative_valence",
    "memory_review_low_value",
    "memory_review_incomplete_core",
    "memory_review_duplicate",
    "memory_review_unstable",
    "memory_draft_written",
    "memory_draft_pending_commit",
    "memory_draft_exp_sm",
    "memory_draft_write_success",
    "memory_draft_write_duplicate_skipped",
    "memory_draft_write_failed",
    "memory_draft_created",
    "memory_draft_merged",
    "memory_draft_strengthened",
    "memory_draft_duplicate_merged",
    "tone_tension_high",
    "tone_fatigue_high",
    "tone_risk_sensitivity_high",
    "tone_pain_high",
    "tone_stability_low",
    "memory_draft_commit_review",
    "draft_commit_ready_to_commit",
    "draft_commit_wait_more_evidence",
    "draft_commit_rejected_low_quality",
    "draft_commit_rejected_incomplete",
    "draft_commit_rejected_no_relevant_context",
    "draft_commit_rejected_technical_context",
    "draft_commit_archived_duplicate",
    "draft_commit_already_committed",
    "draft_commit_sufficient_evidence",
    "draft_commit_high_confidence",
    "draft_commit_valid_context",
    "draft_commit_valid_structure",
    "draft_commit_negative_experience_supported",
    "draft_commit_needs_more_seen_count",
    "draft_commit_low_confidence",
    "draft_commit_low_value",
    "draft_commit_missing_if_patterns",
    "draft_commit_missing_then_patterns",
    "draft_commit_missing_result_patterns",
    "draft_commit_technical_context",
    "draft_commit_duplicate",
    "action_commit_memory_draft",
    "state_memory_draft_commit_requested",
    "memory_committed",
    "memory_committed_expsm",
    "memory_commit_success",
    "memory_commit_duplicate_skipped",
    "memory_commit_failed",
    "state_memory_committed",
    "state_memory_commit_failed",
    "committed_draft_observed",
    "committed_draft_strengthened",
    "committed_draft_pending_expsm_update",
    "committed_draft_merge_skipped_rejected",
    "committed_draft_merge_skipped_archived",
    "action_review_committed_memory_update",
    "state_committed_memory_update_review_requested",
    "expsm_update_review",
    "expsm_update_approved_for_update",
    "expsm_update_wait_more_evidence",
    "expsm_update_rejected_no_significant_delta",
    "expsm_update_rejected_invalid_committed_draft",
    "expsm_update_rejected_missing_commit_snapshot",
    "expsm_update_post_commit_evidence",
    "expsm_update_confidence_improved",
    "expsm_update_repeatability_improved",
    "expsm_update_new_relevant_context",
    "expsm_update_no_significant_delta",
    "expsm_update_invalid_structure",
    "action_update_committed_expsm_record",
    "state_committed_expsm_update_requested",
    "memory_updated",
    "memory_updated_expsm",
    "memory_update_success",
    "memory_update_metadata_only",
    "memory_update_duplicate_skipped",
    "memory_update_failed",
    "state_memory_updated",
    "state_memory_update_failed",
    "expsm_activation",
    "expsm_record_matched",
    "expsm_recommendation_active",
    "expsm_then_active",
    "expsm_result_expected",
    "expsm_feedback",
    "expsm_feedback_hit",
    "expsm_feedback_partial_hit",
    "expsm_feedback_miss",
    "expsm_feedback_no_feedback",
    "expsm_feedback_success",
    "expsm_feedback_failure",
    "expsm_feedback_record_updated",
    "expsm_similarity_observed",
    "expsm_similar_records_group",
    "expsm_future_competition_candidate",
    "expsm_similarity_high",
    "expsm_similarity_medium",
    "expsm_competition_observed",
    "expsm_competition_selected_record",
    "expsm_competition_alternative_record",
    "expsm_unused_alternative_not_punished",
    "expsm_competition_same_action",
    "expsm_competition_different_actions",
    "evaluation_signal",
    "evaluation_useful",
    "evaluation_useless",
    "evaluation_harmful",
    "evaluation_safe",
    "evaluation_needed",
    "evaluation_wanted",
    "evaluation_unwanted",
    "evaluation_avoid",
    "evaluation_priority_high",
    "evaluation_priority_medium",
    "evaluation_priority_low",
    "evaluation_target_observed",
    "evaluation_needed_target",
    "evaluation_wanted_target",
    "evaluation_useful_target",
    "evaluation_safety_target",
    "evaluation_avoidance_target",
    "evaluation_harmful_target",
    "evaluation_mixed_target",
    "evaluation_positive_target",
    "akbsm_association_probe",
    "akbsm_association_found",
    "akbsm_association_missing",
    "akbsm_associated_pattern",
    "akbsm_relation_observed",
    "akbsm_target_probe",
    "expsm_mechanism_search",
    "expsm_mechanism_found",
    "expsm_mechanism_missing",
    "expsm_mechanism_obtain_target",
    "expsm_mechanism_preserve_target",
    "expsm_mechanism_avoid_target",
    "expsm_mechanism_mitigate_harm",
    "expsm_mechanism_unknown_potential",
    "target_mechanism_candidate",
    "target_satisfaction_observer",
    "target_satisfaction_observed",
    "target_satisfied",
    "target_partially_satisfied",
    "target_not_satisfied",
    "target_worsened",
    "target_satisfaction_inconclusive",
    "target_satisfaction_positive_evidence",
    "target_satisfaction_negative_evidence",
    "value_feedback_candidate",
    "value_positive_candidate",
    "value_negative_candidate",
    "value_mixed_candidate",
    "value_inconclusive_candidate",
    "value_feedback_increase_candidate",
    "value_feedback_decrease_candidate",
    "value_feedback_review_candidate",
    "value_feedback_request_more_evidence",
    "value_feedback_review",
    "value_feedback_review_ready",
    "value_feedback_review_wait",
    "value_feedback_review_reject",
    "value_feedback_review_archive",
    "value_feedback_ready_for_future_application",
    "value_feedback_not_ready",
    "value_feedback_review_strong_positive",
    "value_feedback_review_strong_negative",
    "value_feedback_review_weak_evidence",
    "value_feedback_review_insufficient_evidence",
    "value_feedback_review_weak_negative_evidence",
    "value_feedback_review_negative_insufficient_evidence",
    "value_feedback_review_inconclusive",
    "value_feedback_updated",
    "value_feedback_update_positive",
    "value_feedback_update_negative",
    "value_feedback_update_mixed",
    "value_feedback_update_inconclusive",
    "value_feedback_metadata_updated",
    "value_feedback_semantic_core_preserved",
    "value_feedback_technical_feedback_preserved",
    "value_usefulness",
    "value_harmfulness",
    "value_need",
    "value_want",
    "value_avoid",
    "value_safety",
    "value_priority",
    "state_no_change",
    "state_integrity_preserved",
    "state_integrity_risk",
    "state_action_blocked",
    "state_recovery_progress",
    "state_stability_high",
    "state_satisfaction_high",
    "prediction_failed",
    "high_tension",
    "high_pain",
    "high_fatigue",
    "decision_audit_observed",
    "decision_audit_clear_win",
    "decision_audit_narrow_win",
    "decision_audit_tie_like",
    "decision_audit_single_candidate",
    "decision_audit_value_promoted",
    "decision_audit_value_demoted",
    "decision_audit_value_unchanged",
    "decision_audit_value_positive_bonus",
    "decision_audit_value_negative_penalty",
    "decision_audit_value_none_or_tiny",
    "decision_audit_target_specific_value",
    "decision_audit_generic_value",
    "decision_audit_no_value",
    "action_guard_audit_observed",
    "action_guard_audit_no_blocked_candidates",
    "action_guard_audit_blocked_low_score_only",
    "action_guard_audit_blocked_high_score_candidate",
    "action_guard_audit_selected_only_allowed",
    "action_guard_audit_allowed_candidate",
    "action_guard_audit_blocked_candidate",
    "action_guard_audit_severity_none",
    "action_guard_audit_severity_low",
    "action_guard_audit_severity_medium",
    "action_guard_audit_severity_high",
    "decision_cycle_summary",
    "decision_cycle_clean_selection",
    "decision_cycle_value_influenced_selection",
    "decision_cycle_guard_constrained_selection",
    "decision_cycle_uncertain_selection",
    "decision_cycle_risky_or_constrained_selection",
    "decision_cycle_confidence_high",
    "decision_cycle_confidence_medium",
    "decision_cycle_confidence_low",
    "decision_cycle_value_promoted_selected",
    "decision_cycle_value_penalized_selected",
    "decision_cycle_guard_blocked_high_score",
    "decision_cycle_narrow_decision",
    "decision_cycle_tie_like_decision",
    "decision_cycle_single_candidate",
    "decision_cycle_target_specific_value_used",
    "decision_cycle_no_value_influence",
    "decision_cycle_guard_summary_missing",
)
