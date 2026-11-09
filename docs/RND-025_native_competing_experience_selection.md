# RND-025 — Native Competing Acquired Experience Selection

2026-11-09. **CLOSED — ACCEPTED FOR CLOSURE.**
Текущий статус заменяет исторические OPEN/STOP checkpoints ниже.

История: **IMPLEMENTATION FIRST PASS — OPEN FOR ARCHITECTURE & BEHAVIORAL REVIEW.**
Это не closure. Исходная ветка `main`, HEAD
`226100d553351fe42697b5fa86e6593519c71777`; RND-021/022/023/024 CLOSED.
RND-025/A: READY FOR IMPLEMENTATION. LOCAL ONLY, без commits/remote/tags.

## Feasibility gate: PASS

До добавления файлов реализации выполнен отдельный isolated gate:
`/tmp/rnd025b-gate.py`, результат `/tmp/rnd025b-gate-result.json`.
Использованы существующие API, без изменения confinement/provenance.

Один dedicated temporary root содержит два **пустых training read stores** и
отдельный исходно пустой `competition.json`. Registry paths сразу temporary.
Две сессии читают только свои пустые stores; два acquisition owner направляют
CREATE через существующий `NFPExpSMCreateWriter` в общий competition store.
`isolated_root` owner охватывает training reader, registry и writer destination.
Это соответствует фактическому RND-021 containment contract. Writer и сессия
остаются живыми до окончания acquisition. Вызовы сериализованы.

Нельзя обучать B через тот же reader, куда уже записана A: существующий Heart
разрешает exploratory bootstrap только при отсутствии retrieval candidates.
Это правило не ослаблено. Training readers после обучения остаются пустыми.

## Два acquisition paths

Используется неизменённый `SyntheticClosedLoopVisualWorld(shape=(1,3),
initial_row=0, initial_column=1)`. Никаких ручных transitions или learned records.

| Session | Exploratory commands | Реальные позиции | Целевая поддержка |
|---|---|---|---|
| A | right, left, right | center→right→center→right | center/right: 2 occurrences |
| B | left, right, left | center→left→center→left | center/left: 2 occurrences |

Отдельные test-owner IDs, authorization IDs, session UUID, acquisition owner и
request ID. На T=0,1,2 выполняется по одному exploratory action, на T=1,2,3
приходит соответствующий actual T+1. PAUSE на T=3 оставляет observation без
четвёртого действия. Все три exact retained ShortMemory transitions каждой
сессии проходят RND-021 admission. Поддержка групп — `(2,1)`; ни одно evidence
не отфильтровано ради promotion. Full-set conflict check проходит.

Каждый owner создаёт только один proposal/request и делает один отдельный
`create(test_owner_authorized=True)`. Existing writer дополнительно проверяет
`allow_expsm_commit` temporary `mutating_memory` policy. Fresh reconciliation и
дополнительный authoritative strict read подтверждают каждую запись.

В выполненных fixtures writer выделил **A ID=`1`, B ID=`2`**. Код не подставляет
эти IDs: он использует возвращённые writer records и связывает все последующие
этапы по ним.

| Record | Context values | Action values | Extracted actual effect | support |
|---|---|---|---|---:|
| A (`1`) | `(0,1,0)` | right `(0,1)` | `(0,-1,+1)` | 2 |
| B (`2`) | `(0,1,0)` | left `(1,0)` | `(+1,-1,0)` | 2 |

У context/effect topology `(1,3)`, у action `(2,)`. У каждой записи свои три
admitted occurrence/evidence identities, целевую группу поддерживают две из них.
Frozen acquisition traces содержат session/request IDs, occurrence/evidence IDs,
exploratory provenance и CREATE/readback statuses. Наборы между сессиями не
пересекаются; повторный CREATE и третья запись отсутствуют.

Оба локальных grouper законно выдают `proposal:000001`: это **не** глобальная
идентичность. Разные action/effect, writer IDs, session/request и evidence scope
не позволяют объявить записи одним опытом. Семантический dedup writer не добавлен;
за пределами этого конечного owner durable exactly-once CREATE не заявляется.

## C0/C1/C2/C3: фактическое поведение

Baseline сохраняется как полные authoritative bytes общего store до feedback.
Независимые controls получают точную полную копию этих bytes, без редактирования
JSON, records или metrics. Все ordinary sessions заново создают тот же мир из
центра, без exploration. UUID различаются; sensory tensors и начальные ticks
одинаковы. Старый мир не возвращается в центр ручной записью позиции.

Параметры объявлены до наблюдений: retrieval threshold `1/3`, native activation
minimum `.35`, selector threshold `.35`, effect agreement `.75`, active mode.
Весов, world dynamics, guard, candidate ordering или thresholds после результата
не меняли. Sensitivity configuration для переключения не требуется.

| Контроль | Retrieval order | Activation rank / scores | Selection / поведение |
|---|---|---|---|
| C0 | A,B | A `.775`, B `.775` | A; исходная ничья |
| C1 до APPLY | A,B | A `.775`, B `.775` | A/right, actual right, evaluator HIT |
| C1 после APPLY, свежая center session | A,B | B `.775`, A `.7568166666666667` | B |
| C2: настоящий HIT, APPLY OFF; свежий повтор | A,B | A `.775`, B `.775` | A |
| C3: отдельная свежая post-C1 session | A,B | B `.775`, A `.7568166666666667` | B/left, actual left |

Retriever возвращает обе записи с context similarity=1, без action/effect filter.
Обе проходят activation minimum и входят в top-3. Store/retrieval order A,B
сохраняется после APPLY. Стабильная activation sort сохраняет порядок равных
scores; `DecisionSelector.select_native` использует первый максимум. Начальная
A выбрана именно этим deterministic tie-breaking. После APPLY у B строгий
перевес: изменение не вызвано перестановкой или пороговым исчезновением A.

C1 действительно выполняет A через remembered coordinator: один guard pass,
один physical right apply, pending и real owned-world consequence T+1. Exact
retained transition даёт extractor effect `(0,-1,+1)`. Existing evaluator
возвращает HIT, similarity=1. Только его evidence передаётся policy-gated writer.
Fresh strict readback подтверждает A hits/misses=`1/0`, confidence/repeatability
`.382/.425`, intended/result/actual record, receipt/evidence digest/event key и
execution occurrence index. Receipt attribution — source A. B целиком неизменна;
TargetCore A неизменён. В store ровно две записи.

C2 выполняет тот же real right и получает тот же actual T+1 и HIT, но writer не
вызывается. Store bytes и receipt ledger точно совпадают с baseline. Повторная
ordinary center session сохраняет `.775/.775` и selection A.

C3 подтверждает всю цепь:
`persisted B → retrieved B → activated B → selected B → request B → execution B
→ guarded physical left → actual T+1 → exact ShortMemory occurrence`.
Action `(1,0)` реально переводит мир `(0,1)→(0,0)`; sensor values T+1=`(1,0,0)`.
Pending/recent occurrence совпадает с C3 execution, источник равен B, guard_passed
истинен, exploratory intent отсутствует. Выполнен ровно один physical apply.
Дополнительный feedback B не применяется. Baseline и post-C1 snapshots не смешаны.

## Математика и границы вывода

Stage 2 production formula не менялась. После события при новых `h,m`:

```text
q = .60 * (1 - exp(-h/20)) * h/max(1,h+m)
c' = round(clamp(.75*min(c,.75) + .25*q, 0,.75), 3)
r' = round(clamp(max(.85*r, .90*(1-exp(-(h+m)/10))), 0,.90), 3)
v = (h+1)/(h+m+2)
activation = clamp(.55*similarity + .20*min(c,.75) + .15*r + .10*v, 0,1)
```

До feedback: `h=m=0`, `c=r=.5`, `v=.5`, поэтому activation обеих `.775`.
Первый HIT A: `h=1,m=0`, persisted `c=.382,r=.425`, `v=2/3`:

```text
A = .55 + .20*.382 + .15*.425 + .10*(2/3)
  = .7568166666666667
B = .55 + .20*.500 + .15*.500 + .10*(1/2)
  = .775
```

Проверена последовательность: persisted metrics A изменились → activation A
изменилась → ranking A/B сменился → selector выбрал B → coordinator исполнил B.
Matched no-feedback control исключает эффект одной лишь evaluation.

**Feedback-driven selection switching ≠ improved reliability preference ≠ utility learning.**
Первый HIT текущей Stage 2 formula может **снижать** score подтверждённой записи
относительно нетронутой. Эта особенность не исправлена. Не заявляются reward/utility
learning, оптимальная стратегия, самостоятельное целеполагание или предпочтение
более полезного/надёжного действия.

## Authority, bounded owner и ошибки

`CompetingEpisode` — отдельный явно вызываемый trusted isolated owner. RND-024
one-record owner не ослаблен и не используется для двух записей. Переиспользованы
только его scalar diagnostics, call-observer и strict read helper. Новый owner
проверяет две distinct acquired записи и обе candidate chains, связывает selected
source с его immutable TargetCore, action/effect и actual execution; source не
назначается владельцем заранее. Selector/evaluator/writers/world прежние.

Конечные границы: две acquisition sessions по 4 ticks, по три admitted evidence,
один CREATE на owner; ordinary episode — 2 ticks, 2 candidates, один physical
apply, ≤1 retained transition, один evaluator, ≤1 APPLY/reconciliation. ShortMemory
8 entries / age 10; journal 128. Diagnostics exact built-in str длиной 1..256,
первая причина STOP сохраняется. Нет растущего owner history или strong session
reference. Frozen records/evidence и малые scalar summaries не удерживают мир.
Произвольные синхронные callbacks/formatting не имеют preemption.

Сохранены policy gates, RND-021 provenance, owned real T+1, single pending/apply
per occurrence, Stage 2 receipt/idempotency. READBACK_FAILED допускает только
существующую read-only reconciliation; дополнительно проверяется неизменность
второй записи. WRITE_FAILED, включая failure после возможной persistent mutation,
останавливает owner как persistence_uncertain, даже при retry_safe в existing
result. Blind retries нет. При неожиданных исключениях terminal state/fallback
фиксируются до диагностики; bare raise сохраняет primary identity/traceback.
Санитизируется только diagnostic text, не authority/result status.

Tests охватывают support/replay, occurrence conflict, отсутствие exploratory
permission, отдельно owner CREATE authority и denied writer policy, source/core/
prediction/selection-chain mismatch, missing/expired/unretained T+1, потерю sensor
journal, guard denial, uncertain physical apply, stale TargetCore, denied APPLY,
duplicate feedback ALREADY_APPLIED, changed evidence EVENT_CONFLICT, recovery и
post-replace failures. Отдельно checked eligible unselected B нельзя приписать
execution A. Ablation без B получает A через настоящий одиночный CREATE; после
настоящего HIT/APPLY обычный selector продолжает выбирать A.

Отрицательный full-set conflict использует явно обозначенный owned sensor fault:
путь delivery→ShortMemory→factory→admission настоящий, но sensor snapshot при T=3
намеренно противоречит прежнему effect. Это negative fault injection, не утверждение
о недетерминированности неизменённого positive world. Fabricated learned evidence
в positive arms нет. Negative evidence/result alterations используются только
для проверок отказа и existing writer replay/conflict API.

GC/weakref tests при живом owner подтверждают освобождение session/world, primary
exception, payload и malicious diagnostic text после удаления внешних test hooks.
Нет универсальной защиты от произвольной подмены trusted Python runtime; caller
обязан сохранять exclusive serialized ownership. Durable restart recovery/outbox
не добавлены. После uncertainty нельзя заново запускать acquisition в том же root:
инициализация требует нового каталога, существующий store не перезаписывается.

## Проверки первого pass

Все Python launches: `PYTHONDONTWRITEBYTECODE=1 python -B`. Writable fixtures,
logs и validation copy — только temporary isolation. Целевой verifier проверен
в исходном checkout и в свежей `/tmp` copy; повторные прогоны не суммируются.

| Suite tools/verify_*.py | Unique unittest methods PASS |
|---|---:|
| native_competing_experience_selection | 40 |
| bounded_native_acquisition | 40 |
| synthetic_exploratory_bootstrap | 41 |
| first_native_acquired_experience_loop | 22 |
| native_outcome_feedback_loop | 33 |
| nfp_expsm_operational_retrieval | 5 |
| nfp_remembered_action_guarded_execution | 8 |
| nfp_native_feedback_evaluation | 15 |
| nfp_native_feedback_apply | 11 |
| nfp_native_feedback_replay_idempotency | 15 |
| nfp_expsm_policy_gated_create | 8 |
| expsm_persistence_stage1 | 9 |
| persistent_nfp_expsm_representation | 10 |
| native_heart_b2 | 23 |
| **Итого** | **280** |

Gate, smoke runs, промежуточные исправления тестовых fixtures, повторный targeted
run и запуск из validation copy не прибавлены. Stage 1 AST audit: 7 writers,
7 mutation paths, ноль direct-write/transaction/preflight/store-order violations.
Syntax compile без bytecode и whitespace проверены отдельно.

Substrate сохраняет исторический **FAIL**: runtime imports clc.patterns в
`clc/runtime/native_bounded_delivery.py`, `clc/runtime/native_heart_session.py`,
`clc/runtime/native_session.py`. Других violators нет. Этот FAIL не исправлен,
не включён в PASS count и остаётся открытым.

Logs: `/tmp/rnd025b-target.log`, `/tmp/rnd025b-regression-*.log`;
validation result `/tmp/rnd025b-validation-result.json` указывает fresh copy и log.
Исходный полный inventory `/tmp/rnd025b-baseline.json`; финальное сравнение
`/tmp/rnd025b-final-safety.json`.

## Safety и точный Git scope

По сравнению с pre-edit inventory все существовавшие файлы и каталоги checkout
неизменны. Все 12 Production Memory files и directory inventory совпадают;
Memory bytes также совпадают с HEAD. Weights, Stage 1/2 и closed RND-021–024
не менялись. Все 119 baseline ignored `.pyc` побайтово сохранены.
`sf4.py` не затронут: SHA-256
`0e3190a815dd4e65ac768e586b04cd877d845c67e0641fdbddc7e232fbcec975`.
Новых checkout lock/cache/manifest/service files нет. Tracked diff и staging
пусты; новые файлы первого pass остаются untracked для review.

Созданы только:

- `scenarios/native_competing_experience_selection.py`;
- `tools/verify_native_competing_experience_selection.py`;
- `docs/RND-025_native_competing_experience_selection.md`.

Исходный untracked `sf4.py` сохранён отдельно от scope. Production Memory writes,
automatic acquisition/feedback hooks, новые selector/writer/evaluator/schema/world
не добавлены. Commits/remote/tags не выполнялись. RND-026 не начат.

**STOP FOR ARCHITECTURE & BEHAVIORAL REVIEW.**


## Final closure — CLOSED

2026-11-09. Architecture & behavioral review: **ACCEPTED FOR CLOSURE**.
Implementation и review checkpoints выше сохранены как история.

Два независимых acquisition paths подтверждены: отдельные exploratory sessions,
authorization и owners; пустые training read stores; полный admission трёх real
retained transitions на session, группы support 2/1. Два policy-gated CREATE в
общий isolated store дали writer-assigned A=`1` (center/right, effect `(0,-1,+1)`)
и B=`2` (center/left, effect `(+1,-1,0)`).

C0: обе записи eligible, `.775/.775`, native tie-breaking выбирает A.
C1: genuine right A, actual T+1 и evaluator HIT; один authorized APPLY изменяет
только A. Hits/misses 1/0, confidence/repeatability .382/.425; fresh activation
A=.7568166667, B=.775. При default .35 production selector выбирает B.
C2: matched genuine execution/HIT без APPLY сохраняет store bytes/receipt ledger
и fresh selection A. C3: B исполняет guarded left, физический переход center→left
и реальный T+1; source/TargetCore/pending/occurrence continuity подтверждена.

Доказана propagation real feedback → persisted metrics → altered ranking →
native selection A→B → guarded physical execution B. Улучшение предпочтения более
надёжного опыта, самостоятельное определение полезности, reward/utility learning
и оптимальная стратегия не доказаны. Первый HIT по текущей production Stage 2
formula снижает score A относительно нетронутой B; это не исправлялось.

RND-021/022 provenance/authority, отдельные CREATE/APPLY policy gates, single
apply/pending, replay/idempotency и conflict handling сохранены. READBACK_FAILED
использует authoritative reconciliation; uncertain WRITE_FAILED даёт terminal
STOP без blind retry. Bounded exact-string diagnostics, primary exceptions и
отсутствие нежелательного session/world retention подтверждены targeted tests.
Automatic learning hooks отсутствуют. Дополнительный review probe потери
acknowledgement второго CREATE подтвердил остановку без третьего CREATE и без
blind restart в существующем root.

Счёт проверок не суммируется: **280 unique implementation PASS** — предыдущая
полная validation; **40 свежих targeted review PASS** — повтор того же targeted
набора; recovery probe учитывается отдельно. Closure меняет только документацию,
Python source не менялся; полной регрессии без новых оснований нет.

Исторический `/tmp/rnd025b-baseline.json` отсутствует. Поэтому повторного сравнения
с ним и исторических per-file bytecode hashes не заявляем. Closure baseline
`/tmp/rnd025-closure-baseline.json` фиксирует текущие hashes/inventory до изменения
документации. Все 12 Production Memory files сравниваются с tracked HEAD; weights,
Stage 1/2 и прочие tracked files неизменны. Текущие 119 ignored `.pyc`, directory
inventory и sf4.py сохраняются побайтово за closure. Известный sf4 SHA-256:
`0e3190a815dd4e65ac768e586b04cd877d845c67e0641fdbddc7e232fbcec975`.
Syntax/whitespace и точный scope проверены перед commit. Исторический Substrate
baseline FAIL с теми же тремя runtime paths остаётся открытым, новых violators нет.

Единственный локальный closure commit:
`feat(learning): add feedback-driven competing experience selection`.
Parent: `226100d553351fe42697b5fa86e6593519c71777`; scope — ровно три RND-025
файла scenario/verifier/document, перечисленные выше. sf4.py исключён из staging.
Remote/tags и RND-026 не выполняются.

**STOP AFTER CLOSURE.**
