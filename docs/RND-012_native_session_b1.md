# RND-012 — Native Session B1

Дата: 2026-11-06. Статус: **CLOSED — review принят, B1 завершён**.
Контрольная точка: `main`, HEAD `2fe0f1b1881dcea28c869f17e6d2d0b2037414d2`.
Работа локальная; разрешён один коммит `feat(native): integrate bounded NFP session B1`.
Remote contact: none; fetch/pull/push, обращения к origin, merge и tags не выполняются.

## Реализованный контур

[NativeSession](../clc/runtime/native_session.py) — самостоятельный ограниченный
владелец серии синхронных эпизодов по принятой
[архитектуре B1](RND-010_clc_native_integration_architecture.md).
Он получает явно созданные компоненты и synthetic world. Writable constructors,
пути и подготовка опыта остаются у вызывающего кода. Session не создаёт registry
с default path, не вызывает CLCRuntime, writers, Feedback APPLY/CREATE или ExpSM CRUD.

[Behavioral verifier](../tools/verify_native_session_b1.py) создаёт изолированные
instances в `TemporaryDirectory`: ExpSM fixture и manifest. `PatternRegistry`
получает только этот временный manifest; его constructor и `id()` могут писать
служебные записи. Registry нужен legacy constructors activation/guard и пустому
`ContextMemory`, но native frames не преобразуются в `pat_*` representation.
`ContextMemoryManager` получает обязательные пустые `ContextMemory` и `ContextOpsPool`;
legacy queue/apply_pending в session не используется.

Фактическая последовательность вызовов:

1. При отсутствии external present: `world.snapshot()` →
   `VisualFieldTransducer.transduce()` → one-frame `NFPWindow` →
   `ContextMemoryManager.observe_external_sensory_window()`.
   Уже зарегистрированный present может быть передан владельцем компонентов;
   session не перемаркирует его и не обновляет его tick.
2. `NFPExpSMRetriever.retrieve(NFPExpSMRetrievalQuery(before), config)` читает
   prepared store по текущему present. Именно `retrieval.candidates` передаются
   в `ExpSMActivationModule.activate_native()`, затем в `DecisionSelector.select_native()`.
3. Для реального selected создаётся `SelectedNFPExecutionRequest(selected, before.end_tick)`.
   `NFPRememberedActionExecutionCoordinator.execute()` вызывается с
   `observe_consequence=True` и явной ShortMemory.
4. Coordinator проверяет freshness и pending, вызывает materializer, затем
   `ModeActionGuard.is_native_action_allowed()`, `ActionTransducer.transduce()`
   и единственный `world.apply_actuator_signal()`.
5. После world apply coordinator вызывает `observe_action_frame()` для pending,
   получает настоящий snapshot, transduce/window, вызывает
   `observe_external_sensory_window()` и `ShortMemory.remember(recent, current_tick=...)`.
6. Session подтверждает retention наличием **того же объекта recent** в
   `ShortMemory.snapshot()`. Только `EXECUTED_AND_OBSERVED`, подтверждённый retention
   и отсутствие detail дают `completed`. Следующая query использует новый present
   manager, полученный на шаге 5.

Session не содержит политики выбора опыта, формулы activation, guard semantics,
материализации или повторного actuator path. Универсальный `_run_tick()` не добавлен.

## Время, identity и authority

Единственный источник progression B1 — synthetic `apply_actuator_signal`:
сигнал проверяется относительно T и переводит мир в T+1. Начальный before,
selection request и ACTION относятся к T. Snapshot после исполнения относится к
T+1; pending ожидает ровно action_tick+1. Дополнительного advance и повторного
apply ради observation нет. Snapshot считывает мир, увеличивая только snapshot ID.

Срез использует visual topology `(1, 4)` в fixture, one-frame окна и ACTION topology
`(2,)`. VisualFieldTransducer сохраняет двумерную topology snapshot; `(2,)` в
архитектуре B1 относится к ACTION. Это параметры первого среза, не ограничения
целевой архитектуры. Один pending обеспечивает существующий manager.
Visual-only, один pending и ACTION topology `(2,)` — ограничения прототипа B1,
а не всей архитектуры RNDeM.

NFP сохраняет modality, topology, origin, active_tick, frame_id и provenance_ref.
External provenance имеет вид `sensor_snapshot:...`; ACTION создаётся production
materializer с `ACTION_GENERATED` и `provenance_ref=None` по существующему контракту.
Source experience, activation, selection и target core доступны в typed результатах.
Session добавляет UUID session_id и source_id в envelope каждого эпизода; они
задают scope локальных counters, не меняя исходные NFP refs.

Materializer создаёт один UUIDv4 `execution_occurrence_id` на materialization.
Coordinator переносит его без замены в result/pending/recent. Observation не создаёт
новый occurrence. Guard denial тоже может иметь materialized occurrence без
физического исполнения; наличие UUID не означает world apply. Retrieval candidate
IDs могут повторяться между эпизодами, поэтому сами по себе не являются event ID.
Совпадение values не означает identity; отношение T→T+1 не доказывает единственную
причину изменения мира.

У session нет memory-write authority. ExpSM fixture записывается владельцем **до**
запуска и побайтово проверяется после happy path. В session опыт не обучается и
не обновляется. ShortMemory — только bounded in-process retention, не durable store.
Переданные компоненты и их roots являются доверенной конфигурацией владельца;
NativeSession не является универсальным контролем filesystem authority.

## Lifecycle и ошибки

`max_episodes` задаёт положительный конечный бюджет, journal ограничен им.
`run()` ставит stop latch до первого внешнего вызова. Повторный `run()` возвращает
сохранённые эпизоды, не получает observation и не исполняет действие снова.
После budget exhaustion серия также завершена. Автоматического resume/recovery нет.
Новая session после process restart не обещает восстановления старого occurrence;
обёртывать неизвестный исход в новую session для слепого retry нельзя.

| Сценарий | World apply | Recent / ShortMemory | Результат session |
| --- | --- | --- | --- |
| Empty native store / below retrieval threshold | 0 | Нет / нет | `no_native_match`, остановка; retrieval status/reason сохранены |
| Selector threshold отвергает candidates | 0 | Нет / нет | `selection_none`, остановка |
| Guard denial | 0 | Нет / нет | Сохранён `guard_denied`, без fallback |
| Stale present относительно world tick | 0 | Нет / нет | `stale_selection`, без перемаркировки snapshot |
| Pending занят | 0 новых | Нет нового / нет нового | `causal_slot_occupied`, существующий pending не заменяется |
| Успех | 1 | Есть / есть | `completed`, можно перейти к следующему эпизоду |
| Sensor exception после apply | 1 | Нет / нет | Observation pending, остановка без retry |
| Late sensor tick | 1 | Нет / нет | Старый pending истекает, late present не достраивает transition; остановка |
| Tracking failure после apply | 1 | Нет / нет | Tracking failed, остановка; отсутствие pending не доказывает отсутствие эффекта |
| Retention failure | 1 | Есть / нет | Сохраняется `executed_and_observed` с retention detail; episode не `completed` |
| World exception после возможного apply | 1 вызов | Нет / нет | `world_execution_failed`, физический результат не выводится из `.executed=False`; остановка |

При незавершённом post-world результате диагностируется
`physical_result_may_be_uncertain; session_stopped`. Для retention failure это
консервативный stop marker: typed result отдельно подтверждает успешное observation,
но retention отсутствует. Успех исполнения, успех observation и успех retention
не объявляются взаимозаменяемыми. Session не повторяет действие ни по одному статусу.
Непредвиденные exceptions распространяются вызывающему коду с уже установленным
stop latch и phase diagnostic; durable сохранение результата не обещается.

## Проверки и review

Все повторные Python-запуски выполнялись с `PYTHONDONTWRITEBYTECODE=1 python -B`;
переменная окружения наследуется subprocesses. Реальные script entry points:

| Entry point в `tools/` | Результат |
| --- | --- |
| `verify_native_session_b1.py` | 5 tests PASS |
| `verify_nfp_context_short_memory.py` | 24 tests PASS; whole Memory inventory PASS |
| `verify_nfp_expsm_operational_retrieval.py` | 5 tests PASS; production activation/selection, top-N и boundaries |
| `verify_nfp_remembered_action_guarded_execution.py` | 8 tests PASS |
| `verify_nfp_native_feedback_replay_idempotency.py` | 15 tests PASS |

**Итого: 57/57 tests PASS** по последнему успешному прогону. При закрытии изменён
только статусный документ; implementation/verifier совпадают с проверенными версиями,
поэтому повторный прогон тестов не выполнялся.

Happy path содержит три prepared native records с различными visual contexts и
одним правым motor action. При threshold 0.99 каждый current context даёт ровно
одного matching candidate с similarity 1.0. Опыт не выбирается по ID: assertions
проверяют получившийся выбор. Мир проходит `(0,0) → (0,1) → (0,2) → (0,3)`, ticks
`0 → 1 → 2 → 3`; ровно три apply и три записи ShortMemory.

Verifier проверяет связи retrieval candidate → activation → selection, materialized
ACTION identity/origin/topology/tick, неизменный UUIDv4 через execution/pending/recent,
identity retained recent, distinct observation IDs/provenance и передачу after-window
следующей query. Audit каждого настоящего world apply проверяет before/after position
и tick; выбранный signal совпадает с переданным миру. Повторный run не меняет count.

Пять test methods включают subcases для empty store, below-threshold query,
selector refusal, guard, stale, pending, sensor/tracking/retention failures и
исключения **после реального изменения synthetic world**. Happy path использует
production implementations; RecordingManager только записывает returned pending
после `super()`. Ошибки вводятся subclasses в verifier, production hooks не добавлены.
Late sensor case намеренно возвращает неконсистентный поздний tick как fault injection;
это не time adapter и не утверждение о нормальной работе synthetic snapshot.

Early/late observation и expiration manager дополнительно проверяются существующим
Context/ShortMemory verifier; B1 не имеет публичного API отложенной доставки sensory
input. Отдельный асинхронный delivery/recovery path ради тестов не добавлен.

Code review двух новых Python-файлов проверил все ветви run/coordinator integration:
единственный путь применения мира остаётся у coordinator, guard и materializer не
обходятся; `.executed` не используется как доказательство отсутствия физического
эффекта; retention проверяется отдельно от status. Значимых изменений существующих
production API и нового дефекта существующих компонентов не выявлено.

Полный regression suite и historical full-diff design verifiers не запускались:
изменяются только новые session/verifier/document, существующие contracts не меняются.
Allowlist и assertions существующих verifiers не редактировались.

## Memory, cleanup и состояние изменения

Первый регрессионный прогон создал служебный
`Memory/ExpSM/__pycache__/Exp_CRUD.cpython-314.pyc`, из-за чего whole-inventory check
завершился FAIL при 24 успешных behavioral tests. Это не было объявлено PASS:
работа была остановлена. После отдельного разрешения пользователя подтверждены
отсутствие файла в pre-run inventory и Git tracking, обычный тип файла, CPython magic,
timestamp/size matching source и code filename. Удалён только этот bytecode.
Пустой каталог оставлен: его creation provenance до прогона не была зафиксирована.

Повторная проверка подтвердила исходный inventory из **12 файлов Memory** и совпадение
всех SHA-256, без новых файлов. Temporary fixture roots удаляются TemporaryDirectory
cleanup. AGENTS.md неизменён и ignored. Новые paths ограничены session, verifier и
этим документом; Stage-1/2, legacy CLC, NFP schema, guard semantics, ADR и утверждённые
contracts не изменялись. Заключительно проверены полный diff включая untracked files,
относительные Markdown links, whitespace, branch/HEAD/status и исходный Memory inventory.

## Границы до отдельного RND-013

Это исполняемая bounded B1 session, а не continuous RNDeM. Время зависит от действий;
no-match завершает серию. Нет Heart, idle ticks/idle advance, continuous delivery, pause/resume, multi-pending,
bounded transport queues, полноценного Квадрата/ДАР, real actuators, обучения,
auto Feedback APPLY/CREATE или durable outbox/recovery.

RND-013 потребует отдельного Heart и synthetic time adapter, раздельного T+1 admission
при `observe_consequence=False`, idle progression без фиктивных действий, pending
expiration/ShortMemory pruning на пустых ticks и lifecycle pause/stop. Здесь эти
функции не реализованы и задача автоматически не начинается.

**RND-012 CLOSED.** Review принят пользователем. Проверены три согласованных файла,
отсутствие fallback selection, второго world apply и автоматического retry,
изоляция всех writable constructors проверочного запуска, Markdown links и полный
file/byte inventory original Memory. Разрешён один локальный коммит только с
`clc/runtime/native_session.py`, `tools/verify_native_session_b1.py` и этим документом.
RND-013 не начинается автоматически; после фиксации — остановка.
