from dataclasses import dataclass, field, replace
from collections.abc import Mapping
from typing import Any

from clc.context.context_retention_policy import (
    ContextRetentionPolicy,
    ContextRetentionResult,
    SIDE_LIST_NAMES,
    SideListRetentionPolicy,
    SideListRetentionResult,
)
from clc.context.window import ContextWindow
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.nfp import NFPFrame
from clc.core.operations import ContextOperation, thaw_payload
from clc.core.pattern_registry import PatternRegistry
from clc.neuromodulation.tone_state import ToneState


@dataclass
class ContextMemory:
    id_gen: IdGenerator
    pattern_registry: PatternRegistry
    raw_frames: list[NFPFrame] = field(default_factory=list)
    thought_frames: list[NFPFrame] = field(default_factory=list)
    labels: list[dict[str, Any]] = field(default_factory=list)
    predictions: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    effects: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    experience_candidates: list[dict[str, Any]] = field(default_factory=list)
    consolidation_candidates: list[dict[str, Any]] = field(default_factory=list)
    memory_write_reviews: list[dict[str, Any]] = field(default_factory=list)
    memory_draft_writes: list[dict[str, Any]] = field(default_factory=list)
    memory_draft_commit_reviews: list[dict[str, Any]] = field(default_factory=list)
    memory_commits: list[dict[str, Any]] = field(default_factory=list)
    committed_draft_observations: list[dict[str, Any]] = field(default_factory=list)
    expsm_update_reviews: list[dict[str, Any]] = field(default_factory=list)
    memory_updates: list[dict[str, Any]] = field(default_factory=list)
    expsm_activations: list[dict[str, Any]] = field(default_factory=list)
    expsm_feedback: list[dict[str, Any]] = field(default_factory=list)
    expsm_similarity_observations: list[dict[str, Any]] = field(default_factory=list)
    expsm_competition_observations: list[dict[str, Any]] = field(default_factory=list)
    evaluation_signals: list[dict[str, Any]] = field(default_factory=list)
    evaluation_targets: list[dict[str, Any]] = field(default_factory=list)
    akbsm_association_probes: list[dict[str, Any]] = field(default_factory=list)
    expsm_mechanism_searches: list[dict[str, Any]] = field(default_factory=list)
    target_satisfaction_observations: list[dict[str, Any]] = field(default_factory=list)
    value_feedback_candidates: list[dict[str, Any]] = field(default_factory=list)
    value_feedback_reviews: list[dict[str, Any]] = field(default_factory=list)
    value_feedback_updates: list[dict[str, Any]] = field(default_factory=list)
    decision_audits: list[dict[str, Any]] = field(default_factory=list)
    action_guard_audits: list[dict[str, Any]] = field(default_factory=list)
    decision_cycle_summaries: list[dict[str, Any]] = field(default_factory=list)
    consolidation_pressures: list[dict[str, Any]] = field(default_factory=list)
    system_mode_changes: list[dict[str, Any]] = field(default_factory=list)
    neuromodulation_updates: list[dict[str, Any]] = field(default_factory=list)
    module_updates: list[dict[str, Any]] = field(default_factory=list)
    events: list[ContextOperation] = field(default_factory=list)
    windows: list[ContextWindow] = field(default_factory=list)
    tone_state: ToneState = field(default_factory=ToneState)
    last_context_retention_result: ContextRetentionResult | None = None
    last_side_list_retention_result: SideListRetentionResult | None = None

    def add_frame(self, frame: NFPFrame) -> None:
        if frame.origin == "self_generated":
            self.thought_frames.append(frame)
        else:
            self.raw_frames.append(frame)

    def add_event(self, event: ContextOperation) -> None:
        payload = thaw_payload(event.payload)
        payload["_event_tick"] = event.tick
        stored_event = replace(event, payload=payload)
        self.events.append(stored_event)
        payload = thaw_payload(stored_event.payload)
        if event.marker in {OperationMarker.RAW_INPUT_WRITE, OperationMarker.SELF_GENERATED_THOUGHT}:
            return
        if event.marker == OperationMarker.LABEL:
            self.labels.append(payload)
        elif event.marker == OperationMarker.PREDICTION:
            self.predictions.append(payload)
        elif event.marker == OperationMarker.NEUROMODULATION_UPDATE:
            self.neuromodulation_updates.append(payload)
            tone = payload.get("tone_state")
            if isinstance(tone, ToneState):
                self.tone_state = tone
        elif event.marker == OperationMarker.INTERNAL_DECISION:
            self.decisions.append(payload)
        elif event.marker == OperationMarker.INTERNAL_ACTION_EFFECT:
            self.effects.append(payload)
        elif event.marker == OperationMarker.OUTCOME_EVALUATION:
            self.outcomes.append(payload)
        elif event.marker == OperationMarker.EXPERIENCE_CANDIDATE:
            self.experience_candidates.append(payload)
        elif event.marker == OperationMarker.CONSOLIDATION_CANDIDATE:
            self.consolidation_candidates.append(payload)
        elif event.marker == OperationMarker.MEMORY_WRITE_REVIEW:
            self.memory_write_reviews.append(payload)
        elif event.marker == OperationMarker.MEMORY_DRAFT_WRITTEN:
            self.memory_draft_writes.append(payload)
        elif event.marker == OperationMarker.MEMORY_DRAFT_COMMIT_REVIEW:
            self.memory_draft_commit_reviews.append(payload)
        elif event.marker == OperationMarker.MEMORY_COMMITTED:
            self.memory_commits.append(payload)
        elif event.marker == OperationMarker.COMMITTED_DRAFT_OBSERVED:
            self.committed_draft_observations.append(payload)
        elif event.marker == OperationMarker.EXPSM_UPDATE_REVIEW:
            self.expsm_update_reviews.append(payload)
        elif event.marker == OperationMarker.MEMORY_UPDATED:
            self.memory_updates.append(payload)
        elif event.marker == OperationMarker.EXPSM_ACTIVATION:
            self.expsm_activations.append(payload)
        elif event.marker == OperationMarker.EXPSM_FEEDBACK:
            self.expsm_feedback.append(payload)
        elif event.marker == OperationMarker.EXPSM_SIMILARITY_OBSERVED:
            self.expsm_similarity_observations.append(payload)
        elif event.marker == OperationMarker.EXPSM_COMPETITION_OBSERVED:
            self.expsm_competition_observations.append(payload)
        elif event.marker == OperationMarker.EVALUATION_SIGNAL:
            self.evaluation_signals.append(payload)
        elif event.marker == OperationMarker.EVALUATION_TARGET_OBSERVED:
            self.evaluation_targets.append(payload)
        elif event.marker == OperationMarker.AKBSM_ASSOCIATION_PROBE:
            self.akbsm_association_probes.append(payload)
        elif event.marker == OperationMarker.EXPSM_MECHANISM_SEARCH:
            self.expsm_mechanism_searches.append(payload)
        elif event.marker == OperationMarker.TARGET_SATISFACTION_OBSERVED:
            self.target_satisfaction_observations.append(payload)
        elif event.marker == OperationMarker.VALUE_FEEDBACK_CANDIDATE:
            self.value_feedback_candidates.append(payload)
        elif event.marker == OperationMarker.VALUE_FEEDBACK_REVIEW:
            self.value_feedback_reviews.append(payload)
        elif event.marker == OperationMarker.VALUE_FEEDBACK_UPDATED:
            self.value_feedback_updates.append(payload)
        elif event.marker == OperationMarker.DECISION_AUDIT_OBSERVED:
            self.decision_audits.append(payload)
        elif event.marker == OperationMarker.ACTION_GUARD_AUDIT_OBSERVED:
            self.action_guard_audits.append(payload)
        elif event.marker == OperationMarker.DECISION_CYCLE_SUMMARY:
            self.decision_cycle_summaries.append(payload)
        elif event.marker == OperationMarker.CONSOLIDATION_PRESSURE:
            self.consolidation_pressures.append(payload)
        elif event.marker == OperationMarker.SYSTEM_MODE_CHANGE:
            self.system_mode_changes.append(payload)
        elif event.marker == OperationMarker.MODULE_UPDATE:
            self.module_updates.append(payload)

    def apply_retention(self, policy: ContextRetentionPolicy) -> ContextRetentionResult:
        before_count = len(self.events)
        if not policy.enabled or policy.max_events is None:
            result = _retention_result(policy, self.events, before_count, before_count, 0)
            self.last_context_retention_result = result
            return result
        excess = max(0, before_count - policy.max_events)
        if excess <= 0:
            result = _retention_result(policy, self.events, before_count, before_count, 0)
            self.last_context_retention_result = result
            return result
        self.events = self.events[excess:]
        result = _retention_result(policy, self.events, before_count, len(self.events), excess)
        self.last_context_retention_result = result
        return result

    def apply_side_list_retention(
        self,
        policy: SideListRetentionPolicy,
        *,
        oldest_event_tick: int | None,
    ) -> SideListRetentionResult:
        per_list: dict[str, dict[str, int | None]] = {}
        warnings: list[str] = []
        total_before = 0
        total_after = 0
        total_pruned = 0
        for name in SIDE_LIST_NAMES:
            if not hasattr(self, name):
                warnings.append(f"{name} side list is not available")
                continue
            entries = getattr(self, name)
            if not isinstance(entries, list):
                warnings.append(f"{name} side list is not a list")
                continue
            before = len(entries)
            total_before += before
            oldest_before, newest_before, unknown_before = _entry_bounds_for_list(entries)
            if not policy.enabled:
                after_entries = entries
                pruned_by_tick = 0
                pruned_by_max = 0
            else:
                after_entries, pruned_by_tick, unknown_tick_count = _prune_entries_by_tick(
                    entries,
                    oldest_event_tick,
                    policy,
                )
                if unknown_tick_count:
                    warnings.append(f"{name} kept {unknown_tick_count} entries without diagnostic ticks")
                after_entries, pruned_by_max = _prune_entries_by_max(after_entries, policy.max_entries_for(name))
                if after_entries is not entries:
                    setattr(self, name, after_entries)
            after = len(after_entries)
            oldest_after, newest_after, _unknown_after = _entry_bounds_for_list(after_entries)
            pruned = before - after
            total_after += after
            total_pruned += pruned
            per_list[name] = {
                "before": before,
                "after": after,
                "pruned_by_tick": pruned_by_tick,
                "pruned_by_max_entries": pruned_by_max,
                "oldest_tick_before": oldest_before,
                "newest_tick_before": newest_before,
                "oldest_tick_after": oldest_after,
                "newest_tick_after": newest_after,
                "unknown_tick_entries_before": unknown_before,
            }
        result = SideListRetentionResult(
            enabled=policy.enabled,
            oldest_event_tick=oldest_event_tick,
            total_before=total_before,
            total_after=total_after,
            total_pruned=total_pruned,
            per_list=per_list,
            warnings=warnings,
        )
        self.last_side_list_retention_result = result
        return result

    def all_frames(self) -> list[NFPFrame]:
        return sorted(self.raw_frames + self.thought_frames, key=lambda frame: (frame.tick, frame.frame_id))

    def get_recent_frames(self, n: int) -> list[NFPFrame]:
        return self.all_frames()[-n:]

    def get_recent_events(self, n: int) -> list[ContextOperation]:
        return self.events[-n:]

    def build_window(self, last_n_frames: int, source: str | None = None, origin: str | None = None) -> ContextWindow | None:
        frames = self.all_frames()
        if source is not None:
            frames = [frame for frame in frames if frame.source == source]
        if origin is not None:
            frames = [frame for frame in frames if frame.origin == origin]
        frames = frames[-last_n_frames:]
        if not frames:
            return None
        window = ContextWindow(
            window_id=self.id_gen.next("win"),
            from_tick=frames[0].tick,
            to_tick=frames[-1].tick,
            frame_ids=tuple(frame.frame_id for frame in frames),
        )
        self.windows.append(window)
        return window

    def get_current_tone(self) -> ToneState:
        return self.tone_state

    def recent_labels(self, n: int = 8) -> list[dict[str, Any]]:
        return self.labels[-n:]

    def recent_predictions(self, n: int = 5) -> list[dict[str, Any]]:
        return self.predictions[-n:]

    def get_recent_decisions(self, n: int = 5) -> list[dict[str, Any]]:
        return self.decisions[-n:]

    def get_recent_effects(self, n: int = 5) -> list[dict[str, Any]]:
        return self.effects[-n:]

    def get_recent_outcomes(self, n: int = 5) -> list[dict[str, Any]]:
        return self.outcomes[-n:]

    def get_recent_experience_candidates(self, n: int = 5) -> list[dict[str, Any]]:
        return self.experience_candidates[-n:]

    def get_recent_consolidation_candidates(self, n: int = 5) -> list[dict[str, Any]]:
        return self.consolidation_candidates[-n:]

    def get_recent_memory_write_reviews(self, n: int = 5) -> list[dict[str, Any]]:
        return self.memory_write_reviews[-n:]

    def get_recent_memory_draft_writes(self, n: int = 5) -> list[dict[str, Any]]:
        return self.memory_draft_writes[-n:]

    def get_recent_memory_draft_commit_reviews(self, n: int = 5) -> list[dict[str, Any]]:
        return self.memory_draft_commit_reviews[-n:]

    def get_recent_memory_commits(self, n: int = 5) -> list[dict[str, Any]]:
        return self.memory_commits[-n:]

    def get_recent_committed_draft_observations(self, n: int = 5) -> list[dict[str, Any]]:
        return self.committed_draft_observations[-n:]

    def get_recent_expsm_update_reviews(self, n: int = 5) -> list[dict[str, Any]]:
        return self.expsm_update_reviews[-n:]

    def get_recent_memory_updates(self, n: int = 5) -> list[dict[str, Any]]:
        return self.memory_updates[-n:]

    def get_recent_expsm_activations(self, n: int = 5) -> list[dict[str, Any]]:
        return self.expsm_activations[-n:]

    def get_recent_expsm_feedback(self, n: int = 5) -> list[dict[str, Any]]:
        return self.expsm_feedback[-n:]

    def get_recent_expsm_similarity_observations(self, n: int = 5) -> list[dict[str, Any]]:
        return self.expsm_similarity_observations[-n:]

    def get_recent_expsm_competition_observations(self, n: int = 5) -> list[dict[str, Any]]:
        return self.expsm_competition_observations[-n:]

    def get_recent_evaluation_signals(self, n: int = 5) -> list[dict[str, Any]]:
        return self.evaluation_signals[-n:]

    def get_recent_evaluation_targets(self, n: int = 5) -> list[dict[str, Any]]:
        return self.evaluation_targets[-n:]

    def get_recent_akbsm_association_probes(self, n: int = 5) -> list[dict[str, Any]]:
        return self.akbsm_association_probes[-n:]

    def get_recent_expsm_mechanism_searches(self, n: int = 5) -> list[dict[str, Any]]:
        return self.expsm_mechanism_searches[-n:]

    def get_recent_target_satisfaction_observations(self, n: int = 5) -> list[dict[str, Any]]:
        return self.target_satisfaction_observations[-n:]

    def get_recent_value_feedback_candidates(self, n: int = 5) -> list[dict[str, Any]]:
        return self.value_feedback_candidates[-n:]

    def get_recent_value_feedback_reviews(self, n: int = 5) -> list[dict[str, Any]]:
        return self.value_feedback_reviews[-n:]

    def get_recent_value_feedback_updates(self, n: int = 5) -> list[dict[str, Any]]:
        return self.value_feedback_updates[-n:]

    def get_recent_decision_audits(self, n: int = 5) -> list[dict[str, Any]]:
        return self.decision_audits[-n:]

    def get_recent_action_guard_audits(self, n: int = 5) -> list[dict[str, Any]]:
        return self.action_guard_audits[-n:]

    def get_recent_decision_cycle_summaries(self, n: int = 5) -> list[dict[str, Any]]:
        return self.decision_cycle_summaries[-n:]

    def get_recent_consolidation_pressures(self, n: int = 5) -> list[dict[str, Any]]:
        return self.consolidation_pressures[-n:]

    def get_recent_system_mode_changes(self, n: int = 5) -> list[dict[str, Any]]:
        return self.system_mode_changes[-n:]

    def debug_print_state(self, tick: int) -> None:
        print(f"\n=== tick {tick} ===")
        self._print_frames("new raw frames", [f for f in self.raw_frames if f.tick == tick])
        labels = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.LABEL]
        predictions = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.PREDICTION]
        decisions = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.INTERNAL_DECISION]
        effects = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.INTERNAL_ACTION_EFFECT]
        outcomes = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.OUTCOME_EVALUATION]
        experience_candidates = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.EXPERIENCE_CANDIDATE]
        consolidation_candidates = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.CONSOLIDATION_CANDIDATE]
        memory_write_reviews = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.MEMORY_WRITE_REVIEW]
        memory_draft_writes = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.MEMORY_DRAFT_WRITTEN]
        memory_draft_commit_reviews = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.MEMORY_DRAFT_COMMIT_REVIEW
        ]
        memory_commits = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.MEMORY_COMMITTED]
        committed_draft_observations = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.COMMITTED_DRAFT_OBSERVED
        ]
        expsm_update_reviews = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.EXPSM_UPDATE_REVIEW]
        memory_updates = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.MEMORY_UPDATED]
        expsm_activations = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.EXPSM_ACTIVATION]
        expsm_feedback = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.EXPSM_FEEDBACK]
        expsm_similarity_observations = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.EXPSM_SIMILARITY_OBSERVED
        ]
        expsm_competition_observations = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.EXPSM_COMPETITION_OBSERVED
        ]
        evaluation_signals = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.EVALUATION_SIGNAL]
        evaluation_targets = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.EVALUATION_TARGET_OBSERVED
        ]
        akbsm_association_probes = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.AKBSM_ASSOCIATION_PROBE
        ]
        expsm_mechanism_searches = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.EXPSM_MECHANISM_SEARCH
        ]
        target_satisfaction_observations = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.TARGET_SATISFACTION_OBSERVED
        ]
        value_feedback_candidates = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.VALUE_FEEDBACK_CANDIDATE
        ]
        value_feedback_reviews = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.VALUE_FEEDBACK_REVIEW
        ]
        value_feedback_updates = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.VALUE_FEEDBACK_UPDATED
        ]
        decision_audits = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.DECISION_AUDIT_OBSERVED
        ]
        action_guard_audits = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.ACTION_GUARD_AUDIT_OBSERVED
        ]
        decision_cycle_summaries = [
            e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.DECISION_CYCLE_SUMMARY
        ]
        memory_draft_writer_updates = [
            e.payload
            for e in self.events
            if e.tick == tick
            and e.marker == OperationMarker.MODULE_UPDATE
            and e.payload.get("module") == "memory_draft_writer"
        ]
        consolidation_pressures = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.CONSOLIDATION_PRESSURE]
        mode_changes = [e.payload for e in self.events if e.tick == tick and e.marker == OperationMarker.SYSTEM_MODE_CHANGE]
        homeostasis = [
            e.payload
            for e in self.events
            if e.tick == tick and e.marker == OperationMarker.NEUROMODULATION_UPDATE and e.payload.get("homeostasis_patterns")
        ]
        thoughts = [f for f in self.thought_frames if f.tick == tick]
        self._print_payloads("new labels", labels)
        self._print_payloads("new predictions", predictions)
        print(f"tone state: {self.tone_state.as_debug_dict()}")
        self._print_frames("generated thoughts", thoughts)
        self._print_payloads("selected internal decisions", decisions)
        self._print_payloads("internal action effects", effects)
        self._print_payloads("outcome evaluations", outcomes)
        self._print_payloads("experience candidates", experience_candidates)
        self._print_payloads("consolidation candidates", consolidation_candidates)
        self._print_payloads("memory write reviews", memory_write_reviews)
        self._print_payloads("memory draft writes", memory_draft_writes)
        self._print_payloads("draft commit reviews", memory_draft_commit_reviews)
        self._print_payloads("memory commits", memory_commits)
        self._print_payloads("committed draft observations", committed_draft_observations)
        self._print_payloads("expsm update reviews", expsm_update_reviews)
        self._print_payloads("memory updates", memory_updates)
        self._print_payloads("expsm activations", expsm_activations)
        self._print_payloads("expsm feedback", expsm_feedback)
        self._print_payloads("expsm similarity observations", expsm_similarity_observations)
        self._print_payloads("expsm competition observations", expsm_competition_observations)
        self._print_payloads("evaluation signals", evaluation_signals)
        self._print_payloads("evaluation targets", evaluation_targets)
        self._print_payloads("akbsm association probes", akbsm_association_probes)
        self._print_payloads("expsm mechanism searches", expsm_mechanism_searches)
        self._print_payloads("target satisfaction observations", target_satisfaction_observations)
        self._print_payloads("value feedback candidates", value_feedback_candidates)
        self._print_payloads("value feedback reviews", value_feedback_reviews)
        self._print_payloads("value feedback updates", value_feedback_updates)
        self._print_payloads("decision audits", decision_audits)
        self._print_payloads("action guard audits", action_guard_audits)
        self._print_payloads("decision cycle summaries", decision_cycle_summaries)
        self._print_payloads("memory draft writer", memory_draft_writer_updates)
        self._print_payloads("consolidation pressure", consolidation_pressures)
        self._print_payloads("mode changes", mode_changes)
        self._print_payloads("homeostasis updates", homeostasis)

    def _print_frames(self, title: str, frames: list[NFPFrame]) -> None:
        print(f"{title}:")
        if not frames:
            print("  none")
            return
        for frame in frames:
            ttl = f" ttl={frame.ttl} decay={frame.decay}" if frame.ttl is not None else ""
            print(f"  {frame.frame_id} {frame.source}{ttl} {self._debug_activations(frame.activations)}")

    def _print_payloads(self, title: str, payloads: list[dict[str, Any]]) -> None:
        print(f"{title}:")
        if not payloads:
            print("  none")
            return
        for payload in payloads:
            if title == "experience candidates":
                self._print_experience_candidate(payload)
                continue
            if title == "consolidation candidates":
                self._print_consolidation_candidate(payload)
                continue
            if title == "memory write reviews":
                self._print_memory_write_review(payload)
                continue
            if title == "memory draft writes":
                self._print_memory_draft_write(payload)
                continue
            if title == "draft commit reviews":
                self._print_draft_commit_review(payload)
                continue
            if title == "memory commits":
                self._print_memory_commit(payload)
                continue
            if title == "committed draft observations":
                self._print_committed_draft_observation(payload)
                continue
            if title == "expsm update reviews":
                self._print_expsm_update_review(payload)
                continue
            if title == "memory updates":
                self._print_memory_update(payload)
                continue
            if title == "expsm activations":
                self._print_expsm_activation(payload)
                continue
            if title == "expsm feedback":
                self._print_expsm_feedback(payload)
                continue
            if title == "expsm similarity observations":
                self._print_expsm_similarity(payload)
                continue
            if title == "expsm competition observations":
                self._print_expsm_competition(payload)
                continue
            if title == "evaluation signals":
                self._print_evaluation_signal(payload)
                continue
            if title == "evaluation targets":
                self._print_evaluation_target(payload)
                continue
            if title == "akbsm association probes":
                self._print_akbsm_association_probe(payload)
                continue
            if title == "expsm mechanism searches":
                self._print_expsm_mechanism_search(payload)
                continue
            if title == "target satisfaction observations":
                self._print_target_satisfaction(payload)
                continue
            if title == "value feedback candidates":
                self._print_value_feedback_candidate(payload)
                continue
            if title == "value feedback reviews":
                self._print_value_feedback_review(payload)
                continue
            if title == "value feedback updates":
                self._print_value_feedback_update(payload)
                continue
            if title == "decision audits":
                self._print_decision_audit(payload)
                continue
            if title == "action guard audits":
                self._print_action_guard_audit(payload)
                continue
            if title == "decision cycle summaries":
                self._print_decision_cycle_summary(payload)
                continue
            if title == "selected internal decisions":
                self._print_decision(payload)
                continue
            if title == "memory draft writer":
                self._print_memory_draft_writer_update(payload)
                continue
            if title == "consolidation pressure":
                self._print_consolidation_pressure(payload)
                continue
            if title == "mode changes":
                self._print_mode_change(payload)
                continue
            print(f"  {self._debug_payload(payload)}")

    def _print_experience_candidate(self, payload: dict[str, Any]) -> None:
        core = payload.get("core_chain", {})
        context = payload.get("context_refs", {})
        print(
            f"  id={payload.get('candidate_id')} status={payload.get('candidate_status')} "
            f"confidence={payload.get('confidence')} write_status={payload.get('write_status')}"
        )
        print(
            "    core: "
            f"decisions={self._debug_value('decision_patterns', core.get('decision_patterns', []))} "
            f"effects={self._debug_value('effect_patterns', core.get('effect_patterns', []))} "
            f"predictions={self._debug_value('predicted_patterns', core.get('predicted_patterns', []))} "
            f"outcomes={self._debug_value('outcome_patterns', core.get('outcome_patterns', []))}"
        )
        print(
            "    context: "
            f"labels={len(context.get('label_event_ids', []))} "
            f"frames={len(context.get('frame_ids', []))} "
            f"nearby_predictions={len(context.get('nearby_prediction_event_ids', []))} "
            f"active_patterns={len(context.get('active_patterns', []))}"
        )
        learnability = payload.get("learnability", {})
        if learnability:
            print(
                "    learnability: "
                f"category={learnability.get('category')} "
                f"confidence={learnability.get('confidence')} "
                f"reasons={self._debug_value('reason_patterns', learnability.get('reason_patterns', []))}"
            )

    def _print_consolidation_candidate(self, payload: dict[str, Any]) -> None:
        core = payload.get("core_chain", {})
        print(
            f"  id={payload.get('consolidation_candidate_id')} group={payload.get('group_id')} "
            f"support={payload.get('support_count')} avg_confidence={payload.get('avg_confidence')} "
            f"avg_valence={payload.get('avg_valence')} target={payload.get('suggested_target')} "
            f"write_status={payload.get('write_status')}"
        )
        print(f"    core_signature={self._debug_signature(payload.get('core_signature', []))}")
        print(
            "    core: "
            f"decisions={self._debug_value('decision_patterns', core.get('decision_patterns', []))} "
            f"effects={self._debug_value('effect_patterns', core.get('effect_patterns', []))} "
            f"predictions={self._debug_value('predicted_patterns', core.get('predicted_patterns', []))} "
            f"outcomes={self._debug_value('outcome_patterns', core.get('outcome_patterns', []))}"
        )

    def _print_memory_write_review(self, payload: dict[str, Any]) -> None:
        print(
            f"  review_id={payload.get('review_id')} source_group={payload.get('source_group_id')} "
            f"status={payload.get('review_status')} support={payload.get('support_count')} "
            f"avg_confidence={payload.get('avg_confidence')} avg_valence={payload.get('avg_valence')} "
            f"write_status={payload.get('write_status')}"
        )
        print(f"    reasons={self._debug_value('reasons', payload.get('reasons', []))}")
        print(f"    core_signature={self._debug_signature(payload.get('core_signature', []))}")

    def _print_memory_draft_write(self, payload: dict[str, Any]) -> None:
        print(
            f"  draft_id={payload.get('draft_id')} source_review_id={payload.get('source_review_id')} "
            f"write_kind={payload.get('write_kind')} seen_count={payload.get('seen_count')} "
            f"target={payload.get('target')} status={payload.get('draft_status')} "
            f"permanent_memory_modified={payload.get('permanent_memory_modified')}"
        )
        print(f"    if_patterns={self._debug_value('if_patterns', payload.get('if_patterns', []))}")
        self._print_scored_if_patterns(payload.get("if_patterns_scored", ()), payload.get("if_patterns", ()))
        print(f"    then_patterns={self._debug_value('then_patterns', payload.get('then_patterns', []))}")
        print(f"    result_patterns={self._debug_value('result_patterns', payload.get('result_patterns', []))}")
        print(f"    outcome_patterns={self._debug_value('outcome_patterns', payload.get('outcome_patterns', []))}")
        print(f"    context_enrichment={payload.get('context_enrichment', {})}")
        print(f"    path={payload.get('draft_path')}")

    def _print_scored_if_patterns(self, scored: Any, accepted_patterns: Any) -> None:
        if not isinstance(scored, (list, tuple)) or not scored:
            return
        accepted = set(accepted_patterns if isinstance(accepted_patterns, (list, tuple)) else ())
        print("    scored_if_patterns:")
        shown = 0
        for record in scored:
            if not isinstance(record, Mapping):
                continue
            pattern_id = record.get("pattern")
            if not pattern_id:
                continue
            filtered = " filtered_out" if pattern_id not in accepted else ""
            sources = ",".join(record.get("sources", ()))
            print(
                f"      {self.pattern_registry.debug_name(pattern_id)} "
                f"score={record.get('score')} sources=[{sources}]{filtered}"
            )
            shown += 1
            if shown >= 6:
                break

    def _print_memory_draft_writer_update(self, payload: dict[str, Any]) -> None:
        if payload.get("event", "").startswith("draft_skipped"):
            print(f"  skipped review {payload.get('source_review_id')}:")
            print(f"    reason: {payload.get('reason')}")
            return
        print(f"  {self._debug_payload(payload)}")

    def _print_draft_commit_review(self, payload: dict[str, Any]) -> None:
        metrics = payload.get("metrics", {})
        print(
            f"  review_id={payload.get('commit_review_id')} draft_id={payload.get('draft_id')} "
            f"status={payload.get('review_status')} draft_status={payload.get('draft_status')} "
            f"score={payload.get('decision_score')}"
        )
        print(
            f"    seen_count={metrics.get('seen_count')} support_count={metrics.get('support_count')} "
            f"avg_confidence={metrics.get('avg_confidence')} avg_valence={metrics.get('avg_valence')}"
        )
        print(f"    reasons={self._debug_value('reasons', payload.get('reasons', []))}")

    def _print_memory_commit(self, payload: dict[str, Any]) -> None:
        summary = payload.get("record_summary", {})
        print(
            f"  commit_id={payload.get('memory_commit_id')} target={payload.get('target')} "
            f"experience_id={payload.get('experience_id')} source_draft_id={payload.get('source_draft_id')} "
            f"permanent_memory_modified={payload.get('permanent_memory_modified')}"
        )
        print(
            f"    confidence={summary.get('confidence')} repeatability={summary.get('repeatability')} "
            f"if={summary.get('if_count')} then={summary.get('then_count')} result={summary.get('result_count')}"
        )

    def _print_committed_draft_observation(self, payload: dict[str, Any]) -> None:
        print(
            f"  observation_id={payload.get('observation_id')} draft_id={payload.get('draft_id')} "
            f"committed_experience_id={payload.get('committed_experience_id')}"
        )
        print(
            f"    seen_count={payload.get('seen_count')} "
            f"post_commit_seen_count={payload.get('post_commit_seen_count')} "
            f"pending_expsm_update={payload.get('pending_expsm_update')} "
            f"permanent_memory_modified={payload.get('permanent_memory_modified')}"
        )

    def _print_expsm_update_review(self, payload: dict[str, Any]) -> None:
        deltas = payload.get("deltas", {})
        print(
            f"  review_id={payload.get('update_review_id')} draft_id={payload.get('draft_id')} "
            f"committed_experience_id={payload.get('committed_experience_id')}"
        )
        print(
            f"    status={payload.get('review_status')} score={payload.get('decision_score')} "
            f"update_status={payload.get('update_status')} "
            f"permanent_memory_modified={payload.get('permanent_memory_modified')}"
        )
        print(
            f"    post_commit_seen_count={deltas.get('post_commit_seen_count')} "
            f"confidence_delta={deltas.get('confidence_delta')} "
            f"seen_delta={deltas.get('seen_delta')} "
            f"new_if={self._debug_value('if_patterns', deltas.get('new_relevant_if_patterns', []))}"
        )

    def _print_memory_update(self, payload: dict[str, Any]) -> None:
        metrics = payload.get("metrics", {})
        print(
            f"  update_id={payload.get('memory_update_id')} target={payload.get('target')} "
            f"experience_id={payload.get('experience_id')} mode={payload.get('update_mode')}"
        )
        print(
            f"    confidence={metrics.get('old_confidence')} -> {metrics.get('new_confidence')} "
            f"repeatability={metrics.get('old_repeatability')} -> {metrics.get('new_repeatability')} "
            f"seen_count={metrics.get('seen_count')} post_commit_seen_count={metrics.get('post_commit_seen_count')}"
        )
        print(
            f"    semantic_core_modified={payload.get('semantic_core_modified')} "
            f"new_record_created={payload.get('new_record_created')} "
            f"reflexes_modified={payload.get('reflexes_modified')} "
            f"akbsm_modified={payload.get('akbsm_modified')}"
        )

    def _print_expsm_activation(self, payload: dict[str, Any]) -> None:
        print(
            f"  activation_id={payload.get('activation_id')} experience_id={payload.get('experience_id')} "
            f"match_score={payload.get('match_score')} coverage={payload.get('coverage')}"
        )
        print(
            f"    confidence={payload.get('effective_confidence', payload.get('confidence'))} "
            f"raw_confidence={payload.get('raw_confidence')} "
            f"repeatability={payload.get('repeatability')} "
            f"hits={payload.get('hits')} misses={payload.get('misses')} viability={payload.get('viability')}"
        )
        print(f"    matched_if={self._debug_value('if_patterns', payload.get('matched_if_patterns', []))}")
        print(f"    then={self._debug_value('then_patterns', payload.get('then_patterns', []))}")
        print(f"    expected_result={self._debug_value('result_patterns', payload.get('result_patterns', []))}")

    def _print_expsm_feedback(self, payload: dict[str, Any]) -> None:
        print(
            f"  feedback_id={payload.get('feedback_id')} experience_id={payload.get('experience_id')} "
            f"activation_id={payload.get('activation_id')} status={payload.get('feedback_status')} "
            f"decision={payload.get('decision_id')} trace_source={payload.get('trace_source')}"
        )
        print(
            f"    selected={self._debug_value('selected_action', payload.get('selected_action'))} "
            f"matched_expected={self._debug_value('matched_expected_patterns', payload.get('matched_expected_patterns', []))}"
        )
        print(
            f"    hits={payload.get('old_hits')} -> {payload.get('new_hits')} "
            f"misses={payload.get('old_misses')} -> {payload.get('new_misses')} "
            f"confidence={payload.get('old_confidence')} -> target {payload.get('target_confidence')} -> {payload.get('new_confidence')} "
            f"repeatability={payload.get('old_repeatability')} -> {payload.get('new_repeatability')}"
        )
        print(
            f"    confidence_model={payload.get('confidence_model')} "
            f"cap={payload.get('feedback_confidence_cap')} "
            f"success_ratio={payload.get('success_ratio')} "
            f"hit_strength={payload.get('hit_strength')} "
            f"soft_cap_applied={payload.get('legacy_confidence_soft_cap_applied')}"
        )

    def _print_decision(self, payload: dict[str, Any]) -> None:
        print(
            f"  decision_id={payload.get('decision_id')} "
            f"action={self._debug_value('decision_pattern_id', payload.get('decision_pattern_id'))} "
            f"score={payload.get('candidate_score')}"
        )
        if payload.get("source") == "expsm_activation":
            print(
                f"    source=expsm_activation experience_id={payload.get('source_experience_id')} "
                f"activation_id={payload.get('source_activation_id')} "
                f"match_score={payload.get('source_match_score')} viability={payload.get('source_viability')} "
                f"effective_confidence={payload.get('source_effective_confidence')}"
            )
        elif payload.get("source") == "expsm_mechanism_search":
            print(
                f"    source=expsm_mechanism_search experience_id={payload.get('source_experience_id')} "
                f"mechanism_search_id={payload.get('source_mechanism_search_id')} "
                f"target={self.pattern_registry.debug_name(str(payload.get('source_target_pattern_id')))} "
                f"target_kind={payload.get('source_target_kind')} "
                f"purpose={payload.get('source_mechanism_purpose')} "
                f"mechanism_score={payload.get('source_mechanism_score')}"
            )
        breakdown = payload.get("score_breakdown")
        if isinstance(breakdown, Mapping):
            print(
                f"    score_breakdown: base={breakdown.get('base_score')} "
                f"final={breakdown.get('final_score')} "
                f"memory={breakdown.get('memory_score')} "
                f"expsm_bonus={breakdown.get('expsm_bonus')} "
                f"mechanism_source={breakdown.get('mechanism_source_score')}"
            )

    def _print_decision_audit(self, payload: dict[str, Any]) -> None:
        selected = payload.get("selected", {})
        alternatives = payload.get("alternatives", ())
        audit = payload.get("audit", {})
        print(f"  {payload.get('decision_audit_id')} decision={payload.get('source_decision_id')}")
        if isinstance(selected, Mapping):
            print(
                f"    selected: {self._debug_value('action_pattern', selected.get('action_pattern'))} "
                f"source={selected.get('source')} score={selected.get('final_score')}"
            )
        if isinstance(audit, Mapping):
            print(
                f"    confidence: {audit.get('audit_confidence')} "
                f"margin={audit.get('score_margin')}"
            )
            print(
                f"    value: {audit.get('value_scope')} {audit.get('value_influence')} "
                f"delta={audit.get('value_delta')} ranking={audit.get('ranking_effect')}"
            )
        print("    alternatives:")
        if not alternatives:
            print("      none")
            return
        for alternative in alternatives[:8]:
            if not isinstance(alternative, Mapping):
                continue
            print(
                f"      {self._debug_value('action_pattern', alternative.get('action_pattern'))} "
                f"source={alternative.get('source')} score={alternative.get('final_score')}"
            )

    def _print_action_guard_audit(self, payload: dict[str, Any]) -> None:
        summary = payload.get("summary", {})
        selected = payload.get("selected", {})
        blocked = payload.get("blocked_candidates", ())
        print(f"  {payload.get('action_guard_audit_id')} decision={payload.get('source_decision_id')}")
        print(f"    mode: {payload.get('mode')}")
        if isinstance(summary, Mapping):
            print(
                f"    proposed={summary.get('proposed_count')} "
                f"allowed={summary.get('allowed_count')} blocked={summary.get('blocked_count')}"
            )
            print(
                f"    effect: {summary.get('guard_effect')} "
                f"severity={summary.get('severity')}"
            )
        if isinstance(selected, Mapping):
            print(
                f"    selected: {self._debug_value('action_pattern_id', selected.get('action_pattern_id'))} "
                f"score={selected.get('final_score')}"
            )
        print("    blocked:")
        if not blocked:
            print("      none")
            return
        for item in blocked[:8]:
            if not isinstance(item, Mapping):
                continue
            print(
                f"      {self._debug_value('action_pattern_id', item.get('action_pattern_id'))} "
                f"score={item.get('final_score')} reason={item.get('guard_reason')}"
            )

    def _print_decision_cycle_summary(self, payload: dict[str, Any]) -> None:
        selected = payload.get("selected", {})
        decision = payload.get("decision_summary", {})
        guard = payload.get("guard_summary", {})
        cycle = payload.get("cycle_summary", {})
        print(f"  {payload.get('decision_cycle_summary_id')}")
        if isinstance(selected, Mapping):
            print(
                f"    selected: {self._debug_value('action_pattern_id', selected.get('action_pattern_id'))} "
                f"source={selected.get('source')} score={selected.get('final_score')}"
            )
        if isinstance(cycle, Mapping):
            print(
                f"    status: {cycle.get('cycle_status')} "
                f"confidence={cycle.get('cycle_confidence')}"
            )
        if isinstance(decision, Mapping):
            print(
                f"    decision: {decision.get('audit_confidence')} "
                f"margin={decision.get('score_margin')}"
            )
            print(
                f"    value: {decision.get('value_influence')} "
                f"{decision.get('value_influence_scope')} "
                f"delta={decision.get('value_delta')}"
            )
        if isinstance(guard, Mapping):
            if guard.get("available"):
                print(
                    f"    guard: {guard.get('guard_effect')} "
                    f"severity={guard.get('severity')}"
                )
            else:
                print("    guard: missing")
        flags = cycle.get("flags", ()) if isinstance(cycle, Mapping) else ()
        print(f"    flags: {', '.join(flags) if flags else 'none'}")

    def _print_expsm_similarity(self, payload: dict[str, Any]) -> None:
        print(
            f"  group_id={payload.get('group_id')} records={', '.join(payload.get('record_ids', []))} "
            f"max_similarity={payload.get('max_similarity_score')} avg_similarity={payload.get('avg_similarity_score')} "
            f"future_competition_candidate={payload.get('future_competition_candidate')}"
        )

    def _print_expsm_competition(self, payload: dict[str, Any]) -> None:
        selected = payload.get("selected", {})
        print(
            f"  observation_id={payload.get('competition_observation_id')} "
            f"decision_id={payload.get('decision_id')} "
            f"candidate_count={payload.get('candidate_count')}"
        )
        if isinstance(selected, Mapping):
            print(
                f"    selected: experience {selected.get('experience_id')} / "
                f"{self.pattern_registry.debug_name(str(selected.get('action_pattern')))} / "
                f"score {selected.get('final_score')}"
            )
        print("    alternatives:")
        alternatives = payload.get("alternatives", ())
        if not alternatives:
            print("      none")
        for alternative in alternatives:
            if not isinstance(alternative, Mapping):
                continue
            punished = "not punished" if alternative.get("unused_not_punished") else "unknown"
            print(
                f"      experience {alternative.get('experience_id')} / "
                f"{self.pattern_registry.debug_name(str(alternative.get('action_pattern')))} / "
                f"score {alternative.get('final_score')} / {punished}"
            )
        print(
            f"    same_action_pattern: {payload.get('same_action_pattern')} "
            f"unused_records_punished={payload.get('unused_records_punished')} "
            f"permanent_memory_modified={payload.get('permanent_memory_modified')}"
        )

    def _print_evaluation_signal(self, payload: dict[str, Any]) -> None:
        dimensions = payload.get("evaluation_dimensions", {})
        print(
            f"  evaluation_id={payload.get('evaluation_id')} scope={payload.get('evaluation_scope')} "
            f"source_marker={payload.get('source_marker')}"
        )
        if isinstance(dimensions, Mapping):
            print(
                f"    usefulness={dimensions.get('usefulness')} harmfulness={dimensions.get('harmfulness')} "
                f"need={dimensions.get('need')} want={dimensions.get('want')} avoid={dimensions.get('avoid')} "
                f"safety={dimensions.get('safety')} priority={dimensions.get('priority')}"
            )
        print("    target_patterns:")
        for pattern_id in payload.get("target_patterns", ()):
            print(f"      {self.pattern_registry.debug_name(pattern_id)}")

    def _print_evaluation_target(self, payload: dict[str, Any]) -> None:
        roles = payload.get("target_role_names", ())
        if not isinstance(roles, (list, tuple)):
            roles = ()
        pattern_id = str(payload.get("pattern_id", ""))
        print(f"  {payload.get('target_observation_id')}")
        print(f"    pattern: {self.pattern_registry.debug_name(pattern_id)}")
        print(f"    kind: {payload.get('target_kind')}")
        print(f"    roles: {', '.join(str(role) for role in roles)}")
        print(f"    score: {payload.get('target_score')}")

    def _print_akbsm_association_probe(self, payload: dict[str, Any]) -> None:
        print(f"  {payload.get('probe_id')}")
        print(f"    source: {self.pattern_registry.debug_name(str(payload.get('source_pattern_id', '')))}")
        print(f"    target kind: {payload.get('target_kind')}")
        print(f"    found: {payload.get('associations_found')}")
        associations = payload.get("associated_patterns", ())
        if not associations:
            print("    associations: none")
            return
        print("    associations:")
        for association in associations:
            if not isinstance(association, Mapping):
                continue
            print(
                f"      {self.pattern_registry.debug_name(str(association.get('pattern_id', '')))} "
                f"relation={association.get('relation_type')} "
                f"score={association.get('score')} distance={association.get('distance')}"
            )

    def _print_expsm_mechanism_search(self, payload: dict[str, Any]) -> None:
        print(f"  {payload.get('mechanism_search_id')}")
        print(f"    target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")
        print(f"    kind: {payload.get('target_kind')}")
        print(f"    found: {payload.get('mechanisms_found')}")
        mechanisms = payload.get("mechanisms", ())
        if not mechanisms:
            print("    mechanisms: none")
            return
        print("    mechanisms:")
        for mechanism in mechanisms:
            if not isinstance(mechanism, Mapping):
                continue
            print(
                f"      experience {mechanism.get('experience_id')} "
                f"purpose={mechanism.get('mechanism_purpose')} "
                f"base={mechanism.get('base_mechanism_score', mechanism.get('mechanism_score'))} "
                f"adjusted={mechanism.get('value_adjusted_score', mechanism.get('mechanism_score'))}"
            )
            if "value_bonus" in mechanism or "value_penalty" in mechanism:
                print(
                    f"        value_bonus={mechanism.get('value_bonus', 0.0)} "
                    f"penalty={mechanism.get('value_penalty', 0.0)} "
                    f"balance={mechanism.get('value_balance', 0.0)} "
                    f"confidence={mechanism.get('value_confidence', 0.0)} "
                    f"risk={mechanism.get('value_risk', 0.0)}"
                )
                print(
                    f"        value mode={mechanism.get('value_scoring_mode', 'no_value')} "
                    f"generic bonus={mechanism.get('generic_value_bonus', 0.0)} "
                    f"penalty={mechanism.get('generic_value_penalty', 0.0)} "
                    f"target bonus={mechanism.get('target_specific_value_bonus', 0.0)} "
                    f"penalty={mechanism.get('target_specific_value_penalty', 0.0)} "
                    f"helpful_match={mechanism.get('target_helpful_match_score', 0.0)} "
                    f"risky_match={mechanism.get('target_risky_match_score', 0.0)}"
                )

    def _print_target_satisfaction(self, payload: dict[str, Any]) -> None:
        print(f"  {payload.get('target_satisfaction_id')}")
        print(f"    target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")
        print(f"    status: {payload.get('satisfaction_status')}")
        print(f"    score: {payload.get('satisfaction_score')}")
        print(f"    evidence_strength: {payload.get('evidence_strength')}")
        print(
            f"    source: {payload.get('source_mechanism_search_id')} / "
            f"experience {payload.get('source_experience_id')}"
        )

    def _print_value_feedback_candidate(self, payload: dict[str, Any]) -> None:
        print(f"  {payload.get('value_feedback_candidate_id')}")
        print(f"    experience: {payload.get('source_experience_id')}")
        print(f"    target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")
        print(
            f"    satisfaction: {payload.get('satisfaction_status')} "
            f"score={payload.get('satisfaction_score')} evidence={payload.get('evidence_strength')}"
        )
        print(f"    direction: {payload.get('value_direction')}")
        print(f"    strength: {payload.get('candidate_strength')}")
        print(f"    recommended future operation: {payload.get('recommended_future_operation')}")

    def _print_value_feedback_review(self, payload: dict[str, Any]) -> None:
        print(f"  {payload.get('value_feedback_review_id')}")
        print(f"    candidate: {payload.get('source_value_feedback_candidate_id')}")
        print(f"    experience: {payload.get('source_experience_id')}")
        print(f"    target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")
        print(f"    decision: {payload.get('review_decision')}")
        print(f"    reason: {payload.get('review_reason')}")
        print(f"    strength: {payload.get('candidate_strength')}")
        print(f"    evidence: {payload.get('evidence_strength')}")
        print(f"    future op: {payload.get('recommended_future_operation')}")
        print(f"    apply_now: {payload.get('apply_now')}")

    def _print_value_feedback_update(self, payload: dict[str, Any]) -> None:
        print(f"  {payload.get('value_feedback_update_id')}")
        print(f"    experience: {payload.get('source_experience_id')}")
        print(f"    direction: {payload.get('value_direction')}")
        print(f"    target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")
        print(f"    strength: {payload.get('candidate_strength')}")
        print(f"    evidence: {payload.get('evidence_strength')}")
        print("    updated: value_feedback metadata only")
        print(f"    semantic_core_modified: {payload.get('semantic_core_modified')}")
        print(f"    technical_feedback_modified: {payload.get('technical_feedback_modified')}")

    def _print_consolidation_pressure(self, payload: dict[str, Any]) -> None:
        sources = payload.get("sources", {})
        print(
            f"  id={payload.get('pressure_id')} value={payload.get('pressure_value')} "
            f"level={payload.get('pressure_level')} "
            f"pending_experience={sources.get('pending_experience_candidates')} "
            f"pending_consolidation={sources.get('pending_consolidation_candidates')} "
            f"fatigue={sources.get('fatigue')} tension={sources.get('tension')}"
        )

    def _print_mode_change(self, payload: dict[str, Any]) -> None:
        print(
            f"  id={payload.get('mode_change_id')} {payload.get('from_mode')} -> {payload.get('to_mode')} "
            f"reason={payload.get('reason')} activation={payload.get('activation')}"
        )

    def _debug_signature(self, signature: Any) -> Any:
        if not isinstance(signature, (list, tuple)) or not signature:
            return signature
        debug_items: list[Any] = [signature[0]]
        for item in signature[1:]:
            if isinstance(item, (list, tuple)):
                debug_items.append([self.pattern_registry.debug_name(pattern_id) for pattern_id in item])
            else:
                debug_items.append(item)
        return debug_items

    def _debug_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: self._debug_value(key, value) for key, value in payload.items() if not key.startswith("_")}

    def _debug_activations(self, activations: Any) -> dict[str, float]:
        return {self.pattern_registry.debug_name(pattern_id): value for pattern_id, value in dict(activations).items()}

    def _debug_value(self, key: str, value: Any) -> Any:
        if key.endswith("_pattern_id"):
            return self.pattern_registry.debug_name(value)
        if key in {"label_kind", "prediction_kind", "outcome_pattern_id", "update_kind", "candidate_kind", "pressure_kind", "mode_pattern_id", "effect_kind", "review_kind", "draft_kind", "status_pattern_id", "review_status_pattern_id", "observation_kind", "feedback_kind", "selected_action", "evaluation_kind", "target_kind_pattern", "probe_kind", "search_kind"}:
            return self.pattern_registry.debug_name(value)
        if key.endswith("_pattern_ids") and isinstance(value, (list, tuple)):
            return [self.pattern_registry.debug_name(item) for item in value]
        if key in {
            "predicted_patterns",
            "suggested_patterns",
            "generate_thought_patterns",
            "matched_patterns",
            "missing_patterns",
            "homeostasis_patterns",
            "pressure_patterns",
            "reason_patterns",
            "reasons",
            "secondary_effect_patterns",
            "input_patterns",
            "if_patterns",
            "then_patterns",
            "result_patterns",
            "decision_patterns",
            "effect_patterns",
            "outcome_patterns",
            "expected_patterns",
            "actual_patterns",
            "matched_expected_patterns",
            "target_patterns",
            "evaluation_patterns",
            "target_roles",
        } and isinstance(value, (list, tuple)):
            return [self.pattern_registry.debug_name(item) for item in value]
        if key == "activation_focus" and isinstance(value, Mapping):
            return self._debug_activations(value)
        if key == "predicted_pattern" and isinstance(value, Mapping):
            return {"activations": self._debug_activations(value.get("activations", {}))}
        if isinstance(value, Mapping):
            return {child_key: self._debug_value(child_key, child_value) for child_key, child_value in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._debug_value(key, item) for item in value]
        return value


def _retention_result(
    policy: ContextRetentionPolicy,
    events: list[ContextOperation],
    before_count: int,
    after_count: int,
    pruned_count: int,
) -> ContextRetentionResult:
    return ContextRetentionResult(
        enabled=policy.enabled,
        max_events=policy.max_events,
        before_count=before_count,
        after_count=after_count,
        pruned_count=pruned_count,
        oldest_remaining_tick=events[0].tick if events else None,
        newest_remaining_tick=events[-1].tick if events else None,
    )


def _entry_bounds_for_list(entries: list[object]) -> tuple[int | None, int | None, int]:
    bounds = [_entry_tick_bounds(entry) for entry in entries]
    known = [item for item in bounds if item[0] is not None and item[1] is not None]
    unknown = len(bounds) - len(known)
    if not known:
        return None, None, unknown
    return min(item[0] for item in known if item[0] is not None), max(item[1] for item in known if item[1] is not None), unknown


def _prune_entries_by_tick(
    entries: list[object],
    oldest_event_tick: int | None,
    policy: SideListRetentionPolicy,
) -> tuple[list[object], int, int]:
    if not policy.prune_older_than_oldest_event or oldest_event_tick is None:
        return entries, 0, 0
    retained: list[object] = []
    pruned = 0
    unknown = 0
    for entry in entries:
        oldest_tick, newest_tick = _entry_tick_bounds(entry)
        if oldest_tick is None or newest_tick is None:
            unknown += 1
            if policy.keep_unknown_tick_entries:
                retained.append(entry)
            else:
                pruned += 1
            continue
        if newest_tick < oldest_event_tick:
            pruned += 1
            continue
        retained.append(entry)
    return retained, pruned, unknown


def _prune_entries_by_max(entries: list[object], max_entries: int | None) -> tuple[list[object], int]:
    if max_entries is None or len(entries) <= max_entries:
        return entries, 0
    pruned = len(entries) - max_entries
    return entries[-max_entries:], pruned


def _entry_tick_bounds(entry: object) -> tuple[int | None, int | None]:
    if isinstance(entry, Mapping):
        from_tick = entry.get("from_tick")
        to_tick = entry.get("to_tick")
        if isinstance(from_tick, int) and isinstance(to_tick, int):
            return from_tick, to_tick
        for key in ("_event_tick", "tick", "source_tick", "created_at_tick", "updated_at_tick"):
            value = entry.get(key)
            if isinstance(value, int):
                return value, value
        return None, None
    value = getattr(entry, "tick", None)
    if isinstance(value, int):
        return value, value
    from_tick = getattr(entry, "from_tick", None)
    to_tick = getattr(entry, "to_tick", None)
    if isinstance(from_tick, int) and isinstance(to_tick, int):
        return from_tick, to_tick
    if isinstance(from_tick, int):
        return from_tick, from_tick
    return None, None
