# RND-011 — Согласование проверочных контрактов ShortMemory

Статус: **CLOSED**. Review принят; три несовпадения признаны устаревшими
проверочными контрактами относительно утверждённой Stage 2. Исправлены только
проверочные контракты, production-реализация не изменена. Работа локальная;
закрытие оформляется одним коммитом `test: reconcile ShortMemory contracts with Stage 2`.
RND-012 не начат.
Исходная ветка `main`, HEAD `112dd807dae0545a0632382103f724d4404f8a48`,
рабочее дерево чистое. Локальный `AGENTS.md` не отслеживается и игнорируется.

## Основания и воспроизведение

Исходные расхождения описаны в [RND-000](RND-000_architecture_inventory.md).
Актуальные контракты: [Context/ShortMemory design](design_nfp_context_and_short_memory.md),
[Stage-2 replay/idempotency](design_nfp_native_feedback_replay_idempotency.md),
[causal transition](../clc/context/causal_transition.py),
[canonical manager](../clc/context/context_memory_manager.py).

До запусков изучены entry points и пути записи. Репозиторий скопирован в
`/tmp/rnd011-jt8rdx8d/repo` без `.git` и bytecode; все исполняющие runtime/Memory
проверки запускались там через реальные `python -B tools/<verifier>.py`.
Внутренние fixtures используют `TemporaryDirectory`; `demo_run` дополнительно
копирует Memory и выбирает SAFE_DEMO. До работы сохранён полный список файлов
исходной Memory с SHA-256 и хеш `AGENTS.md`.

До исправления: **24 теста, 3 failures, 0 errors**, вся Memory копии неизменна.
Все три исходных метода присутствуют в запуске; их имена и scenario coverage
сохранены после исправления. Production-дефект или необходимость нового
архитектурного решения в исследованных трёх случаях не подтверждены.

## Mismatch → причина → исправление → доказательство → результат

### A. Import isolation

- Mismatch: `test_canonical_manager_and_no_runtime_invocation_or_eager_import`
  требовал отсутствия `clc.patterns` даже после полного запуска `main.py`.
- Причина: устаревшее требование ко всей demo execution, смешивавшее импорт
  типов с активацией native подсистем. Свежий subprocess после одного лишь
  `import clc.runtime.clc_runtime` не содержит ни одного из пяти запрещённых
  native модулей. Загрузка происходит позже, во время legacy demo.
- Доказательство: трассировка импортов установила цепочку
  `main.py → demo_run → legacy ExpSMOutcomeFeedback._load_data
  → ExpSMStoreTransaction.load_for_mutation_strict → load_state_strict
  → normalize_store → validate_store → _validate_record_sections → experience.expsm_representation
  → experience.effects → context.causal_transition → patterns`.
  Общая валидация формата загружает определения native values; это не создание
  ShortMemory, не native execution и не автоматический native Feedback APPLY.
  См. [transaction](../clc/consolidation/expsm_store_transaction.py),
  [legacy Feedback](../clc/expsm/expsm_outcome_feedback.py),
  [representation](../clc/experience/expsm_representation.py),
  [effects](../clc/experience/effects.py).
- Исправление: строгий запрет пяти модулей и их submodules перенесён на фазу
  чистого импорта runtime. Во время demo сохранены ловушки трёх native методов
  manager; добавлен profile guard создания native pattern/transition объектов
  и вызовов `activate_native`/`select_native`. После demo запрещены импорты
  transduction, actuation, ShortMemory, native retrieval, evaluation и APPLY.
  Разрешена только необходимая загрузка pattern/causal типов из старого списка.
- Результат: исходный тест PASS. Три отрицательных контроля отвергли намеренный
  eager pattern import, создание `PatternTopology` и импорт native APPLY.

### B. UUID validation и eviction

- Mismatch: `test_no_permanent_writes_or_consolidation_on_eviction` отвергал `uuid`.
- Причина: устаревший AST allowlist до Stage 2. Локальный `from uuid import UUID`
  в `_validate_occurrence_id` проверяет каноническую UUIDv4 identity, не генерирует
  её заново и не выполняет запись или консолидацию.
- Исправление: исключение разрешает только абсолютный `from uuid import UUID`
  без alias и только в `causal_transition.py`. Общий список не расширен; обычные
  `import`, произвольные импорты и прежние запрещённые вызовы остаются запрещены.
  Сравнение полного inventory Memory до/после eviction/prune сохранено.
- Доказательство: [Stage-2 identity contract](design_nfp_native_feedback_replay_idempotency.md)
  требует UUIDv4, созданный один раз при materialization и переносимый без замены.
- Результат: исходный тест PASS, Stage-1 audit и replay/idempotency PASS.

### C. Public causal schema

- Mismatch: `test_public_fields_have_no_semantic_or_hidden_world_data` не ожидал
  `execution_occurrence_id` в pending/recent records.
- Причина: устаревшая схема assertions до Stage 2. Поле — техническая identity
  execution attempt, а не semantic label, hidden world data или доказательство
  физического исполнения/причинности. `None` сохраняет небиндинговые direct calls.
- Исправление: добавлено только одно поле в точный набор публичных полей.
  В том же тесте проверены `None`, допустимый UUIDv4, перенос UUID через manager
  pending → recent, сохранение объектов context/action по identity и отказ для
  semantic string, пустой строки, числа, uppercase UUID и UUID другой версии.
- Доказательство: Stage-2 design прямо требует переноса той же identity через
  intent/result/pending/recent/evaluation/evidence/receipt. UUID не заменяет NFP
  и не доказывает, что world был изменён.
- Результат: исходный тест PASS; guarded execution, Feedback evaluation/APPLY и
  durable replay PASS.

## Сохранённые гарантии

Точный публичный набор полей и ShortMemory state остаётся закрытым; проверки
hidden-world sentinel, debug-name independence, NFP identity/provenance,
EXTERNAL_SENSORY/ACTION_GENERATED, replay rejection, времени и topology сохранены.
Равные значения before/after на границе мира остаются допустимыми: временная
последовательность не является доказательством исключительной причинности.
Один pending и observation T+1 проверяются как ограничения текущего native
прототипа, а не окончательная архитектура RNDeM.
Eviction/prune не пишет permanent Memory и не запускает consolidation/APPLY;
AST boundary и полные hashes остаются проверяемыми. Stage-1/Stage-2 writers,
persistence, receipt semantics, production/runtime, NFP schema и ADR не изменены.

## Targeted regression

| Реальный entry point в `tools/` | Результат |
|---|---|
| `verify_nfp_context_short_memory.py` | PASS, 24 tests, включая все три исходных |
| `verify_minimal_activation_pattern_substrate.py` | PASS, 26 checks |
| `verify_nfp_remembered_action_guarded_execution.py` | PASS, 8 tests |
| `verify_nfp_native_feedback_replay_idempotency.py` | PASS, 15 tests |
| `verify_expsm_persistence_stage1.py` | PASS, 9 tests; 7 writers, 0 audit violations |
| `verify_nfp_native_feedback_evaluation.py` | PASS, 15 tests |
| `verify_nfp_native_feedback_apply.py` | PASS, 11 tests |
| `verify_nfp_context_and_short_memory_design.py` | PASS, 10 sections, 5 references |
| `verify_nfp_native_feedback_replay_idempotency_design.py` | PASS; запуск в исходном Git checkout |

Итого 82 unittest cases, дополнительно substrate/design scripts и отрицательные
контроли. Изменённый Stage-2 full-diff verifier сначала отверг новый путь
ShortMemory verifier. В allowlist добавлены только два точных пути RND-011:
этот документ и `tools/verify_nfp_context_short_memory.py`; собственный путь
verifier уже разрешён. Проверка неизвестных изменений сохранена и отрицательным контролем подтверждён
отказ для `unexpected_rnd011_probe.txt` (без создания файла).

## Финальный контроль и границы

Полный diff и Markdown-ссылки проверены; изменения ограничены двумя verifiers
и этим документом. Полный inventory и SHA-256 исходной Memory совпадают с
начальными: новых, удалённых или изменённых файлов нет. `AGENTS.md` неизменён,
по-прежнему ignored/untracked. Ветка `main` сохранена. До закрывающего
коммита HEAD совпадал с исходным. Разрешён один локальный коммит только трёх
согласованных файлов; fetch/pull/push, обращений к origin, merge и тегов нет.

Полная регрессия проекта не запускалась. Проверки ограничены указанными
entry points и текущими fixtures; это не доказательство отсутствия любых
побочных эффектов во всех возможных будущих импортируемых модулях. Восстановление
pending после restart, multiple pending, delayed observations и автоматическое
CLC-native wiring не проектировались и не проверялись. Отсутствие continuous
native wiring относится к текущему прототипу. RND-011 CLOSED по принятому review.
После последнего успешного прогона изменена только документация, поэтому
полная targeted regression повторно не запускалась; исторические результаты сохранены.
