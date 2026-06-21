from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.experience.causal_trace import CausalTrace, build_causal_trace
from clc.experience.learnability_filter import LearnabilityFilter
from clc.field.active_context_field import ActiveContextField


class ExperienceCandidateBuilder:
    """Builds temporary experience candidates from evaluated internal chains."""

    module_name = "experience_candidate_builder"

    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.candidate_kind = pattern_registry.id("experience_candidate")
        self.status_patterns = {
            "positive_candidate": pattern_registry.id("experience_positive_candidate"),
            "negative_candidate": pattern_registry.id("experience_negative_candidate"),
            "weak_candidate": pattern_registry.id("experience_weak_candidate"),
            "pending_consolidation": pattern_registry.id("experience_pending_consolidation"),
        }
        self._handled_outcome_ids: set[str] = set()
        self.pattern_registry = pattern_registry
        self.learnability_filter = LearnabilityFilter(pattern_registry)
        self._skipped_learnability: list[dict[str, Any]] = []

    def run(self, tick: int, memory: ContextMemory, active_field: ActiveContextField) -> list[ContextOperation]:
        operations: list[ContextOperation] = []
        for outcome in memory.get_recent_outcomes(16):
            outcome_id = outcome.get("outcome_id")
            status = outcome.get("outcome_status")
            if not outcome_id or outcome_id in self._handled_outcome_ids:
                continue
            if status not in {"confirmed", "partially_confirmed", "failed"}:
                continue
            self._handled_outcome_ids.add(outcome_id)
            trace = build_causal_trace(outcome, memory, active_field, self.pattern_registry)
            learnability = self.learnability_filter.classify_trace(trace)
            if not learnability["learnable"]:
                self._record_skipped(tick, outcome, trace, learnability)
                continue
            payload = self._build_candidate(outcome, trace, learnability)
            operations.append(
                ContextOperation(
                    self.id_gen.next("op"),
                    OperationMarker.EXPERIENCE_CANDIDATE,
                    tick,
                    self.module_name,
                    None,
                    payload,
                )
            )
        return operations

    def debug_skipped_learnability(self, limit: int = 8) -> list[dict[str, Any]]:
        return self._skipped_learnability[-limit:]

    def _build_candidate(
        self,
        outcome: dict[str, Any],
        trace: CausalTrace,
        learnability: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_status = self._candidate_status(outcome.get("outcome_status"))
        confidence = self._confidence(outcome, candidate_status)
        core_chain = trace.core_chain()
        context_refs = trace.context_refs()
        payload = {
            "candidate_id": self.id_gen.next("exp_cand"),
            "candidate_kind": self.candidate_kind,
            "candidate_status": candidate_status,
            "candidate_status_pattern_id": self.status_patterns[candidate_status],
            "source_outcome_id": outcome.get("outcome_id"),
            "source_outcome_status": outcome.get("outcome_status"),
            "source_outcome_event_id": outcome.get("source_event_id"),
            "core_chain": core_chain,
            "context_refs": context_refs,
            "pattern_refs": _pattern_refs_from_trace(core_chain, context_refs),
            "learnability": learnability,
            "tone_result": {
                "tone_delta": dict(outcome.get("tone_delta", {})),
                "valence": self._valence(candidate_status, outcome.get("tone_delta", {})),
            },
            "confidence": confidence,
            "priority": self._priority(candidate_status, confidence),
            "activation": confidence,
            "ttl": 8,
            "write_status": "pending_consolidation",
            "write_status_pattern_id": self.status_patterns["pending_consolidation"],
        }
        return payload

    def _record_skipped(
        self,
        tick: int,
        outcome: dict[str, Any],
        trace: CausalTrace,
        learnability: dict[str, Any],
    ) -> None:
        self._skipped_learnability.append(
            {
                "tick": tick,
                "outcome_id": outcome.get("outcome_id"),
                "source_outcome_status": outcome.get("outcome_status"),
                "category": learnability.get("category"),
                "reason_patterns": list(learnability.get("reason_patterns", ())),
                "confidence": learnability.get("confidence"),
                "core_chain": trace.core_chain(),
            }
        )
        if len(self._skipped_learnability) > 64:
            self._skipped_learnability = self._skipped_learnability[-64:]

    def _candidate_status(self, outcome_status: str | None) -> str:
        if outcome_status == "confirmed":
            return "positive_candidate"
        if outcome_status == "failed":
            return "negative_candidate"
        return "weak_candidate"

    def _confidence(self, outcome: dict[str, Any], candidate_status: str) -> float:
        confidence = float(outcome.get("confidence", outcome.get("activation", 0.5)))
        if candidate_status == "weak_candidate":
            confidence *= 0.7
        return round(max(0.05, min(1.0, confidence)), 3)

    def _priority(self, candidate_status: str, confidence: float) -> float:
        if candidate_status == "positive_candidate":
            return round(0.45 + confidence * 0.25, 3)
        if candidate_status == "negative_candidate":
            return round(0.55 + confidence * 0.3, 3)
        return round(0.25 + confidence * 0.2, 3)

    def _valence(self, candidate_status: str, tone_delta: dict[str, Any]) -> float:
        if candidate_status == "positive_candidate":
            base = 0.55
        elif candidate_status == "negative_candidate":
            base = -0.55
        else:
            base = 0.1
        base += float(tone_delta.get("satisfaction", 0.0)) * 2.0
        base += float(tone_delta.get("stability", 0.0))
        base -= float(tone_delta.get("pain", 0.0)) * 2.0
        base -= float(tone_delta.get("tension", 0.0))
        return round(max(-1.0, min(1.0, base)), 3)


def _unique(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(values) if value]


def _pattern_refs_from_trace(core_chain: dict[str, list[str]], context_refs: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        "input_patterns": _unique(list(context_refs.get("active_patterns", ()))),
        "decision_patterns": _unique(list(core_chain.get("decision_patterns", ()))),
        "effect_patterns": _unique(list(core_chain.get("effect_patterns", ()))),
        "predicted_patterns": _unique(list(core_chain.get("predicted_patterns", ()))),
        "outcome_patterns": _unique(list(core_chain.get("outcome_patterns", ()))),
    }
