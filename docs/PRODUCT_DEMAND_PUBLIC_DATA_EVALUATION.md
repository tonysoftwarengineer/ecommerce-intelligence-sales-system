# Product-Demand Public-Data Evaluation

## Scope

This report records Milestone 11B-1 Step 6 evidence from two public datasets. It
runs the unchanged seven-day rolling-origin engine and transparent baseline
methods developed in Steps 1-5. Dataset-specific adapters are kept outside the
forecast formulas.

The results remain `evaluation_only`. They do not establish production trust
thresholds, prove future business performance, or add forecasts to the API or
dashboard.

## Reproduction

The raw datasets are re-downloadable and remain in the git-ignored `data/`
directory. Generate the local JSON report with:

```bash
python3 -m scripts.evaluate_product_demand_public_data \
  --uci-workbook data/public/online_retail_II.xlsx \
  --m5-sales data/public/m5_sales_train_evaluation.csv \
  --m5-calendar data/public/m5_calendar.csv \
  --output data/public/product_demand_public_evaluation.json
```

Run the adapter and evidence tests with:

```bash
python3 -m pytest -q tests/test_product_demand_public_data_evaluation.py
```

### Source identity

| Source | Local bytes | SHA-256 |
|---|---:|---|
| UCI Online Retail II workbook | 45,622,278 | `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980` |
| M5 `sales_train_evaluation.csv` | 121,736,518 | `4b4a47c44c38380d2a9168216fea8c9ff2f31b1ddb772f8a0995952a038b8aa0` |
| M5 `calendar.csv` | 103,448 | `d12b5914ef03e66649adf5dd9e996e6602251c22b7a6af8f1f7e3aa12f8860f5` |

- UCI citation: https://doi.org/10.24432/C5CG6D
- M5 archive: https://doi.org/10.5281/zenodo.10203108
- Official M5 competition description:
  https://www.kaggle.com/competitions/m5-forecasting-accuracy/data

## Adaptation Decisions

### UCI Online Retail II

- The source contains 1,067,371 transaction rows and 5,304 nonblank product
  codes.
- The 25 products with the highest transaction-row counts are selected with a
  deterministic product-code tie-break.
- `StockCode` is the source identity and the unit is labelled `source_item`; no
  stocking conversion is inferred.
- Invoice identifiers beginning with `C` are treated as pre-fulfilment
  cancellations, following the dataset documentation.
- Ambiguous negative quantities outside those cancellation rows are not repaired.
  Products containing them remain unavailable.
- The strict safety view keeps absent dates as `missing_unknown`. A separate,
  explicitly research-only view assumes the workbook is a complete transaction
  ledger and treats absent product rows inside each observed product window as
  confirmed zero sales. Only that labelled view is evaluated.

This two-view design prevents an accuracy experiment from silently weakening the
production completeness rules.

### M5

- The source contains 30,490 item-store series and 1,941 explicit daily columns.
- The adapter deterministically samples six series from each of four descriptive
  groups: delayed start, sparse, intermittent, and dense, for 24 products total.
- The 10% and 50% nonzero-day boundaries organize this test sample only; they are
  not trust thresholds.
- Zeros before a product's first positive sale are trimmed because they do not
  prove the product was active. Explicit zeros after first sale are retained as
  confirmed zero observed sales.
- M5 item-store unit sales are evaluated as observed fulfilled sales. They do not
  reveal latent demand lost to stockouts.

## Coverage Results

| Evidence | UCI | M5 |
|---|---:|---:|
| Source products/series | 5,304 | 30,490 |
| Selected products | 25 | 24 |
| Prepared and evaluated products | 14 | 24 |
| Products with daily evidence | 14 | 24 |
| Products with seven-day-total evidence | 14 | 24 |
| Selected daily method beat zero benchmark | 14 | 24 |

UCI excluded 11 of the 25 selected products because their quantity semantics
were not safe. Across the full workbook, 22,950 rows had negative quantities;
3,457 of those did not use the documented cancellation prefix. The strict sample
calendar retained 2,174 absent product dates as unknown. The 14 evaluable
research-view products remain limited because UCI does not prove stockout
completeness.

M5 contained 13,435 delayed-start series, 1,186 sparse series, 9,943 intermittent
series, and 5,926 dense series under the sample-only grouping rules. The adapter
trimmed 6,040 pre-first-sale zero days across the selected 24 products. No sampled
series was all-zero.

## Method Results

| Result | UCI | M5 |
|---|---:|---:|
| Moving-average-28 daily wins | 13/14 | 23/24 |
| Moving-average-7 daily wins | 1/14 | 1/24 |
| Mean-of-4-weekly-totals wins | 13/14 | 22/24 |
| Last-week-total wins | 1/14 | 2/24 |

The zero benchmark ranked first for none of the prepared products, and the
selected non-benchmark daily method beat it for all 38 evaluated products. This
comparison is made on the same historical folds used by each product's daily
leaderboard.

### Metric distributions

| Dataset and method | Median | P90 |
|---|---:|---:|
| UCI moving-average-28 daily MAE | 38.321 source items/day | 72.727 |
| UCI moving-average-28 RMSSE | 0.913 | 1.605 |
| UCI mean-of-4-weekly-totals absolute 7-day error | 137.974 source items | 241.985 |
| M5 moving-average-28 daily MAE | 0.658 items/day | 2.187 |
| M5 moving-average-28 RMSSE | 0.810 | 1.394 |
| M5 mean-of-4-weekly-totals absolute 7-day error | 2.195 items | 8.529 |

Raw unit errors are not comparable between UCI and M5 because the products and
scales differ. RMSSE is scale-independent, but a good median does not mean every
product is reliable: both datasets have P90 RMSSE above 1 for the 28-day moving
average.

## What Clean Scenarios Did Not Show

1. Real transaction files can make lifecycle semantics the main blocker. UCI
   removed 11 high-activity products before model comparison because negative
   rows were ambiguous.
2. Completeness is an evidence decision, not a CSV-shape decision. UCI cannot be
   evaluated as a regular zero-filled calendar without a labelled research
   assumption.
3. Product starts are common. M5 demonstrates why thousands of pre-launch zeros
   must not be interpreted as active zero demand.
4. A simple smoother is highly competitive in these samples. That is useful
   baseline evidence, but it is not enough to hard-code moving-average-28 for all
   products or industries.
5. Aggregate medians hide difficult products. Step 7 must review tails,
   directional errors, method stability, coverage, and the daily-versus-weekly
   decision before proposing user-facing policy.

## Runtime Snapshot

One local development run recorded:

- UCI preparation: 50.845 seconds
- UCI evaluation: 2.126 seconds
- M5 preparation: 6.915 seconds
- M5 evaluation: 19.077 seconds
- Total before JSON serialization: 78.964 seconds

These values include public-file loading and are development observations, not a
production SLO.

## Conclusion and Next Gate

Step 6 is complete. The same evaluator ran successfully across controlled
scenarios, a transaction workbook with ambiguous lifecycle rows, and a complete
daily item-store matrix with sparse and delayed-start products.

The next step is the Milestone 11B-1 Step 7 review gate. That review may propose
trust, coverage, and daily-versus-weekly rules, but it must not retroactively tune
Step 6 or add a dashboard forecast without a separately accepted 11B-2 decision.
