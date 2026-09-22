# Cross-Industry Anomaly Evaluation Pack

## Purpose

This evaluation pack tests the current anomaly detector against ten deterministic synthetic business datasets. It demonstrates expected detection, expected non-detection, and safe fallback behavior across different ecommerce and sales patterns.

These are not claims of validation on real customer data. They are controlled test cases with known expected results. Real-world validation and user feedback remain future work.

## Detector under evaluation

- Metrics: recognized sales, completed orders, and average order value.
- Baseline: rolling median and Median Absolute Deviation (MAD) of six prior complete months.
- Minimum history: six baseline months plus one current complete month.
- Alert threshold: 3.5 scaled robust deviations.
- Exclusions: incomplete latest periods and non-contiguous histories.
- Scope boundary: the detector identifies unusual movement, not cause or recommended action.

## Scenario matrix

| # | Industry | Pattern | Expected outcome |
|---|---|---|---|
| 1 | Grocery retail | Stable monthly sales | No findings |
| 2 | Fashion ecommerce | Campaign-driven sales spike | Sales and AOV anomalies |
| 3 | Electronics retail | Completed-order drop | Sales and order-count anomalies |
| 4 | Food delivery | Higher basket value | Sales and AOV anomalies |
| 5 | Subscription commerce | Gradual growth | No findings |
| 6 | Wholesale distribution | One unusually large contract | Sales and AOV anomalies |
| 7 | Professional services | Unusually low sales month | Sales and AOV anomalies |
| 8 | Beauty and cosmetics | Missing historical month | Unavailable: non-contiguous history |
| 9 | Logistics services | Incomplete current month | Unavailable: latest period excluded and insufficient history |
| 10 | Pharmacy retail | Refund-only adjustment | No findings; refund detection is not built yet |

## How to run

```bash
python3 -m pytest -q tests/test_cross_industry_anomaly_evaluation.py
```

## What this proves

- The detector can distinguish stable or gradual movement from strong outliers.
- It can identify whether sales, order count, or average order value is unusual.
- It does not silently fill missing periods with zero sales.
- It provides unavailable states when the historical baseline is unreliable.
- Its current scope is explicit: refund-only anomalies require a future dedicated refund diagnostic.

## Remaining evaluation gaps

- Real anonymized datasets from businesses in several industries.
- Seasonal patterns spanning multiple years.
- Feedback-labelled false positives and missed anomalies.
- Evaluation of category, refund, cancellation, and regional anomaly rules.
- Production monitoring for alert volume, latency, and user feedback.
