from dataclasses import dataclass

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.evaluation_field import EvaluationEntry, EvaluationField
from clc.system.system_state import SystemState


NEED_THRESHOLD = 0.50
WANT_THRESHOLD = 0.50
AVOID_THRESHOLD = 0.50
USEFUL_TARGET_THRESHOLD = 0.60
HARMFUL_TARGET_THRESHOLD = 0.50
PRIORITY_THRESHOLD = 0.45
MAX_TARGETS_PER_TICK = 5
TARGET_OBSERVATION_COOLDOWN_TICKS = 3
SIGNIFICANT_DELTA = 0.08


@dataclass
class _ObservationMemory:
    tick: int
    target_score: float
    roles: tuple[str, ...]


class EvaluationTargetObserver:
    """Observes strong value-field entries without turning them into actions."""

    module_name = "evaluation_target_observer"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        self.observation_kind = pattern_registry.id("evaluation_target_observed")
        self.role_ids = {
            "needed_target": pattern_registry.id("evaluation_needed_target"),
            "wanted_target": pattern_registry.id("evaluation_wanted_target"),
            "useful_target": pattern_registry.id("evaluation_useful_target"),
            "safety_target": pattern_registry.id("evaluation_safety_target"),
            "avoidance_target": pattern_registry.id("evaluation_avoidance_target"),
            "harmful_target": pattern_registry.id("evaluation_harmful_target"),
        }
        self.kind_ids = {
            "positive_target": pattern_registry.id("evaluation_positive_target"),
            "mixed_target": pattern_registry.id("evaluation_mixed_target"),
            "avoidance_target": pattern_registry.id("evaluation_avoidance_target"),
        }
        self._last_observations: dict[str, _ObservationMemory] = {}

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        evaluation_field: EvaluationField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        if system_state.mode not in {"active", "recovery"}:
            return []
        candidates = []
        for entry in evaluation_field.top(16):
            roles = _classify_roles(entry)
            if not roles:
                continue
            target_score = _target_score(entry)
            candidates.append((target_score, entry, roles))
        candidates.sort(key=lambda item: item[0], reverse=True)

        operations: list[ContextOperation] = []
        for target_score, entry, roles in candidates:
            if len(operations) >= MAX_TARGETS_PER_TICK:
                break
            if not self._should_emit(tick, entry.pattern_id, roles, target_score):
                continue
            operations.append(self._operation(tick, entry, roles, target_score))
        return operations

    def _should_emit(self, tick: int, pattern_id: str, roles: tuple[str, ...], target_score: float) -> bool:
        key = f"{pattern_id}|{','.join(roles)}"
        previous = self._last_observations.get(key)
        if previous is None:
            self._last_observations[key] = _ObservationMemory(tick, target_score, roles)
            return True
        if roles != previous.roles:
            self._last_observations[key] = _ObservationMemory(tick, target_score, roles)
            return True
        if tick - previous.tick >= TARGET_OBSERVATION_COOLDOWN_TICKS:
            self._last_observations[key] = _ObservationMemory(tick, target_score, roles)
            return True
        if abs(target_score - previous.target_score) >= SIGNIFICANT_DELTA:
            self._last_observations[key] = _ObservationMemory(tick, target_score, roles)
            return True
        return False

    def _operation(
        self,
        tick: int,
        entry: EvaluationEntry,
        role_names: tuple[str, ...],
        target_score: float,
    ) -> ContextOperation:
        target_kind = _target_kind(role_names)
        payload = {
            "target_observation_id": self.id_gen.next("evaluation_target"),
            "observation_kind": self.observation_kind,
            "pattern_id": entry.pattern_id,
            "pattern_name": self.pattern_registry.debug_name(entry.pattern_id),
            "target_roles": [self.role_ids[role_name] for role_name in role_names],
            "target_role_names": list(role_names),
            "evaluation_dimensions": {
                "usefulness": round(entry.usefulness, 3),
                "harmfulness": round(entry.harmfulness, 3),
                "need": round(entry.need, 3),
                "want": round(entry.want, 3),
                "avoid": round(entry.avoid, 3),
                "safety": round(entry.safety, 3),
                "priority": round(entry.priority, 3),
            },
            "target_score": round(target_score, 3),
            "source_evaluation_ids": list(entry.sources),
            "source_scopes": list(entry.scopes),
            "target_kind": target_kind,
            "target_kind_pattern": self.kind_ids[target_kind],
            "memory_modified": False,
            "permanent_memory_modified": False,
            "activation": round(target_score, 3),
            "ttl": 12,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.EVALUATION_TARGET_OBSERVED,
            tick,
            self.module_name,
            None,
            payload,
        )


def _classify_roles(entry: EvaluationEntry) -> tuple[str, ...]:
    roles: list[str] = []
    if entry.need >= NEED_THRESHOLD and entry.priority >= PRIORITY_THRESHOLD:
        roles.append("needed_target")
    if entry.want >= WANT_THRESHOLD and entry.priority >= 0.30:
        roles.append("wanted_target")
    if entry.usefulness >= USEFUL_TARGET_THRESHOLD and entry.harmfulness < 0.30:
        roles.append("useful_target")
    if entry.avoid >= AVOID_THRESHOLD:
        roles.append("avoidance_target")
    if entry.harmfulness >= HARMFUL_TARGET_THRESHOLD:
        roles.append("harmful_target")
    if entry.safety >= 0.60 and entry.need >= 0.40:
        roles.append("safety_target")
    return tuple(roles)


def _target_kind(role_names: tuple[str, ...]) -> str:
    has_positive = any(role in role_names for role in ("needed_target", "wanted_target", "useful_target", "safety_target"))
    has_avoidance = any(role in role_names for role in ("avoidance_target", "harmful_target"))
    if has_positive and has_avoidance:
        return "mixed_target"
    if has_avoidance:
        return "avoidance_target"
    return "positive_target"


def _target_score(entry: EvaluationEntry) -> float:
    return _clamp(
        entry.need * 0.25
        + entry.want * 0.20
        + entry.usefulness * 0.20
        + entry.safety * 0.15
        + entry.avoid * 0.10
        + entry.harmfulness * 0.10
        + entry.priority * 0.25
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
