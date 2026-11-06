# RND-110 — Аудит границ записи и политик памяти RNDeM

**Дополнение после review:** разделы A–J сохраняют первоначальный аудит на исходном HEAD как историческое свидетельство. Исправление только F01, его текущий публичный контракт и результаты регрессии описаны в [разделе K](#k-f01-remediation-после-review). F02–F09 не исправлены.

Дата: 2026-11-06. Актуальный статус: **CLOSED** — review исправлений принят пользователем; разрешена одна локальная фиксация. Разделы A–J описывают состояние до исправления, K1–K6 сохраняют историю correction/review; итог закрытия — K7. Работа исключительно локальная.

Контрольная точка: `main`, `441c2b26725f6a116a38dec5baed339f1ec38e20`. Репозиторий: `RNDeM_Prototype`. Локальный `AGENTS.md` прочитан, не отслеживается, исключён записью `/AGENTS.md` в `.git/info/exclude`. Начальное рабочее дерево чистое. Предыдущий [RND-000](RND-000_architecture_inventory.md) использован как список проверяемых гипотез, не как замена анализа кода.

## A. Executive Summary

**Единого запрета дисковой записи по профилю нет.** `MemoryMutationPolicy` ограничивает определённые writers. Штатные demo/scenario runners защищают исходную Memory копированием в временный каталог. Прямой `CLCRuntime(memory_root, profile="safe_demo")` этого копирования не делает.

Проверены семь authoritative ExpSM writers, публичный `ExpSMCRUD.save`, пять путей сохранения ExpSM draft lifecycle, manifest, AKBSM nodes/edges, WL, transaction primitives, runtime initialization/reload/recovery, runners и обслуживающие утилиты. Основной inventory содержит **21 логический persistent-write path** (W01–W21), включая технический lock и административное enrichment manifest. Дополнительно отдельно перечислены копирование временной Memory, диагностические outputs и test fixtures; они не прибавлены к числу memory-write paths. Число означает маршруты решения/сохранения, а не количество методов CRUD или вызовов `json.dump`.

**Подтверждено одно нарушение — F01, P1:** публичный `ExpSMCRUD.save()` может сохранить stale snapshot поверх свежего store. Lock и fresh read выполняются, но результат fresh read не используется как основа записываемого состояния. На временных данных воспроизведены потеря чужой записи и удаление нового Stage-2 receipt из v2 ledger. После удаления receipt retry возвращает `UPDATED`, а не `ALREADY_APPLIED`. Стандартный CLC не вызывает этот административный API; это не доказательство runtime bypass.

**Policy gaps:** scope `allow_draft_writes` для двух review gates, authority manifest persistence и границы доверия административных API/custom policy. Legacy Outcome Feedback без policy — **документированное ограничение**, а не автоматически нарушение: [boundary](design_short_memory_to_expsm_boundary.md), раздел перед Representation Decision, и [representation](design_persistent_nfp_expsm_representation.md), раздел перед Representation Decision, явно называют OutcomeFeedback/CRUD исключениями. Его запись из runtime в `safe_demo`/`draft_only` подтверждена на временной Memory.

43 targeted unittest прошли. Demo и четыре scenario fixtures прошли. Новые harnesses воспроизвели F01 и проверили запреты/разрешённую запись, manifest, draft gates и runtime Outcome Feedback. Stage-1/2 гарантии сохраняются для проверенных специализированных writers и decorated CRUD mutations, но **универсальный no-lost-updates/receipt-preservation для публичного `save()` опровергнут**. Непрерывный native runtime этим аудитом не разрешается.

Все существовавшие 448 файлов вне `.git`/`__pycache__`, в том числе все 12 файлов Memory, сохранены побайтово. Production-код, tests, Memory, AGENTS и архитектурные контракты не изменены.

## B. Persistent Write Inventory

### B1. Метод и область

Проведён поиск файловых primitives в `clc/`, `Memory/`, entry points и `tools/`: write/append open, `json.dump`, write_text/bytes, replace/rename, unlink/remove, mkdir/touch, temporary files, copytree, os.open, сериализация, persistence helpers, logging и внешние storage libraries. Проверены callers найденных helpers, а не только совпадения синтаксиса. `json.dumps`/`to_json_data` без сохранения не считались записью.

Обозначения: **A** — authoritative; **D** — drafts; **T** — technical metadata; **R** — temporary runtime; **L** — diagnostics; **F** — fixtures. Общие источники: [runtime](../clc/runtime/clc_runtime.py), [policy](../clc/runtime/memory_mutation_policy.py), [transaction](../clc/consolidation/expsm_store_transaction.py).

| ID / категория | Caller → decision/guard → writer/file operation → target |
| --- | --- |
| W01 A | Explicit native caller → typed request validator + `allow_expsm_commit` → `NFPExpSMCreateWriter.create` → shared transaction → ExpSM_data.json |
| W02 A/T | Explicit native caller → occurrence/digest, source/TargetCore, `allow_expsm_update` → `NFPFeedbackApplyWriter.apply` → one shared replacement of metrics + receipts → ExpSM_data.json v2 |
| W03 A | CLC phase 05 / direct run → consolidation + recent commit decision + policy + valid ready draft → `ExpSMCommitWriter.run` → `_atomic_write_json(expsm_path)` delegates transaction → ExpSM_data.json |
| W04 A | CLC phase 05 / direct run → consolidation + recent update decision + policy + approved post_commit review → `ExpSMUpdateWriter.run` → transaction → ExpSM_data.json |
| W05 A | CLC phase 07 / direct run → consolidation + ready value review + policy → `ValueFeedbackUpdateWriter.run` → transaction → ExpSM_data.json value metadata |
| W06 A | CLC phase 06 / direct run → active + delayed linked decision/outcome + existing experience + dedup → `ExpSMOutcomeFeedback.run` → transaction → ExpSM_data.json hits/misses/confidence/repeatability/feedback metadata |
| W07 A | Administrative CRUD methods and module wrappers → structural/existence/ID validation, no runtime policy → `authoritative_mutation` fresh load → mutation + save → transaction → ExpSM_data.json |
| W08 A/T | Administrative direct `ExpSMCRUD.save()` → lock + fresh format read, **stale self.data replacement** → transaction → complete ExpSM_data.json, including receipts (F01) |
| W09 D | CLC phase 05 / direct run → consolidation + recent store decision + approved review + `allow_draft_writes` + draft validation → `MemoryDraftWriter._save_store` → mkdir/open w/json.dump → ExpSM_drafts.json |
| W10 D | CLC phase 05 / direct run → consolidation + reviewable draft + not already reviewed → `DraftCommitGate.run/_save_store` → direct truncate/dump → draft status/commit_review in ExpSM_drafts.json |
| W11 D | CLC phase 02 / direct run → consolidation + committed draft + pending_expsm_update → `ExpSMUpdateReviewGate.run/_save_store` → direct truncate/dump → post_commit review metadata in ExpSM_drafts.json |
| W12 D | W03 valid/duplicate/repaired committed draft → `_atomic_write_json(draft_store_path)` → fixed sibling .json.tmp + replace → ExpSM_drafts.json; governed by commit flag, not independently draft flag |
| W13 D | W04 approved/already-applied update → `_atomic_write_json(draft_store_path)` → fixed sibling .json.tmp + replace → ExpSM_drafts.json; governed by update flag, not independently draft flag |
| W14 T | Registry init/default completion, `id/register/register_if_missing`, bulk-update exit, direct save → validation/dirty rules, no policy → `PatternRegistry.save` → manifest.json.tmp write_text + replace → pattern_manifest.json |
| W15 A | Administrative `AKBSMCRUD.create_nfp/update_nfp` + wrappers → ID/existence checks → `_write_nfp_file/_write_json` → mkdir/open w/dump → AKBSM/DB/<id>.nfp |
| W16 A | Administrative `delete_nfp` → existence + connected-edge rules → unlink node + optional W17 → node removal and graph cleanup |
| W17 A | Administrative edge create/update/delete or direct save_edges / W16 → endpoint/existence checks for CRUD; direct save_edges accepts supplied mapping → `_write_json` → open w/dump → AKBSM/AKBSM_ne.json |
| W18 A | Administrative WL create/write/clear + wrappers → create checks overwrite only → `WLCRUD.write` → mkdir/write_text → WL/WL.txt |
| W19 A | Administrative WL append/append_line + wrappers → formatting only → `WLCRUD.append` → mkdir/open a/write → WL/WL.txt |
| W20 T | Any caller entering `ExpSMStoreTransaction.mutation` → no authority policy at primitive → mkdir/os.open O_CREAT/flock → sibling ExpSM_data.lock; lock remains after unlock |
| W21 T | Explicit CLI `tools/enrich_pattern_semantics.py::main` → compare inferred semantics, assert IDs/names/counter unchanged → direct manifest write_text if changed → original Memory/pattern_manifest.json |

Sources for W01–W08 are detailed in D. Other sources: [draft writer](../clc/consolidation/memory_draft_writer.py), [draft gate](../clc/consolidation/draft_commit_gate.py), [update review](../clc/consolidation/expsm_update_review_gate.py), [registry](../clc/core/pattern_registry.py), [AKBSM CRUD](../Memory/AKBSM/AKBSM_CRUD.py), [WL CRUD](../Memory/WL/WL_CRUD.py), [enrichment](../tools/enrich_pattern_semantics.py).

`ExpSMStoreTransaction.write_complete_store` is the shared physical sink for W01–W08, not an eighth specialized writer. It is callable directly inside `mutation()` and has no policy. Its caller owns authorization, complete candidate construction and fresh-load discipline; it is not a filesystem security boundary. Temporary NamedTemporaryFile + fsync + replace + cleanup are included in each authoritative route, not counted as distinct cognitive writes. W20 is counted separately because it creates durable filesystem metadata even when no JSON mutation follows.

### B2. Additional side effects and excluded categories

| Категория | Механизм / граница |
| --- | --- |
| R → isolated durable files | `demo_run` и `run_scenario_fixture`: TemporaryDirectory + copytree Memory; subsequent W01–W20 where reachable target copied paths; cleanup removes the entire session tree |
| R, RAM only | ContextMemory/ShortMemory, fields, operation pools, native evidence/proposals, AKBSM proposal provider/lifecycle/controller/ContextMemory metadata adapters: no persistent sink found; metadata flags explicitly reject commit/write authority |
| L | Runtime/diagnostic modules print/return data; existing *.log files are not evidence of a logging writer in CLC. Shell redirection may persist stdout at caller-chosen path. Audit `tools/audit_debug_name_dependencies.py::write_json_report/write_markdown_report` writes docs reports; not a memory mutation route |
| F | Verifiers create synthetic JSON/manifests in TemporaryDirectory. `tools/phase_regression_snapshots.py::write_snapshot` writes scenario regression snapshots when explicitly invoked; not runtime learning |
| Maintenance | `tools/clean_pycache.py` deletes generated __pycache__; not persistent memory. Python bytecode creation is disabled in this audit using `-B` |
| Test helper hazards | Some verifiers construct `PatternRegistry()` at default original path or `CLCRuntime(ROOT / "Memory")`. They are not approved safe merely because their filename begins verify. Full policy verifier intentionally NOT RUN |

No production writer found for DTF, a durable Chronicle/ShortMemory journal, native pending-event outbox, proposal disk storage or AKBSM runtime graph mutation. `PatternStore.add_pattern` and runtime fallback records are in-memory additions; registry name registration can separately cause W14. Serialization methods alone grant no write authority.

## C. Policy / Mode Matrix

### C1. Declared profile factory

`policy_for_profile` sets the following booleans. `memory_is_temporary` is a **caller-supplied claim**, not path confinement or a check that a directory is temporary. `real_memory_root` is reporting metadata. Caller-supplied `MemoryMutationPolicy` replaces the profile-derived object in CLC; flags and profile label can therefore disagree. The frozen dataclass is configuration, not an unforgeable capability.

| Flag | safe_demo, temporary=False | safe_demo, temporary=True | draft_only | mutating_memory |
| --- | --- | --- | --- | --- |
| allow_draft_writes | false | true | true | true |
| allow_expsm_commit | false | false | false | true |
| allow_expsm_update | false | false | false | true |
| allow_value_feedback_update | false | false | false | true |
| allow_akbsm_write | false | false | false | false |
| akbsm_draft_proposals_enabled | false | false | false | false |
| mode_c_memory_gate_advisory_enabled | false | false | false | false |

### C2. Write route matrix

Cells distinguish contract and execution. “Да” always requires the additional conditions listed; not an unconditional write. “Вне” means profile has no enforceable scope here, not authorization for future cognitive integration. Sources: policy, writer run/create/apply methods, [legacy boundary](design_short_memory_to_expsm_boundary.md), [AKBSM ADR](adr_akbsm_write_policy.md).

| Путь | safe_demo | draft_only | mutating_memory | Дополнительные условия / фактическая проверка | Direct writer / CLC |
| --- | --- | --- | --- | --- | --- |
| W01 native CREATE | контракт/факт нет | нет | да | validator + allow_expsm_commit; no system mode input | explicit mandatory policy enforced / not wired |
| W02 native APPLY | нет для нового update | нет для нового update | да | target, occurrence, digest, classification, allow_expsm_update; known duplicate/conflict resolved before policy | explicit mandatory policy enforced / not wired |
| W03 commit | нет | нет | да | consolidation, recent selected commit decision, ready valid reviewed draft, allow_expsm_commit | same run gates / same gates |
| W04 update | нет | нет | да | consolidation, recent selected update decision, pending approved review, allow_expsm_update | same run gates / same gates |
| W05 value update | нет | нет | да | consolidation, complete ready review, thresholds, allow_value_feedback_update | same run gates / same gates |
| W06 legacy outcome | documented exception; факт да | exception; факт да | да | active, work/evidence/linkage, existing record, dedup; policy absent | same evidence checks / reachable phase 06 |
| W07/W08 ExpSM CRUD | вне / факт да | вне / да | вне / да | administrative explicit invocation, no mode/policy; W08 has integrity defect | yes / not used |
| W09 draft create/merge | temporary only; факт same | да | да | consolidation, decision, review, allow_draft_writes | same gates / phase 05 |
| W10/W11 draft reviews | intended scope OPEN QUESTION; факт да even temporary=False | факт да | факт да | consolidation + eligible drafts; no policy; draft metadata only | same / phases 05 and 02 |
| W12/W13 lifecycle after commit/update | нет via factory flags | нет | да | commit/update flag, independent draft flag not checked | same / same |
| W14 registry | authority OPEN QUESTION; факт да | да | да | new names/default completion/explicit save, no mode/policy | any component / init and tick |
| W15–W17 AKBSM CRUD | runtime contract forbidden; admin API outside profile | same | same | independent administrative API, no policy | yes / no runtime path found |
| W18/W19 WL CRUD | OPEN QUESTION / admin writes | same | same | independent administrative API | yes / no runtime path found |
| W20 lock | technical side effect possible | possible | possible | mutation entry, not profile; APPLY reads before denying | primitive / whichever writer enters |
| W21 enrich manifest | outside runtime profile | same | same | explicit administrative CLI; no mode/policy | explicit CLI / not wired |

Native APPLY may return `ALREADY_APPLIED` under a deny policy because an existing receipt is checked first: this does **not** apply a new metric update. It may create a lock file; authoritative JSON bytes after denial remain unchanged. “Denied memory mutation” is not “zero files created”.

Optional policy defaults of MemoryDraftWriter, ExpSMCommitWriter, ExpSMUpdateWriter and ValueFeedbackUpdateWriter are **MUTATING_MEMORY**, whereas default CLCRuntime profile is SAFE_DEMO. Direct callers omitting policy do not inherit runtime restrictions. This is a compatibility/API design boundary, not a bypass of an object that actually received a denying policy. Native CREATE/APPLY require an explicit policy.

### C3. Modes and action guard

[ModeActionGuard._decision](../clc/system/mode_action_guard.py) allows most active actions, consolidation internal memory actions, suppresses external attention in consolidation, blocks consolidation transitions in recovery but otherwise reduces action priority; unknown modes default allowed with factor .7. It is **not** a memory policy checker.

| Component | active | consolidation | recovery / unknown |
| --- | --- | --- | --- |
| Commit/update/value/draft writer run | no write | potentially writes after route-specific gates | no write |
| DraftCommitGate / UpdateReviewGate | no write | eligible draft metadata write without policy | no write |
| Outcome Feedback run | potentially writes | no write | no write |
| Native create/apply | no mode parameter | no mode parameter | no mode parameter |
| Registry / administrative CRUD | no mode restriction | no mode restriction | no mode restriction |

Guarded selected decisions influence W03/W04/W09 through recent-decision evidence. Value writer and review gates do not require a separate selected write action. Writer `run` methods do not re-invoke ModeActionGuard; an administrative caller can construct ContextOperations and review payloads. Review statuses are data, not signed permissions. That is not proof of a runtime producer forging approvals. Private `_save_store`, `_write_data`, `_run_locked` are implementation helpers, not separate approved public authorization APIs; arbitrary trusted Python code is not confined by these classes.

## D. Authoritative ExpSM Writers

### D1. Shared persistence and readback

[ExpSMStoreTransaction](../clc/consolidation/expsm_store_transaction.py) coordinates an in-process RLock by resolved path plus outermost stable sibling `.lock` flock. Nested mutation is reentrant. `load_for_mutation_strict` requires mutation; source v2 format is tracked. `write_complete_store` requires mutation, validates the complete candidate, rejects downgrade of a read v2 source, writes a unique sibling temporary file, flushes/fsyncs, replaces the complete store, best-effort fsyncs parent, cleans pre-replace temporary files. Invalid stores fail closed; absent store normalizes to empty legacy sections.

**Authorization is not performed here.** Nor does the sink merge stale candidate contents with current data. A lock serializes operations, but cannot repair an already stale snapshot. Public primitive callers must not infer permission from obtaining a lock.

Readback is caller-owned: native writers compare expected full typed records and native APPLY receipt/index; legacy writers and CRUD re-read/validate store but do not universally compare exact intended record contents. Parent-directory fsync errors are suppressed, so this is not a promise of power-loss durability on every FS/OS. fcntl is a Linux/POSIX mechanism. No multi-file transaction covers ExpSM + drafts or AKBSM node + edges.

### D2. Per-writer evidence

| Writer / public entry | Authority and direct invocation | Guards / Stage 1 / v2 | Denial and failure behavior |
| --- | --- | --- | --- |
| [NFPExpSMCreateWriter.create](../clc/experience/expsm_native_create.py) | Mandatory explicit policy; allow_expsm_commit. Explicit isolated API, not CLC | complete typed request validator, initialization profile; no mode/action/review gate inside writer. Request builder/proposal review is upstream, not proof enforced by sink. Shared fresh-load transaction, writer-owned max+1; complete v2 preserved | invalid/unsupported request or policy denial before mutation/no allocation; STORE_INVALID; WRITE_FAILED before replace preserves old bytes; READBACK_FAILED after replace is indeterminate, attempted ID, retry_safe=false; read-only reconciliation |
| [NFPFeedbackApplyWriter.apply](../clc/expsm/nfp_native_feedback_apply.py) | Mandatory policy; allow_expsm_update. Explicit API, not CLC | HIT/MISS typed evidence; UUIDv4 occurrence identity, canonical digest, exact source + native record + TargetCore; known receipt/occurrence conflict checks before policy; fresh operational metrics; one v2 metric+receipt replacement | only HIT/MISS evaluation results carry typed evidence; non-applying results do not update; DENIED_BY_POLICY, TARGET_NOT_FOUND/NOT_NATIVE, STALE_OR_CHANGED_TARGET, STORE_INVALID; ALREADY_APPLIED and EVENT_CONFLICT; WRITE_FAILED vs indeterminate READBACK_FAILED + read-only reconciliation |
| [ExpSMCommitWriter.run](../clc/consolidation/expsm_commit_writer.py) | injected policy in CLC, allow_expsm_commit; omitted policy means mutating in direct call | consolidation, recent commit decision ≤4 ticks with consolidation selection, valid ExpSM target ready draft/review, structural/evidence checks, signature dedup. Shared fresh ExpSM load, full v2 preserved. Draft save separate | wrong mode/no decision returns []; denied MODULE_UPDATE before transaction; malformed store/read/write failure yields failed module update. Authoritative replace can succeed before draft-save failure; no cross-file rollback |
| [ExpSMUpdateWriter.run](../clc/consolidation/expsm_update_writer.py) | injected policy, allow_expsm_update; direct omitted policy mutating | consolidation + recent update decision ≤4 ticks, committed draft/pending update/approved review, review IDs and target existence. Shared transaction; full v2 preserved; separate draft save | no work []; denied/invalid/write error MODULE_UPDATE; same partial multi-file completion risk as commit; applied review sets may already change before a later write fails |
| [ValueFeedbackUpdateWriter.run](../clc/evaluation/value_feedback_update_writer.py) | injected policy, allow_value_feedback_update; direct omitted policy mutating | consolidation + required review fields; ready_for_future_application=true, apply_now=false, ready decision, strength≥.70, evidence≥.60, exact source; review dedup RAM + stored metadata. No selected write-action requirement. Shared transaction; v2 preserved | wrong mode/no ready review []; denied MODULE_UPDATE; read/write failure failed MODULE_UPDATE; helper refuses a path different from authoritative path; readback validates JSON/store |
| [ExpSMOutcomeFeedback.run](../clc/expsm/expsm_outcome_feedback.py) | no policy input; does not read SystemState.memory_mutation_policy. Documented legacy evidence-based exception; reachable CLC phase 06 | active; FEEDBACK_DELAY_TICKS=2; linked selected decision, outcome/effect; existing experience; hit/partial_hit/miss vs no_feedback; RAM and stored key dedup. Fallback matching remains for non-explicit source cases. Shared fresh-load transaction and full v2 preservation | wrong mode/no work []; OSError/ValueError swallowed into []; no policy denial marker. `_processed_keys` updated before write, so failures are not Stage-2 retry guarantees. Ordinary readback validates, not native receipt proof |
| [ExpSMCRUD](../Memory/ExpSM/Exp_CRUD.py) | independent administrative class + module wrappers with original DATA_FILE default; no policy or mode; no CLC caller found | 12 decorated mutators fresh-load under transaction: experience/reflex create/update/delete, both conversions, four counters; ID/existence checks. save itself nested transaction; decorated route preserves v2/receipts | exceptions propagate; no policy denial. `save()` direct is separate unsafe W08: read current format but replace stale self.data; valid v2 can lose receipts, despite no format downgrade |

Native create/apply lock-acquisition errors occur at the outer `with transaction.mutation()` and can propagate instead of returning WRITE_FAILED. Their structured results cover the caught load/write/readback portions, not every possible OS exception. This is not evidence of a successful unauthorized write.

### D3. Stage-1 / Stage-2 verification boundary

Stage-1 tests passed for per-path locking/reentrancy, lock failure closed, mixed writer AST ownership, fresh mutation-load ordering, full replacement, legacy/v2 validation, multiprocess same/different record updates. Stage-2 tests passed for occurrence UUID/digest versions, exact source/TargetCore, operational drift, receipt ledger, atomic metric+receipt, duplicate/conflict, reopen/retry/lost acknowledgement, and other writer-family v2 receipt preservation.

These tests **do not cover standalone stale `ExpSMCRUD.save()`**. The Stage-1 AST inventory enumerates 7 writer-family entry points and 12 decorated CRUD methods; matching `fresh read exists` is insufficient to establish that written candidate uses it. F01 is a counterexample to universal no-lost-updates and durable replay preservation across every public write path. Native APPLY itself still passes its own invariants under cooperating correct writers.

Recovery reconciliation helpers load/compare state and never retry/create/apply. Ledger is not a pending event queue; no guaranteed recovery of events lost before APPLY, no automatic Feedback integration or durable outbox was added. Historical design sections describing Stage-1 v2 refusal are superseded by current Stage-2 code/tests, which allow v2 and preserve receipts in the tested routes.

## E. Demo / Runtime Isolation

### E1. Actual chains

- [main.py](../main.py) → `demo_run` → TemporaryDirectory → copytree original Memory if present → CLCRuntime(copy, SAFE_DEMO, temporary=True) → demo feed calls. Missing source Memory uses a new temporary fallback root. Writers and registry receive copied-root paths.
- [run_scenario_fixture](../clc/scenarios/scenario_runner.py) → hash selected original files → TemporaryDirectory → copytree supplied memory_root → `_runtime_for_fixture(temp_memory)` → runtime inputs → cleanup → original selected hash comparison. Fixture can change profile/temporary flag; actual root still remains copied.
- Direct `CLCRuntime(...)`: passes supplied root directly to registry, PatternStore, AKBSMAdapter, ExpSMAdapter, outcome/value/draft/commit/update writers. No temporary copy or path validation. Default root is original Memory. Passing safe_demo alone is insufficient for read-only behavior.
- Direct native writers and Memory module administrative wrappers are separate explicit entry points. Default CRUD wrappers bind their module DATA_FILE/DB_DIR/EDGE_FILE, which can be original Memory regardless of another runtime's root. These APIs are not called by standard CLC writers.

No symlinks found in current Memory. copytree defaults copy file contents; no surviving writer path from standard runners to original Memory found in the inspected graph. The original root remains accessible to trusted Python code: isolation here is path injection and copying, not OS confinement against hostile code, monkeypatches or later unreviewed imports.

### E2. Three kinds of safety

| Protection | What is proved | What is not proved |
| --- | --- | --- |
| Policy | Explicitly denied draft/commit/update/value attempts return blocked operations and preserve all copied bytes; native CREATE/APPLY denials preserve authoritative JSON | zero disk side effects for all components; Outcome/registry/review coverage |
| Filesystem isolation | demo/scenario writes resolve to temporary Memory; original baseline hashes unchanged | direct runtime on original root is safe |
| No event | Some normal scenarios produce no eligible feedback/draft | prohibition when eligible evidence or pre-existing drafts appear |

The audit supplied eligible events to a safe_demo and draft_only runtime on copied Memory and invoked the actual phase 06 helper: legacy record hits changed **1 → 2** in both profiles. Events were injected by the harness; this proves the runtime path is reachable with suitable ContextMemory evidence, not that every ordinary demo input generates that evidence. Direct run has the same evidence gates. ModeActionGuard is not consulted at phase-06 feedback write time.

For draft review, a pre-existing incomplete pending draft became rejected/reviewed and was saved even with allow_draft_writes=false. A committed draft with pending update was reviewed/saved likewise. Both kept authoritative bytes unchanged. A new registry name changed manifest under safe_demo; initialization can also save missing/extended manifests before the first tick, independently of policy. A complete manifest with no new IDs need not change.

Reload triggered by permanent_memory_modified markers reloads ExpSMAdapter and refreshes ValueFeedbackMemoryView; no independent disk save found. Recovery reconciliation is read-only. Entering mutation may create .lock, including a denied native APPLY after its authoritative read. Registry initialization is the clear persistent startup side effect; no autonomous AKBSM/WL write found in init/reload/recovery.

Scenario runner's built-in `_real_memory_hashes` covers only ExpSM_data, AKBSM_ne, semantic_core and technical_feedback JSON. It omits manifest, drafts, WL, nodes and new lock files. Its memory_unchanged=true alone is weaker than whole-tree byte/name comparison. This audit separately compared all 12 original Memory files and checked for new files.

## F. Confirmed Findings

Severity reflects demonstrated impact and reachability, not an assumption that every low-level API is a cognitive bypass.

| Finding | Classification / severity | Evidence and conclusion |
| --- | --- | --- |
| F01 | **CONFIRMED VIOLATION / P1** | `Memory/ExpSM/Exp_CRUD.py::save` lines 61–66 fresh-loads current format but writes stale self.data. Two objects: A loads empty; B creates id=1; A.save removes id=1. v2 case: A loads one-receipt envelope; native APPLY adds receipt 2; A.save reduces ledger 2→1; retry returns UPDATED. Violates no-lost-updates/receipt survival across public authoritative writes. Explicit admin invocation required; no CLC call found. |
| F02 | **POLICY GAP / P2** | `DraftCommitGate.run/_save_store` and `ExpSMUpdateReviewGate.run/_save_store` save review metadata in consolidation without allow_draft_writes. Test under safe_demo temporary=False changes draft bytes, not authoritative bytes. Policy factory/representation table describe draft permission, but exact inclusion of review/status bookkeeping is not defined explicitly enough to assert universal violation. OPEN QUESTION: is review persistence covered by draft write permission? |
| F03 | **POLICY GAP / P2** | `PatternRegistry.__post_init__/id/save` and enrich utility persist technical manifest without profile policy. New name under safe_demo changed copied manifest. Authority for technical registry writes is not documented as universal read-only exception or permission. Not proof of unauthorized authoritative ExpSM mutation. |
| F04 | **ISOLATION DEPENDENCY / P2** | `demo_run`, scenario runner copy roots; direct runtime does not. Eligible Outcome evidence wrote at runtime phase 06 in safe_demo/draft_only. If caller passes original Memory, same resolved paths can target it. Tested only copied root; original-root execution intentionally NOT RUN. Safe demos depend on correct entry point/root. |
| F05 | **DESIGN LIMITATION / P2** | Legacy Outcome/low-level CRUD policy exception explicitly documented in boundary/representation. Outcome has active/evidence/dedup limits, not inherited policy authority. Direct mutating defaults for four legacy writers are also outside safe runtime defaults. Treating safe_demo as universal authoritative-read-only would be incorrect. |
| F06 | **POLICY GAP / P2** | Admin ExpSM/AKBSM/WL CRUD, manifest enrichment and shared persistence primitives lack profile authorization. No runtime AKBSM/WL caller found; intended admin credential/root boundary remains undefined. AKBSM ADR prohibits runtime cognitive writes and does not retroactively make existing manual utilities runtime bypasses. |
| F07 | **DESIGN LIMITATION / P3** | Draft truncate/dump, fixed temporary filenames, AKBSM node+edge sequence, WL truncate/append and registry fixed tmp do not inherit ExpSM locking/readback/durability. Commit/update authoritative+draft are separate replacements. No crash experiment on these routes; limitation established by code, not observed corruption. |
| F08 | **ISOLATION DEPENDENCY / P2** | Whole-tree safety is not proved by scenario runner's four-file hash set; full policy verifier constructs original-root runtime, and thus is unsuitable under this audit's strict safety rule. Isolated helper reuse passed, full script NOT RUN. |
| F09 | **DESIGN LIMITATION / P3** | MemoryMutationPolicy/temporary flags trusted configuration; system modes and ModeActionGuard cover actions, not all writers. Native writers have no mode gate; no production contract found requiring such a gate for explicit native APIs. |
| FP01 | **FALSE POSITIVE** | Absence of policy argument in Outcome Feedback does not by itself violate current documented authority. Real write confirmed; legacy exception documented. Future integration authority remains a decision. |
| FP02 | **FALSE POSITIVE** | `_atomic_write_json` in commit/update is not a direct-authoritative-write bypass: path==expsm_path delegates shared transaction; direct file save is draft target branch only. Value helper rejects other paths. |
| FP03 | **FALSE POSITIVE** | AKBSM proposal/lifecycle/advisory metadata does not commit graph. Default flags false, commit_allowed=True rejected, no production filesystem sink or standard CLC provider wiring found. |
| FP04 | **FALSE POSITIVE** | No hidden runtime WL/AKBSM CRUD writer or disk write in serialization/PatternStore fallback found. Explicit administrative APIs remain real writes, not runtime bypass evidence. |

Totals: **1 confirmed violation; 3 policy gaps (F02/F03/F06); 2 isolation dependencies (F04/F08); 3 design limitations (F05/F07/F09); 4 false positives.** Severity of F01–F09: **P0=0, P1=1, P2=6, P3=2**. FP01–FP04 are additional resolved hypotheses without assigned severity.

## G. Behavioral Evidence

### G1. Existing targeted checks

Command (all executed with `-B`):

```text
python -B -m unittest tools.verify_expsm_persistence_stage1 \
  tools.verify_nfp_expsm_policy_gated_create \
  tools.verify_nfp_native_feedback_apply \
  tools.verify_nfp_native_feedback_replay_idempotency
```

Result: **PASS — 43 tests, 2.375 s, exit 0.** Source inspection before execution confirmed tested writer targets/fixtures use TemporaryDirectory. Tests read original sources/scenarios for assertions; they do not invoke a suspect writer against original Memory. Detailed behavioral test names are in [Stage 1](../tools/verify_expsm_persistence_stage1.py), [CREATE](../tools/verify_nfp_expsm_policy_gated_create.py), [APPLY](../tools/verify_nfp_native_feedback_apply.py), [replay](../tools/verify_nfp_native_feedback_replay_idempotency.py).

| Check | Result / limit |
| --- | --- |
| Shared locking, nested locking, lock failure closed, cross-process same/different record updates | PASS in Stage-1 suite; no claim for arbitrary stale snapshots |
| Native request validation, deny bytes unchanged, permitted create, pre-replace failure, indeterminate readback + read-only recovery | PASS |
| Native exact source/TargetCore, operational drift, deny bytes unchanged, hit/miss formulas, pre-replace error, readback reconciliation | PASS |
| UUID/digest versions, duplicate reopen, EVENT_CONFLICT, occurrence conflict, lost ack/retry, metric+receipt one replace, restart idempotency | PASS |
| v2 + receipts across seven writer families | PASS for tested public mutation entries/decorated CRUD; standalone save NOT covered |
| `python -B main.py` | PASS exit 0; output redirected only to /tmp; copied Memory |
| audio_periodic | PASS, memory_unchanged=true, warnings=[] |
| akbsm_safe_demo_no_write | PASS, memory_unchanged=true, warnings=[] |
| akbsm_draft_only_no_commit | PASS, memory_unchanged=true, warnings=[] |
| akbsm_mutating_memory_still_blocked | PASS, memory_unchanged=true, warnings=[] |
| Full `verify_memory_mutation_policy.py` | NOT RUN: `_case_direct_safe_default` constructs runtime on original Memory; reused isolated helper instead |
| Full 115-verifier/regression campaign | NOT RUN; outside targeted audit scope |

### G2. Temporary experimental harness

A disposable `/tmp/rnd110_harness.py` used `TemporaryDirectory`, copied Memory with shutil.copytree and explicitly passed copied roots. Synthetic replay fixtures reused `ReplayIdempotencyTests.setUp/tearDown`, whose store path is temporary. No production source/test modification. Harness/result/demo logs removed after reporting. Method and inputs below allow reproduction without retaining a permanent test file.

| Experiment | Actual result / interpretation |
| --- | --- |
| Reuse `_blocked_runtime_writer_attempts` with copied-root CLCRuntime safe_demo temporary=False | PASS: draft/commit/update/value all emitted policy-blocked operations; all copied file bytes/names unchanged after attempts (snapshot taken after init) |
| Same with draft_only | PASS: commit/update/value blocked; copied tree unchanged for those supplied events; not a proof draft creation is denied |
| Reuse `_case_mutating_temp_fixture(copy)` | PASS: ready value review permits copied ExpSM write and leaves originals unchanged |
| New registry ID under safe_demo | PASS reproduction: copied manifest changed although allow_draft_writes=false; no inference that manifest is a draft |
| Pending draft `{draft_id, draft_status=draft_pending_commit}` → DraftCommitGate.run in consolidation, safe_demo/non-temp policy | PASS reproduction: 1 operation; draft bytes changed; authoritative bytes unchanged |
| Committed draft with committed_experience_id=2, pending_expsm_update=true, no valid snapshot → UpdateReviewGate.run | PASS reproduction: rejected review persisted, 1 operation; draft changed, authoritative unchanged |
| Runtime Outcome, safe_demo and draft_only | PASS reproduction: copied record hits 1→2 in each. Supplied mechanism decision tick 1, linked effect tick 2, confirmed target outcome tick 3; phase 06 at tick 4, active_processing=True |
| Two CRUD instances, stale save | **FAIL contract / successful defect reproduction**: create id=1 via B; A.save removes it |
| v2 stale save after new native APPLY | **FAIL contract / successful defect reproduction**: receipt count 2→1, schema_version remains 2, retry UPDATED |

Runtime Outcome fixture fields: experience id=1, if=internal_tension, then=action_preserve_integrity, result/recommendation=state_integrity_preservation, confidence=.7, repeatability=.6, hits=1, misses=0, status=2. Decision source=expsm_mechanism_search with exact source_experience_id/search_id/target; effect references decision ID; outcome references effect/decision and includes matched target. This is an eligible legacy path, not a mocked writer or policy bypass by monkeypatch.

Minimal F01 reproduction, **only with a temporary path**:

```python
# p is inside TemporaryDirectory, contains {"experience": {}, "reflexes": {}}.
a = ExpSMCRUD(p)
b = ExpSMCRUD(p)
b.create_experience(["a"], ["b"], ["c"], ["b"], experience_id="1")
a.save()  # record 1 disappears: a.data predates b's mutation
```

For v2: seed valid envelope with one native receipt using existing replay fixture; instantiate stale CRUD; apply a second valid event with occurrence UUID `55555555-5555-4555-8555-555555555555`; observe two receipts; stale.save(); observe one receipt; retry second event returns UPDATED. Because stale save also restores old metrics, the experiment establishes lost durable history and broken duplicate classification, not an assertion that net counters necessarily double in this exact sequence.

### G3. Limits and preservation checks

Behavioral tests exercise selected valid/denied/error cases, not every combinatorial mode, OS failure or malicious path. Draft creation positive behavior is supported by code review and existing lifecycle logic, but no separate new positive draft-create experiment was needed to reproduce the authority gaps; native CREATE and allowed value writes provide positive authoritative checks. AKBSM/WL CRUD were statically traced, not behaviorally mutated in this audit. Original-root suspect writer calls, arbitrary hostile-code confinement and power-loss testing: **NOT RUN**.

Before behavioral execution, SHA-256 inventory covered 448 existing files outside .git/__pycache__, including all 12 Memory files. No originals changed or disappeared during tests; final check also checks additions. The initial control checks/source reads preceded this baseline and performed no file writes. No fetch/pull/push/origin access, merge, tags or commit were used.

## H. Proposed Corrections

**Only proposals. No implementation authorized or performed.**

### H1. F01 — first priority, P1

Minimal safe direction: stop public `save()` from blindly persisting an externally stale snapshot. Keep the seven writers' Stage-1/2 mechanics. Two reviewable options:

1. Separate internal locked save of a fresh decorated mutation from external full-store save; require external save to match a persisted baseline/version and reject stale state under the existing shared lock.
2. Restrict/prohibit standalone full-store save as an administrative API; preserve internal decorated mutators through a private locked persistence method. External bulk replacement would need an explicit separate contract, not an accidental `save()` call.

Affected components: `Memory/ExpSM/Exp_CRUD.py`, public API documentation and targeted Stage-1/Stage-2 regression coverage. Shared transaction, receipt format and native APPLY need not be rewritten. A blind automatic merge is not sufficient: creates/updates/deletes and metrics/receipts have conflicting semantics. “Just re-read” is also insufficient if caller edits must be preserved.

Compatibility risk: callers that mutate `crud.data` and call save currently expect full replacement; rejection/separation changes this behavior. Nested decorated writes must remain reentrant and must not be rejected as stale after legitimate fresh-load mutations. Do not silently discard caller changes.

Required tests:

- Positive: fresh create/update/delete/conversion/counters still persist; intentional supported fresh bulk save succeeds if retained; v2 extension metadata and all receipts survive.
- Negative: A loads, B creates/updates/deletes, A saves → explicit conflict/refusal with exact current bytes unchanged; no misleading success; same and different record cases.
- Stage-2 regression: stale v2 save cannot delete any new receipt/index or revert native metrics; retry same event remains ALREADY_APPLIED, changed evidence remains EVENT_CONFLICT; a stale legacy snapshot cannot downgrade v2.
- Concurrent/restart: two objects/processes, nested locks, snapshot across reopen, concurrent native APPLY vs admin save, error/readback handling. Existing 43 targeted tests remain green; add behavioral coverage of public save rather than AST presence-only assertions.

### H2. Decisions before other fixes

F02/F03/F06 are not automatically license to apply a new universal policy. First agree whether `allow_draft_writes` includes review/status persistence, whether manifest allocation is allowed in safe_demo, and whether administrative CRUD stays outside profile control.

If draft reviews are covered, minimal later correction is policy propagation to both gates with a non-persisting review/blocked result when denied; test deny bytes unchanged with pre-existing drafts, permit review, and commit/update lifecycle regressions. W12/W13 custom combinations (commit=true, draft=false) require a separate decision about required bookkeeping.

If safe_demo is to become authoritative-read-only on any supplied root, explicitly revise the documented Outcome exception, pass policy to legacy feedback and add negative eligible-evidence tests plus positive legacy feedback tests. This changes current compatibility; do not quietly treat it as an already approved contract.

If manifest changes must be blocked, define a read-only registry/ephemeral ID or pre-provisioning workflow and test missing/default completion/new-name startup and ticks. Avoid silently losing stable IDs. Harden original-memory hash coverage to full file-name/byte inventory and run verifiers only through temporary roots; this improves evidence without rewriting persistence.

## I. Open Architectural Decisions

1. Does safe_demo promise only selected writer denials plus runner isolation, or prohibit every authoritative mutation on any supplied root? Current code/docs support the former; generic read-only claims are unsafe.
2. Is legacy Outcome active-mode feedback intentionally allowed on real Memory under draft_only? Existing documented exception permits the path; user approval is needed before future runtime policy tightening/integration.
3. Does draft write permission include rejecting/reviewing existing draft cards and commit/update bookkeeping? Should denial allow RAM-only reviews?
4. Is persistent PatternRegistry allocation/semantic enrichment permitted under each profile? Must missing/new manifest initialization fail, remain transient or use preallocated identifiers?
5. Are ExpSM/AKBSM/WL CRUD trusted administrative tools outside runtime authority, or should explicit separate administrative capabilities/root confinement be required? What authority permits full snapshot replacement?
6. Should native CREATE/APPLY have system-mode/review authority in addition to explicit flags when integrated? They currently are isolated explicit APIs, not automatically eligible under a future continuous loop.
7. Who owns integrity/version conflict handling for administrative full-store save? Is intentional destructive import ever allowed to replace receipt history, and under what separate contract?
8. Is a trusted temporary flag sufficient, or should approved demo/test entry points prove copied-root identity and whole-tree preservation? No filesystem sandbox is currently supplied by policy.
9. What cross-file guarantees are required for ExpSM + draft acknowledgements, AKBSM node + edge updates and technical manifests? Stage 1 is ExpSM-only.
10. Are pre-APPLY event loss and non-durable pending transitions acceptable, or is an outbox required before continuous Feedback? Receipts alone do not answer this.

RND-110 remains **OPEN**. Review of findings and a separate user decision are required before fixes or any next integration task.


## J. Final Local Verification

- Branch/HEAD unchanged: `main` / `441c2b26725f6a116a38dec5baed339f1ec38e20`.
- All 448 baseline files unchanged; original Memory: 12 files, zero changed/deleted/added files, no persistent-byte diff.
- Production source, existing tests/verifiers, AGENTS and contracts unchanged. Only added repository file: this document.
- Relative Markdown links validated against existing local targets.
- Disposable harness, result JSON, search inventory, baseline and demo log in `/tmp` removed after final verification; TemporaryDirectory fixtures cleaned up.
- `git diff --stat` empty for tracked files; `git status --short`: `?? docs/RND-110_memory_write_authority_audit.md`.
- AGENTS remains untracked/ignored through `.git/info/exclude`.
- No commit, corrections or transition to another RND task. **STOP FOR REVIEW; RND-110 OPEN.**


## K. F01 Remediation после review

Дата: 2026-11-06. По отдельному разрешению пользователя исправлен только F01. RND-110 **OPEN**, исправление ожидает review; commit не создан. Первоначальный аудит и воспроизведения A–J не переписаны под новый результат: там описано состояние до correction.

**Хронология correction:** K1–K5 фиксируют первый вариант исправления. Его финальный review завершился STOP из-за отдельного receipt-authority пробела и трёх stale verifier allowlists. Актуальное дополнение и результаты их исправления — K6 ниже.

### K1. Root cause и выбранное исправление

`ExpSMCRUD.save()` брал shared lock и читал authoritative format, но сохранял старое `self.data`. Сериализация файловых операций не делала старый снимок актуальным. Публичный save мог потерять записи/метрики/receipt history, оставаясь структурно корректным v2.

В [Exp_CRUD.py](../Memory/ExpSM/Exp_CRUD.py) добавлен optimistic whole-store freshness check под **существующей** Stage-1 блокировкой. Каждый экземпляр сохраняет независимую строковую JSON identity загруженного полного store (`_baseline`). Внешние изменения mutable `self.data` не изменяют baseline. JSON identity чувствительна к типам (например, true и 1 различаются), игнорирует порядок ключей/форматирование; не меняет canonical digest native Feedback.

`save()` под lock читает текущий complete store, сравнивает с baseline, строго валидирует candidate, а при текущем v2 требует сохранения **всего** receipt ledger без изменений, включая оба индекса, версии и содержимое receipts. Только затем вызывает прежний `write_complete_store(self.data)` и readback. После успешного readback baseline обновляется. Автоматического merge нет, shared transaction/receipt/event/digest/native writers не изменены.

Декоратор сохраняет прежний порядок: lock → fresh authoritative read в self.data → baseline этого fresh read → поддерживаемый CRUD method → вложенный save. Собственные изменения метода сравниваются с правильным baseline, а не с изменённым candidate. Это сохраняет reentrancy и работу всех 12 decorated mutators.

### K2. Публичный контракт и совместимость

| Случай | Новый результат |
| --- | --- |
| Fresh instance, intentional supported edits to crud.data, save | Сохранение через прежнюю transaction; successful readback обновляет self.data/baseline; возвращается None |
| Store изменился после загрузки, даже другой record ID | `ExpSMStaleSnapshotError`, подкласс ExpSMError; записи нет, текущие authoritative bytes и локальные правки остаются прежними |
| Fresh v2 candidate удаляет/изменяет ledger, индекс или receipt | `ExpSMReceiptIntegrityError` либо прежняя strict validation error для malformed candidate; записи нет |
| Fresh v2 save меняет обычный record, сохраняя ledger | Допускается; ledger и разрешённые extension metadata сохраняются |
| Stale legacy snapshot после появления v2 | Отказ по stale check; downgrade невозможен |
| Fresh v2 snapshot намеренно превращён в legacy | Отказ, candidate не записывается |
| Decorated create/update/delete/conversions/counters | Fresh-load под lock, поддерживаемые мутации продолжают работать в legacy/v2 |
| load() | Как прежде возвращает текущий snapshot; не заменяет self.data. Теперь явно документировано: также не обновляет baseline, поэтому нельзя незаметно «освежить» старые локальные правки одним чтением |
| Reopen/new ExpSMCRUD(path) | Загружает текущие self.data и независимый baseline; явный способ начать заново после конфликта |
| Pre-replace failure | Исключение наружу, прежние bytes; baseline не продвигается; проверенный pre-replace случай допускает повтор после устранения причины |
| Post-replace/readback failure | Исключение наружу; результат может быть неопределённым для caller. Baseline не обновляется без успешного readback; нет заявления retry-safe. Требуется прочитать authoritative состояние и осознанно восстановить работу |

Найденные реальные callers save — методы самого ExpSMCRUD. В runtime и других production компонентах прямых вызовов save не найдено. Репозиторий не содержит отдельного обещания безусловного replacement после внешних изменений; fresh editing API сохранён. Обычный save больше не служит инструментом редактирования receipt ledger. Отдельный небезопасный bypass не добавлен.

Unknown permitted envelope metadata и record fields проходят прежний complete-store механизм; native record format и версии сохранены. Сравнение касается загруженного нормализованного содержимого, не истории каждого промежуточного изменения файла или byte-formatting. Legacy top-level normalization не расширялась. Политики и доверенные административные полномочия из F02–F09 не изменены.

### K3. Новые тесты: red → green

Добавлен [verify_expsm_crud_save_authority.py](../tools/verify_expsm_crud_save_authority.py): **19 behavioral tests**, все writable stores — TemporaryDirectory. Вызываются реальные публичные CRUD/native writer APIs; private persistence helper не заменяет проверяемую операцию. Failure injection применяется только к OS replace/readback для проверки ошибок.

На неизменённой реализации из `git show HEAD:Memory/ExpSM/Exp_CRUD.py`, загруженной в отдельный in-process module, выполнены четыре тех же regression cases: stale create с другим ID, stale update, stale tombstone delete и stale v2 после нового native receipt. Результат **4 ожидаемых failures, 0 errors**: исключение конфликта отсутствовало. Ни исходные файлы, ни production Memory для этого эксперимента не подменялись. Первые черновые запуски тестов также выявили неполные synthetic legacy fixtures; fixtures исправлены под существующую strict validation, после чего выполнен указанный чистый red-прогон.

После correction проходят:

- Fresh save, последовательные save с обновлением baseline, независимость baseline от внешних правок self.data, read-only load/reopen.
- Stale create/update/tombstone/different IDs; отказ не меняет authoritative bytes и не удаляет локальные правки.
- Stale legacy→v2 и stale v2→новый receipt; ledger сохраняется, retry=ALREADY_APPLIED, changed-evidence=EVENT_CONFLICT.
- Fresh tampering: удаление ledger, очистка обоих индексов, изменение digest, удаление occurrence index, изменение receipt timestamp, подмена типа версии; отказ без записи.
- Fresh v2 legitimate save, unknown extension metadata, ledger preservation и downgrade refusal.
- Все 12 decorated mutations, conversions с tombstones, nested locking и обновление baseline в legacy и v2.
- Concurrent public whole-store saves: ровно один success и один conflict, подтверждённая запись сохраняется. Concurrent decorated counters: 24 подтверждённых увеличения сохранены.
- Pre-replace failure: exact bytes и cleanup temporary file; успешный retry именно после известного pre-replace отказа.
- Post-replace readback failure: запись уже могла состояться, исключение, stale отказ на слепой повтор, явный reopen.
- Strict invalid authoritative JSON и invalid local candidate остаются незаписываемыми.

### K4. Regression / writer matrix

```text
python -B -m unittest -v tools.verify_expsm_crud_save_authority \
  tools.verify_expsm_persistence_stage1 \
  tools.verify_nfp_native_feedback_replay_idempotency \
  tools.verify_nfp_native_feedback_apply \
  tools.verify_nfp_expsm_policy_gated_create
```

**PASS — 62 tests, 2.181 s, exit 0.** Разбивка: новые CRUD 19/19; Stage 1 9/9; Stage 2 15/15; native Feedback APPLY 11/11; native CREATE 8/8.

| Writer family | Проверка / результат |
| --- | --- |
| NFPExpSMCreateWriter | CREATE 8/8 + Stage-2 v2-preservation family test — PASS |
| NFPFeedbackApplyWriter | APPLY 11/11 + replay 15/15 + новые stale receipt/retry tests — PASS |
| ExpSMCommitWriter | Stage-1 AST/transaction checks + Stage-2 `test_v2_receipts_survive_other_authoritative_writer_families` actual permitted commit — PASS |
| ExpSMUpdateWriter | Те же проверки + actual permitted update с сохранением receipts — PASS |
| ValueFeedbackUpdateWriter | Те же проверки + отдельный `python -B tools/verify_value_feedback_update_writer.py` — PASS; bounded links, semantic/technical fields unchanged, duplicate skipped |
| ExpSMOutcomeFeedback | Те же проверки + actual eligible active-mode feedback с v2 receipts — PASS; policy exception не изменена |
| ExpSMCRUD | Новые 19/19 + shared Stage-1 decorator/concurrency и Stage-2 family preservation — PASS |

Stage-2 historical duplicate после более позднего legitimate update и cross-process duplicate/conflict tests выполнены и прошли. Stage-1 spawned-process same/different record update tests также прошли. Это не новая гарантия crash durability для всех остальных хранилищ.

`python -B tools/verify_nfp_native_feedback_replay_idempotency_design.py`: PASS. Его full-diff allowlist уже разрешает Exp_CRUD.py и сам verifier. Добавлены только две exact entries: новый CRUD verifier и ранее untracked audit/remediation документ. Wildcard и ослабления поведенческих assertions не добавлены.

### K5. Оставшиеся ограничения и финальное состояние

- F01 correction реализован и проверен, но ожидает review; первоначальная находка сохранена как историческая.
- F02–F09/FP не объявляются исправленными. Нет новых policy gates, изменений runtime, других writers или ledger semantics.
- Baseline сравнивает содержимое whole store и намеренно отклоняет непересекающиеся stale edits; merge отсутствует. Нет универсальной защиты от внешних программ, которые игнорируют transaction, или намеренной записи через другие административные primitives.
- После неопределённого post-replace состояния требуется reconciliation/reopen; успешный повтор без проверки не обещан.
- Изменены только Exp_CRUD.py, новый targeted verifier, две exact allowlist entries в design verifier и данный audit/remediation документ.
- Production Memory data: 9 файлов данных/manifest unchanged; три CRUD source files внутри Memory проверены отдельно — изменён только разрешённый Exp_CRUD.py. Новых файлов/lock files в исходной Memory нет.
- Исходный baseline содержит 449 файлов вне .git/__pycache__. Помимо разрешённого исправления, allowlist и дополнения аудита, исходные файлы неизменны; единственный новый файл correction — targeted verifier.
- Git main/HEAD сохранены; AGENTS ignored, не отслеживается, bytes неизменны. Diff проверен; temporary run logs/baseline удалены.
- **STOP FOR REVIEW. RND-110 OPEN. Commit отсутствует.**


### K6. Receipt authority и согласование четырёх verifier contracts

Дата: 2026-11-06. Исправляются только два замечания предыдущего review в области F01: P1 receipt authority и P2 stale full-diff allowlists. F02–F09 остаются открытыми/зафиксированными; их policy semantics не изменены.

**Причина P1 независима от первоначального stale defect.** Первый correction сравнивал store с baseline корректно, но проверял ledger equality только при уже существующем authoritative v2. Fresh legacy snapshot поэтому мог сохранить structurally valid v2 с receipt, которое не было применено в этом store. Review воспроизвёл hits 3→3 и первый APPLY=ALREADY_APPLIED. Lock, свежий baseline и структурная validation не доказывают происхождение receipt.

Текущая граница public save:

- Сохранять разрешённые обычные правки можно только в текущей authoritative форме store.
- Standalone save не выполняет legacy→v2, даже с пустым ledger; не выполняет v2→legacy.
- Проверка format/ledger теперь безусловная, до authoritative replacement. Для ledger сравниваются наличие поля и полное type-sensitive содержимое. Нельзя внедрить receipts в legacy как неверсированное поле, которое нормализация затем скрывает; отсутствующий store также не даёт полномочий создавать receipts.
- Existing v2 сохраняет точный ledger/index: нельзя добавлять, удалять или изменять receipts, версии и обязательные indexes. Структурная validation сохраняется, но не заменяет проверку полномочий.
- Отказ — ExpSMReceiptIntegrityError либо strict-validation exception для malformed candidate; bytes и локальные правки неизменны, baseline не продвигается. Stale check выполняется первым и сохраняет прежний ExpSMStaleSnapshotError.
- Законная migration legacy→v2 с atomic metric+receipt остаётся у существующего native Feedback APPLY. Второй API создания receipts не добавлен.

Исследованные boundary/replay documents не требуют standalone CRUD migration. Fresh legacy editing сохранён без миграции, fresh v2 editing — с неизменным ledger и разрешённой extension metadata. Общая transaction, native APPLY/CREATE, другие writers и event/digest/TargetCore semantics не изменены.

**Behavioral evidence.** Добавлено пять тестов (включая subtests), всего CRUD verifier теперь **24 tests**. До дополнительного исправления целевой прогон подтвердил отсутствие отказа для legacy migration с receipt, empty-v2 migration, неверсированного ledger и отсутствующего store; существующая v2 insertion protection уже работала. После исправления все 24 tests проходят.

Новые tests генерируют receipts реальным production APPLY в отдельном временном donor store. Donor receipt намеренно не считается доказательством применения события в target. Проверяются реальные public target save и APPLY:

| Проверка | Результат |
| --- | --- |
| Fresh legacy + импорт valid receipt через v2 | PASS: отказ, exact target bytes/local edits/baseline сохранены |
| Затем настоящий target APPLY того же события | PASS: UPDATED, hits увеличены на 1, target мигрирует в v2 |
| Повтор / changed evidence того же события | PASS: ALREADY_APPLIED / EVENT_CONFLICT |
| Fresh legacy + empty v2 ledger | PASS: migration через save запрещена |
| Fresh legacy + ledger без store_schema_version | PASS: поле не может скрыть receipt от authority check |
| Missing store + versioned/unversioned receipt payload | PASS: отказ, authoritative file остаётся отсутствующим; локальные правки/baseline сохранены |
| Existing v2 + новый receipt от donor | PASS: отказ; настоящий target APPLY нового события затем UPDATED, повтор ALREADY_APPLIED |
| Existing v2 deletion/mutation/index alteration | PASS: прежние tampering tests, refusal без изменения bytes/baseline |
| Fresh legacy save, последовательный и повторный no-op save | PASS: после отказа baseline остаётся usable; формат legacy сохранён |
| Reopen/decorated mutation после legitimate migration | PASS: current v2 baseline, ledger не теряется, historical duplicate ALREADY_APPLIED |
| Исходные stale/lifecycle/nested/concurrency/error tests | PASS; не ослаблялись |

**Реальные script entry points выполнены:**

```text
python -B tools/verify_expsm_crud_save_authority.py                       # 24/24
python -B tools/verify_expsm_persistence_stage1.py                       # 9/9
python -B tools/verify_nfp_native_feedback_replay_idempotency.py         # 15/15
python -B tools/verify_nfp_native_feedback_apply.py                      # 11/11
python -B tools/verify_nfp_expsm_policy_gated_create.py                   # 8/8
python -B tools/verify_value_feedback_update_writer.py                  # PASS
python -B tools/verify_nfp_expsm_operational_retrieval_design.py          # PASS
python -B tools/verify_nfp_action_materialization_guarded_execution_design.py # PASS
python -B tools/verify_nfp_native_feedback_design.py                     # PASS
python -B tools/verify_nfp_native_feedback_replay_idempotency_design.py   # PASS
```

Итого **67/67 behavioral unittest tests**, дополнительно value writer script и четыре design contracts — PASS. Все potentially mutating stores временные. Stage-2 historical duplicate, cross-process duplicate/conflict, metric+receipt atomicity и receipt-preservation across seven writer families повторно прошли; Stage-1 shared locks/fresh-load ordering/reentrancy и spawned-process tests прошли. Все 12 decorated mutations сохранены в legacy/v2; общий baseline остаётся одной заменяемой immutable строкой, не историей snapshots. Неопределённый post-replace результат по-прежнему не объявляется retry-safe.

**P2 / full-diff meta-audit.** В operational retrieval, guarded execution и native Feedback verifier добавлены только exact paths `tools/verify_expsm_crud_save_authority.py` и `docs/RND-110_memory_write_authority_audit.md`. Replay verifier уже содержит эти две записи из первого correction. Production contract assertions не изменялись и проверки не удалялись.

Для всех четырёх contracts выполнен meta-audit: их actual changed-path collectors возвращают ровно согласованные семь рабочих файлов; current paths принимаются; добавленный только in-memory неизвестный путь `rnd110_unapproved_change.py` даёт failure с этим путём в диагностике; wildcard entries отсутствуют. Никакие пробные изменения исходных файлов для meta-audit не делались.

Текущие allowlists содержат 54/50/44/36 exact entries соответственно. Они исторически широкие: paths transaction/APPLY уже разрешены и их synthetic changed-path set принимается при неизменном source. Это существующее ограничение full-diff guards, а не доказательство безопасности произвольного изменения этих модулей. Их списки не расширялись другими historical paths. Фактический diff отдельно проверен: запрещённые production components не изменены.

**Финальная область и ограничения.** Рабочие изменения: Exp_CRUD.py, CRUD verifier, четыре exact design allowlist updates и audit document — семь файлов. В этом продолжении replay verifier дополнительно не менялся. Первоначальная находка F01 и первый correction сохранены как исторические свидетельства; K6 описывает актуальную границу.

Данные original Memory (9 data/manifest files) побайтово совпадают с HEAD; hash inventory не изменён: `6db294d8169e8c809d3c66eec7d0b3a57439180e8f8544e83d3cb14bd48d2e4a`. Новых production lock files/временных файлов нет. AGENTS остаётся ignored/untracked и неизменным. Shared transaction и остальные шесть writer implementations не изменены. Branch main/HEAD сохранены; diff check и относительные ссылки проверены.

Ограничения административных полномочий, другие persistence domains и F02–F09 остаются вне исправления. Нет универсального filesystem sandbox или автоматического merge; intentional record edits всё ещё относятся к доверенному административному API. После проверок — **STOP FOR REVIEW, RND-110 OPEN, без commit**.


### K7. Closure summary

RND-110 **CLOSED** по отдельному решению пользователя после принятого review.

- F01 stale snapshot replacement — **FIXED**.
- Дополнительный P1 receipt-authority defect — **FIXED**.
- Public save сохраняет текущую форму store, не создаёт и не меняет существующий receipt ledger/index и не выполняет legacy→v2 migration.
- Native Feedback APPLY сохраняет законную legacy→v2 migration с atomic metric+receipt.
- **67/67 behavioral tests — PASS**; четыре full-diff design verifiers и проверка rejection неизвестного пути — **PASS**.
- Stage-1/Stage-2 invariants сохранены в проверенной области, включая stale conflicts, locking/reentrancy, receipt preservation и restart/retry idempotency.
- F02–F09 остаются нерешёнными findings для будущих отдельных задач. Их исправление и новая runtime integration не входят в закрытие RND-110.
- safe_demo не объявляется универсально read-only; полная регрессия проекта не заявляется.

Исходные свидетельства A–J и результаты K1–K6 сохранены. После последнего успешного прогона implementation/tests не менялись: closure изменяет только документацию. Разрешён один локальный commit семи согласованных файлов; без remote contact, merge и tags. Новые задачи автоматически не начинаются.
