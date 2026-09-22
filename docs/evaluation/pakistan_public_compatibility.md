# Pakistan online-retail public-source compatibility audit

This is a **multi-merchant public dataset**, not one permissioned small-retailer
export. It tests source compatibility and safe withholding, **not forecast accuracy**.
The [source listing](https://opendata.com.pk/dataset/pakistan-largest-ecommerce-dataset/resource/7395e1d0-c02b-4e1d-abb8-84ae52681ffb) specifies no reuse license. No raw source or
transaction-level derivative is published in this repository.

- Source URL: https://opendata.com.pk/dataset/a6a52e2b-c209-4f9f-8b99-eb67ef33d04e/resource/7395e1d0-c02b-4e1d-abb8-84ae52681ffb/download/archive.zip
- Archive SHA-256: `6db2476c34887025ec98a1a068d1a8753f4e5d276d63e0170bef1de9dc59bbcd`
- Source rows audited: 1,048,575
- Nonblank records: 584,524
- Structural sales mapping valid: true
- Missing required mapped fields: none
- Distinct status labels: 17
- Same grand-total text repeated within an order: 175,742 rows
- Conflicting grand-total text within an order: 0 rows
- Forecast eligibility: **withheld**; no forecast was produced.

## Source quality counts

| Issue code | Count |
| --- | ---: |
| `blank_source_row` | 464,051 |
| `missing_sku` | 20 |
| `non_positive_grand_total` | 9,708 |
| `non_positive_unit_price` | 2,232 |
| `unconfirmed_slash_date_format` | 584,524 |
| `unnamed_header_columns` | 5 |

## Status-label counts

These are labels in the source, not confirmed accounting or fulfillment rules.

| Label class | Rows |
| --- | ---: |
| `cancelled_label` | 201,249 |
| `completed_label` | 233,685 |
| `refund_ambiguous` | 67,579 |
| `unknown` | 82,011 |

## Why forecasting is withheld

- `mixed_merchant_source`
- `unconfirmed_open_day_coverage`
- `unconfirmed_stockout_tracking`
- `unconfirmed_unit_of_measure`
- `unconfirmed_revenue_authority`
- `unconfirmed_date_format`
- `unclassified_order_statuses`

Open-day coverage, stockout completeness, unit meaning, and revenue authority
remain unconfirmed. Missing product-day rows are **not** treated as zero sales.
The independent-business forecast checkpoint and the RAG Phase 2 locked test
remain separate and pending.

## Reproduce

From the repository root, run `python3 -m scripts.evaluate_pakistan_public_compatibility`.
The command fetches the fixed ZIP URL into bounded memory, streams its CSV,
writes detailed aggregate diagnostics to ignored `data/public/external/`, and
regenerates this Markdown report. It does not retain the raw archive or rows.
