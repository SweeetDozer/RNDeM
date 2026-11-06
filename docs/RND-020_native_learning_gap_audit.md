# RND-020 — Native Learning Loop Gap Audit

Дата: 2026-11-06. **CLOSED — архитектурный review принят, ACCEPTED FOR CLOSURE.**
Исходные `main`, HEAD `f6f0dc393acb02597f1093f91e04e9127ea71a73`, чистое дерево.
LOCAL ONLY: remote-операций и обращений к внешним сервисам нет.

## 1. Вывод и основание

**FACT.** Номер не занят фактической задачей в доступном локальном дереве и
локальной истории с упоминанием RND-020 в commit subject. Поиск включая hidden
files, кроме `.git`, обнаружил только заявления «RND-020 не начат» в RND-019.
Историческое резервирование номера в генплане само по себе не конфликт.
Это проверка доступного checkout/history, не утверждение о remote.

**Главный разрыв — INFERENCE:** отсутствует владелец ограниченного handoff
`retained actual transition → evidence/grouping → explicit proposal → reviewed
creation request → policy-gated CREATE`. Низкоуровневые звенья уже существуют;
ShortMemory автоматически ничего не консолидирует. Дополнительный независимый
разрыв: session выбирает только remembered experience, поэтому с пустой native
ExpSM не совершает первого исследовательского действия. Нельзя скрыть этот
разрыв фиктивным SelectedNFPExpSMExperience или заранее подготовленным целевым опытом.

Полноценный строгий эксперимент без начального опыта **сейчас невозможен**.
Минимальный безопасный путь требует явной authority для начального действия и
узкого bounded proposal/CREATE handoff. Новая память, новый selector и общий
learning framework не нужны. Ни provisional semantics, ни durable CREATE dedup
не следует приписывать существующему writer.

Источники: [RND-000](RND-000_architecture_inventory.md) — исторический inventory;
[RND-110](RND-110_memory_write_authority_audit.md) — актуальные remediation и F02–F09;
[RND-012](RND-012_native_session_b1.md), [RND-013](RND-013_native_heart_b2.md),
[RND-014](RND-014_native_bounded_delivery.md),
[RND-015](RND-015_legacy_native_joint_checkpoint.md),
[RND-016](RND-016_echo_expectation_continuity.md),
[RND-017](RND-017_multitick_internal_work.md),
[RND-018](RND-018_minimal_dar_admission.md),
[RND-019](RND-019_echo_dar_cognitive_integration.md). Устаревшие «future/design-only»
в ранних документах сверены с текущими production API ниже. Изучены релевантные
разделы и целевые реализации; полный репозиторий и регрессия не перечитывались/не запускались.

## 2. Полный путь и фактические API

Обозначения: **S** — уже вызывается native session; **I** — изолированное явное API;
**GAP** — предлагаемая связь, которой сейчас нет. Production API означает код
компонента, а не разрешение запускать его на Production Memory. Synthetic world
находится в scenario support и не является реальным actuator.

```text
world.snapshot → VisualFieldTransducer.transduce → external NFPWindow
  → ContextMemoryManager.observe_external_sensory_window                   [S]
  → NFPExpSMRetriever.retrieve → activate_native → select_native            [S]
  → SelectedNFPExecutionRequest → coordinator.execute
  → materializer → ModeActionGuard → ActionTransducer → world.apply        [S]
  → настоящий snapshot в T+1 → manager → RecentCausalTransition
  → ShortMemory.remember                                                  [S]
  → ExperienceEvidenceFactory.build → grouper.observe → make_proposal      [I; GAP owner]
  → ExpSMRecordCreationRequestBuilder.build → NFPExpSMCreateWriter.create   [I; GAP admission]
  → isolated ExpSM → fresh retrieve → activate_native → select_native
  → новый ACTION occurrence → guard → world                               [S после явного CREATE]

empty retrieval ── нет production native exploration branch ──> первое действие [GAP]
```

| Переход / реальный API | Вход и реально доступные данные | Identity / provenance | Authority, состояние и что мешает автоматизации |
| --- | --- | --- | --- |
| External → NFP: `world.snapshot()`, `VisualFieldTransducer.transduce`, `NFPWindow` | VisualFieldSnapshot: shape, values, active_tick, snapshot_id; one-frame visual window | Immutable frame/window, EXTERNAL_SENSORY, sensor snapshot provenance | **S**. Sensor обязан поставлять настоящее наблюдение; remembered/internal frame не допускается как actual. Источник времени не переименовывается |
| NFP → Context: `ContextMemoryManager.observe_external_sensory_window` | Present window; при существующем pending — точный T+1 | Pending сохраняет before/action и execution_occurrence_id | **S**. Manager не доказывает источник sensor; bounded delivery обеспечивает owned-world binding. Нет универсальной проверки внешнего producer |
| Context → selected: `NFPExpSMRetriever.retrieve(query, config)`, `ExpSMActivationModule.activate_native`, `DecisionSelector.select_native` | Current external context, mixed store; candidate action/effect и operational metadata | source_experience_id → activation_id → selection_id, TargetCore | **S**. Read-only retrieval; no match не создаёт action. Нет exploration authority |
| Selected → ACTION: `SelectedNFPExecutionRequest`, `NFPActionOccurrenceMaterializer.materialize` | Typed выбранный опыт и свежий context end_tick | Новый ACTION_GENERATED, UUIDv4 execution_occurrence_id; source/selection/TargetCore | **S**. Это materializer remembered action, не конструктор произвольного исследовательского intent |
| ACTION → World: `NFPRememberedActionExecutionCoordinator.execute`, `ModeActionGuard.is_native_action_allowed`, `ActionTransducer.transduce`, `world.apply_actuator_signal` | Fresh T, свободный causal slot, допустимая motor topology `(2,)`, активный mode | Один occurrence на materialization; actuator signal связан с ACTION | **S**. Guard до apply; один apply. Нет blind retry или права обойти coordinator |
| World → actual: B1 coordinator с `observe_consequence=True`; B2 `NativeHeartSession._pulse` с sensor следующего tick | Настоящий snapshot, не predicted_effect; T+1 относительно action T | Новый snapshot/frame/window; occurrence переносится через pending в recent | **S**. B2 execute использует `observe_consequence=False`; housekeeping/observation precede retrieval. Late/missing observation не достраивается prediction |
| Actual → ShortMemory: `ShortMemory.remember(recent, current_tick=...)`, `prune`, `snapshot` | Recent before/action/after; bounded count и age | Сохраняется recent с occurrence; transition counter локален manager | **S**. Только RAM; eviction не является trigger обучения. B1 отдельно проверяет retention identity; нельзя переносить эту проверку на все paths без анализа |
| Recent → effect/evidence: `ObservedEffectExtractor.extract`, `ExperienceEvidenceFactory.build` | External visual endpoints, ACTION, delta after−before; zero delta допустима | effect/evidence hashes от transition/frame-derived identity; исходные NFP не изменяются | **I**. Нет вызова из session. Evidence не имеет отдельного execution_occurrence_id; нужна внешняя проверенная связь с retained recent |
| Evidence → proposal: `ExperienceEvidenceGrouper.observe`, `.candidates`, `.make_proposal(candidate_id, current_tick=...)` | Три независимых similarity thresholds и min_support; первый реальный exemplar | evidence IDs, локальные candidate/proposal counters; proposal содержит refs, не сами NFP | **I**. DUPLICATE по evidence_id, AMBIGUOUS без изменения групп; нет bounded lifetime по умолчанию, durable identity и автоматической выдачи proposal |
| Proposal → request: `ExpSMRecordCreationRequestBuilder.build(proposal, representative_evidence, request_id=...)` | Нужен отдельно сохранённый exemplar; serializes context/action/observed effect; operational defaults | Проверяется representative_evidence_id, unique support count; creation metadata хранит support/proposal/tick/profile | **I**. Не проверяет физическое выполнение, независимость support или causal validity. Нет full provenance/occurrence chain в persisted record |
| Request → ExpSM: `NFPExpSMCreateWriter.create` | Typed v1 request, только supported defaults, store path и MemoryMutationPolicy | Writer выделяет numeric max+1 record ID; request_id не durable dedup key | **I**. `allow_expsm_commit`, strict fresh load, transaction/write/readback. Нет native review/admission owner, CREATE receipt или provisional статусного фильтра |
| Persisted → retrieval → selection → action | Валидный native record, compatible modality/topology/frame count, threshold и activation | Новый retrieval читает store заново; новый ACTION получает новый UUID | **S**, если запись явно создана. Нет необходимости reload legacy adapter; не использовать legacy fallback. Selection ранжирует activation, не причинную достоверность или полезность |
| Used experience → Feedback | `NFPFeedbackEvaluator.evaluate(execution, transition, config)`; `NFPFeedbackApplyWriter.apply` | Exact-source TargetCore и occurrence; predicted/actual evidence; Stage-2 receipts | **I**, не автоматическая native learning subscription. APPLY требует отдельного update permission; это обновление использованного опыта, не CREATE нового |

Ссылки на реализации: [native session](../clc/runtime/native_session.py),
[Heart session](../clc/runtime/native_heart_session.py),
[delivery](../clc/runtime/native_bounded_delivery.py),
[transition](../clc/context/causal_transition.py),
[manager](../clc/context/context_memory_manager.py), [ShortMemory](../clc/context/short_memory.py),
[execution](../clc/actuation/remembered_action_execution.py),
[motor](../clc/actuation/motor.py), [effects](../clc/experience/effects.py),
[evidence](../clc/experience/evidence.py), [grouping](../clc/experience/grouping.py),
[representation](../clc/experience/expsm_representation.py),
[CREATE](../clc/experience/expsm_native_create.py),
[retrieval](../clc/expsm/nfp_operational_retrieval.py),
[activation](../clc/expsm/expsm_activation_module.py),
[selector](../clc/action/decision_selector.py),
[Feedback evaluation](../clc/expsm/nfp_native_feedback.py),
[Feedback apply](../clc/expsm/nfp_native_feedback_apply.py),
[transaction](../clc/consolidation/expsm_store_transaction.py).

## 3. Что действительно приобретается

**A — FACT.** Из собственного completed transition можно чистыми API сформировать
candidate/proposal без готовой целевой записи: before context + реально materialized
ACTION + signed actual endpoint delta уже доступны. Но session сама эти API не
вызывает; без начального remembered experience она не получает ACTION вообще.
Наличие raw transition класса не заменяет evidence admission: его можно создать
вне фактического исполнения, а occurrence в типе optional.

Новый опыт — связка контекста, структуры действия, наблюдённого эффекта и поддержки
различными событиями, пригодная для операционного retrieval. Сохранение NFP alone
не содержит связи action/effect, support и разрешённой процедуры CREATE. Effect —
числовое изменение, не sensory frame, не semantic success и не reward. Перекрывающиеся
окна не вычитаются целиком: extractor берёт последние endpoints.

**B — ограничение причинности.** UUID доказывает binding конкретной попытки, а не
факт apply сам по себе: materialization возможна до guard denial. Нужны execution
result, запись фактического synthetic world apply и retained T+1 recent с тем же
UUID/action identity. Последовательность T→T+1 не исключает независимых изменений
мира. Повторы увеличивают observational support, но не доказывают причинность;
скрытая постоянная причина может повторяться. Для synthetic эксперимента владелец
мира фиксирует отсутствие иных state-changing calls и использует отдельный idle
контроль. Это знание harness о мире, не выведенная системой универсальная причинность.

**DESIGN:** сохраняемый опыт трактовать как provisional observed association.
Существующий native v1 record не имеет causal_confirmed/provisional gate;
не добавлять произвольные поля и не заявлять, что retrieval их учитывает.
Для первого изолированного синтетического эксперимента scope ограничивается
явным test owner/admission; publication в production запрещена. Production-путь
потребует отдельно согласовать представление и потребление uncertainty.
При неоднозначном одиночном событии CREATE не разрешать. Конфликтующие эффекты
не усреднять в «подтверждённый» эффект и не превращать в hits/misses кандидата.

**C — прогноз.** Proposal сейчас содержит IDs/support/ticks, а не отдельный
prediction slot; exemplar берётся из candidate. Builder сохраняет **наблюдённый**
effect exemplar. После retrieval этот effect может служить предварительным
ожиданием для нового действия: materializer/result несут predicted_effect,
evaluator сравнивает его с новым actual через extractor. Нельзя переписать старый
actual новым прогнозом или использовать forecast при missing observation.
Предварительный прогноз, существовавший ДО обучающего действия, можно удержать
в bounded envelope рядом с evidence; такого поля в proposal сейчас нет. В первом
эксперименте он не обязателен и не добавляется в persistent v1.

Раздельные величины: prediction agreement (HIT/MISS), usefulness относительно
цели и causal attribution. Первое не означает второе или третье. CREATE принимает
только defaults `hits=0, misses=0, confidence=0.5, repeatability=0.5`, profile
`legacy_crud_defaults_v1`; support_count не конвертируется в confidence/hits.

## 4. Authority, Stage 1/2 и нерешённые findings

Разрешённый новый writer route:
`explicit bounded admission → builder → NFPExpSMCreateWriter.create(request)`.
Policy владеет вызывающая сторона; для CREATE требуется allow_expsm_commit.
`safe_demo`/`draft_only` commit не разрешают. Изолированный root обязателен даже
при наличии policy; mutating profile не должен становиться default session.
Ни ShortMemory retention, ни min_support, ни ЭХО/ДАР не дают права постоянной записи.

Stage 1: использовать существующую transaction boundary внутри writer — lock,
strict load, complete-store persistence, replace/readback. Текущий F01 remediation
сохраняет authoritative receipt envelope при совместимых записях; не пересобирать
store через legacy facade и не пользоваться transaction primitives как policy API.
Stage 2: Feedback commit связывает изменение exact-source с receipt и occurrence
index; CREATE не становится таким commit только из-за общего transaction слоя.
Не трогать receipts, не объявлять создание записи receipt-protected операцией.

| Finding RND-110 | Ограничение первого эксперимента; finding остаётся открытым |
| --- | --- |
| F02 draft review/status policy | Не использовать legacy review metadata writers как native admission; admission первого эксперимента чистый и непостоянный |
| F03 manifest authority | Передать отдельный temporary manifest всем registry constructors; constructor/id могут писать |
| F04 isolation entrypoint | Все writable paths явно направить в isolated root; не запускать original-root CLCRuntime |
| F05 legacy exceptions/defaults | Не вызывать Outcome/legacy mutating defaults; safe_demo не universal read-only guarantee |
| F06 admin CRUD/primitives | Не использовать CRUD, manifest enrichment или direct transaction для обхода CREATE policy |
| F07 durability domains | RAM proposal, draft и ExpSM — разные domains; атомарность world+proposal+store не обещается |
| F08 hash coverage | Сравнить полный inventory и bytes всего Production Memory, включая служебные файлы; опасный original-root verifier не запускать |
| F09 trusted config/modes | Roots, policy, callbacks доверенные; guard mode не является общим mode gate всех memory writers |

## 5. Replay, сбои и bounded state

FACT: grouper dedup — set evidence_id, а не execution UUID. Factory hashes зависят
от transition/frame identity; одинаковые manager-local counters при объединении
sessions опасны. Повторный make_proposal создаёт новый proposal ID даже для той же
группы. Повторный create того же request может выделить следующий record ID.
Следовательно, ни один из этих механизмов не даёт сквозной CREATE exactly-once.

**DESIGN для первого bounded run:** owner хранит immutable envelope
`session/source scope + execution_occurrence_id + transition/frame refs + actual
payload digest + evidence_id`, проверяет exact binding и подтверждённое retention.
Один UUID с другим digest — conflict, одинаковый UUID/digest — duplicate без
повторного support. Не менять immutable NFP или переход ради namespace. Envelope
держать отдельно; один manager/session на run устраняет коллизии локальных counters
внутри существующего grouper. Proposal отдельно связывать с фиксированным набором
поддержки; повторный вызов не считать новым приобретением.

Задать конечные budgets ticks, raw/evidence bytes, occurrences, candidates,
proposal/CREATE attempts и diagnostics. Достигнут лимит — остановить admission,
не выкидывать dedup keys и не продолжать запись вслепую. Один store writer и одна
pending CREATE; eviction ShortMemory ничего не запускает. После STOP этот learning
run не возобновляется автоматически. Это bounded in-process dedup, не durability.

| Момент сбоя | Текущая гарантия / безопасное поведение предлагаемого owner |
| --- | --- |
| Guard denial / stale / occupied slot | Нет eligible observed evidence; не делать proposal из occurrence alone |
| После возможного world apply до actual | Неизвестный физический исход; stop, no blind retry; новое snapshot не гарантирует восстановление потерянного T+1 |
| Actual получен, retention не подтверждён | Не считать полноценным handoff; stop admission, не заменять отсутствующий raw источник prediction |
| Retained transition до proposal | RAM может исчезнуть; допустима потеря обучения, не повтор воздействия ради восстановления |
| Proposal/request до CREATE | RAM-only run теряет intent при restart; без durable identity automatic resume запрещён |
| DENIED_BY_POLICY / INVALID_REQUEST / STORE_INVALID | Не обходить gate; сохранить bounded diagnostic, не менять operational memory |
| WRITE_FAILED | Следовать typed result/retry_safe contract; первый эксперимент останавливает попытки. Это не разрешение повторять action |
| READBACK_FAILED после replace | Сохранить attempted_record_id и исходный request; вызвать read-only `reconcile_expsm_readback_failure` |
| Reconcile CONFIRMED_PERSISTED | Признать сохранение, не повторять CREATE |
| Reconcile CONFIRMED_ABSENT | Отсутствие этого ID в валидном store, не доказательство отсутствия всех дублей; первый run останавливается без automatic retry |
| Reconcile UNRESOLVED_OR_STORE_INVALID | Stop/review; не считать ни success, ни safe absence |
| Persistence успешна, owner потерял acknowledgement | Новый автоматический CREATE запрещён: durable acquisition receipt отсутствует; при утрате request/attempted ID гарантированного recovery нет |

Для повторяемого restart-safe learning впоследствии нужен отдельный reviewed
CREATE idempotency contract (стабильный acquisition key/digest, atomic authoritative
binding), совместимый с Stage 1/2. Sidecar JSON со своим replacement не делает
две записи атомарными. Первый опыт может честно обойтись stop-on-uncertainty без
нового ledger. Feedback ledger не защищает physical execution и потерянный proposal.

## 6. Приоритеты и рекомендуемый implementation step

| Приоритет | Конкретный gap | Минимальное решение для будущей реализации |
| --- | --- | --- |
| P0 для безопасного CREATE | Нет проверенного occurrence → evidence → proposal admission и владельца write authority | Узкий opt-in bounded handoff; проверить execution/retention/source binding, support, conflicts и policy; использовать существующие factory/builder/writer |
| P0 для empty-store эксперимента | Нет первоначального native exploratory intent | Отдельно определить допустимый synthetic-only action intent без source_experience/predicted_effect; reuse guarded apply/tracking boundary без фиктивного remembered selection |
| P0 до автоматического повторения CREATE | Нет acquisition dedup и uncertainty lifecycle | В первом run — single-owner bounded keys, один attempt и stop-on-uncertainty; durable CREATE idempotency отложить, restart не поддерживать |
| P1 для интерпретации | Нет persisted provisional/causal certainty semantics | Первый эксперимент ограничить isolated observational memory; до production решить uncertainty admission/representation/retrieval |
| P1 для долгой session | Grouper sets/candidates/support IDs не bounded | Finite experiment budgets, stop admission по лимиту; lifetime привязать к run |
| P1 для доказательства обучения | Нет matched-control native acquisition experiment | Одинаковые query/config/world initial state, отличие только acquired store; capture полную source chain |
| P2 | Нет общей utility/causal learner, durable recovery | Не требуется для первого observational acquisition experiment |

**Главный рекомендуемый следующий implementation step:** отдельной задачей сделать
чистый bounded `completed native transition → reviewed acquisition handoff` с
explicit create operation на тестовой ExpSM. Название здесь описательное, это
**не существующий API**. Вход — retained recent плюс execution/source envelope;
выход — typed candidate/proposal/request и явный результат единственной CREATE
попытки. Не подключать writer к ShortMemory.remember/prune или default `_pulse`.
Вначале проверить изолированную композицию и запреты, затем opt-in session owner.
Его самостоятельная реализация ещё не закрывает empty-store full-loop эксперимент.

До начала такой реализации согласовать два решения: (1) разрешён ли отдельный
synthetic exploratory intent и через какую общую guarded execution boundary он
проходит; (2) допустимо ли использовать provisional association для выбора в
изолированном сценарии при defaults v1. Это вопросы для review, а не скрытые
изменения существующих контрактов этим аудитом. Если нужен именно empty-store
end-to-end одним implementation increment, scope обязан явно включать оба P0
контракта. Из текущего remembered API нельзя честно получить exploration одним
wiring change.

Альтернативы:

- **Нетargetный подготовленный моторный опыт.** Может дать начальное действие
  существующему coordinator, если его retrieval реально выигрывает. Требует
  показать, что целевой context/action/effect не закодирован в seed. Доказывает
  acquisition поверх motor prior, но не способность начать с пустой ExpSM;
  легко получить только переименование source вместо изменения поведения.
- **Явный внешний experiment driver.** Может вручную вызвать transducer/guard/
  world/manager и собрать реальные transitions; это полезный isolated acquisition
  test, но не native session end-to-end. Не выдавать его за решение bootstrap.
- **Legacy consolidation.** Иные representations/review/authority semantics,
  открытые F02–F09 и риск смешения legacy/native; не минимальный путь.
- **Сначала durable CREATE ledger.** Сильнее recovery, но расширяет schema и
  authority scope до доказательства acquisition; для bounded stop-on-uncertainty
  эксперимента избыточно. Нельзя заменить его существующим Feedback receipt.
- **ЭХО/ДАР как learner.** RND-016 ожидания и RND-019 comparison сохраняют источники,
  но не приобретают моторный опыт и не дают CREATE authority. RND-017/018 bounded
  comparison/admission можно подключить позже; для numeric endpoint experiment
  они не обязательны.

### Принятое направление и предварительная декомпозиция

Архитектурный review принял выводы аудита и направление дальнейшей разработки.
Это не утверждение новых production-контрактов: exploratory intent, acquisition
admission, provisional retrieval semantics и durable CREATE idempotency требуют
отдельного согласования в соответствующих задачах. Provisional observed association
не является causal fact; persistence v1 не обеспечивает полноценную семантику
provisional retrieval. Существующие evidence, grouping, builder, CREATE, retrieval,
selection и guarded execution пригодны для частичного переиспользования в указанных
выше границах.

Рекомендуемая декомпозиция, номера и задачи **предварительные**:

1. RND-021 — Bounded Acquisition Handoff.
2. RND-022 — Synthetic Exploratory Action Intent.
3. RND-023 — First Acquired Experience, end-to-end experiment.

Этим closure ни одна из этих задач не начинается; implementation не разрешён.

## 7. Первый эксперимент: два этапа и контроль

**DESIGN, не выполнен.** Ниже спецификация после принятия недостающих контрактов;
это не заявление о готовом запуске текущей session. Использовать существующий
[SyntheticClosedLoopVisualWorld](../scenarios/support/synthetic_closed_loop_visual_world.py)
с visual shape `(1,2)`, начальной позицией `(0,0)`, one-frame context и motor `(2,)`.
Мир показывает one-hot position. Policy/root/manifest заданы test owner явно.
Начальная isolated ExpSM содержит пустые experience/reflexes: целевой записи и
правильного эффекта нет. Любые envelopes/receipts создаются только разрешённым
форматом существующего store, не ручной подделкой authority.

### Этап A — до обучения

1. Получить настоящее external A=`(1,0)` через owned-world sensor, transducer,
   manager. Убедиться, что native retrieval не даёт selection. Это подтверждает
   исходную неспособность текущего session выбрать action.
2. **Требуемый новый контракт:** test owner выдаёт конечный план исследовательских
   motor intents: right `(0,1)`, left `(1,0)`, right `(0,1)`, left `(1,0)`.
   План определяет только действия, не правильные последствия и не правила
   будущего selector. Каждое действие проходит freshness/pending/ModeActionGuard,
   единственный apply и tracking с новым UUID. Никакого fabricated source experience
   или обязательного predicted effect у exploration нет.
3. Heart/world остаются согласованными: action в T, actual только в T+1; read
   snapshot не двигает world. После последнего действия дать отдельный observation
   pulse без нового exploration. Получить две разные реальные A→right→B transition
   и две B→left→A. Никаких resets, перемаркировок source time или второго apply
   для получения observation внутри learning session. Ограничить run конечным budget.
4. Owner на безопасной границе после observation/retention извлекает evidence,
   сохраняет occurrence envelope и вызывает grouper с thresholds `1.0/1.0/1.0`,
   min_support=2. Правильные deltas не подставляются: их вычисляет extractor из
   фактически полученных endpoints. Exemplar целевой группы содержит actual
   `(-1,+1)`, если мир действительно дал A→B. Число в этом документе — проверяемое
   следствие модели, не вход builder/selector.
5. Приём всех evidence заканчивается до review/CREATE: так conflict case не
   проскочит через раннюю promotion. Owner проверяет все группы на одинаковые
   context/action с несовместимыми effects; на первом эксперименте такой конфликт
   блокирует их promotion независимо от достаточного support одной группы.
   Это новый admission rule, которого сам grouper не реализует.
6. Явно запросить proposal целевой A/right группы. Выбор экспериментального
   candidate производится по retained evidence связи с первым exploratory occurrence,
   не по заранее ожидаемому delta, hidden_position или «правильному» record ID.
   При min_support=2 один ambiguous/single occurrence ничего не публикует.
   Proposal — provisional, не causal fact; обратная группа остаётся transient.

No-action idle arm с тем же начальным миром подтверждает, что без вмешательства
позиция не меняется; аудит world calls исключает иные mutators. Дополнительная
fault-injection arm меняет наблюдение независимо от action и проверяет отказ
causal promotion. Idle/control evidence не переименовывать в action transition.

### Этап B — после обучения

1. Зафиксировать proposal + exemplar + acquisition envelope и единственный
   request. Builder defaults не переопределять; admission не выставляет hits.
   Явно вызвать existing policy-gated CREATE на isolated ExpSM. Проверить typed
   CREATED и fresh readback; при uncertainty — процедура раздела 5, без retry.
2. Создать два новых matched-control native session episodes, каждый со своим
   свежим миром `(1,2)` в A, одинаковыми query values, topology, time schedule,
   mode, configs и budgets. IDs новых наблюдений должны быть свежими; одинаковые
   values не означают повторное sensor событие. Exploration в обеих arms выключен.
   Серверный restart recovery здесь не моделируется: это новые независимые эпизоды.
3. Control C0 получает исходную пустую ExpSM. Control C1 получает результат CREATE
   через тот же writer path. Разница inputs — только наличие acquired record;
   не менять query, weights, thresholds или decision rules после обучения.
4. C0: retrieve empty → select None → ноль apply. C1: fresh retrieve возвращает
   созданный record с source_experience_id из CREATE; activate_native передаёт
   его selector, select_native выбирает его, coordinator materializes новый UUID,
   guard допускает right, мир реально переходит A→B, actual в T+1 удерживается.
   При similarity=1 defaults дают activation
   `.55 + .20*.5 + .15*.5 + .10*.5 = .775`;
   decision_threshold заранее зафиксировать `.35`, retrieval threshold `1.0`.
5. Записать полную цепочку CREATE record ID → retrieved source → activation →
   selection → ACTION frame/occurrence → actuator/world apply → retained actual.
   Удаление acquired record в отдельной контрольной копии возвращает C0 поведение.
   Не требовать изменения immutable query IDs и не подключать legacy fallback.
6. Опционально pure Feedback evaluator проверяет acquired prediction против нового
   actual. APPLY выключен: доказательство acquisition не требует автоматического
   reinforcement или изменения defaults.

Это минимальное изменение поведения «нет выбранного действия → действие из нового
опыта», а не демонстрация оптимальности среди двух действий. Для claims о полезности
или предпочтении лучшего варианта потребуется дополнительный target/value experiment.

### Обязательные контрольные случаи

| Случай | Ожидаемое доказательство |
| --- | --- |
| Без созданного опыта C0 | Одинаковый A не даёт native match/selection/action; никакой скрытый fallback |
| С созданным опытом C1 | Именно acquired record проходит реальную retrieval/selection/guarded execution цепочку |
| Недостаточные evidence | Одна A/right occurrence; make_proposal возвращает None при min_support=2; CREATE не вызывается |
| Конфликтующее observation | Независимый mutator/fault даёт иной effect при том же A/right; grouper разводит группы, новый admission блокирует promotion; не выдаёт conflict за MISS неиспользованного опыта |
| Повторное событие | Тот же retained transition/envelope дважды: один support; повтор proposal/request owner блокирует, UUID с другим actual digest — conflict; одинаковые values с другим UUID считаются отдельным наблюдением |
| Отклонённый CREATE | Валидный request + safe_demo/draft_only → DENIED_BY_POLICY, store bytes неизменны, C1 остаётся C0; никаких CRUD fallback |
| Отсутствующий/поздний actual | Никакого proposal из prediction; pending expires по T+1 contract; нет повторного физического действия |
| CREATE readback failure | Reconciliation определяет confirmed persisted/absent/unresolved; ни один исход не запускает world apply |

## 8. Критерии приобретённого опыта и риски

Эксперимент принимается только при одновременном выполнении:

- Целевого record/context-action-effect triple нет в исходной базе и selection
  shortcut; обучение использует реальные, удержанные external before/after.
- Фактический world apply подтверждён отдельно от materialization/UUID; exact
  occurrence binding выдержан до raw transition и внешнего acquisition envelope.
- Support складывается из различных occurrences, не replay; конфликт и недостаток
  evidence блокируют admission. Новая запись не объявляется causal fact.
- CREATE выполняется существующим writer при явной policy; IDs writer-owned,
  readback проверен, Stage 1/2 и чужие receipts не изменены обходным путём.
- Новый independent episode извлекает именно созданную запись; C0/C1 имеют
  одинаковые значения present и конфигурацию; intervention acquired store меняет
  реальный selection/action. В логе нет второго executor или hidden world hint.
- Defaults не равны выученной вероятности; HIT/MISS не выдаются за utility,
  причинность или количество поддерживающих observations.
- Все состояния и попытки ограничены; restart не обещает resume; unknown physical
  outcome никогда не вызывает blind retry; Production Memory неизменна целиком.

Остаточные риски: persistent v1 хранит structural context/action/effect и краткую
creation metadata, а не полный sensor/execution audit trail; envelope первого
эксперимента RAM-only. Утрата envelope исключает последующее доказательство exact
acquisition provenance. Предиктивная применимость при похожем контексте не
гарантирует одинаковый мир. Source-time, Heart-time и world-time не взаимозаменяемы;
finite synchronous synthetic schedule не доказывает asynchronous recovery.
Trusted root/configuration и administrative authority не решены универсально.

## 9. Намеренно вне scope и проверки аудита

Не реализуются learning hooks, exploratory execution, новый schema/status,
CREATE ledger, production publication, UPDATE/APPLY automation, reward/utility,
causal discovery, delayed/multi-action credit assignment, AKBSM/Chronicle,
универсальная память, real actuators, restart recovery или unbounded continuous
learning. ЭХО/ДАР опциональны. Legacy/native isolation, Stage 1/2, NFP immutability,
T+1, guard и текущие weights/contracts не меняются. Следующая RND не начинается.

В этой задаче создан только этот документ. Production-код, тесты и Memory не
редактировались; constructors/runtime/verifiers не запускались. Использованы
read-only source inspection, локальные Git queries и whole-tree Memory hashing.
Известный Substrate baseline FAIL не исправлялся и не перепроверялся: design-only
scope не требует запуска исполняющих контуров.

Closure после архитектурного review: **RND-020 CLOSED, ACCEPTED FOR CLOSURE**.
Разрешён один локальный коммит `docs(learning): audit native acquisition loop gaps`
только с `docs/RND-020_native_learning_gap_audit.md`. Ветка `main`; remote и tags
не используются. Проверки closure: точный Git scope и staged diff, ссылки,
whitespace и `git diff --check`; полный inventory и SHA-256 всех 12 файлов
Production Memory совпадают с исходными. Production-код, тесты, конфигурации и
веса не меняются; новых служебных файлов нет. Behavioral regression и Substrate
verifier не запускаются; исторический baseline FAIL остаётся открытым.

**STOP: implementation не начат; действий по RND-021 нет.**
