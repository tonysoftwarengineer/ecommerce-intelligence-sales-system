# Product-Demand Locked Evaluation

## Scope

This report records the first Milestone 11B-4 locked evaluation of the frozen
limited-preview product-demand policy. It uses 48 M5 item-store series that were
excluded from the 24-product development cohort and withholds each selected
series' final thirteen complete weeks.

This is a **within-source locked holdout**, not an independent-business or live
prospective evaluation. It can challenge the existing policy, but it cannot by
itself approve decision-ready forecasting.

## Reproduction

```bash
python3 -m scripts.evaluate_product_demand_locked_holdout \
  --m5-sales data/public/m5_sales_train_evaluation.csv \
  --m5-calendar data/public/m5_calendar.csv \
  --output data/public/product_demand_locked_evaluation.json
```

The protocol was documented in
`docs/MILESTONE_11B_4_LOCKED_PRODUCT_DEMAND_EVALUATION.md` before scores were
viewed. The complete generated JSON remains in the git-ignored `data/public`
directory.

## Lock integrity

- Development seed: `milestone-11b-public-v1`.
- Locked seed: `milestone-11b-locked-v1`.
- Development cohort: 24 products, six per demand stratum.
- Locked cohort: 48 products, twelve per demand stratum.
- Development/locked overlap: **0 products**.
- Holdout: 13 weekly forecast opportunities per product.
- Forecast opportunities: **624**.
- Skipped locked products: **0**.
- Source hashes matched the previously recorded M5 files.

## Results

| Scope | Preview coverage | Skill vs zero | WAPE | Gate interpretation |
|---|---:|---:|---:|---|
| Overall | 83.3% | 72.8% | 27.2% | Positive overall, but strata must be checked |
| Delayed start | 100.0% | 71.2% | 28.8% | Passed |
| Dense | 100.0% | 76.2% | 23.8% | Passed |
| Intermittent | 100.0% | 52.7% | 47.3% | Passed |
| Sparse | 33.3% | 0.0% | 100.0% | Failed |

The policy showed 520 previews and abstained from 104 opportunities. All 104
abstentions were sparse products whose historical method did not beat zero.
However, the sparse forecasts that did pass the historical gate produced the
same mean absolute error as forecasting zero on the locked future weeks.

Across shown forecasts, overforecast and underforecast error were similar:
1,334.74 units overforecast and 1,346.46 units underforecast. Reporting these
separately prevents a near-zero signed bias from hiding operationally meaningful
errors in both directions.

## Gate result: Failed

The predeclared gate required shown forecasts to beat zero overall and in every
demand stratum that produced forecasts. Sparse demand tied zero, so the gate
failed. Supported weekly use remains **unapproved**, and the dashboard must keep
its existing **Preview — not decision-ready** language.

## Interpretation

1. The trust policy is directionally useful: it rejected two-thirds of sparse
   forecast opportunities and retained strong locked skill in the other three
   strata.
2. The historical positive-skill rule is not sufficient for sparse products;
   some past winners did not add value on untouched future weeks.
3. Aggregate performance alone would have hidden this failure because dense
   demand dominates unit totals. Stratum-level gating was necessary.
4. The locked cohort must now remain evaluation-only. It must not be used to
   tune a replacement threshold and then be presented again as untouched proof.

## Next decision

Use development and scenario data—not this locked cohort—to compare bounded
sparse-demand policy options. Likely candidates are a stronger stability guard,
explicit sparse-product abstention, and guarded category fallback. Record the
choice in a new ADR, then evaluate it on a new untouched cohort or a genuinely
independent dataset.

Prediction-interval calibration, business-specific waste-versus-stockout costs,
category-fallback validation, and independent-business data remain separate
release requirements.

## Verification

- The locked report was generated twice; all evidence except runtime measurements
  matched exactly.
- 317 non-integration backend tests passed; 4 integration tests were deselected.
- Ruff lint and formatting, mypy, and git diff checks passed.
- The first complete locked run took 55.9 seconds locally, including loading and
  preparing the two disjoint cohorts.
