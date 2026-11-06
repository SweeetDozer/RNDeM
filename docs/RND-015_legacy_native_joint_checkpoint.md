# RND-015 — Совместный checkpoint legacy CLC и NFP-native RNDeM

Дата: 2026-11-06. Статус: **CLOSED — архитектурный review принят, design gates и финальные проверки пройдены**.

Контрольная точка подтверждена: `main`, HEAD
`c12cda8964f91b876f24e9a6de9e33c8da57533d`, исходное дерево чистое,
RND-010–014 CLOSED. Работа LOCAL ONLY: remote contact, fetch/pull/push,
merge и tags не выполнялись. После принятого review разрешён один локальный commit
семи согласованных файлов. Локальный ignored `AGENTS.md` прочитан.

Основания: [A→C architecture](RND-010_clc_native_integration_architecture.md),
[B1](RND-012_native_session_b1.md), [B2](RND-013_native_heart_b2.md),
[delivery](RND-014_native_bounded_delivery.md),
[inventory](RND-000_architecture_inventory.md),
[write authority, включая K6/K7](RND-110_memory_write_authority_audit.md).
Исторические результаты этих документов не засчитываются за новые проверки.

## Реализованная структура

Добавлены только тестовые
[harness/adapters](../tools/legacy_native_joint_checkpoint.py) и
[targeted verifier](../tools/verify_legacy_native_joint_checkpoint.py).
Production-файлы и утверждённые контракты не изменены. При закрытии дополнительно
изменены только четыре согласованных design allowlists и этот статусный документ.

`LegacyAdapter` сам создаёт `TemporaryDirectory`, копирует всю исходную Memory
и использует существующий fixture builder `_runtime_for_fixture`. Входы поступают
через реальные `feed_audio`, `feed_sensor`, `feed_image`; payload defaults и
преобразования соответствуют scenario runner. Tick остаётся аргументом feed.
Fixtures с synthetic summaries, private idle `tick` или другими non-feed inputs
отклоняются до создания runtime. Универсальный scenario runner поддерживает больше
видов fixtures; этот adapter намеренно проверяет только публичный feed boundary.

Пассивные instance wrappers наблюдают 12 методов из `RUNTIME_PHASE_MAP` и
`ContextOpsPool.drain`. Каждый wrapper вызывает исходный метод ровно один раз,
с исходными аргументами, и возвращает его результат. Они не вызывают `_run_tick`,
selector, guard или executor дополнительно. Для каждой фазы сохраняются tick,
phase ID, полные события и кандидаты до/после; отдельно — все FIFO drain batches.
`plain()` сохраняет значения без округления и без исключения полей.

`NativeAdapter` готовит три native records для visual `(1,4)` и правого ACTION
`(2,)`, как в B2 verifier, в другом `TemporaryDirectory`. Используются production
retriever, activation, selector, coordinator, guard, Context/ShortMemory и
`NativeDeliverySession`, наследующий неизменённый `NativeHeartSession` B2.
Пассивные World/Manager/Retriever/Short subclasses переиспользуются из B2 verifier:
они сохраняют реальные snapshots/apply/idle/query/retention calls. Factory не
переиспользует unittest lifecycle или assertions. Failure modes — существующие
синтетические fault injections этого fixture, а не изменение production execution.

Native `start/pause/resume/stop/step` делегируются session. `step()` не получает tick:
единственная native tick authority — Heart. `SyntheticTimeAdapter` остаётся владельцем
проверки соответствующего world advancement, без второго clock или ремонта ticks.

`JointLifecycle` исполняет конечный явный список `(adapter, operation, argument)`.
Допустимы только start/pause/resume/stop, legacy feed и native step. План проверяется
до dispatch, бюджет — 1–128 операций суммарно за жизнь driver. Результаты хранятся
раздельно. Нет автоподстановки входов, catch-up ticks, retry, background tasks,
общего `_run_tick` или неявной передачи данных между контурами.

Legacy start/pause/resume/stop — **только admission gate тестового adapter**:
у CLCRuntime такого production lifecycle API нет. Отклонённый feed не ставится
в очередь, resume не исполняет backlog, stop терминален. Native использует
настоящую lifecycle state machine Heart; driver не дублирует её состояния.

## Independent против joint

Две реальные fixtures:

- `real_input_repeated_audio_signal`: 6 audio feeds;
- `real_input_conflicting_sensor_signal`: 8 sensor feeds.

Каждая проверяется с пятью native конфигурациями: без sensory input, обычный
ACTION/observation, пустой native store, sensory flood, guard denial в consolidation.
Итого **10 differential combinations**. Для каждой выполняются независимые adapters
и те же inputs/5 native steps при чередовании под driver. Каждый legacy feed
сохраняет собственный tick, независимо от положения native step в плане.

Сравниваются без legacy-нормализации:

- все before/after phase traces и полные FIFO batches;
- regression summary: decisions/scores/sources, markers, audits, retention/views;
- полный inventory/size/SHA-256 обеих полученных временных legacy Memory.

Дополнительно реальный `run_scenario_fixture` даёт независимый baseline обеих
fixtures, сверенный с существующими checked-in phase snapshots. У adapter summary
поле `memory_safety` заполняется результатом runner: его внутренний summary builder
оставляет четыре значения None. Это не подмена behavioral fields; полная Memory
проверяется отдельным whole-tree inventory до/после suite.

Native differential сравнивает полные typed tick records, stop report, delivery
journal/counts/depths, queries, world samples/applies/idles/position, pending log,
ShortMemory и observer call order. Только UUID session scope, реально materialized
occurrences и delivery events переименовываются согласованным взаимно-однозначным
отображением. Оно сохраняет повторное использование ссылки и различие identities.
UUIDs генерируются `uuid4()` в production; их литералы не являются поведенческим
результатом между независимыми runs. Отдельные assertions проверяют UUIDv4,
уникальность occurrences и identity handoff внутри каждого run. Ticks, source IDs,
provenance, origin, values, topology, target core, statuses и diagnostics не скрываются.
Diagnostic timestamps не нормализуются: в сравниваемых traces их нет.

## Проверенные временные и причинные границы

Legacy сохраняет ровно 00–11 на каждый feed. Два feed с одинаковым caller tick
по-прежнему запускают два полных цикла; native idle не добавляет третий.
RAW_INPUT_WRITE после phase 00 виден phase 03 того же tick. Новые phase-06 events
отсутствуют у более ранней phase 03 и доступны следующему feed cycle.

Фактическая граница mechanism search уточнена по коду: phase 06 коммитит search
results, а следующий ActionProposer в phase 03 создаёт candidates по этим results.
У audio fixture проверена реальная ссылка `source_mechanism_search_id` на результат
предыдущего tick и отсутствие такой ссылки преждевременно. Sensor fixture не даёт
такого positive match; её отсутствие candidate не выдаётся за доказательство match.
Для обеих fixtures late-event visibility и differential traces проверены полностью.
FIFO batches после штатного добавления `_event_tick` методом ContextMemory.add_event
в точности воспроизводят итоговый список ContextMemory.events в исходном порядке.

Native нормальные ticks монотонны и согласованы с world: один apply **либо** один
idle на переход. Без sensor нет snapshot, query, NFP или ACTION. Новое observation
сохраняет EXTERNAL_SENSORY, source snapshot provenance и текущий Heart tick.
ACTION сохраняет ACTION_GENERATED, исходную topology и provenance=None; occurrence
не заменяется tick или selection ID. Observation T+1 завершает исходный occurrence
и сохраняется в ShortMemory до следующего apply. Последний completed observation
может не дать нового match: retention не требует следующего действия.

При отсутствии T+1 pending остаётся до overdue T+2; новый action не допускается
на старом sensory present. Pause не продвигает время, resume не создаёт catch-up;
stop сохраняет unresolved occurrence и не исполняет накопленные действия.
Legacy feed между native steps не меняет Heart/world/pending/query trace.
Legacy late results не подаются в native input; native observation не появляется
в legacy ContextMemory или active native-present API его manager.

Flood подаёт 100 optional samples на tick при sensory capacity=2,
dispatch budget=2, journal capacity=400. Protected consequence доходит в T+1,
occurrence сохраняется, observation обрабатывается раньше следующего action.
Overflow явно учитывается; optional samples не становятся authoritative sensory.
Ни idle, ни flood, ни остановка другого adapter не вызывают второй world apply.

## Изоляция и write authority

Production Memory используется только как read/copy source и для inventory;
она не передаётся runtime, registry или writer. Legacy root содержит копию всех
12 исходных файлов. Native root содержит собственные prepared ExpSM и manifest.
Все writable constructors, включая оба PatternRegistry, получают temporary paths.
Нет общей mutable ContextMemory, ContextOpsPool, ShortMemory, registry или ExpSM.
Отдельный negative test записывает новое registry имя поочерёдно в каждый root
и доказывает побайтовую неизменность другого root.

`safe_demo` не объявляется read-only: temporary draft writes разрешены policy,
PatternRegistry может писать manifest, legacy Outcome/admin exceptions из RND-110
сохраняются. Ни эти исключения, ни F02–F09 здесь не исправлены. Изоляция достигается
корнями и владением, а не новым универсальным write gate. Native prepared store
дополнительно проверяется побайтово при закрытии каждого adapter.
Автоматического cross-runtime Feedback, native APPLY/CREATE или обучения нет.

Начальный полный inventory: **12 файлов, 15 339 016 байт**. Сравнение всех имён,
размеров и SHA-256 до/после испытаний обязательно; агрегат sorted compact JSON
inventory (path → size/sha256):
`4a31b96a9fdc9d9fb8a8661e8786ee79fdfb6adf2415b052c8645cbfef851971`.

## Positive/negative сценарии и результаты

Помимо 10 differential combinations проверяются **10 отдельных совместных
lifecycle сценариев**: idle isolation; feed между native ticks/no cross delivery;
flood; legacy pause/stop без backlog; native pause/stop с pending; native resume
с отсутствующим T+1; sensor failure; post-world uncertain result; legacy invalid
feed; два feed с одним caller tick. Ещё два tests проверяют независимость roots
и отклонение неверного/слишком большого плана до исполнения.

Итого **83/83 unittest tests PASS** вместе с B1/B2/delivery/Context-ShortMemory;
legacy scenario/check counts учитываются отдельно.

Итого targeted suite содержит **13 unittest methods**: одна matrix method включает
10 subcases, остальные 12 — отдельные проверки. Это 20 joint lifecycle сценариев,
а не 20 unittest methods. При exception driver сохраняет уже полученные результаты,
тип/сообщение ошибки и native stop report, терминально закрывает лишь ошибочный
adapter и продолжает явно запланированные операции другого. Legacy invalid input
проверяется до исполнения; это не доказательство отсутствия effects для произвольной
legacy exception. При world failure после физического эффекта сохраняются unresolved
UUID, synchronization_blocked и `physical_result_may_be_uncertain`; автоматического
retry нет, другой adapter получает свой результат. Durable recovery не обещается.

Все Python-запуски: `PYTHONDONTWRITEBYTECODE=1 python -B`, включая inherited env
для subprocess verifiers. Безопасность entry points проверена до запуска: native
fixtures создают temporary paths; scenario runner копирует Memory до создания
runtime; phase-map checks читают код и запускают те же изолированные scenario paths.
Небезопасный original-root `verify_memory_mutation_policy.py` не запускался.

| Проверка | Новый результат |
| --- | --- |
| Joint targeted verifier | 13/13 PASS; 10 differential combinations, 20 joint lifecycle сценариев |
| Native B1 | 5/5 PASS |
| Native B2 | 23/23 PASS |
| Bounded delivery | 18/18 PASS |
| Context/ShortMemory | 24/24 PASS, whole Memory inventory PASS |
| Legacy phase regression snapshots | 8/8 PASS |
| Runtime tick phase map | PASS, 12 phases; все реальные child entry points PASS |
| Phase-level invariants | 10/10 checks PASS, 62 apply_pending, реальные child entry points PASS |

Runtime phase map дополнительно запускает 77 scenario fixtures, 7 reflection и
7 policy-review scenarios и static influence-boundary check. Это реальные child
entry points; shallow env выставляет сам parent только против рекурсивного запуска,
не против behavioral assertions child scripts. Повторные child executions не
суммируются как новые уникальные test cases. Полная project regression не заявляется.

Ранние прогоны нового verifier выявили ошибки самих новых assertions: FIFO commit
metadata, место materialization mechanism candidates и предположение об обязательном
новом apply после каждого recent. Assertions исправлены по текущему коду и реальным
traces. Production behavior, selector и guard ради прохождения не менялись.

## Граница общей инфраструктуры

| Статус | Что действительно имеется |
| --- | --- |
| Уже общий механизм | Оба контура используют production ContextMemory/ContextMemoryManager/ContextOpsPool, PatternRegistry, IdGenerator, DecisionSelector и ModeActionGuard как классы кода с разными экземплярами и соответствующими legacy/native API. Сам finite test driver переиспользуется для обоих adapters. Это не общий cognitive path. |
| Общий контракт | start/pause/resume/stop в тестовом driver; запрет implicit retry и backlog; изолированное владение roots; раздельные результаты и явный partial failure. Реализация lifecycle разная: legacy admission gate и native Heart. |
| Только кандидат | Clock mapping между caller ticks и Heart, production lifecycle для legacy, общий bounded diagnostics envelope, typed delivery между контурами, resource/admission hooks. Нужны отдельные semantics и review; здесь clock mapping и transport между runtime отсутствуют. |

Native delivery уже bounded; legacy ContextOpsPool этим механизмом не пользуется
и bounded transport не объявляется общим. Диагностические traces ограничены конечным
тестовым планом, но общее production retention API не извлечено. Legacy и natural
NFPFrame остаются разными типами. Нет общего scheduler, memory representation,
общего selector decision или cross-runtime cognitive learning.

Дальнейшие небольшие RND-кандидаты: определить clock-mapping contract без новой tick
authority; спроектировать общий diagnostic envelope без cognitive payload conversion;
описать resource/admission hooks с сохранением protected observation priority.
Ни один кандидат не начат. Memory-authority findings требуют своей отдельной задачи.

## Full-diff design review и закрытие

Первоначальные четыре full-diff entry points вернули FAIL исключительно из-за
трёх новых paths RND-015. Реализация остановилась для согласования. Архитектурный
review принят; пользователь отдельно разрешил ровно 12 exact additions и один
локальный commit семи файлов после успешных проверок.

В каждый из четырёх sets добавлены только три string literals:

```python
"docs/RND-015_legacy_native_joint_checkpoint.md",
"tools/legacy_native_joint_checkpoint.py",
"tools/verify_legacy_native_joint_checkpoint.py",
```

| Verifier | Место additions | Реальный entry point | Negative control |
| --- | --- | --- | --- |
| [retrieval](../tools/verify_nfp_expsm_operational_retrieval_design.py) | локальный `allowed` set в `main()` | PASS, exit 0 | PASS, exit 1, `unexpected design-pass files` |
| [guarded execution](../tools/verify_nfp_action_materialization_guarded_execution_design.py) | `ALLOWED` | PASS, exit 0 | PASS, exit 1, `unexpected changed files` |
| [Feedback](../tools/verify_nfp_native_feedback_design.py) | `ALLOWED` | PASS, exit 0 | PASS, exit 1, `unexpected changed files` |
| [replay/idempotency](../tools/verify_nfp_native_feedback_replay_idempotency_design.py) | `ALLOWED` | PASS, exit 0 | PASS, exit 1, `unexpected changed files` |

Итого **4/4 design gates PASS и 4/4 negative controls PASS**. Проверены реальные
script entry points с фактическим полным diff семи файлов, включая untracked,
затем финальный staged diff. Для negative controls временный untracked файл
`rnd015_unknown_changed_path_probe.txt` безопасно добавлен в корень репозитория;
каждый неизменённый changed-path collector увидел его через реальный Git status.
Каждый entry point вернул ненулевой код и конкретное имя probe в unexpected-path
диагностике. Probe удалён в finally; production files не менялись.

Побайтовая реконструкция каждого verifier удалением ровно трёх новых строк совпала
с его HEAD-версией. Итого diff четырёх verifiers — **12 insertions, 0 deletions**.
Wildcards, assertions, changed-path collectors и другие разрешения не менялись.
Production contracts, schema, writers, guard/execution и ADR не менялись.

Финальный review исходного harness подтвердил: legacy использует только публичные
feeds, wrappers вызывают оригинал один раз и сохраняют return; его lifecycle gate
не является production lifecycle CLCRuntime. Native tick остаётся у Heart;
план driver конечен, не добавляет скрытых ticks, scheduler, retry или cognitive
inputs между runtime. Normalization касается только реально generated UUIDs и
сохраняет их связи; legacy traces сравниваются без normalization. Все potentially
writable dependencies получают собственные temporary roots. Original Memory —
только read/copy source, не аргумент runtime/writers. Partial results, exceptions,
unresolved occurrences и неопределённость физического результата сохраняются.
Новых production-дефектов в этом review не обнаружено.

Implementation и behavioral verifier при закрытии побайтово не изменены, поэтому
сохранены результаты предыдущего принятого прогона: **83/83 unittest tests PASS**,
отдельно **8/8 legacy snapshots PASS**, phase map и phase-level checks PASS.
Это сохранённые результаты, не новый behavioral прогон. **20 совместных lifecycle
сценариев, включая 10 differential combinations**, остаются в прежнем объёме.
Unsafe original-root verifiers не запускались. Все новые Python-запуски выполнены
через `PYTHONDONTWRITEBYTECODE=1 python -B`, включая subprocess entry points.

Финальная safety-сверка: полный inventory всех **12 исходных Memory files**,
размеры (**15 339 016 bytes**) и SHA-256 совпадают и с началом closure, и с исходным
checkpoint implementation. Агрегат inventory сохранён выше. `AGENTS.md` побайтово
неизменён, ignored через `.git/info/exclude`, не отслеживается. Новых production
lock/bytecode files нет. Временные roots, probe и диагностические артефакты удалены.
Markdown links, Python syntax, whitespace всего diff, `git diff --check` и staged
diff проверены. В staging разрешены ровно следующие семь файлов:

```text
tools/legacy_native_joint_checkpoint.py
tools/verify_legacy_native_joint_checkpoint.py
docs/RND-015_legacy_native_joint_checkpoint.md
tools/verify_nfp_expsm_operational_retrieval_design.py
tools/verify_nfp_action_materialization_guarded_execution_design.py
tools/verify_nfp_native_feedback_design.py
tools/verify_nfp_native_feedback_replay_idempotency_design.py
```

Закрытие фиксируется одним локальным commit:
`test(integration): verify legacy and native lifecycle coexistence`.
Сохраняются границы синтетического checkpoint, независимые representations,
отсутствие общего production scheduler/когнитивного объединения/durable recovery
и открытые memory-authority findings F02–F09 RND-110. Общий переиспользуемый код,
общий тестовый lifecycle contract и будущие production-кандидаты разделены выше.
**RND-015 CLOSED. После коммита и финальной сверки — остановка; новая задача не начинается.**
