# RND-026 — Evidence-Based Confidence Diagnostic Bench

2026-11-09. **CLOSED — ACCEPTED FOR CLOSURE.**
RND-026/C independent architecture & methodology review принят.
Итоговый статус заменяет исторические FIRST PASS / OPEN checkpoints ниже.
Production calibration policy не менялась; future shadow experiment не начат.

## История implementation first pass

2026-11-09. **FIRST PASS — READY FOR ARCHITECTURE REVIEW (исторический checkpoint).**
LOCAL ONLY. Контрольная точка: main,
`3666f13b049dfe89569aa27b903feb0a5ca9fba5`; RND-021–025 CLOSED.
RND-026/A: READY FOR DIAGNOSTIC EXPERIMENT. Production policy не менялась.

## Назначение и границы

Реализованы только отдельный математический runner, verifier и этот документ.
Стенд не создаёт persisted ExpSM records, не вызывает APPLY/CREATE writers,
не запускает world/ShortMemory и не подключается к NativeHeartSession.

**Mathematical simulation ≠ production feedback replay ≠ native world learning experiment.**
Численные результаты не доказывают новую способность Распутина.

## Модели и production oracle

- M0: реальный `_updated_record` из `clc/expsm/nfp_native_feedback_apply.py`,
  принимающий transient frozen `FormulaRecord(ExpSMOperationalMetadataV1)`;
  реальный `ExpSMActivationModule.activate_native` вычисляет score.
  `object.__new__` задаёт только необходимый id_gen, без registry/path/files.
  ACTION/effect в transient candidate равны None: materialization/execution не заявлены.
- M1: `(h+1)/(h+m+2)`, Beta(1,1) posterior mean.
- M2: `(h+2)/(h+m+4)`, Beta(2,2) posterior mean. При `a=h+2,b=m+2`:
  variance=`a*b/((a+b)^2*(a+b+1))`, std=`sqrt(variance)`.
- M3: `z_next=.95*z_old+.05*y`, initial z=.5.
- M3_alpha20: заранее заданная sensitivity `.80*z_old+.20*y`, initial .5.

M1/M2 предполагают Bernoulli interpretation, обоснованный prior и условную
независимость/стационарность observations. Коррелированные или смешанные контексты
могут сделать uncertainty чрезмерно оптимистичной. EWMA оценивает недавнюю частоту,
а не Beta posterior. Сглаженная частота `(h+k*mu0)/(n+k)` алгебраически совпадает
с Beta mean при alpha=k*mu0, beta=k*(1-mu0); отдельной пятой основной моделью
не объявлена.

Установленной SciPy нет. 95% credible intervals и их coverage — N/A;
нормальное приближение не применяется. Точный M2 posterior std доступен.
Новые поля ExpSM не нужны: Beta использует h/m; EWMA-state transient и не
восстанавливается из одних lifetime counts.

M0 не probability. Ни confidence, ни activation не получают Brier/ECE;
для них эти поля N/A. Utility действий не моделируется.

Production порядок: increment h/m, вычислить targets, smoothing/caps, round(3),
следующий event использует округлённое состояние. Формулы для описания:

```text
q = clamp(.60*(1-exp(-h/20))*h/max(1,h+m),0,.60)
c' = round(clamp(.75*min(c,.75)+.25*q,0,.75),3)
r' = round(clamp(max(.85*r,.90*(1-exp(-(h+m)/10))),0,.90),3)
v = (h+1)/(h+m+2)
a = clamp(.55*s+.20*min(clamp(c,0,1),.75)+.15*r+.10*v,0,1)
```

Эти формулы не дублируются в runner. M0 predict кэширует результат production
activation после реального helper update. Initial activation тоже берётся из oracle.
Repeatability означает количество trial evidence, включая MISS; это не HIT rate.

Gate до benchmark проверяет initial/H/M/HH/HM/MH/10H/50H/50M по RND-026/A,
absolute tolerance 1e-12. Расхождение вызывает STOP до генерации benchmark streams.
**Feasibility и production parity: PASS.**

## Presets, информационные границы и budgets

Full: seeds 0..31, horizon=1000; stationary p={0,.1,.5,.9,1};
change после observation 500: .9→.1 и .1→.9. EWMA coefficients зафиксированы до
результатов. Smoke: seed=0, horizon=32, включая полный bounded prescribed набор.
У каждого series/candidate отдельный `random.Random`, seed получен из SHA-256
строки `rnd026-v1:series:seed:candidate`; Python hash() не используется.
Модели получают общие external outcome tables, а не разные RNG realizations.
Побайтовая воспроизводимость проверена в том же Python runtime; cross-version
гарантия random.Random не заявляется.

Пары A/B: .9/.1, .7/.6, .5/.5, 1/0, .9/.1→.1/.9 на t=500.
Нумерация t=0..999: t=500 соответствует observation 501.
Политики M0/M1/M2/M3/M3_alpha20 используют deterministic argmax своего score,
при ничьей A. Вероятностным моделям threshold .35 не навязывается.
Отдельная M0_native вызывает production selector при threshold .35,
реальную activation eligibility .35/top-3/stable sort. Transient prefilter s>=1/3
соответствует fixed RND-024/025 retrieval configuration, но не выдаётся за вызов
persisted retriever. В основном benchmark s=1: обе записи всегда eligible,
M0_native и M0 дают одинаковые полные результаты во всех seeds/modes/cases.

Full-information: обе записи получают observation каждого шага, в том числе
невыбранная; это верхний контроль доступности информации.
Partial-feedback: только выбранная получает table[candidate][tick]. Неизбранная
не читается и не обновляется. Используется calendar-time table, не очередь,
прокручиваемая только при выборе. Selection получает только состояния моделей,
без latent probabilities и без tables. Prediction фиксируется до чтения outcome,
после чего начисляются метрики и ровно один update на revealed candidate/event.
Per-candidate strictly increasing event token предотвращает дубликаты без ledger.

Алгоритмы не видят latent p; внешний evaluator использует p только для метрик.
В single-stream внешний фиксированный Bernoulli HIT не является native evidence.

Границы: 7 stream presets ×32×5×1000 = 1,120,000 updates;
5 pair presets ×32×6×(2+1)×1000 = 2,880,000 updates.
Всего 4,000,000 benchmark updates плюс конечный prescribed/gate набор.
Одновременно raw table содержит максимум 2×1000 outcomes и 2×1000 latent p;
после series/seed освобождается. Нет растущего raw-event history.
Метрики: постоянные 10 bins и три окна, два gap counters; per-seed summaries
ограничены presets/seeds. ID counters bounded общим budget, без новых keys на event.
Detailed JSON около 25 MB; не является постоянным production хранилищем.

## Метрики

Все forecast metrics pre-event. Окна: all=1000, initial200=observations 1..200,
last200=801..1000. В smoke короткие окна могут пересекаться; full не пересекаются.

- Brier = mean((prediction-before-event-y)^2), только M1/M2/EWMA.
- ECE: 10 bins [0,.1), ...,[.9,1], sum(n_bin/N*abs(mean_prediction-hit_rate)).
  JSON содержит count, mean prediction и hit frequency каждого bin, каждого seed
  и окна; пустые bin means N/A. Агрегат ECE — среднее per-seed ECE, не pooled ECE.
- Forecast metrics в competition: full оценивает оба forecast (2N outcomes),
  partial — только revealed selected forecast (N outcomes). Эти выборки различны.
- Ranking accuracy = число selections с максимальным latent p / число шагов
  с различными p. При равных p ranking comparisons=0, accuracy=N/A.
  Tie score разрешается действительной политикой A-first, без half-credit.
- Switch frequency = число изменений selected на соседних шагах/(N-1).
  None включается как отдельный результат; для N<2 frequency=N/A.
- Selection regret = mean(max_i p_i-p_selected). Для None принято 0 obtained
  reliability; no_selection отдельно. В основном benchmark None не возникает.
- Starvation_i = максимальное число последовательных eligible шагов без выбора i,
  включая начало и конец горизонта. Каждое окно считает gap внутри своего окна.
  В full-information это selection starvation, а не feedback starvation.
- Stream adaptation: первый offset>=0 после t=500, с которого 20 consecutive
  pre-event probability estimates находятся в ±.1 нового p. Для M0 N/A.
- Competition adaptation: первый offset после t=500, с которого 20 consecutive
  selections предпочитают новый лучший latent p; для всех моделей.
- Если устойчивый run не завершён на горизонте: delay=N/A, censored=1.
  Среднее delay вычисляется только по uncensored seeds и всегда сопровождается
  censored fraction. Это не среднее время адаптации всех runs.
- M2 uncertainty — posterior std до event и в snapshots. Interval coverage=N/A.

Каждый numeric aggregate имеет mean, population std, min, max, valid_seeds,
na_seeds. N/A сериализуется null; пропущенные значения не заменяются нулями.

## Предписанные последовательности

Полные initial/intermediate/final snapshots всех моделей в results.json.
Checkpoints: 0,1,2,3,4,5,7,8,10,11,20,50,100,500,1000 и последний шаг каждой
последовательности. Ниже конечные значения M0, s=1; delta относительно initial
c=r=v=.5, a=.775 есть в JSON для каждой строки.

| Sequence | h/m | c | r | v | activation | delta activation |
| --- | --- | --- | --- | --- | --- | --- |
| initial | 0/0 | .500 | .500 | .500000 | .775000 | .000000 |
| (HM)x25 | 25/25 | 0.210000 | 0.894000 | 0.500000 | 0.776100 | 0.001100 |
| (HM)x500 | 500/500 | 0.299000 | 0.900000 | 0.500000 | 0.794800 | 0.019800 |
| (MH)x25 | 25/25 | 0.204000 | 0.894000 | 0.500000 | 0.774900 | -0.000100 |
| (MH)x500 | 500/500 | 0.298000 | 0.900000 | 0.500000 | 0.794600 | 0.019600 |
| H | 1/0 | 0.382000 | 0.425000 | 0.666667 | 0.756817 | -0.018183 |
| H10M90 | 10/90 | 0.025000 | 0.900000 | 0.107843 | 0.700784 | -0.074216 |
| H90M10 | 90/10 | 0.551000 | 0.900000 | 0.892157 | 0.884416 | 0.109416 |
| H9M | 9/1 | 0.194000 | 0.569000 | 0.833333 | 0.757483 | -0.017517 |
| H9Mx10 | 90/10 | 0.537000 | 0.900000 | 0.892157 | 0.881616 | 0.106616 |
| HH | 2/0 | 0.301000 | 0.361000 | 0.750000 | 0.739350 | -0.035650 |
| HHHMM | 3/2 | 0.163000 | 0.354000 | 0.571429 | 0.692843 | -0.082157 |
| HM | 1/1 | 0.290000 | 0.361000 | 0.500000 | 0.712150 | -0.062850 |
| Hx10 | 10/0 | 0.205000 | 0.569000 | 0.916667 | 0.768017 | -0.006983 |
| Hx100 | 100/0 | 0.594000 | 0.900000 | 0.990196 | 0.902820 | 0.127820 |
| Hx1000 | 1000/0 | 0.599000 | 0.900000 | 0.999002 | 0.904700 | 0.129700 |
| Hx5 | 5/0 | 0.192000 | 0.354000 | 0.857143 | 0.727214 | -0.047786 |
| Hx50 | 50/0 | 0.541000 | 0.894000 | 0.980769 | 0.890377 | 0.115377 |
| M | 0/1 | 0.375000 | 0.425000 | 0.333333 | 0.722083 | -0.052917 |
| M10H90 | 90/10 | 0.530000 | 0.900000 | 0.892157 | 0.880216 | 0.105216 |
| M90H10 | 10/90 | 0.015000 | 0.900000 | 0.107843 | 0.698784 | -0.076216 |
| MH | 1/1 | 0.285000 | 0.361000 | 0.500000 | 0.711150 | -0.063850 |
| MM | 0/2 | 0.281000 | 0.361000 | 0.250000 | 0.685350 | -0.089650 |
| MMHHH | 3/2 | 0.138000 | 0.354000 | 0.571429 | 0.687843 | -0.087157 |
| Mx10 | 0/10 | 0.028000 | 0.569000 | 0.083333 | 0.649283 | -0.125717 |
| Mx100 | 0/100 | 0.002000 | 0.900000 | 0.009804 | 0.686380 | -0.088620 |
| Mx1000 | 0/1000 | 0.002000 | 0.900000 | 0.000998 | 0.685500 | -0.089500 |
| Mx5 | 0/5 | 0.118000 | 0.354000 | 0.142857 | 0.640986 | -0.134014 |
| Mx50 | 0/50 | 0.002000 | 0.894000 | 0.019231 | 0.686423 | -0.088577 |

Конечные probability estimates кандидатов; это отдельные шкалы, не mapping в confidence:
| Sequence | M1 | M2 | M3 .05 | M3 .2 |
| --- | --- | --- | --- | --- |
| (HM)x25 | 0.500000 | 0.500000 | 0.488166 | 0.444445 |
| (HM)x500 | 0.500000 | 0.500000 | 0.487179 | 0.444444 |
| (MH)x25 | 0.500000 | 0.500000 | 0.511834 | 0.555555 |
| (MH)x500 | 0.500000 | 0.500000 | 0.512821 | 0.555556 |
| H | 0.666667 | 0.600000 | 0.525000 | 0.600000 |
| H10M90 | 0.107843 | 0.115385 | 0.006928 | 0.000000 |
| H90M10 | 0.892157 | 0.884615 | 0.595777 | 0.107374 |
| H9M | 0.833333 | 0.785714 | 0.650632 | 0.746313 |
| H9Mx10 | 0.892157 | 0.884615 | 0.873171 | 0.775942 |
| HH | 0.750000 | 0.666667 | 0.548750 | 0.680000 |
| HHHMM | 0.571429 | 0.555556 | 0.515610 | 0.476160 |
| HM | 0.500000 | 0.500000 | 0.498750 | 0.480000 |
| Hx10 | 0.916667 | 0.857143 | 0.700632 | 0.946313 |
| Hx100 | 0.990196 | 0.980769 | 0.997040 | 1.000000 |
| Hx1000 | 0.999002 | 0.998008 | 1.000000 | 1.000000 |
| Hx5 | 0.857143 | 0.777778 | 0.613110 | 0.836160 |
| Hx50 | 0.980769 | 0.962963 | 0.961528 | 0.999993 |
| M | 0.333333 | 0.400000 | 0.475000 | 0.400000 |
| M10H90 | 0.892157 | 0.884615 | 0.993072 | 1.000000 |
| M90H10 | 0.107843 | 0.115385 | 0.404223 | 0.892626 |
| MH | 0.500000 | 0.500000 | 0.501250 | 0.520000 |
| MM | 0.250000 | 0.333333 | 0.451250 | 0.320000 |
| MMHHH | 0.571429 | 0.555556 | 0.529515 | 0.651840 |
| Mx10 | 0.083333 | 0.142857 | 0.299368 | 0.053687 |
| Mx100 | 0.009804 | 0.019231 | 0.002960 | 0.000000 |
| Mx1000 | 0.000998 | 0.001992 | 0.000000 | 0.000000 |
| Mx5 | 0.142857 | 0.222222 | 0.386890 | 0.163840 |
| Mx50 | 0.019231 | 0.037037 | 0.038472 | 0.000007 |

Первый HIT: q≈.0292623453, c=round(.375+.25*q,3)=.382,
r=max(.425,.085646...)=.425. Activation .7568166667 против initial .775.
Confidence minimum .182 после 7H, рост с 8H. Activation minimum после 4H;
10H ещё ниже initial, 11H=.7757076923 выше. Это падение от высокого initial score
к low-support target и снижение initial repeatability, а не reward sign error.
HM/MH имеют одинаковые h/m/r/v, но confidence .290/.285: smoothing cumulative
targets зависит от порядка. Beta means не зависят от порядка; EWMA зависит.
50M дают repeatability .894, как 50H. Round(3) сохраняет c=.002 при одних MISS;
1000H дают .599, не неокруглённый предел .600.

## Stationary streams: агрегаты 32 seeds

Brier initial200 и last200; ECE last200. M0 probability metrics=N/A.
Полные all/initial200/last200, std и bins доступны в JSON.

| p | Model | Brier initial | Brier last | ECE last | Final score mean |
| --- | --- | --- | --- | --- | --- |
| p=0 | M0 | N/A | N/A | N/A | 0.685500 |
| p=0 | M1 | 0.003200 | 0.000001 | 0.001114 | 0.000998 |
| p=0 | M2 | 0.005578 | 0.000005 | 0.002223 | 0.001992 |
| p=0 | M3 | 0.012821 | 0.000000 | 0.000000 | 0.000000 |
| p=0 | M3_alpha20 | 0.003472 | 0.000000 | 0.000000 | 0.000000 |
| p=0.1 | M0 | N/A | N/A | N/A | 0.706917 |
| p=0.1 | M1 | 0.092223 | 0.085804 | 0.015602 | 0.100299 |
| p=0.1 | M2 | 0.093437 | 0.085816 | 0.016606 | 0.101096 |
| p=0.1 | M3 | 0.098535 | 0.088071 | 0.039233 | 0.098152 |
| p=0.1 | M3_alpha20 | 0.100130 | 0.095476 | 0.082426 | 0.105274 |
| p=0.5 | M0 | N/A | N/A | N/A | 0.794691 |
| p=0.5 | M1 | 0.253811 | 0.250312 | 0.028693 | 0.498659 |
| p=0.5 | M2 | 0.253018 | 0.250311 | 0.028685 | 0.498662 |
| p=0.5 | M3 | 0.255589 | 0.256022 | 0.073572 | 0.509833 |
| p=0.5 | M3_alpha20 | 0.277899 | 0.276465 | 0.146342 | 0.542680 |
| p=0.9 | M0 | N/A | N/A | N/A | 0.882864 |
| p=0.9 | M1 | 0.092308 | 0.087868 | 0.019002 | 0.899202 |
| p=0.9 | M2 | 0.093565 | 0.087875 | 0.017087 | 0.898406 |
| p=0.9 | M3 | 0.099090 | 0.089964 | 0.037066 | 0.901770 |
| p=0.9 | M3_alpha20 | 0.101077 | 0.097167 | 0.080142 | 0.894045 |
| p=1 | M0 | N/A | N/A | N/A | 0.904700 |
| p=1 | M1 | 0.003200 | 0.000001 | 0.001114 | 0.999002 |
| p=1 | M2 | 0.005578 | 0.000005 | 0.002223 | 0.998008 |
| p=1 | M3 | 0.012821 | 0.000000 | 0.000000 | 1.000000 |
| p=1 | M3_alpha20 | 0.003472 | 0.000000 | 0.000000 | 1.000000 |

M2 final posterior std, mean по seeds:
| Preset | Std |
| --- | --- |
| change=.1-.9 | 0.015768 |
| change=.9-.1 | 0.015769 |
| p=0 | 0.001406 |
| p=0.1 | 0.009501 |
| p=0.5 | 0.015766 |
| p=0.9 | 0.009514 |
| p=1 | 0.001406 |

При p=.5 и большом support M2 std уменьшается, хотя uncertainty отдельного
будущего Bernoulli outcome остаётся большой: parameter uncertainty и variability
outcome различны. Stronger Beta(2,2) prior имеет тот же initial mean .5, но меньшую
initial std; при большом support M1/M2 сближаются.

## Change-point streams

Final estimates и last200 calibration после смены. Delay — uncensored mean;
цензурирование обязательно показывается рядом.

| Change | Model | Final score | Brier last | ECE last | Delay observed | Censored fraction |
| --- | --- | --- | --- | --- | --- | --- |
| change=.1-.9 | M0 | 0.795309 | N/A | N/A | N/A | N/A |
| change=.1-.9 | M1 | 0.502900 | 0.287986 | 0.446958 | N/A | 1.000000 |
| change=.1-.9 | M2 | 0.502895 | 0.287891 | 0.446857 | N/A | 1.000000 |
| change=.1-.9 | M3 | 0.890708 | 0.089195 | 0.039392 | 51.812500 | 0.000000 |
| change=.1-.9 | M3_alpha20 | 0.895087 | 0.096416 | 0.081879 | 69.531250 | 0.000000 |
| change=.9-.1 | M0 | 0.795359 | N/A | N/A | N/A | N/A |
| change=.9-.1 | M1 | 0.500343 | 0.291243 | 0.450587 | N/A | 1.000000 |
| change=.9-.1 | M2 | 0.500342 | 0.291140 | 0.450478 | N/A | 1.000000 |
| change=.9-.1 | M3 | 0.097360 | 0.089318 | 0.037743 | 46.875000 | 0.000000 |
| change=.9-.1 | M3_alpha20 | 0.087402 | 0.096694 | 0.081472 | 62.281250 | 0.000000 |

Lifetime Beta means после 500 старых +500 новых observations остаются около .5.
M0 также использует lifetime counts: activation около .795 не оценивает новое p.
EWMA адаптируется. При критерии 20 consecutive estimates within ±.1 alpha=.2
может дать больший stream delay, чем .05, из-за большего шума. В конкуренции
alpha=.2 переключается быстрее. Единого победителя по всем свойствам нет.

## Competition: full-information и partial-feedback

Ranking/regret — last200, switches и maximum gap — за весь horizon.
Gap A/B в таблице — среднее per-seed maximum gap, не общий maximum.
В JSON есть также min/max и dispersion по seeds. M0_native совпадает с M0
во всех полных результатах и отдельно не дублируется в таблицах.

### full
| Pair | Model | Ranking last | Regret last | Switches | Gap A | Gap B |
| --- | --- | --- | --- | --- | --- | --- |
| pair=.5-.5 | M0 | N/A | 0.000000 | 9.500000 | 355.718750 | 452.562500 |
| pair=.5-.5 | M1 | N/A | 0.000000 | 15.250000 | 328.375000 | 453.375000 |
| pair=.5-.5 | M2 | N/A | 0.000000 | 15.250000 | 328.375000 | 453.375000 |
| pair=.5-.5 | M3 | N/A | 0.000000 | 91.875000 | 73.281250 | 78.718750 |
| pair=.5-.5 | M3_alpha20 | N/A | 0.000000 | 175.968750 | 30.250000 | 32.312500 |
| pair=.7-.6 | M0 | 1.000000 | 0.000000 | 2.812500 | 27.406250 | 952.625000 |
| pair=.7-.6 | M1 | 1.000000 | 0.000000 | 4.125000 | 21.437500 | 954.343750 |
| pair=.7-.6 | M2 | 1.000000 | 0.000000 | 4.125000 | 21.437500 | 954.343750 |
| pair=.7-.6 | M3 | 0.794219 | 0.020578 | 58.875000 | 35.625000 | 187.562500 |
| pair=.7-.6 | M3_alpha20 | 0.650938 | 0.034906 | 152.531250 | 23.531250 | 45.625000 |
| pair=.9-.1 | M0 | 1.000000 | 0.000000 | 0.062500 | 0.062500 | 999.906250 |
| pair=.9-.1 | M1 | 1.000000 | 0.000000 | 0.062500 | 0.031250 | 999.937500 |
| pair=.9-.1 | M2 | 1.000000 | 0.000000 | 0.062500 | 0.031250 | 999.937500 |
| pair=.9-.1 | M3 | 1.000000 | 0.000000 | 0.062500 | 0.031250 | 999.937500 |
| pair=.9-.1 | M3_alpha20 | 1.000000 | 0.000000 | 0.062500 | 0.031250 | 999.937500 |
| pair=1-0 | M0 | 1.000000 | 0.000000 | 0.000000 | 0.000000 | 1000.000000 |
| pair=1-0 | M1 | 1.000000 | 0.000000 | 0.000000 | 0.000000 | 1000.000000 |
| pair=1-0 | M2 | 1.000000 | 0.000000 | 0.000000 | 0.000000 | 1000.000000 |
| pair=1-0 | M3 | 1.000000 | 0.000000 | 0.000000 | 0.000000 | 1000.000000 |
| pair=1-0 | M3_alpha20 | 1.000000 | 0.000000 | 0.000000 | 0.000000 | 1000.000000 |
| pair=change | M0 | 0.016563 | 0.786750 | 0.500000 | 3.406250 | 996.406250 |
| pair=change | M1 | 0.022344 | 0.782125 | 0.656250 | 4.531250 | 995.312500 |
| pair=change | M2 | 0.022344 | 0.782125 | 0.656250 | 4.531250 | 995.312500 |
| pair=change | M3 | 1.000000 | 0.000000 | 1.187500 | 485.687500 | 514.093750 |
| pair=change | M3_alpha20 | 1.000000 | 0.000000 | 1.187500 | 496.218750 | 503.562500 |

### partial
| Pair | Model | Ranking last | Regret last | Switches | Gap A | Gap B |
| --- | --- | --- | --- | --- | --- | --- |
| pair=.5-.5 | M0 | N/A | 0.000000 | 6.000000 | 497.281250 | 496.812500 |
| pair=.5-.5 | M1 | N/A | 0.000000 | 2.187500 | 314.406250 | 670.343750 |
| pair=.5-.5 | M2 | N/A | 0.000000 | 2.687500 | 314.375000 | 664.312500 |
| pair=.5-.5 | M3 | N/A | 0.000000 | 21.156250 | 319.750000 | 305.156250 |
| pair=.5-.5 | M3_alpha20 | N/A | 0.000000 | 16.343750 | 340.093750 | 364.593750 |
| pair=.7-.6 | M0 | 0.562500 | 0.043750 | 5.562500 | 435.250000 | 559.281250 |
| pair=.7-.6 | M1 | 0.687500 | 0.031250 | 0.812500 | 312.156250 | 687.125000 |
| pair=.7-.6 | M2 | 0.718750 | 0.028125 | 0.906250 | 281.125000 | 718.062500 |
| pair=.7-.6 | M3 | 0.910469 | 0.008953 | 3.781250 | 103.750000 | 817.062500 |
| pair=.7-.6 | M3_alpha20 | 0.842656 | 0.015734 | 9.281250 | 186.218750 | 527.000000 |
| pair=.9-.1 | M0 | 1.000000 | 0.000000 | 4.500000 | 1.062500 | 994.406250 |
| pair=.9-.1 | M1 | 1.000000 | 0.000000 | 0.625000 | 0.468750 | 999.156250 |
| pair=.9-.1 | M2 | 1.000000 | 0.000000 | 0.625000 | 0.468750 | 999.156250 |
| pair=.9-.1 | M3 | 1.000000 | 0.000000 | 0.750000 | 0.437500 | 998.968750 |
| pair=.9-.1 | M3_alpha20 | 0.999531 | 0.000375 | 1.812500 | 1.031250 | 891.093750 |
| pair=1-0 | M0 | 1.000000 | 0.000000 | 4.000000 | 1.000000 | 994.000000 |
| pair=1-0 | M1 | 1.000000 | 0.000000 | 0.000000 | 0.000000 | 1000.000000 |
| pair=1-0 | M2 | 1.000000 | 0.000000 | 0.000000 | 0.000000 | 1000.000000 |
| pair=1-0 | M3 | 1.000000 | 0.000000 | 0.000000 | 0.000000 | 1000.000000 |
| pair=1-0 | M3_alpha20 | 1.000000 | 0.000000 | 0.000000 | 0.000000 | 1000.000000 |
| pair=change | M0 | 0.000000 | 0.800000 | 4.312500 | 1.000000 | 994.250000 |
| pair=change | M1 | 0.026719 | 0.778625 | 0.656250 | 5.468750 | 994.343750 |
| pair=change | M2 | 0.026719 | 0.778625 | 0.656250 | 5.468750 | 994.343750 |
| pair=change | M3 | 1.000000 | 0.000000 | 1.437500 | 485.437500 | 514.125000 |
| pair=change | M3_alpha20 | 0.999844 | 0.000125 | 2.812500 | 493.031250 | 442.031250 |

Competition change-point adaptation:
| Mode/model | Delay observed | Censored fraction | Uncensored seeds |
| --- | --- | --- | --- |
| full/M0 | N/A | 1.000000 | 0 |
| full/M1 | 479.000000 | 0.968750 | 1 |
| full/M2 | 479.000000 | 0.968750 | 1 |
| full/M3 | 14.312500 | 0.000000 | 32 |
| full/M3_alpha20 | 3.781250 | 0.000000 | 32 |
| partial/M0 | N/A | 1.000000 | 0 |
| partial/M1 | 475.500000 | 0.875000 | 4 |
| partial/M2 | 475.500000 | 0.875000 | 4 |
| partial/M3 | 14.562500 | 0.000000 | 32 |
| partial/M3_alpha20 | 5.281250 | 0.000000 | 32 |

## Интерпретация результатов

- При full-information .7/.6 M0/M1/M2 достигают last200 ranking=1.0;
  partial M0=.5625, M1=.6875, M2=.71875. Ограничение информации меняет вывод.
- Partial .7/.6: EWMA .05 ranking=.91046875, но в стационарном single-stream
  его Brier/ECE хуже lifetime Beta. Ranking и calibration не взаимозаменяемы.
- При .9/.1→.1/.9 partial M0 last200 ranking=0, regret=.8, adaptation censored
  32/32. M1/M2 тоже в основном не успевают; EWMA .05 ranking=1, mean observed
  ranking delay=14.5625, censored=0/32.
- В full change M1/M2 delay=479 относится только к 1/32 runs; нельзя выдавать
  его за среднюю успешную адаптацию всех seeds. Partial 475.5 относится к 4/32.
- Равные p=.5/.5 не порождают ranking errors: accuracy=N/A, regret=0.
  EWMA .2 full имеет в среднем 175.96875 switches против M0 9.5.
- В full даже gap=1000 не означает отсутствие evidence: обе записи обновляются.
  В partial это действительно feedback starvation выбранной политикой.
- В 1/0 partial M0 делает 4 switches из-за initial transient; Beta/EWMA — 0.
  Это не само по себе доказательство рациональности/нерациональности.
- При начальной ничьей всегда выбирается A; stationary presets ориентированы
  лучшим кандидатом A. Label counterbalancing не выполнен, поэтому нельзя
  обобщать ranking averages на симметричную популяцию задач. Change preset
  проверяет противоположное направление после t=500.
- Fixed-context i.i.d. synthetic Bernoulli не воспроизводит контекстные сдвиги,
  correlated observations, native eligibility loss, guard отказ или sensor bias.
  Seeds дают empirical dispersion, не доказательство универсальности.

Production implementation соответствует закрытому контракту. Первый HIT,
рост evidence score после MISS и path dependence — математические свойства,
не автоматически технические дефекты. Нормативное решение, какую величину
выбирать и сколько exploration допускать, остаётся открытым.

## Нужен ли shadow experiment

Есть основание для отдельного shadow comparison на одинаковом classifier-produced
feedback: измерить связь synthetic conclusions с реальными native HIT/MISS и
selection bias. До этого полезны mirrored A/B controls и отдельное разделение
контекстных подгрупп. Ни shadow, ни новые presets этого этапа не начаты.
Shadow не должен менять selection, thresholds, records или writer authority.
Одна и та же выбранная production trajectory не даёт counterfactual outcomes
невыбранных действий; это ограничение должно сохраняться в отчёте.
Production formula replacement пока не обоснована. Изменение confidence потребует
отдельного mapping/version/migration решения для persisted records, selection
thresholds, replay/readback fingerprints и RND-024/025 expectations.

## Воспроизведение

Из корня repository:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m scenarios.evidence_confidence_diagnostic_bench --preset full --output-dir /tmp/rnd026b-new-run
PYTHONDONTWRITEBYTECODE=1 python -B tools/verify_evidence_confidence_diagnostic_bench.py
```

Output directory должен быть новым dedicated child /tmp.
Проверка temporary-copy выявила и устранила first-pass confinement gap:
output теперь запрещён внутри текущего checkout даже при размещении checkout в /tmp. Existing directory,
symlink и checkout destination отвергаются, перезаписи нет. Error diagnostics
содержат только fixed prefix и exception type, не произвольные exception details.
При отказе вычисления результат не объявляется PASS. Внешние arbitrary Python
callbacks не поддерживаются как недоверенный security boundary; preemption нет.

Primary results: `/tmp/rnd026b-full/results.json`, compact `summary.json`.
Свежая validation copy: `/tmp/rnd026b-validation-final/RNDeM_Prototype`;
повторный full output: `/tmp/rnd026b-validation-final/full`.
Временные artifacts могут исчезнуть; этот документ хранит основные агрегаты,
а runner позволяет получить bins/per-seed results заново.

## Проверки и safety

Новый verifier: **29 unique unittest methods PASS** в checkout и temporary copy.
Покрыты oracle parity/calls, caps/rounding, order effects, Beta/std/EWMA,
Brier/ECE boundaries, N/A, ties/native eligibility/top-3, first-HIT switching,
pre-event prediction, guarded outcome access, unchanged unselected state,
common full-information inputs, monotonic event tokens, reproducible RNG/JSON,
budgets, adaptation/censoring, metrics/windows, output confinement, errors,
parity STOP и неизменность checkout inventory при тестировании.

Existing regression unique unittest methods:

| Suite | PASS |
|---|---:|
| nfp_native_feedback_apply | 11 |
| nfp_native_feedback_evaluation | 15 |
| nfp_native_feedback_replay_idempotency | 15 |
| nfp_expsm_operational_retrieval | 5 |
| persistent_nfp_expsm_representation | 10 |
| native_outcome_feedback_loop | 33 |
| native_competing_experience_selection | 40 |
| **Regression total** | **129** |
| **New + regression unique total** | **158** |

Отдельный existing `verify_scoring_selection_semantics.py`: PASS (8 semantic
checks), не прибавлен как unittest methods. Повторные verifier/full runs не
суммируются. Production parity gate и smoke runs тоже не прибавлены.

Полный output checkout/fresh-copy сопоставлен по SHA-256. Syntax compile
в памяти без bytecode и whitespace проверены. Все Python launches используют
PYTHONDONTWRITEBYTECODE=1 python -B, включая temporary copy.

Pre-edit inventory `/tmp/rnd026b-before.json`; final safety inventory
`/tmp/rnd026b-final-safety.json`. Все 616 существовавших файлов и directory
inventory сохранены; новые только три scope files. Все 12 Production Memory
SHA-256 и каталоги, weights, Stage 1/2, RND-021–025, 119 baseline .pyc и
root sf4.py неизменны. Новых service/lock/cache/manifest files нет.
Staging пуст; branch/HEAD прежние; commits/tags/remote отсутствуют.
Substrate baseline FAIL остаётся открытым, не исправлен и не объявлен PASS.

Scope:

- `scenarios/evidence_confidence_diagnostic_bench.py`;
- `tools/verify_evidence_confidence_diagnostic_bench.py`;
- `docs/RND-026_evidence_confidence_diagnostic_bench.md`.

**READY FOR ARCHITECTURE REVIEW. FIRST PASS. STOP FOR REVIEW.**


## Independent review — RND-026/C

2026-11-09. **ACCEPTED FOR CLOSURE** для диагностического этапа.
Review выполнен read-only, без изменения runner, verifier и production.
Documentation и PASS count не использовались как самостоятельное доказательство.

Независимо подтверждены:

- 4 960 trajectory steps M0 аналитическим расчётом, включая фактическое
  округление после каждого update и вход округлённого состояния в следующий;
- 2 688 окон pre-event Brier/ECE/posterior std;
- 360 окон ranking/regret/switching/starvation;
- 11 295 листовых агрегатов: mean, population std, min/max, valid/NA counts;
- общий deterministic external stream, pre-event predictions, отсутствие future
  leakage, чтений hidden outcomes и updates неизбранной записи в partial;
- caps, candidate ordering, stable top-3, native activation и selector thresholds;
- 12 отрицательных output cases, включая checkout под /tmp, existing destination,
  symlinks, traversal и resolved aliases; destination mutation при отказах нет;
- 29 новых +129 regression = **158 unique unittest PASS**; semantic scoring/
  selection PASS отдельно. Повторы checkout/fresh-copy не суммируются;
- полный fresh-copy rerun: results.json и summary.json побайтово совпали
  с обоими full outputs implementation pass; Python source совпал с tested copy.

M0 вызывает реальные `_updated_record` и `activate_native`; native comparison
использует existing `DecisionSelector.select_native`. Transient object.__new__
не читает production files и не получает mutation authority.
Initial acquired defaults h=m=0, c=r=.5 сохранены. Ни одна production formula
не менялась. Confidence/activation — эвристические scores, не calibrated
probabilities. Первый HIT снижает activation .775→.7568166667; repeatability
учитывает trial attempts, включая MISS; порядок HIT/MISS влияет на M0.

### Mirrored A/B probe

В review через публичный `run_pair` поменяны местами одновременно labels,
latent probability streams и соответствующие исходные outcome streams.
Tie-breaking остался A-first. Production и основной runner не менялись.
Ниже partial-feedback ranking accuracy последних 200 шагов, среднее по 32 seeds:

| Model | Original .7/.6 | Mirrored |
|---|---:|---:|
| M0 | .562500 | .593750 |
| Beta(1,1) | .687500 | .500000 |
| Beta(2,2) | .718750 | .500000 |
| EWMA .05 | .910469 | .935000 |
| EWMA .20 | .842656 | .824844 |

При зеркальном назначении labels преимущество Beta над M0 меняет знак.
A-first tie-breaking существенно влияет на результаты при ограниченном feedback.
Исходные результаты математически корректны для исходных presets, но их ranking
нельзя обобщать на симметричную популяцию задач. Это ограничение обязательно
учитывать в будущих experiments. Mirrored probe не является исчерпывающей
проверкой всех prior/tie-breaking/initialization policies.

Review artifacts (temporary, могут исчезнуть):
`/tmp/rnd026c-review/probes.log`, `mirror.json`, `output-probes.log`,
`final-safety.json`; fresh full output `/tmp/rnd026c-review/full`.
SHA-256 полного results.json:
`b4083df955f9a766a56a11a1f76a03786a7143bdd9ddce8872081ebb9d45e66f`.

## Final closure — CLOSED

2026-11-09. RND-026/A audit, RND-026/B diagnostic implementation и RND-026/C
independent review завершены. **ACCEPTED FOR CLOSURE.**

Исследованы M0 existing Stage 2, M1 Beta(1,1), M2 Beta(2,2) с posterior std,
M3 EWMA alpha=.05 и заранее заданная sensitivity alpha=.20.
В некоторых исследованных stationary условиях Beta имеет лучшие Brier/ECE;
EWMA быстрее адаптируется к заданным change points, но демонстрирует больший
шум и частоту переключений. Универсальный победитель не установлен.
Credible intervals/coverage остаются N/A; posterior std не подменяет интервал.

Full-information раскрывает observations обеих записей; partial-feedback —
только выбранной. Реальное native execution автоматически не даёт
counterfactual outcome неизбранного действия. Prediction зафиксирован до
reveal/update; deterministic generation и отсутствие future leakage подтверждены.

Partial reversal .9/.1→.1/.9:

- M0: 32/32 censored;
- M1/M2: 28/32 censored; mean delay 475.5 относится только к четырём
  успешным runs, а не ко всей группе;
- EWMA .05: 32/32 successful, mean ranking delay 14.5625;
- EWMA .20: 32/32 successful, mean ranking delay 5.28125.

Более быстрый ranking switch не означает лучшую calibrated probability estimate
или более полезное реальное motor action. Синтетический reliability regret
не является learned utility/reward.

**Mathematical simulation ≠ production formula oracle ≠ persisted Stage 2 replay ≠ genuine native world feedback.**
В RND-026 выполнены первые два уровня. Existing writer/native regression suites
проверяют сохранение прежних contracts, а не доказывают новый экспериментальный
native learning result.

Не доказаны улучшение реального native learning, превосходство одной модели во
всех условиях, готовность замены Stage 2 confidence, utility/reward learning,
устойчивое решение starvation или корректность priors для реального мира.
Future shadow comparison обоснован как исследовательская гипотеза, но не начат.
Production migration и изменение selection policy не разрешены этим closure.

Перед closure SHA-256 обоих Python files сверены с принятым review и tested
fresh copy: source неизменён, редактировалась только документация. Полная
регрессия повторно не запускалась без новой причины. Подтверждены прежние
**158 unique unittest PASS**, semantic scoring/selection PASS отдельно,
production parity, bounded execution, deterministic outputs и confinement.
Syntax compile в памяти, whitespace, git diff checks и точный staged scope
проверяются для финального документа и неизменённых Python sources.

Historical baseline `/tmp/rnd026b-before.json` доступен; все 616 прежних файлов
и directory inventory совпадают. Все 12 Production Memory files/SHA-256 и
каталоги, weights, Stage 1/2, RND-021–025 и 119 baseline ignored .pyc сохранены.
Root sf4.py неизменён, исключён из staging/commit; SHA-256:
`0e3190a815dd4e65ac768e586b04cd877d845c67e0641fdbddc7e232fbcec975`.
Новых service/lock/cache/manifest files нет. Substrate имеет только три
исторических runtime violators; baseline FAIL остаётся открытым.

Разрешён один локальный commit:
`test(learning): add evidence confidence diagnostic bench`, ровно три RND-026
paths из scope выше. Полный closure HEAD доступен в Git history.
Remote-операции, tags и дополнительные commits не выполняются.

**CLOSED. STOP после closure. Shadow experiment и RND-027 не начаты.**
