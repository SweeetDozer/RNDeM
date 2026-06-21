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
    payload = _read_json()
    findings = payload.get("findings", []) if isinstance(payload.get("findings"), list) else []
    by_classification = payload.get("by_classification", {})
    split = payload.get("unknown_runtime_logic_split", {})

    checks = {
        "audit runs": completed.returncode == 0,
        "json report written": JSON_REPORT.exists(),
        "markdown report written": MARKDOWN_REPORT.exists(),
        "allowed classifications": _allowed_classifications(findings),
        "allowed risks": _allowed_risks(findings),
        "unknown split present": isinstance(split, dict),
        "unknown bucket reduced": _count(by_classification, "unknown_runtime_logic") < 190,
        "ambiguous bucket bounded": _count(by_classification, "ambiguous_runtime_logic") < 190,
        "source labels classified stable": _source_labels_classified_stable(findings),
        "semantic decisions not low risk": _semantic_decisions_not_low_risk(findings),
        "markdown documents split": _markdown_documents_split(),
        "safety verifiers pass": _safety_verifiers_pass(),
    }
    passed = all(checks.values())
    print("Unknown runtime logic split verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    print(f"  previous unknown baseline: 190")
    print(f"  current unknown_runtime_logic: {_count(by_classification, 'unknown_runtime_logic')}")
    print(f"  current ambiguous_runtime_logic: {_count(by_classification, 'ambiguous_runtime_logic')}")
    print(f"  runtime_source_label: {_count(by_classification, 'runtime_source_label')}")
    print(f"  semantic_decision_needs_migration: {_count(by_classification, 'semantic_decision_needs_migration')}")
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


def _allowed_classifications(findings: list[object]) -> bool:
    return all(isinstance(item, dict) and item.get("classification") in ALLOWED_CLASSIFICATIONS for item in findings)


def _allowed_risks(findings: list[object]) -> bool:
    return all(isinstance(item, dict) and item.get("risk") in ALLOWED_RISKS for item in findings)


def _source_labels_classified_stable(findings: list[object]) -> bool:
    candidates = [
        item
        for item in findings
        if isinstance(item, dict)
        and item.get("path") == "clc/action/candidate_sources.py"
        and ("expsm_activation" in str(item.get("snippet")) or "expsm_mechanism_search" in str(item.get("snippet")))
    ]
    return bool(candidates) and all(
        item.get("classification") in {"runtime_source_label", "stable_constant_or_enum"}
        and item.get("risk") in {"low", "medium"}
        for item in candidates
    )


def _semantic_decisions_not_low_risk(findings: list[object]) -> bool:
    semantic_findings = [
        item
        for item in findings
        if isinstance(item, dict)
        and item.get("classification") in {"legacy_semantic_decision", "semantic_decision_needs_migration"}
    ]
    return all(item.get("risk") in {"medium", "high"} for item in semantic_findings)


def _markdown_documents_split() -> bool:
    if not MARKDOWN_REPORT.exists():
        return False
    text = MARKDOWN_REPORT.read_text(encoding="utf-8")
    return "## Unknown runtime logic split" in text and "Stable string categories" in text


def _safety_verifiers_pass() -> bool:
    for relative_path in (
        "tools/verify_scoring_selection_semantics.py",
        "tools/verify_run_tick_phase_split_boundaries.py",
        "tools/verify_policy_pressure_influence_boundary.py",
    ):
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(result.stdout)
            return False
    return True


def _count(by_classification: object, key: str) -> int:
    if not isinstance(by_classification, dict):
        return 0
    value = by_classification.get(key, 0)
    return int(value) if isinstance(value, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
