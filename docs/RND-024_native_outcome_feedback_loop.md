# RND-024 — Native Outcome Evaluation & Feedback Loop

2026-11-09. **CLOSED — ACCEPTED FOR CLOSURE.**
Architecture review и final diagnostic integrity review приняты.
Окончательные результаты и границы доказательства — в разделе «Final closure».
История first pass, двух этапов corrections и reviews сохранена ниже;
исторические OPEN/CORRECTION REQUIRED не являются текущим статусом.

## История first pass и corrections

Исторический старт, 2026-11-07: **IMPLEMENTATION FIRST PASS — OPEN FOR REVIEW**.
Затем выполнены targeted P2/P3 и bounded diagnostic integrity corrections;
контрольная точка до final review: **OPEN FOR TARGETED REVIEW**, не CLOSED.

Исходная контрольная точка: `main`, HEAD
`07c74b8b0f2e07925af633f962f7018d3d71a358`. LOCAL ONLY; без commits,
remote, tags. Исходный untracked `sf4.py` в корне сохранён.

## Audit gap и feasibility gate

RND-024/A завершился INTEGRATION BLOCKED для неизменной fixture RND-023 `(1,2)`.
Из column 0 right повторяет изученный эффект; из column 1 right упирается
в границу, но context similarity 0 исключает запись из exact retrieval.
Даже при ослабленном retrieval исходная activation .225 ниже встроенного .35.
Поэтому настоящий MISS через полный operational pipeline там не получался.

Последующий запрос явно разрешил новую isolated acquisition fixture `(1,3)`
на существующем `SyntheticClosedLoopVisualWorld`, без изменения RND-023.
Предварительный gate выполнен отдельно в `/tmp` **до создания implementation**:
3 native exploratory actions right/left/right; все 3 retained transitions admitted;
support групп 2/1; один authorized CREATE, CREATED, CONFIRMED_PERSISTED.
В новых control sessions acquired source `1` выбрался из columns 0 и 1;
настоящие actual deltas дали evaluator HIT и MISS соответственно. Gate **PASS**.

Начальная позиция задаётся публичным constructor API `initial_column` до создания
session, selection и occurrence. Hidden state после action не меняется.

Все experimental parameters объявлены заранее в scenario:

- world `(1,3)`, training column 0, commands `(0,1)` / `(1,0)`;
- retrieval threshold `1/3`, agreement threshold `.75`;
- основной selector `.35`; отдельное sensitivity condition `.4`;
- неизменная production activation, включая `MIN_MATCH_SCORE=.35`;
- training 4 ticks / 3 intents / 3 actions; control 2 ticks / максимум 1 action;
- ShortMemory 8 entries / age 10; delivery journal 128;
- один acquired source, один evaluator result, максимум один APPLY и reconciliation.

## Реальный путь и provenance

Driver/owner: `scenarios/native_outcome_feedback_loop.py`.
Verifier: `tools/verify_native_outcome_feedback_loop.py`.

```text
empty temporary ExpSM
 → RND-022 exploration in NativeDeliverySession
 → existing guarded coordinator / transducer / owned-world apply
 → next-tick owned-world snapshot / native delivery / ShortMemory
 → RND-021 BoundedNativeAcquisition.admit (ALL retained transitions)
 → seal / full-set conflict check / supported proposal (support=2)
 → explicit authorized CREATE / fresh confirmed readback
 → independent store copies / fresh non-exploratory sessions
 → retrieve / activate_native / select_native / coordinator.execute
 → one physical apply / real retained T+1
 → NFPFeedbackEvaluator.evaluate
 → NFPFeedbackApplyWriter.apply under mutating_memory policy
 → fresh authoritative record + receipt readback
 → new retriever / activation / selector in identical initial context
```

No manually created training experience, transition, expected effect or feedback
classification. Existing builder initializes hits/misses=0 and
confidence/repeatability=.5; support does not raise operational confidence.
Observed association remains provisional, not an assertion of exclusive causation.

`acquire()` returns the confirmed record/store snapshot, actual support counts and
all three bounded `ExploratoryAcquisitionProvenance` projections. No session/world
reference survives in that fixture. RND-023 code and closed contracts are unchanged.

`FeedbackEpisode.observe()` observes real production calls with temporary wrappers;
return objects are never substituted in positive episodes. It binds exact retrieved
candidate → activation ID → selected request → genuine execution result. Source ID,
TargetCore and expected effect must match the persisted acquired record. The bound
physical signal must be the execution's actual signal and match the selected action.

Actual authority requires the exact retained transition object also present as the
session's completed recent transition, exact before/action/after identities,
pending transition ID, occurrence UUID, action tick and immediate T+1. Both windows
must have their owned native delivery events; the consequence event must carry the
same occurrence. Payload retransduction must reproduce the admitted sensory frame.
Timing alone does not establish provenance. Missing journal/retention fails closed.

The existing evaluator extracts actual through `ObservedEffectExtractor` and uses
`NativePredictedObservedEffectComparator`; the owner never decides HIT/MISS itself.
Only its internally bound evaluation can reach its `apply()` method, which accepts
no external evidence. This is trusted serialized ownership, not authentication of
arbitrary Python objects or protection from coordinated runtime tampering.

## F0 / F1 / F2: actual results

All conditions use independent stores and new worlds/managers/registries/retrievers/
activation/selectors/coordinators. Exploration is OFF in every control. Each selected
action is right and initially has source `1`; every action has a new UUID distinct
from all training occurrences. Each physical apply has real next-tick observation.

| Episode | Start column | Actual delta | Effect similarity | Evaluator | APPLY |
|---|---:|---|---:|---|---|
| F0-column0 | 0 | `(-1,+1,0)` | 1 | HIT | not called |
| F0-column1 | 1 | `(0,-1,+1)` | .3333333333 | MISS | not called |
| F1 | 0 | `(-1,+1,0)` | 1 | HIT | UPDATED |
| F2 | 1 | `(0,-1,+1)` | .3333333333 | MISS | UPDATED |

Expected effect in all cases is the acquired `(-1,+1,0)`. F0 may evaluate for
diagnostics but never invokes the writer: store bytes and receipt ledger remain
unchanged. F0-column1 is the matched no-feedback baseline for F2.

| Persisted record | hits | misses | confidence | repeatability |
|---|---:|---:|---:|---:|
| acquired / both F0 | 0 | 0 | .500 | .500 |
| F1 after APPLY | 1 | 0 | .382 | .425 |
| F2 after APPLY | 0 | 1 | .375 | .425 |

Native Stage 2's existing smoothing makes confidence decline even after this first
HIT: the low-evidence target is below the initial .5 prior. This is the actual
formula, not a manually imposed reward. Only hits or misses, confidence,
repeatability and updated timestamp change inside the record; context/action/effect
and acquisition provenance remain unchanged. Each APPLY also persists one receipt.

## APPLY, reconciliation, replay и uncertainty

F1/F2 each invoke the existing writer once under an explicit temporary
`mutating_memory` policy. UPDATED already includes writer readback. The owner then
performs a separate fresh `ExpSMStoreTransaction.load_state_strict()` read and
checks exact intended record, event key, evidence digest and occurrence index.
This is authoritative success readback; the recovery API is only applicable to
READBACK_FAILED and is not artificially invoked for success.

On READBACK_FAILED the owner calls existing
`reconcile_nfp_feedback_readback_failure()` once: lost acknowledgement reconciles
to RECONCILED_APPLIED; corrupted storage yields RECONCILIATION_CONFLICT. Neither
causes APPLY retry. Denial, stale core, missing evidence, guard refusal and uncertain
execution also cannot promote another action or feedback attempt.

Explicit negative replay probes reopen the existing writer: identical evidence
returns ALREADY_APPLIED without increments; altered evidence or reattributing the
same occurrence to another source returns EVENT_CONFLICT. These intentional probes
are outside the owner's one-attempt API, not positive-path retries.

The audit's directory-fsync edge was reproduced: after atomic replace an OSError
returns WRITE_FAILED with `retry_safe=True`, although metrics and receipt already
exist. The owner instead records `persistence_uncertain` and never retries. Existing
reconciliation rejects WRITE_FAILED; the owner does not relabel the result or
implement another recovery engine. A diagnostic strict read in the negative test
establishes the injected case's bytes, but does not turn WRITE_FAILED into a general
retry authorization. Pre-replace WRITE_FAILED is conservatively terminal as well.

Exceptions retain their original identity/traceback, with a bounded first-cause
diagnostic and terminal owner state. APPLY attempt is latched before writer entry.

## Post-feedback A/B/C/D

Fresh post sessions read the persisted store into new production components with
the same external initial context, initial world state, configuration and guard.
There are no competitor records. The cognitive record's feedback fields and
timestamp, plus transactional receipt metadata, are the only store changes.

| Condition | A: metrics | B: activation before → after | C: selected source | D: physical action |
|---|---|---|---|---|
| F0 column0, selector .35 | unchanged | .775 → .775 | `1 → 1` | right → right |
| F0 column1, selector .35 | unchanged | .4083333333 → same | `1 → 1` | right → right |
| F1, selector .35 | changed | .775 → .7568166667 | `1 → 1` | right → right |
| F2, selector .35 | changed | .4083333333 → .3554166667 | `1 → 1` | right → right |
| F0 column1, fixed .4 | unchanged | .4083333333 → same | `1 → 1` | right → right |
| F2, fixed .4 | changed | .4083333333 → .3554166667 | `1 → none` | right → no action |

The .4 sensitivity condition was declared before feedback, independently of the
default .35 result. Thresholds/weights were never tuned after observing outcomes.
Default selection does not change. Sensitivity demonstrates suppression of this
one remembered choice, not discovery of a better alternative or utility learning.

## Verification, safety, limitations — first pass до correction

All Python launches: `PYTHONDONTWRITEBYTECODE=1 python -B`, including regression
parent processes and their inherited multiprocessing children. New test fixtures
are exclusively `/tmp`; every regression suite ran in a fresh validation copy.

| Verifier | Unique unittest PASS |
|---|---:|
| native_outcome_feedback_loop (new) | 23 |
| first_native_acquired_experience_loop | 22 |
| bounded_native_acquisition | 40 |
| synthetic_exploratory_bootstrap | 41 |
| nfp_native_feedback_evaluation | 15 |
| nfp_native_feedback_apply | 11 |
| nfp_native_feedback_replay_idempotency | 15 |
| nfp_expsm_operational_retrieval | 5 |
| nfp_remembered_action_guarded_execution | 8 |
| nfp_expsm_policy_gated_create | 8 |
| expsm_persistence_stage1 | 9 |
| persistent_nfp_expsm_representation | 10 |
| short_memory_expsm_evaluation | 10 |
| **Total** | **217** |

Repeated targeted runs are not added. Actual current RND-023 suite has 22 tests;
the older document's historical 10-test count is not reused. Separate
`scoring_selection_semantics` script PASS. Stage 1 AST audit: 7 writers, 7 mutation
paths, zero direct-write/transaction/preflight/store-order violations.

New negative coverage: missing actual T+1; wrong source/occurrence/prediction/core;
unselected activation; copied or inconsistent actual transition; missing owned
delivery provenance; guard denial; physical mutation with lost acknowledgement;
policy denial; duplicate/conflicting events; stale core at writer; READBACK_FAILED;
unresolved storage; pre/post-replace WRITE_FAILED; original APPLY/reconciliation/
observation exceptions; session release before/after binding; retention expiry;
single-call budgets; nonisolated paths and undeclared thresholds.

Substrate remains the known **FAIL**: runtime imports in
`clc/runtime/native_bounded_delivery.py`, `clc/runtime/native_heart_session.py`,
`clc/runtime/native_session.py`. No production/runtime edits or new violators.

Logs: `/tmp/rnd024-target.log`; regression copies/logs/results:
`/tmp/rnd024-validation-4ihg8or0`. Whole-checkout pre-edit SHA-256/file/directory
inventory: `/tmp/rnd024-baseline.json`; final comparison:
`/tmp/rnd024-final-safety.json`. All 12 Production Memory files and directories,
weights, Stage 1/2, 119 baseline ignored `.pyc` and root `sf4.py` remain unchanged.
No new Memory directory, lock, manifest, bytecode or service file in checkout.
Syntax AST and whitespace checks PASS; index untouched.

Only the following three new files belong to RND-024:

- `scenarios/native_outcome_feedback_loop.py`;
- `tools/verify_native_outcome_feedback_loop.py`;
- `docs/RND-024_native_outcome_feedback_loop.md`.

No new production contract, evaluator, writer, schema, world implementation or
automatic Heart hook. The owner is finite, synchronous and trusted; callbacks
cannot be preempted, receipt ledger growth is Stage 2's existing unbounded contract,
and durable restart recovery for the experiment owner is not implemented. Acquired
association, feedback reliability correction, activation and choice are separate
claims. Reward/utility learning and production publication remain outside scope.

**STOP FOR REVIEW — FIRST PASS, not closure.**

## Targeted correction — exception safety и verifier portability

2026-11-07. **CORRECTION COMPLETE / OPEN FOR TARGETED REVIEW.**
RND-024 остаётся FIRST PASS, не CLOSED. HEAD и scope прежние.

### P2: primary exception и terminal state

Review воспроизвёл потерю первичного исключения: в exception handlers `observe()`
и `apply()` вызывался незащищённый `str(exc)`. Если `__str__` выбрасывал вторичную
ошибку, наружу выходил RuntimeError вместо исходного exception object. В observation
ветви state оставался `observing`, reason пустой. После post-replace interruption
persisted misses уже мог быть 1, state был `persistence_uncertain`, но reason также
оставался пустым. Double APPLY не наблюдался.

Исправление ограничено диагностикой isolated owner:

1. Handler сначала фиксирует `stopped` либо `persistence_uncertain`.
2. Если первой причины ещё нет, фиксирует постоянную bounded category:
   `observation_exception` либо `persistence_exception`.
3. Только затем пытается получить human-readable text через `_exception_reason()`.
   Имя типа и `str(exc)` находятся внутри защищённой границы; при отказе остаётся
   постоянный fallback. Полученный текст ограничен 256 символами.
4. Сам вызов helper дополнительно защищён: даже его MemoryError/interrupt не
   заменяет исходный failure. Handler завершает bare `raise` первичного исключения.
5. Уже установленная первая reason не перезаписывается и не форматируется заново.

Четыре новых постоянных unittest methods с несколькими fault arms проверяют:

- неисправный `__str__` при sensor failure до физического действия и при evaluator
  failure после настоящего retained T+1;
- неисправный `__str__` в `post_replace_readback` после реального writer replace;
- ошибку existing reconciliation, включая сохранение уже установленной первой reason;
- отказ самого diagnostic helper на observation/APPLY/reconciliation boundaries.

Во всех случаях проверены identity исходного exception object, присутствие
первичного raise frame в traceback, отсутствие `__str__` frames во внешнем
traceback, непустая bounded reason и terminal state **в момент начала диагностики**.
Повторные `observe/apply` не вызывают session.run, physical action или writer.
Owner не хранит raw exception/traceback в долгоживущем состоянии.

Post-replace fault использует negative-only BaseException subclass, который не
перехватывается существующими writer catches OSError/ValueError. Существующий
writer действительно меняет запись; отдельный `authoritative_record()` через
`ExpSMStoreTransaction.load_state_strict()` подтверждает misses=1 и один receipt.
Это диагностическое чтение injected case, не разрешение retry: owner остаётся
`persistence_uncertain`, result/readback/recovery не объявляются успешными.
READBACK_FAILED и read-only reconciliation сохраняют прежнюю production семантику.
WRITE_FAILED edge и запрет blind retry не изменены.

### P3: проверка реального path invariant

Раньше тест считал `ROOT / 'forbidden-rnd024'` запрещённым. В validation checkout
под `/tmp` это допустимый temporary descendant: review получил 22 PASS / 1 FAIL.

Теперь отрицательные пути — сам resolved temporary root и его parent. Они нарушают
действующий invariant «dedicated subdirectory strictly inside temporary root»
независимо от расположения checkout. Spies на `Path.mkdir/write_text` подтверждают
отказ до записи; forbidden directories/files не создаются. Дополнительно genuine
valid temporary descendant проходит remembered execution. Проверка containment
зависимостей owner сохранена. Production validators не менялись.

### Проверки correction

Исходные observation/post-replace reproductions и path case после исправлений:
3 targeted methods PASS, затем включены в полный suite без повторного подсчёта.

| Текущий запуск | Результат |
|---|---|
| Полный RND-024 verifier, исходный checkout | **27 PASS** |
| Тот же verifier, свежая validation copy под `/tmp` | **27 PASS** |
| Те же 12 regression suites, что в first-pass таблице | **194 PASS** |
| **Уникальные unittest methods текущего набора** | **221 PASS** |
| Scoring/selection script | PASS, отдельно от unittest count |
| Substrate | **известный baseline FAIL**, те же три runtime paths |

Два расположения и предварительные targeted runs не суммируются. Исторические
217 PASS не добавляются к текущим 221. Stage 1 AST audit сохраняет 7 writers,
7 mutation paths и ноль direct-write/transaction/preflight/store-order violations.

F0-column0/column1 сохраняют HIT/MISS без writer и точные store bytes/ledger.
F1 даёт persisted hits/misses=1/0, confidence/repeatability=.382/.425;
F2 — 0/1 и .375/.425. Genuine acquisition/source/occurrence binding сохранён.
Уровни A/B/C/D прежние: metrics и activation меняются; при .35 source/right
сохраняются; при заранее фиксированном .4 MISS даёт source `1 → none`,
right → no action. Matched F0 сохраняет выбор. Параметры, world dynamics,
expected/actual/evaluation и policy semantics не менялись.

Все Python launches и subprocesses: `PYTHONDONTWRITEBYTECODE=1 python -B`;
writable fixtures/stores/logs только во временной изоляции. Логи:
`/tmp/rnd024-correction-reproductions.log`, `/tmp/rnd024-correction-target.log`,
validation copies/results `/tmp/rnd024-correction-validation-thz85opa`.

Pre-edit correction inventory: `/tmp/rnd024-correction-baseline.json`;
финальное сравнение: `/tmp/rnd024-correction-final-safety.json`.
Изменены только три RND-024 файла, перечисленные выше; все прочие files/directories
совпадают с pre-edit SHA-256/inventory. Все 12 Production Memory files и каталоги,
weights, Stage 1/2, 119 ignored `.pyc` и корневой `sf4.py` неизменны. Нет новых
checkout lock/cache/manifest/service files; syntax/whitespace PASS; staging пуст.
Production evaluator/writer, selector, acquisition, world и RND-021/022/023 не менялись.

Ограничения first pass сохранены: trusted serialized isolated owner, отсутствие
preemption для произвольного formatting/callback, отсутствие durable owner restart
recovery и utility/reward learning. Substrate FAIL не исправлялся. Ни commits,
ни remote/tags, ни следующего этапа.

**STOP FOR TARGETED REVIEW.**

## Bounded diagnostic integrity — дополнительная P2 correction

2026-11-07. **OPEN FOR TARGETED REVIEW.** Этот раздел заменяет предыдущий
correction checkpoint в части текущих diagnostics и PASS count; CLOSED не заявлен.

### Reproduction и причина

Повторный review обнаружил, что `str(exc)` может вернуть subclass `str`.
Его `__radd__` перехватывает сложение с label, а `__getitem__` при срезе возвращает
сам exception. До этой correction `_exception_reason()` действительно возвращал
exception вместо строки. Owner.reason сохранял traceback и через него session/world:
observation state был `stopped`, post-replace state — `persistence_uncertain`,
persisted misses=1. Primary identity сохранялась, retries не было, но diagnostics
нарушали bounded scalar и lifetime contract. Reproduction повторён до исправления.

### Exact diagnostic boundary и аудит записей

Добавлен локальный `_bounded_reason(value, fallback)`:

- exact `type(value) is str` проверяется до bool/len/slice/concatenation;
- fallback отдельно проверяется на exact built-in str и длину 1..256;
- недопустимый type/empty value заменяется безопасным constant fallback;
- oversized exact str обрезается до 256; subclass не конвертируется повторно.

`_exception_reason()` отдельно проверяет exception type name и результат единственного
`str(exc)` до их сложения. Все компоненты и final result проходят scalar boundary;
неисправное форматирование по-прежнему оставляет constant fallback. Внешние handlers
повторно проверяют результат helper перед сохранением: даже ошибочный helper,
вернувший exception/subclass/empty/oversized value, не может сохранить raw object.
Terminal state и fallback фиксируются до optional formatting; bare raise и первая
reason сохранены. Сам первоначальный empty sentinel означает отсутствие диагностики,
а не terminal error reason.

Аудит всех owner assignments охватил `_stop`, execution-status label, observation
handler, APPLY handler, WRITE_FAILED и ветви reconciliation/result. `_stop` больше
не делает срез непроверенного значения. Для ineligible evaluator result теперь
устанавливается постоянная непустая STOP reason. WRITE_FAILED сохраняет первую
reason, если она уже существует.

При этом аудите воспроизведён смежный diagnostic snapshot path: production writer
перехватывает negative-only OSError subclass, чей `__str__` возвращает подкласс
строки с ссылкой на exception. Его result.reason также мог удерживать traceback.
Аналогична diagnostic reason у recovery result. Owner теперь сохраняет локальные
dataclass projections с bounded exact-str reason для writer/reconciliation results.
**Только diagnostic text проходит эту границу**: authority/status, records,
event key/digest, receipt, retry semantics и authoritative reconciliation outcome
сохранены. Production writer/reconciler не менялись; другого transaction/recovery
engine нет. Diagnostic read не разрешает retry после uncertain persistence.

### Постоянные tests и GC

Добавлены шесть unittest methods с несколькими arms:

1. Исходный malicious subclass на observation и post-replace APPLY: primary identity
   и primary traceback сохранены, subclass operators не вызываются, reason exact str.
2. GC/weakref проверки observation/APPLY/reconciliation: после выхода из error scope
   и освобождения test-only injection callbacks exception, 64-KiB payload,
   session и world собираются. Сам тест не возвращает primary/traceback наружу.
3. Components: обычный str, subclasses, arbitrary objects, empty/oversized values,
   invalid fallback и subclass exception type name; на untrusted components нет
   dispatch bool/len/add/radd/getitem.
4. Ошибочные return values diagnostic helper на всех трёх exception boundaries.
5. `_stop` scalar boundary и сохранение первой reason.
6. Writer/reconciliation diagnostic snapshots с malicious OSError text, включая
   GC/weakref проверку exception/payload/session/world после освобождения injector.

Общие assertions усилены exact `type(owner.reason) is str` и длиной 1..256.
Сохранились previous broken-`__str__`, failing-helper и reconciliation tests.
Post-replace arm подтверждает persisted record/receipt существующим strict readback,
но owner остаётся `persistence_uncertain`. Повторные session/action/APPLY запрещены.
Ни raw exception, ни traceback не сохраняются owner в diagnostics или snapshots.

### Текущий validation checkpoint

| Запуск | Результат |
|---|---|
| Original reproduction / retention / components, предварительный targeted run | 3 PASS, входят в full suite |
| Полный RND-024 verifier из исходного checkout | **33 PASS** |
| Тот же verifier из свежей validation copy под `/tmp` | **33 PASS** |
| Те же 12 regression suites | **194 PASS** |
| **Уникальные unittest methods** | **227 PASS** |
| Scoring/selection script | PASS отдельно |
| Substrate | прежний baseline **FAIL**, новых violators нет |

Исторические 217/221, повторный full verifier и предварительные targeted tests
не прибавляются. Stage 1/2, P3 containment и portability неизменны.

Feedback loop сохранён: F0 column0/column1 не вызывает writer и сохраняет bytes/
ledger; F1 — HIT, hits/misses=1/0, confidence/repeatability=.382/.425;
F2 — MISS, 0/1, .375/.425. Activation F1 `.775 → .7568166667`,
F2 `.4083333333 → .3554166667`. Default .35 сохраняет source/right;
predeclared .4 после MISS даёт `1 → none`, right → no action; matched F0 сохраняет
выбор. Никаких изменений world, thresholds, weights, formulas, provenance или policy.

Все Python/subprocess launches: `PYTHONDONTWRITEBYTECODE=1 python -B`;
writable fixtures/logs/copies только в `/tmp`. Logs:
`/tmp/rnd024-diagnostic-reproductions.log`, `/tmp/rnd024-diagnostic-target.log`,
validation results `/tmp/rnd024-diagnostic-validation-ecvl3zak`.
Baseline inventory `/tmp/rnd024-diagnostic-baseline.json`;
final safety `/tmp/rnd024-diagnostic-final-safety.json`.

Git scope — те же три RND-024 файла. Все остальные files/directories,
12 Production Memory files, weights, Stage 1/2, 119 ignored `.pyc` и `sf4.py`
совпадают с pre-edit SHA-256/inventory; новых служебных файлов нет.
Syntax/whitespace PASS; tracked diff и staging пусты. Branch main, HEAD
`07c74b8b0f2e07925af633f962f7018d3d71a358`. Commits/remote/tags не выполнялись.
Trusted serialized ownership, отсутствие preemption произвольного `__str__` и
прочие first-pass ограничения сохраняются; utility/reward learning не заявлено.

**STOP FOR TARGETED REVIEW.**

## Final closure — CLOSED

2026-11-09. **CLOSED — ACCEPTED FOR CLOSURE.** Final targeted review подтвердил
закрытие diagnostic P2; P3 portability принят ранее. Дополнительных findings нет.
Ниже итоговый checkpoint; предыдущие OPEN/STOP/CORRECTION REQUIRED относятся
только к истории реализации и исправлений.

### Подтверждённый learning/feedback path

Пустая temporary ExpSM → genuine native exploratory training в существующем мире
`(1,3)` → три actual retained transitions → RND-021 admission всего набора,
acquisition support=2 → один explicit authorized CREATE и confirmed readback →
fresh remembered retrieval/activation/selection с acquired source → guarded
execution и один physical apply → genuine owned-world T+1 → existing native
evaluator → policy-gated Stage 2 APPLY → authoritative record/receipt readback.
Source ID, TargetCore, occurrence, pending и exact retained T+1 связаны.

| Контроль | Persisted hits/misses | Confidence/repeatability | Activation до → после |
|---|---|---|---|
| F0-column0, feedback OFF | 0/0 | .500/.500 | .775 → .775 |
| F0-column1, feedback OFF | 0/0 | .500/.500 | .4083333333 → same |
| F1 HIT | 1/0 | .382/.425 | .775 → .7568166667 |
| F2 MISS | 0/1 | .375/.425 | .4083333333 → .3554166667 |

F0 не вызывает writer, record bytes и receipt ledger неизменны. F1/F2 update
подтверждены свежим authoritative readback. При default selector .35 source `1`
и действие right сохраняются. При заранее объявленном sensitivity selector .4
после MISS source `1 → none`, right → no action; matched F0-column1 сохраняет
selection. Это раздельные доказательства A — persisted metrics, B — activation,
C — selection при фиксированной .4 и D — соответствующее физическое поведение.

### Corrections и safety semantics

Replay/conflict, policy denial и stop-on-uncertainty сохранены. После неизвестного
persistence outcome, включая WRITE_FAILED после replace/fsync, blind retry нет.
Существующие writer/reconciliation authority и statuses не менялись.

Terminal diagnostic reason — exact built-in `str`, длина 1..256; компоненты,
fallback и result/recovery diagnostic snapshots проходят одну scalar boundary.
Malicious string subclass operators не обходят её. Primary exception identity и
traceback сохраняются; terminal state и fallback устанавливаются до диагностики;
первая reason не затирается. GC/weakref tests и дополнительный final-review probe
подтвердили освобождение exception, malicious string, payload, session/world при
живом owner после удаления внешних test references.

Final targeted review: 33 PASS в основном checkout и 33 PASS в свежей `/tmp`
validation copy, без двойного счёта. 194 regression PASS; итого **227 уникальных
unittest PASS**, отдельно scoring/selection PASS. Исторические 217/221 не добавлены.

К closure прежние `/tmp` logs/inventories оказались недоступны. Чтобы подтвердить
текущую Python-версию перед commit, выполнен один свежий isolated validation run:
**33 targeted + 194 regression = 227 PASS**, scoring/selection PASS. После этого
менялась только документация; Python hashes совпадают с validated copies.
Логи/results и closure inventory: `/tmp/rnd024-closure-k6dw6eh0`.
Все Python/subprocess launches: `PYTHONDONTWRITEBYTECODE=1 python -B`;
fixtures/stores/logs только в temporary isolation.

SHA-256 всех 12 Production Memory files совпадают с исходным HEAD; каталоги,
weights и Stage 1/2 не менялись. 119 ignored `.pyc` побайтово неизменны за closure;
исторические per-file bytecode hashes из исчезнувших `/tmp` baseline повторно
сравнить невозможно. Root `sf4.py` совпадает с ранее зафиксированным SHA-256
`0e3190a815dd4e65ac768e586b04cd877d845c67e0641fdbddc7e232fbcec975`.
Новых lock/cache/manifest/service files и Substrate violators нет.
Syntax/whitespace и точный трёхфайловый staged scope проверены перед commit.

### Ограничения и локальный scope

Нет learned utility/reward optimization: feedback проверяет предсказание, а не
полезность действия. Изменение выбора показано при sensitivity .4, а не default
.35. Эксперимент — isolated trusted serialized owner; automatic Heart feedback
hook не добавлен. Нет общего durable restart recovery для experiment owner.
Existing Stage 2 receipt ledger growth contract не изменён; произвольные callbacks
не получают preemption. Исторический Substrate baseline **FAIL остаётся открытым**
с прежними тремя runtime paths и не объявляется PASS.

Единственный локальный closure commit:
`feat(learning): integrate native outcome feedback loop`.
Его parent — `07c74b8b0f2e07925af633f962f7018d3d71a358`, ветка `main`.
Commit scope — ровно:

- `scenarios/native_outcome_feedback_loop.py`;
- `tools/verify_native_outcome_feedback_loop.py`;
- `docs/RND-024_native_outcome_feedback_loop.md`.

`sf4.py` не входит в RND-024 и не добавляется в staging. Production contracts,
Memory, weights, Stage 1/2 и RND-021/022/023 не изменены. Только локальный commit;
remote/tags и следующий этап не выполнялись.

**STOP AFTER CLOSURE.**
