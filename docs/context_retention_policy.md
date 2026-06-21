# Context Retention Policy

`ContextMemory` retention is runtime-only. It limits the in-memory event log used
as the current context timeline, not permanent memory.

Permanent layers are not pruned by this policy:

- ExpSM records.
- AKBSM records.
- ExpSM draft stores.
- Value feedback metadata.
- Pattern store files.

## API

`ContextRetentionPolicy` lives in `clc/context/context_retention_policy.py`.

Default policy:

```python
ContextRetentionPolicy(
    max_events=5000,
    protected_recent_events=200,
    enabled=True,
)
```

`max_events=None` disables the hard event limit. `enabled=False` disables
runtime event pruning entirely. `protected_recent_events` is validated to be no
larger than `max_events` when a hard limit exists.

## Application Point

Retention is applied centrally in `ContextMemoryManager.apply_pending()` after
queued operations have been appended to `ContextMemory`. Individual modules do
not prune.

When the event count exceeds `max_events`, the oldest excess events are removed
from `ContextMemory.events`. Chronological order is preserved, and the newest
events remain in place.

## Safe To Prune

Only old runtime `ContextOperation` entries in `ContextMemory.events` are pruned.
Event payloads are not modified before removal.

## Side-List Retention

- Raw frames and thought frames.
- Context windows.
- Per-marker side lists such as labels, decisions, outcomes, and candidates.

Side-list retention is also runtime-only. Side lists store payload copies or
runtime objects rather than references into `ContextMemory.events`, so they are
bounded separately after event retention has established the oldest retained
event tick.

Primary side-list rule: remove entries older than the oldest retained
`ContextMemory.events` tick. Secondary rule: apply a max-entry cap per list.
Unknown-tick entries are preserved by default and reported as warnings. Windows
are pruned by `to_tick`, so a window is removed only when its end is older than
the retained event window.

Default side-list policy:

```python
SideListRetentionPolicy(
    enabled=True,
    prune_older_than_oldest_event=True,
    default_max_entries=500,
    keep_unknown_tick_entries=True,
)
```

## Not Pruned Yet

- Runtime fields such as active patterns, action candidates, evaluation entries,
  and AKBSM association entries.
- Permanent memory files.
- No semantic compaction or summarization is performed before pruning.

## Future Policy Options

- Summarization before pruning.
- Marker-specific retention windows.
- Event compaction.
- Frame/window retention tied to event retention.
- Policy-gated cleanup for per-marker side lists.
- Side lists with their own max length per list.
- Side lists pruned by oldest remaining `ContextMemory.events` tick.
- Side lists converted to derived views from events.
- Marker-specific lists compacted into summaries before pruning.
- Marker-specific semantic retention beyond simple tick/count rules.
