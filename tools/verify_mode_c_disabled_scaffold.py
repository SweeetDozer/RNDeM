from __future__ import annotations

import ast
import hashlib
import inspect
import subprocess
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clc.runtime.memory_mutation_policy import RuntimeProfile, policy_for_profile
from clc.runtime.mode_c_advisory import MemoryGateAdvisory, ModeCMemoryGateAdvisoryProvider


EXP_HASH = "6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e"
AKB_HASH = "0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd"

SCAFFOLD_PATHS = (
    ROOT / "clc" / "runtime" / "mode_c_advisory.py",
    ROOT / "clc" / "runtime" / "memory_mutation_policy.py",
)

FORBIDDEN_BEHAVIOR_REFERENCES = (
    "DecisionSelector",
    "ActionScoring",
    "ActionProposer",
    "ModeActionGuard",
)

FORBIDDEN_PAYLOAD_METHODS = (
    "write",
    "commit",
    "approve",
    "reject",
    "run",
)


def main() -> int:
    before = _real_hashes()
    results = {
        "default_policy_disabled": _case_default_policy_disabled(),
        "safe_demo_no_effect": _case_safe_demo_no_effect(),
        "no_memory_write_effect": before["expsm"] == EXP_HASH and before["akbsm"] == AKB_HASH,
        "influence_boundary_passes": _run_verifier("tools/verify_policy_pressure_influence_boundary.py"),
        "marker_36_absent": _case_marker_36_absent(),
        "payload_metadata_only": _case_payload_metadata_only(),
        "provider_noop_by_default": _case_provider_noop_by_default(),
        "no_scoring_selection_references": _case_no_scoring_selection_references(),
    }
    after = _real_hashes()
    results["real_expsm_hash_unchanged"] = before["expsm"] == after["expsm"] == EXP_HASH
    results["real_akbsm_hash_unchanged"] = before["akbsm"] == after["akbsm"] == AKB_HASH
    passed = all(results.values())

    print("Mode C disabled scaffold verification:")
    for key, ok in results.items():
        print(f"  {key}: {'yes' if ok else 'no'}")
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _case_default_policy_disabled() -> bool:
    policies = (
        policy_for_profile(RuntimeProfile.SAFE_DEMO),
        policy_for_profile(RuntimeProfile.DRAFT_ONLY),
        policy_for_profile(RuntimeProfile.MUTATING_MEMORY),
    )
    return all(policy.mode_c_memory_gate_advisory_enabled is False for policy in policies)


def _case_safe_demo_no_effect() -> bool:
    policy = policy_for_profile(RuntimeProfile.SAFE_DEMO)
    provider = ModeCMemoryGateAdvisoryProvider(policy)
    return provider.from_policy_pressure_review(object()) == ()


def _case_marker_36_absent() -> bool:
    forbidden_marker_name = "MARKER" + "_36"
    for path in (ROOT / "clc").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "marker 36" in text.lower() or forbidden_marker_name in text or "= 36" in text:
            return False
    return True


def _case_payload_metadata_only() -> bool:
    field_map = {field.name: field for field in fields(MemoryGateAdvisory)}
    apply_now_field = field_map.get("apply_now")
    forbidden_methods = [
        name
        for name, member in inspect.getmembers(MemoryGateAdvisory)
        if callable(member) and any(term in name.lower() for term in FORBIDDEN_PAYLOAD_METHODS)
    ]
    return (
        is_dataclass(MemoryGateAdvisory)
        and getattr(MemoryGateAdvisory, "__dataclass_params__").frozen is True
        and apply_now_field is not None
        and apply_now_field.default is False
        and not forbidden_methods
    )


def _case_provider_noop_by_default() -> bool:
    policy = policy_for_profile(RuntimeProfile.DRAFT_ONLY)
    provider = ModeCMemoryGateAdvisoryProvider(policy)
    return provider.from_policy_pressure_review(_FakePolicyPressureReview()) == ()


def _case_no_scoring_selection_references() -> bool:
    findings: list[str] = []
    for path in SCAFFOLD_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_BEHAVIOR_REFERENCES:
                findings.append(node.id)
            elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_BEHAVIOR_REFERENCES:
                findings.append(node.attr)
    return not findings


def _run_verifier(relative_path: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-B", relative_path],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        return False
    return True


def _real_hashes() -> dict[str, str]:
    return {
        "expsm": _hash_file(ROOT / "Memory" / "ExpSM" / "ExpSM_data.json"),
        "akbsm": _hash_file(ROOT / "Memory" / "AKBSM" / "AKBSM_ne.json"),
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _FakePolicyPressureReview:
    tick = 3
    pressure_type = "evidence_pressure"
    severity = "medium"
    confidence = 1.0
    recommended_future_operation = "collect_more_evidence"
    primary_issue = "repeated_uncertain_selection"


if __name__ == "__main__":
    raise SystemExit(main())
