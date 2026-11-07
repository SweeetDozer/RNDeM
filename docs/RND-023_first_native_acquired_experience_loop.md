# RND-023 — First Native Acquired Experience Loop

Дата: **2026-11-07**. **CLOSED — ACCEPTED FOR CLOSURE.**
Architecture review и final targeted provenance review приняты координатором.
Актуальный итог — раздел «Final closure — CLOSED» в конце документа.
История first pass, двух P2, corrections и review checkpoints ниже сохранена;
исторические OPEN/STOP заменены итоговым CLOSED. Substrate baseline FAIL остаётся
отдельным открытым ограничением и не заменяется на PASS.

## Историческая контрольная точка первого pass

Дата: **2026-11-07**. **IMPLEMENTATION FIRST PASS / OPEN FOR REVIEW, не closure.**
Текущий checkpoint: **TARGETED CORRECTION выполнена, OPEN FOR TARGETED REVIEW**.
Результаты correction ниже заменяют исторический first-pass verdict.
Сквозной behavioral criterion подтверждён в isolated synthetic experiment.
Это не полноценное reinforcement learning, доказанное причинное понимание или
оптимальная стратегия. Следующий этап не начат; commits, tags и remote-операций нет.

Исходные: `main`, HEAD `2652353f9417dc73d945c6679de49cecd087759b`.
RND-020/021/022 изучены вместе с текущими API. В отличие от ожидаемого чистого
дерева до начала присутствовал untracked `docs/sf4.py`: он сохранён побайтово,
не является частью RND-023.

## Реализуемость и реальная цепочка

Проверены четыре совместимости: empty store допускает RND-022 execution;
несколько round-robin действий дают независимые occurrences; exact context/action
с одинаковым actual delta группируются RND-021; builder defaults v1 проходят
неизменённые retrieval/activation/selection. Фундаментального integration gap нет.

Отдельный driver: `scenarios/first_native_acquired_experience_loop.py`.
Behavioral owner/verifier: `tools/verify_first_native_acquired_experience_loop.py`.
Все компоненты создаются с явными temporary paths; новый world, selector, writer,
память и automatic Heart acquisition hook не вводятся.

```text
empty temporary ExpSM (experience={}, reflexes={})
 → NativeDeliverySession, explicit exploration config + test-owner authorization
 → owned world snapshot → VisualFieldTransducer → current external NFP context
 → empty native retrieval → SyntheticExplorationPolicy.issue, round robin
 → existing coordinator.execute_exploratory
 → topology/materialization → ModeActionGuard → ActionTransducer
 → SyntheticClosedLoopVisualWorld.apply_actuator_signal, pending occurrence
 → next native pulse, actual owned-world sensor T+1
 → ContextMemoryManager → RecentCausalTransition → ShortMemory
 → explicit BoundedNativeAcquisition.admit on ALL retained transitions
 → existing evidence factory/extractor/grouper, min_support=2
 → seal → full-set conflict check → prepare (one supported group)
 → separate explicit test-owner authorization → policy-gated CREATE (one attempt)
 → fresh authoritative reconciliation CONFIRMED_PERSISTED
 → new isolated control session / fresh retriever
 → activate_native → select_native → remembered execution coordinator
 → same guard/transducer/apply path → real actual T+1
```

Training world — существующий synthetic world `(1,2)`, начальная позиция `(0,0)`.
Разрешены команды `((0,1),(1,0))`; round robin с бюджетами 3 intents / 3 actions.
Нет hidden-state callback, целевого effect, reward, заданного learned record или
remembered motor prior. Default selector threshold `.35`; retrieval exact `1.0`,
как в RND-021. Эти параметры фиксируются при сборке, не меняются после результата.

| Tick | Native действие | Реальное наблюдение следующего tick |
| --- | --- | --- |
| 0 | exploratory right | T=1: `(0,1)` |
| 1 | exploratory left | T=2: `(1,0)` |
| 2 | exploratory right | T=3: `(0,1)` |
| 3 | owner PAUSE после observation | нового действия нет |

ShortMemory удерживает все три transitions. Ни один training transition не
конструируется вручную. Factory самостоятельно вычисляет actual deltas: два
right occurrences дают согласованный `(-1,+1)` в повторившемся context; left
переход образует другую группу. Admission не отбирает заранее желаемый effect:
передаётся весь retained set. Support групп — **2 и 1**. Поддержанная группа
определяется только по `support_count >= 2`; неоднозначность не даёт request.

ExpSM остаётся пустой после training, admission, seal/prepare и CREATE без
отдельного owner authorization. Только `create(test_owner_authorized=True)` с
`mutating_memory` policy создаёт record **`1`**; результат `CREATED`, отдельный
fresh readback — `CONFIRMED_PERSISTED`, exact record совпадает с writer response.
Повторный CREATE не выполняется. Source transition digests до/после acquisition
неизменны. Defaults v1: hits/misses=0, confidence/repeatability=.5.

## Единственное изменение production contract

В `clc/experience/bounded_native_acquisition.py` добавлен frozen scalar
`ExploratoryAcquisitionProvenance` и optional поле envelope. Оно сохраняет:

- exploratory intent ID, authorization ID, test-owner ID, configuration ID;
- настоящий execution occurrence ID;
- session ID и owned visual source ID;
- настоящий transition ID.

Проверка выполняется после прежнего RND-021 execution/sensor/retention binding,
до reservation/factory/grouper admission. Требуются exact issued intent object
в diagnostics живой session policy; admitted/guarded/applied без denied/uncertain;
совпадение outcome, occurrence, текущего authorization/configuration/session,
context window/tick и реально исполненной команды. Source-less execution без
intent отвергается. Наличие фиктивного remembered source, prediction или target
core у exploratory execution также отвергается. Для remembered acquisition
старый путь сохранён, projection=None.

Каждый scalar — непустая строка до 256 символов. Не более 8 projections по
существующему evidence budget: до 16384 символов дополнительных scalar данных,
без raw result, policy, session, world или callbacks. Это не строгий heap byte bound.
После successful admission session может быть освобождена: projection остаётся,
prepare/CREATE используют прежний RND-021 handoff. До admission утрата session
терминально запрещает acquisition. Lifetime и writer ownership не изменены.

Новых evidence IDs и execution authority нет; persisted v1, NFP, ShortMemory
schema, coordinator, policy, guard и session не менялись. Проекция — проверяемый
RAM audit в доверенном serialized experiment, не криптографическое доказательство
и не durable authorization. Произвольная согласованная порча Python runtime
администратором за пределами контракта. Provisional observed association не
становится causal fact; support не повышает operational confidence.

## Независимые controls и ablation

Все три контроля получают новые world/manager/registry/ShortMemory/retriever/
activation/selector/coordinator и отдельные temporary stores. Общее: world `(1,2)`
с позицией `(0,0)`, external input `(1,0)` при T=0, `active` mode, тот же guard,
retrieval=1.0, selector=.35 с defaults, ShortMemory `(8,10)`, journal=128,
Heart=2 ticks, PAUSE при T=1 после actual observation. Exploration config и
authorization отсутствуют во всех controls; fallback невозможен.
Training требует 4 ticks и PAUSE при T=3 для трёх exploratory executions.

| Episode | Store | Eligible selected source | Physical actions | Actual T+1 |
| --- | --- | --- | ---: | --- |
| C0 EMPTY | пустой | отсутствует | 0 | позиция `(0,0)` |
| C1 ACQUIRED | только fresh-confirmed record `1` | **`1`** | **1** | позиция `(0,1)`, recent bound к новому occurrence |
| Ablation | независимая копия C1, удалён только `1` | отсутствует | 0 | позиция `(0,0)` |

C1 читает заново сериализованный store новым authoritative retriever. Spies
только наблюдают реальные production calls, не подменяют returned objects:
retrieval candidate.source=`1` → activated.source=`1` → selected.source=`1` →
execution.source=`1`. Дополнительно сверены retrieval candidate ID и activation
ID выбранного request, continuity target core и execution; guard_passed=True,
status=`ACTION_EXECUTED_OBSERVATION_PENDING`, exploratory_intent=None.
В следующем pulse retained actual transition имеет execution occurrence этого
действия, before/after различаются. Совпадение одной motor command недостаточно:
проверяется полная source chain. Активация при defaults равна `.775`, выше `.35`;
никакой настройки весов для выбора не потребовалось.

Ablation удаляет ровно writer-owned ID из независимой копии store; остальные
данные и episode configuration сохраняются. Возврат к C0 подтверждает влияние
наличия acquired record на выбор в этом контролируемом эксперименте, не общую
причинную модель мира.

## Негативные проверки

Новый verifier: **10 unittest methods PASS**, с несколькими fault arms:

1. Полная положительная цепочка, CREATE authorization gate, C0/C1/ablation,
   fresh source identity и no repeated CREATE.
2. Один occurrence/replay: duplicate не увеличивает support, request/CREATE нет.
3. Missing authorization и подмена authorization/test-owner/configuration ID:
   envelope/evidence не допускаются.
4. Подмена intent ID, occurrence ID, transition ID, удаление intent и подмена
   occurrence в genuine execution record: admission отвергается.
5. Утрата session до admission запрещена; освобождение после admission сохраняет
   bounded provenance и позволяет authorized CREATE без ссылки на session.
6. Missing actual T+1 и guard denial: нет retained evidence/CREATE.
7. Неопределённый apply после реальной мутации: один apply, terminal stop,
   resume не повторяет его, evidence/CREATE нет.
8. Full-set conflict: 5 native exploratory actions; реальные sensor fault arms
   создают конфликт при уже поддержанной группе. Все 5 evidence допускаются,
   `seal/prepare` отвергает весь набор (`stopped_effect_conflict`).
9. Policy `safe_demo`: `DENIED_BY_POLICY`, store пуст, повторной попытки нет.
10. `READBACK_FAILED`: fresh recovery подтверждает persisted либо фиксирует
    malformed store как unresolved; ни один исход не вызывает CREATE retry.

Fault injection применяется только в отрицательных arms (sensor/apply/auth/IDs/
readback). В positive training и controls world dynamics и returned API objects
не подменяются. Остальные budgets, retention/occurrence binding, no blind retry,
recovery и failure contracts повторно проверены RND-021/022 regression suites.

## Проверки и количественные результаты первого pass (история)

Все Python-процессы: `PYTHONDONTWRITEBYTECODE=1 python -B`, включая subprocess
проверки short memory. Writable fixtures/stores/logs только в `/tmp`.
Новый verifier выполнялся в рабочем checkout с полностью явными temporary paths.
Каждая regression suite выполнялась в своей отдельной свежей validation copy:
`/tmp/rnd023-validation-ldnuwwll`; логи и `results.json` находятся там же.
Новый финальный targeted log: `/tmp/rnd023-target.log`.

| Verifier tools/verify_*.py | Tests | Result |
| --- | ---: | --- |
| first_native_acquired_experience_loop | 10 | PASS |
| bounded_native_acquisition | 40 | PASS |
| synthetic_exploratory_bootstrap | 41 | PASS |
| nfp_expsm_operational_retrieval (включая native activation/selection) | 5 | PASS |
| nfp_remembered_action_guarded_execution | 8 | PASS |
| native_session_b1 | 5 | PASS |
| native_heart_b2 | 23 | PASS |
| native_bounded_delivery | 18 | PASS |
| nfp_context_short_memory | 24 | PASS |
| short_memory_expsm_evaluation | 10 | PASS |
| persistent_nfp_expsm_representation | 10 | PASS |
| nfp_expsm_policy_gated_create | 8 | PASS |
| expsm_persistence_stage1 | 9 | PASS |
| nfp_native_feedback_replay_idempotency | 15 | PASS |
| nfp_native_feedback_apply | 11 | PASS |
| scoring_selection_semantics | отдельный script, не unittest count | PASS |
| minimal_activation_pattern_substrate | baseline audit | **FAIL, известный** |

Всего **10 targeted + 227 regression = 237 уникальных unittest PASS**, плюс
отдельный scoring/selection script PASS. Повторные targeted runs не суммируются.
Substrate FAIL воспроизведён: прежние runtime imports в `native_bounded_delivery.py`,
`native_heart_session.py`, `native_session.py`. Новых violators нет. FAIL не
исправлялся и не объявляется PASS. Stage 1 AST: 7 writers, 7 mutation paths,
0 direct-write / transaction / preflight / store-order violations. Stage 2 replay
и feedback suites PASS; Stage 1/2 реализации не изменены.

Syntax проверяется через AST без создания bytecode; whitespace через
`git diff --check` и отдельную проверку новых файлов. Индекс пуст.

## Production Memory safety и scope первого pass (история)

До первого изменения снят SHA-256 inventory всех checkout files, в том числе
всех 12 Production Memory files, directory inventory и 119 ignored `.pyc`:
`/tmp/rnd023-baseline.json`. Результат: `/tmp/rnd023-final-safety.json`. Финальное сравнение PASS: изменения ограничены ровно четырьмя
RND-023 путями ниже; прежний `docs/sf4.py` остаётся побайтово прежним.
Нет Production Memory writes, новых memory directories, lock/manifest/service/
bytecode файлов. Веса и Stage 1/2 неизменны.

Directory inventory: `Memory/AKBSM`, `Memory/AKBSM/DB`, `Memory/ExpSM`, `Memory/WL`.
SHA-256 исходного и финального содержимого:

| Production Memory file | SHA-256 |
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

Git scope RND-023 — ровно четыре пути:

- modified `clc/experience/bounded_native_acquisition.py`;
- new `scenarios/first_native_acquired_experience_loop.py`;
- new `tools/verify_first_native_acquired_experience_loop.py`;
- new `docs/RND-023_first_native_acquired_experience_loop.md`.

Финальные branch/HEAD: `main`, `2652353f9417dc73d945c6679de49cecd087759b`.
Git status: один modified, четыре untracked (три RND-023 + исходный `docs/sf4.py`).
Staging пуст. Никаких commits, remote, tags или следующего этапа.

## Остаточные ограничения и STOP

Первый loop подтверждён только для доверенного serialized isolated synthetic
owner, finite experiment и одного supported association. Нет автономного
определения полезности, reward optimization, production publication,
автоматического обучения в NativeHeartSession, durable provenance/dedup/restart
recovery или криптографического authorization proof. V1 не фильтрует provisional
records; поэтому все приобретённые записи остаются temporary experiment data.
Непредсказуемые внешние callbacks не получают preemption; текущий in-process
lifetime contract RND-021 сохраняется. Substrate baseline FAIL остаётся открытым.

**STOP FOR FIRST-PASS REVIEW. RND-023 OPEN, не CLOSED.**


## Targeted correction — provenance integrity и bounded identities

Дата: 2026-11-07. Два P2 architecture review исправлены. **Не closure; STOP FOR
TARGETED REVIEW.** Никаких commits, remote-операций, tags или следующего этапа.
Первоначальные 237 PASS выше — история, не прибавляются к текущему прогону.

### P2-A: классификация по согласованным источникам

Причина: ветка `intent is None` принимала любой ненулевой source ID за remembered
origin и обходила exploratory validation. Source ID сам по себе не является
доказательством remembered execution.

Теперь owner получает diagnostics живой SyntheticExplorationPolicy, проверяет
policy/session scope и доступность bounded tuple (не более существующих 64
entries). Поиск occurrence ограничен diagnostics **той же session**, затем
сверяются exact issued intent object и occurrence вместе. Чужая historical
session даже с тем же текстовым occurrence не классифицирует текущий execution.
Неверный policy scope и недоступные diagnostics не дают успешной классификации.

Если текущий occurrence отмечен exploratory policy, потеря intent либо попытка
заявить remembered source отвергаются. Exploratory branch по-прежнему требует
admitted/guarded/applied без denial/uncertainty, правильные authorization/owner/
configuration/context/tick/command и отсутствие remembered source/prediction/core.
Отсутствующая/вытесненная history не заменяется reconstruction по UUID.

Remembered branch требует отсутствие текущего exploratory occurrence, настоящий
непустой bounded source и typed SerializedObservedEffectV1. Это соответствует
существующему MaterializedNFPActionIntent: его публичный конструктор требует
source и typed predicted effect, а coordinator переносит их в result. Штатного
non-exploratory source-less producer в NativeDeliverySession не обнаружено.
Source-less/no-intent executions и наличие только source намеренно отвергаются;
это явное tightening admission, не новая execution authority. Криптографической
аутентификации произвольно согласованной порчи всех runtime objects нет.

### P2-B: только exact built-in identity strings

Причина: `isinstance(value, str)` принимал subclasses, сохраняющие произвольные
attributes. Frozen dataclass не делал вложенные ID объекты простыми scalar.

Новый локальный validator требует `type(value) is str` и длину 1..256. Проверяются
все восемь полей: intent, authorization, test-owner, configuration, occurrence,
session, source и transition IDs. Frozen ExploratoryAcquisitionProvenance также
проверяет это в `__post_init__`: даже прямой constructor не сохранит subclass.
Строки не преобразуются, не усекаются, IDs и значения не подменяются.

Связанные значения проверяются до их удержания/копирования: cached session/source
scope — в owner constructor; transition/occurrence types — до digest/asdict;
сравниваемые intent/auth/config/session/context identities — перед validation
comparison. Прежние metadata overflow STOP для обычных строк сохранены.
Глобальный `_texts_fit`, RND-022 policy и схемы NFP/ShortMemory/ExpSM не менялись.
Не вводились heap scanner, serializer, diagnostics snapshot или дополнительные
сильные ссылки на runtime objects.

### Exception safety и ранее принятый набор

Порядок остаётся: existing execution/sensor/retention binding → classification/
provenance validation/construction → occurrence reservation → factory → grouper.
Ранний type check transition IDs выполняется до digest, не создаёт evidence.

Refusal не добавляет reservations/envelopes и не меняет support. Предыдущий
admitted set сохраняется без rollback приватного grouper. Исключение diagnostics
или projection constructor фиксирует `stopped_provenance_error` с прежними bounded
error categories и повторно передаётся caller; первая STOP reason сохраняется.
Ни admission retry, ни prepare/CREATE после такого STOP невозможны. Исключения и
tracebacks owner не удерживает. Input budget по-прежнему расходуется на вызов.

### Original reproductions: до / после

| Reproduction | До correction | После correction |
| --- | --- | --- |
| Genuine exploratory executions 0/2: intent=None, fabricated source; authorization=None | admitted/admitted, support=2, projections=None, CREATE created | оба отвергнуты; intervening unauthorized transition тоже отвергнут; reservations/envelopes/candidates пусты, request/CREATE отсутствуют |
| 12-символьный str subclass с payload 1 МБ и ссылкой на world | 3 admitted, исходный object в projection; world удерживается после session release | 3 refusal; owner не удерживает ID/payload/world; weakrefs ID/world после gc пусты |
| Обычные built-in strings | genuine exploratory admission | 3 admitted; session/world освобождаются, frozen audit сохраняется, authorized CREATE и CONFIRMED_PERSISTED работают |

Permanent negative tests используют genuine execution/transition/sensor paths;
fault injection меняет только соответствующие origin/diagnostic/identity поля.
Обычный training path и controls не изменены. Integration driver
`scenarios/first_native_acquired_experience_loop.py` побайтово прежний.

### Постоянные regression cases и текущие результаты

Новый verifier теперь содержит **22 unittest methods PASS**: прежние 10 плюс
12 correction tests с несколькими arms. Покрыты оригинальный bypass, потеря
history/policy, подмена одного occurrence при сохранении prior admitted evidence,
wrong scope/occurrence/intent session, genuine remembered source с unrelated
historical collision, все 8 identity fields (256 PASS, 257/empty/subclass refusal),
публичные auth constructors с 256-символьными строками, payload/world retention,
constructor refusal для scope subclasses, transition/occurrence subclasses,
освобождение plain session/world и STOP при construction/diagnostics exceptions.
Прежний metadata overflow terminal STOP также отдельно сохранён тестом.

Полный positive loop снова даёт 3 actual evidence, группы support=2/1,
единственный authorized CREATE record `1`, CONFIRMED_PERSISTED и source continuity
retrieval → activation → selection → execution. **C0/C1/ablation = 0/1/0**, source
C1 ровно `1`, guard пройден, actual T+1 получен. Exploration во всех controls
выключен. Weights, thresholds, world dynamics, writer и selector не менялись.

Текущая регрессия повторяет 14 unittest suites таблицы первого pass с прежними
counts: **227 regression PASS**. Дополнительно scoring/selection script PASS.
Итого текущего checkpoint: **22 targeted + 227 regression = 249 уникальных
unittest PASS**. Повторные и исторические runs не суммируются. Substrate baseline
по-прежнему **FAIL** на прежних трёх runtime imports; новых violators нет.

Все Python-вызовы, включая subprocesses, выполнялись с
`PYTHONDONTWRITEBYTECODE=1 python -B`. Final targeted log:
`/tmp/rnd023-correction-target.log`; final regression logs/results —
`/tmp/rnd023-validation-u_nw3910`, launcher report —
`/tmp/rnd023-correction-regressions-final.log`. Regression copies проверяют ту же
финальную production implementation и неизменённый driver. Новые correction
cases выполнялись финальной targeted suite. Последнее расширение retention case
не меняет production code. Ранее выполненные повторения не добавляются к 249.

### Correction scope и safety

От correction checkpoint изменены ровно три файла: bounded acquisition,
RND-023 verifier и этот документ. Общий scope RND-023 остаётся четырьмя путями
первого pass; integration driver не менялся. Stage 1/2, writer, guard, session,
coordinator, policy, ExpSM v1, weights и остальные production files неизменны.
Syntax AST, whitespace и пустой staging проверены отдельно.

Baseline correction inventory: `/tmp/rnd023-correction-baseline.json`.
Inventory/SHA-256 всех 12 Production Memory files (таблица выше) и directory
inventory, 119 ignored baseline `.pyc` и все прочие checkout files совпали.
Финальный результат: `/tmp/rnd023-correction-safety.json` — PASS.
Новых lock/cache/manifest/service files в checkout нет. Writable fixtures/stores
и validation copies расположены только в isolated `/tmp` directories.

Фактический посторонний untracked файл — **`sf4.py` в корне**, SHA-256
`0e3190a815dd4e65ac768e586b04cd877d845c67e0641fdbddc7e232fbcec975`.
Его содержимое совпадает с historical `docs/sf4.py`, но location отличается.
Файл не перемещался, не удалялся, не восстанавливался и не менялся в correction;
в staging не добавлялся. Исторические упоминания старого location выше сохранены.

Branch `main`, HEAD `2652353f9417dc73d945c6679de49cecd087759b`.
Git: 1 modified + 4 untracked (три новых RND-023 файла и посторонний `sf4.py`),
staging пуст. Без commit/remote/tags. **STOP FOR TARGETED REVIEW, RND-023 OPEN.**


## Final closure — CLOSED

Дата: **2026-11-07**. **Вердикт координатора: ACCEPTED FOR CLOSURE. RND-023 CLOSED.**
Architecture review и final targeted provenance review завершены. Оба P2
исправлены и повторно проверены; новых блокирующих дефектов не обнаружено.
Дополнительные production-изменения для closure не потребовались. В closure
меняется только этот документ; Python-файлы побайтово совпадают с принятой версией.

### Подтверждённый результат

- Initial temporary ExpSM полностью пуста: experience={}, reflexes={}, без
  motor priors, целевого effect или заранее подготовленного learned record.
- Первые right/left/right действия инициирует существующая RND-022 policy с
  отдельной test-owner authorization. Выполнение идёт через общий guarded
  coordinator/topology/transducer/apply path; driver не вызывает apply напрямую.
- Actual T+1 получены настоящим owned-world sensor. Manager/ShortMemory создают
  и удерживают три transitions с независимыми execution occurrences.
- Все три evidence передаются в bounded acquisition. Existing extractor
  вычисляет observed effects; два согласованных evidence дают support=2.
  Третье evidence не исключается, full-set conflict rejection сохранён.
- Единственный explicit authorized policy-gated CREATE создаёт writer-owned
  persisted record **`1`**. Fresh authoritative readback подтверждает
  CONFIRMED_PERSISTED; автоматического CREATE или повторной попытки нет.
- Независимые одинаково настроенные controls с выключенным exploration дают
  **C0/C1/ablation = 0/1/0**. Source **`1`** непрерывен через fresh retrieval →
  activation → selection → guarded execution; мир изменяется, actual T+1 наблюдён.
  Удаление только acquired record возвращает поведение к C0. Приобретённый опыт
  изменяет последующий remembered selection при одинаковом начальном input.
- Exploratory/remembered classification требует согласованных session/occurrence
  diagnostics, genuine issued intent и authorization. Поддельный source не
  превращает exploratory execution в remembered admission; unrelated historical
  session не создаёт ложного match. Утраченная history не реконструируется по UUID.
- Все восемь provenance IDs — **exact built-in strings**, длиной **1–256**:
  intent, authorization, test-owner, configuration, occurrence, session, source,
  transition. Constructor и admission отвергают subclasses без усечения или
  подмены ID. Cached scope и transition types проверены до retention/digest.
- Refusal/validation/construction происходят до reservation/factory/grouper:
  rejected evidence не меняет support. Terminal STOP сохраняет первую причину,
  блокирует promotion/CREATE и не маскирует первоначальное исключение. Resource
  bounds, weak session/writer ownership, single pending slot, stop-on-uncertainty
  и отсутствие blind retry сохранены. Session/world освобождаются и после
  успешного admission, и после отказа nested identities.

### Final review и проверенная версия

Final targeted provenance review независимо повторил **22 targeted + 227
regression = 249 уникальных unittest PASS**, плюс отдельный scoring/selection
script **PASS**. Полные logs/results: `/tmp/rnd023-final-review-validation-z173pfwm`,
`/tmp/rnd023-final-review-regression-results.json`; targeted log:
`/tmp/rnd023-final-review-target.log`. Исторические и повторные прогоны не
прибавляются к 249.

Четыре дополнительных review probe arms отражаются отдельно: malformed diagnostics,
diagnostics exception и projection-construction exception после уже принятого
support=2 сохраняют прежний набор, фиксируют STOP, запрещают CREATE, сохраняют
original exception и освобождают world; direct projection tests всех восьми
полей не вызывают subclass hooks до exact-type refusal.
Reproducer/results: `/tmp/rnd023-final-review-probes.py` и
`/tmp/rnd023-final-review-probes.json`. Они не увеличивают unittest count.

Перед closure сверены все Python-файлы checkout со свежими validation copies
final review; совпадение побайтовое. Три Python-файла RND-023 имеют SHA-256:

| Python file | SHA-256 принятой версии |
| --- | --- |
| `clc/experience/bounded_native_acquisition.py` | `042d453a36b3de24d9b6ed76e12b8a4261c17d31d32395fd6f374cdf93f47fa9` |
| `scenarios/first_native_acquired_experience_loop.py` | `1fd185e2ad9ff8195262ddf2d5d1ee0ec83d8788d2667f3e29f7367880e5d545` |
| `tools/verify_first_native_acquired_experience_loop.py` | `cb26633726d99bda9c7b65ca026a6bac515bf44021cf1d39a88ff93b274b6e3d` |

В closure изменена только документация, поэтому регрессия не повторяется.
Все необходимые Python-запуски использовали `PYTHONDONTWRITEBYTECODE=1 python -B`;
writable fixtures и stores находятся исключительно в temporary isolation.
Syntax AST, whitespace, `git diff --check`, production diff и полное содержимое
трёх новых RND-023 файлов проверены. RND-021/022 execution behavior, guard, session,
coordinator, policy, writer, weights и Stage 1/2 не изменены. Acquisition boundary
усилен ровно описанным provenance contract.

### Сохранённые ограничения

- Только isolated trusted serialized synthetic experiment.
- Provisional observed association, не доказательство причинности или причинного
  понимания. Ablation подтверждает влияние наличия record на selection в этом
  эксперименте, не причинную модель мира.
- Нет learned utility/reward optimization или оптимальной стратегии.
- Нет automatic acquisition в Heart, production publication или production writes.
- Нет durable dedup/restart recovery, durable authorization proof или
  криптографической защиты от согласованной порчи всего Python runtime.
- Нет глобального Python heap byte bound или preemption внешних callbacks.
- **Substrate baseline FAIL остаётся открытым**: прежние runtime imports в
  native_bounded_delivery.py, native_heart_session.py и native_session.py.
  Он не исправлен и не объявляется PASS; новых violators нет.

### Closure safety и Git scope

Полный inventory/SHA-256 всех **12 Production Memory файлов** совпадает с HEAD и
таблицей выше. Directory inventory прежний: Memory/AKBSM, Memory/AKBSM/DB,
Memory/ExpSM, Memory/WL. Все **119 baseline ignored `.pyc`** сохранены побайтово
относительно принятого final-review snapshot; новых service/lock/cache/manifest
файлов или каталогов в checkout нет. Веса и Stage 1/2 неизменны.
Closure baseline: `/tmp/rnd023-closure-baseline.json`.

Полный staged diff и `git diff --cached --check` проверяются перед commit.
Staging/commit ограничены **ровно четырьмя путями**:

1. `clc/experience/bounded_native_acquisition.py`
2. `scenarios/first_native_acquired_experience_loop.py`
3. `tools/verify_first_native_acquired_experience_loop.py`
4. `docs/RND-023_first_native_acquired_experience_loop.md`

Посторонний **`sf4.py`** в корне — пользовательская заготовка будущего цифрового
подсолнуха Lite. Он остаётся untracked и не входит в staging/commit; его location
и bytes сохранены. SHA-256:
`0e3190a815dd4e65ac768e586b04cd877d845c67e0641fdbddc7e232fbcec975`.
Исторический location docs/sf4.py автоматически не восстанавливается.

Closure выполняется одним локальным commit на `main` от родительского HEAD
`2652353f9417dc73d945c6679de49cecd087759b`, message:
`feat(learning): integrate first native acquired experience loop`.
Идентификатор closure commit определяется Git history и итоговым отчётом.
После commit tracked working tree чистый; единственный допустимый untracked —
`sf4.py`. Никаких remote-операций, tags и следующего этапа.

**RND-023 CLOSED. STOP.**
