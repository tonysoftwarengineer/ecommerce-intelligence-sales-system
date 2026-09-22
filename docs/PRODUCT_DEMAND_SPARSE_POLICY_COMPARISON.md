# Sparse-policy development comparison

**Date:** 2026-09-15  
**Status:** Scored development experiment; no live approval rule changed

## Plain-English finding

On this small development cohort, requiring consistent historical performance
and simply withholding sparse-product previews produced the same outcome.
Neither candidate proved that sparse forecasting became more accurate: both
withheld every sparse forecast. All eighteen non-sparse products retained their
existing previews.

The comparison protocol was recorded in
[the experiment plan](PRODUCT_DEMAND_SPARSE_POLICY_COMPARISON_PLAN.md) before
scoring. It reuses the existing 24 development products, six flagged sparse
using training history only. Their final 13 weeks are development-validation
weeks, **not untouched release evidence**. No previously locked products were
scored, and source hashes matched the original development sources.

## Results

| Policy | Products with previews | Shown weekly opportunities | Sparse weekly previews | Overall shown-week WAPE |
|---|---:|---:|---:|---:|
| Current historical gate | 19/24 | 247/312 (79.2%) | 13/78 | 44.09% |
| Additional three-block consistency | 18/24 | 234/312 (75.0%) | 0/78 | 43.97% |
| Explicit training-sparse abstention | 18/24 | 234/312 (75.0%) | 0/78 | 43.97% |

The existing gate already withheld five of the six sparse products. Both
candidates removed the remaining one's thirteen forecasts. No control forecasts
were removed from non-sparse products. The aggregate WAPE difference is tiny and
scores a changed population; it is not evidence that either method's predictions
improved on the same products.

### The removed item, concretely

M5 item-store `FOODS_2_068_TX_2_evaluation` had about 11.0% historical skill
versus zero in its pre-validation training history. Its selected method was the
mean of the previous four weekly totals.

Across the subsequent thirteen development-validation weeks:

- Actual sales totalled **2 units**.
- The method's absolute errors totalled **4 units**, including 2.25 units of
  overforecast error and 1.75 units of underforecast error.
- Predicting zero would have had **2 units** of absolute error.
- Therefore shown sparse WAPE was **200%**, and skill versus zero was **-100%**.

In the three recent historical consistency blocks, selected/zero absolute
errors were 1.25/0, 7.75/8, and 5.75/3. Only one block added value. The stricter
candidate therefore withheld this item without using its future outcomes.

This is a real public-retail item, not a claim about a particular restaurant.
Think of a special cake sold only occasionally: approval based on its entire
past can miss that its recent advantage is inconsistent.

## Trade-off and interpretation

The consistency rule has a potential advantage: it could retain a genuinely
consistent sparse product. This cohort contains no example proving that benefit.
It also adds exploratory parameters and needs 39 shared historical weeks for
its extra check. Explicit sparse abstention is simpler but cannot retain any
sparse product, even one that might be useful in a different business.

**Working recommendation:** explicit sparse abstention is the simpler candidate
to take to a new validation protocol. It is not accepted or implemented here.
The exploratory 10% positive-day cutoff is not a validated production threshold.
The owner must review the trade-off and approve any proposed live change.

### Category fallback

Category fallback is **not accuracy-compared** here. A sampled M5 department
does not establish complete category membership, and different stores must not
silently become one business. Existing CSV/regression scenarios verify passing
fallback behavior and its confirmation gate, but that is not independent proof
of category accuracy. Keep ADR-011 unchanged and category forecasts preview-only.

## Verification and next step

- Fifteen new unit checks cover consistency arithmetic, training-only flags,
  unchanged weekly model selection, no gate bypass, temporal isolation, and
  undefined accuracy when no forecasts are shown.
- Fifty-two focused tests passed, including existing trust, locked-evaluation,
  ten-CSV, and category tests. Ruff lint/format and mypy passed for the evaluator.
- Live API, model formulas, dashboard behavior, ADR-010, and ADR-011 are unchanged.
- Two complete runs produced exactly identical JSON evidence (SHA-256
  `997497dc9158e984e80be8839f56dd84a00868471f7de86f7c7ad07f385e2c2a`).
- Full reproducible evidence is in the git-ignored
  `data/public/product_demand_sparse_policy_comparison.json`.

Reproduce from the repository root:

```bash
python3 -m scripts.compare_product_demand_sparse_policies
```

Next: owner reviews [proposed ADR-012](architecture/ADR-012-sparse-demand-policy-review.md).
Only an accepted decision authorizes a live implementation. A future fresh
evaluation must report coverage as well as accuracy; withholding all sparse
forecasts is an abstention outcome, not a successful sparse-accuracy result.
