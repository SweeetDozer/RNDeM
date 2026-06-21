# Debug-name audit classifications

The debug-name dependency audit separates PatternRegistry display/debug names
from stable runtime control labels. The split is intentionally conservative:
stable labels are not escalated just because they are strings, while runtime
semantic decisions are not hidden as low-risk constants.

## Categories

- `runtime_source_label`: Stable runtime provenance labels such as
  `expsm_activation` and `expsm_mechanism_search`. These are not
  PatternRegistry debug names.
- `stable_constant_or_enum`: Stable control strings or enum-like values that
  do not derive semantic meaning from pattern display names.
- `debug_or_report_label`: Labels used for debug output, reports, snapshots, or
  human-readable payload fields.
- `pattern_id_construction`: Code constructing or resolving known pattern ids.
  These are worth reviewing during manifest changes, but they are not by
  themselves debug-name semantic decisions.
- `pattern_manifest_tooling`: Manifest enrichment, audit, and verification
  tooling.
- `legacy_semantic_decision`: Existing runtime semantic logic that still uses a
  stable string or name-like value and should be reviewed.
- `semantic_decision_needs_migration`: High-risk runtime semantic logic that
  should move to PatternRegistry metadata or typed helpers.
- `ambiguous_runtime_logic`: Findings that still need human classification.

The old `unknown_runtime_logic` bucket is kept as an allowed legacy value for
schema compatibility, but current reports should split it into the categories
above.

## Current split

Current audit baseline:

- previous `unknown_runtime_logic`: 190
- current `unknown_runtime_logic`: 0
- current `ambiguous_runtime_logic`: 1
- current `legacy_semantic_decision`: 0
- current `candidate_construction` high-risk: 0
- current total high-risk findings: 0

Known stable candidate source labels are classified as `runtime_source_label`.
Known pattern id construction and pattern id comparisons are classified as
`pattern_id_construction` instead of high-risk candidate construction unless
they derive semantic meaning from display names.

The final medium-risk `legacy_semantic_decision` findings were reclassified as
stable constants or pattern-id construction after manual review. The current
report has no high-risk findings and no legacy semantic decision findings.
