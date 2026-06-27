from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class RuntimeProfile(str, Enum):
    SAFE_DEMO = "safe_demo"
    DRAFT_ONLY = "draft_only"
    MUTATING_MEMORY = "mutating_memory"


@dataclass(frozen=True)
class MemoryMutationPolicy:
    profile: RuntimeProfile
    allow_draft_writes: bool
    allow_expsm_commit: bool
    allow_expsm_update: bool
    allow_value_feedback_update: bool
    allow_akbsm_write: bool
    mode_c_memory_gate_advisory_enabled: bool = False
    real_memory_root: str | None = None
    memory_is_temporary: bool = False

    def summary(self) -> dict[str, object]:
        return {
            "profile": self.profile.value,
            "memory_is_temporary": self.memory_is_temporary,
            "real_memory_root": self.real_memory_root,
            "allow_draft_writes": self.allow_draft_writes,
            "allow_expsm_commit": self.allow_expsm_commit,
            "allow_expsm_update": self.allow_expsm_update,
            "allow_value_feedback_update": self.allow_value_feedback_update,
            "allow_akbsm_write": self.allow_akbsm_write,
            "mode_c_memory_gate_advisory_enabled": self.mode_c_memory_gate_advisory_enabled,
        }


def policy_for_profile(
    profile: RuntimeProfile | str,
    *,
    memory_root: str | Path | None = None,
    memory_is_temporary: bool = False,
) -> MemoryMutationPolicy:
    profile = RuntimeProfile(profile)
    real_memory_root = str(memory_root) if memory_root is not None and not memory_is_temporary else None
    if profile == RuntimeProfile.SAFE_DEMO:
        return MemoryMutationPolicy(
            profile=profile,
            allow_draft_writes=bool(memory_is_temporary),
            allow_expsm_commit=False,
            allow_expsm_update=False,
            allow_value_feedback_update=False,
            allow_akbsm_write=False,
            real_memory_root=real_memory_root,
            memory_is_temporary=memory_is_temporary,
        )
    if profile == RuntimeProfile.DRAFT_ONLY:
        return MemoryMutationPolicy(
            profile=profile,
            allow_draft_writes=True,
            allow_expsm_commit=False,
            allow_expsm_update=False,
            allow_value_feedback_update=False,
            allow_akbsm_write=False,
            real_memory_root=real_memory_root,
            memory_is_temporary=memory_is_temporary,
        )
    return MemoryMutationPolicy(
        profile=profile,
        allow_draft_writes=True,
        allow_expsm_commit=True,
        allow_expsm_update=True,
        allow_value_feedback_update=True,
        allow_akbsm_write=False,
        real_memory_root=real_memory_root,
        memory_is_temporary=memory_is_temporary,
    )
