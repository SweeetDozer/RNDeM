from clc.akbsm.akbsm_association_field import AKBSMAssociationField
from clc.context.context_memory import ContextMemory


class AKBSMAssociationFieldUpdater:
    module_name = "akbsm_association_field_updater"

    def __init__(self) -> None:
        self.applied_probe_ids: set[str] = set()

    def run(
        self,
        tick: int,
        memory: ContextMemory,
        association_field: AKBSMAssociationField,
    ) -> None:
        for probe in memory.get_recent_akbsm_association_probes(24):
            probe_id = str(probe.get("probe_id", ""))
            if not probe_id or probe_id in self.applied_probe_ids:
                continue
            self.applied_probe_ids.add(probe_id)
            source_pattern_id = str(probe.get("source_pattern_id", ""))
            if not source_pattern_id:
                continue
            activation = float(probe.get("activation", 0.55) or 0.0)
            ttl = int(probe.get("ttl", 10) or 10)
            target_kind = probe.get("target_kind")
            target_roles = [str(role) for role in probe.get("target_role_names", ())]
            for association in probe.get("associated_patterns", ()):
                if not isinstance(association, dict):
                    continue
                associated_pattern_id = association.get("pattern_id")
                if not associated_pattern_id:
                    continue
                association_field.update_association(
                    source_pattern_id,
                    str(associated_pattern_id),
                    relation_type=_optional_str(association.get("relation_type")),
                    score=float(association.get("score", 0.0) or 0.0),
                    distance=int(association.get("distance", 1) or 1),
                    path=_path_list(association.get("path")),
                    source_probe_id=probe_id,
                    target_kind=_optional_str(target_kind),
                    target_roles=target_roles,
                    activation=activation,
                    ttl=ttl,
                    tick=tick,
                )
        association_field.decay(tick)
        if len(self.applied_probe_ids) > 512:
            self.applied_probe_ids = set(list(self.applied_probe_ids)[-256:])


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _path_list(value: object) -> list[str] | None:
    if not isinstance(value, (list, tuple)):
        return None
    return [str(item) for item in value]
