# Debug-name dependency audit

Debug-name-based semantic logic is risky because renaming or localizing display labels can silently change runtime behavior. This report maps those dependencies before replacing them.

## Summary counts

Total findings: 736

## Migrated sites

- `clc/action/action_proposer.py:397` migrated: ActionProposer action-pattern detection uses PatternRegistry.is_action instead of debug_name prefix matching.
- `clc/experience/learnability_filter.py:76` migrated: LearnabilityFilter semantic decisions use PatternRegistry semantic metadata instead of explicit debug-name sets.
- `clc/consolidation/memory_write_filters.py:26` migrated: Memory-write technical filters use PatternRegistry semantic metadata instead of debug-name prefix matching.
- `clc/consolidation/draft_semantic_filters.py:36` migrated: Draft relevance/enrichment semantic filters use PatternRegistry metadata instead of debug-name prefix matching.
- `clc/action/candidate_sources.py:19` migrated: Scoring/selection source checks use stable candidate source helpers instead of inline semantic-looking strings.

Migrated areas: ActionProposer action-pattern detection; LearnabilityFilter semantic filtering; memory-write technical filters; draft relevance/enrichment semantic filters; scoring/selection source-label checks.

Stable candidate source labels are tracked separately from PatternRegistry debug names; they describe runtime provenance, not pattern semantics.

Classification meanings are documented in `docs/debug_name_audit_classifications.md`.

Remaining high-risk areas: none in the current audit.

By classification:
- ambiguous_runtime_logic: 1
- candidate_construction: 0
- debug_or_report_label: 9
- debug_output_only: 50
- learning_filter: 0
- legacy_semantic_decision: 0
- memory_write_policy: 0
- pattern_id_construction: 450
- pattern_manifest_tooling: 14
- runtime_source_label: 15
- scoring_or_selection: 0
- semantic_decision_needs_migration: 0
- semantic_filter: 3
- stable_constant_or_enum: 60
- test_or_verifier_only: 134
- unknown_runtime_logic: 0

By risk:
- high: 0
- low: 282
- medium: 453
- unknown: 1

## Unknown runtime logic split

Previous `unknown_runtime_logic` baseline: 190
Current `unknown_runtime_logic`: 0
Current `ambiguous_runtime_logic`: 1

New split counts:
- ambiguous_runtime_logic: 1
- debug_or_report_label: 9
- pattern_id_construction: 450
- pattern_manifest_tooling: 14
- runtime_source_label: 15
- stable_constant_or_enum: 60

Stable string categories:
- runtime_source_label: 15
- stable_constant_or_enum: 60
- debug_or_report_label: 9
- pattern_manifest_tooling: 14

## Legacy semantic decision migration

Previous focused baseline:
- legacy_semantic_decision: 38
- semantic_decision_needs_migration: 0
- candidate_construction high-risk: 57
- total high-risk findings: 76

Current focused counts:
- legacy_semantic_decision: 0
- semantic_decision_needs_migration: 0
- candidate_construction high-risk: 0
- total high-risk findings: 0

This pass intentionally leaves `runtime_source_label` and `pattern_id_construction` findings out of the migration target set.

Ambiguous findings needing human review:

- `clc/runtime/clc_runtime.py:311` ambiguous_runtime_logic/unknown: `parts = debug_name.split("_")`
  Recommendation: inspect manually and classify before changing debug names

High-risk semantic decisions still needing migration:

No findings.

## High-risk findings

No findings.

## Medium-risk findings

- `clc/action/action_guard_audit_observer.py:24` pattern_id_construction/medium: `self.audit_kind = pattern_registry.id("action_guard_audit_observed")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:26` pattern_id_construction/medium: `"no_blocked_candidates": pattern_registry.id("action_guard_audit_no_blocked_candidates"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:27` pattern_id_construction/medium: `"blocked_low_score_only": pattern_registry.id("action_guard_audit_blocked_low_score_only"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:28` pattern_id_construction/medium: `"blocked_high_score_candidate": pattern_registry.id("action_guard_audit_blocked_high_score_candidate"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:29` pattern_id_construction/medium: `"selected_was_only_allowed_candidate": pattern_registry.id("action_guard_audit_selected_only_allowed"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:32` pattern_id_construction/medium: `"allowed": pattern_registry.id("action_guard_audit_allowed_candidate"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:33` pattern_id_construction/medium: `"blocked": pattern_registry.id("action_guard_audit_blocked_candidate"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:36` pattern_id_construction/medium: `"none": pattern_registry.id("action_guard_audit_severity_none"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:37` pattern_id_construction/medium: `"low": pattern_registry.id("action_guard_audit_severity_low"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:38` pattern_id_construction/medium: `"medium": pattern_registry.id("action_guard_audit_severity_medium"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:39` pattern_id_construction/medium: `"high": pattern_registry.id("action_guard_audit_severity_high"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_guard_audit_observer.py:164` pattern_id_construction/medium: `if item.get("action_pattern_id") == selected_action and item.get("guard_status") == "allowed"`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:28` pattern_id_construction/medium: `self.consolidation_pending_memory_write = pattern_registry.id("consolidation_pending_memory_write")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:29` pattern_id_construction/medium: `self.consolidation_negative_candidate = pattern_registry.id("consolidation_negative_candidate")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:30` pattern_id_construction/medium: `self.consolidation_pressure_medium = pattern_registry.id("consolidation_pressure_medium")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:31` pattern_id_construction/medium: `self.consolidation_pressure_high = pattern_registry.id("consolidation_pressure_high")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:32` pattern_id_construction/medium: `self.memory_review_approved = pattern_registry.id("memory_review_approved_for_expsm")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:33` pattern_id_construction/medium: `self.memory_review_needs_more_support = pattern_registry.id("memory_review_needs_more_support")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:34` pattern_id_construction/medium: `self.memory_review_rejected_incomplete = pattern_registry.id("memory_review_rejected_incomplete_core")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:35` pattern_id_construction/medium: `self.memory_review_rejected_unstable = pattern_registry.id("memory_review_rejected_unstable")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:38` pattern_id_construction/medium: `self.expsm_update_approved = pattern_registry.id("expsm_update_approved_for_update")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:40` pattern_id_construction/medium: `"wait_more_data": pattern_registry.id("action_wait_more_data"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:41` pattern_id_construction/medium: `"increase_attention": pattern_registry.id("action_increase_attention"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:42` pattern_id_construction/medium: `"inspect_pattern": pattern_registry.id("action_inspect_pattern"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:43` pattern_id_construction/medium: `"store_memory_candidate": pattern_registry.id("action_store_memory_candidate"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:44` pattern_id_construction/medium: `"commit_memory_draft": pattern_registry.id("action_commit_memory_draft"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:45` pattern_id_construction/medium: `"review_committed_memory_update": pattern_registry.id("action_review_committed_memory_update"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:46` pattern_id_construction/medium: `"update_committed_expsm_record": pattern_registry.id("action_update_committed_expsm_record"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:47` pattern_id_construction/medium: `"reduce_load": pattern_registry.id("action_reduce_load"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:48` pattern_id_construction/medium: `"preserve_integrity": pattern_registry.id("action_preserve_integrity"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:49` pattern_id_construction/medium: `"continue_observation": pattern_registry.id("action_continue_observation"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:50` pattern_id_construction/medium: `"generate_more_thought": pattern_registry.id("action_generate_more_thought"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:51` pattern_id_construction/medium: `"enter_consolidation_mode": pattern_registry.id("action_enter_consolidation_mode"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/action_proposer.py:52` pattern_id_construction/medium: `"exit_consolidation_mode": pattern_registry.id("action_exit_consolidation_mode"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:23` pattern_id_construction/medium: `self.audit_kind = pattern_registry.id("decision_audit_observed")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:25` pattern_id_construction/medium: `"clear_win": pattern_registry.id("decision_audit_clear_win"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:26` pattern_id_construction/medium: `"narrow_win": pattern_registry.id("decision_audit_narrow_win"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:27` pattern_id_construction/medium: `"tie_like": pattern_registry.id("decision_audit_tie_like"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:28` pattern_id_construction/medium: `"single_candidate": pattern_registry.id("decision_audit_single_candidate"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:31` pattern_id_construction/medium: `"promoted": pattern_registry.id("decision_audit_value_promoted"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:32` pattern_id_construction/medium: `"demoted": pattern_registry.id("decision_audit_value_demoted"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:33` pattern_id_construction/medium: `"unchanged": pattern_registry.id("decision_audit_value_unchanged"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:36` pattern_id_construction/medium: `"positive_bonus": pattern_registry.id("decision_audit_value_positive_bonus"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:37` pattern_id_construction/medium: `"negative_penalty": pattern_registry.id("decision_audit_value_negative_penalty"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:38` pattern_id_construction/medium: `"none_or_tiny": pattern_registry.id("decision_audit_value_none_or_tiny"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:41` pattern_id_construction/medium: `"target_specific": pattern_registry.id("decision_audit_target_specific_value"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:42` pattern_id_construction/medium: `"generic_fallback": pattern_registry.id("decision_audit_generic_value"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_audit_observer.py:43` pattern_id_construction/medium: `"no_value": pattern_registry.id("decision_audit_no_value"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:23` pattern_id_construction/medium: `self.summary_kind = pattern_registry.id("decision_cycle_summary")`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:25` pattern_id_construction/medium: `"clean_selection": pattern_registry.id("decision_cycle_clean_selection"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:26` pattern_id_construction/medium: `"value_influenced_selection": pattern_registry.id("decision_cycle_value_influenced_selection"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:27` pattern_id_construction/medium: `"guard_constrained_selection": pattern_registry.id("decision_cycle_guard_constrained_selection"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:28` pattern_id_construction/medium: `"uncertain_selection": pattern_registry.id("decision_cycle_uncertain_selection"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:29` pattern_id_construction/medium: `"risky_or_constrained_selection": pattern_registry.id("decision_cycle_risky_or_constrained_selection"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:32` pattern_id_construction/medium: `"high": pattern_registry.id("decision_cycle_confidence_high"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:33` pattern_id_construction/medium: `"medium": pattern_registry.id("decision_cycle_confidence_medium"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:34` pattern_id_construction/medium: `"low": pattern_registry.id("decision_cycle_confidence_low"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:37` pattern_id_construction/medium: `"value_promoted_selected": pattern_registry.id("decision_cycle_value_promoted_selected"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:38` pattern_id_construction/medium: `"value_penalized_selected": pattern_registry.id("decision_cycle_value_penalized_selected"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:39` pattern_id_construction/medium: `"guard_blocked_high_score": pattern_registry.id("decision_cycle_guard_blocked_high_score"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:40` pattern_id_construction/medium: `"narrow_decision": pattern_registry.id("decision_cycle_narrow_decision"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:41` pattern_id_construction/medium: `"tie_like_decision": pattern_registry.id("decision_cycle_tie_like_decision"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:42` pattern_id_construction/medium: `"single_candidate": pattern_registry.id("decision_cycle_single_candidate"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:43` pattern_id_construction/medium: `"target_specific_value_used": pattern_registry.id("decision_cycle_target_specific_value_used"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:44` pattern_id_construction/medium: `"no_value_influence": pattern_registry.id("decision_cycle_no_value_influence"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/decision_cycle_summary_observer.py:45` pattern_id_construction/medium: `"guard_summary_missing": pattern_registry.id("decision_cycle_guard_summary_missing"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:19` pattern_id_construction/medium: `pattern_registry.id("action_wait_more_data"): self._wait_more_data,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:20` pattern_id_construction/medium: `pattern_registry.id("action_increase_attention"): self._increase_attention,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:21` pattern_id_construction/medium: `pattern_registry.id("action_inspect_pattern"): self._inspect_pattern,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:22` pattern_id_construction/medium: `pattern_registry.id("action_store_memory_candidate"): self._store_memory_candidate,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:23` pattern_id_construction/medium: `pattern_registry.id("action_commit_memory_draft"): self._commit_memory_draft,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:24` pattern_id_construction/medium: `pattern_registry.id("action_review_committed_memory_update"): self._review_committed_memory_update,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:25` pattern_id_construction/medium: `pattern_registry.id("action_update_committed_expsm_record"): self._update_committed_expsm_record,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:26` pattern_id_construction/medium: `pattern_registry.id("action_reduce_load"): self._reduce_load,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:27` pattern_id_construction/medium: `pattern_registry.id("action_preserve_integrity"): self._preserve_integrity,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:28` pattern_id_construction/medium: `pattern_registry.id("action_continue_observation"): self._continue_observation,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:29` pattern_id_construction/medium: `pattern_registry.id("action_generate_more_thought"): self._generate_more_thought,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:30` pattern_id_construction/medium: `pattern_registry.id("action_enter_consolidation_mode"): self._enter_consolidation_mode,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:31` pattern_id_construction/medium: `pattern_registry.id("action_exit_consolidation_mode"): self._exit_consolidation_mode,`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- `clc/action/internal_action_executor.py:37` pattern_id_construction/medium: `"memory_candidate": pattern_registry.id("state_memory_candidate_created"),`
  Recommendation: review when changing pattern ids, but do not treat as a debug-name semantic decision
- ... 373 more findings in `docs/debug_name_dependency_audit.json`.

## Low-risk/debug-only findings

- `clc/action/action_guard_audit_observer.py:171` debug_output_only/low: `"action_pattern_name": registry.debug_name(str(selected_action)),`
  Recommendation: keep debug_name for display/logging only
- `clc/action/action_guard_audit_observer.py:186` debug_output_only/low: `"action_pattern_name": registry.debug_name(action_pattern),`
  Recommendation: keep debug_name for display/logging only
- `clc/action/candidate_sources.py:10` runtime_source_label/low: `SOURCE_EXPSM_ACTIVATION = "expsm_activation"`
  Recommendation: keep stable runtime provenance labels separate from PatternRegistry debug names
- `clc/action/candidate_sources.py:11` runtime_source_label/low: `SOURCE_EXPSM_MECHANISM_SEARCH = "expsm_mechanism_search"`
  Recommendation: keep stable runtime provenance labels separate from PatternRegistry debug names
- `clc/action/decision_audit_observer.py:133` debug_or_report_label/low: `selected["action_debug_name"] = registry.debug_name(action_pattern)`
  Recommendation: keep for report/debug payloads; do not use as semantic control input
- `clc/action/decision_audit_observer.py:166` debug_or_report_label/low: `alt["action_debug_name"] = registry.debug_name(action_pattern)`
  Recommendation: keep for report/debug payloads; do not use as semantic control input
- `clc/action/decision_audit_observer.py:178` debug_or_report_label/low: `"action_debug_name",`
  Recommendation: keep for report/debug payloads; do not use as semantic control input
- `clc/action/decision_audit_observer.py:218` runtime_source_label/low: `if source == "expsm_activation":`
  Recommendation: keep stable runtime provenance labels separate from PatternRegistry debug names
- `clc/action/decision_audit_observer.py:220` runtime_source_label/low: `if source == "expsm_mechanism_search":`
  Recommendation: keep stable runtime provenance labels separate from PatternRegistry debug names
- `clc/action/decision_audit_observer.py:245` stable_constant_or_enum/low: `if mode == "target_specific":`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/action/decision_audit_observer.py:260` runtime_source_label/low: `and item.get("source") == "expsm_mechanism_search"`
  Recommendation: keep stable runtime provenance labels separate from PatternRegistry debug names
- `clc/action/decision_cycle_summary_observer.py:131` debug_output_only/low: `"action_pattern_name": selected.get("action_debug_name") or registry.debug_name(action_pattern),`
  Recommendation: keep debug_name for display/logging only
- `clc/action/decision_cycle_summary_observer.py:215` stable_constant_or_enum/low: `if value_scope == "target_specific":`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/akbsm/akbsm_association_field_updater.py:28` stable_constant_or_enum/low: `target_roles = [str(role) for role in probe.get("target_role_names", ())]`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/akbsm/akbsm_association_probe.py:78` stable_constant_or_enum/low: `role_key = ",".join(str(role) for role in target.get("target_role_names", ()))`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/akbsm/akbsm_association_probe.py:103` debug_output_only/low: `"pattern_name": self.pattern_registry.debug_name(str(item["pattern_id"])),`
  Recommendation: keep debug_name for display/logging only
- `clc/akbsm/akbsm_association_probe.py:130` debug_output_only/low: `"source_pattern_name": self.pattern_registry.debug_name(source_pattern_id),`
  Recommendation: keep debug_name for display/logging only
- `clc/consolidation/consolidation_pressure_module.py:116` stable_constant_or_enum/low: `and outcome.get("outcome_status") in {"failed", "partially_confirmed"}`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/consolidation/draft_context_relevance_scorer.py:273` stable_constant_or_enum/low: `for pattern_id in core_chain.get("outcome_patterns", ()):`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/context/context_memory.py:419` stable_constant_or_enum/low: `and e.payload.get("module") == "memory_draft_writer"`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/context/context_memory.py:653` debug_output_only/low: `f" {self.pattern_registry.debug_name(pattern_id)} "`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:785` runtime_source_label/low: `if payload.get("source") == "expsm_activation":`
  Recommendation: keep stable runtime provenance labels separate from PatternRegistry debug names
- `clc/context/context_memory.py:792` runtime_source_label/low: `elif payload.get("source") == "expsm_mechanism_search":`
  Recommendation: keep stable runtime provenance labels separate from PatternRegistry debug names
- `clc/context/context_memory.py:796` debug_output_only/low: `f"target={self.pattern_registry.debug_name(str(payload.get('source_target_pattern_id')))} "`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:928` debug_output_only/low: `f"{self.pattern_registry.debug_name(str(selected.get('action_pattern')))} / "`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:941` debug_output_only/low: `f"{self.pattern_registry.debug_name(str(alternative.get('action_pattern')))} / "`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:963` debug_output_only/low: `for pattern_id in payload.get("target_patterns", ()):`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:964` debug_output_only/low: `print(f" {self.pattern_registry.debug_name(pattern_id)}")`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:972` debug_output_only/low: `print(f" pattern: {self.pattern_registry.debug_name(pattern_id)}")`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:979` debug_output_only/low: `print(f" source: {self.pattern_registry.debug_name(str(payload.get('source_pattern_id', '')))}")`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:991` debug_output_only/low: `f" {self.pattern_registry.debug_name(str(association.get('pattern_id', '')))} "`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:998` debug_output_only/low: `print(f" target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1015` debug_output_only/low: `if "value_bonus" in mechanism or "value_penalty" in mechanism:`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1035` debug_output_only/low: `print(f" target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1047` debug_output_only/low: `print(f" target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1060` debug_output_only/low: `print(f" target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1072` debug_output_only/low: `print(f" target: {self.pattern_registry.debug_name(str(payload.get('target_pattern_id', '')))}")`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1101` debug_output_only/low: `debug_items.append([self.pattern_registry.debug_name(pattern_id) for pattern_id in item])`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1110` debug_output_only/low: `return {self.pattern_registry.debug_name(pattern_id): value for pattern_id, value in dict(activations).items()}`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1114` debug_output_only/low: `return self.pattern_registry.debug_name(value)`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1115` debug_output_only/low: `if key in {"label_kind", "prediction_kind", "outcome_pattern_id", "update_kind", "candidate_kind", "pressure_kind", "mode_pattern_id", "effect_kind", "review_kind", "draft_kind"...`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1116` debug_output_only/low: `return self.pattern_registry.debug_name(value)`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1118` debug_output_only/low: `return [self.pattern_registry.debug_name(item) for item in value]`
  Recommendation: keep debug_name for display/logging only
- `clc/context/context_memory.py:1144` debug_output_only/low: `return [self.pattern_registry.debug_name(item) for item in value]`
  Recommendation: keep debug_name for display/logging only
- `clc/evaluation/decision_cycle_history_view.py:67` stable_constant_or_enum/low: `flag in flags for flag in ("value_promoted_selected", "value_penalized_selected")`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/evaluation_field_updater.py:24` stable_constant_or_enum/low: `for pattern_id in signal.get("target_patterns", ()):`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/evaluation_target_observer.py:114` debug_output_only/low: `"pattern_name": self.pattern_registry.debug_name(entry.pattern_id),`
  Recommendation: keep debug_name for display/logging only
- `clc/evaluation/evaluation_target_observer.py:115` stable_constant_or_enum/low: `"target_roles": [self.role_ids[role_name] for role_name in role_names],`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/policy_pressure_review.py:139` stable_constant_or_enum/low: `if policy_pressure.pressure_type == "value_signal_pressure":`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/reflection_candidate_builder.py:139` stable_constant_or_enum/low: `and trend_label not in {"no_data", "value_influenced_recent_history"}`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/target_satisfaction_observer.py:71` runtime_source_label/low: `if decision.get("source") != "expsm_mechanism_search":`
  Recommendation: keep stable runtime provenance labels separate from PatternRegistry debug names
- `clc/evaluation/target_satisfaction_observer.py:141` stable_constant_or_enum/low: `"outcome_event_ids": [str(outcome.get("outcome_id")) for outcome in outcomes if outcome.get("outcome_id")],`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/target_satisfaction_observer.py:143` stable_constant_or_enum/low: `"evaluation_signal_ids": [str(signal.get("evaluation_id")) for signal in signals if signal.get("evaluation_id")],`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/target_satisfaction_observer.py:160` debug_output_only/low: `"target_pattern_name": self.pattern_registry.debug_name(target_pattern_id),`
  Recommendation: keep debug_name for display/logging only
- `clc/evaluation/target_satisfaction_observer.py:227` stable_constant_or_enum/low: `outcome_ids = {str(outcome.get("outcome_id")) for outcome in outcomes if outcome.get("outcome_id")}`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/target_satisfaction_observer.py:233` stable_constant_or_enum/low: `target_patterns = {str(pattern_id) for pattern_id in signal.get("target_patterns", ())}`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/target_satisfaction_observer.py:335` stable_constant_or_enum/low: `score = -negative_signal + positive_signal + (0.25 if any(o.get("outcome_status") == "confirmed" for o in outcomes) else 0.0)`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/target_satisfaction_observer.py:359` stable_constant_or_enum/low: `for key in ("outcome_event_ids", "effect_event_ids", "evaluation_signal_ids"):`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_candidate_builder.py:121` debug_output_only/low: `"target_pattern_name": str(observation.get("target_pattern_name") or self.pattern_registry.debug_name(str(observation.get("target_pattern_id", "")))),`
  Recommendation: keep debug_name for display/logging only
- `clc/evaluation/value_feedback_candidate_builder.py:123` stable_constant_or_enum/low: `"target_role_names": [str(role) for role in observation.get("target_role_names", ())],`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_memory_view.py:314` stable_constant_or_enum/low: `"target_role_names": [str(role) for role in roles if role],`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_memory_view.py:362` stable_constant_or_enum/low: `kind_match = bool(target_kind and link.get("target_kind") == target_kind)`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_review_gate.py:134` stable_constant_or_enum/low: `if candidate_type == "value_inconclusive_candidate":`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_review_gate.py:138` stable_constant_or_enum/low: `if candidate_type == "value_negative_candidate":`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_review_gate.py:145` stable_constant_or_enum/low: `if candidate_type == "value_positive_candidate":`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_review_gate.py:183` debug_or_report_label/low: `or self.pattern_registry.debug_name(str(candidate.get("target_pattern_id", "")))`
  Recommendation: keep for report/debug payloads; do not use as semantic control input
- `clc/evaluation/value_feedback_review_gate.py:186` stable_constant_or_enum/low: `"target_role_names": [str(role) for role in candidate.get("target_role_names", ())],`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_update_writer.py:186` debug_output_only/low: `"target_pattern_name": str(review.get("target_pattern_name") or self.pattern_registry.debug_name(str(review.get("target_pattern_id", "")))),`
  Recommendation: keep debug_name for display/logging only
- `clc/evaluation/value_feedback_update_writer.py:188` stable_constant_or_enum/low: `"target_role_names": [str(role) for role in review.get("target_role_names", ())],`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_update_writer.py:275` stable_constant_or_enum/low: `"target_role_names": [str(role) for role in review.get("target_role_names", ())],`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_update_writer.py:306` stable_constant_or_enum/low: `if value_direction == "positive" or candidate_type == "value_positive_candidate":`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_update_writer.py:308` stable_constant_or_enum/low: `if value_direction == "negative" or candidate_type == "value_negative_candidate":`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/evaluation/value_feedback_update_writer.py:310` stable_constant_or_enum/low: `if candidate_type == "value_inconclusive_candidate":`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/experience/causal_trace.py:79` stable_constant_or_enum/low: `and event.payload.get("decision_id") == source_decision_id`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/expsm/expsm_competition_observer.py:45` runtime_source_label/low: `if decision.get("source") != "expsm_activation":`
  Recommendation: keep stable runtime provenance labels separate from PatternRegistry debug names
- `clc/expsm/expsm_competition_observer.py:66` stable_constant_or_enum/low: `for candidate in decision.get("expsm_candidate_snapshot", ())`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/expsm/expsm_mechanism_search.py:112` debug_output_only/low: `"pattern_name": self.pattern_registry.debug_name(target_pattern_id),`
  Recommendation: keep debug_name for display/logging only
- `clc/expsm/expsm_mechanism_search.py:120` debug_output_only/low: `"pattern_name": self.pattern_registry.debug_name(entry.associated_pattern_id),`
  Recommendation: keep debug_name for display/logging only
- `clc/expsm/expsm_mechanism_search.py:212` stable_constant_or_enum/low: `target_roles = [str(role) for role in target.get("target_role_names", ())]`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- `clc/expsm/expsm_mechanism_search.py:282` stable_constant_or_enum/low: `roles = {str(role) for role in target.get("target_role_names", ())}`
  Recommendation: keep as stable control value unless it starts depending on display/debug pattern names
- ... 202 more findings in `docs/debug_name_dependency_audit.json`.

## Recommended migration path

Phase 1: audit current dependencies.

Phase 2: introduce semantic_class/tags in PatternRegistry manifest.

Phase 3: add PatternRegistry APIs: has_tag(pattern_id, tag), semantic_class(pattern_id), is_action(pattern_id), is_memory(pattern_id), is_audit(pattern_id), is_learnable(pattern_id).

Phase 4: migrate high-risk filters first.

Phase 5: keep debug_name only for display/logging.
