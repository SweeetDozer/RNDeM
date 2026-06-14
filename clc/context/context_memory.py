from dataclasses import dataclass, field, replace
from collections.abc import Mapping
from typing import Any

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
    consolidation_pressures: list[dict[str, Any]] = field(default_factory=list)
    system_mode_changes: list[dict[str, Any]] = field(default_factory=list)
    neuromodulation_updates: list[dict[str, Any]] = field(default_factory=list)
    module_updates: list[dict[str, Any]] = field(default_factory=list)
    events: list[ContextOperation] = field(default_factory=list)
    windows: list[ContextWindow] = field(default_factory=list)
    tone_state: ToneState = field(default_factory=ToneState)

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
        elif event.marker == OperationMarker.CONSOLIDATION_PRESSURE:
            self.consolidation_pressures.append(payload)
        elif event.marker == OperationMarker.SYSTEM_MODE_CHANGE:
            self.system_mode_changes.append(payload)
        elif event.marker == OperationMarker.MODULE_UPDATE:
            self.module_updates.append(payload)

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
        breakdown = payload.get("score_breakdown")
        if isinstance(breakdown, Mapping):
            print(
                f"    score_breakdown: base={breakdown.get('base_score')} "
                f"final={breakdown.get('final_score')} "
                f"memory={breakdown.get('memory_score')} "
                f"expsm_bonus={breakdown.get('expsm_bonus')}"
            )

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
        if key in {"label_kind", "prediction_kind", "outcome_pattern_id", "update_kind", "candidate_kind", "pressure_kind", "mode_pattern_id", "effect_kind", "review_kind", "draft_kind", "status_pattern_id", "review_status_pattern_id", "observation_kind", "feedback_kind", "selected_action"}:
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
