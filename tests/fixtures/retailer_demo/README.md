# Fictional online retailer walkthrough

Harbor Home is a **synthetic** shop selling one repeat-purchase physical item.
This CSV is intentionally simple and predictable. It demonstrates the browser
workflow; it does not validate forecast accuracy on a real retailer.

1. Open the local dashboard and choose **Upload a sales CSV**. Upload
   `retailer_sales.csv`.
2. Apply mapping suggestions and review them. Choose **Row total**: map
   `order_id`, `order_date`, `customer_id`, and `revenue` to their namesake
   columns. Also map `product_id`, `product_name`, `quantity`,
   `unit_of_measure`, and `order_status`. Use `%Y-%m-%d` and currency `NGN`.
3. The fixture's `Completed` status represents completed sales; classify it as
   such. This fixture has no discount column, so choose no discount. The last
   month, April 2025, is complete in the synthetic export. Validate the mapping
   and rows, then generate the dashboard.
4. Read the validated sales and diagnostic sections first. For the product
   demand experiment, this fictional export is declared complete for every
   open day and has no unrecorded stockout days. Confirm those fixture facts and
   evaluate. Any number shown is a seven-day **preview**, not a restock target.
   For a real shop, these confirmations require business records; do not guess.
5. Upload `shipping_policy.md` in the document panel, choose **Policy**, and
   select **Upload and index**. Ask: “How long does standard Lagos delivery take
   after dispatch?” If Gemini is available, inspect the quote and citation. If
   Gemini is unavailable, the sales dashboard remains usable. An unrelated
   question should return insufficient evidence.

The automated Chromium journey uses a deterministic fake answer provider. It
checks the user flow and citation display, not real Gemini quality. The first
source is a single-SKU teaching fixture; the [retailer evaluation matrix](../../../docs/evaluation/online_retailer_evidence_matrix.md)
tracks broader and independent evidence gaps.
