# RND-022 — Synthetic Exploratory Action Bootstrap

**Текущий итоговый статус: CLOSED.** Дата closure: 2026-11-07.
Вердикт координатора после final architecture/behavioral и receipt/exception-safety
reviews: **ACCEPTED FOR CLOSURE**. Новых блокирующих дефектов нет; дополнительных
production-исправлений не требуется. Итоговые гарантии и ограничения — в разделе
«Final closure — CLOSED» в конце документа.

Далее сохранена история implementation, corrections и reviews. Все OPEN, FAIL,
STOP FOR REVIEW, прежние Git snapshots и запреты commit в исторических разделах
описывают соответствующие промежуточные точки и не являются актуальным статусом.
Последний раздел closure имеет приоритет для итогового состояния.

Дата implementation: 2026-11-06. **Исторический первый pass: IMPLEMENTATION / OPEN.**
Исходная точка: `main`, HEAD `3c665d9b542189b49f4761d34b551ad3f59bb6c6`,
чистое дерево, RND-021 CLOSED. LOCAL ONLY; без commit, remote-операций и tags.
RND-023 не начат.

## Совместимая execution boundary

До реализации проверены RND-020/021, NativeHeartSession/NativeDeliverySession,
retrieval → activation → native selection, SelectedNFPExecutionRequest,
NFPActionOccurrenceMaterializer, coordinator, ModeActionGuard/ActionTransducer,
ContextMemoryManager/pending/ShortMemory и SyntheticClosedLoopVisualWorld.

Ранее materializer и guard принимали только remembered intent: обязательные
source experience, activation, selection и predicted effect. Подделывать эти поля
нельзя. Минимальная совместимая граница — извлечение существующего хвоста
coordinator в `_execute_materialized`. Оба entry points делегируют ему; во всём
coordinator остаётся **ровно один** вызов `world.apply_actuator_signal`.

Remembered path сохраняет исходные request validation, freshness, pending check,
materialization, source/selection identity и prediction. Общий хвост сохраняет
порядок topology → mode guard → ActionTransducer → apply → pending → observation.
Дополнительные result fields: `exploratory_intent=None`, `guard_passed=False`
до успешного guard; existing statuses и физическое поведение сохранены.
Guard дополнительно принимает строго типизированный MaterializedExploratoryAction;
его правило безопасности прежнее: актуальный action tick и mode `active`.
Никакой альтернативной authority для apply не введено.

## Реальный путь

```text
explicit config + typed test-owner authorization + owned synthetic world
  → fresh sensor snapshot(T) → external NFPWindow → manager
  → successful retrieval(NO_COMPARABLE_RECORDS) → activation → selection=None
  → SyntheticExplorationPolicy.issue
  → ExploratoryIntent(intent/authorization/owner/config/session/context/tick/command)
  → coordinator.execute_exploratory → single-use admission reservation
  → fresh UUIDv4 ACTION frame + independent UUIDv4 execution occurrence
  → shared topology/ModeActionGuard/ActionTransducer boundary
  → single world.apply (world advances T→T+1)
  → manager.observe_action_frame → PendingCausalTransition(occurrence)
  → SyntheticTimeAdapter.finish(actuator=True), no idle advancement
  → next native pulse: actual world.snapshot(T+1)
  → manager.observe_external_sensory_window → RecentCausalTransition(occurrence)
  → ShortMemory.remember → clear unresolved/awaiting occurrence
```

Exploration не вызывает snapshot после apply в том же pulse. В NativeHeartSession
sensor задаётся caller; NativeDeliverySession использует прежний собственный
producer/consumer и occurrence-bound consequence port. T+1 не реконструируется
из прогнозов и не переименовывается из более позднего observation.

Exploratory intent не имеет experience ID, selection ID, reward, effect или
predicted effect. Result имеет `source_experience_id=None`, `target_core=None`,
`predicted_effect=None`. Отсутствие прогноза не заменяется нулевым эффектом.
Связь intent → frame → occurrence хранится в typed execution result и bounded
policy diagnostic; pending/recent сохраняют настоящий execution occurrence.

## Включение и выбор

По умолчанию `exploration_config=None`: прежнее session behavior.
Для включения caller передаёт SyntheticExplorationConfig и отдельно
SyntheticExplorationAuthorization(test_owner_id, authorization_id, configuration_id).
Без authorization config не разрешает выдачу intent. Несовпадающий configuration
ID отвергается. Это явная authority trusted isolated test owner, не криптографическая
аутентификация и не permission на production actuator.

```python
config = SyntheticExplorationConfig(
    configuration_id='round-robin-v1',
    commands=((0.0, 1.0), (1.0, 0.0)),
    max_intents=1, max_actions=1,
)
authorization = SyntheticExplorationAuthorization(
    test_owner_id='isolated-test-owner', authorization_id='permit-022',
    configuration_id='round-robin-v1',
)
# NativeHeartSession / NativeDeliverySession(...,
#     exploration_config=config, exploration_authorization=authorization)
```

Команды предоставляет test owner. Выбор: `commands[issued_count % len(commands)]`.
Это технический bootstrap round robin, **не learned strategy**. Он не читает hidden
position/state, не оценивает полезность и не знает world dynamics. Policy читает
только публичный world tick при admission, не effect или sensor values для выбора.
Перестановка команд меняет выбор при неизменном world code.

Fallback намеренно консервативен: только selected=None, пустые candidates и статус
`NO_COMPARABLE_RECORDS` после нормально завершившихся retrieval/activation/selection.
Это включает empty store и отсутствие structurally comparable/above-threshold опыта.
`STORE_INVALID`, `INVALID_QUERY`, `UNSUPPORTED_MEMORY_PRESENT`, exceptions,
selection=None при непустых candidates и отклонение remembered action не разрешают
exploration. Remembered selection всегда имеет приоритет.

## Budgets, authority и lifecycle

- Только экземпляры SyntheticClosedLoopVisualWorld, включая synthetic fault-test
  subclasses; неподдерживаемый world отвергается при session construction.
  Policy weakly binds точный owned world и точный issued context object.
- 1..16 immutable commands; каждая — две finite числовые компоненты в [0,1].
  Topology и transducer дополнительно проверяются общим coordinator.
- Independent `max_intents` и `max_actions`: integers 0..64,
  `max_actions <= max_intents`. Actions budget расходуется при admission **до guard**:
  denial тоже расходует разрешённую попытку. Поэтому applied никогда не больше
  admitted и бюджета. После исчерпания session продолжает idle/обычный native path.
- Lifetime первого pass — ровно тот же tick (`intent_lifetime_ticks=0`). Freshness
  требует exact context identity и `context.end_tick == intent.tick == world.tick`.
  На tick может быть выдан не более одного intent. Copied/fabricated/reused intent
  не проходит exact issued-object reservation; outcome больше не `issued`.
- Single pending slot проверяется при issue и повторно перед materialization.
  Необработанный occurrence блокирует последующий exploration даже после expiration
  pending. Missing/late observation не создаёт transition и не разблокирует policy.
- Не более 64 frozen diagnostics: intent, admitted/guarded/applied/denied/uncertain,
  fixed outcome и occurrence. Identity strings ≤256; tick <2^63; inputs ≤8 frames
  и ≤4096 values/frame. Нет удержания raw result/exception/traceback в policy;
  external exception detail exploratory result заменяется фиксированной категорией.
- `issued` — создан intent; `admitted` — зарезервирована попытка; `guarded` — guard
  разрешил; `applied` — apply вернулся и pending зарегистрирован; `denied` — сигнал
  не был допущен к apply; `uncertain` — apply/tracking/session failure с потенциальным
  воздействием. Возврат apply при некорректном world advancement помечается uncertain
  session diagnostic. Эти признаки не заменяют статусы authoritative execution.
- World/context удерживаются policy только через weakrefs; session/callback/history
  не удерживаются. Existing finite max_ticks ограничивает session records/journal/
  unresolved bookkeeping. Строгий byte budget всего Python heap не заявляется.
- Reservation до внешней работы исключает blind retry. Apply exceptions до/после
  mutation, tracking failure и time divergence останавливают session прежним
  fail-closed путём. Pause/resume сохраняет pending и не повторяет старый occurrence.
  STOP и tick exhaustion terminal; restart не создаётся. Глобального lifecycle
  manager, durable dedup или restart recovery нет.

## Основной эксперимент и RND-021

Verifier создаёт isolated ExpSM с `experience={}`; remembered motor priors в основном
сценарии отсутствуют. Без opt-in — ноль actions. С config+authorization — один
самостоятельно выданный intent, один guard/transducer/apply, T+1 actual consequence,
настоящий retained ShortMemory transition с тем же occurrence. ExpSM остаётся пустой.

Отдельная проверка использует **неизменённый** BoundedNativeAcquisition:
actual owned-delivery transition успешно получает `admitted`; evidence совпадает
с ExperienceEvidenceFactory.build(transition), source_experience_id в envelope —
None. RND-021 уже допускает отсутствие remembered source/prediction и подтверждает
apply через session record, pending, time advancement и sensor delivery provenance.
Admission не ослаблен; CREATE не вызван, writer policy запрещает commit.

Ограничение для RND-023: текущая ExecutionProvenance RND-021 не проецирует exploratory
intent ID, authorization/test-owner/config IDs. Поэтому её хватает существующему
acquisition admission, но она не сохраняет полный audit исследовательского разрешения
после освобождения session. Если будущий handoff требует такого audit, нужен отдельный
явный bounded provenance contract для этих IDs. Здесь он не добавляется. Нужны также
будущие явные orchestration/promotion gates полного learning loop; ни automatic
CREATE, ни Feedback APPLY, ни production publication не реализованы.

## Проверки

Все запуски: `PYTHONDONTWRITEBYTECODE=1 python -B`; regression выполнена в temporary
validation copies. 17 suites, **27 targeted + 255 regression = 282 уникальных PASS**.
Повторы не добавлены к числу уникальных tests.

| tools/verify_*.py | Tests |
| --- | ---: |
| synthetic_exploratory_bootstrap | 27 |
| nfp_remembered_action_guarded_execution | 8 |
| native_session_b1 | 5 |
| native_heart_b2 | 23 |
| native_bounded_delivery | 18 |
| nfp_context_short_memory | 24 |
| bounded_native_acquisition | 40 |
| short_memory_expsm_evaluation | 10 |
| persistent_nfp_expsm_representation | 10 |
| nfp_expsm_policy_gated_create | 8 |
| expsm_persistence_stage1 | 9 |
| nfp_native_feedback_replay_idempotency | 15 |
| nfp_native_feedback_apply | 11 |
| echo_expectations | 17 |
| multitick_internal_work | 14 |
| minimal_dar_admission | 15 |
| echo_dar_cognitive_integration | 28 |

Негативные проверки покрывают disabled/no authorization, mode denial, invalid commands/
topology, stale/copied context, wrong owned world, occupied slot, missing/late sensor,
unknown apply до/после mutation, double world advancement, copied/reused intent,
pause/resume/control STOP, tick exhaustion, delivery/intent/action resources,
remembered precedence/denial, selection-none, typed retrieval errors и exceptions,
sensor/tracking failures. Runtime test traps запрещают CREATE, Feedback APPLY и
filesystem writes; Production Memory inventory проверяется дополнительно.

Исходный AST verifier remembered execution ожидал apply внутри execute и дал один
FAIL после extraction. Обновлён на проверку одного apply во всём coordinator,
его единственного размещения в shared primitive, делегирования обоих entry points
и расположения guard/transducer до apply. После исправления — 8/8 PASS; behavioral
remembered tests сохранены. Stage 1 audit: 7 writers; direct-write, transaction,
preflight и store-order violations=0, Stage 2 enabled, runtime wiring=false.
Известный Substrate baseline FAIL не запускался, не исправлен и не объявляется PASS.

## Git scope и Production Memory safety

Scope — ровно восемь файлов:

1. `clc/actuation/synthetic_exploration.py` (новый).
2. `clc/actuation/remembered_action_execution.py`.
3. `clc/system/mode_action_guard.py`.
4. `clc/runtime/native_heart_session.py`.
5. `clc/runtime/native_bounded_delivery.py`.
6. `tools/verify_synthetic_exploratory_bootstrap.py` (новый).
7. `tools/verify_nfp_remembered_action_guarded_execution.py` (AST audit).
8. Этот документ (новый).

Syntax и `git diff --check` проверены; source в validation copies сверён с checkout.
Stage 1/2, RND-021 owner, Heart, Context/ShortMemory, selector/retriever/activation,
world dynamics и веса не менялись. Нет добавленных служебных/bytecode/lock/manifest
файлов в checkout. Все logs/validation copies вне репозитория в `/tmp`.
Полный inventory всех 12 Production Memory файлов и каталогов совпадает с исходным.
Нет production Memory writes. Итоговые ветка/HEAD прежние, пять modified и три
untracked файла из перечисленного scope; staging и commit отсутствуют.

### Проверенный inventory/SHA-256

| Production Memory file | SHA-256 (до = после) |
| --- | --- |
| `Memory/AKBSM/AKBSM_CRUD.py` | `268daa402f5fdd7239100e33a9a181b767340a221ec6073607ea442616f8773e` |
| `Memory/AKBSM/AKBSM_ne.json` | `0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd` |
| `Memory/AKBSM/DB/1.nfp` | `9dc8bdea3ab22028eb71bf88beefedba0a31ed85c60f3d804c533896d2f31536` |
| `Memory/AKBSM/DB/2.nfp` | `2a4365119b61bbd90ba6e6bb5c72aac605331779084434485d3a6d3539a2d227` |
| `Memory/DTF.json` | `081ce0056d36c0bf599b279828ee35705b84f942ce3d8e58db05cebdcfdf9c26` |
| `Memory/DTF_TFH.json` | `b5289aa54f2b3f87ee5e7a3d1fa428cae5c85bcbfacd0cfeb568ef452ba938de` |
| `Memory/ExpSM/ExpSM_data.json` | `6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e` |
| `Memory/ExpSM/ExpSM_drafts.json` | `12a54a83784bbef939fb16b319dce5f1b94f77745c6e49a197118249b9fecbd4` |
| `Memory/ExpSM/Exp_CRUD.py` | `ab081ea719c24307336f13143a94412d088e53b2ad18b22710ffd0ad2485c880` |
| `Memory/WL/WL.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `Memory/WL/WL_CRUD.py` | `8f8d53ddd88b0439520404f2c52407915d2982fb39c0d49e33776d15bea14b13` |
| `Memory/pattern_manifest.json` | `d442580fa93cd057854b91382e36f85db904ebc25a8ebbfd6772052b39c338f6` |

Каталоги (до = после): `Memory`, `Memory/AKBSM`, `Memory/AKBSM/DB`, `Memory/ExpSM`, `Memory/WL`.

## История: targeted correction — post-apply interruption (тогда OPEN)

Это correction pass после architecture review, **не closure**. Приняты остальные
архитектурные выводы review. Историческая батарея первого pass выше — 282 PASS;
review добавил 6 успешных probes и один failing reproduction. Повторы не суммируются.

### Точная последовательность исходного P2

1. Policy выдаёт intent и переводит его из issued в admitted до materialization.
2. Coordinator создаёт новый ACTION и execution occurrence UUIDv4 локально.
3. Shared execution проходит topology, guard и transducer.
4. Воспроизведение вызывает настоящий world.apply, который меняет мир T→T+1,
   затем выбрасывает KeyboardInterrupt. Call не возвращает успешный результат;
   наличие mutation в этом тесте известно из fault fixture, не из UUID.
5. `except Exception` shared boundary не перехватывает KeyboardInterrupt.
   Pending ещё не зарегистрирован; coordinator не завершён и result не возвращён.
6. В session переменная execution остаётся None. Прежний mark_uncertain(None)
   ничего не делал: policy оставалась admitted, uncertain=False, без occurrence.
   При этом прежний session STOP/in_flight/synchronization block уже запрещал retry.

### Минимальная дополнительная граница диагностики

Только session не располагает нужными фактами: `_in_flight` устанавливается до guard,
а UUID создаётся внутри coordinator. Поэтому для точного различения pre-apply и
possible-apply случаев необходимы диагностические checkpoints в существующем
coordinator. Это прямое обоснование изменения двух файлов сверх предпочтительных
трёх: `synthetic_exploration.py` и `remembered_action_execution.py`.

Добавлены обновления **существующей** bounded ExplorationDiagnostic:

- bind_execution: сохраняет occurrence после materialization; не является proof of apply;
- pass_guard: фиксирует успешный guard, но не физическое воздействие;
- enter_apply: фиксирует вход в границу потенциально изменяющего мир вызова;
- confirm_pending: только после возврата apply и успешной регистрации pending
  фиксирует прежний authoritative ACTION_EXECUTED_OBSERVATION_PENDING.

Опциональный параметр shared primitive используется только exploratory entry point;
remembered path не передаёт policy. Вызов world.apply, guard, transducer и правила
admission не изменены. Второго apply или второй системы authoritative statuses нет.

В exception path session сначала блокирует synchronization и устанавливает STOP,
затем policy.interrupt использует issued intent и доступный result/checkpoint.
Для применения с неизвестным исходом остаются uncertain=True, исходный intent и
occurrence; occurrence добавляется в unresolved, даже если result не был возвращён.
Pre-apply interruption остаётся denied/interrupted_before_apply без физического
uncertain и без ложного pending. Slot, если он реально успел быть записан перед
tracking interruption, не очищается и не дублируется.

При известном result приватная bounded projection сохраняет его точный status.
Если `finish` прерывается до/после projection, узкий exception handler использует
уже существующий result и повторно выбрасывает **тот же** exception. Он не повторяет
materialization, guard, apply, регистрацию pending или наблюдение. Если coordinator
завершился, но result не дошёл до session, checkpoint подтверждённого pending
сохраняется. Поздняя ошибка session не превращает этот подтверждённый outcome в
искусственный uncertain. Ошибка tracking до подтверждённого возврата остаётся
консервативно uncertain, даже если fault fixture уже успел записать pending.

Ни raw result, ни exception, ни traceback, ни callbacks не удерживаются policy.
Все checkpoints обновляют существующую frozen запись в пределах прежних 64 entries.
STOP, budgets, single-use reservation, отсутствие blind retry и future RND-023
provenance gap остаются прежними. Standalone restart/durable exactly-once не заявлены.

### Постоянные tests и текущая regression

Добавлено **7** test methods к прежним 27:

- KeyboardInterrupt внутри apply до mutation и после настоящей mutation: один call,
  uncertain с UUID, unresolved, без pending/idle/retry, тот же exception;
- прерывание guard до apply: нет physical uncertainty, pending или actuator advancement;
- finish interruption до/после projection после apply+pending: подтверждённый status
  сохранён, один pending, один apply;
- ошибка session после получения coordinator result: authoritative outcome сохранён;
- tracking interruption после записи pending: conservative uncertain, slot сохранён;
- coordinator завершился, но caller не получил result: checkpoint не потерян;
- реальный delivery → actual T+1 → один retained ShortMemory transition, затем
  tick exhaustion без повторного действия.

Прежние cases дополнительно покрывают pause/resume, STOP, guard denial, fallback,
budgets, missing/late observation, CREATE/Feedback traps и реальный RND-021 admission.

В correction запущены семь релевантных suites в temporary validation copies:

| tools/verify_*.py | Tests | Result |
| --- | ---: | --- |
| synthetic_exploratory_bootstrap | 34 | PASS |
| nfp_remembered_action_guarded_execution | 8 | PASS |
| native_session_b1 | 5 | PASS |
| native_heart_b2 | 23 | PASS |
| native_bounded_delivery | 18 | PASS |
| bounded_native_acquisition | 40 | PASS |
| nfp_context_short_memory | 24 | PASS |

**34 targeted + 118 regression = 152 уникальных PASS текущего correction run.**
С прежними 282 и review probes это число не складывается. Полная батарея verifiers
не повторялась. Все Python-запуски, включая subprocesses, используют одновременно
PYTHONDONTWRITEBYTECODE=1 и python -B. Final source сверён с validation copies.

Correction изменяет ровно пять существующих файлов общего восьмифайлового scope:
NativeHeartSession, synthetic exploration policy, coordinator, exploratory verifier
и этот документ. ModeActionGuard, ActionTransducer, NativeDeliverySession, remembered
AST verifier и RND-021 owner в correction не менялись. Syntax/diff whitespace,
единственный apply, прежний fallback и полный Git scope проверены.

Полный inventory/SHA-256 12 Production Memory файлов и directory inventory совпадают
с baseline, приведённым выше. Stage 1/2, веса и остальные repository files неизменны.
119 прежних ignored .pyc сохранены с прежними hashes; correction новых bytecode,
lock, manifest или service files в checkout не создаёт. Logs/fixtures находятся в
/tmp. Новых Substrate runtime-import violators нет; исторический baseline FAIL
не запускался, не исправлен и не объявляется PASS.

Ветка main, HEAD 3c665d9b542189b49f4761d34b551ad3f59bb6c6; прежний общий scope:
5 modified + 3 untracked, индекс пуст. Коммит, remote-операции, tags и RND-023
отсутствуют. **STOP FOR TARGETED REVIEW — RND-022 остаётся OPEN.**

## История: diagnostic marker exception safety correction (тогда OPEN)

Последующий final targeted review выявил три новых P2 (5 probes PASS, 3 FAIL).
Раздел ниже заменяет прежнее предположение о достаточности одних policy markers
для восстановления фактов после их собственных исключений. Это correction, не closure.

### Причины и минимальный factual handoff

- enter_apply мог записать `applying` и затем упасть до world.apply. Recovery считала
  этот optimistic marker доказательством возможного вызова и создавала ложный uncertain.
- confirm_pending мог упасть до записи marker после настоящего apply+pending.
  Result ещё не был сформирован, и recovery теряла известный coordinator факт.
- interrupt мог упасть при уже активном первичном исключении. Вторичная ошибка
  заменяла первичную и прерывала регистрацию unresolved occurrence.

Введён один ExploratoryExecutionReceipt в существующем synthetic execution contract.
Это bounded handoff coordinator → diagnostics/session, **не второй executor, не
новая authority и не искусственный execution result**. Policy удерживает только
последний receipt; factual поля пишет только coordinator в сериализованном call path:

| Факт | Когда записывается | Что не доказывает |
| --- | --- | --- |
| occurrence_created / execution_occurrence_id | После настоящей materialization, до bind marker | Не доказывает guard или apply |
| guard_passed | После успешного guard, до pass_guard marker | Не доказывает apply |
| apply_entry | После успешного возврата enter_apply marker, непосредственно в call boundary world.apply | Не доказывает mutation или успешный возврат |
| apply_returned | Непосредственно после нормального возврата world.apply | Не доказывает регистрацию pending или observation |
| pending_registered | После нормального возврата manager.observe_action_frame, до confirm_pending marker | Не доказывает actual T+1 |
| result_status | Только после формирования и возврата результата shared coordinator | Не заменяет sensory evidence |

Receipt содержит только intent ID, occurrence ID, четыре boolean stages и optional
строку существующего authoritative status. Все IDs происходят из уже проверенного
intent/materialization. Нет raw result, pending, world, session, callbacks, exceptions
или tracebacks. Plain slotted receipt не создаёт unbounded stage history.

Markers остаются диагностической проекцией. Recovery читает receipt, а не выводит
физические факты из optimistic policy outcome. Если confirm_pending прерван до/после
записи marker, receipt подтверждает только `pending_registered`; диагностический
outcome имеет именно это имя, а result_status остаётся None, если shared coordinator
не успел сформировать настоящий result. Completed/observed result не синтезируется.
Если настоящий result уже сформирован, его status сохраняется точно.

`apply_entry` отмечает границу потенциального воздействия в том же try, что и apply.
Это не durable proof физической mutation: асинхронное прерывание непосредственно на
границе вызова остаётся консервативно uncertain. Отдельно распознаётся исключение
самого pre-apply marker: call boundary ещё не достигнута, receipt.apply_entry=False.

### Исключения и fail-closed поведение

Coordinator ловит исключение в узком exploratory lifecycle scope и вызывает
recover_interruption, затем делает bare raise первичного исключения. Эта функция
изолирует только **вторичную** ошибку interrupt при уже активном primary exception:
устанавливает bounded diagnostic_recovery_failed и использует отдельную приватную
проекцию receipt без повторного marker/executor. Повторный заход session не повторяет
recovery marker: хранится один bounded recovery-attempt intent ID.

Если сама резервная проекция недоступна, устанавливается diagnostic_projection_failed.
Receipt сохраняет реальные факты; обычная diagnostic projection в этом случае явно
неполна и не должна считаться обновлённой. Первичное исключение всё равно передаётся
caller. Это не универсальный except-pass: ошибки обозначены flags; первичное
исключение не скрывается и не превращается в успешный result.

Session устанавливает прежние STOP/synchronization block и добавляет unresolved
occurrence напрямую из receipt.apply_entry, независимо от успешности проекции.
Pre-apply failure не создаёт uncertain/pending/unresolved. Real apply interruption
сохраняет uncertain и UUID, без idle/retry. После возврата apply, но до подтверждённого
возврата pending registration, сохраняется conservative uncertain с отдельным
apply_returned=True. Реально записанный при tracking interruption pending не очищается
и не дублируется. После pending-confirmed diagnostic error не стирает известный факт.

Внутренний receipt и recovery control flow — доверенные сериализованные компоненты,
не arbitrary user callback/plugin API. Fault injection покрывает запись markers и
ошибки recovery/projection; произвольная подмена самого recovery controller, порча
receipt и бесконечные повторные asynchronous interruptions не обещаны как recoverable.
Строгого глобального heap/real-time bound и durable exactly-once по-прежнему нет.

### Original reproductions: до / после

| Reproduction | До correction | После correction |
| --- | --- | --- |
| enter_apply записал marker и выбросил KeyboardInterrupt | applies=0, ложный uncertain/unresolved | applies=0, apply_entry=False, denied/pre-apply, uncertain=False, pending=None |
| confirm_pending упал до записи | apply=1, pending=1, потерянный known outcome | apply=1, pending=1, pending_registered=True, outcome=pending_registered, result_status=None, uncertain=False |
| world mutation + KeyboardInterrupt, затем interrupt RuntimeError | Caller получал RuntimeError, отсутствовал unresolved | Caller получает тот же KeyboardInterrupt; receipt и uncertain/occurrence/unresolved сохранены; recovery-failed flag |

Ни один из этих путей не повторяет admission, materialization, apply, pending или idle.
Positive real delivery → actual T+1 → ShortMemory и RND-021 admission сохранены.
При исключении без actual observation не создаются acquisition evidence/CREATE;
исследовательское разрешение не заменяет execution proof. Прежний authorization
provenance gap RND-023 не изменён.

### Постоянные tests и проверки

Добавлены 7 test methods (с несколькими fault arms) к прежним 34:

1. enter_apply до/после записи, RuntimeError и KeyboardInterrupt;
2. confirm_pending до/после записи, обе категории исключений, без fake result;
3. primary world KeyboardInterrupt + secondary recovery RuntimeError/KeyboardInterrupt;
4. primary finish RuntimeError + secondary recovery KeyboardInterrupt, known result;
5. apply вернулся, pending registration ещё не состоялась;
6. secondary projection failure: primary и receipt остаются, session terminal;
7. bind_execution/pass_guard failures до/после записи: правильные identity/stage.

Сначала весь новый verifier, включая original reproductions: **41 PASS**.
Затем семь relevant suites в новых isolated validation copies:

| tools/verify_*.py | Tests | Result |
| --- | ---: | --- |
| synthetic_exploratory_bootstrap | 41 | PASS |
| nfp_remembered_action_guarded_execution | 8 | PASS |
| native_session_b1 | 5 | PASS |
| native_heart_b2 | 23 | PASS |
| native_bounded_delivery | 18 | PASS |
| nfp_context_short_memory | 24 | PASS |
| bounded_native_acquisition | 40 | PASS |

**Текущий run: 41 targeted + 118 regression = 159 уникальных PASS.** Повтор первого
verifier, прежние 152/282 PASS и review probes не прибавляются. Полная батарея
verifiers не повторялась. Все Python-команды и subprocesses запускались через
PYTHONDONTWRITEBYTECODE=1 и python -B. Final Python сверён с validation copies.
Remembered execution не передаёт receipt/policy; shared markers и factual writes
для него инертны. Единственный apply, fallback, guard/transducer order и source/
activation/selection/prediction binding сохранены. RND-021 owner не изменён.

Scope correction — те же пять файлов: coordinator, synthetic policy, Heart session,
exploratory verifier и этот документ. Общий scope RND-022 — прежние восемь файлов.
Syntax, git diff --check и пустой staging проверены. Inventory/SHA-256 всех 12
Production Memory файлов и directory inventory неизменны; Stage 1/2, веса,
ModeActionGuard, world и остальные repository files не менялись. 119 baseline
ignored .pyc сохранены побайтово; новых cache/lock/manifest/service files нет.
Logs/validation fixtures находятся только в /tmp. Новых Substrate runtime-import
violators нет; исторический baseline FAIL не запускался и остаётся открытым.

main, HEAD 3c665d9b542189b49f4761d34b551ad3f59bb6c6; 5 modified + 3 untracked,
индекс пуст. Без commit, remote-операций, tags и RND-023.
**STOP FOR TARGETED REVIEW. RND-022 OPEN, не CLOSED.**


## Final closure — CLOSED

Дата: **2026-11-07**. Вердикт координатора: **ACCEPTED FOR CLOSURE**.
RND-022 **CLOSED**. Все обнаруженные P2 исправлены и проверены; новых блокирующих
дефектов нет. Дополнительные production-изменения для closure не требуются.
Исторические OPEN/FAIL/STOP выше сохранены как хронология и заменены этим итогом.

### Итоговые гарантии

- Exploration применяется только к synthetic world, выключен по умолчанию и требует
  отдельной явной test-owner authorization с binding к конфигурации.
- Motor commands задаются конечным разрешённым набором. Round-robin — технический
  bootstrap без знания hidden world state, ожидаемого эффекта, reward или полезности.
- Typed exploratory intent не содержит фиктивных experience/selection IDs или
  prediction. ACTION и execution occurrence получают новые независимые UUIDv4.
- Оба execution paths используют единый authoritative coordinator и единственный
  world.apply. Topology, ModeActionGuard и ActionTransducer проверяются до воздействия.
- Сохраняются freshness, finite budgets, single-use reservation и single pending
  causal slot. Blind retry и восстановление неизвестного физического исхода запрещены.
- Настоящее consequence observation поступает только в следующем pulse T+1.
  Подтверждённый RecentCausalTransition с тем же occurrence удерживается ShortMemory;
  pending_registered сам по себе не является actual observation.
- Неизменённый RND-021 принимает настоящий exploratory transition по прежним
  owned-world/sensor/retention checks, без поддельного remembered provenance.
- Bounded ExploratoryExecutionReceipt передаёт факты coordinator отдельно от policy
  diagnostic markers: occurrence, guard, apply entry/return, pending registration и
  только реально сформированный result status. Policy хранит один последний receipt.
- При ошибках markers различаются pre-apply, uncertain apply и confirmed pending.
  Первоначальные exception object и traceback сохраняются при secondary recovery
  errors; failure flags явно отмечают недоступную diagnostic projection. Receipt
  не удерживает raw execution, session, world, callbacks, exception или traceback.
- В error paths нет повторных materialization, apply, pending registration или idle
  advancement. STOP и synchronization block сохраняются; unresolved occurrence не
  очищается как будто последствие наблюдалось. Гарантия относится к live session.
- Remembered execution и fallback semantics сохранены: допустимый remembered
  selection имеет приоритет; ошибки retrieval/session и remembered guard denial
  не превращаются в разрешение exploration.

### Сохранённые ограничения

- Нет learned exploration strategy, самостоятельного определения цели или полезности.
- Нет автоматического acquisition/CREATE, Feedback APPLY или production publication.
- RND-021 envelope не сохраняет полный authorization/intent provenance. Отдельный
  bounded handoff этих IDs остаётся будущим контрактом RND-023; он здесь не реализован.
- Нет durable dedup/restart recovery, durable exactly-once, глобального lifecycle
  manager или строгого Python heap byte bound.
- Test-owner authorization действует только в доверенном isolated synthetic contract
  и не даёт production actuator authorization. Произвольная порча runtime state и
  бесконечные асинхронные прерывания не объявлены recoverable.
- **Исторический Substrate baseline FAIL остаётся открытым**: не исправлен и не
  объявляется PASS; новых violators этой работой не добавлено.

### Принятые проверки и final review

Closure Python-исходники побайтово совпадают с обеими temporary validation copies,
на которых получены **41 targeted + 118 regression = 159 уникальных PASS**.
Сверены все 299 Python-файлов checkout, а не только изменённые modules.
В closure меняется только документация, поэтому тестовая батарея не повторялась.
Исторические 282 и 152 PASS не считаются свежей регрессией и не суммируются с 159.

Final Receipt & Exception Safety Review добавил **два отдельных targeted probes PASS**:

1. Тот же primary exception object и исходный apply traceback сохраняются при
   одновременном отказе recovery marker и fallback projection; один apply,
   unresolved occurrence и terminal STOP, без idle/retry.
2. При удержании policy с последним receipt освобождаются session, world, context и
   raw result. Receipt содержит только bounded scalar fields и не удерживает history.

Эти два probes отражены отдельно, без двойного подсчёта предыдущих tests.
Все необходимые Python-запуски используют PYTHONDONTWRITEBYTECODE=1 и python -B;
fixtures/logs/safety snapshots расположены только в /tmp.

### Git scope и safety при closure

Полный diff пяти modified файлов и содержимое трёх untracked файлов проверены.
Staging и closure commit ограничены ровно восемью путями из раздела Git scope:
synthetic policy, coordinator, guard, Heart session, bounded delivery, два verifiers
и этот документ. Проверены syntax, git diff --check, git diff --cached --check,
полный staged diff и точный список staged paths. Production Memory, веса и другие
файлы в commit не входят.

Полный inventory/SHA-256 всех **12 Production Memory файлов** и directory inventory
совпадают с исходным inventory выше. Stage 1/2 и production-веса неизменны.
Все **119 baseline ignored .pyc** сохранены побайтово; новых service/lock/bytecode/
manifest файлов в checkout нет. Новых Substrate runtime-import violators нет.

Closure выполняется одним локальным commit на main от родительского HEAD
3c665d9b542189b49f4761d34b551ad3f59bb6c6 с сообщением:
`feat(actuation): add bounded synthetic exploration bootstrap`.
Идентификатор closure commit фиксируется Git history и итоговым отчётом.
Remote-операции и tags не выполняются. **RND-023 не начат. RND-022 завершён.**
