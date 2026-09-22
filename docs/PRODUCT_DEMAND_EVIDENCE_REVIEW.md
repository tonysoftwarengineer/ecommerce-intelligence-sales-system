# Product-Demand Evidence Review

## Scope

This report reviews Milestone 11B-1 scenario, UCI, and M5 evidence before any
trust threshold or user-facing product-demand forecast is accepted. It does not
change model results and does not add an API or dashboard forecast.

Reproduce the local JSON evidence with:

```bash
python3 -m scripts.review_product_demand_public_evidence \
  --uci-workbook data/public/online_retail_II.xlsx \
  --m5-sales data/public/m5_sales_train_evaluation.csv \
  --m5-calendar data/public/m5_calendar.csv \
  --output data/public/product_demand_evidence_review.json
```

## Review Questions

1. Does the selected method beat meaningful simple benchmarks?
2. Are poor products hidden by aggregate medians?
3. Is bias small relative to average observed demand?
4. Does the winning method remain stable across early and recent history?
5. Do daily values contain day-specific shape, or only repeat a flat average?
6. Does daily detail improve or damage the seven-day-total decision?
7. Is the current three-fold evaluation minimum supported as production policy?

## Main Evidence

| Evidence | UCI | M5 |
|---|---:|---:|
| Reviewed products | 14 | 24 |
| Shared historical folds per product | 93-101 | 57-273 |
| Daily RMSSE below 1 | 8/14 | 16/24 |
| Daily RMSSE above 1 | 6/14 | 8/24 |
| Same daily winner in early and recent history | 9/14 | 9/24 |
| Selected daily winner ever varied within a week | 0/14 | 0/24 |
| Daily total error equal to weekly method | 3/14 | 15/24 |
| Weekly method lower total error | 11/14 | 9/24 |
| Same weekly winner in early and recent history | 4/14 | 15/24 |
| Weekly method worse than or equal to zero | 0/14 | 5/24 |

### Daily granularity

All 38 public-data daily winners were moving-average methods. They repeated one
flat value across the seven forecast dates; none produced a changing within-week
shape. After adding SBA/Croston, the daily method's seven-day-total error matched
the weekly winner for 18 of 38 products and the weekly winner was better for the
other 20.

Daily RMSSE was above 1 for 14 of 38 products. Only 18 of 38 products retained
the same best daily method between the first and second halves of their history.
Therefore, the current engine has evidence for a seven-day level, but it has not
earned day-specific user-facing precision.

### Weekly evidence

UCI weekly forecasts were materially better than zero for all 14 evaluated
products. After adding SBA/Croston, median skill versus zero was 56.0%, but
weekly winners were stable across early and recent history for only 4 products.
Median absolute weekly bias was 3.88% of mean actual weekly demand.

Across the full M5 sample, median weekly skill versus zero was 44.2%, but the
aggregate hid a serious sparse-demand failure:

- five of six sparse products were worse than zero on seven-day-total MAE;
- sparse median skill versus zero was -29.9%;
- zero tied for the lowest weekly error in a median 98.3% of sparse historical
  weeks; and
- the currently selected method could beat last-week-total while still losing
  to zero.

This proves that one benchmark is insufficient and that the zero benchmark must
participate in weekly skill gating even though it cannot automatically become a
user-facing forecast.

The accepted ADR-009 extension now applies that rule explicitly on identical
historical weeks:

| Weekly zero-skill gate | Passed | Failed |
|---|---:|---:|
| UCI | 14 | 0 |
| M5 | 19 | 5 |

A pass means only that the selected method added value over forecasting zero. It
does not yet mean the forecast is supported or decision-ready. A failure blocks
a numeric forecast for that product. Product-level results are retained in the
reproducible JSON report.

### SBA/Croston extension

The accepted intermittent-demand candidate uses fixed smoothing 0.1, separates
positive demand sizes from the intervals between them, applies the SBA 0.95 bias
correction, and returns only a seven-day total. Its parameters were not tuned to
the UCI or M5 results.

SBA/Croston became the weekly winner for 11 of 14 UCI products and 8 of 24 M5
products. It improved total-error evidence, but it did not rescue any of the five
M5 zero-gate failures. For one sparse failure it improved skill versus zero from
-23.3% to -18.9%; the result remained negative and therefore remained blocked.

The extension also exposed a trade-off: UCI weekly subperiod stability fell from
12 to 4 products and absolute weekly bias increased even while total error
improved. This is why lower average error alone cannot authorize production use.

### Daily-shape comparison

Step 10 held each selected weekly total constant and compared two ways of
allocating that same total across seven dates:

- an equal one-seventh allocation; and
- the proportions implied by the date-varying seasonal-naive candidate.

Both allocations preserve the exact weekly total, so this experiment isolates
whether the daily pattern adds value instead of rewarding a method for changing
the weekly level.

| Lowest-error daily shape versus flat | UCI | M5 |
|---|---:|---:|
| Better | 0/14 | 4/24 |
| Worse | 14/14 | 20/24 |
| Positive skill in both history halves | 0/14 | 2/24 |

UCI median daily-shape skill versus flat was -7.92%, with every reviewed product
worse than equal allocation. M5 median skill was -18.70%; only four products
were better overall and only two stayed positive in both the earlier and later
halves of history. One of those two improvements was negligible, while the
other was 4.25% overall.

The experiment therefore does not approve date-specific forecasts. It supports
the existing decision to keep the seven-day total as the candidate user-facing
granularity and to label any daily planning rate as an average rather than a
prediction for each date.

### Bias

After SBA/Croston selection, UCI median absolute weekly bias was 3.88% of mean
actual demand, with a maximum of 8.91%. M5 median was 1.72%, with a maximum of
12.62%. Bias remains directionally reported; no waste-versus-stockout cost
weight is invented.

### Minimum history

Step 11 tested method selection with 3, 6, 13, and 26 completed weekly folds.
Every checkpoint was evaluated on the same later 13-fold holdout, so differences
were not caused by judging one checkpoint during an easier period than another.

| Selection folds | UCI passed zero gate | M5 passed zero gate | UCI median holdout skill | M5 median holdout skill |
|---:|---:|---:|---:|---:|
| 3 | 14/14 | 19/24 | 60.66% | 27.08% |
| 6 | 14/14 | 17/24 | 60.66% | 21.17% |
| 13 | 14/14 | 18/24 | 59.81% | 17.05% |
| 26 | 14/14 | 17/24 | 62.43% | 17.05% |

More folds did not produce monotonic improvement. UCI high-transaction products
remained strong at every checkpoint, while only one or two of the six sparse M5
products passed depending on checkpoint. Sparse median holdout skill remained
negative, from -26.64% to -33.77%.

Therefore, completed-fold count alone cannot be a production trust rule. The
experiment rejects both the current three-fold minimum and a blanket six-month
rule as sufficient evidence of reliability. The final policy must combine a
minimum evidence floor with out-of-sample skill and product-pattern safeguards.

## Interpretation

The review supports three conclusions:

1. Do not show per-date demand forecasts yet. A flat repeated average would look
   more precise than the evidence permits.
2. Do not enable one universal weekly policy. Dense, intermittent, and UCI
   high-activity products have useful weekly evidence, while the current sparse
   methods fail the zero benchmark for most sampled products.
3. Complete the final 11B-1 threshold review before 11B-2. The zero-skill gate,
   intermittent-demand candidate, daily-shape comparison, and history-length
   sensitivity experiment are now implemented.

## External Guidance

- Rolling-origin evaluation is retained because each test window must use only
  earlier observations: https://otexts.com/fpp3/tscv.html
- Scale-free errors and benchmark-relative skill are preferable when comparing
  different series, but require sufficiently large test evidence:
  https://otexts.com/fpp3/distaccuracy.html
- The M5 findings show that simple methods remain competitive, combinations can
  improve accuracy, and intermittent-demand results vary across aggregation
  levels: https://doi.org/10.1016/j.ijforecast.2021.11.013

These references support the evaluation principles. They do not provide a
universal minimum-fold or trust threshold, so none is presented as a standard.

## Gate Result

The Step 7 evidence review is complete and ADR-009 Option B is accepted. The
weekly zero-skill gate, SBA/Croston evaluation, and daily-shape comparison are
implemented, and history-length sensitivity is complete. Milestone 11B-2 is
still **not approved**. ADR-010 now proposes an evidence-gated, preview-only
release policy: safe semantics, a fair weekly winner, at least 13 shared folds,
and strictly positive skill against zero. Supported weekly and date-specific
forecasts remain unapproved. The project owner must accept or revise that policy
before implementation.
