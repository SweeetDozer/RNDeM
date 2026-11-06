# RND-014 — Первые bounded native delivery ports

Дата: 2026-11-06. Статус: **CLOSED — review принят, финальные проверки пройдены**.

Контрольная точка: `main`, `2a2fb0fc8cc60e0ae12fda933060a38dab02f84c`,
чистое дерево; RND-010–013 CLOSED. Работа локальная, без remote contact,
fetch/pull/push, merge и tags. После принятого review разрешён один локальный
commit семи согласованных файлов: `feat(native): add bounded delivery ports and provenance`.

Основание: [архитектура RND-010](RND-010_clc_native_integration_architecture.md),
[B1](RND-012_native_session_b1.md), [B2](RND-013_native_heart_b2.md).

## Изученные границы

[NativeHeartSession](../clc/runtime/native_heart_session.py) напрямую вызывает
sensor, transducer, ContextMemoryManager, ShortMemory, retrieval, activation,
selector, coordinator и SyntheticTimeAdapter. Sensor вызывается внутри уже
открытого Heart/world tick. Coordinator исполняет ACTION с
`observe_consequence=False`: world apply происходит в T, создаётся один pending
с ожиданием T+1. На следующем pulse observe → remember precede retrieval/execute.

[ContextMemoryManager](../clc/context/context_memory_manager.py) одновременно
принимает present и обслуживает pending. Совпадение end_tick с ожидаемым tick
завершает pending; проверки источника в нём нет. Повторный observe в том же tick
может перезаписать present. Вызов expire продвигает его внутреннее время; позднее
старый tick уже нельзя принять. Поэтому дополнительный observer никогда не
вызывает manager, а старый payload никогда не переименовывается новым tick.
Coordinator повторно не вызывается ради доставки; finish и world apply не
повторяются. Несколько кадров одного tick не собираются в temporal window.

[ContextOpsPool](../clc/context/context_ops_pool.py) — unbounded queue операций
контекста, drain которых выполняет manager. Это не native delivery port: перенос
туда событий смешал бы доставку с записью контекста. Pool изучен, не изменён.

Существующие identity: snapshot_id, NFP frame/window IDs, provenance_ref,
active_tick, transition_id и UUIDv4 execution_occurrence_id. Source/stream binding
в PendingCausalTransition отсутствует. Схемы NFP, manager, coordinator и B2
не менялись.

## Реализованные interfaces и доверенная граница

[Модуль](../clc/runtime/native_bounded_delivery.py):

- `NativeDeliverySession(components, max_ticks, limits=DeliveryLimits(),
  ingress=None, sample_enabled=None, initial_tick=0)` наследует B2 и делегирует
  его `_pulse`, scheduling, execution и time adapter без копирования цикла.
  Сохраняются start/step/run/pause/resume/stop/stop_report.
- `ingress(tick, delivery)` вызывается внутри B2 sensor после open(T).
  Только здесь открыта optional admission через
  `accept(payload, source_id=..., stream_id=..., source_sequence=None,
  source_timestamp=None) → DeliveryResult(event, status)`.
- Payload: неизменяемый VisualFieldSnapshot, NFPFrame или typed Control.
  ACTION command как доставляемого типа нет. ACTION NFPFrame может только
  наблюдаться в journal; к execution он не маршрутизируется.
- Control: TICK, PAUSE, STOP, OVERLOAD, DELIVERY_FAILURE. PAUSE/STOP вызывают
  штатный Heart lifecycle. Остальные — диагностические маркеры. Ни один не
  разрешает ExpSM write, retrieval или ACTION.
- `delivery.depths` возвращает sensory/control/protected queue depths;
  `journal` — bounded deque DeliveryTrace; `counts` — агрегаты стадий с конечным
  набором ключей. Accepted/rejected результаты возвращаются producer сразу.

Авторитетный producer фиксирован: **прямой вызов `components.world.snapshot()`
этим owner после открытия tick**. Это тот же exclusively owned world, который
coordinator использует для исполнения. `sample_enabled(tick)` разрешает пропустить
реальную выборку, но не подставить произвольный payload. Полученный sample
доставляется единственному native visual consumer через обычный sensor B2.

Это реальная локальная source binding через владение producer, а не доверие
строке source_id. Reserved source `owned-synthetic-world` нельзя использовать
через accept. Session с уже существующим pending отклоняется в constructor:
происхождение исполнения из другой session не присваивается новому producer.
Компоненты и callbacks — доверенная конфигурация, операции сериализованы;
враждебный callback, напрямую меняющий world/manager или private fields,
не является поддерживаемым producer API. Произвольный внешний authoritative
sensor и перенос pending между sessions не реализованы.

## Ports, порядок и admission

| Port | Структура | Consumer |
| --- | --- | --- |
| Sensory input | bounded FIFO optional snapshots/frames | bounded observer journal |
| Execution consequence | один защищённый visual slot; также принимает fresh visual без pending | единственный B2 sensor/native consumer |
| Diagnostics/control | отдельная bounded FIFO | lifecycle/diagnostic consumer |

Каждый dispatch обслуживает до одного control, затем защищённый sample, затем
optional sensory до исчерпания budget. Физически visual slot один; без pending
его envelope имеет категорию SENSORY, с pending — CONSEQUENCE. Защита действует
и для начального present. Нет недоверенного `critical` marker.

FIFO внутри sensory и control сохраняется, включая переходы между ticks.
Использование одного source/stream в другом port при наличии недоставленного
события отклоняется `stream_port_conflict`, чтобы сменой категории нельзя было
обогнать собственную очередь. Source и stream независимы: одинаковые snapshot
IDs/values у разных producers не объединяют их события. Межпоточного общего FIFO
нет: protected/control имеют явно описанный приоритет.

Различаются стадии journal:

1. `accepted`: событие помещено в port;
2. `delivered`: payload передан конкретному consumer (observer или native visual);
3. `native_admitted`: B2 принял sample в context, есть window_id;
4. `retrieval_used` и/или `causal_observed`: B2 использовал новое present в query
   и/или завершил ожидаемый transition.

Стадии native usage фиксируются после успешного B2 pulse по его реальному
NativeHeartTick; при исключении сохраняется `delivery_failure`, успешное
завершение pulse не объявляется. Нет transaction rollback manager при ошибке
последующего retention. Observer delivery не означает native admission.
При pause/stop в pulse native observation может обслужить pending, но admission
нового действия уже закрыта штатным Heart gate.

## Identity и provenance

DeliveryEvent frozen и содержит session_id, source_id, stream_id, отдельный UUID
`delivery_event_id`, optional source sequence/timestamp, admission_tick и
монотонный admission_order, native_refs, optional execution_occurrence_id и payload.
UUID delivery создаётся при каждом предложении события независимо от values и
Heart tick. При отказе до создания envelope result.event = None; при overflow
producer получает конкретный rejected envelope.

Для snapshot native_refs содержит исходный sensor_snapshot ID; для NFPFrame —
исходные frame_id/provenance_ref. Исходные объекты не изменяются, включая origin,
active_tick, values и topology. INTERNAL_REACTIVATION остаётся внутренним и
доставляется только observer. Snapshot преобразуется штатным transducer B2;
новый frame/window получает штатные session-scoped IDs и исходную provenance.

Occurrence не создаётся доставкой. Только protected consequence ссылается на
реальный pending.execution_occurrence_id; при dispatch проверяются текущие
pending occurrence и expected_observation_tick. Остальные события occurrence
не заявляют. Само это поле не доказывает исключительную причинность.

## Ограничения и overload

| DeliveryLimits | Default |
| --- | ---: |
| sensory_capacity | 8 |
| control_capacity | 4 |
| dispatch_budget | 8 |
| journal_capacity | 32 |
| max_values в одном sensory payload | 4096 |

Все параметры — положительные int, dispatch_budget не меньше 2: резерв для
control и protected visual. Protected capacity фиксирована равной 1, поскольку
B2 допускает только один native present за tick. Source/stream ограничены 128
символами, native frame refs — 256. Неподдерживаемые типы/невалидные metadata
отклоняются исключением, внутри pulse это штатная terminal B2 failure.

Optional overflow возвращает `overflow`, увеличивает rejected и записывает trace;
очередь не вытесняет ранее принятое событие. `payload_limit`, `reserved_source`,
`stream_port_conflict`, `port_not_open` тоже явные отказы. Journal циклически
вытесняет старые записи, totals сохраняются: это bounded диагностика, не durable
история. External admission вне открытого tick запрещена.

Если protected slot занят или sample превышает limit: `required_delivery_failed`,
trace `required_failure`, terminal Heart reason `required_delivery_failed;
no_retry`; новый ACTION запрещён. При неправильном tick/occurrence binding
protected sample отклоняется, Heart останавливается. B2 завершает ещё открытый
переход своим единственным idle, если actuator не был вызван. Уже совершённое
исполнение не повторяется, pending не подменяется. Terminal stop отменяет остаток
очередей с cancelled totals/trace. Исключение producer также очищает backlog
после terminal Heart boundary, без повторного pulse.

Список seen delivery IDs не хранится: IDs выдаёт сам port, повторной отправки
готового envelope API нет. Это **не exactly-once и не durable delivery**.
Повторные optional предложения одного payload — разные события. Повтор snapshot
от owned producer дополнительно отклоняется штатной freshness-проверкой B2.

Delivery queue/journal occupancy ограничены capacities, размер payload ограничен
max_values. Неизменённые B2 records, snapshot freshness set и unresolved occurrence
set ограничены явным конечным max_ticks; бесконечная session не поддерживается.
ShortMemory сохраняет собственные bounds/prune. Callback producer обязан сам
вернуться за ограниченное время; preemption/worker scheduler здесь нет.

## Heart/world и pending priority

1. Штатный B2 открывает T через SyntheticTimeAdapter.
2. Sensor adapter открывает admission, вызывает optional ingress, берёт реальный
   sample у owned world, закрывает admission после dispatch.
3. Control закрывает lifecycle admission, если требуется. Protected sample
   dispatch не зависит от глубины noisy FIFO.
4. B2 observe/remember обрабатывает pending T+1 до retrieval/selection/coordinator.
   Чужие sensory streams не вызывают observe и не могут завершить pending.
5. Production coordinator единственный исполняет ACTION, создавая occurrence.
6. Штатный B2 finish вызывает либо один idle, либо принимает уже выполненный
   actuator advance. Adapter не вызывает world apply/idle и не повторяет finish.
7. После завершения pulse фиксируются native usage traces. Pause сохраняет
   bounded backlog, resume не превращает его в action. Stop очищает очереди.

Если T+1 sample отключён, pending остаётся на штатной границе. На overdue pulse
adapter пропускает authoritative sampling, B2 expire удаляет старую связь;
новая выборка возможна со следующего pulse. Это явно более консервативная
политика adapter: он не использует позднюю выборку для разрешения старого pending.
Чужие/старые payloads всё ещё могут доставляться observer с исходным tick.

## Проверки

[Targeted behavioral verifier](../tools/verify_native_bounded_delivery.py):
**18/18 PASS**. Проверены эффекты world/current present/retrieval/ShortMemory,
а не только имена statuses: distinct same-tick IDs, FIFO нескольких dispatch,
source/stream independence, неизменённые NFP objects/provenance, одинаковые values,
queue/budget limits, явный overflow, noisy flood и pending→recent occurrence,
remember до следующего apply, чужой T+1 и spoofed source, late payload без relabel,
missing T+1/expiration, protected slot failure без retry, pause/resume/stop,
control backlog, source binding отказ для чужого pending, cross-port FIFO,
manual producer exception cleanup, queued ACTION frame без повторного execution, post-world failure и неверный source tick.
Длительный тест: 600 ticks, 12 000 optional offers, journal ≤ 7, sensory queue ≤ 3,
фиксированный набор counters, B2 snapshot set ≤ max_ticks, ноль physical actions.

Все Python entry points: `PYTHONDONTWRITEBYTECODE=1 python -B`.
Writable Memory/manifest fixtures — только TemporaryDirectory; fixture stores
проверяются на неизменность. Production Memory inventory/hash проверяется отдельно.

| Existing verifier | Результат |
| --- | --- |
| [B2](../tools/verify_native_heart_b2.py) | 23/23 PASS |
| [B1](../tools/verify_native_session_b1.py) | 5/5 PASS |
| [Context/ShortMemory temporal](../tools/verify_nfp_context_short_memory.py) | 24/24 PASS |
| [Guarded execution](../tools/verify_nfp_remembered_action_guarded_execution.py) | 8/8 PASS |
| [Operational retrieval](../tools/verify_nfp_expsm_operational_retrieval.py) | 5/5 PASS |
| [Replay/idempotency](../tools/verify_nfp_native_feedback_replay_idempotency.py) | 15/15 PASS |

Итого **98/98 behavioral tests PASS**. Полная project regression не запускалась.

Четыре full-diff design verifier запущены реальными entry points:

- [retrieval](../tools/verify_nfp_expsm_operational_retrieval_design.py);
- [guarded execution](../tools/verify_nfp_action_materialization_guarded_execution_design.py);
- [Feedback](../tools/verify_nfp_native_feedback_design.py);
- [replay/idempotency](../tools/verify_nfp_native_feedback_replay_idempotency_design.py).

Первоначальный прогон дал 4/4 FAIL только из-за новых RND-014 paths.
После принятия review пользователь отдельно разрешил exact additions. В каждый
из четырёх allowlists добавлены только следующие три пути (12 exact entries):

```text
clc/runtime/native_bounded_delivery.py
docs/RND-014_native_bounded_delivery.md
tools/verify_native_bounded_delivery.py
```

Финальный результат реальных script entry points: **4/4 PASS**. Для каждого
отдельно выполнен negative changed-path control: временный untracked файл
`rnd014_unknown_changed_path_probe.txt` добавлялся в фактическое рабочее дерево;
каждый entry point вернул ненулевой exit code и unexpected-path диагностику
с точным именем probe. **4/4 negative controls PASS**. Probe удалён в finally.
Collectors/assertions и исторические разрешения не менялись, wildcard не добавлен.
Побайтовая реконструкция исходных четырёх verifiers удалением 12 новых entries
совпала с HEAD; никаких иных source edits в них нет.

Статически проверены поддерживаемые producer/consumer пути: чужой source_id
не открывает authoritative admission; accept не вызывает execution или manager;
observer delivery только записывает journal. Защищённый visual slot обслуживается
перед noisy sensory FIFO при зарезервированном dispatch budget. Dispatch не
вызывает world apply/finish; control даёт только lifecycle pause/stop и диагностику,
без memory-write/action authority. Required overload терминально закрывает Heart
admission и не повторяет уже выполненное действие. Это относится к API port;
callbacks и исключительно принадлежащие session компоненты остаются доверенной
конфигурацией, как описано выше. Исходные B1/B2 paths побайтово совпадают с HEAD.

Implementation и behavioral tests при закрытии не изменялись. Сохранённые
**98/98 PASS**, включая 600-tick bounded test, приняты без повторного запуска;
полная project regression не запускалась.

Финальный diff и staging ограничены ровно семью разрешёнными файлами:

```text
clc/runtime/native_bounded_delivery.py
tools/verify_native_bounded_delivery.py
docs/RND-014_native_bounded_delivery.md
tools/verify_nfp_expsm_operational_retrieval_design.py
tools/verify_nfp_action_materialization_guarded_execution_design.py
tools/verify_nfp_native_feedback_design.py
tools/verify_nfp_native_feedback_replay_idempotency_design.py
```

Production Memory: все 12 исходных файлов, точный inventory и SHA-256 совпадают
с началом закрытия и исходным HEAD. AGENTS.md unchanged/ignored. Markdown links,
полный diff включая новые файлы и `git diff --check` проверены. Новых bytecode
или lock files нет; существующие artifacts сохранены с исходными SHA-256.
Временный probe и audit/test outputs очищаются после финальной сверки;
TemporaryDirectory behavioral fixtures очищены в предыдущем прогоне.

## Ограничения и дальнейшие направления

Это первый локальный synthetic transport slice, не полный Квадрат или ДАР.
Нет универсальных plugins, wire/network transport, durable queues/outbox,
restart recovery, multi-pending, real actuators, новых writers или автоматического
обучения/Feedback APPLY/CREATE. Будущие внешние authoritative sensors требуют
настоящего producer binding; arbitrary metadata для этого недостаточно.
Новые causal semantics требуют отдельного решения. Несколько native visual
admissions за tick не поддерживаются. Fairness optional observers при постоянном
control traffic не гарантируется; обязательный visual имеет зарезервированный slot.
Subclass adapter зависит от малого private `_pulse` hook B2; изменение этого hook
потребует повторной проверки. ДАР в будущем может управлять delivery budgets,
но не полномочиями памяти или guard.

**RND-014 CLOSED. Review принят, разрешён один локальный commit семи файлов.
После закрытия — остановка. RND-015 не начат. Remote contact: none.**
