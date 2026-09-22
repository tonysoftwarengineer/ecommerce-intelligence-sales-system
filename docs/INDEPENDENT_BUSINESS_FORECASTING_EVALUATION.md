# Independent-Business Product-Demand Evaluation

This local checkpoint evaluates the existing **Preview — not decision-ready**
product-demand policy against one permissioned, anonymized business export. It
does not train a model, tune a threshold, or approve supported weekly use.

## Privacy boundary

Keep the raw CSV, the mapping JSON, and the detailed JSON report under
`data/private/`. The repository ignores `data/`. The Markdown summary contains
only aggregate counts and metrics; do not commit product names, product codes,
customer information, prices, or calendar dates.

## Required source fields

The current generic-sales workflow needs an order ID, order date, customer ID,
and an accepted revenue representation. Product-demand evaluation additionally
needs a stable product code or confirmed unique product name, a quantity, and a
unit of measure. Order status is optional only when the business can truthfully
confirm that every row is completed.

For a product to receive a full future holdout score, it normally needs about
30 complete calendar weeks: enough earlier history for the existing 13-fold
preview gate plus 13 unseen weeks. Shorter or unsafe product histories are
reported as unavailable; they are never forced into a number.

## Local configuration

Save a reviewed configuration beside the raw CSV, for example
`data/private/business_mapping.json`:

```json
{
  "mapping": {
    "order_id": "Order ID",
    "order_date": "Order Date",
    "customer_id": "Customer ID",
    "unit_price": "Unit Price",
    "quantity": "Quantity",
    "product_id": "SKU",
    "unit_of_measure": "Unit",
    "product_category": "Category",
    "order_status": "Status"
  },
  "revenue_mode": "unit_price_times_quantity",
  "negative_revenue_policy": "invalid",
  "date_format": "%Y-%m-%d",
  "currency": "NGN",
  "assume_all_completed": false,
  "status_mapping": {
    "completed": "completed",
    "cancelled": "cancelled",
    "refunded": "returned"
  },
  "discount_type": "none",
  "confirm_quarantine": true,
  "product_demand": {
    "default_unit_of_measure": null,
    "confirm_product_names_unique": false,
    "confirm_product_categories": true,
    "export_covers_all_open_days": true,
    "stockout_tracking_complete": true,
    "business_closed_dates": [],
    "stockout_dates": []
  }
}
```

Every confirmation must reflect real business knowledge. In particular, do not
claim complete open-day coverage when the export has gaps, and do not claim
complete stockout tracking when stockouts were not recorded.

## Run the checkpoint

```bash
python3 -m scripts.evaluate_independent_product_demand \
  --csv data/private/business_sales.csv \
  --config data/private/business_mapping.json \
  --private-output data/private/business_evaluation.json \
  --summary-output docs/evaluation/independent_business_forecasting.md
```

The evaluator uses the same mapping validation, data validation, canonical
transformation, calendar preparation, and product-demand service as the
dashboard. It freezes the selected method at the pre-holdout cutoff, then
scores the final 13 complete seven-day windows without letting future values
influence earlier predictions.

## Result interpretation

- `consistent_external_evidence`: shown product previews beat zero on this one
  business holdout. They still remain preview-only.
- `observed_limitation`: shown product previews did not beat zero. Record the
  result; do not tune the policy using this holdout.
- `inconclusive`: safe data, history, or comparable shown forecasts were not
  available. This is an honest result, not a failure to hide.

After a real run, perform one dashboard upload with the same mapping and verify
that its readiness and preview/unavailable states agree with the local report.
