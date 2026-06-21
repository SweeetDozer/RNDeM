from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


BEHAVIOR_MODULES = (
    "clc/action/action_proposer.py",
    "clc/action/action_scoring.py",
    "clc/action/decision_selector.py",
    "clc/system/mode_action_guard.py",
    "clc/consolidation/memory_draft_writer.py",
    "clc/consolidation/draft_commit_gate.py",
    "clc/consolidation/expsm_commit_writer.py",
    "clc/consolidation/expsm_update_writer.py",
    "clc/evaluation/value_feedback_update_writer.py",
    "clc/field/field_updater.py",
    "clc/neuromodulation/neuromodulation_module.py",
)

FORBIDDEN_MODULES = {
    "clc.evaluation.policy_pressure",
    "clc.evaluation.policy_pressure_review",
    "clc.evaluation.reflection_review",
    "clc.evaluation.need_more_evidence_signal",
}

FORBIDDEN_NAMES = {
    "PolicyPressure",
    "PolicyPressureBuilder",
    "PolicyPressureReview",
    "PolicyPressureReviewBuilder",
    "ReflectionReview",
    "ReflectionReviewBuilder",
    "NeedMoreEvidenceSignal",
    "NeedMoreEvidenceSignalBuilder",
    "policy_pressure",
    "policy_pressure_builder",
    "policy_pressure_review",
    "policy_pressure_review_builder",
    "reflection_review",
    "reflection_review_builder",
    "need_more_evidence_signal",
    "need_more_evidence_signal_builder",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    detail: str


def main() -> int:
    findings: list[Finding] = []
    missing: list[str] = []

    for relative_path in BEHAVIOR_MODULES:
        path = ROOT / relative_path
        if not path.exists():
            missing.append(relative_path)
            continue
        findings.extend(_scan_file(path, relative_path))

    passed = not findings and not missing
    print("PolicyPressure influence boundary verification:")
    print(f"  behavior modules scanned: {len(BEHAVIOR_MODULES) - len(missing)}")
    if missing:
        print("  missing behavior modules:")
        for relative_path in missing:
            print(f"    {relative_path}")
    if findings:
        print("  forbidden references:")
        for finding in findings:
            print(f"    {finding.path}:{finding.line}: {finding.kind}: {finding.detail}")
    else:
        print("  forbidden references: none")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _scan_file(path: Path, relative_path: str) -> list[Finding]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
    except SyntaxError as exc:
        return [Finding(relative_path, exc.lineno or 0, "syntax", exc.msg)]

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            findings.extend(_scan_import(relative_path, node))
        elif isinstance(node, ast.ImportFrom):
            findings.extend(_scan_import_from(relative_path, node))
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                findings.append(Finding(relative_path, node.lineno, "name", node.id))
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_NAMES:
                findings.append(Finding(relative_path, node.lineno, "attribute", node.attr))
    return findings


def _scan_import(relative_path: str, node: ast.Import) -> list[Finding]:
    findings: list[Finding] = []
    for alias in node.names:
        if alias.name in FORBIDDEN_MODULES:
            findings.append(Finding(relative_path, node.lineno, "import", alias.name))
    return findings


def _scan_import_from(relative_path: str, node: ast.ImportFrom) -> list[Finding]:
    module = _absolute_import_module(node)
    findings: list[Finding] = []
    if module in FORBIDDEN_MODULES:
        findings.append(Finding(relative_path, node.lineno, "import-from", module))
    for alias in node.names:
        if alias.name in FORBIDDEN_NAMES:
            findings.append(Finding(relative_path, node.lineno, "import-name", alias.name))
    return findings


def _absolute_import_module(node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    if not node.module:
        return ""
    return "." * node.level + node.module


if __name__ == "__main__":
    raise SystemExit(main())
