# RND-018 — Minimal DAR Resource & Admission Controller

Дата: 2026-11-06. **CLOSED — архитектурный review принят, ACCEPTED FOR CLOSURE.**
Исходный main/HEAD: `c4d3ca62e930b99be4eb1c27206c6e15dfbd5585`.
LOCAL ONLY. При closure разрешён один локальный коммит пяти файлов.
Tags и remote operations не выполняются. RND-019 не начат.

## Безопасная интеграция

Изучены RND-017, MultiTickComparison, NativeHeartSession B2, Heart,
SyntheticTimeAdapter и bounded delivery. Dispatch находится перед Heart.step
в публичном NativeHeartSession.step(), пока session вне pulse. Вызывается
существующий submit_internal_comparison, его guard внутри pulse сохранён.
Процессор ровно один, создан конструктором session. После Heart.step session
забирает immutable snapshot и освобождает terminal processor slot.
Следующий dispatch возможен только на следующей границе step.

Opt-in run вызывает эти же session.step с pacing policy Heart.run (новый
pacing origin при возобновлении, без catch-up, sleep порциями <= 0.05).
Heart остаётся источником ticks; его код, state machine и pulse contract не
изменены. Default run по-прежнему вызывает Heart.run напрямую. Opt-in loop
не является worker и не выполняет координаты самостоятельно. Вычисление
по-прежнему выполняется после observation/housekeeping/ЭХО перед retrieval.
Ни очередь, ни backpressure не пропускают observation или advancement world.

Bounded delivery доставляет sensory/consequence/control events, а не хранит
resumable requests/results; его очередь и journal для этого недостаточны.
ДАР не дублирует delivery и не изменяет его гарантии или authoritative port.

## API и immutable модель

Включение: `NativeHeartSession(..., internal_work_limits=WorkLimits(...),
admission_limits=AdmissionLimits(...))`. Без явных WorkLimits включение запрещено.

Новые типы в clc.internal.admission: AdmissionLimits, ComparisonRequest,
AdmissionRejected (ValueError). ComparisonAdmission — внутренний session owner.
`validate_comparison` в multitick переиспользует прежние admission checks
RND-017 без изменения поведения; native NFP dataclasses уже валидированы и frozen.

Новые session APIs:

- `submit_comparison_request(left, right) -> ComparisonRequest`;
- `comparison_requests() -> tuple[ComparisonRequest, ...]` в порядке приёма;
- `cancel_comparison_request(request_id) -> ComparisonRequest`;
- `release_comparison_request(request_id) -> None`.

ComparisonRequest frozen: UUID request_id, монотонный order, retained_cells,
state, WorkSnapshot либо None, фиксированный kind structural_comparison.
Immutable input windows удерживаются внутренне до dispatch/cancel. Пользователь
не передаёт ID или произвольный тип команды: duplicate supplied ID не применим.
Нет бессрочного реестра освобождённых ID. Успешный возврат submit означает accepted,
начальное состояние queued. Отказ явно выбрасывает TypeError/ValueError для
неверного входа либо AdmissionRejected для перегрузки; отклонённые входы не
сохраняются, диагностический журнал отказов не создаётся.

Мутации заявок разрешены только вне pulse в READY/RUNNING/PAUSED; submit после
STOP запрещён. При включённом ДАР direct submit/cancel/release старого slot API
отклоняются, snapshot доступен для диагностики. Старый API вне ДАР не меняется.

## Бюджеты и backpressure

AdmissionLimits содержит три положительных целых (bool запрещён):

| Лимит | Default | Смысл |
| --- | ---: | --- |
| max_pending | 4 | Ожидающие входные пары, без активного процесса |
| max_requests | 8 | Все удерживаемые заявки, включая terminal outcomes |
| max_retained_cells | 16384 | Сумма координат обоих окон queued + active |

Дополнительно WorkLimits задаёт max_cells на одно окно (4096 default) и
cells_per_tick (64 default). Учитываются обе ссылки на входы, даже если окна
совпадают: консервативный учёт без dedup. В каждый момент активен максимум один
процесс; queued <= max_pending, а общее число заявок <= max_requests.

Каждая принятая заявка заранее резервирует своё terminal место через
max_requests. Поэтому завершение никогда не зависит от освобождения отдельного
result journal: outcomes не вытесняются, новые submit получают backpressure
до явного release. При terminal outcome удержание activation inputs равно нулю;
request, result и descriptors остаются до release. Ограниченные количеством
заявок snapshots не образуют бесконечный журнал. Полученные caller snapshots
могут жить дольше освобождения — caller сам отвечает за свои ссылки.

Это **не строгий byte-memory bound**: длины metadata-строк RND-017 не ограничены.
Descriptors ограничены числом кадров и заявок, сохраняют ссылки на immutable
строки, не activation values. Byte budget, если понадобится, потребует отдельного
контракта NFP metadata; в этом pass он не вводится.

## FIFO, lifecycle и результат

queued -> running -> completed/failed/cancelled. Dispatched snapshot до первого
advance может ещё иметь queued. Вытеснения нет. Освобождение processor slot
после terminal не удаляет request outcome. FIFO соблюдается среди неотменённых
queued заявок. После вычислительной ошибки следующая заявка запускается тем же
процессором на следующем step, без повторного исполнения завершённых координат.

Отмена queued удаляет входы и сохраняет cancelled outcome без process ID
(процесс ещё не создавался). Отмена active сохраняет WorkSnapshot с process ID,
cursor и provenance и освобождает processor. Отмена terminal идемпотентна.
Release разрешён только terminal; повторный release/неизвестный ID дают KeyError.
Pause сохраняет все входы и cursor. Resume продолжает со следующей координаты.
STOP, tick exhaustion и session failure отменяют queued/active в finally, но
не меняют уже completed/failed outcomes. Управление — только через session APIs,
прямое управление session.heart не поддерживается для lifecycle internal work.

Request.work.process_id связывает request с конкретным вычислением;
WorkSnapshot.result.process_id и result_id связывают итог. InternalSimilarity
не изменяется: origin INTERNAL_STATE, source_descriptors в порядке left/right,
исходные window/frame IDs, origins, ticks и provenance_ref сохраняются после
освобождения окон и slot. Mixed origins допускаются прежними NFP contracts;
это provenance вычисления, а не подтверждение внешнего evidence или знания.

ДАР не имеет world/Memory writer/Feedback APPLY/weights/action authority.
Никаких новых internal commands, обучения, persistent queue, priorities,
Доски, Переговорок, process managers или physical parallelism нет.

## Поведенческий эксперимент и проверки

`tools/verify_minimal_dar_admission.py`: 15 новых behavioral cases через реальные
session API и временные writable fixtures. Основной сценарий принимает три
разные пары по 4 координаты, удерживает 24 координаты, затем обрабатывает каждую
по одной координате/tick. Первый результат на tick 3: score 0.25; второй на tick 7:
0.375; третий на tick 11: 0.5. До своего dispatch последующие заявки имеют work=None.
Три process ID различны, все результаты сравниваются с NFPWindowSimilarity,
provenance доступен, processor автоматически освобождается после каждого итога.
За 12 шагов Heart/world достигают 12, выполнены 12 observation retrieval и idle,
нет actions или ShortMemory transitions. Дополнительный шаг не меняет outcomes.

Негативные cases: queue overflow, aggregate active+queued input budget,
terminal capacity/backpressure, invalid limits/input/future/size,
cancel queued/active/terminal, преждевременный и повторный release, isolated
computation fault и следующий dispatch, session fault, pause/resume, READY STOP,
callback STOP, tick exhaustion, slot ownership и pulse guards, mixed provenance.
UUID генерируются системой; supplied duplicate IDs не поддерживаются API.
Paced run проверен с pause из sleep callback и последующим resume.
Две differential проверки сравнивают native actions, ShortMemory и ЭХО;
одна использует реальное непустое ожидание ЭХО с проверкой источников матчей.

Свежая батарея в `/tmp/rnd018-validation/repo` — копия без .git,
`python -B` / `PYTHONDONTWRITEBYTECODE=1`: **137 уникальных tests PASS**.

| Verifier | PASS cases |
| --- | ---: |
| minimal_dar_admission | 15 |
| multitick_internal_work | 14 |
| native_heart_b2 | 23 |
| native_session_b1 | 5 |
| native_bounded_delivery | 18 |
| nfp_context_short_memory | 24 |
| echo_expectations | 17 |
| nfp_remembered_action_guarded_execution | 8 |
| legacy_native_joint_checkpoint | 13 |

Известный Substrate **FAIL**, не исправлен и не засчитан в PASS. Запущен verifier
как в текущей временной копии, так и в чистом git archive исходного HEAD:
единственный FAIL `runtime does not import clc.patterns`; одинаковые нарушители
native_bounded_delivery.py, native_heart_session.py, native_session.py.
Новых нарушителей нет. Полная батарея verifiers не запускалась.

Production Memory: полный inventory всех 12 файлов и SHA-256 до/после
проверок совпадают с HEAD в основной и временной копии. Production-веса не
изменялись. Логи, baseline archive, временная копия и inventory:
`/tmp/rnd018-validation`. Syntax всех четырёх изменённых/новых Python файлов,
`git diff --check`, совпадение протестированных исходников и scope проверены.

## Открытые вопросы и следующий этап

- Opt-in session.run повторяет небольшую pacing policy Heart.run ради dispatch
  вне pulse. Сейчас проверена совместимость, но дальнейшие изменения pacing
  должны учитывать оба пути. Изменение контракта Heart в этом pass не требуется.
- Нет origin-specific admission policy, byte-limits metadata, durable recovery
  или внешних request IDs. Они требуют отдельных контрактов, не подразумеваются.
- Rejected submissions не удерживаются; caller получает явную ошибку. Terminal
  outcomes удерживаются до release; release является явным подтверждением caller.
- Нет одновременного исполнения нескольких внутренних процессов, когнитивных
  приоритетов и самостоятельного обучения. Новых когнитивных полномочий нет;
  никакая работа следующего этапа не начата.

Scope ровно пять файлов:
clc/internal/admission.py, clc/internal/multitick.py,
clc/runtime/native_heart_session.py, tools/verify_minimal_dar_admission.py,
этот документ. До closure: исходный main/HEAD, два tracked изменения и три
untracked файла, индекс пуст; это состояние подтверждено перед staging.


## Архитектурный review и финальное закрытие

Координатор принял review: **ACCEPTED FOR CLOSURE**, блокирующих дефектов нет.
RND-018 **CLOSED**. Production-исправления после review не требовались;
при closure изменён только этот документ. Все четыре Python-исходника побайтово
совпадают с принятой и протестированной версией. Повторная полная регрессия
не запускалась: подтверждена актуальность прежних **137 behavioral PASS** и
**семи дополнительных review-проверок PASS**, без сложения повторных прогонов.

Дополнительные review-проверки (`/tmp/rnd018-review.py`, лог
`/tmp/rnd018-review.log`) покрывают:

1. Backpressure при max_requests с одновременно terminal и queued заявками:
   принятые заявки продолжают FIFO, предыдущие результаты не теряются.
2. Успешный dispatch без pulse при pause: cursor остаётся нулевым; resume
   продолжает тот же process, STOP корректно отменяет active и queued.
3. Ошибку sensor до первой вычислительной порции: нет ложного completed result,
   все входы освобождаются, outcome сохраняется.
4. Ошибку session после фактического world advancement: уже completed результат
   сохраняется, незавершённые заявки отменяются, повторного advancement нет.
5. Учёт координат и weak references для completed/failed/active cancelled/queued
   cancelled: после terminal session не удерживает activation input windows.
6. Differential pacing default/DAR: sleep pause, STOP, исключение и обычный run;
   после resume нет catch-up, ticks/world/clock/sleep traces совпадают.
7. Reentrant step guard и полную публичную цепочку
   request_id → process_id → result_id → source_descriptors для mixed origins.

Эти семь проверок пока остаются временными review artifacts; рекомендуется
перенести их в постоянный verifier при следующем изменении lifecycle.
Дублирование pacing — технический долг, различий в проверенных сценариях нет.
Для structural comparison существующих NFP validators и сохранения provenance
достаточно; отдельная origin policy сейчас не требуется. Для нескольких active
процессов понадобится расширить ownership/resource contract, без выдачи
полномочий на action, Feedback APPLY или Memory writes.

При closure повторно проверены syntax, точный scope пяти файлов, пустой индекс
перед staging, полный итоговый diff и whitespace. Inventory/SHA-256 всех
12 файлов Production Memory совпадают с исходным HEAD; новых служебных файлов
и изменений production-весов нет. Direct submit при активном ДАР по-прежнему
запрещён вне session dispatch, guard submission внутри pulse сохранён.

Substrate baseline **FAIL остаётся открытым**: те же три нарушителя, без новых.
Никаких изменений verifier или маскировки FAIL не выполнялось.

Разрешён один локальный коммит ровно указанного scope:
`feat(dar): add bounded native work admission`.
После commit — STOP, без RND-019 и архитектурных расширений.
