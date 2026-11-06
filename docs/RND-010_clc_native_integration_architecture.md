# RND-010 — Архитектурный мост CLC → NFP-native RNDeM

Дата: 2026-11-06. **CLOSED — архитектурное направление и границы первого интеграционного этапа приняты.** Реализация не начинается.

**FACT.** Контрольная точка: `main`, HEAD `5262fc6661189ec38d43da354c019ec8acd515de`, исходное рабочее дерево чистое; локальный `AGENTS.md` ignored и не отслеживается. RND-000 и RND-110 CLOSED согласно входному заданию; в RND-000 сохранена историческая формулировка остановки для review, RND-110 содержит явный closure K7. Это не изменение статуса прежних задач. Изучены актуальные исходники и проверочные сценарии; новые поведенческие прогоны в RND-010 не выполнялись. Исторический PASS ниже не означает новую проверку.

Обозначения: **FACT** — подтверждённая реализация на данном HEAD либо явно отмеченный результат review; **INFERENCE** — вывод из неё; **DESIGN PROPOSAL** — предлагаемое новое поведение; **OPEN QUESTION** — решение пользователя. Метка в начале абзаца или таблицы распространяется на весь соответствующий блок.

Основание: [RND-000](RND-000_architecture_inventory.md), [RND-110, включая актуальные K6–K7](RND-110_memory_write_authority_audit.md), [натуральный контракт](natural_pattern_data_contract.md), [phase map](runtime_tick_phase_map.md), [native execution](design_nfp_action_materialization_guarded_execution.md), [native context](design_nfp_context_and_short_memory.md), [Feedback replay](design_nfp_native_feedback_replay_idempotency.md). Исторические разделы аудита о дефекте F01 не описывают нынешний исправленный `save()`.

**FACT — принято по архитектурному review.** Стратегия A → минимальный C: сначала отдельная native session, общая инфраструктура выделяется по подтверждённым практическим потребностям; legacy CLC не переписывается. Первый контур B1 — synthetic visual, one-frame query, один pending, ACTION topology `(2,)`, подготовленный временный ExpSM. Следующий B2 — самостоятельные ticks Сердца, включая отсутствие действий и входных событий. Production Memory изолирована от экспериментального runtime; автоматические CREATE/APPLY запрещены. Restart recovery на первом синтетическом этапе не требуется; неопределённый результат исполнения не разрешает повторное действие. F02–F09 остаются открытыми findings и здесь не исправляются. Эти решения определяют первый интеграционный этап, а не окончательные возможности RNDeM. Внутренние способы реализации ниже сохраняют статус DESIGN PROPOSAL.

## A. Текущее состояние и реальные границы

### A1. Legacy runtime и время

**FACT.** [CLCRuntime](../clc/runtime/clc_runtime.py): `feed_audio`, `feed_sensor`, `feed_image` кладут одну операцию preprocessing в pool и немедленно вызывают `_run_tick(tick)`. Tick приходит от вызывающего кода, не от собственного Heart. Два feed с одинаковым tick — два вызова всего цикла, а не одно мультимодальное событие. `_run_tick` вызывает фазы 00–11 последовательно; импорт native класса не означает его исполнения в этих фазах.

**FACT.** [RuntimePhaseEntry/RUNTIME_PHASE_MAP](../clc/runtime/runtime_phase_map.py) фиксирует временные границы: 00 commit входа; 01 perception/prediction/tone/thought; 02 field/activation/pressure; 03 selection; 04 observers/effects; 05 mode/consolidation/writers; 06 outcome/Feedback/association/mechanism/candidates; 07 value feedback; 08 modulation; 09 final refresh; 10 observational views; 11 debug. Результат mechanism search фазы 06 не может менять уже выбранное действие фазы 03 этого tick. Не следует переносить поздние результаты «раньше» при замене прямых вызовов доставкой сообщений.

**FACT.** [ContextOperation](../clc/core/operations.py) несёт `op_id, marker, tick, source_module, target, payload`; mappings/sequences замораживаются, произвольные вложенные объекты — не обязательно. [ContextOpsPool](../clc/context/context_ops_pool.py) — неограниченный FIFO `push/extend/drain`, один draining manager. [ContextMemoryManager.apply_pending](../clc/context/context_memory_manager.py) применяет marker-specific payload в legacy ContextMemory. `target` не реализует подписки и не выдаёт полномочия.

### A2. Натуральные представления

**FACT.** [clc.patterns.model](../clc/patterns/model.py): `NFPFrame` содержит immutable numeric values `[0,1]`, modality, origin, topology, active_tick, frame_id, provenance_ref. `NFPWindow` требует одинаковую modality/topology, уникальные frame IDs и строго возрастающие ticks; непрерывность ticks не обязательна. Окно само не требует одинаковый origin. `PatternMoment` группирует кадры одного tick, в том числе разных модальностей; это не обязательный барьер ожидания всех источников. `NFPSequence` допускает перекрывающиеся окна и пока не имеет основного потокового исполнителя.

**FACT.** [VisualFieldTransducer.transduce](../clc/transduction/visual.py) превращает scalar-field `VisualFieldSnapshot` в VISUAL/EXTERNAL_SENSORY, сохраняя snapshot tick и `sensor_snapshot:*` provenance. [NFPWindowAssembler.push](../clc/transduction/windowing.py) принимает внешние совместимые кадры, выдаёт sliding window после заполнения; его `_seen_frame_ids` растёт за всё время жизни. Реализованный visual boundary не означает наличия natural audio/internal transducers.

**FACT.** Legacy [clc.core.nfp.NFPFrame](../clc/core/nfp.py) использует mapping activation IDs и TTL/decay; legacy [InputPreprocessor](../clc/preprocessing/input_preprocessor.py) производит эти кадры, не натуральную topology. [NFPReactivation.reactivate_frame](../clc/patterns/reactivation.py) создаёт INTERNAL_REACTIVATION со ссылкой на исходный frame. Retrieval не реконструирует сохранённый опыт как новое внешнее наблюдение.

**INFERENCE.** Объединение двух одноимённых NFPFrame или преобразование values в pat_* ради совместимости потеряет смысл native boundary. Нужны явно названные порты/адаптеры с указанными потерями, только когда появится конкретный потребитель. Для первого контура преобразование вообще не требуется.

### A3. Реальные native связи и скрытые зависимости

Таблица — **FACT**; механизмы исполняются отдельными явными вызовами, не автономным CLC.

| Граница | Реальный интерфейс и ограничение |
| --- | --- |
| External → active present | [ContextMemoryManager](../clc/context/context_memory_manager.py), `observe_external_sensory_window`: только visual EXTERNAL_SENSORY; monotonic end_tick; свой state отдельно от legacy side lists |
| Active present → retrieval | [NFPExpSMRetriever.retrieve](../clc/expsm/nfp_operational_retrieval.py), `NFPExpSMRetrievalQuery/Config`: свежий read-only mixed store, native structural matching; modality/topology/frame-count должны совпадать; legacy записи считаются, но не используются как native candidates; malformed/unsupported дают отдельные статусы |
| Retrieval → activation → selection | [ExpSMActivationModule.activate_native](../clc/expsm/expsm_activation_module.py) использует operational formula, confidence cap и top-N; [DecisionSelector.select_native](../clc/action/decision_selector.py) выбирает max activation с threshold, возвращает typed experience, не ACTION |
| Selection → execution | [SelectedNFPExecutionRequest / NFPRememberedActionExecutionCoordinator.execute](../clc/actuation/remembered_action_execution.py): context.end_tick = selection tick = world.current_tick, свободный pending slot, materialization, topology, guard, transducer, world, tracking, observation |
| Action boundary | [NFPActionOccurrenceMaterializer.materialize](../clc/actuation/remembered_action_execution.py) создаёт fresh ACTION_GENERATED frame и UUIDv4 occurrence; [ActionTransducer.transduce](../clc/actuation/motor.py) поддерживает ACTION topology `(2,)`; [ModeActionGuard.is_native_action_allowed](../clc/system/mode_action_guard.py) проверяет current tick и mode=active, не общую безопасность реального actuator |
| Observation → ShortMemory | Coordinator может сам снять snapshot и создать одно-кадровое after-window; manager возвращает `RecentCausalTransition` только на T+1; [ShortMemory.remember/prune](../clc/context/short_memory.py) ограничивает entries и age, требует порядок observation, запрещает retained duplicate transition_id |
| Prediction check | [NFPFeedbackEvaluator.evaluate](../clc/expsm/nfp_native_feedback.py) отдельно сравнивает signed predicted/actual effects с binding source/TargetCore/action/occurrence; не reward и не writer |

**FACT.** [Pending/RecentCausalTransition](../clc/context/causal_transition.py) — один pending на manager, expected tick строго action_tick+1. `expire_pending_if_overdue` удаляет только при `current_tick > expected`, а не на самом T+1. Late sensory может стать новым present, но не завершает старый переход. Manager принимает равные end_tick; второй такой observation не дополняет уже закрытый переход. ShortMemory допускает несколько переходов с одинаковым observation_tick при разных IDs, однако это не поддержка нескольких одновременных pending в manager.

**FACT.** Проверочные сценарии [retrieval verifier](../tools/verify_nfp_expsm_operational_retrieval.py), [execution verifier](../tools/verify_nfp_remembered_action_guarded_execution.py), [Feedback verifier](../tools/verify_nfp_native_feedback_evaluation.py) демонстрируют отдельные участки/сборки с fixtures и synthetic world. Selected может быть построен fixture: сам execution test не доказывает, что каждый вызов прошёл retrieval. Известные несовпадения ShortMemory verifier с occurrence/import контрактами описаны в RND-000; их нельзя скрыть объявлением всей цепочки green.

**FACT.** Native методы достаточно самостоятельны для reuse, но constructors activation и guard используют `PatternRegistry.id()`, что может писать manifest. `ContextMemoryManager` требует legacy ContextMemory/pool даже для native state. Native selector не наследует legacy candidate cooldown/suppression и не вызывает guard: guard остаётся у execution. [SyntheticClosedLoopVisualWorld](../scenarios/support/synthetic_closed_loop_visual_world.py) увеличивает `current_tick` только в `apply_actuator_signal`, snapshot лишь считывает состояние и увеличивает snapshot ID. Это существенные зависимости, а не готовый непрерывный runtime.

## B. Минимальный рабочий native-контур

### B1. Первый вертикальный срез

**DESIGN PROPOSAL.** Начать с отдельной локальной native session без CLCRuntime: synthetic world + temporary ExpSM fixture/manifest, ContextMemoryManager с пустыми ContextMemory/ContextOpsPool, ограниченная ShortMemory, существующие retriever/activation/selector/coordinator/guard/transducers. Fixture содержит явно подготовленный native опыт; получение/обучение такого опыта не условие первой интеграции.

```text
external snapshot → VisualFieldTransducer → one-frame NFPWindow
  → ContextMemoryManager.active present → NFPExpSMRetriever
  → activate_native → select_native → SelectedNFPExecutionRequest
  → coordinator: fresh ACTION + occurrence → guard → ActionTransducer
  → synthetic world → external snapshot at T+1
  → manager RecentCausalTransition → ShortMemory
```

**DESIGN PROPOSAL.** Первый результат — повторяемая bounded session из нескольких связанных эпизодов, а не полный ПЖК. Начальное и subsequent query windows одно-кадровые, как и coordinator after-window; fixture context имеет ту же длину/topology. Это устраняет несовместимость multi-frame query и single-frame observation без изменения retrieval. Assembler/PatternMoment для этого среза не обязательны. Retrieval без кандидата или selection=None — наблюдение без действия, не fallback на произвольную legacy команду.

**DESIGN PROPOSAL.** Точный протокол первого среза:

1. Получить snapshot T, создать уникальные frame/window IDs и зарегистрировать external present.
2. Retrieval выполняется только для этого present. Сохранить end_tick рядом с selection; при изменении present/мира selection отклоняется и не пересчитывается молча внутри исполнителя.
3. Вызвать `execute(..., observe_consequence=True, short_memory=short)`. В текущем synchronous synthetic сценарии world переводит T→T+1, coordinator снимает настоящее external observation. Только он вызывает actuator; транспорт не делает дополнительных apply.
4. Проверить не только status: `recent_transition`, same occurrence, provenance и фактическую вставку в ShortMemory. `EXECUTED_AND_OBSERVED` возможен с detail `short_memory_retention_failed`; это неполный результат среза, не повод повторить действие.
5. Следующая retrieval использует новый external present. Отдельно проверяются отказ guard, stale selection, занятой pending, отсутствие match, observation pending, late observation и post-world tracking failure. После неопределённого execution остановить выдачу следующих действий до разрешения состояния.

**INFERENCE.** B1 уже можно собрать из текущих компонентов. Он проверит интеграцию, но ещё зависит от действий для продвижения synthetic времени. Поэтому первый действительно непрерывный контур требует малого следующего среза B2; нельзя переименовать цикл вызовов coordinator в готовый Heart.

**FACT — граница принятого этапа.** Один pending transition, визуальный сенсор, one-frame окна, ACTION topology `(2,)` и сериализация исполнения — временные ограничения первого интеграционного контура. Они не определяют окончательные возможности RNDeM, ЭХО, Квадрата или будущих параллельных процессов. Универсальный multi-pending manager сейчас не вводится.

### B2. Первый непрерывный вариант

**DESIGN PROPOSAL.** Добавить малый Heart driver, session owner и synthetic time adapter; не расширять `_run_tick`. Heart выдаёт T независимо от сенсоров/действий. При исполнении в T coordinator вызывается с `observe_consequence=False`: мир физически уже продвинулся на T+1, но after snapshot допускается в active present лишь на Heart T+1. При отсутствии действия adapter продвигает synthetic world без actuator, без ACTION и без occurrence. Это новое поведение адаптера, которого сейчас нет; недопустимо подделывать «нулевое действие» для течения времени.

**FACT — принятый контракт будущего RND-013.** Сердце отвечает за собственный ритм, но не обязательно само изменяет состояние среды. За соответствующий переход T→T+1 синтетический мир продвигается ровно на один шаг модельного времени независимо от наличия действия. Если `world.apply_actuator_signal` уже продвинул мир, адаптер не выполняет второго продвижения. При отсутствии действия временной адаптер может продвинуть мир без ACTION и occurrence. Observation T+1 принимается только на соответствующей временной границе; повтор action ради продвижения времени недопустим. Это требование будущей реализации, synthetic world в RND-010 не меняется.

**DESIGN PROPOSAL.** На Heart T+1 сначала принять выделенное observation для pending и явно вызвать `ShortMemory.remember`, затем разрешить новую selection. Coordinator не вызывается повторно для получения observation. Если observation нет — только housekeeping; на T+2 pending expire, сохраняется диагностический факт потери связи, действие не повторяется. Адаптер не перемаркирует старый snapshot текущим tick. Начальный протокол приёма допускает один выбранный visual sample на поток/tick; дополнительные наблюдения сохраняют identity и не переписывают after первого завершённого transition.

**DESIGN PROPOSAL.** Feedback evaluation можно добавить как чистого подписчика после B1/B2. Ни CREATE, ни APPLY, ни consolidation writers не нужны. ShortMemory→effect/evidence/grouping→proposal остаётся отдельной read-only ветвью, а не обязательным шагом до первого действия. Production Memory не передаётся writable компонентам; все потенциально пишущие registry/store constructors получают только temporary root. Одного safe_demo недостаточно.

## C. Минимальные контракты ПЖК / Сердца / Квадрата / ДАР

Способы реализации C — **DESIGN PROPOSAL**, не описание готовых подсистем. Принятые ограничения первого этапа и уточнения времени/наблюдений явно отмечены как результаты review.

### C1. ПЖК и Сердце

- Session owner отвечает за start/run/pause/stop и lifetime объектов. Heart выдаёт целочисленный monotonic tick; ручной источник используется для детерминированной проверки, собственный monotonic clock — для живого pacing. Wall-clock UTC — metadata, не occurrence identity и не основа порядка native переходов.
- Несколько событий имеют один tick и разные event/source IDs. Tick не означает обязательное событие, решение или действие; во всём session допускается максимум один outstanding native execution по текущему manager.
- External source timestamp/sequence и время приёма сохраняются отдельно от assigned active_tick. Для первого synthetic adapter время мира и tick согласованы правилами B2. Для будущего реального источника нужна явная mapping policy; нельзя перезаписывать historical frame.active_tick ради прохождения stale guard.
- Пустой tick вызывает `expire_pending_if_overdue(T)`, `ShortMemory.prune(T)` и bounded diagnostics, но не фабрикует sensory evidence, retrieval по stale present или действие. Heart не выбирает содержимое реакции.
- Pause ставится на безопасной границе dispatch: прекращает новые ticks и новые execution admissions, фиксирует pending/in-flight. Для synthetic session среда тоже заморожена. Resume продолжает tick; pause не равна consolidation/recovery mode. Живой внешний мир во время паузы не обещает сохранение T+1 и требует нового observation/revalidation.
- Stop запрещает новые actions, завершает доступную доставку observation в установленном бюджете, сообщает unresolved occurrence и закрывает session. Отмена ожидания не отменяет физический эффект; restart без durable pending не обещает восстановить его.

**FACT — принятое различие времени и свидетельства.** Новый Heart tick без нового sensory input означает течение внутреннего времени, а не новое внешнее свидетельство. Старый NFP нельзя выдавать за свежий из-за наступления следующего tick. Новая сенсорная выборка с неизменившимися значениями допустима как новое наблюдение, если действительно получена заново и имеет корректные tick, ID и provenance. Отсутствие входа или подходящего опыта не требует фиктивного действия. Обслуживание pending, retention и diagnostics продолжается и на пустых ticks.

### C2. Квадрат — доставка, не когнитивный центр

| Контракт | Минимальное правило |
| --- | --- |
| Что передаётся | Native frame/window либо typed retrieval/selection/execution/transition result через конкретные порты; отдельно control markers: tick, pause, stop, deadline/overload |
| Кому | Явная локальная wiring table: sensory→present; present→retrieval; candidates→activation→selector; selection request→executor; observation→present/ShortMemory; диагностика получает read-only результат |
| Основание маршрута | Тип порта, source/stream и session wiring; marker/target не permission. Executor повторно проверяет свежесть/guard, writers отдельно проверяют authority |
| Минимум metadata | Session/source/stream identity, delivery event ID, source time при наличии, admission tick/order, ссылки на исходные IDs; occurrence только после materialization и переносится неизменно |
| Порядок | FIFO внутри потока, монотонный порядок приёма в manager; без глобального барьера всех источников. Heart T+1 observation перед новой execution admission; сериализация state mutations, независимые pure computations могут идти отдельно |
| Буферизация | Ограниченные очереди конкретных портов и limit работы за dispatch; не общий универсальный broker. Не смешивать pending observation и необязательный debug в одной вытесняемой очереди |
| Перегрузка | Прекратить admission новых actions до потери обязательного observation; явный отказ/overload result. Не молча выбрасывать action intent после физического исполнения. Для необязательной телеметрии — ограничение/счётчик пропусков; coalescing sensory только до admission и с явной потерей temporal evidence |
| Provenance | Доставка не меняет origin, active_tick и provenance_ref. Дополнительные source/session refs хранятся во внешней оболочке/журнале session, не требуют заранее общего формата NFP |

**FACT.** Нынешний transducer snapshot ref и счётчики frame/window/transition локальны; `IdGenerator` и retrieval candidate IDs не дают глобальной event identity. **DESIGN PROPOSAL.** Scope таких ссылок session/source обязателен, но не заменяет UUID occurrence. Не объявлять `provenance_ref` полным durable графом происхождения: serialization опыта хранит структуру/creation metadata, не всю sensor историю.

**INFERENCE.** ContextOpsPool полезен как образец простого FIFO и границы single-writer. Его нельзя использовать как готовый Квадрат: нет bounds, ack/backpressure, потоков и подписок; `apply_pending` при этом пишет legacy context и ожидает свой payload. Первый native transport может быть прямыми typed вызовами и маленькими очередями. Общий memory layout, wire schema, actor framework и детальный scheduler сейчас не закрепляются.

### C3. Точки будущего ДАР

**DESIGN PROPOSAL.** Уже нужны admission quota по потоку, предел queued items, лимит retrieval/store size и длительности dispatch, число кандидатов, бюджет диагностики, pause/overload сигнал, pending-observation priority и измерение latency/queue depth. Если синхронный retrieval не укладывается в бюджет, он прекращает блокировать Heart через изолированную задачу; результат всё равно проходит stale check. ДАР позже меняет бюджеты/приоритеты через эти точки, но не origin/occurrence, action guard или memory authority. Полная оптимизация/распределение вычислений вне scope.

## D. Стратегии перехода

Таблица — **INFERENCE** из A; объём относительный, без обещания календарных сроков.

| Вариант | Изменения и reuse | Ограничения / риск legacy | Проверяемость и развитие |
| --- | --- | --- | --- |
| A. Отдельный малый native runtime | Малый session owner, wiring и time adapter; reuse native API без преобразования паттернов | Низкий риск для phase map; constructor registry и duplicate lifecycle logic требуют контроля. Сам по себе не объединяет CLC и native | Высокая изоляция; быстро проверяется B1/B2; позже есть риск двух расходящихся инфраструктур |
| B. Включить native прямо в CLC | Изменения feed/phases/context/selection/execution, адаптация входов и времени | Высокий риск скрытого same-tick эффекта, legacy Feedback/writer side effects; два representation и два selection пути в одном runtime | Реальные phase snapshots обязательны на каждом шаге; полезно позже для конкретного модуля, дорого как первый вертикальный срез |
| C. Общая минимальная инфраструктура | Выделение lifecycle/time/transport contracts и два независимых адаптера | Средний/высокий начальный объём; опасность универсального scheduler до знания требований; legacy feed семантика должна сохраниться | Хорошая целевая совместимость; проверка differential legacy + native sessions, но не следует делать готовность всего C условием B1 |

**FACT — направление A → минимальный C принято.** A сначала, с узкими портами C1–C3; затем C только в объёме подтверждённых общих нужд. **DESIGN PROPOSAL.** B можно рассматривать позднее точечно, когда известен конкретный native producer/consumer и зафиксирована его phase visibility. Не создавать два независимых tick authority внутри одного native session. Legacy пока живёт со своим caller-supplied tick и прежним порядком, без автоматической пересылки native observation в его Memory.

**DESIGN PROPOSAL.** Первый совместный checkpoint — запуск обеих изолированных sessions под одним тестовым lifecycle driver с раздельными roots/state: результаты legacy phase trace совпадают с baseline; native trace удовлетворяет B2. Это совместная проверка инфраструктуры, не объявление когнитивного слияния. Извлекать общий transport лишь после этого checkpoint; удалять первый native adapter не требуется.

## E. Dependency map и малые следующие задачи

Все номера RND-011–015 ниже — **DESIGN PROPOSAL**, предварительная декомпозиция дальнейшей работы, не разрешение автоматически её выполнять; резервирования/создания задач не было. Следующая задача будет начата отдельно в новом чате Codex. Каждая предлагаемая задача оставляет систему в проверяемом состоянии.

```text
RND-011 ─→ RND-012 ─→ RND-013 ─────────→ RND-015
              └────→ RND-014 ─────────→ RND-015
RND-110 findings ─→ отдельные authority решения (не блокируют isolated B1)
RND-014 ─→ optional pure Feedback evaluation (без APPLY)
```

| Задача | Цель / существующие компоненты | Минимальное новое поведение | Зависимости | Проверяемый результат и критерий завершения | Вне scope |
| --- | --- | --- | --- | --- | --- |
| RND-011: согласование проверочных контрактов | ShortMemory/context, occurrence, существующие native verifiers | Разобрать известные import/UUID несовпадения RND-000 и закрепить актуальный контракт, исправлять только подтверждённые расхождения | Review RND-010; Stage-2 identity сохраняется | Реальные script entry points выбранных context/execution verifiers выполняют assertions; реальные regression cases не ослаблены; остаточные failures явно объяснены | Новый runtime, «green» через пропуск checks, полная регрессия |
| RND-012: vertical native session B1 | Transducer, manager, retriever, activate_native, select_native, coordinator, synthetic world, ShortMemory | Малая bounded wiring session, temporary fixture roots, trace source/selection/occurrence | RND-011 для достоверного acceptance; черновая сборка может идти параллельно разбору | Несколько эпизодов проходят полный путь, отдельные no-match/guard/stale/pending/failure cases; action count и ShortMemory проверены; original Memory hashes неизменны | Heart реального времени, writers, обучение, все сенсоры |
| RND-013: собственные ticks B2 | Тот же coordinator observe=False, manager expire, ShortMemory prune, synthetic world adapter | Manual + monotonic pacing Heart, idle advance без ACTION, pause/stop; observation T+1 отдельно | Контракты RND-012 | Idle ticks продолжаются без фиктивного sensory/action; ровно один шаг мира на переход, без второго advance после apply; свежая неизменившаяся выборка отличается от отсутствия входа; observation принимается на границе T+1; нет stale action; несколько событий/tick; pause/stop с pending; deterministic traces не зависят от скорости wall clock | Общий scheduler, real actuator, durable recovery |
| RND-014: bounded delivery и provenance | Native typed results, ID/source refs; ContextOpsPool только как reference | Малые port queues/admission limits, session/source scope, overload и bounded trace | Порты RND-012; развивается параллельно RND-013 | Flood/noisy-source test не голодает observation; overflow явно виден, нет duplicate world apply; память session ограничена заданным run budget | Полный Квадрат/ДАР, universal wire schema |
| RND-015: совместный checkpoint A→C | Legacy phase map/scenario infrastructure + native session | Общий lifecycle harness с независимыми adapters; извлечение только реально общих частей | RND-013/014 | Legacy phase order/same-vs-next-tick visibility и snapshots сохранены, native idle/action/stop cases проходят совместно; roots разделены | Слияние NFPFrame, перенос всех legacy модулей, общий cognitive loop |

**DESIGN PROPOSAL.** Optional pure Feedback/evidence ветвь может развиваться после RND-012 независимо от Heart: evaluator/effects/grouping только читают completed transitions. Решения F02/F03/F06 вести отдельной линией. Никакая из этих задач не требует законченного ПЖК, всего Квадрата или полного ДАР. Автоматический APPLY, durable pending/outbox и реальные actuators требуют отдельных контрактов и review, а не незаметного расширения RND-013.

## F. Инварианты, риски и границы доказательств

### F1. Что сохраняется без ослабления

**FACT + DESIGN PROPOSAL (обязательство сохранения существующего контракта).** [Stage-1 transaction](../clc/consolidation/expsm_store_transaction.py), [Stage-1 verifier](../tools/verify_expsm_persistence_stage1.py), [Stage-2 verifier](../tools/verify_nfp_native_feedback_replay_idempotency.py) и [исправленный CRUD](../Memory/ExpSM/Exp_CRUD.py) остаются за пределами первой интеграции:

- Per-resolved-path lock/reentrancy, strict fresh load, complete-store replacement, v2 metadata/receipt preservation, fail closed на invalid store; lock не является разрешением записи. Не обещается абсолютная power-loss durability или multi-file atomicity.
- Public CRUD save отклоняет stale baseline; сохраняет authoritative формат и точный receipt ledger/index. Он не выдаёт receipts и не делает legacy→v2 migration. Законная migration с atomic metric+receipt принадлежит native APPLY (RND-110 K6/K7).
- Occurrence UUID создаётся один раз при materialization; Heart tick, similarity, selection ID и effect не заменяют identity. Same key+same digest — ALREADY_APPLIED; same key+changed evidence и reuse occurrence с другим source — EVENT_CONFLICT. TargetCore и fresh operational metrics проверяются отдельно.
- APPLY atomic metric+receipt не даёт exactly-once физического действия. Readback failure после replace — неопределённость, reconciliation читает, не исполняет повторно; CREATE также не становится безопасным для слепого retry.
- В native-контуре нет auto Feedback APPLY/CREATE, legacy Outcome Feedback или consolidation write chain. Routing markers и mode=active не являются universal memory-write authority.
- External observations, remembered structures, INTERNAL_REACTIVATION и ACTION_GENERATED не смешиваются. Сходство — не identity, signed endpoint difference — не доказательство единственной причины.

### F2. Остаточные риски и практическое обращение с ними

Таблица: статус — **FACT**, мера — **DESIGN PROPOSAL**.

| Риск / ограничение | Мера первой интеграции |
| --- | --- |
| World call может бросить exception после частичного физического эффекта; WORLD_EXECUTION_FAILED не доказывает отсутствие эффекта для произвольного world | Ни один статус после входа в world call не запускает автоматический физический retry. Зафиксировать occurrence/result, остановить новые actions при неопределённости; использовать только synthetic adapter с известной семантикой |
| Pending регистрируется после world apply; есть окно потери tracking и нет durable pending outbox | Проверить post-world tracking failure; не обещать восстановление после crash/restart и не генерировать replacement occurrence |
| Один pending и строго T+1, не общий causal engine | Сериализация execution; late observation не достраивает старый transition. Несколько sensory streams могут поступать, но только явно выбранный visual stream завершает pending; parallel causal observations требуют нового контракта |
| NFPWindow/assembler не принимают два кадра одного потока с одним tick | Разные потоки/PatternMoment не проталкивать в одно temporal window. Первый срез one-frame; multisensor admission позже |
| Unbounded pool, assembler seen-ID set, journals; durable receipt ledger растёт | Портовые bounds и run cap с самого начала; ShortMemory pruning на idle. Не выдавать бесконечную работу с assembler за bounded. В первой session assembler не нужен; долговременную retention seen-IDs проектировать отдельно. Receipts нельзя обрезать без сохранения replay гарантий |
| Global/source identity недостаточна в текущих локальных counters | Session/source scope поверх исходных refs; UUID occurrence сохраняется независимо. Restart native session не обещает продолжения transition counters |
| Нет универсальной write authority, safe_demo зависит от root и входа | Temporary stores/manifest, без CLCRuntime и default administrative paths; проверять всё дерево original Memory, не четыре файла |
| Legacy phase visibility можно нарушить общей доставкой | Separate adapters и differential checkpoint; никакого native результата в phase 03 задним числом |
| Synthetic success ограничен topology `(2,)` и visual world | Отчёт доказывает wiring/guards/temporal bookkeeping, не общую когнитивную способность, обучаемость или безопасность внешнего actuator |

**FACT.** F02–F09 RND-110 остаются открытыми: F02 draft review/status policy; F03 manifest write authority; F04 root isolation runtime; F05 legacy Outcome/admin policy exceptions и mutating defaults; F06 admin CRUD/low-level authority; F07 отдельная durability domains и multi-file gaps; F08 ограниченный hash coverage/небезопасный original-root verifier; F09 trusted configuration и отсутствие общего mode/write gate. **DESIGN PROPOSAL.** Не исправлять их попутно: B1 обходится без этих write routes, registry изолирован. Для production integration F02/F03/F06 требуют отдельного решения; F04/F08 — root/whole-tree checks; F05/F07/F09 — явные ограничения authority/durability. Это mitigation выбранного контура, не закрытие findings.

## G. Вопросы для решения пользователя

**FACT — review завершён.** Вопросы стратегии A → минимальный C, scope B1/B2 и отсутствия restart recovery на первом синтетическом этапе решены, как зафиксировано в начале документа и разделах B–C. Пустые ticks не создают свидетельство; новые реальные выборки могут иметь те же values. Временные ограничения первого контура не становятся ограничениями целевой RNDeM.

**OPEN QUESTION — для отдельной будущей задачи, не блокирует закрытие RND-010.** При разборе F02/F03/F06: входят ли review/status и технический manifest в профильные разрешения записи, где проходит административная authority? Ответ не требуется для изолированного B1 и не должен подразумеваться routing контрактом. F02–F09 остаются открытыми findings; их исправление здесь не разрешено.

**DESIGN PROPOSAL.** Конкретные capacity, pacing interval и implementation queue type выбрать в малых реализационных задачах по проверяемым нагрузкам. Это инженерные параметры, не дополнительные архитектурные вопросы к пользователю. Общий scheduler, transport representation и durable chronology остаются незакреплёнными.

## Проверка области изменения и остановка

**FACT.** RND-010 закрывается только документальным изменением после принятого review. Исходники, tests/verifiers, интерфейсы, ADR, runtime, AGENTS и production Memory не изменяются; регрессия не требуется и не запускалась. Historical PASS относится к указанным RND-000/RND-110 отчётам, а не к новой session. При закрытии проверены относительные Markdown-ссылки, согласованность уточнений и `git diff --check`; SHA-256 inventory всех исходных файлов, включая 12 файлов Memory и локальный ignored/untracked AGENTS, неизменен. Единственный добавляемый в локальный коммит файл — `docs/RND-010_clc_native_integration_architecture.md`; staged paths проверяются отдельно.

**RND-010 CLOSED.** Архитектурное направление и границы первого интеграционного этапа приняты. Разрешён один локальный коммит `docs: approve RND-010 native integration architecture`, только с этим документом. Последующие задачи не начаты; RND-011 автоматически не запускается. Remote contact: none; fetch/pull/push, обращения к origin, merge и tags не выполняются. После закрытия — остановка.
