# RND-013 — Сердце и непрерывный native-контур B2

Дата: 2026-11-06. Статус: **CLOSED — архитектурный review принят, финальные проверки пройдены**.

B2 — ограниченный синтетический непрерывный контур с самостоятельным Heart.
Это не готовый полный ПЖК и не готовый Квадрат/ДАР.

Контрольная точка: `main`, HEAD `3f896da96a8349554582b74a3f0a701ab23a7b53`,
исходное дерево чистое. Локальный AGENTS.md прочитан, ignored и неизменён.
[RND-010](RND-010_clc_native_integration_architecture.md),
[RND-011](RND-011_short_memory_contract_reconciliation.md) и
[RND-012](RND-012_native_session_b1.md) CLOSED. Работа только локальная:
без remote contact, fetch/pull/push, merge и tags. После успешной финальной
сверки разрешён один локальный commit десяти согласованных файлов:
`feat(native): add independent Heart and B2 lifecycle`.

## Фактические API до реализации

- [NativeSession B1](../clc/runtime/native_session.py) использует world tick для
  freshness selection и немедленно наблюдает последствие через coordinator.
  World apply сам меняет `current_tick` с T на T+1. No-match останавливает B1.
- [Coordinator](../clc/actuation/remembered_action_execution.py) с
  `observe_consequence=False` проходит штатные freshness/pending checks,
  materializer, guard и transducer, затем world apply и `observe_action_frame()`.
  Он возвращает `ACTION_EXECUTED_OBSERVATION_PENDING` с реальным pending и UUIDv4
  occurrence. Snapshot, recent и ShortMemory retention в этой ветке отсутствуют.
- [ContextMemoryManager](../clc/context/context_memory_manager.py) отдельно
  принимает `observe_external_sensory_window(window)`. При window.end_tick =
  expected_observation_tick он возвращает recent и освобождает pending; observation
  позднее T+1 освобождает pending без recent. Старое evidence не переписывается.
- `expire_pending_if_overdue(T+1)` оставляет pending; только tick > T+1 его
  удаляет. Метод продвигает внутреннее время manager даже без observation.
- [ShortMemory](../clc/context/short_memory.py) поддерживает независимый
  `prune(current_tick)`; `remember(recent, current_tick=...)` вызывается отдельно.
- Synthetic world до B2 не имел idle API. Добавлен только `advance_idle`;
  существующие snapshot/apply, coordinator, ContextMemoryManager, ShortMemory,
  NFP schema и guard semantics не изменены. Значимых изменений утверждённых
  production contracts не потребовалось.

## Компоненты и интерфейсы

[Heart](../clc/runtime/heart.py) — самостоятельный источник целочисленных ticks:

- `Heart(max_ticks=..., initial_tick=0)`; положительный целочисленный бюджет;
- `start()`, `pause()`, `resume()`, `stop(reason=...)`;
- `step(pulse)` выдаёт один tick callback и возвращает bool;
- `run(pulse, paced=False, interval=0.01, clock=time.monotonic, sleep=time.sleep)`;
- `tick` — следующий собственный tick, `state` — READY/RUNNING/PAUSED/STOPPED;
- `admission_open` — только lifecycle gate. Это не разрешение физического
  действия или записи памяти; действие по-прежнему разрешает production guard.

Heart не знает sensor, selection, occurrence или Memory. Внутри tick callback
обрабатывается синхронно. После нормального возврата callback Heart увеличивает
собственный tick на один; не присваивает ему значение world.current_tick.
При исключении tick не увеличивается, Heart терминально останавливается.
При известном возвращённом неопределённом execution result pulse завершается
с диагностикой и stop; это потребляет выданный tick, но не утверждает world advance.
После такого stop выравнивание Heart/world не обещается и продолжение запрещено.

Paced run использует monotonic clock только для ожидания следующего pulse.
Первый tick немедленный, последующие — не ранее interval после окончания
предыдущего callback. Нет catch-up, worker thread или фонового scheduler.
Ожидания разбиты на части не более 0.05 s; lifecycle проверяется между ними.
После resume run получает новый pacing origin; время pause не порождает ticks.
Manual и paced режимы имеют одинаковый модельный trace независимо от скорости
clock. Timestamp clock не участвует в identity NFP или occurrence.

[NativeHeartSession](../clc/runtime/native_heart_session.py) — отдельный B2 owner:

- `NativeHeartComponents` явно передаёт world, context_manager, retriever,
  retrieval_config, activation, selector, coordinator, short_memory, system_state.
  Компоненты должны находиться в исключительном владении session; совместный
  запуск другой session с теми же mutable components не поддерживается.
- `NativeHeartSession(components, max_ticks=..., sensor=None, initial_tick=0)`;
  начальные Heart/world ticks должны совпадать.
- `start(); step()` — manual; `run(paced=True, ...)` — bounded paced;
  `run()` автоматически начинает только READY, но не возобновляет PAUSED/STOPPED.
- `sensor(tick)` возвращает реальный `VisualFieldSnapshot` или None. По умолчанию
  sensor отсутствует. Для regular synthetic sampling owner может передать
  `lambda tick: world.snapshot()`. Это реальная выборка, включая неизменные values.
- `NativeHeartTick` сохраняет tick, observation, recent, expired, execution,
  advancement (`idle` / `actuator` / `none`) и diagnostic.
- `stop()` возвращает `NativeHeartStop`; `stop_report()` доступен независимо от
  остановки: Heart/world ticks, Heart state/diagnostic, pending,
  unresolved_occurrences, in_flight, synchronization_blocked и phase diagnostic.

Никаких default writable roots, ExpSM writers, обучения или Feedback здесь нет.
Retrieval/activation/selection/guard/materialization/execution не дублируются.
B1 остаётся самостоятельным неизменённым bounded synchronous path.

## Контракт Heart/world и границы T / T+1

[SyntheticTimeAdapter](../clc/runtime/synthetic_time_adapter.py) предоставляет
`open(tick)`, `finish(actuator_advanced=...)`, `block()`.

1. Heart открывает T. `open(T)` требует world.current_tick == T и отсутствия
   незакрытого перехода. Несогласованность блокирует adapter, без ремонта evidence.
2. При наличии новой выборки session проверяет snapshot.active_tick == T и ранее
   не использованный snapshot_id. Transducer создаёт внешний sensory NFP;
   frame/window IDs scoped session UUID + tick, provenance берётся из snapshot.
3. Manager принимает observation. Если это ожидаемое T+1, pending завершается
   и recent сохраняется в ShortMemory **до retrieval и следующего action admission**.
4. Выполняются `expire_pending_if_overdue(T)` и `ShortMemory.prune(T)`.
5. Только новая observation текущего T допускается в production retrieval,
   activation и selection. При lifecycle pause/stop request admission закрыта.
6. Выбранный ACTION проходит существующий guarded coordinator с
   `observe_consequence=False`. ACTION имеет tick T, occurrence — отдельный UUIDv4;
   world apply продвигает мир до T+1, manager создаёт pending с ожидаемым T+1.
   Observation последствия в T не создаётся.
7. `finish(actuator_advanced=True)` требует world == T+1 и не вызывает idle.
   Без actuator `finish(False)` требует world == T, вызывает один
   [advance_idle(expected_tick=T)](../scenarios/support/synthetic_closed_loop_visual_world.py)
   и проверяет world == T+1. Этот метод меняет только модельное время, не позицию;
   ACTION, motor signal и occurrence не создаются.
8. После callback Heart сам увеличивает tick до T+1. Следующий pulse сначала
   принимает реальное observation T+1; только затем допускается новое исполнение.

Таким образом, нормальный модельный переход содержит ровно один world advance:
либо actuator, либо idle. Внутри ACTION tick мир уже T+1, а Heart ещё обрабатывает T;
это явная промежуточная граница, а не расхождение для исправления.
Двойной `finish`, неожиданный advance, неверный результат world apply или idle
не разрешают второй advance. Session останавливается без повторного действия.
После WORLD_EXECUTION_FAILED нельзя делать вывод о физике по `.executed=False`:
наличие actuator signal означает возможный world effect, поэтому idle запрещён.
Tracking failure после apply также блокирует дальнейшее исполнение.

## Пустые ticks и причинность

При **новой sensory выборке без действия** values могут оставаться теми же.
Snapshot ID, provenance и NFP identity новые; retrieval выполняется снова.
No-match, selection=None и guard denial не останавливают Heart; переход завершается
через idle. Guard denial сохраняет существующую семантику materialization:
occurrence ID может уже существовать в result, хотя физического исполнения нет.
Он не учитывается как unresolved physical execution.

При **отсутствии нового sensory входа** sensor возвращает None или отсутствует:
нет snapshot/transduction, retrieval, selection или action. Старый present остаётся
тем же объектом с исходным tick. Heart и world продолжаются через idle, manager
обслуживает pending expiration, ShortMemory — pruning. Фиктивных observations нет.

Если observation отсутствует в T+1, pending сохраняется. При T+2 без observation
он возвращается в `NativeHeartTick.expired`; при реальной поздней observation
manager сам освобождает старую связь без recent. Такое позднее observation может
стать новым present и участвовать в новом retrieval. Оно не достраивает старый
transition. Это новый выбор, а не retry старого occurrence.
Expired, но не подтверждённые occurrences остаются в bounded stop diagnostics;
expiration не доказывает отсутствие физического эффекта. Лимиты одного pending
и ровно T+1 сохранены как ограничения текущего прототипа, не окончательная RNDeM.

## Pause, resume, stop и ошибки

Внешние вызовы сериализованы. Pause вне pulse немедленно запрещает новый tick;
Heart и synthetic world стоят на одной границе. Pending не истекает по wall time.
Resume продолжает следующий tick и принимает ожидаемое observation.
Pause/stop, запрошенные внутри callback, немедленно закрывают admission и вступают
в state на безопасной границе окончания callback. Уже начатое физическое действие
не отменяется; штатный текущий переход завершается. Бюджет имеет приоритет над
pause на последнем pulse, поэтому resume не превышает max_ticks.

Stop терминален. Повторные start/resume/run/step не исполняют уже совершённые
действия. Stop report показывает pending и известные unresolved occurrences;
при исключении внутри coordinator `in_flight=True` консервативно означает неизвестный
результат, а не работающий background worker. Неизвестный occurrence UUID не
выдумывается. Stop report внутри callback отражает ещё текущую границу и diagnostic;
после callback нужно получить окончательный `stop_report()`.

Exceptions sensor, retention, coordinator или adapter распространяются вызывающему
коду при уже установленном terminal latch и blocked adapter. Нет automatic retry,
blind idle advance, изменения старых NFP, durable state или restart recovery.
Typed execution result сохраняется в tick record при возвращённой post-world
ошибке; при исключении доступны stop report и последняя phase diagnostic.

## Проверки

Все Python entry points запускались с `PYTHONDONTWRITEBYTECODE=1 python -B`;
subprocesses наследуют запрет bytecode, explicit subprocess commands используют
`-B`, multiprocessing spawn наследует interpreter flags. Writable constructors
используют только TemporaryDirectory roots; fixtures удаляются cleanup.

| Entry point в tools/ | Результат |
| --- | --- |
| [verify_native_heart_b2.py](../tools/verify_native_heart_b2.py) | **23/23 PASS** |
| [verify_native_session_b1.py](../tools/verify_native_session_b1.py) | **5/5 PASS** |
| [verify_nfp_context_short_memory.py](../tools/verify_nfp_context_short_memory.py) | **24/24 PASS** |
| [verify_nfp_remembered_action_guarded_execution.py](../tools/verify_nfp_remembered_action_guarded_execution.py) | **8/8 PASS** |
| [verify_nfp_expsm_operational_retrieval.py](../tools/verify_nfp_expsm_operational_retrieval.py) | **5/5 PASS** |
| [verify_nfp_native_feedback_replay_idempotency.py](../tools/verify_nfp_native_feedback_replay_idempotency.py) | **15/15 PASS** |

Итого **80/80 tests PASS**. В первом B2 прогоне обнаружено неверное имя поля query
в verifier (`context` вместо `current_context`), исправлено; failed run не засчитан
как PASS. После дополнения cases финальный B2 прогон — 23 успешных tests.

B2 проверяет actual position/ticks, snapshot IDs/provenance, signal identity,
occurrence continuity pending→recent, exact retained recent и порядок
observe→remember→apply. World apply и idle учитываются раздельно. Покрыты:

- no-match и selection=None по несколько ticks, совсем отсутствующий sensor;
- одинаковые values при разных identities; старый present без relabel/retrieval;
- настоящий ACTION T и отдельное observation T+1 до следующего admission;
- отсутствие второго advance после actuator; повтор finish и time divergence;
- pending в T+1 без observation, overdue и настоящее позднее observation;
- ShortMemory retention и возрастное pruning на ticks без sensory события;
- guard denial, stale request без нового occurrence или автоматического retry;
- pause/resume, pause внутри sampling, bounded manual/monotonic pacing;
- stop с pending, stop/in-flight diagnostic, повтор terminal run;
- world failure до/после apply, tracking/sensor/retention failure;
- неправильный двойной world advance, exception после реального idle advance;
- совпадение model traces manual и paced, завершение с тремя retained transitions.

Temporal contracts отдельно подтверждаются existing Context/ShortMemory tests:
current sensory tick, early/late observation, expiration boundary, explicit prune.
Полная project regression не запускалась. После 80/80 PASS implementation B2 и
behavioral tests не менялись, поэтому повторные behavioral прогоны не требовались.
Изменение synthetic world аддитивное; B1 5/5 подтверждает сохранение поведения,
а исходный `native_session.py` побайтово совпадает с HEAD контрольной точки.

## Финальный review design contracts и meta-audit

Первый финальный прогон четырёх full-diff design verifiers отверг только шесть
новых/изменённых путей B2; других failures не было. Выполнен STOP, без изменения
verifiers, закрытия статуса или commit. Пользователь отдельно разрешил добавить
ровно эти шесть exact paths в каждый allowlist и расширить commit до десяти файлов.

После согласованных additions реальные script entry points дали **4/4 PASS**:

| Full-diff design verifier | Результат |
| --- | --- |
| [retrieval design](../tools/verify_nfp_expsm_operational_retrieval_design.py) | PASS: 17 sections, 62 grouped contracts, 9 source references |
| [guarded execution design](../tools/verify_nfp_action_materialization_guarded_execution_design.py) | PASS: 73 contracts, 10 changed files |
| [Feedback design](../tools/verify_nfp_native_feedback_design.py) | PASS: 66 contracts, 26 source facts, 17 V1 fields, 10 TargetCore fields |
| [replay/idempotency design](../tools/verify_nfp_native_feedback_replay_idempotency_design.py) | PASS: 21 sections, 53 contracts, 24 source facts, 10 evidence fields, 17 V1 fields |

До запуска проверены entry points: только stdlib, чтение файлов/AST/JSON и
read-only Git subprocesses; production constructors, Memory writers и locks
не вызываются. Все Python-запуски использовали `PYTHONDONTWRITEBYTECODE=1 python -B`.

Meta-audit — **PASS**:

1. Все четыре verifier приняли фактический diff из десяти согласованных файлов.
2. Временный untracked `rnd013_unknown_path_negative_control.txt` добавлен как
   неизвестный путь. Каждый из четырёх реальных entry points вернул exit 1,
   указав именно этот путь как единственный unexpected changed file: **4/4 PASS**
   negative controls. Временный файл удалён в finally.
3. AST каждого verifier после удаления шести согласованных set entries полностью
   совпадает с исходным AST из HEAD. Assertions, исходные entries, source facts
   и changed-path detection не изменены. Добавлены только шесть точных строк
   и поясняющий комментарий в каждом allowlist, без wildcard или подавления errors.
4. Фактический список изменений сверяется независимо с точным списком десяти
   разрешённых файлов; implementation/test hashes неизменны после 80/80 PASS.
   B1, schema, coordinator, guard, writers, receipt ledger и ADR не изменены.
5. Исторические широкие разрешения allowlists не служат доказательством безопасности
   произвольного production diff. Проверены именно согласованные paths и их
   содержимое; production Memory дополнительно сверена по inventory и SHA-256.

## Финальная сверка и границы RND-014

Изменения: три новых runtime modules, новый behavioral verifier, этот документ,
один аддитивный idle method synthetic world и четыре согласованных allowlists.
Итого ровно десять файлов. Полный diff включая новые файлы,
Markdown links и `git diff --check` проверены. Исходные 12 файлов production Memory
сверены по полному file inventory и SHA-256: неизменны. Новых production lock или
bytecode файлов нет; существующий inventory таких артефактов сохранён.
AGENTS.md unchanged/ignored; временные fixtures и audit artifact очищены.

Ограничения: один сериализованный owner, один visual sensor, одна выборка на tick,
one-frame query, один pending/T+1, ACTION topology `(2,)`, finite tick budget,
синхронные callbacks без deadlines и thread-safety. Manual stepping допускает
любой темп; paced режим не обещает hard real-time. Размер records/seen identities/
unresolved diagnostics ограничен бюджетом session, durable retention отсутствует.
Нет legacy `_run_tick`, переноса 12 фаз, ПЖК, Квадрата/ДАР, real actuators,
automatic learning/Feedback APPLY/CREATE или записи в production Memory.

Будущий RND-014 потребует отдельного контракта bounded delivery/queues,
source-scoped provenance, overload и нескольких событий на tick. Эти функции,
как и recovery/multi-pending, здесь не реализованы и автоматически не начинаются.
**RND-013 CLOSED.** Review принят, 80/80 behavioral tests сохранены, 4/4 full-diff
design verifiers и 4/4 negative changed-path controls пройдены. Разрешён один
локальный commit только десяти согласованных файлов. После закрытия работа
останавливается; RND-014 автоматически не начинается.
