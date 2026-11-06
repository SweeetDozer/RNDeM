# RND-021 — Bounded Native Experience Acquisition

Дата: 2026-11-06. **CLOSED — ACCEPTED FOR CLOSURE** после implementation, corrections и targeted review.
Текущий статус — CLOSED; промежуточные review checkpoints ниже сохранены как история.
Исходные `main`, HEAD `3f420bb03b3b9382828456904de5b193a9c08760`, дерево чистое.
LOCAL ONLY; разрешён один closure commit с тремя файлами RND-021. Remote-операций, tags и RND-022 нет.

## Реальный путь

Новый явно вызываемый компонент:
`clc.experience.bounded_native_acquisition.BoundedNativeAcquisition`.
Он принимает исключительно `NativeDeliverySession`: для произвольного B2 sensor
публичного external producer binding недостаточно. Это намеренно узкий opt-in
контракт для exclusively owned, serialized synthetic experiment, вне Heart pulse.
Default session, ShortMemory.remember/prune и scheduler не изменены.

```text
SyntheticClosedLoopVisualWorld.snapshot
 → NativeDeliverySession owned-world delivery → VisualFieldTransducer
 → ContextMemoryManager.observe_external_sensory_window
 → existing retrieve / activate_native / select_native
 → SelectedNFPExecutionRequest → coordinator.execute
 → materializer → ModeActionGuard → ActionTransducer → world.apply
 → ACTION_EXECUTED_OBSERVATION_PENDING + pending + actuator advancement
 → owned-world sensor в T+1 → manager → RecentCausalTransition
 → ShortMemory.remember
 → explicit acquisition.admit(recent)
 → ExperienceEvidenceFactory.build → ObservedEffectExtractor.extract
 → ExperienceEvidenceGrouper.observe
 → acquisition.seal → full-set conflict admission → make_proposal
 → ExpSMRecordCreationRequestBuilder.build
 → explicit test-owner authorization → NFPExpSMCreateWriter.create
 → isolated ExpSM → fresh read-only reconciliation / fresh retrieval
```

Все перечисленные звенья, кроме нового owner/admission, существовали до RND-021.
Новый grouper, память, writer, selector, CREATE ledger или persistence primitive
не вводились. Stage 1/2, guarded execution, schema v1, веса и RND-016–019 не менялись.

## Binding и immutable envelope

Admission требует именно тот объект recent, который удерживается в ShortMemory
и в completed session record, а не копию с совпадающими IDs. Проверяются:

- исходный before window, action frame и pending по object identity;
- exact occurrence в execution, pending, recent и consequence delivery event;
- transition ID pending/recent без переписывания;
- успешный статус coordinator без detail, реальный actuator signal и pending;
- `advancement=actuator`, согласованные текущие Heart/world ticks и отсутствие
  synchronization_blocked; T→T+1, before.end_tick=T и retention age;
- signal values/tick/source-frame digest через существующий ActionTransducer;
  его локальный signal counter не переименовывается и не считается occurrence;
- реальные `native_admitted` owned-world events для before и after;
- session/source/stream, admission/source ticks, snapshot sequence, отсутствие
  выдуманного timestamp и равенство результата VisualFieldTransducer исходному NFP.

`ACTION_EXECUTED_OBSERVATION_PENDING` здесь не означает неизвестный physical outcome:
в production coordinator этот статус с pending и пустым detail возвращается после
нормального возврата `world.apply` и регистрации pending. `.executed` намеренно
не используется как достаточное условие: оно включает tracking failure.
WORLD_EXECUTION_FAILED, guard denial, tracking failure, missing/late actual,
internal reactivation и prediction evidence не допускаются. UUID alone недостаточен.

Публичный bounded delivery journal может вытеснять события. Если нужный sensor
trace уже утрачен, admission отказывает (`sensor_provenance_unavailable`), без
восстановления из tick/UUID. Envelope после успешного admission удерживает frozen
recent, компактный frozen `ExecutionProvenance`, оба frozen delivery events со snapshot payloads и
factory evidence. Дополнительно доступны session/source scope, occurrence,
transition/window/action identities, sensor event IDs, ticks, evidence ID и SHA-256
полного source transition content. Этот digest включает actual endpoints, values,
provenance и occurrence; factory evidence детерминированно проверяется по нему
и удержанному source. Исходные NFP не меняются.

Это trusted in-process dependency contract, не защита от произвольного изменения
`session.records`, world, policy или Python-объектов администратором. Fault injection
в тестах намеренно нарушает такие связи только в отрицательных ветках.

## Состояние и бюджеты

`admitting → reserved occurrence → admitted envelope → sealed → preparing → prepared → attempted → typed result/reconciliation`.
Reservation является per-occurrence записью, а не отдельным глобальным состоянием owner.
Только успешно завершённый observe позволяет добавить admitted envelope.
Терминальные STOP-состояния: occurrence/effect conflict, identity collision,
payload/metadata/input/evidence/lifetime exhaustion, ошибки factory/grouper/proposal/builder/writer/reconciliation, утрата session для admission или writer для CREATE, unresolved recovery.
Первая причина STOP зафиксирована в frozen `AcquisitionStop`: reason, optional occurrence/digest
и фиксированная категория исключения. Поздние вызовы и timeout её не заменяют.

Defaults: 16 admission calls, 8 reservations/dedup keys и до 8 admitted evidence/envelopes и не более 8 candidates,
4096 values на frame, один frame на каждый sensory endpoint, ссылки ≤256 символов,
60 секунд monotonic lifetime. Некорректные входы и duplicates тоже расходуют input
budget. Dedup keys никогда не вытесняются; исчерпание навсегда закрывает admission.
Session records уже ограничены Heart.max_ticks, delivery journal — своей capacity.
Нет unbounded diagnostic journal: admission возвращает один результат, owner
удерживает один proposal, request, writer result и fresh readback. Один CREATE
call на весь owner; lifetime проверяется на каждом публичном действии.
Синхронные существующие callbacks/filesystem calls должны возвращаться за конечное
время: owner не вводит preemption или worker для зависшего внешнего callback.

Одинаковый occurrence/source digest возвращает duplicate без второго observe.
Другой digest того же occurrence терминально блокирует acquisition. Разные реальные
occurrences с одинаковыми activation values дают независимые evidence IDs и support.
Коллизия factory evidence identity между разными occurrences также останавливает
admission; source IDs ради уникальности не переписываются.

`seal` завершает набор evidence. При fixed thresholds `1/1/1`, `min_support=2`
owner перед proposal и перед CREATE сравнивает **все admitted evidence попарно**:
совпадающие context/action с несовместимым effect блокируют весь run, даже если
выбранная группа уже имеет поддержку 2. Ничего не усредняется.
Proposal содержит реальный representative и фиксированные support IDs. Повторный
prepare после prepared или stopped_builder_error ничего не создаёт. Недостаточный support не даёт request.

## Authority и recovery

Конструктор требует dedicated root внутри системного temporary directory,
`memory_is_temporary=True` и confinement всех доступных store/lock/registry paths
writer, retriever, activation, context manager и action guard. Перед CREATE исходные snapshots путей session и текущие paths живого writer
проверяются снова с разрешением symlinks; повторного доступа к session нет. Registry constructors тестового driver
сразу получают temporary manifest, до создания session/owner. Это узкая проверка
конфигурации, не универсальный filesystem sandbox и не исправление F02–F09 RND-110.
Production-root runtime не создаётся; Production Memory не передаётся writer.

CREATE требует отдельного `test_owner_authorized=True`; затем существующий writer
проверяет `allow_expsm_commit`. Политики v1 и defaults не менялись.
Никаких CRUD/Feedback APPLY/transaction bypass. Persisted ID выделяет writer.

| Результат | Поведение owner |
| --- | --- |
| DENIED_BY_POLICY / INVALID_REQUEST / unsupported / STORE_INVALID | Завершённая единственная попытка; нет альтернативного writer |
| WRITE_FAILED | Сохраняется typed result; автоматического retry нет, независимо от retry_safe |
| CREATED | Дополнительная fresh read-only reconciliation original request/record ID |
| READBACK_FAILED | Existing `reconcile_expsm_readback_failure`, без CREATE retry |
| CONFIRMED_PERSISTED | Удерживается подтверждённая запись; повторная CREATE невозможна |
| CONFIRMED_ABSENT | Только attempted ID отсутствует; отсутствие любых дублей не доказано |
| UNRESOLVED_OR_STORE_INVALID | stopped_unresolved; дальнейшая автоматическая работа запрещена |
| Неожиданное исключение writer | attempted установлен до вызова, stopped_writer_error сохраняет причину; исключение передаётся caller, повтор запрещён |
| Исключение reconciliation | stopped_reconciliation_error, original writer result сохранён; uncertainty не подменяется подтверждением |
| Oversized response diagnostic | stopped_result_metadata_budget; oversized result не сохраняется owner, запись не повторяется |

Evidence/proposal — provisional observed association, не causal fact.
`support_count` не становится confidence/hits/misses. Builder сохраняет обычные
v1 defaults: hits=misses=0, confidence=repeatability=0.5. V1 retrieval не имеет
provisional filter; поэтому никакой production publication не разрешается.
RAM envelope теряется при завершении процесса. Нет durable dedup, crash-safe
exactly-once, outbox, restart recovery или универсального causal inference.

## Изолированный эксперимент и проверки

`PYTHONDONTWRITEBYTECODE=1 python -B tools/verify_bounded_native_acquisition.py`: **40 tests PASS** (32 прежних + 8 retention/lifecycle tests).
Это внешний isolated integration driver, не автоматическое native learning.

В temporary ExpSM находятся два явных motor priors: A/right и B/left с нулевым
нетаргетным effect. Целевого observed effect в исходной базе нет. Обычные retrieval,
activation, selection, guard и apply выполняют right/left/right; test owner
подаёт PAUSE на observation pulse T=3. Мир `(1,2)` даёт два независимых A/right/B
retained transitions; эффекты `(-1,+1)` вычисляет extractor, не fixture.
Созданная writer-owned запись подтверждается writer response, дополнительной
fresh reconciliation и отдельным fresh retriever. Исходные transition digests,
Heart records/stop report, ShortMemory, world applies, current context и DAR state
до/после acquisition совпадают; ЭХО/ДАР в этом driver выключены.

Отрицательные проверки: один occurrence, replay, иной digest того же occurrence,
независимые одинаковые effects, конфликтующие effects (в том числе поддержанная
группа 2 против дополнительной группы 1), guard denial, late/missing actual,
unknown outcome после apply, утрата retained transition, подмена execution status
и occurrence, internal/predicted evidence, утрата sensor journal, denied CREATE,
повтор prepare/CREATE, INVALID_REQUEST, STORE_INVALID, WRITE_FAILED, unexpected
writer exception, READBACK_FAILED и все три reconciliation исхода, finite budgets,
sealed admission и отказ nonisolated paths. Fault injection только в negative arms.

Регрессия первого pass (исторические результаты, все PASS):

| tools/verify_*.py | Tests |
| --- | ---: |
| nfp_remembered_action_guarded_execution | 8 |
| native_session_b1 | 5 |
| native_heart_b2 | 23 |
| native_bounded_delivery | 18 |
| nfp_context_short_memory | 24 |
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

Первый pass: 18 behavioral + 215 regression tests; текущие correction результаты ниже. Stage 1 AST audit: 7 writers, нулевые
boundary violations. Syntax и whitespace проверены отдельно.

Первый regression запуск без `-B` создал один Python cache file
`Memory/ExpSM/__pycache__/Exp_CRUD.cpython-314.pyc` при импорте существующего CRUD.
Три concurrent inventory checks заметили добавление и завершились FAIL/ERROR,
хотя behavioral assertions прошли. Созданный cache удалён; эти три проверки
повторены с `-B`, все PASS. Исходные Memory bytes не менялись. Финальный полный
inventory/SHA-256 всех 12 Production Memory файлов совпадает с исходным;
новых служебных файлов и каталогов в Memory нет. Веса не изменены.
Известный Substrate baseline FAIL не исправлялся, не запускался и не объявляется PASS.

Историческая контрольная точка первого correction: изменены только новый owner,
новый verifier и этот документ, коммита на том этапе не было.
**Исторический статус: OPEN / повторный review; заменён текущим CLOSED. RND-022 не начат.**


## Correction: exception safety и ресурсные границы

Исправлены только четыре замечания review и связанные пробелы в проверках.

### Reservation, admission и exception safety

После source validation, до factory, owner сохраняет frozen `OccurrenceReservation`
с occurrence/digest. Reservation расходует тот же evidence budget, что и успешный
admission, и не удаляется. Factory exception → stopped_factory_error, без admitted
envelope. Grouper exception до или после возможной мутации → stopped_grouper_error:
резерв остаётся, admission не считается успешным, повторный observe запрещён.
В таком STOP `candidates` может показывать частично изменённый state исходного
grouper: это диагностический snapshot, не подтверждённая поддержка для promotion.
Owner не откатывает приватные поля grouper и не заявляет его атомарности.

Успешный frozen proposal/support фиксируется до builder; state становится
preparing. Builder exception → stopped_builder_error; proposal identity и support
сохраняются, request остаётся None. Ни повторный prepare, ни новый builder, ни CREATE
невозможны. Ошибка make_proposal после возможной мутации тоже терминальна.

Исключения передаются caller после фиксации STOP. Owner не сохраняет exception,
traceback или произвольный текст ошибки: одна диагностика содержит фиксированную
категорию (`RuntimeError`, `ValueError`, `OSError` и т. п.; для остальных —
`external_exception`). Это не растущий history log. Исходная причина STOP никогда
не заменяется lifetime timeout. Writer attempt фиксируется до вызова, как прежде.

### Инвентаризация удерживаемых данных

| Удерживаемый объект | Проверенные данные / ограничение |
| --- | --- |
| Reservation | ≤8; occurrence ≤256 символов, SHA-256 digest фиксированной длины |
| Recent transition | Один before и один after frame; их window IDs, provenance/debug strings и frame IDs/provenance/debug ≤256; ACTION metadata также проверены |
| NFP topology/time | Rank ≤16, неотрицательные scalar integers ≤64 bits; values/frame ≤4096 по default config |
| ExecutionProvenance | Фиксированный frozen набор status/source ID/occurrence/action ID/tick/signal ID/source ref/pending ID/source proposal ID/source created-at; strings ≤256, integers ≤64 bits |
| Source execution (вход validation) | Проверяются detail, source_experience_id, occurrence, signal refs/integers, nested target_core record kind/proposal ID/profile/created-at и scalar metadata; oversized input отвергается до reservation |
| Frozen delivery events | Ровно два на envelope; все session/source/stream/event/occurrence/native_refs strings ≤256, native_refs count ≤2; scalar counters/ticks ≤64 bits, snapshot shape из 2 dimensions, values ≤default 4096; source_timestamp=None |
| Factory evidence/effect | Context/action должны ссылаться на проверенные source NFP, source transition/ticks совпадать; evidence/effect/source/endpoint IDs ≤256; effect values и topology/scalars ограничены |
| Grouper | ≤8 candidates/evidence; хранит только уже проверенные evidence, без raw execution |
| Proposal/request | Не более одного зафиксированного proposal и одного request; support IDs ≤8, representative — реальный evidence, request NFP происходят из проверенного source |
| Writer result/readback | По одному typed result; reason/record IDs ≤256 проверяются до удержания. Matching persisted record соответствует bounded request; v1 metadata/defaults формируются существующим builder/writer |
| STOP diagnostic | Один frozen объект; bounded occurrence/digest и фиксированные reason/error category |

Envelope больше не удерживает raw execution, target_core или predicted_effect.
Проверенная projection сохраняет необходимые apply/source identities; неиспользуемые
record descriptors не копируются. Вложенные proposal ID и created-at проверяются
до проекции: oversized provenance не обрезается и не публикуется в неполном виде.
Window-level metadata и native_refs также больше не являются пропусками бюджета.

Эти bounds относятся к данным, принимаемым в acquisition state, а не к общему
числу байтов Python heap. Session и writer остаются explicitly owned caller objects; owner хранит только
weak references к ним. Owner не сканирует произвольный object graph и не очищает
существующий session journal/records после отказа. Raw execution может оставаться
в session record, пока session удерживается другими владельцами; acquisition
больше не продлевает этот жизненный цикл. Подробности retention correction ниже.
Строки ограничены числом символов, значения — количеством; строгий byte-level
memory budget, hard real-time deadline и preemption не заявляются.

### Correction проверки

Предыдущий correction pass: 32 уникальных targeted tests PASS (18 исходных + 14);
актуальный retention pass и его 40 targeted PASS описаны ниже.
Исходные reproductions теперь закреплены постоянными regression tests:

- observe exception до мутации: reservation=1, envelopes=0, candidates=0, STOP;
- observe после мутации: reservation=1, envelopes=0, tentative candidate support=1,
  повтор и promotion запрещены, CREATE calls=0;
- builder exception: единственный proposal:000001 с неизменным support, request=None,
  make_proposal calls=1, builder calls=1, CREATE calls=0;
- nested source_proposal_id длиной 1 000 000 → явный stopped_metadata_budget,
  нет envelopes/reservations/candidates;
- metadata boundary 256 принимается без raw execution/target_core references;
  длина 257, oversized detail/source ID/created-at/native refs/window metadata
  отвергаются без усечения provenance;
- conflict/resource STOP → поздний timeout и все публичные вызовы не заменяют
  frozen diagnostic; timeout без предшествующей ошибки устанавливает свой STOP;
- factory/proposal/reconciliation exceptions и oversized writer/recovery diagnostics
  оставляют определённое terminal state, без скрытого retry;
- обычный acquisition → CREATE → fresh reconciliation/retrieval остаётся PASS.

В отдельной temporary validation copy с идентичными исходниками запущены targeted
suite и 11 релевантных regression suites из таблицы выше: от
nfp_remembered_action_guarded_execution до nfp_native_feedback_apply включительно.
Результат предыдущего correction: **32 targeted + 141 regression = 173 уникальных tests PASS**.
Дополнительные повторы одного и того же suite в это число не включены.
Stage 1 AST audit: 7 writers, boundary violations=0. ECHO/DAR code не менялся;
исторические 74 PASS этих четырёх suites не добавлены к текущему correction count.
Все Python вызовы correction используют одновременно `-B` и
`PYTHONDONTWRITEBYTECODE=1`; переменная наследуется subprocesses.

Полный inventory/SHA-256 всех 12 Production Memory файлов и directory inventory
совпали с началом correction; новых bytecode/lock/manifest/service файлов и каталогов
нет. Syntax, whitespace и точный scope трёх новых RND-021 файлов проверены.
Stage 1/2, writer, schema v1, Heart, ShortMemory, action guard, ECHO/DAR, legacy,
selection и веса не изменялись. Substrate baseline FAIL не запускался и не исправлялся.
HEAD `3f420bb03b3b9382828456904de5b193a9c08760`, ветка main, три прежних untracked
файла RND-021; staging/commit/remote/tags отсутствуют. **Исторический STOP FOR RE-REVIEW; заменён текущим CLOSED.**


## Targeted correction: session retention boundary

Устранён подтверждённый P2 `owner → session → records → raw execution`.
Вместо сильной ссылки используется `weakref.ref(session)` без callback.
Доступ к session берётся во временную локальную переменную только на время
admission; owner не сохраняет компоненты, bound methods, session callbacks или
closures, содержащие runtime history. Production-код не вызывает `gc.collect()`.

Узкая проверка остальных путей обнаружила потенциальный обход через
`owner → writer → failure_hook → session`: произвольный diagnostic/fault hook
может замыкать session. Поэтому writer также хранится через weakref без callback.
Это устраняет путь целиком, без произвольного обхода Python object graph и без
изменения NFPExpSMCreateWriter. Caller должен удерживать writer до окончания CREATE;
его утрата вызывает stopped_writer_unavailable до попытки записи, без нового writer
или альтернативной authority. Private `_writer` property только разыменовывает
weakref для существующих диагностических/fault-injection тестов и ничего не кэширует.
Тестовый owner явно удерживает свои writer fixtures независимо от acquisition.

### Обращения к session по фазам

| Фаза | Доступ / сохраняемые данные |
| --- | --- |
| Constructor | Валидация типа, bounded session/source IDs и isolation paths компонентов; сохраняются только strings, пять immutable Path values и weakref |
| admit | Временный strong borrow живой session; exact retained identity, records, Heart/world/age, execution status/pending/signal и delivery provenance проверяются как прежде |
| Successful admission | Сохраняются bounded immutable envelope/evidence/projection, reservation и `last_admission_tick`, снятый с проверенной Heart boundary; session/raw execution не сохраняются |
| seal | Закрытие admitted set; доступ к session не нужен |
| prepare | Existing grouper/builder получают frozen support и tick последнего успешного admission; request ID использует проверенный source scope snapshot |
| CREATE / reconciliation | Временный strong borrow живого writer; текущие writer paths/policy и сохранённые component path values проверяются без доступа к session |
| diagnostics | Frozen STOP и bounded provenance; никаких session/exception/traceback references |

`proposal.created_active_tick` теперь явно относится к сохранённой acquisition
boundary последнего успешного admission, а не к более позднему значению runtime
clock при prepare. Этот tick наблюдён при проверке живой session, ограничен 64 bits,
не реконструирован из UUID и не выдаётся за новое external observation. Порядок
T→T+1 исходных transitions не меняется. Scope mismatch живой session отвергается.

Если session исчезла до нового admit, устанавливается stopped_session_unavailable:
factory/grouper не вызываются, сохранённые UUID не заменяют живой source binding.
Если evidence уже зафиксированы, seal/prepare/CREATE не разыменовывают session:
сохранённого проверенного набора достаточно для explicit handoff. Caller может
завершить acquisition после освобождения source session, пока writer жив и обе
CREATE authority gates выполнены. Новый admit после утраты session терминально
закрывает run, сохраняя предыдущие evidence и первую причину STOP.

Owner-held данные ограничены прежними budgets плюс фиксированными source IDs,
path values, одним admission tick и двумя weakref objects. Session-owned данные
по-прежнему подчиняются собственному retention contract. Другие владельцы могут
продолжать удерживать session, raw execution или hook; их освобождение и глобальный
Python heap byte bound не обещаются. Исключения по-прежнему передаются caller,
а owner не сохраняет exception/traceback. Локальная временная ссылка во время
проверки или CREATE допустима; постоянных strong runtime-history paths нет.

### Retention/lifecycle проверки

Добавлены 8 постоянных tests; прежние 32 test method bodies не изменены:

- Test A / исходный P2 reproduction: после успешного реального admission и удаления
  внешнего session reference session и все raw execution освобождаются по weakrefs,
  хотя owner, immutable transition, projection и sensor provenance остаются живы;
- Test B / исходный oversized reproduction: source_proposal_id длиной 1 000 000
  явно отклонён, после удаления caller reference session/raw execution освобождены,
  owner остаётся в stopped_metadata_budget без envelopes/reservations;
- session исчезла до admission: явный STOP без factory и реконструкции события;
- два настоящих evidence сохранены, session исчезла: seal → prepare → authorized
  CREATE → fresh authoritative readback и отдельный retriever PASS; специальная
  ловушка подтверждает отсутствие любого session dereference на этих фазах;
- prepared request после утраты source сохраняет proposal/evidence identity,
  отдельное разрешение test owner и denied policy по-прежнему обязательны;
- новый admit после утраты source сохраняет ранее принятый envelope и первый STOP;
- conflict → source GC → timeout/public calls не заменяют первичную диагностику;
- writer fault hook замыкает session: после удаления внешних writer/session references
  оба объекта и raw execution освобождаются; owner не удерживает hook косвенно,
  CREATE завершается stopped_writer_unavailable без попытки записи.

`gc.collect()` используется только в этих диагностических тестах.
Исходный P2 reproduction отдельно повторён в temporary validation copy: в обеих
ветках session/raw execution освобождены **при ещё живом acquisition owner**.
Никакие необходимые evidence/provenance ради этого не удаляются.

Текущий результат: **40 targeted + 141 regression = 181 уникальный PASS**.
Все 12 suites запущены в isolated validation root с
`PYTHONDONTWRITEBYTECODE=1 python -B`, включая наследуемое окружение subprocesses.
Повторы suites и отдельные lifetime probes не прибавлены к unique PASS count.
Релевантная regression — те же 11 native/ShortMemory/evidence/ExpSM/Stage 1/2 suites,
что в предыдущем correction; Stage 1 audit: 7 writers, boundary violations=0.

Syntax/whitespace/`git diff --check`, scope ровно трёх новых RND-021 файлов,
inventory/SHA-256 всех 12 Production Memory файлов и directory inventory проверены.
Новых Memory файлов/каталогов/bytecode нет, веса неизменны. Исходные session,
ShortMemory, Heart, guarded execution, grouper, builder, writer и Stage 1/2 не менялись.
Substrate baseline FAIL не запускался и не объявляется PASS.
Ветка main, HEAD `3f420bb03b3b9382828456904de5b193a9c08760`, три прежних untracked
файла. **Исторический STOP FOR TARGETED REVIEW / OPEN; заменён текущим CLOSED.**
На этой промежуточной точке commit/remote/tags и RND-022 отсутствовали.


## Final closure — CLOSED

Вердикт координатора: **ACCEPTED FOR CLOSURE**. Все обнаруженные P2/P3 исправлены;
дополнительные production-изменения не требуются. Текущий статус RND-021 — **CLOSED**.
Исторические OPEN/STOP FOR REVIEW выше не являются текущим статусом.

Итоговые гарантии:

- Exact owned-world execution → actual observation T+1 → retained ShortMemory
  transition binding; UUID/materialization alone не являются proof of apply.
- Immutable bounded acquisition envelope и ExecutionProvenance; occurrence/digest
  reservation до factory/grouper, без повторного support после исключения.
- Terminal STOP при неопределённой мутации внешнего компонента; proposal identity,
  representative и support фиксированы перед builder, первая причина STOP неизменна.
- Owner-held metadata ограничены числом объектов/values и длинами metadata;
  строгий Python heap byte bound не заявляется.
- Session и writer удерживаются только через weakrefs без скрытых strong paths
  к runtime history, callbacks или traceback; session-owned retention не меняется.
- Caller владеет lifetime session до admission и writer до CREATE. Проверенный
  набор позволяет завершить seal → prepare → CREATE после освобождения session.
- CREATE требует отдельной test-owner authorization и allow_expsm_commit;
  существующие builder → writer, одна attempt, без автоматического retry и обходов.
- Fresh authoritative readback проверяет writer-owned запись в isolated ExpSM.

Ограничения сохраняются: trusted isolated synthetic experiment; provisional
observed association, не causal fact; RAM-only без durable dedup/restart recovery;
нет autonomous exploration, автоматического learning hook или production publication.
Substrate baseline FAIL остаётся открытым: не исправлен и не объявлен PASS.

Closure validation: Python-исходники побайтово совпадают с temporary validation
версией, прошедшей **40 targeted + 141 regression = 181 уникальный PASS**.
Меняется только статус/итог документации; полная регрессия повторно не запускалась.
Syntax, whitespace, полный staged diff и точный scope трёх файлов проверяются перед
разрешённым локальным коммитом. Полный inventory/SHA-256 всех 12 Production Memory
файлов и каталогов неизменен; новых bytecode/lock/manifest/service файлов нет.
Production-веса, Stage 1/2 и существующие tracked компоненты не менялись.

Разрешён единственный локальный commit:
`feat(learning): add bounded native experience acquisition`.
Его scope: `clc/experience/bounded_native_acquisition.py`,
`tools/verify_bounded_native_acquisition.py`, этот документ.
Closure выполняется на main от исходного HEAD
`3f420bb03b3b9382828456904de5b193a9c08760`; hash closure commit доступен в Git history.
**STOP: RND-022 не начат; remote-операции и tags не выполняются.**
