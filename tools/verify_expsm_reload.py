import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_MEMORY = PROJECT_ROOT / "Memory"
REAL_EXPSM = REAL_MEMORY / "ExpSM" / "ExpSM_data.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.core.markers import OperationMarker  # noqa: E402
from clc.core.operations import ContextOperation  # noqa: E402
from clc.runtime.clc_runtime import CLCRuntime  # noqa: E402


def main() -> int:
    before_hash = _sha256(REAL_EXPSM)
    result = {
        "temp memory": "no",
        "write applied": "no",
        "reload called": "no",
        "adapter saw updated value": "no",
        "real ExpSM_data.json unchanged": "no",
        "result": "FAIL",
    }

    with tempfile.TemporaryDirectory(prefix="rndem_expsm_reload_check_") as temp_dir:
        temp_memory = Path(temp_dir) / "Memory"
        if REAL_MEMORY.exists():
            shutil.copytree(REAL_MEMORY, temp_memory)
        else:
            _write_minimal_expsm(temp_memory / "ExpSM" / "ExpSM_data.json")
        result["temp memory"] = "yes"

        runtime = CLCRuntime(temp_memory)
        target_id = _first_active_experience_id(temp_memory / "ExpSM" / "ExpSM_data.json")
        if target_id is None:
            _print_result(result)
            return 1

        token = "reload_verified_token"
        _write_metadata_token(temp_memory / "ExpSM" / "ExpSM_data.json", target_id, token)
        result["write applied"] = "yes"

        before_reload_count = runtime.expsm.reload_count
        tick = 999
        runtime.memory.add_event(
            ContextOperation(
                op_id="op_verify_expsm_reload",
                marker=OperationMarker.MEMORY_UPDATED,
                tick=tick,
                source_module="verify_expsm_reload",
                target=None,
                payload={
                    "memory_update_id": "verify_expsm_reload",
                    "target": "ExpSM",
                    "experience_id": target_id,
                    "permanent_memory_modified": True,
                },
            )
        )
        runtime._reload_expsm_if_modified(tick)

        if runtime.expsm.reload_count > before_reload_count and runtime.expsm.last_reload_tick == tick:
            result["reload called"] = "yes"

        metadata = runtime.expsm.experiences.get(target_id, {}).get("metadata", {})
        if isinstance(metadata, dict) and metadata.get("reload_verification_token") == token:
            result["adapter saw updated value"] = "yes"

    after_hash = _sha256(REAL_EXPSM)
    if before_hash == after_hash:
        result["real ExpSM_data.json unchanged"] = "yes"

    passed = all(value == "yes" for key, value in result.items() if key != "result")
    result["result"] = "PASS" if passed else "FAIL"
    _print_result(result)
    return 0 if passed else 1


def _first_active_experience_id(path: Path) -> str | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    experiences = data.get("experience", {})
    for record_id, record in experiences.items():
        if not isinstance(record, dict):
            continue
        if str(record.get("status", "")).lower() in {"archived", "deleted", "tombstone"}:
            continue
        return str(record_id)
    return None


def _write_metadata_token(path: Path, record_id: str, token: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    updated = copy.deepcopy(data)
    record = updated["experience"][record_id]
    metadata = record.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        record["metadata"] = metadata
    metadata["reload_verification_token"] = token
    path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")


def _write_minimal_expsm(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"experience": {}, "reflexes": {}}, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _print_result(result: dict[str, str]) -> None:
    print("ExpSM reload verification:")
    for key in (
        "temp memory",
        "write applied",
        "reload called",
        "adapter saw updated value",
        "real ExpSM_data.json unchanged",
        "result",
    ):
        print(f"  {key}: {result[key]}")


if __name__ == "__main__":
    raise SystemExit(main())
