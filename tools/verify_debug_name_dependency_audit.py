from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = PROJECT_ROOT / "tools" / "audit_debug_name_dependencies.py"
JSON_REPORT = PROJECT_ROOT / "docs" / "debug_name_dependency_audit.json"
MARKDOWN_REPORT = PROJECT_ROOT / "docs" / "debug_name_dependency_audit.md"

ALLOWED_CLASSIFICATIONS = {
    "debug_output_only",
    "test_or_verifier_only",
    "semantic_filter",
    "candidate_construction",
    "learning_filter",
    "scoring_or_selection",
    "memory_write_policy",
    "unknown_runtime_logic",
    "runtime_source_label",
    "stable_constant_or_enum",
    "debug_or_report_label",
    "pattern_id_construction",
    "pattern_manifest_tooling",
    "legacy_semantic_decision",
    "semantic_decision_needs_migration",
    "ambiguous_runtime_logic",
}
ALLOWED_RISKS = {"low", "medium", "high", "unknown"}


def main() -> int:
    completed = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    checks: dict[str, bool] = {
        "audit_runs": completed.returncode == 0,
        "json_written": JSON_REPORT.exists(),
        "markdown_written": MARKDOWN_REPORT.exists(),
    }

    payload: dict[str, object] = {}
    findings: list[dict[str, object]] = []
    if JSON_REPORT.exists():
        try:
            payload = json.loads(JSON_REPORT.read_text(encoding="utf-8"))
            raw_findings = payload.get("findings", [])
            findings = raw_findings if isinstance(raw_findings, list) else []
        except json.JSONDecodeError:
            payload = {}
            findings = []

    checks["schema_has_total"] = isinstance(payload.get("total_findings"), int)
    checks["findings_list"] = isinstance(findings, list)
    checks["finding_count_matches"] = payload.get("total_findings") == len(findings)
    checks["migrated_sites_list"] = isinstance(payload.get("migrated_sites", []), list)
    checks["unknown_split_present"] = isinstance(payload.get("unknown_runtime_logic_split", {}), dict)
    checks["classifications_allowed"] = all(
        isinstance(item, dict) and item.get("classification") in ALLOWED_CLASSIFICATIONS for item in findings
    )
    checks["risks_allowed"] = all(isinstance(item, dict) and item.get("risk") in ALLOWED_RISKS for item in findings)
    checks["required_fields_present"] = all(_has_required_fields(item) for item in findings)
    high_risk = [item for item in findings if isinstance(item, dict) and item.get("risk") == "high"]
    checks["high_risk_included_if_detected"] = all(item.get("classification") in ALLOWED_CLASSIFICATIONS for item in high_risk)

    if MARKDOWN_REPORT.exists():
        markdown = MARKDOWN_REPORT.read_text(encoding="utf-8")
        checks["markdown_has_summary"] = "## Summary counts" in markdown and "## High-risk findings" in markdown
    else:
        checks["markdown_has_summary"] = False

    print("Debug-name dependency audit verifier:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  total findings: {len(findings)}")
    print(f"  high-risk findings: {len(high_risk)}")
    if completed.returncode != 0:
        print("Audit stdout:")
        print(completed.stdout)
        print("Audit stderr:")
        print(completed.stderr)

    passed = all(checks.values())
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _has_required_fields(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    required = {"path", "line", "kind", "snippet", "classification", "risk", "recommendation"}
    return required <= set(item)


if __name__ == "__main__":
    raise SystemExit(main())
