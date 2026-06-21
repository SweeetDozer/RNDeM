from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REAL_EXPSM = ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"
REAL_AKBSM = ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"

EQUIVALENCE_VERIFIERS = (
    "tools/verify_scenario_fixtures.py",
    "tools/verify_reflection_pressure_scenarios.py",
    "tools/verify_policy_pressure_review_scenarios.py",
)


def main() -> int:
    expsm_before = _hash_file(REAL_EXPSM)
    akbsm_before = _hash_file(REAL_AKBSM)
    checks = {
        "scenario marker expectations pass": _run_verifiers(),
        "real ExpSM unchanged": expsm_before == _hash_file(REAL_EXPSM),
        "real AKBSM unchanged": akbsm_before == _hash_file(REAL_AKBSM),
    }
    passed = all(checks.values())
    print("Run tick phase split equivalence verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _run_verifiers() -> bool:
    for relative_path in EQUIVALENCE_VERIFIERS:
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(result.stdout)
            return False
    return True


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
