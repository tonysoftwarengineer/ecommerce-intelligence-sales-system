# Product-Demand Synthetic Scenario Evaluation

## Scope

This report records deterministic synthetic evidence for Milestone 11B-1. It
tests forecasting behavior, safety boundaries, unavailable states, and evaluation
fairness. It is not validation on real businesses and does not establish
production trust thresholds.

Run the reproducible report with:

```bash
python3 -m scripts.evaluate_product_demand_scenarios
```

Run the scenario assertions with:

```bash
python3 -m pytest -q tests/test_product_demand_scenario_pack.py
```

## Result Summary

- Scenarios: 12
- Declared expectations passed: 12
- Declared expectations failed: 0
- Products isolated correctly: one intentionally invalid product did not block
  its valid sibling
- Local scenario-pack runtime snapshot: 34.432 ms
- Selection label: `evaluation_only` for every generated report

The runtime is a development-machine observation, not a latency SLO.

## Scenario Matrix

| # | Scenario | Expected evidence | Result |
|---|---|---|---|
| 1 | Stable daily level | All baselines evaluate; simple stable methods may win | Passed; latest-value daily and last-week-total weekly |
| 2 | Strong weekday seasonality | Seasonal naive 7 should reproduce the daily pattern | Passed; seasonal-naive-7 daily |
| 3 | Recent upward level shift | Record adaptation errors without forcing a declared winner | Passed; complete exploratory evidence retained |
| 4 | Intermittent confirmed-zero demand | Confirmed zeroes remain real targets; weekly occurrence is learnable | Passed; seasonal-naive-7 daily |
| 5 | All-zero active product | Zero benchmark is visible but cannot become the winner | Passed; non-benchmark winner selected |
| 6 | Short history | No forced forecast or leaderboard | Passed; unavailable with `short_history` |
| 7 | Unknown internal gap | Unknown date is not converted to zero | Passed; `unknown_target_gap` retained |
| 8 | Stockout-censored period | Censored date restricts affected folds/candidates | Passed; five candidates evaluated and `censored_target` retained |
| 9 | Unconfirmed active period | Closure/activity ambiguity remains explicit | Passed; `product_activity_unconfirmed` retained |
| 10 | Invalid product beside valid product | Negative target is isolated to its product | Passed; invalid product rejected, valid product evaluated |
| 11 | Nonzero-day-average inflation | Demonstrate why nonzero-day means cannot fill missing days | Passed; implied 42 units versus observed 18, an inflation of 24 |
| 12 | Equal MAE with opposite bias | Equal overall error must not hide direction | Passed; latest-value bias +6 and moving-average-7 bias -6 |

Expected winners are asserted only for mathematically unambiguous patterns. The
level-shift scenario deliberately checks evidence and availability without
declaring one permanent winner.

## Important Findings

1. The evaluation architecture distinguishes a real zero from missing, closed,
   or stockout-censored demand.
2. Per-product isolation works: invalid demand for one product does not erase
   valid sibling-product evidence.
3. A nonzero-day average can materially inflate weekly demand. In the controlled
   case, its implied weekly total was 42 units while the observed weekly total
   was 18.
4. MAE alone can hide operational direction. Two methods both produced MAE 6,
   while one overforecast by 6 units per day and the other underforecast by 6.
5. The wider scenario pack exposed a Decimal precision edge case in bias
   accounting. Bias is now derived from audited overforecast minus underforecast
   totals, preserving the accounting identity exactly.

## What This Does Not Prove

- It does not prove accuracy on a real retailer's product catalogue.
- It does not define universal minimum-history, accuracy, or trust thresholds.
- It does not evaluate weather, holidays, promotions, price changes, stock
  recommendations, or external ML models.
- The Step 9 rerun now includes fixed-parameter SBA/Croston as a weekly-total
  candidate. All twelve scenario expectations still pass. This does not prove
  that SBA/Croston is universally suitable for intermittent demand.
- It does not make any forecast available in the API or dashboard.

The next evidence layer is Step 6: documented UCI Online Retail II and M5 sample
evaluations using dataset-specific adapters outside the domain forecasting code.
