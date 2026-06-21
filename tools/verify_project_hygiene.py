from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "project_hygiene_audit.md"
GITIGNORE_PATH = ROOT / ".gitignore"

CORE_DOCS = (
    "docs/current_architecture_checkpoint.md",
    "docs/phase_regression_snapshots.md",
    "docs/runtime_tick_phase_map.md",
    "docs/project_hygiene_audit.md",
)

CORE_SAFETY_VERIFIERS = (
    "tools/verify_phase_regression_snapshots.py",
    "tools/verify_phase_level_invariants.py",
    "tools/verify_run_tick_phase_split_boundaries.py",
    "tools/verify_legacy_semantic_decision_migration.py",
)


def main() -> int:
    cache_dirs = list(ROOT.rglob("__pycache__"))
    pyc_files = list(ROOT.rglob("*.pyc"))
    checks = {
        "hygiene audit doc exists": DOC_PATH.exists(),
        "cache ignore policy exists": _cache_ignore_policy_ok(),
        "no cache artifacts": not cache_dirs and not pyc_files,
        "core project docs exist": _core_docs_exist(),
        "core safety verifiers pass": _run_core_safety_verifiers(),
    }
    passed = all(checks.values())
    print("Project hygiene verification:")
    for label, ok in checks.items():
        print(f"  {label}: {'yes' if ok else 'no'}")
    print(f"  __pycache__ count: {len(cache_dirs)}")
    print(f"  .pyc count: {len(pyc_files)}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _cache_ignore_policy_ok() -> bool:
    if not GITIGNORE_PATH.exists():
        print("  warning: .gitignore missing")
        return True
    text = GITIGNORE_PATH.read_text(encoding="utf-8")
    has_pycache = "__pycache__/" in text
    has_pyc = "*.pyc" in text or "*.py[cod]" in text
    return has_pycache and has_pyc


def _core_docs_exist() -> bool:
    return all((ROOT / path).exists() for path in CORE_DOCS)


def _run_core_safety_verifiers() -> bool:
    for relative_path in CORE_SAFETY_VERIFIERS:
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


if __name__ == "__main__":
    raise SystemExit(main())
