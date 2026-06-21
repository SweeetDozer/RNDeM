from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_REPORT = PROJECT_ROOT / "docs" / "debug_name_dependency_audit.json"
MARKDOWN_REPORT = PROJECT_ROOT / "docs" / "debug_name_dependency_audit.md"

CLASSIFICATIONS = {
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

RISKS = {"low", "medium", "high", "unknown"}

SEARCH_TERMS = (
    "debug_name(",
    ".startswith(",
    ".endswith(",
    ".split(",
    " in debug_name",
    "debug_name in ",
    "action_",
    "memory_",
    "consolidation_",
    "evaluation_",
    "decision_",
    "value_",
    "expsm_",
    "akbsm_",
    "target_",
    "outcome_",
)

SEMANTIC_PREFIX_RE = re.compile(
    r"""["'](?:action|memory|consolidation|evaluation|decision|value|expsm|akbsm|target|outcome)_[A-Za-z0-9_]+["']"""
)


@dataclass(frozen=True)
class DebugNameDependencyFinding:
    path: str
    line: int
    kind: str
    snippet: str
    classification: str
    risk: str
    recommendation: str
    semantic_decision: bool = False
    stable_runtime_label: bool = False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit debug-name-based semantic dependencies.")
    parser.add_argument("--fail-on-high-risk", action="store_true", help="Exit 2 when high-risk findings are detected.")
    args = parser.parse_args(argv)

    findings = collect_findings()
    write_json_report(findings)
    write_markdown_report(findings)
    print_report(findings)
    if args.fail_on_high_risk and any(item.risk == "high" for item in findings):
        return 2
    return 0


def collect_findings() -> list[DebugNameDependencyFinding]:
    findings: list[DebugNameDependencyFinding] = []
    for path in _python_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative == "clc/core/pattern_registry.py":
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_number, line in enumerate(lines, start=1):
            kind = _line_kind(line)
            if kind is None:
                continue
            classification = classify_finding(relative, line_number, line)
            risk = risk_for(classification)
            findings.append(
                DebugNameDependencyFinding(
                    path=relative,
                    line=line_number,
                    kind=kind,
                    snippet=_compact(line),
                    classification=classification,
                    risk=risk,
                    recommendation=recommendation_for(classification),
                    semantic_decision=classification in {"legacy_semantic_decision", "semantic_decision_needs_migration"},
                    stable_runtime_label=classification in {"runtime_source_label", "stable_constant_or_enum"},
                )
            )
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind))


def classify_finding(path: str, line_number: int, line: str) -> str:
    snippet = line.strip()
    lowered_path = path.lower()
    if _is_pattern_manifest_tooling(path):
        return "pattern_manifest_tooling"
    if path.startswith("tools/"):
        return "test_or_verifier_only"
    if _is_runtime_source_label(path, snippet):
        return "runtime_source_label"
    if _is_debug_output(path, line_number, snippet):
        return "debug_output_only"
    if _is_debug_or_report_label(snippet):
        return "debug_or_report_label"
    if _is_pattern_id_construction(snippet):
        return "pattern_id_construction"
    if _is_stable_constant_or_enum(snippet):
        return "stable_constant_or_enum"
    if "learnability_filter.py" in lowered_path:
        return "learning_filter"
    if "action_proposer.py" in lowered_path:
        return "candidate_construction"
    if "decision_selector.py" in lowered_path or "action_scoring.py" in lowered_path:
        return "scoring_or_selection"
    if any(name in lowered_path for name in ("draft_commit_gate.py", "expsm_commit_writer.py", "memory_mutation_policy.py")):
        return "memory_write_policy"
    if any(name in lowered_path for name in ("draft_context_relevance_scorer.py", "draft_input_context_enricher.py")):
        return "semantic_filter"
    if any(name in lowered_path for name in ("expsm_mechanism_search.py", "evaluation_signal_module.py", "evaluation_target_observer.py")):
        return "candidate_construction"
    if any(name in lowered_path for name in ("value_feedback_", "target_satisfaction_", "akbsm_association_", "field_updater.py")):
        return "semantic_filter"
    if "mode_action_guard.py" in lowered_path:
        return "scoring_or_selection"
    if _is_runtime_semantic_decision(path, snippet):
        return "semantic_decision_needs_migration"
    if _is_legacy_semantic_decision(snippet):
        return "legacy_semantic_decision"
    return "ambiguous_runtime_logic"


def risk_for(classification: str) -> str:
    if classification in {
        "debug_output_only",
        "test_or_verifier_only",
        "runtime_source_label",
        "stable_constant_or_enum",
        "debug_or_report_label",
        "pattern_manifest_tooling",
    }:
        return "low"
    if classification in {"semantic_filter", "pattern_id_construction", "legacy_semantic_decision"}:
        return "medium"
    if classification in {
        "candidate_construction",
        "learning_filter",
        "scoring_or_selection",
        "memory_write_policy",
        "semantic_decision_needs_migration",
    }:
        return "high"
    return "unknown"


def recommendation_for(classification: str) -> str:
    if classification == "debug_output_only":
        return "keep debug_name for display/logging only"
    if classification == "test_or_verifier_only":
        return "keep as verifier fixture data unless it starts asserting runtime semantics by display name"
    if classification == "semantic_filter":
        return "replace semantic string filters with PatternRegistry semantic tags/classes"
    if classification == "candidate_construction":
        return "migrate candidate construction checks to explicit semantic classes such as is_action/is_target"
    if classification == "learning_filter":
        return "replace learnability name sets with explicit is_learnable and semantic class metadata"
    if classification == "scoring_or_selection":
        return "replace selection/scoring name checks with semantic tags before renaming pattern labels"
    if classification == "memory_write_policy":
        return "move memory write allow/reject logic to semantic tags and policy APIs"
    if classification == "runtime_source_label":
        return "keep stable runtime provenance labels separate from PatternRegistry debug names"
    if classification == "stable_constant_or_enum":
        return "keep as stable control value unless it starts depending on display/debug pattern names"
    if classification == "debug_or_report_label":
        return "keep for report/debug payloads; do not use as semantic control input"
    if classification == "pattern_id_construction":
        return "review when changing pattern ids, but do not treat as a debug-name semantic decision"
    if classification == "pattern_manifest_tooling":
        return "keep in manifest/audit tooling; ensure runtime decisions use PatternRegistry metadata"
    if classification == "legacy_semantic_decision":
        return "plan semantic metadata migration or document why this stable string is intentional"
    if classification == "semantic_decision_needs_migration":
        return "migrate this runtime semantic decision to explicit PatternRegistry metadata or typed source helpers"
    if classification == "ambiguous_runtime_logic":
        return "inspect manually and classify before changing debug names"
    return "inspect manually and classify before changing debug names"


def unknown_runtime_logic_split(findings: list[DebugNameDependencyFinding]) -> dict[str, object]:
    new_categories = {
        "runtime_source_label",
        "stable_constant_or_enum",
        "debug_or_report_label",
        "pattern_id_construction",
        "pattern_manifest_tooling",
        "legacy_semantic_decision",
        "semantic_decision_needs_migration",
        "ambiguous_runtime_logic",
    }
    by_classification = Counter(item.classification for item in findings)
    return {
        "previous_unknown_runtime_logic_baseline": 190,
        "current_unknown_runtime_logic": by_classification.get("unknown_runtime_logic", 0),
        "ambiguous_runtime_logic": by_classification.get("ambiguous_runtime_logic", 0),
        "new_category_counts": {
            key: by_classification.get(key, 0)
            for key in sorted(new_categories)
            if by_classification.get(key, 0) > 0
        },
    }


def write_json_report(findings: list[DebugNameDependencyFinding]) -> None:
    JSON_REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "title": "Debug-name dependency audit",
        "total_findings": len(findings),
        "by_classification": dict(sorted(Counter(item.classification for item in findings).items())),
        "by_risk": dict(sorted(Counter(item.risk for item in findings).items())),
        "unknown_runtime_logic_split": unknown_runtime_logic_split(findings),
        "migrated_sites": migrated_sites(),
        "findings": [asdict(item) for item in findings],
    }
    JSON_REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown_report(findings: list[DebugNameDependencyFinding]) -> None:
    MARKDOWN_REPORT.parent.mkdir(parents=True, exist_ok=True)
    by_classification = Counter(item.classification for item in findings)
    by_risk = Counter(item.risk for item in findings)
    split = unknown_runtime_logic_split(findings)
    high_semantic = [
        item
        for item in findings
        if item.classification == "semantic_decision_needs_migration" or item.risk == "high"
    ]
    ambiguous = [item for item in findings if item.classification == "ambiguous_runtime_logic"]
    lines = [
        "# Debug-name dependency audit",
        "",
        "Debug-name-based semantic logic is risky because renaming or localizing display labels can silently change runtime behavior. This report maps those dependencies before replacing them.",
        "",
        "## Summary counts",
        "",
        f"Total findings: {len(findings)}",
        "",
        "## Migrated sites",
        "",
        *_migrated_site_lines(),
        "",
        "Migrated areas: ActionProposer action-pattern detection; LearnabilityFilter semantic filtering; memory-write technical filters; draft relevance/enrichment semantic filters; scoring/selection source-label checks.",
        "",
        "Stable candidate source labels are tracked separately from PatternRegistry debug names; they describe runtime provenance, not pattern semantics.",
        "",
        "Classification meanings are documented in `docs/debug_name_audit_classifications.md`.",
        "",
        _remaining_high_risk_summary(findings),
        "",
        "By classification:",
        *[f"- {key}: {by_classification.get(key, 0)}" for key in sorted(CLASSIFICATIONS)],
        "",
        "By risk:",
        *[f"- {key}: {by_risk.get(key, 0)}" for key in sorted(RISKS)],
        "",
        "## Unknown runtime logic split",
        "",
        f"Previous `unknown_runtime_logic` baseline: {split['previous_unknown_runtime_logic_baseline']}",
        f"Current `unknown_runtime_logic`: {split['current_unknown_runtime_logic']}",
        f"Current `ambiguous_runtime_logic`: {split['ambiguous_runtime_logic']}",
        "",
        "New split counts:",
        *[
            f"- {key}: {value}"
            for key, value in sorted(split["new_category_counts"].items())
            if isinstance(split.get("new_category_counts"), dict)
        ],
        "",
        "Stable string categories:",
        f"- runtime_source_label: {by_classification.get('runtime_source_label', 0)}",
        f"- stable_constant_or_enum: {by_classification.get('stable_constant_or_enum', 0)}",
        f"- debug_or_report_label: {by_classification.get('debug_or_report_label', 0)}",
        f"- pattern_manifest_tooling: {by_classification.get('pattern_manifest_tooling', 0)}",
        "",
        "## Legacy semantic decision migration",
        "",
        "Previous focused baseline:",
        "- legacy_semantic_decision: 38",
        "- semantic_decision_needs_migration: 0",
        "- candidate_construction high-risk: 57",
        "- total high-risk findings: 76",
        "",
        "Current focused counts:",
        f"- legacy_semantic_decision: {by_classification.get('legacy_semantic_decision', 0)}",
        f"- semantic_decision_needs_migration: {by_classification.get('semantic_decision_needs_migration', 0)}",
        f"- candidate_construction high-risk: {_risk_classification_count(findings, 'candidate_construction', 'high')}",
        f"- total high-risk findings: {by_risk.get('high', 0)}",
        "",
        "This pass intentionally leaves `runtime_source_label` and `pattern_id_construction` findings out of the migration target set.",
        "",
        "Ambiguous findings needing human review:",
        "",
        *_finding_lines(ambiguous, limit=30),
        "",
        "High-risk semantic decisions still needing migration:",
        "",
        *_finding_lines(high_semantic, limit=30),
        "",
        "## High-risk findings",
        "",
        *_finding_lines([item for item in findings if item.risk == "high"], limit=80),
        "",
        "## Medium-risk findings",
        "",
        *_finding_lines([item for item in findings if item.risk == "medium"], limit=80),
        "",
        "## Low-risk/debug-only findings",
        "",
        *_finding_lines([item for item in findings if item.risk == "low"], limit=80),
        "",
        "## Recommended migration path",
        "",
        "Phase 1: audit current dependencies.",
        "",
        "Phase 2: introduce semantic_class/tags in PatternRegistry manifest.",
        "",
        "Phase 3: add PatternRegistry APIs: has_tag(pattern_id, tag), semantic_class(pattern_id), is_action(pattern_id), is_memory(pattern_id), is_audit(pattern_id), is_learnable(pattern_id).",
        "",
        "Phase 4: migrate high-risk filters first.",
        "",
        "Phase 5: keep debug_name only for display/logging.",
        "",
    ]
    MARKDOWN_REPORT.write_text("\n".join(lines), encoding="utf-8")


def print_report(findings: list[DebugNameDependencyFinding]) -> None:
    by_classification = Counter(item.classification for item in findings)
    high_risk = [item for item in findings if item.risk == "high"]
    split = unknown_runtime_logic_split(findings)
    print("Debug-name dependency audit")
    print()
    print(f"Total findings: {len(findings)}")
    print()
    print("By classification:")
    for key in sorted(CLASSIFICATIONS):
        print(f"  {key}: {by_classification.get(key, 0)}")
    print()
    print("Unknown runtime logic split:")
    print(f"  previous unknown_runtime_logic baseline: {split['previous_unknown_runtime_logic_baseline']}")
    print(f"  current unknown_runtime_logic: {split['current_unknown_runtime_logic']}")
    print(f"  current ambiguous_runtime_logic: {split['ambiguous_runtime_logic']}")
    print("Legacy semantic decision migration:")
    print(f"  legacy_semantic_decision: {by_classification.get('legacy_semantic_decision', 0)}")
    print(f"  semantic_decision_needs_migration: {by_classification.get('semantic_decision_needs_migration', 0)}")
    print(f"  candidate_construction high-risk: {_risk_classification_count(findings, 'candidate_construction', 'high')}")
    print(f"  total high-risk findings: {Counter(item.risk for item in findings).get('high', 0)}")
    print()
    print("High risk findings:")
    for item in high_risk[:30]:
        print(f"  {item.path}:{item.line}")
        print(f"    classification={item.classification}")
        print(f"    risk={item.risk}")
        print(f"    snippet={item.snippet}")
        print(f"    recommendation={item.recommendation}")
    if len(high_risk) > 30:
        print(f"  ... {len(high_risk) - 30} more high-risk findings in {JSON_REPORT.relative_to(PROJECT_ROOT)}")
    print()
    print("Migrated sites:")
    for site in migrated_sites():
        print(f"  {site['path']}:{site['line']} {site['status']} - {site['description']}")
    print()
    print(f"JSON report: {JSON_REPORT.relative_to(PROJECT_ROOT)}")
    print(f"Markdown report: {MARKDOWN_REPORT.relative_to(PROJECT_ROOT)}")


def migrated_sites() -> list[dict[str, object]]:
    sites: list[dict[str, object]] = []
    action_path = PROJECT_ROOT / "clc" / "action" / "action_proposer.py"
    for index, line in enumerate(action_path.read_text(encoding="utf-8").splitlines(), start=1):
        if "self.pattern_registry.is_action(pattern_id)" in line:
            sites.append(
                {
                    "path": "clc/action/action_proposer.py",
                    "line": index,
                    "status": "migrated",
                    "description": "ActionProposer action-pattern detection uses PatternRegistry.is_action instead of debug_name prefix matching.",
                }
            )
            break
    learnability_path = PROJECT_ROOT / "clc" / "experience" / "learnability_filter.py"
    for index, line in enumerate(learnability_path.read_text(encoding="utf-8").splitlines(), start=1):
        if "pattern_registry.is_non_learnable" in line or "self.pattern_registry.is_non_learnable" in line:
            sites.append(
                {
                    "path": "clc/experience/learnability_filter.py",
                    "line": index,
                    "status": "migrated",
                    "description": "LearnabilityFilter semantic decisions use PatternRegistry semantic metadata instead of explicit debug-name sets.",
                }
            )
            break
    memory_write_filter_path = PROJECT_ROOT / "clc" / "consolidation" / "memory_write_filters.py"
    for index, line in enumerate(memory_write_filter_path.read_text(encoding="utf-8").splitlines(), start=1):
        if "def is_memory_write_technical_pattern" in line:
            sites.append(
                {
                    "path": "clc/consolidation/memory_write_filters.py",
                    "line": index,
                    "status": "migrated",
                    "description": "Memory-write technical filters use PatternRegistry semantic metadata instead of debug-name prefix matching.",
                }
            )
            break
    draft_filter_path = PROJECT_ROOT / "clc" / "consolidation" / "draft_semantic_filters.py"
    for index, line in enumerate(draft_filter_path.read_text(encoding="utf-8").splitlines(), start=1):
        if "def is_draft_technical_noise" in line:
            sites.append(
                {
                    "path": "clc/consolidation/draft_semantic_filters.py",
                    "line": index,
                    "status": "migrated",
                    "description": "Draft relevance/enrichment semantic filters use PatternRegistry metadata instead of debug-name prefix matching.",
                }
            )
            break
    source_path = PROJECT_ROOT / "clc" / "action" / "candidate_sources.py"
    for index, line in enumerate(source_path.read_text(encoding="utf-8").splitlines(), start=1):
        if "def is_expsm_activation_source" in line:
            sites.append(
                {
                    "path": "clc/action/candidate_sources.py",
                    "line": index,
                    "status": "migrated",
                    "description": "Scoring/selection source checks use stable candidate source helpers instead of inline semantic-looking strings.",
                }
            )
            break
    return sites


def _python_files() -> list[Path]:
    files = list((PROJECT_ROOT / "clc").rglob("*.py")) + list((PROJECT_ROOT / "tools").glob("*.py"))
    main_py = PROJECT_ROOT / "main.py"
    if main_py.exists():
        files.append(main_py)
    return sorted(files)


def _line_kind(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "learnability_" in line and "pattern_registry.id(" in line:
        return None
    kinds: list[str] = []
    if "debug_name(" in line:
        kinds.append("debug_name_call")
    if ".startswith(" in line and ("debug_name" in line or SEMANTIC_PREFIX_RE.search(line)):
        kinds.append("startswith_semantic_name")
    if ".endswith(" in line and ("debug_name" in line or SEMANTIC_PREFIX_RE.search(line)):
        kinds.append("endswith_semantic_name")
    if ".split(" in line and "debug_name" in line:
        kinds.append("split_debug_name")
    if " in debug_name" in line or "debug_name in " in line:
        kinds.append("debug_name_membership")
    if _has_direct_semantic_literal(line):
        kinds.append("direct_semantic_name_literal")
    return "+".join(dict.fromkeys(kinds)) if kinds else None


def _is_pattern_manifest_tooling(path: str) -> bool:
    return path in {
        "tools/audit_debug_name_dependencies.py",
        "tools/enrich_pattern_semantics.py",
    }


def _is_runtime_source_label(path: str, snippet: str) -> bool:
    if path == "clc/action/candidate_sources.py":
        return True
    source_labels = {"expsm_activation", "expsm_mechanism_search"}
    return any(label in snippet for label in source_labels) and any(
        token in snippet
        for token in (
            'source"',
            "source'",
            "source ==",
            "source !=",
            "SOURCE_EXPSM",
            "is_expsm_",
            "_selected_source_type",
        )
    )


def _is_debug_or_report_label(snippet: str) -> bool:
    report_tokens = (
        "debug_name(",
        "action_debug_name",
        "pattern_name",
        "target_pattern_name",
        "source_type",
        "print(",
    )
    if any(token in snippet for token in report_tokens):
        return True
    return False


def _is_pattern_id_construction(snippet: str) -> bool:
    if "pattern_registry.id(" in snippet or "registry.id(" in snippet:
        return True
    pattern_tokens = (
        "decision_pattern_id",
        "action_pattern_id",
        "source_action_pattern_id",
        "blocked_action_pattern_id",
        "review_decision_pattern_id",
        "action_pattern",
        "target_pattern_id",
        "effect_pattern_id",
        "outcome_pattern_id",
        "feedback_kind",
        "then_patterns",
        "action_patterns",
        "decision_patterns",
        "source_pattern_id",
        "source_pattern_ids",
    )
    comparison_tokens = (" == ", " != ", " in ", " not in ")
    return any(token in snippet for token in pattern_tokens) and any(token in snippet for token in comparison_tokens)


def _is_stable_constant_or_enum(snippet: str) -> bool:
    stable_tokens = (
        "_id",
        "_status",
        "_reason",
        "_decision",
        "_scope",
        "_mode",
        "mode",
        "_kind",
        "_type",
        "_unchanged",
        "module",
        "flag",
        "flags",
        "snapshot",
        "_snapshot",
        "target_kind",
        "target_role",
        "guard_status",
        "review_decision",
        "outcome_status",
        "value_influence",
        "value_scope",
        "event",
        "trend_label",
        "pressure_type",
        "candidate_type",
        "direction",
        "value_adjusted_score",
    )
    comparison_tokens = (" == ", " != ", " in ", " not in ", ".startswith(", ".endswith(")
    return any(token in snippet for token in stable_tokens) and any(token in snippet for token in comparison_tokens)


def _is_runtime_semantic_decision(path: str, snippet: str) -> bool:
    if "debug_name(" not in snippet:
        return False
    if _is_debug_or_report_label(snippet):
        return False
    risky_paths = (
        "clc/expsm/expsm_mechanism_search.py",
        "clc/evaluation/",
        "clc/consolidation/",
        "clc/action/",
        "clc/system/",
    )
    return any(path.startswith(prefix) for prefix in risky_paths)


def _is_legacy_semantic_decision(snippet: str) -> bool:
    semantic_control_tokens = (".startswith(", ".endswith(", " in ", " not in ", " == ", " != ")
    return bool(SEMANTIC_PREFIX_RE.search(snippet)) and any(token in snippet for token in semantic_control_tokens)


def _has_direct_semantic_literal(line: str) -> bool:
    if not SEMANTIC_PREFIX_RE.search(line):
        return False
    semantic_context_tokens = (
        "pattern_registry.id(",
        "registry.id(",
        "debug_name",
        ".startswith(",
        ".endswith(",
        " == ",
        " != ",
        " in ",
        " not in ",
        "SOURCE_EXPSM",
    )
    return any(token in line for token in semantic_context_tokens)


def _is_debug_output(path: str, line_number: int, snippet: str) -> bool:
    if "print(" in snippet or "debug_print" in snippet:
        return True
    if path == "clc/runtime/clc_runtime.py" and line_number >= 600:
        return True
    if path == "clc/context/context_memory.py" and line_number >= 600:
        return True
    if "debug_name" in snippet and any(token in snippet for token in ("pattern_name", "action_pattern_name", "target_pattern_name")):
        return True
    return False


def _finding_lines(findings: list[DebugNameDependencyFinding], *, limit: int) -> list[str]:
    if not findings:
        return ["No findings."]
    lines: list[str] = []
    for item in findings[:limit]:
        lines.append(f"- `{item.path}:{item.line}` {item.classification}/{item.risk}: `{item.snippet}`")
        lines.append(f"  Recommendation: {item.recommendation}")
    if len(findings) > limit:
        lines.append(f"- ... {len(findings) - limit} more findings in `{JSON_REPORT.relative_to(PROJECT_ROOT)}`.")
    return lines


def _risk_classification_count(findings: list[DebugNameDependencyFinding], classification: str, risk: str) -> int:
    return sum(1 for item in findings if item.classification == classification and item.risk == risk)


def _remaining_high_risk_summary(findings: list[DebugNameDependencyFinding]) -> str:
    high_risk = [item for item in findings if item.risk == "high"]
    if not high_risk:
        return "Remaining high-risk areas: none in the current audit."
    by_classification = Counter(item.classification for item in high_risk)
    details = ", ".join(f"{key}: {value}" for key, value in sorted(by_classification.items()))
    return f"Remaining high-risk areas: {details}."


def _migrated_site_lines() -> list[str]:
    sites = migrated_sites()
    if not sites:
        return ["No migrated sites detected."]
    return [
        f"- `{site['path']}:{site['line']}` {site['status']}: {site['description']}"
        for site in sites
    ]


def _compact(line: str, limit: int = 180) -> str:
    snippet = " ".join(line.strip().split())
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 3] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
