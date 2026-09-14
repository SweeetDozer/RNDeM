from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKLIST_PATH = ROOT / "docs" / "v1_release_checklist.md"
READINESS_PATH = ROOT / "docs" / "v1_readiness_criteria.md"

EXPECTED_EXPSM_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
EXPECTED_AKBSM_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

REQUIRED_DOCUMENTS = (
    "README.md",
    "docs/v1_readiness_criteria.md",
    "docs/v1_release_checklist.md",
    "docs/contextmemory_temporary_metadata_architecture_map.md",
    "docs/contextmemory_temporary_metadata_architecture_diagram.md",
    "docs/current_architecture_checkpoint.md",
    "docs/post_v0_0_2_safety_architecture_checkpoint.md",
    "docs/project_hygiene_audit.md",
    "docs/adr_behavior_influence_modes.md",
    "docs/adr_akbsm_write_policy.md",
    "docs/adr_contextmemory_temporary_metadata_tick_diagnostic_visibility.md",
)

REQUIRED_VERIFIERS = (
    "tools/verify_v1_readiness_criteria.py",
    "tools/verify_v1_release_candidate.py",
    "tools/verify_contextmemory_temporary_metadata_architecture_diagram.py",
    "tools/verify_contextmemory_temporary_metadata_architecture_map.py",
    "tools/verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_tick_diagnostic_visibility_adr.py",
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_diagnostic_wiring_adr.py",
    "tools/verify_contextmemory_temporary_metadata_observation_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_runtime_observation_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_runtime_observation_adr.py",
    "tools/verify_contextmemory_temporary_metadata_negative_retention.py",
    "tools/verify_akbsm_proposal_temporary_metadata_placement_adapter.py",
    "tools/verify_contextmemory_temporary_metadata_placement_scaffold.py",
    "tools/verify_contextmemory_temporary_metadata_placement_api_adr.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_integration_scaffold.py",
    "tools/verify_akbsm_proposal_contextmemory_metadata_scaffold.py",
    "tools/verify_scenario_fixtures.py",
    "tools/verify_memory_mutation_policy.py",
    "tools/verify_debug_name_dependency_audit.py",
    "tools/audit_debug_name_dependencies.py",
)

REQUIRED_SCENARIOS = (
    "scenarios/real_input_repeated_audio_signal.json",
    "scenarios/real_input_retention_with_observation_views.json",
    "scenarios/mode_c_disabled_no_effect.json",
    "scenarios/akbsm_write_disabled_no_effect.json",
    "scenarios/akbsm_draft_proposal_disabled_no_effect.json",
    "scenarios/akbsm_draft_proposal_enabled_probe_creates_temp_metadata.json",
    "scenarios/akbsm_transition_controller_metadata_coverage.json",
    "scenarios/akbsm_proposal_contextmemory_metadata_scaffold.json",
    "scenarios/akbsm_proposal_temporary_metadata_placement_adapter.json",
    "scenarios/contextmemory_temporary_metadata_placement_scaffold.json",
    "scenarios/contextmemory_temporary_metadata_negative_retention_coverage.json",
    "scenarios/contextmemory_temporary_metadata_runtime_observation_negative_no_behavior.json",
    "scenarios/contextmemory_temporary_metadata_diagnostic_wiring_scaffold.json",
    "scenarios/contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.json",
)

CORE_VERIFIERS = (
    "tools/verify_v1_readiness_criteria.py",
    "tools/verify_contextmemory_temporary_metadata_architecture_diagram.py",
    "tools/verify_contextmemory_temporary_metadata_architecture_map.py",
    "tools/verify_contextmemory_temporary_metadata_tick_wrapper_negative_no_behavior.py",
    "tools/verify_contextmemory_temporary_metadata_tick_diagnostic_wrapper_scaffold.py",
    "tools/verify_memory_mutation_policy.py",
    "tools/verify_debug_name_dependency_audit.py",
)


def main() -> int:
    checklist = CHECKLIST_PATH.read_text(encoding="utf-8") if CHECKLIST_PATH.exists() else ""
    readiness = READINESS_PATH.read_text(encoding="utf-8") if READINESS_PATH.exists() else ""
    combined = f"{readiness}\n{checklist}"
    core_safety = _core_safety_passes()
    results = {
        "docs/v1_readiness_criteria.md exists": READINESS_PATH.exists(),
        "docs/v1_release_checklist.md exists": CHECKLIST_PATH.exists(),
        "architecture map exists": (ROOT / "docs/contextmemory_temporary_metadata_architecture_map.md").exists(),
        "architecture diagram exists": (ROOT / "docs/contextmemory_temporary_metadata_architecture_diagram.md").exists(),
        "current architecture checkpoint exists": (ROOT / "docs/current_architecture_checkpoint.md").exists(),
        "post-v0.0.2 safety checkpoint exists": (
            ROOT / "docs/post_v0_0_2_safety_architecture_checkpoint.md"
        ).exists(),
        "project hygiene audit exists": (ROOT / "docs/project_hygiene_audit.md").exists(),
        "required documents exist": _paths_exist(REQUIRED_DOCUMENTS),
        "required verifier files exist": _paths_exist(REQUIRED_VERIFIERS),
        "required scenario fixtures exist": _paths_exist(REQUIRED_SCENARIOS),
        "release meaning/exclusions documented": _has_all(
            checklist,
            (
                "v1.0.0 means a stable safety-bounded RNDeM CLC prototype checkpoint",
                "v1.0.0 is a stop-and-review point",
                "v1.0.0 is not AGI",
                "v1.0.0 is not autonomous self-modification",
                "v1.0.0 is not permission for AKBSM writes",
                "v1.0.0 is not permission for real ContextMemory placement",
                "v1.0.0 is not permission for behavior/scoring/guard influence",
            ),
        ),
        "final tag procedure documented but not executed": _has_all(
            checklist,
            (
                "`v1.0.0` may only be tagged after",
                'git tag -a v1.0.0 -m "Stable safety-bounded RNDeM CLC prototype checkpoint"',
                "Do not run this command in this pass",
            ),
        )
        and not _tag_exists("v1.0.0"),
        "stop-and-review procedure documented": _has_all(
            checklist,
            (
                "After v1.0.0 is tagged",
                "stop feature work",
                "review the full architecture map and diagram",
                "decide next roadmap only after discussion",
            ),
        ),
        "release blocker list documented": _has_all(
            checklist,
            (
                "dirty working tree",
                "failed verifier",
                "Memory/AKBSM hash mismatch",
                "marker 36 present",
                "debug-name high-risk findings > 0",
                "real ContextMemory reads/writes present",
                "behavior/scoring/guard influence present",
            ),
        ),
        "final checklist documented": _has_all(
            checklist,
            (
                "- [ ] main is up to date with origin/main",
                "- [ ] release-candidate verifier passes",
                "- [ ] Memory/ExpSM hash matches expected",
                "- [ ] v1.0.0 tag points at reviewed main",
            ),
        ),
        "v1 does not claim AGI": "not AGI" in combined and "is AGI" not in combined,
        "v1 does not authorize autonomous self-modification": "not autonomous self-modification" in combined,
        "v1 does not authorize _run_tick hook": _has_all(
            combined,
            (
                "does not authorize _run_tick wiring",
                "not permission for direct _run_tick diagnostic hook",
                "Direct `_run_tick` diagnostic hook remains deferred",
            ),
        ),
        "v1 does not authorize default runtime diagnostics": "not permission for default runtime diagnostics"
        in combined,
        "v1 does not authorize real ContextMemory placement": _has_all(
            combined,
            (
                "does not authorize real ContextMemory reads/writes",
                "not permission for real ContextMemory placement",
            ),
        ),
        "v1 does not authorize proposal storage/queues": _has_all(
            combined,
            (
                "does not authorize proposal storage",
                "not permission for permanent proposal storage",
                "not permission for proposal queues",
            ),
        ),
        "v1 does not authorize AKBSM/ExpSM writes": "does not authorize AKBSM/ExpSM writes" in combined,
        "v1 does not authorize behavior/scoring/guard influence": "does not authorize behavior/scoring/guard influence"
        in combined,
        "direct _run_tick hook remains deferred": "Direct `_run_tick` diagnostic hook remains deferred"
        in checklist,
        "external tick wrapper remains outside _run_tick": "External tick diagnostic wrapper remains outside `_run_tick`"
        in checklist,
        "no ContextMemoryManager call/import from temporary metadata diagnostic ladder": core_safety,
        "no semantic_core.json": not (ROOT / "semantic_core.json").exists(),
        "no technical_feedback_patterns.json": not (ROOT / "technical_feedback_patterns.json").exists(),
        "marker 36 absent": core_safety,
        "debug-name high-risk findings remain 0": _debug_name_high_risk_zero(core_safety),
        "Memory/ExpSM hash matches expected": _sha256(ROOT / "Memory/ExpSM/ExpSM_data.json")
        == EXPECTED_EXPSM_HASH,
        "Memory/AKBSM hash matches expected": _sha256(ROOT / "Memory/AKBSM/AKBSM_ne.json")
        == EXPECTED_AKBSM_HASH,
        "existing safety still passes": core_safety,
    }
    passed = all(results.values())
    print("v1.0.0 release-candidate verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _has_all(text: str, needles: tuple[str, ...]) -> bool:
    return all(needle in text for needle in needles)


def _paths_exist(paths: tuple[str, ...]) -> bool:
    return all((ROOT / path).exists() for path in paths)


def _sha256(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tag_exists(name: str) -> bool:
    result = subprocess.run(
        ["git", "tag", "-l", name],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _core_safety_passes() -> bool:
    if os.environ.get("RNDEM_VERIFIER_SHALLOW") == "1":
        return True
    env = dict(os.environ)
    env["RNDEM_VERIFIER_SHALLOW"] = "1"
    for relative_path in CORE_VERIFIERS:
        result = subprocess.run(
            [sys.executable, "-B", relative_path],
            cwd=ROOT,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            return False
    return True


def _debug_name_high_risk_zero(core_safety: bool) -> bool:
    if not core_safety:
        return False
    audit_path = ROOT / "docs/debug_name_dependency_audit.md"
    text = audit_path.read_text(encoding="utf-8") if audit_path.exists() else ""
    return "high-risk findings: 0" in text.lower()


if __name__ == "__main__":
    raise SystemExit(main())
