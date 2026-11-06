# RND-017 — Minimal Multi-Tick Internal Work

Дата: 2026-11-06. Статус: **CLOSED — correction review принят, ACCEPTED FOR CLOSURE**.
Исходный HEAD: `9a601f94bbda01fdb23460bc74f82a1b13947e40`, main.
LOCAL ONLY; remote-операций нет.

## Выбор интеграции

Изучены NativeHeartSession B2, Heart, SyntheticTimeAdapter, B1,
BoundedNativeHeartSession, legacy InternalActionExecutor, NFP similarity и
reactivation. Legacy executor обрабатывает выбранные symbolic decisions и
создаёт ContextOperation; native resumable computation там отсутствует.
NFPWindowSimilarity синхронно сравнивает все координаты. Reactivation только
создаёт внутреннюю копию кадра. Эти API не дают продолжения вычисления.

Добавлен узкий native `MultiTickComparison`, вызываемый opt-in из B2 после
housekeeping/ЭХО и до retrieval. Heart, world adapter, bounded delivery,
legacy executor и существующие NFP contracts не изменены. Новый процесс не
получает world, coordinator, Memory writers, Feedback или callback пользователя.

## API и жизненный цикл

`NativeHeartSession(..., internal_work_limits=WorkLimits(...))` создаёт один
принадлежащий сессии процессор. По умолчанию механизм выключен.

- `submit_internal_comparison(left, right)` — явное разрешение только сравнения;
  допустимо на границе READY/RUNNING/PAUSED, запрещено внутри pulse и после STOP.
- `internal_work_snapshot()` — frozen состояние или None.
- `cancel_internal_work()` — идемпотентная отмена, освобождение входных окон.
- `release_internal_work()` — освобождение terminal slot; активный slot отклоняется.

Состояния: queued → running → completed либо failed/cancelled. Завершение за
один tick допустимо для маленького входа. Одновременно удерживается ровно один
процесс, включая terminal snapshot; автоматической очереди и журнала нет.
Новый процесс требует явного release предыдущего. Состояние хранится только
в RAM, crash recovery и durable persistence отсутствуют.

## Реальная работа и происхождение результата

Два совместимых native NFPWindow: одинаковые modality/topology/frame count.
На каждом tick обрабатывается ограниченное число координат выровненных кадров:
накапливается сумма абсолютных различий. Сохраняются cursor и distance; следующие
шаги используют именно это расстояние. После последней координаты вычисляется
`1 - distance / total_cells` с ограничением [0, 1]. Это структурное сходство,
соответствующее существующему NFPWindowSimilarity по смыслу; из-за порядка
сложения floating point побитовая эквивалентность не обещается.

Результат `InternalSimilarity` имеет UUID result/process, оба source window ID,
completed Heart tick и origin INTERNAL_STATE. После correction результат и snapshot
также сохраняют `source_descriptors` в порядке `(left, right)`. Входные immutable NFP сохраняют
исходные identity/provenance/ticks; до завершения result=None. Результат — typed
measurement, не внешний sensory NFP, не identity proof, факт или готовая категория.
Он не подаётся в present, retrieval, ЭХО или selection. Входы могут иметь любой
native origin; это не даёт им статус внешнего evidence. Future input отклоняется.

## Heart и ресурсы

Heart единолично задаёт порядок вызовов. Работа не двигает world и не меняет
NFP timestamps. Tick advance процессора строго монотонный: повторный или обратный
вызов отклоняется до вычисления. Нет автономного worker, retry или catch-up.
Pause сохраняет cursor/distance; resume продолжает следующий tick. Pause/stop
из callback закрывают admission. После stop, tick-budget exhaustion либо ошибки
session активная работа отменяется в finally публичных step/run; terminal result
сохраняется, входные окна уже освобождены. Управлять жизненным циклом следует
через session API, прямой вызов session.heart не является API управления работой.

`WorkLimits(cells_per_tick=64, max_cells=4096)` задаёт положительные целые лимиты
(bool запрещён). Удерживаются два окна не более max_cells координат каждое.
Admission проверяет совместимость и лимит до удержания входов. При C координатах
нужно ceil(C/cells_per_tick) активных pulses; Heart.max_ticks ограничивает общее
число pulses. Ошибка вычисления переводит процесс в failed, сохраняет тип ошибки
без traceback/входов и не останавливает Heart. Ошибки самой session сохраняют
существующую terminal semantics B2. Это bounded cooperative work, без hard realtime.

## Проверки и review

`tools/verify_multitick_internal_work.py` — 14 целевых behavioral tests через
реальный NativeHeartSession с временными writable fixtures. Проверяются:
многотактовое расстояние и результат, сравнение с NFPWindowSimilarity, независимые
Heart/world, pause/resume без дублей, stop/callback stop/budget cancellation,
capacity/release, неверные limits/input/future/replay, controlled failure,
opt-in и запрет submission внутри pulse, session failure cleanup, multi-frame
inputs, дифференциальное сохранение native actions/ShortMemory/ЭХО.
Fault injection использует приватное состояние только для воспроизводимой ошибки.

Архитектурный review первого pass обнаружил потерю source provenance после
освобождения входов (P2, CORRECTION REQUIRED). Correction описан ниже;
повторный review принят координатором: ACCEPTED FOR CLOSURE. Остаются вопросы будущего ДАР: когда он получит право явно
submit/release и нужен ли отдельный контракт допуска конкретных origin/modality. Этот pass не даёт ДАР полномочий,
не запускает задачи автоматически, не реализует scheduler, обучение, Доску,
новую память или physical parallelism. RND-018 не начат.

## Результат первого pass

Исходная behavioral батарея первого pass в временной копии без `.git`, `python -B` и
`PYTHONDONTWRITEBYTECODE=1`: **119 tests PASS**:

| Verifier | Tests |
| --- | ---: |
| multitick_internal_work | 11 |
| echo_expectations | 17 |
| native_heart_b2 | 23 |
| native_session_b1 | 5 |
| nfp_context_short_memory | 24 |
| nfp_remembered_action_guarded_execution | 8 |
| native_bounded_delivery | 18 |
| legacy_native_joint_checkpoint | 13 |

Substrate verifier: **FAIL**, известная baseline проверка
`runtime does not import clc.patterns`. Чистый archive исходного HEAD также FAIL;
набор нарушителей в обоих случаях ровно native_bounded_delivery.py,
native_heart_session.py, native_session.py. Новых нарушителей нет. Проверка не
изменялась и не засчитывается как PASS. Полная батарея/design allowlists не запускались.

Production Memory: полный inventory ровно 12 файлов и SHA-256 совпадают с HEAD,
до/после regression и в временной копии. Production-веса не менялись; вне пяти
файлов scope изменений нет. Логи: `/tmp/rnd017-78pcwgvw`.
`git diff --check` и syntax новых/изменённых Python проверены.
Scope: `clc/internal/__init__.py`, `clc/internal/multitick.py`,
`clc/runtime/native_heart_session.py`, `tools/verify_multitick_internal_work.py`,
этот документ. HEAD не изменён, рабочее дерево содержит эти пять файлов.


## Provenance correction — review принят

Фактические NFP поля проверены: NFPWindow содержит `window_id: str`,
`provenance_ref: str | None`, `frames: tuple[NFPFrame, ...]`; NFPFrame содержит
`frame_id: str`, `origin: PatternOrigin`, `active_tick: int`,
`provenance_ref: str | None`. Никакой отсутствующей metadata не добавлено.

Добавлены frozen dataclasses:

- `FrameSourceDescriptor(frame_id, origin, active_tick, provenance_ref)`;
- `WindowSourceDescriptor(window_id, provenance_ref, frames)`, где frames — tuple
  из FrameSourceDescriptor в исходном порядке.

`WindowSourceDescriptor.capture()` вызывается для обоих окон при admission,
после проверки совместимости/freshness/лимита, до удержания входов. Snapshot имеет
`source_descriptors=(left_descriptor, right_descriptor)`. При завершении тот же
immutable tuple передаётся в InternalSimilarity. `_inputs=None` освобождает
activation windows, но descriptors остаются доступны через публичный terminal
snapshot и результат. Cancel/failure сохраняют descriptors в snapshot; release
освобождает slot. Полученные ранее snapshots могут удерживаться вызывающей стороной,
как и раньше. У дескрипторов нет activation values и ссылок на NFP objects.
Вложенная захваченная структура состоит только из frozen dataclasses, tuples,
строк, enum, int и None; mutable контейнеров нет.

Прежние поля InternalSimilarity и их positional order сохранены. Новое поле
`source_descriptors` добавлено последним с default None ради совместимости прежнего
конструктора. Производственный submit всегда захватывает оба descriptors, а его
completed result всегда их содержит. Это provenance вычисления, а не проверка
правдивости заявленного origin; measurement по-прежнему INTERNAL_STATE, не sensory
evidence и не identity/causality proof.

Ограниченность: ровно два WindowSourceDescriptor; число FrameSourceDescriptor
равно `2 * window.length <= 2 * max_cells`, поскольку topology.size >= 1.
Дескрипторы захватываются один раз и разделяются snapshot/result без повторного
копирования на ticks. Их построение ограничено max_cells, происходит при admission,
а не внутри вычислительной порции. Ограничения числа координат и дескрипторов
**не являются строгим ограничением объёма памяти в байтах**: длина metadata-строк
отдельно не ограничена. Используются уже существующие NFP строки, без дублирования
значений. Число координат activation inputs по-прежнему ограничено max_cells,
slot по-прежнему один, второй конкурентной работы нет.

Три дополнительных behavioral tests через NativeHeartSession:

- Mixed provenance: два многокадровых источника EXTERNAL_SENSORY и
  INTERNAL_REACTIVATION с разными window/frame IDs и provenance. Проверены порядок,
  исходные ticks, deep immutability, доступность через snapshot/result после
  освобождения входов и сохранность полученного descriptor после release slot.
  Нет sensory observations, retrieval, actions, ShortMemory transitions.
- Fractional multiframe: 6 координат при cells_per_tick=4; cursor 4 → 6,
  накопленное distance, отсутствие раннего результата, итог с допуском 1e-12
  к NFPWindowSimilarity и отсутствие повторной обработки после terminal state.
- Nonempty ECHO differential: активное ожидание одновременно с незавершённой
  работой; в вариантах с/без comparison совпадают Heart/world, idle/actuator
  traces, action values/status, ShortMemory до/после sensory values и ECHO outcomes.

NativeHeartSession, Heart, NFP schema, guards, bounded delivery и production
writers в correction не изменялись. Новых прав или persistent writes нет.

Correction validation: **122 behavioral tests PASS** (14 multitick + 17 ЭХО +
23 Heart B2 + 5 native B1 + 24 Context/ShortMemory + 8 guarded native action +
18 bounded delivery + 13 legacy/native checkpoint). Все entry points запущены
в временной копии без `.git` с `python -B`/PYTHONDONTWRITEBYTECODE=1.
После усиления assertions ECHO отдельный финальный targeted run 14/14 PASS;
сравниваются все поля EchoMatch, кроме независимых session window IDs, связь
которых отдельно проверяется внутри каждого прогона. Повторный targeted run
не прибавляется к количеству уникальных cases. Production код остальных
regression runs тот же. Логи: `/tmp/rnd017-correction-5j4vwb5b`.

Substrate verifier по-прежнему **FAIL**, тот же набор трёх baseline нарушителей,
без новых путей; verifier не изменён. Полный inventory/SHA-256 12 файлов
Production Memory совпадает с исходным HEAD и до/после тестов в основной и
временной копиях. Production-веса не изменены. Syntax, whitespace,
`git diff --check` и точный scope пяти файлов проверены. В correction изменены
только multitick.py, targeted verifier и этот документ; session и __init__.py
побайтово совпадают с первым pass. На момент завершения correction commit не
создавался, задача оставалась открытой для повторного review.


## Финальное закрытие

Координатор принял correction review: **ACCEPTED FOR CLOSURE**. RND-017 **CLOSED**.
Перед закрытием подтверждены исходный HEAD/main, пустой индекс и ровно пять
согласованных файлов. Production-код и тесты побайтово совпадают с проверенной
correction-версией; при closure изменён только этот документ. Новых production API
или изменений ранее принятого API нет. Result сохраняет INTERNAL_STATE и source
provenance после освобождения входов, не поступает в sensory evidence/action paths.

Финальные свежие проверки — **109 tests PASS**:

| Verifier | Tests |
| --- | ---: |
| multitick_internal_work | 14 |
| native_heart_b2 | 23 |
| native_session_b1 | 5 |
| native_bounded_delivery | 18 |
| nfp_context_short_memory | 24 |
| echo_expectations | 17 |
| nfp_remembered_action_guarded_execution | 8 |

Предыдущие **13 PASS** legacy/native joint checkpoint использованы повторно:
production/test sources не изменились. Итого подтверждены **122 уникальных cases
PASS**, без сложения повторных запусков. Свежие логи и inventory:
`/tmp/rnd017-closure-a5uvk6c0`. Полная батарея verifiers не запускалась.

Историческая проблема Substrate остаётся **FAIL, не исправлена и не закрыта**.
Использован подтверждённый correction/baseline результат; свежая проверка runtime
подтвердила ровно те же три нарушителя, без новых путей. Verifier не изменён.

Все 12 файлов Production Memory совпадают с исходным HEAD по полному inventory
и SHA-256, до/после тестов как в основной, так и в временной копии. Production-веса
не изменены; вне scope нет изменённых tracked files или дополнительных untracked
файлов. Проверены syntax, полный пятифайловый diff и `git diff --check`.

Ограничения сохранены: WorkLimits по умолчанию 64 координаты/tick и 4096 координат
на окно, один удерживаемый slot, только RAM. Нет scheduler, очереди,
автоматического запуска, второй конкурентной работы или самостоятельного обучения.
Нет полномочий на физическое действие, Feedback APPLY, изменение весов или
постоянной памяти. Будущие права минимального ДАР требуют отдельного решения.

Разрешён один локальный commit ровно пяти файлов:
`feat(internal): add bounded multitick NFP computation`.
Без remote-операций и tags. После commit — STOP; RND-018 не начинается.
