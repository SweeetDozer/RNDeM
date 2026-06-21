# Pattern semantics

`PatternRegistry` now supports explicit semantic metadata for each pattern id.
The current manifest keeps the existing `ids` and `patterns` maps unchanged and
adds a `semantics` map keyed by pattern id.

Each semantic record has:

- `semantic_class`: one conservative class such as `action`, `memory`,
  `evaluation`, `audit`, `target`, `expsm`, or `unknown`.
- `tags`: a list of simple string tags such as `action`, `memory`,
  `value_feedback`, `decision_audit`, `guard_audit`, `cycle_summary`,
  `internal`, or `non_learnable`.
- `learnability`: one of `normal`, `non_learnable`, `internal_only`, or
  `unknown`.

`debug_name(pattern_id)` remains available, but it should be used for
display/logging only. Runtime semantic decisions should move to registry helper
APIs.

## Registry APIs

`PatternRegistry` exposes:

- `semantic_class(pattern_id)`
- `tags(pattern_id)`
- `has_tag(pattern_id, tag)`
- `is_action(pattern_id)`
- `is_memory(pattern_id)`
- `is_audit(pattern_id)`
- `learnability(pattern_id)`
- `is_internal_only(pattern_id)`
- `is_non_learnable(pattern_id)`

Unknown pattern ids return conservative defaults: semantic class `unknown`,
empty tags, and all `is_*` helpers return `False`.

## Enrichment

Run:

```bash
python tools/enrich_pattern_semantics.py
```

The tool deterministically infers initial semantic metadata from existing
pattern names. It preserves ids, names, and `next_pattern_number`, and does not
touch ExpSM, AKBSM, or value feedback memory.

## Current Migration

The first migrated runtime area is `ActionProposer` action-pattern detection.
It now uses `PatternRegistry.is_action(pattern_id)` instead of
`debug_name(pattern_id).startswith("action_")`.

The second migrated area is `LearnabilityFilter`. It now classifies
non-learnable traces using semantic metadata such as `learnability`,
`non_learnable`, `mode_management`, `maintenance`, `homeostasis`, and
`consolidation_internal` tags. The ordinary action/effect path is preserved via
`ordinary_action` and `ordinary_effect` tags.

The third migrated area is memory-write technical filtering. Draft commit and
ExpSM commit validation now call
`is_memory_write_technical_pattern(pattern_registry, pattern_id)` from
`clc.consolidation.memory_write_filters` instead of checking
`debug_name(pattern_id)` prefixes. The helper rejects audit/internal/system and
specific memory-write/update/review tags while leaving normal input, ordinary
action/effect, prediction, and outcome material available for draft context.

The fourth migrated area is draft relevance/enrichment. `DraftInputContextEnricher`
and `DraftContextRelevanceScorer` now use helpers from
`clc.consolidation.draft_semantic_filters` for draft technical-noise detection,
context-material checks, draft-family matching, competing-family penalties, and
confirmed-outcome checks. These helpers read semantic classes and tags instead
of display/debug names.

The fifth migrated area is action scoring/selection source checks.
`clc.action.candidate_sources` defines stable runtime provenance labels such as
`expsm_activation` and `expsm_mechanism_search`. These labels are not
PatternRegistry debug names; scoring and selection now use source helper
functions instead of inline semantic-looking strings. Pattern semantics still
come from `PatternRegistry` for action/non-action classification.

The debug-name dependency audit now splits the old `unknown_runtime_logic`
bucket into precise categories such as `runtime_source_label`,
`pattern_id_construction`, `debug_or_report_label`,
`legacy_semantic_decision`, and `ambiguous_runtime_logic`. See
`docs/debug_name_audit_classifications.md` for category meanings.

The latest audit refinement moved pattern-id construction and stable metric or
status checks out of high-risk candidate-construction buckets. This keeps the
migration target focused on real debug-name semantic decisions rather than
known PatternRegistry id resolution.

The remaining five medium-risk `legacy_semantic_decision` findings were
reviewed and reclassified as stable payload labels or pattern-id construction.
No runtime behavior or PatternRegistry metadata changed during that review.

## Migration Plan

Phase 1: audit current debug-name dependencies.

Phase 2: enrich the pattern manifest with semantic metadata.

Phase 3: migrate high-risk filters one area at a time.

Phase 4: keep `debug_name` only for display/logging.

Recommended next targets are the single ambiguous demo-image debug-name parsing
finding, more real-input scenarios, and deeper phase-level tests.
