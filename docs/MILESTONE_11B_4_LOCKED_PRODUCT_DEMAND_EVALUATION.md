# Milestone 11B-4: Locked Product-Demand Evaluation

**Protocol status:** Scored without changing the frozen policy  
**Release status:** Evaluation-only; supported weekly use remains unapproved  
**Lock date:** 2026-09-11

## Question

When the frozen preview policy is applied to products and future weeks that did
not participate in policy design, do the forecasts it chooses to show still add
value over forecasting zero?

## What is locked

- Dataset source: M5 `sales_train_evaluation.csv` and `calendar.csv`, identified
  by the source hashes already recorded in the public-data evaluation.
- Development cohort: six products per demand stratum selected with seed
  `milestone-11b-public-v1`.
- Locked cohort: twelve different products per demand stratum selected with seed
  `milestone-11b-locked-v1` after excluding every development-cohort ID.
- Demand strata: delayed start, sparse, intermittent, and dense.
- Holdout: the final thirteen complete seven-day windows of each selected
  product series.
- Forecast policy: the unchanged ADR-010 minimum of thirteen shared historical
  folds and strictly positive skill against the zero benchmark.
- Forecast horizon and target: one seven-day fulfilled-unit total.

No baseline formula, model-selection rule, trust threshold, sample seed, cohort
size, or success criterion may be changed after the locked results are viewed.
Any later change creates a new protocol version and a new untouched cohort.

## Prospective simulation

For each locked product and each holdout week:

1. expose only observations available before that week;
2. before the first holdout week, run the unchanged rolling-origin candidate
   evaluation and trust policy once, then freeze the selected method or
   abstention for the complete holdout;
3. retain either the limited-preview forecast or the policy abstention;
4. reveal and score the next seven-day actual total; and
5. add that completed week to the selected method's input before simulating the
   following week, without rerunning model selection.

This permits the deployed method to update from newly observed history while
preventing holdout outcomes from changing the selected method or entering an
earlier prediction.

## Predeclared evidence

- Product and forecast-opportunity counts.
- Preview coverage and abstention rates.
- Method-selection counts.
- MAE, WAPE, and skill versus zero on the exact opportunities where a preview
  was shown.
- Overforecast and underforecast units and counts reported separately.
- The same evidence split by demand stratum.
- Policy-reason counts for abstentions.

The within-source gate passes only when shown forecasts beat zero overall and in
every stratum that produced a forecast. A stratum with no shown forecasts makes
the gate inconclusive rather than successful. Coverage has no invented pass
threshold because safe abstention is an intended policy behavior.

## Result

The locked gate **failed**. Overall shown-forecast skill versus zero was positive,
but sparse-demand skill was exactly zero on the held-out weeks. The frozen
preview policy and release wording were not changed after this result. See
`docs/PRODUCT_DEMAND_LOCKED_EVALUATION.md` for the evidence and next decision.

## Important limitation

This is a locked, disjoint-product and future-time holdout inside M5. It is
stronger than the development backtest, but it is not a new business, a new
industry, or prospective production evidence. Even a pass cannot authorize
`supported_weekly`. Prediction-interval calibration, business-informed
waste-versus-stockout costs, and external or prospective validation remain
separate requirements.

## Verification plan

- Unit-test disjoint cohort selection.
- Unit-test temporal leakage resistance.
- Unit-test preview, abstention, directional-error, and gate aggregation.
- Produce one reproducible JSON report from the locally hashed public files.
- Record results without modifying the frozen forecasting policy.
