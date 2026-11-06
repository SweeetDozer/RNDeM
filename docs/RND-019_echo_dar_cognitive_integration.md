# RND-019 — ECHO–DAR Cognitive Integration B1

Дата: 2026-11-06. Статус: **CLOSED**.
Повторный архитектурный review correction принят координатором:
**ACCEPTED FOR CLOSURE**. Оба P2-дефекта ownership исправлены;
дополнительные production-изменения при closure не требуются.
Исходный main/HEAD: `984b9ff3f5b55e0946f3651abf591d0379fca1d2`.
Рабочее дерево перед первым pass было чистым; перед closure — ровно три новых
файла RND-019, индекс пуст. Локальный AGENTS.md прочитан. LOCAL ONLY:
fetch/pull/push, remote и tags не использовались. Закрытие оформляется одним
локальным коммитом `feat(echo): integrate candidate evaluation with native DAR`.
RND-020 не начат.

## Проверка контрактов и выбранная связь

Изучены production EchoExpectations (RND-016), MultiTickComparison и
InternalSimilarity (RND-017), ComparisonAdmission и public session API (RND-018),
NativeHeartSession, native NFPWindow, ContextMemoryManager, ContextMemory и
ShortMemory. Интеграция допустима без изменения их семантики:

- `EchoExpectations.expect(source, expected_coordinates=..., ttl=...)` и
  `expect_transition(memory, transition_id, **spec)` уже создают явное ожидание.
- `echo.snapshot()` возвращает существующий frozen Expectation с source.
- `session.step()` / `run()` сохраняют реальные `NativeHeartTick.observation`
  и `echo_matches`. Исторические матчи нужны потому, что last_match в реестре
  перезаписывается следующим наблюдением/пропуском.
- `submit_comparison_request`, `comparison_requests`,
  `cancel_comparison_request`, `release_comparison_request` дают ограниченные
  FIFO заявки, один вычислитель и immutable результаты с provenance.
- ContextMemory содержит legacy frames/events, но не является реестром native
  evidence. Новых ContextOperation или записей туда не требуется.
- ShortMemory принимает только RecentCausalTransition. Она не используется как
  хранилище similarity или новой внешней истории. Читается только snapshot.

Новый [EchoCandidateComparison](../clc/echo/candidate_comparison.py) — небольшой
явный caller-owned компонент, использующий только эти публичные APIs. Он не
добавляет registry, worker, scheduler или tick hook. Production session/Heart,
ЭХО, ДАР и NFP contracts не изменены. По умолчанию компонент не создаётся;
само его создание не запускает работу. Нужны явные ECHO, WorkLimits,
AdmissionLimits и вызов submit. Без ДАР запрос отклоняется существующим API.

## API и схема

```python
bridge = EchoCandidateComparison(session)
initial = bridge.submit(expectation.expectation_id, (b_tick, c_tick))
# session.step()/run() остаются единственным способом продвижения вычислений.
progress_or_result = bridge.snapshot()
bridge.release()
```

Порядок: наблюдение A → явный expect/expect_transition → пропуски → реальные
наблюдения B и C → явный submit → две queued DAR заявки → последовательные
MultiTickComparison в Heart → snapshot относительной оценки.

submit принимает идентификатор существующего живого непротиворечивого ожидания
и два разных tick реальных удерживаемых session observations. Исходное окно
должно быть именно окном session record либо after_sensory_window удерживаемого
ShortMemory transition. Новый внешний NFP не принимается от caller. Для каждого
кандидата требуется исторический EchoMatch того же ожидания, source и observation.
Несовместимые, expired и contradictory матчи отклоняются. Пропуск наблюдения
не превращается в нулевой кадр. Inconclusive и observed_absence можно измерять,
но они не дают предпочтения в гипотезе продолжения.

Две пары `(A, B)` и `(A, C)` передаются обычному ДАР. Если вторая заявка
отклонена, выполняется одна попытка cancel/release первой на той же
сериализованной границе. При ошибке cleanup ownership сохраняется до явного
последующего release; чужие заявки сохраняются. Автоматических повторов нет. Допускается очередь
существующих заявок, но активный вычислительный процесс по-прежнему ровно один.

## Результат и неопределённость

Frozen `CandidateEvaluation` содержит UUID evaluation, expectation ID,
source/candidate WindowSourceDescriptors, два исторических EchoMatch и два
актуальных ComparisonRequest (либо None при преждевременном внешнем release).
Сохраняется цепочка evaluation → request_id → work.process_id → result_id →
source_descriptors: window/frame IDs, origins, ticks, provenance_ref. Для
queued cancelled заявки process/result не выдумываются; источник остаётся
в descriptors оценки. После release caller может хранить уже полученный snapshot.

Состояния snapshot:

| Состояние | Значение |
| --- | --- |
| pending | Хотя бы одно необходимое сравнение queued/running; delta и preference отсутствуют |
| insufficient_data | Нет заявки/result, есть failed/cancelled либо хотя бы один матч не support |
| indistinguishable | Оба результата готовы, оба матча support, измерения равны в пределах округления |
| relative_similarity | Оба результата готовы, оба матча support; предпочтение определяется знаком реальной разности score |

`score_delta = score(A,B) - score(A,C)`. Это signed структурное преимущество B.
Никаких категорий по порогу score и вероятностей идентичности нет. Абсолютный
`1e-12` нужен только для практически равных floating-point измерений, не для
семантического решения. Для недостаточной поддержки ЭХО готовая delta доступна
как measurement, но preferred_observation_id отсутствует. Если вычисление
не завершено/потеряно/отменено/сломано, delta отсутствует.

Наблюдённый NFP, ожидание, measurement и относительная оценка остаются разными
сущностями. Поддержка ожидаемых координат принадлежит существующему ЭХО;
сравнение лишь ранжирует структурную близость среди двух поддержанных наблюдений.
`origin=INTERNAL_STATE`, `identity_confirmed=False` во всех исходах. Даже score=1
не доказывает идентичность и не означает вероятность идентичности.
Оценка относится к явно выбранной исторической паре: последующие expiration,
пропуски и новые наблюдения продолжают обрабатываться ЭХО независимо. snapshot
не продлевает ожидание, не обновляет его last_match и не утверждает актуальную
поддержку в будущем. Результаты не попадают в sensory present, selection или retrieval.

## Поведенческие эксперименты

[Новый verifier](../tools/verify_echo_dar_cognitive_integration.py) использует
реальные NativeHeartSession и VisualFieldSnapshot → production transducer →
immutable structural NFP, без подстановки InternalSimilarity или резолюций.
Writable ExpSM fixtures находятся во временных каталогах.

Основной эксперимент: A=(1,1,0,0) на tick 0, явное ожидание координаты 0,
пропуски 1–2, B=(1,.8,0,0) на tick 3, C=(1,0,1,0) на tick 4.
После submit при cells_per_tick=1 первая работа действительно вычисляет четыре
координаты на ticks 5–8 и даёт score=.95; вторая работает на ticks 9–12 и даёт
score=.5. До окончания второй работы оценки предпочтения нет. Итог delta=.45,
предпочтение B; перестановка паттернов даёт delta=-.45 и предпочтение C.
Синхронный NFPWindowSimilarity используется только как независимая проверка
фактически вычисленных результатов, не как источник ответа для компонента.

Исходные 16 behavioral cases сохранены и покрывают: оба направления предпочтения и provenance;
точное/практическое равенство и score=1 без identity confirmation; inconclusive/observed_absence; queued/active cancel;
вычислительный failed с продолжением следующей заявки без retry; потерянный
после release outcome; явное освобождение и повторное использование capacity;
rollback второй отклонённой заявки без затрагивания чужой; отсутствующие и
невалидные observation ticks; не наблюдённый source/истёкшее ожидание;
contradiction/несовместимую topology; default-disabled и pulse guard;
pause/resume/STOP и frozen snapshots; expect_transition из реальной ShortMemory;
дифференциальный запуск с реально выполняемыми native actions.

В тесте ошибки используется явная fault injection `_internal_work._inputs=None`;
положительные эксперименты используют только production public API.
Проверяется отсутствие ретроспективного перехода для пропущенного T+1,
неизменность числа действий, world ticks, ShortMemory, ContextMemory events,
memory_updates и value_feedback_updates между запусками с bridge и без него.

## Correction: exception-safe ownership

Review первого pass выявил два P2-дефекта:

- **P2-A:** UUID/descriptors создавались после принятия обеих заявок, вне rollback.
  При исключении `_binding=None`, но две queued заявки оставались с входами;
  публичный bridge.release не мог их освободить.
- **P2-B:** при отказе второй заявки исключение release первой в rollback
  оставляло cancelled outcome, terminal slot и потерянный ownership.

Минимальное исправление разделяет два состояния:

- `_binding` — только полностью сформированная metadata оценки и два request ID;
- `_owned_requests` — отдельный список максимум двух принятых request ID,
  сохраняющий право cleanup даже при отсутствии `_binding`.

Все metadata, не зависящие от admission (UUID evaluation, descriptors,
historical matches), готовятся до первой заявки. Каждый успешно возвращённый
request ID немедленно сохраняется в owned list. Повторный submit запрещён,
пока есть готовая binding либо хотя бы один неосвобождённый ID.

При ошибке admission/публикации начального snapshot `_binding` сбрасывается:
неполная/неуспешная попытка не публикует CandidateEvaluation. Выполняется одна
попытка release owned заявок. Catch BaseException также обеспечивает cleanup
при KeyboardInterrupt между последовательными admission. Исходная ошибка
пробрасывается; если cleanup тоже падает, его исключение пробрасывается с
исходной ошибкой в цепочке context. Никакого скрытого retry нет.

release работает независимо от `_binding`. Для каждого owned ID read-only
comparison_requests проверяет наличие; если заявка есть, вызываются cancel и
release. ID удаляется из owned list только после успешного release либо
подтверждённого отсутствия. При исключении cancel/release делается read-only
проверка: операция могла применить эффект до исключения. KeyError сам по себе
не означает, что ресурс освобождён. Ошибка не подавляется даже при подтверждённом
эффекте. Если read-only проверка тоже падает, ownership консервативно сохраняется.

Успешно очищенные ID удаляются по одному. После частичной ошибки остаются только
неосвобождённые/неподтверждённые ID; следующие owned и чужие заявки не меняются.
Позднейший явный bridge.release сверяет состояние и завершает cleanup.
После освобождения всех ID `_binding` сбрасывается; повторный release безопасен.
Если evaluation ещё не сформирована, snapshot возвращает None даже при наличии
оставшегося cleanup ownership. Caller не должен трактовать None как отсутствие
ресурсов после исключения: требуется явный release.
**`snapshot=None` не доказывает отсутствие удержанных ресурсов.**

Новые 12 постоянных targeted cases (всего **28** в verifier) проверяют:

1. Исходный UUID fault: успешный обычный submit/release, затем OSError UUID до
   admission; ни одного нового запроса, bridge остаётся пригодным к работе.
2. Descriptor fault до admission без затрагивания чужой заявки.
3. Исходный rollback fault при max_pending=1: cancelled outcome сохраняется,
   snapshot=None, submit блокируется; явный release освобождает slot, capacity
   восстанавливается и следующая работа обрабатывает ровно одну координату/tick.
4. Частичный cleanup двух owned заявок с сохранением чужих заявок и FIFO.
5. Ошибку cancel до эффекта: release не вызывается, ownership сохраняется.
6. Ошибку cancel после эффекта: terminal outcome остаётся управляемым.
7. Release с фактическим удалением, затем KeyError: отсутствие подтверждается;
   следующая явная попытка не повторяет освобождение удалённого ID.
8. KeyError без удаления: ownership не снимается.
9. Ошибку read-only reconciliation после фактического удаления: ownership
   сохраняется до доступной последующей проверки.
10. Ошибку начального snapshot и rollback read: никакой успешной оценки,
    оба ID остаются доступными для явного cleanup, затем обычный путь успешен.
11. KeyboardInterrupt при второй admission с успешным rollback первой.
12. Ошибку начального read в release: никаких изменений ownership до следующей
    явной попытки; повторный release после завершения идемпотентен.

Fault injection применяется только к воспроизводимым ошибкам. Положительные
ветви выполняют реальные public session API. Два исходных review reproducers
также запущены без изменения их проверок: теперь **2 PASS**, отдельно от общего
числа уникальных постоянных tests. Лог: `/tmp/rnd019-correction/original-reproducers.log`.

## Принятые ограничения

- Одно удерживаемое evaluation на экземпляр, две заявки, никаких автоматических
  evaluations. Совокупное число заявок/окон ограничивает существующий ДАР.
- `release()` явно отменяет незавершённые owned заявки и освобождает outcomes.
  Component удерживает только descriptors/matches/IDs и ссылку на уже существующую
  session, не дополнительные activation windows или растущий журнал.
- Caller соблюдает существующий сериализованный session contract. Owned requests
  нельзя освобождать отдельно до bridge.release; нарушение обнаруживается как
  insufficient_data. Освобождение bridge внутри pulse отклоняет session guard.
- Admission двух заявок последовательный с rollback, без нового batch API.
  Review признал последовательный admission достаточным; batch API не требуется.
- Доступны два наблюдения на разных ticks. Одновременное выделение нескольких
  объектов из одного кадра и object tracking отсутствуют.
- Только уже удерживаемые реальные окна; нет реконструкции старой истории,
  автоматического формирования ожиданий, learning, постоянной памяти результатов,
  AKBSM writes или Feedback APPLY. Metadata byte-limit наследует ограничения RND-018.
- Числовая ничья, правило двух support и историческая семантика приняты
  архитектурным review первого pass. Correction их не меняет.

## Проверки и Memory safety

Проверки выполняются `python -B` во временной копии без .git:
`/tmp/rnd019-correction/repo`. Логи и полный inventory SHA-256 до/после:
`/tmp/rnd019-correction`. Исходный baseline: `/tmp/rnd019-validation`. Исходники и итоговый scope сверяются отдельно.

Первый pass: 153 уникальных tests PASS. Свежая батарея после correction:
**165 уникальных постоянных unittest cases PASS** (28 RND-019 + 137 regression).
Оба исходных review reproducers также PASS, но их повторные проверки не добавлены
к 165. Все исходные 16 behavioral cases прошли в составе 28. Полная батарея всех
repository verifiers не запускалась; повторные прогоны не суммируются.

| Verifier (`tools/verify_*.py`) | PASS tests |
| --- | ---: |
| echo_dar_cognitive_integration | 28 |
| minimal_dar_admission | 15 |
| multitick_internal_work | 14 |
| echo_expectations | 17 |
| native_heart_b2 | 23 |
| native_session_b1 | 5 |
| native_bounded_delivery | 18 |
| nfp_context_short_memory | 24 |
| nfp_remembered_action_guarded_execution | 8 |
| legacy_native_joint_checkpoint | 13 |

Известный Substrate **FAIL, не PASS**: `runtime does not import clc.patterns`.
Повторно воспроизведён после correction в tested copy; единственный FAIL
побуквенно совпадает с сохранённым логом чистого git archive исходного HEAD
(`/tmp/rnd019-validation/substrate-baseline.log`). В обоих случаях
exit 1 и те же три нарушителя: native_bounded_delivery.py,
native_heart_session.py, native_session.py. Новых нарушителей нет. Проверочный
контракт и allowlist не менялись.

Syntax, whitespace, итоговый scope и совпадение протестированных исходников
с workspace проверены. Изменений existing tracked files нет. Scope — ровно
три новых файла: clc/echo/candidate_comparison.py,
tools/verify_echo_dar_cognitive_integration.py и этот документ.
Production Memory не менялась: полный inventory всех 12 файлов совпадает
с HEAD до/после проверок в workspace, tested copy и baseline archive.
Production-веса неизменны; дополнительных служебных файлов в Memory нет.
После correction и при closure scope ограничен теми же тремя файлами RND-019;
production contracts RND-016–018 и существующие tracked files не изменены.
Closure выполняется на main поверх указанного исходного HEAD; в staging
включаются только эти три файла. RND-020 не начат.
Компонент не имеет файлового I/O, Memory writers, Feedback или action callbacks.

Контрольный inventory SHA-256 (все 12 файлов):

| Файл | SHA-256 |
| --- | --- |
| `Memory/AKBSM/AKBSM_CRUD.py` | `268daa402f5fdd7239100e33a9a181b767340a221ec6073607ea442616f8773e` |
| `Memory/AKBSM/AKBSM_ne.json` | `0153def862ef606140903bb454abaa75f651d18d8bcbd9c3aeb10070705c23bd` |
| `Memory/AKBSM/DB/1.nfp` | `9dc8bdea3ab22028eb71bf88beefedba0a31ed85c60f3d804c533896d2f31536` |
| `Memory/AKBSM/DB/2.nfp` | `2a4365119b61bbd90ba6e6bb5c72aac605331779084434485d3a6d3539a2d227` |
| `Memory/DTF.json` | `081ce0056d36c0bf599b279828ee35705b84f942ce3d8e58db05cebdcfdf9c26` |
| `Memory/DTF_TFH.json` | `b5289aa54f2b3f87ee5e7a3d1fa428cae5c85bcbfacd0cfeb568ef452ba938de` |
| `Memory/ExpSM/ExpSM_data.json` | `6a457d5511f063d6484999c0f97802c5dc0fc77c2d504eb183aac1028adc603e` |
| `Memory/ExpSM/ExpSM_drafts.json` | `12a54a83784bbef939fb16b319dce5f1b94f77745c6e49a197118249b9fecbd4` |
| `Memory/ExpSM/Exp_CRUD.py` | `ab081ea719c24307336f13143a94412d088e53b2ad18b22710ffd0ad2485c880` |
| `Memory/WL/WL.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `Memory/WL/WL_CRUD.py` | `8f8d53ddd88b0439520404f2c52407915d2982fb39c0d49e33776d15bea14b13` |
| `Memory/pattern_manifest.json` | `d442580fa93cd057854b91382e36f85db904ebc25a8ebbfd6772052b39c338f6` |


## Финальный review и closure

Координатор принял correction: **ACCEPTED FOR CLOSURE**, RND-019 **CLOSED**.
Окончательный контракт — явная интеграция EchoCandidateComparison с существующим
ECHO, DAR A0 и единственным MultiTickComparison. Caller явно создаёт evaluation
и две сравнительные заявки; реальные вычисления распределены по Heart ticks.
Относительная оценка зависит от вычисленных score и требует двух исторических
supported matches. Числовая ничья использует только допуск `1e-12`.
Источники и результаты сохраняют provenance; `identity_confirmed=False`
независимо от similarity. Ownership заявок отделён от готовой evaluation;
metadata готовится до admission. Ошибки rollback/cleanup сохраняют ownership
для явного повторного release без скрытого retry.

При closure Python-исходники побайтово совпадают с исправленной tested copy
`/tmp/rnd019-correction/repo`. Подтверждены **165 уникальных behavioral PASS**:
исходные 16 RND-019, 12 новых exception-safety tests и 137 regression tests.
Оба первоначальных P2-reproducers также PASS, без добавления повторов к 165.
В проверенных exception paths оставшиеся заявки доступны для явного cleanup;
повторное освобождение сохраняет чужие заявки и FIFO. Новых рисков и изменений
Python нет, поэтому повторный полный прогон регрессии при closure не выполнялся.

Проверены syntax, итоговый diff, whitespace, scope трёх файлов и staged paths.
Inventory/SHA-256 всех 12 Production Memory файлов совпадают с исходным HEAD
и pre-correction baseline; веса неизменны. Substrate baseline **FAIL остаётся
открытым** с теми же тремя нарушителями; новых нарушителей нет, PASS не заявлен.

Сохранены ограничения: два кандидата, явный opt-in, один активный процесс,
RAM-only без persistent writes, самостоятельного обучения и object tracking.
**`snapshot=None` не доказывает отсутствие удержанных ресурсов**: после ошибки
caller завершает освобождение явным release. Автоматической очистки по retry нет.
Локальный коммит содержит только production bridge, verifier и этот документ;
AGENTS.md, логи и временные файлы не включаются. После commit — STOP.
