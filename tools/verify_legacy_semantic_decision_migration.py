from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = PROJECT_ROOT / "tools" / "audit_debug_name_dependencies.py"
JSON_REPORT = PROJECT_ROOT / "docs" / "debug_name_dependency_audit.json"
MARKDOWN_REPORT = PROJECT_ROOT / "docs" / "debug_name_dependency_audit.md"

BASELINE_LEGACY_SEMANTIC_DECISION = 38
BASELINE_SEMANTIC_DECISION_NEEDS_MIGRATION = 0
BASELINE_CANDIDATE_CONSTRUCTION_HIGH = 57
BASELINE_TOTAL_HIGH_RISK = 76

CHANGED_FILES = {
    "tools/audit_debug_name_dependencies.py",
}


def main() -> int:
    completed = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = _read_json()
    findings = payload.get("findings", []) if isinstance(payload.get("findings"), list) else []
    by_classification = payload.get("by_classification", {}) if isinstance(payload.get("by_classification"), dict) else {}
    by_risk = payload.get("by_risk", {}) if isinstance(payload.get("by_risk"), dict) else {}

    legacy_count = _count(by_classification, "legacy_semantic_decision")
    semantic_needs_count = _count(by_classification, "semantic_decision_needs_migration")
    candidate_high = _classification_risk_count(findings, "candidate_construction", "high")
    total_high = _count(by_risk, "high")

    checks = {
        "audit runs": completed.returncode == 0,
        "json report written": JSON_REPORT.exists(),
        "markdown report written": MARKDOWN_REPORT.exists(),
        "legacy semantic decisions resolved": legacy_count == 0,
        "semantic decision needs migration not increased": semantic_needs_count <= BASELINE_SEMANTIC_DECISION_NEEDS_MIGRATION,
        "candidate construction high-risk reduced": candidate_high < BASELINE_CANDIDATE_CONSTRUCTION_HIGH,
        "total high-risk reduced": total_high < BASELINE_TOTAL_HIGH_RISK,
        "allowed categories not failures": _allowed_categories_not_failures(findings),
        "changed files no semantic debug-name findings": _changed_files_clean(findings),
        "relevant behavior verifiers pass": _behavior_verifiers_pass(),
        "markdown documents migration": _markdown_documents_migration(),
    }
    passed = all(checks.values())
    print("Legacy semantic decision migration verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  legacy_semantic_decision: {legacy_count} (baseline {BASELINE_LEGACY_SEMANTIC_DECISION})")
    print(f"  semantic_decision_needs_migration: {semantic_needs_count} (baseline {BASELINE_SEMANTIC_DECISION_NEEDS_MIGRATION})")
    print(f"  candidate_construction high-risk: {candidate_high} (baseline {BASELINE_CANDIDATE_CONSTRUCTION_HIGH})")
    print(f"  total high-risk: {total_high} (baseline {BASELINE_TOTAL_HIGH_RISK})")
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr)
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _read_json() -> dict[str, object]:
    if not JSON_REPORT.exists():
        return {}
    try:
        payload = json.loads(JSON_REPORT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _allowed_categories_not_failures(findings: list[object]) -> bool:
    for item in findings:
        if not isinstance(item, dict):
            return False
        if item.get("classification") in {"runtime_source_label", "pattern_id_construction"}:
            if item.get("risk") == "high":
                return False
    return True


def _changed_files_clean(findings: list[object]) -> bool:
    for item in findings:
        if not isinstance(item, dict) or item.get("path") not in CHANGED_FILES:
            continue
        if item.get("classification") in {"legacy_semantic_decision", "semantic_decision_needs_migration"}:
            return False
    return True


def _behavior_verifiers_pass() -> bool:
    for relative_path in (
        "tools/verify_scenario_fixtures.py",
        "tools/verify_scoring_selection_semantics.py",
        "tools/verify_draft_semantic_filters.py",
        "tools/verify_memory_write_filter_semantics.py",
        "tools/verify_learnability_filter_semantics.py",
    ):
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if result.returncode != 0:
            return False
    return True


def _markdown_documents_migration() -> bool:
    if not MARKDOWN_REPORT.exists():
        return False
    text = MARKDOWN_REPORT.read_text(encoding="utf-8")
    return "## Legacy semantic decision migration" in text and "candidate_construction high-risk" in text


def _classification_risk_count(findings: list[object], classification: str, risk: str) -> int:
    return sum(
        1
        for item in findings
        if isinstance(item, dict) and item.get("classification") == classification and item.get("risk") == risk
    )


def _count(counter: object, key: str) -> int:
    if not isinstance(counter, dict):
        return 0
    value = counter.get(key, 0)
    return int(value) if isinstance(value, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
