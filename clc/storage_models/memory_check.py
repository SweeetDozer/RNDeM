from pathlib import Path

from clc.context.context_memory import ContextMemory
from clc.context.window import ContextWindow
from clc.core.ids import IdGenerator
from clc.core.nfp import NFPFrame
from clc.core.pattern_registry import PatternRegistry
from clc.storage_models.akbsm_adapter import AKBSMAdapter
from clc.storage_models.expsm_adapter import ExpSMAdapter
from clc.storage_models.pattern_store import PatternStore


def run_memory_check(memory_root: Path | str = Path("Memory")) -> dict[str, int | float]:
    memory_path = Path(memory_root)
    registry = PatternRegistry()
    store = PatternStore(memory_path / "AKBSM" / "DB", registry)
    akbsm = AKBSMAdapter(memory_path / "AKBSM" / "AKBSM_ne.json")
    expsm = ExpSMAdapter(memory_path / "ExpSM" / "ExpSM_data.json", store, registry)
    memory = ContextMemory(IdGenerator(), registry)
    frame = NFPFrame(
        frame_id="check_frame_001",
        tick=1,
        origin="external",
        source="aud",
        activations={registry.id("aud_freq_440"): 0.8},
    )
    memory.add_frame(frame)
    window = ContextWindow("check_win_001", 1, 1, (frame.frame_id,))
    similarity = 0.0
    if store.list_patterns():
        similarity = store.similarity_to_window(store.list_patterns()[0], window, memory)
    return {
        "patterns": len(store.list_patterns()),
        "edges": len(akbsm.list_edges()),
        "experiences": len(expsm.list_experiences()),
        "reflexes": len(expsm.list_reflexes()),
        "sample_similarity": similarity,
    }
