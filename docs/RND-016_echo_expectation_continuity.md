# RND-016 — ЭХО: минимальный контур ожиданий и наблюдаемых последствий

Дата: 2026-11-06. Статус: **CLOSED — review принят, целевые проверки и финальная регрессия пройдены**.
Архитектурный и поведенческий review принят: ACCEPTED FOR CLOSURE.
Исходная контрольная точка: `main`, HEAD
`287dba03759111ed0a7958e33a90e9891abfc913`, RND-015 CLOSED.
Перед закрытием подтверждены только согласованные незакоммиченные изменения
RND-016; индекс исходно пуст. Локальный `AGENTS.md` прочитан.
LOCAL ONLY: без fetch/pull/push, remote contact и tags. Разрешён один commit
`feat(echo): add bounded native expectation continuity`. RND-017 не начат.

## Назначение и фактические API

[EchoExpectations](../clc/echo/expectations.py) — ограниченный реестр в оперативной
памяти для явно заданных ожиданий о последующих визуальных NFP. Используется
native `clc.patterns.NFPWindow`, а не legacy `clc.core.nfp.NFPFrame` или текстовые
семантические labels. Признаки заданы координатами topology; противоположные
координаты указывает вызывающая сторона. Сходство само по себе не опровержение.

- `expect(source, expected_coordinates=..., ttl=..., opposing_coordinates=...)`
  создаёт frozen `Expectation` из внешнего sensory window.
- `expect_transition(memory, transition_id, **spec)` читает только удерживаемый
  `RecentCausalTransition` через `ShortMemory.snapshot()` и использует его
  `after_sensory_window`. Сохраняется `history_transition_id`; запись не изменяется.
  Остаётся проверка свежести source относительно уже обработанного времени ЭХО:
  это не произвольный запрос старой истории.
- `advance(tick, observation)` возвращает tuple frozen `EchoMatch`; `None`
  означает отсутствие нового наблюдения. Ticks строго возрастают, окно должно
  заканчиваться текущим tick; все кадры должны быть EXTERNAL_SENSORY и VISUAL.
- `snapshot()` возвращает immutable tuple текущих ожиданий.

Интеграция явная: `NativeHeartSession(..., echo=registry)`.
По умолчанию `echo=None`, сопоставление не вызывается. В `_pulse` ЭХО получает
именно свежий NFP либо `None`, после обработки ContextMemoryManager и prune
ShortMemory, перед retrieval/selection/execution. Результаты доступны в
`NativeHeartTick.echo_matches`; они не управляют действиями и не запускают обучение.
Legacy CLC и его predictor/outcome не изменены и с native искусственно не объединены.

## Состояния, неопределённость и provenance

Ожидание хранит исходный immutable NFPWindow с frame identity/origin/provenance,
локальный идентификатор, координаты признаков, deadline и последний результат.
`EchoMatch` связывает expectation ID, source window ID, observation window ID,
tick и optional history transition ID. Объектная идентичность не утверждается:
`identity_confirmed` всегда False. `possible_continuation` — только гипотеза
при поддержке признаков и достаточном `NFPFrameSimilarity` исходного и последнего
кадров. Никаких утверждений об исключительной причинности нет.

Состояния: `open`, `supported`, `contradicted`. Состояние `supported` фиксирует
наличие поддержки в прошлом; текущий исход читается из `last_match`.
После `contradicted` дальнейшие сравнения не выполняются до удаления по сроку.
Исходы сопоставления различаются:

- `support`: все ожидаемые координаты достигли порога;
- `contradiction`: явно заданная противоположная координата достигла порога;
- `no_data`: кадра нет;
- `observed_absence`: все ожидаемые координаты наблюдаемого кадра равны нулю;
- `inconclusive`: частичное или подпороговое соответствие;
- `incomparable`: несовместимая topology;
- `expired`: срок завершён, без физического опровержения.

Противоположные признаки имеют приоритет над поддержкой. Наблюдаемое отсутствие
не закрывает ожидание автоматически. Источник не оценивается сам против себя.

## Retention и время

По умолчанию максимум 32 записи; при заполнении создание отклоняется.
Каждое ожидание имеет положительный TTL и inclusive deadline
`source.end_tick + ttl`. Поддержка и пропуски не продлевают срок.
При первом `advance` после deadline возвращается `expired`, запись удаляется.
Очистка зависит от продвижения активного времени, а не wall clock.
В реестре нет растущего журнала: только source и один last_match на запись.
История tick records сессии ограничена её существующим `Heart.max_ticks`.

Heart передаёт своё время в ЭХО. Pause не вызывает pulse, не старит ожидание
и не двигает world. Resume продолжает тот же активный порядок без catch-up.
Ticks задают порядок и TTL, но не создают новую сущность события на каждом шаге:
`A → нет данных → нет данных → B` сохраняет тот же expectation ID.

Это независимо от существующего T+1 causal slot ContextMemoryManager.
Пропущенное последствие действия может привести к истечению pending transition;
поздний B поддерживает ожидание ЭХО, но не восстанавливает этот переход,
не создаёт RecentCausalTransition задним числом и не закрывает unresolved occurrence.

## Подтверждённые сценарии и границы

[Targeted verifier](../tools/verify_echo_expectations.py) содержит 17 детерминированных
тестов: поддержка, противоречие, частичное соответствие, несовместимая topology,
пропуски, возвращение B, пустая область против отсутствия кадра, несколько похожих
исходных гипотез и два похожих последующих наблюдения без identity confirmation,
inclusive deadline, capacity, freshness/origin, debug-name independence,
чтение удерживаемого ShortMemory и отказ после eviction, native opt-in integration,
дифференциальное сравнение исполнений с/без ЭХО. Три закреплённых closure-сценария:
late support / causal isolation, pause/resume и ambiguous identity.

Ограничения намеренные: только visual NFP, сравнение последнего кадра окна,
явно заданные координаты и пороги; нет автоматического создания ожиданий,
обучения, object tracking, identity proof, постоянного восстановления реестра
или универсальной исторической БД. Синтетические fixtures проверяют контракт,
а не доказывают полноценное когнитивное поведение.

## Проверки закрытия

Финальные запуски: **108 unittest cases PASS**, без зачёта исторических запусков:

| Entry point в `tools/` | Результат |
|---|---|
| `verify_echo_expectations.py` | PASS, 17 tests, включая три closure-сценария |
| `verify_native_heart_b2.py` | PASS, 23 tests |
| `verify_native_session_b1.py` | PASS, 5 tests |
| `verify_nfp_context_short_memory.py` | PASS, 24 tests |
| `verify_nfp_remembered_action_guarded_execution.py` | PASS, 8 tests |
| `verify_native_bounded_delivery.py` | PASS, 18 tests |
| `verify_legacy_native_joint_checkpoint.py` | PASS, 13 tests |

`git diff --check`, точный scope пяти файлов, Python syntax и относительные ссылки
документа проверены. Вся Production Memory: ровно 12 файлов, полный inventory и
SHA-256 совпадают с исходным HEAD и начальными значениями closure; дополнительных
служебных файлов нет. Production-веса не изменены. Production-файлы после review
сохранены без изменений. Полная батарея verifiers не запускалась.
Логи регрессии сохранены вне репозитория в `/tmp/rnd016-closure-ywhhylga`.
Известный baseline FAIL ниже учитывается отдельно и не входит в число PASS.
После успешных проверок изменён только этот документ; повтор runtime-тестов
для изменения статуса не требовался.
Исполняющие regression verifiers запускаются через `python -B` в временной копии
репозитория без `.git`; writable fixtures используют временные каталоги.

## Известный baseline FAIL Substrate verifier

`tools/verify_minimal_activation_pattern_substrate.py`, функция
`_runtime_does_not_import_patterns()`, проверка `runtime does not import clc.patterns`:
сканируется весь runtime на вхождения `clc.patterns`.
Точные нарушители: `clc/runtime/native_bounded_delivery.py`,
`clc/runtime/native_heart_session.py`, `clc/runtime/native_session.py`.

Во время принятого review ошибка воспроизведена и на рабочей версии, и на чистом
`git archive` исходного HEAD `287dba03759111ed0a7958e33a90e9891abfc913`.
Оба запуска завершились exit 1 с одинаковым единственным FAIL.
RND-016 не добавляет нарушителей этого условия; несовпадение проверочного
контракта с существующей native интеграцией предшествует RND-016.
Это **FAIL, не PASS**. Verifier и allowlist не изменены. Его актуализация требует
отдельного согласования; production не менялся ради обхода проверки.

## Scope и безопасность

Согласованный scope: `clc/echo/__init__.py`, `clc/echo/expectations.py`,
`clc/runtime/native_heart_session.py`, `tools/verify_echo_expectations.py` и этот документ.
При closure production-код после принятого review не изменяется.
ЭХО не имеет файлового I/O, authority на запись Production Memory, weights,
consolidation или feedback APPLY. Все 12 исходных файлов Production Memory
сверяются по полному inventory и SHA-256 с исходным HEAD и до/после проверок.
Новые служебные файлы и изменения production-весов не допускаются.
