from dataclasses import dataclass, field
from contextlib import contextmanager
import json
from pathlib import Path
import re
from typing import Any


MANIFEST_SCHEMA_VERSION = 1
DEFAULT_MANIFEST_PATH = Path("Memory") / "pattern_manifest.json"
PATTERN_ID_RE = re.compile(r"^pat_(\d{4,})$")


@dataclass
class PatternRegistry:
    """Stable mapping between internal pattern ids and human debug names."""

    manifest_path: Path | str = DEFAULT_MANIFEST_PATH
    _name_to_id: dict[str, str] = field(default_factory=dict, init=False)
    _id_to_name: dict[str, str] = field(default_factory=dict, init=False)
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
            self._next_pattern_number = 1
            return True
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid PatternRegistry manifest {self.manifest_path}: {exc}") from exc
        _validate_manifest_data(data, self.manifest_path)
        self._name_to_id = {str(name): str(pattern_id) for name, pattern_id in data["patterns"].items()}
        self._id_to_name = {str(pattern_id): str(name) for pattern_id, name in data["ids"].items()}
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
)
