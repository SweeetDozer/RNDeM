from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clc.context.context_memory import ContextMemory
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry
from clc.evaluation.evaluation_field import EvaluationField
from clc.field.active_context_field import ActiveContextField
from clc.storage_models.akbsm_adapter import AKBSMAdapter
from clc.system.system_state import SystemState


MAX_PROBES_PER_TICK = 3
MAX_RESULTS_PER_PROBE = 8
MAX_DEPTH = 2
PROBE_COOLDOWN_TICKS = 4
SIGNIFICANT_TARGET_DELTA = 0.10


@dataclass
class _ProbeMemory:
    tick: int
    target_score: float


class AKBSMAssociationProbe:
    """Read-only association probe around observed evaluation targets."""

    module_name = "akbsm_association_probe"

    def __init__(
        self,
        id_gen: IdGenerator,
        pattern_registry: PatternRegistry,
        akbsm_path: str | Path,
    ) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry
        root = Path(akbsm_path)
        edge_path = root / "AKBSM_ne.json" if root.is_dir() or root.suffix == "" else root
        self.akbsm = AKBSMAdapter(edge_path)
        self.probe_kind = pattern_registry.id("akbsm_association_probe")
        self._last_probes: dict[str, _ProbeMemory] = {}

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        active_field: ActiveContextField,
        evaluation_field: EvaluationField,
        system_state: SystemState,
    ) -> list[ContextOperation]:
        del active_field, evaluation_field
        if system_state.mode not in {"active", "recovery"}:
            return []
        operations: list[ContextOperation] = []
        targets = [
            target
            for target in memory.get_recent_evaluation_targets(12)
            if target.get("_event_tick") == tick
        ]
        targets.sort(key=lambda item: float(item.get("target_score", 0.0) or 0.0), reverse=True)
        for target in targets:
            if len(operations) >= MAX_PROBES_PER_TICK:
                break
            if not self._should_probe(tick, target):
                continue
            operations.append(self._operation(tick, target))
        return operations

    def _should_probe(self, tick: int, target: dict[str, Any]) -> bool:
        pattern_id = str(target.get("pattern_id", ""))
        if not pattern_id:
            return False
        role_key = ",".join(str(role) for role in target.get("target_role_names", ()))
        key = f"{pattern_id}|{target.get('target_kind')}|{role_key}"
        target_score = _as_float(target.get("target_score", 0.0))
        previous = self._last_probes.get(key)
        if previous is None:
            self._last_probes[key] = _ProbeMemory(tick, target_score)
            return True
        if tick - previous.tick >= PROBE_COOLDOWN_TICKS:
            self._last_probes[key] = _ProbeMemory(tick, target_score)
            return True
        if abs(target_score - previous.target_score) >= SIGNIFICANT_TARGET_DELTA:
            self._last_probes[key] = _ProbeMemory(tick, target_score)
            return True
        return False

    def _operation(self, tick: int, target: dict[str, Any]) -> ContextOperation:
        source_pattern_id = str(target.get("pattern_id", ""))
        associations = self.akbsm.find_associations(
            source_pattern_id,
            max_depth=MAX_DEPTH,
            limit=MAX_RESULTS_PER_PROBE,
        )
        associated_patterns = [
            {
                "pattern_id": item["pattern_id"],
                "pattern_name": self.pattern_registry.debug_name(str(item["pattern_id"])),
                "distance": item["distance"],
                "relation_type": item["relation_type"],
                "score": item["score"],
                "path": item["path"],
            }
            for item in associations
        ]
        raw_links: list[dict[str, Any]] = []
        seen_links: set[tuple[str, str, str]] = set()
        for item in associations:
            for link in item.get("raw_links", ()):
                key = (str(link.get("from")), str(link.get("to")), str(link.get("relation_type")))
                if key in seen_links:
                    continue
                seen_links.add(key)
                raw_links.append(dict(link))

        associations_found = len(associated_patterns)
        activation = max(0.35, min(0.75, _as_float(target.get("target_score", 0.55)) or 0.55))
        if associations_found:
            activation = max(activation, max(_as_float(item.get("score", 0.0)) for item in associated_patterns) * 0.65)
        payload = {
            "probe_id": self.id_gen.next("akbsm_probe"),
            "probe_kind": self.probe_kind,
            "source_target_observation_id": target.get("target_observation_id"),
            "source_pattern_id": source_pattern_id,
            "source_pattern_name": self.pattern_registry.debug_name(source_pattern_id),
            "target_kind": target.get("target_kind"),
            "target_role_names": list(target.get("target_role_names", ())),
            "target_score": target.get("target_score", 0.0),
            "query": {
                "max_depth": MAX_DEPTH,
                "limit": MAX_RESULTS_PER_PROBE,
                "relation_types": None,
            },
            "associations_found": associations_found,
            "associated_patterns": associated_patterns,
            "raw_links": raw_links,
            "memory_modified": False,
            "permanent_memory_modified": False,
            "akbsm_modified": False,
            "activation": round(activation, 3),
            "ttl": 10,
        }
        return ContextOperation(
            self.id_gen.next("op"),
            OperationMarker.AKBSM_ASSOCIATION_PROBE,
            tick,
            self.module_name,
            None,
            payload,
        )


def _as_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
