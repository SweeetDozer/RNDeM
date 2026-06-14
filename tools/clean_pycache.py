from pathlib import Path
import shutil


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    pycache_dirs = sorted(PROJECT_ROOT.rglob("__pycache__"), key=lambda path: len(path.parts), reverse=True)
    pyc_files = sorted(PROJECT_ROOT.rglob("*.pyc"))

    removed_dirs = 0
    for path in pycache_dirs:
        if path.is_dir():
            shutil.rmtree(path)
            removed_dirs += 1

    removed_pyc = 0
    for path in pyc_files:
        if path.exists():
            path.unlink()
            removed_pyc += 1

    print(f"Removed __pycache__ directories: {removed_dirs}")
    print(f"Removed .pyc files: {removed_pyc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
