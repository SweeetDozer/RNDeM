from clc.action.action_candidate_field import ActionCandidateField
from clc.action.candidate_sources import SOURCE_EXPSM_ACTIVATION, SOURCE_EXPSM_MECHANISM_SEARCH
from clc.context.context_memory import ContextMemory
from clc.core.pattern_registry import PatternRegistry
from clc.field.active_context_field import ActiveContextField
from clc.system.system_state import SystemState


class ActionProposer:
    """Turns active patterns and tone pressure into internal action candidates."""

    def __init__(self, pattern_registry: PatternRegistry) -> None:
        self.pattern_registry = pattern_registry
        self.thought_need_more_data = pattern_registry.id("thought_need_more_data")
        self.thought_increase_attention = pattern_registry.id("thought_increase_attention")
        self.thought_inspect_pattern = pattern_registry.id("thought_inspect_pattern")
        self.thought_store_candidate = pattern_registry.id("thought_store_candidate")
        self.thought_preserve_integrity = pattern_registry.id("thought_preserve_integrity")
        self.thought_reduce_load = pattern_registry.id("thought_reduce_load")
        self.risk_label = pattern_registry.id("experienced_risk_pattern")
        self.internal_risk_label = pattern_registry.id("internal_state_risk")
        self.novelty_label = pattern_registry.id("novel_activation_pattern")
        self.homeostasis_reduce_load = pattern_registry.id("homeostasis_reduce_load_pressure")
        self.homeostasis_preserve_integrity = pattern_registry.id("homeostasis_preserve_integrity_pressure")
        self.homeostasis_tension_relief = pattern_registry.id("homeostasis_tension_relief")
        self.experience_pending_consolidation = pattern_registry.id("experience_pending_consolidation")
        self.experience_negative_candidate = pattern_registry.id("experience_negative_candidate")
        self.consolidation_pending_memory_write = pattern_registry.id("consolidation_pending_memory_write")
        self.consolidation_negative_candidate = pattern_registry.id("consolidation_negative_candidate")
        self.consolidation_pressure_medium = pattern_registry.id("consolidation_pressure_medium")
        self.consolidation_pressure_high = pattern_registry.id("consolidation_pressure_high")
        self.memory_review_approved = pattern_registry.id("memory_review_approved_for_expsm")
        self.memory_review_needs_more_support = pattern_registry.id("memory_review_needs_more_support")
        self.memory_review_rejected_incomplete = pattern_registry.id("memory_review_rejected_incomplete_core")
        self.memory_review_rejected_unstable = pattern_registry.id("memory_review_rejected_unstable")
        self.draft_commit_ready = pattern_registry.id("draft_commit_ready_to_commit")
        self.committed_draft_pending_update = pattern_registry.id("committed_draft_pending_expsm_update")
        self.expsm_update_approved = pattern_registry.id("expsm_update_approved_for_update")
        self.actions = {
            "wait_more_data": pattern_registry.id("action_wait_more_data"),
            "increase_attention": pattern_registry.id("action_increase_attention"),
            "inspect_pattern": pattern_registry.id("action_inspect_pattern"),
            "store_memory_candidate": pattern_registry.id("action_store_memory_candidate"),
            "commit_memory_draft": pattern_registry.id("action_commit_memory_draft"),
            "review_committed_memory_update": pattern_registry.id("action_review_committed_memory_update"),
            "update_committed_expsm_record": pattern_registry.id("action_update_committed_expsm_record"),
            "reduce_load": pattern_registry.id("action_reduce_load"),
            "preserve_integrity": pattern_registry.id("action_preserve_integrity"),
            "continue_observation": pattern_registry.id("action_continue_observation"),
            "generate_more_thought": pattern_registry.id("action_generate_more_thought"),
            "enter_consolidation_mode": pattern_registry.id("action_enter_consolidation_mode"),
            "exit_consolidation_mode": pattern_registry.id("action_exit_consolidation_mode"),
        }
        self.action_ids = set(self.actions.values())

    def propose(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        candidate_field: ActionCandidateField,
        system_state: SystemState | None = None,
    ) -> None:
        tone = memory.get_current_tone()
        active_by_id = {pattern.pattern_id: pattern for pattern in active_field.get_top_patterns(limit=50)}
        recent_event_ids = tuple(event.op_id for event in memory.get_recent_events(6))
        mode = system_state.mode if system_state is not None else "active"

        high_pressure = active_by_id.get(self.consolidation_pressure_high)
        medium_pressure = active_by_id.get(self.consolidation_pressure_medium)
        pending_consolidation_count = len(memory.get_recent_consolidation_candidates(12))
        if mode == "active" and high_pressure:
            urgency = min(0.95, 0.72 + tone.fatigue * 0.2 + min(pending_consolidation_count * 0.025, 0.15))
            self._propose(
                candidate_field,
                "enter_consolidation_mode",
                high_pressure.activation,
                tick,
                0.9,
                urgency,
                0.02,
                0.08,
                (high_pressure.pattern_id,),
                recent_event_ids,
            )
        elif mode == "active" and medium_pressure:
            self._propose(
                candidate_field,
                "enter_consolidation_mode",
                medium_pressure.activation * 0.75,
                tick,
                0.66,
                0.35,
                0.02,
                0.08,
                (medium_pressure.pattern_id,),
                recent_event_ids,
            )

        if mode == "consolidation":
            ready_commit = active_by_id.get(self.draft_commit_ready)
            if ready_commit:
                self._propose(
                    candidate_field,
                    "commit_memory_draft",
                    ready_commit.activation,
                    tick,
                    0.88,
                    0.46,
                    0.03,
                    0.16,
                    (ready_commit.pattern_id,),
                    recent_event_ids,
                )
            pending_update = active_by_id.get(self.committed_draft_pending_update)
            if pending_update:
                self._propose(
                    candidate_field,
                    "review_committed_memory_update",
                    pending_update.activation,
                    tick,
                    0.82,
                    0.38,
                    0.02,
                    0.1,
                    (pending_update.pattern_id,),
                    recent_event_ids,
                )
            approved_update = active_by_id.get(self.expsm_update_approved)
            if approved_update:
                self._propose(
                    candidate_field,
                    "update_committed_expsm_record",
                    approved_update.activation,
                    tick,
                    0.78,
                    0.34,
                    0.02,
                    0.12,
                    (approved_update.pattern_id,),
                    recent_event_ids,
                )
            approved_review = active_by_id.get(self.memory_review_approved)
            if approved_review:
                self._propose(
                    candidate_field,
                    "store_memory_candidate",
                    approved_review.activation,
                    tick,
                    0.86,
                    0.55,
                    0.04,
                    0.18,
                    (approved_review.pattern_id,),
                    recent_event_ids,
                )
            needs_support = active_by_id.get(self.memory_review_needs_more_support)
            if needs_support:
                self._propose(
                    candidate_field,
                    "continue_observation",
                    needs_support.activation * 0.6,
                    tick,
                    0.58,
                    0.18,
                    0.02,
                    0.05,
                    (needs_support.pattern_id,),
                    recent_event_ids,
                )
            rejected_review_activation = max(
                active_by_id.get(self.memory_review_rejected_incomplete).activation if active_by_id.get(self.memory_review_rejected_incomplete) else 0.0,
                active_by_id.get(self.memory_review_rejected_unstable).activation if active_by_id.get(self.memory_review_rejected_unstable) else 0.0,
            )
            if rejected_review_activation:
                self._propose(
                    candidate_field,
                    "inspect_pattern",
                    rejected_review_activation,
                    tick,
                    0.62,
                    0.28,
                    0.06,
                    0.12,
                    (self.memory_review_rejected_incomplete, self.memory_review_rejected_unstable),
                    recent_event_ids,
                )
            elapsed = tick - system_state.mode_entered_tick if system_state is not None else 0
            if elapsed >= 3:
                self._propose(
                    candidate_field,
                    "exit_consolidation_mode",
                    0.72,
                    tick,
                    0.78,
                    0.45,
                    0.02,
                    0.08,
                    (),
                    recent_event_ids,
                )
            return

        self._propose_expsm_actions(tick, memory, candidate_field)
        self._propose_expsm_mechanism_actions(tick, memory, candidate_field)

        need_more = active_by_id.get(self.thought_need_more_data)
        if need_more:
            self._propose(candidate_field, "wait_more_data", need_more.activation, tick, 0.62, 0.2, 0.05, 0.1, (need_more.pattern_id,), recent_event_ids)
            self._propose(candidate_field, "continue_observation", need_more.activation * 0.8, tick, 0.58, 0.15, 0.02, 0.05, (need_more.pattern_id,), recent_event_ids)

        increase_attention = active_by_id.get(self.thought_increase_attention)
        if increase_attention:
            self._propose(candidate_field, "increase_attention", increase_attention.activation, tick, 0.72, 0.35, 0.08, 0.18, (increase_attention.pattern_id,), recent_event_ids)

        inspect = active_by_id.get(self.thought_inspect_pattern)
        if inspect:
            self._propose(candidate_field, "inspect_pattern", inspect.activation, tick, 0.68, 0.18, 0.08, 0.12, (inspect.pattern_id,), recent_event_ids)

        store = active_by_id.get(self.thought_store_candidate)
        if store:
            self._propose(candidate_field, "store_memory_candidate", store.activation, tick, 0.6, 0.12, 0.12, 0.2, (store.pattern_id,), recent_event_ids)

        preserve = active_by_id.get(self.thought_preserve_integrity)
        if preserve:
            self._propose(candidate_field, "preserve_integrity", preserve.activation, tick, 0.82, 0.65, 0.05, 0.22, (preserve.pattern_id,), recent_event_ids)

        reduce = active_by_id.get(self.thought_reduce_load)
        if reduce:
            self._propose(candidate_field, "reduce_load", reduce.activation, tick, 0.72, 0.45, 0.04, 0.18, (reduce.pattern_id,), recent_event_ids)

        homeostasis_reduce = active_by_id.get(self.homeostasis_reduce_load)
        if homeostasis_reduce:
            urgency = min(0.75, 0.35 + homeostasis_reduce.activation * 0.4)
            self._propose(candidate_field, "reduce_load", homeostasis_reduce.activation, tick, 0.82, urgency, 0.03, 0.14, (homeostasis_reduce.pattern_id,), recent_event_ids)

        homeostasis_preserve = active_by_id.get(self.homeostasis_preserve_integrity)
        if homeostasis_preserve:
            urgency = min(0.8, 0.45 + homeostasis_preserve.activation * 0.35)
            self._propose(candidate_field, "preserve_integrity", homeostasis_preserve.activation, tick, 0.84, urgency, 0.04, 0.2, (homeostasis_preserve.pattern_id,), recent_event_ids)

        homeostasis_relief = active_by_id.get(self.homeostasis_tension_relief)
        if homeostasis_relief:
            self._propose(candidate_field, "wait_more_data", homeostasis_relief.activation * 0.55, tick, 0.55, 0.08, 0.02, 0.08, (homeostasis_relief.pattern_id,), recent_event_ids)
            self._propose(candidate_field, "continue_observation", homeostasis_relief.activation * 0.65, tick, 0.58, 0.08, 0.01, 0.04, (homeostasis_relief.pattern_id,), recent_event_ids)

        if tone.tension > 0.5:
            self._propose(candidate_field, "increase_attention", tone.tension, tick, 0.65, 0.45, 0.1, 0.18, (), recent_event_ids)

        if tone.curiosity > 0.5 and tone.risk_sensitivity < 0.8:
            self._propose(candidate_field, "inspect_pattern", tone.curiosity, tick, 0.6, 0.2, 0.08, 0.12, (), recent_event_ids)

        if tone.integrity < 0.8:
            amount = 1.0 - tone.integrity
            self._propose(candidate_field, "preserve_integrity", max(0.65, amount), tick, 0.82, 0.75, 0.05, 0.25, (), recent_event_ids)
            self._propose(candidate_field, "reduce_load", max(0.55, amount), tick, 0.72, 0.55, 0.04, 0.2, (), recent_event_ids)

        if tone.fatigue > 0.6:
            self._propose(candidate_field, "reduce_load", tone.fatigue, tick, 0.68, 0.35, 0.03, 0.15, (), recent_event_ids)

        risk_patterns = [active_by_id.get(self.risk_label), active_by_id.get(self.internal_risk_label)]
        strongest_risk = max((pattern.activation for pattern in risk_patterns if pattern is not None), default=0.0)
        if strongest_risk >= 0.6:
            self._propose(candidate_field, "increase_attention", strongest_risk, tick, 0.78, 0.75, 0.12, 0.2, (self.risk_label, self.internal_risk_label), recent_event_ids)

        pending_experience = active_by_id.get(self.experience_pending_consolidation)
        if pending_experience and strongest_risk < 0.65:
            self._propose(candidate_field, "store_memory_candidate", pending_experience.activation, tick, 0.7, 0.28, 0.08, 0.2, (pending_experience.pattern_id,), recent_event_ids)

        pending_consolidation = active_by_id.get(self.consolidation_pending_memory_write)
        if pending_consolidation and strongest_risk < 0.65:
            self._propose(candidate_field, "store_memory_candidate", pending_consolidation.activation, tick, 0.82, 0.42, 0.08, 0.2, (pending_consolidation.pattern_id,), recent_event_ids)

        negative_experience = active_by_id.get(self.experience_negative_candidate)
        if negative_experience:
            self._propose(candidate_field, "inspect_pattern", negative_experience.activation, tick, 0.72, 0.32, 0.08, 0.12, (negative_experience.pattern_id,), recent_event_ids)
            self._propose(candidate_field, "generate_more_thought", negative_experience.activation * 0.7, tick, 0.62, 0.22, 0.05, 0.08, (negative_experience.pattern_id,), recent_event_ids)

        negative_consolidation = active_by_id.get(self.consolidation_negative_candidate)
        if negative_consolidation:
            self._propose(candidate_field, "inspect_pattern", negative_consolidation.activation, tick, 0.78, 0.42, 0.08, 0.12, (negative_consolidation.pattern_id,), recent_event_ids)
            self._propose(candidate_field, "generate_more_thought", negative_consolidation.activation * 0.75, tick, 0.68, 0.28, 0.05, 0.08, (negative_consolidation.pattern_id,), recent_event_ids)

        novelty = active_by_id.get(self.novelty_label)
        current_risk = max((label.get("risk", 0.0) for label in memory.recent_labels(8) if label.get("_event_tick") == tick), default=0.0)
        if novelty and novelty.activation >= 0.45 and current_risk < 0.4:
            self._propose(candidate_field, "inspect_pattern", novelty.activation, tick, 0.7, 0.25, 0.06, 0.12, (novelty.pattern_id,), recent_event_ids)
            self._propose(candidate_field, "store_memory_candidate", novelty.activation * 0.8, tick, 0.58, 0.15, 0.1, 0.22, (novelty.pattern_id,), recent_event_ids)

    def _propose_expsm_actions(self, tick: int, memory: ContextMemory, candidate_field: ActionCandidateField) -> None:
        for activation in memory.get_recent_expsm_activations(6):
            if activation.get("_event_tick") != tick:
                continue
            amount = float(activation.get("activation", activation.get("match_score", 0.0)) or 0.0)
            activation_id = activation.get("activation_id")
            source_events = (str(activation_id),) if activation_id else ()
            activation_kind = activation.get("activation_kind")
            for pattern_id in activation.get("then_patterns", ()):
                if pattern_id not in self.action_ids:
                    continue
                candidate_field.propose(
                    pattern_id=pattern_id,
                    amount=amount,
                    tick=tick,
                    confidence=amount,
                    urgency=0.45,
                    risk=0.04,
                    cost=0.12,
                    source_pattern_ids=tuple(item for item in (pattern_id, activation_kind) if item),
                    source_event_ids=source_events,
                    source_metadata={
                        "source": SOURCE_EXPSM_ACTIVATION,
                        "source_experience_id": str(activation.get("experience_id")),
                        "source_activation_id": str(activation_id),
                        "source_match_score": round(float(activation.get("match_score", amount) or 0.0), 3),
                        "source_viability": round(float(activation.get("viability", 0.0) or 0.0), 3),
                        "source_effective_confidence": round(float(activation.get("effective_confidence", activation.get("confidence", 0.0)) or 0.0), 3),
                        "source_repeatability": round(float(activation.get("repeatability", 0.0) or 0.0), 3),
                    },
                    ttl=3,
                    decay_rate=0.12,
                )

    def _propose_expsm_mechanism_actions(self, tick: int, memory: ContextMemory, candidate_field: ActionCandidateField) -> None:
        for search in memory.get_recent_expsm_mechanism_searches(8):
            search_id = str(search.get("mechanism_search_id", ""))
            if not search_id:
                continue
            target_score = _clamp(float(search.get("target_score", 0.0) or 0.0))
            source_events = (search_id,)
            for mechanism in search.get("mechanisms", ()):
                if not isinstance(mechanism, dict):
                    continue
                base_mechanism_score = _clamp(
                    float(mechanism.get("base_mechanism_score", mechanism.get("mechanism_score", 0.0)) or 0.0)
                )
                mechanism_score = _clamp(float(mechanism.get("value_adjusted_score", mechanism.get("mechanism_score", 0.0)) or 0.0))
                viability = _clamp(float(mechanism.get("viability", 0.0) or 0.0))
                effective_confidence = _clamp(float(mechanism.get("effective_confidence", 0.0) or 0.0))
                repeatability = _clamp(float(mechanism.get("repeatability", 0.0) or 0.0))
                confidence = _clamp(
                    mechanism_score * 0.55
                    + viability * 0.20
                    + effective_confidence * 0.15
                    + repeatability * 0.10
                )
                urgency = min(0.75, _clamp(target_score * 0.45 + mechanism_score * 0.25))
                for pattern_id in mechanism.get("then_patterns", ()):
                    if not self._is_action_pattern(str(pattern_id)):
                        continue
                    candidate_field.propose(
                        pattern_id=str(pattern_id),
                        amount=mechanism_score,
                        tick=tick,
                        confidence=confidence,
                        urgency=urgency,
                        risk=0.05,
                        cost=0.14,
                        source_pattern_ids=tuple(dict.fromkeys((str(pattern_id), str(search.get("target_pattern_id", ""))))),
                        source_event_ids=source_events,
                        source_metadata={
                            "source": SOURCE_EXPSM_MECHANISM_SEARCH,
                            "source_experience_id": str(mechanism.get("experience_id", "")),
                            "source_mechanism_search_id": search_id,
                            "source_target_observation_id": str(search.get("source_target_observation_id", "")),
                            "source_target_pattern_id": str(search.get("target_pattern_id", "")),
                            "source_target_kind": str(search.get("target_kind", "")),
                            "source_target_roles": list(search.get("target_role_names", ())),
                            "source_target_score": round(target_score, 3),
                            "source_mechanism_purpose": str(mechanism.get("mechanism_purpose", "")),
                            "source_mechanism_score": round(mechanism_score, 3),
                            "source_base_mechanism_score": round(base_mechanism_score, 3),
                            "source_value_adjusted_score": round(mechanism_score, 3),
                            "source_value_bonus": round(_clamp(float(mechanism.get("value_bonus", 0.0) or 0.0)), 3),
                            "source_value_penalty": round(_clamp(float(mechanism.get("value_penalty", 0.0) or 0.0)), 3),
                            "source_value_balance": round(float(mechanism.get("value_balance", 0.0) or 0.0), 3),
                            "source_value_confidence": round(_clamp(float(mechanism.get("value_confidence", 0.0) or 0.0)), 3),
                            "source_value_risk": round(_clamp(float(mechanism.get("value_risk", 0.0) or 0.0)), 3),
                            "source_value_trace": dict(mechanism.get("value_trace", {})) if isinstance(mechanism.get("value_trace"), dict) else {},
                            "source_value_scoring_mode": str(mechanism.get("value_scoring_mode", "no_value")),
                            "source_target_specific_value_bonus": round(_clamp(float(mechanism.get("target_specific_value_bonus", 0.0) or 0.0)), 3),
                            "source_target_specific_value_penalty": round(_clamp(float(mechanism.get("target_specific_value_penalty", 0.0) or 0.0)), 3),
                            "source_generic_value_bonus": round(_clamp(float(mechanism.get("generic_value_bonus", 0.0) or 0.0)), 3),
                            "source_generic_value_penalty": round(_clamp(float(mechanism.get("generic_value_penalty", 0.0) or 0.0)), 3),
                            "source_target_helpful_match_score": round(_clamp(float(mechanism.get("target_helpful_match_score", 0.0) or 0.0)), 3),
                            "source_target_risky_match_score": round(_clamp(float(mechanism.get("target_risky_match_score", 0.0) or 0.0)), 3),
                            "source_target_value_trace": dict(mechanism.get("target_value_trace", {})) if isinstance(mechanism.get("target_value_trace"), dict) else {},
                            "source_viability": round(viability, 3),
                            "source_effective_confidence": round(effective_confidence, 3),
                            "source_repeatability": round(repeatability, 3),
                        },
                        ttl=3,
                        decay_rate=0.12,
                    )

    def _is_action_pattern(self, pattern_id: str) -> bool:
        return pattern_id in self.action_ids or self.pattern_registry.is_action(pattern_id)

    def _propose(
        self,
        candidate_field: ActionCandidateField,
        action_name: str,
        amount: float,
        tick: int,
        confidence: float,
        urgency: float,
        risk: float,
        cost: float,
        source_pattern_ids: tuple[str, ...],
        source_event_ids: tuple[str, ...],
    ) -> None:
        candidate_field.propose(
            pattern_id=self.actions[action_name],
            amount=amount,
            tick=tick,
            confidence=confidence,
            urgency=urgency,
            risk=risk,
            cost=cost,
            source_pattern_ids=source_pattern_ids,
            source_event_ids=source_event_ids,
            ttl=3,
            decay_rate=0.12,
        )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
