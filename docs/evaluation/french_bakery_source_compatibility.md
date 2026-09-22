# French Bakery External-Source Compatibility Evaluation

## Outcome

**Forecast eligibility: `withheld`. No forecast was produced.**

This is the expected safe result. The source can be parsed for aggregate profiling, but it
does not contain enough confirmed business semantics to enter the frozen product-demand
forecasting pipeline.

## Source provenance

- Source: [French Bakery Daily Sales](https://github.com/Juli27co/French-bakery-daily-sales)
- Source type: external public dataset
- Permissioned independent-business export: no
- Source SHA-256: `30ad79586edf25c7fc90d75c48d37b6e2c689fbf4d476aeeec69c17a3c60a32f`

## Aggregate findings

| Measure | Count |
| --- | ---: |
| Source rows | 234,005 |
| Parseable nested rows | 234,004 |
| Quarantined malformed rows | 1 |
| Rows affected by a row-level quality issue | 1,327 |
| Observed calendar dates | 600 |
| Calendar span in days | 637 |
| Dates with no source rows | 37 |
| Rows with non-positive quantity | 1,295 |
| Rows with non-positive unit price | 32 |

## Why forecasting was withheld

| Reason code | Aggregate scope | Meaning |
| --- | ---: | --- |
| `missing_customer_identity` | 234,004 | The published source has transaction tickets but no stable customer identity. |
| `unconfirmed_completed_sales_status` | 234,004 | The source does not classify completed, cancelled, returned, or refunded rows. |
| `unknown_no_sale_dates` | 37 | Dates without rows cannot be distinguished from closures, missing exports, stockouts, or genuine zero demand. |
| `unclassified_non_positive_quantity` | 1,295 | Non-positive quantities exist without return or cancellation semantics. |
| `missing_unit_of_measure` | 234,004 | The source does not define the unit represented by each quantity. |
| `missing_product_category` | 234,004 | The source does not provide a confirmed product-category hierarchy. |

The adapter did not invent customer identities, order statuses, units, categories, closure
dates, stockout facts, or return meanings. The malformed source row was quarantined without
attempting to reconstruct it.

## Limitations and decision

- This result tests external-source compatibility, not forecast accuracy.
- It does not change the dashboard contract, forecasting methods, thresholds, or preview rules.
- It does not clear the permissioned independent-business evaluation checkpoint.
- It does not authorize RAG Phase 2.
- Raw rows, affected row positions, and detailed profiling output remain local and Git-ignored.

The successful outcome of this checkpoint is an explainable withheld forecast rather than a
forced prediction from ambiguous data.

## Reproduce locally

```bash
python3 -m scripts.evaluate_french_bakery_source \
  --csv data/public/external/french_bakery_sales.csv \
  --private-output data/public/external/french_bakery_compatibility.json \
  --summary-output docs/evaluation/french_bakery_source_compatibility.md
```
