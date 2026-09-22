# Ten-CSV product-demand test pack

Seeded synthetic CSV/API behavior checks; not real-business accuracy validation or production approval.

Run: `python3 -m scripts.evaluate_product_demand_csv_pack`

## Manual mapping

Choose **Row total**, map same-named columns, currency NGN, date format %Y-%m-%d.
Map Completed to completed sale; Cancelled to excluded. No discount calculation.
Map product_category only in file 04. Product IDs and unit_of_measure are provided:
do not confirm unique names or set a default unit. Latest month completeness is declared
for these synthetic fixtures only. In a real export, the business must confirm it.

## Demand confirmations

Check export coverage and stockout tracking for every file EXCEPT:
file 07: leave export coverage unchecked; file 08: leave stockout tracking unchecked.
File 04: additionally confirm category mappings. No planned closures are declared.
These confirmations are fixture facts, not instructions to guess for real business data.

## Expected and observed outcomes

| CSV | Expected product/category previews | Invalid rows | Checks |
|---|---:|---:|---|
| 01_noisy_weekday_retail.csv | 1/0 | 0 | PASS |
| 02_growing_demand.csv | 1/0 | 0 | PASS |
| 03_intermittent_and_cancellations.csv | 1/0 | 0 | PASS |
| 04_category_fallback.csv | 0/1 | 0 | PASS |
| 05_mixed_products.csv | 1/0 | 0 | PASS |
| 06_short_history.csv | 0/0 | 0 | PASS |
| 07_unknown_missing_days.csv | 0/0 | 0 | PASS |
| 08_unrecorded_stockouts.csv | 0/0 | 0 | PASS |
| 09_conflicting_units.csv | 0/0 | 0 | PASS |
| 10_many_invalid_rows.csv | 0/0 | 90 | PASS |

## Historical selection evidence for available product previews

These are historical model-selection errors, not independent future test errors.

| CSV | Product | Selected method | Weekly forecast | Historical weekly MAE | Zero MAE | Shared test weeks |
|---|---|---|---:|---:|---:|---:|
| 01_noisy_weekday_retail | RETAIL-01 | mean_4_weekly_totals | 90.25 | 5.08 | 93.23 | 26 |
| 02_growing_demand | GROWTH-01 | last_week_total | 136.00 | 6.69 | 98.27 | 26 |
| 03_intermittent_and_cancellations | SPARE-01 | sba_croston | 29.34 | 12.35 | 21.42 | 26 |
| 05_mixed_products | HEALTHY | mean_4_weekly_totals | 82.75 | 4.37 | 83.65 | 26 |

File 05 must isolate two unavailable products without hiding the healthy product.
File 10 requires quarantine confirmation; the dashboard is preview-only and demand is unavailable.
Every emitted number must beat zero over at least 13 common historical test weeks.
The daily planning rate is weekly total / 7, not seven daily predictions.

## Limitations

Passing these tests proves the stated behavior on ten fixtures, not that all failures are handled.
Historical errors used to select the winning method are not an independent held-out accuracy estimate.
No forecasts were validated against future real-business outcomes; no policies were loosened.
These tests exercise the real API in-process, not browser interactions. Full responses and error
metrics are saved in report.json. Existing browser tests should still be run separately.
The earlier locked evaluation's sparse-stratum failure remains unresolved; these synthetic checks do not supersede docs/PRODUCT_DEMAND_LOCKED_EVALUATION.md.
