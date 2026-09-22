# Online retailer evidence matrix

**Audience:** a small online retailer selling physical products with repeat
sales. The first promise is validated sales analysis and safe investigations.
Seven-day fulfilled-unit demand remains **Preview — not decision-ready**.

This matrix separates correct system behavior from forecast accuracy. Synthetic
browser and API fixtures prove how the software reacts to known inputs; they do
not establish how accurately it predicts another shop's future orders.

The [Pakistan multi-merchant public-source audit](pakistan_public_compatibility.md)
adds a separate full-source compatibility check: 584,524 nonblank records were
profiled, but missing open-day, stockout, unit, and revenue semantics kept the
forecast withheld. It is not an independent small-retailer accuracy result.

| Retailer situation | Evidence already exercised | What remains unproven |
| --- | --- | --- |
| Regular repeat sales | Synthetic [ten-CSV pack](../../tests/fixtures/product_demand_csv_pack/README.md) includes noisy weekday and growing demand; [M5 locked holdout](../PRODUCT_DEMAND_LOCKED_EVALUATION.md) reported positive skill for dense series. | Independent small online retailer forecast accuracy, stockout completeness, and business cost of error. |
| Sparse or occasional SKU sales | Locked M5 sparse stratum failed. [Development comparison](../PRODUCT_DEMAND_SPARSE_POLICY_COMPARISON.md), [fresh sparse-abstention validation](../PRODUCT_DEMAND_SPARSE_ABSTENTION_FRESH_VALIDATION.md), and [consistency development test](../PRODUCT_DEMAND_CONSISTENCY_DEVELOPMENT_RESULT.md) rejected the tested safeguards. | A policy that safely identifies unstable SKUs without withholding useful forecasts. No scored cohort can be reused as fresh proof. |
| New product or short history | The ten-CSV pack's short-history case withholds a number; M5 delayed-start series passed the first locked holdout's gate. | Real retailer cold-start quality and the effect of launches, promotions, or changing availability. |
| Returns and cancellations | [Retail rules](../../tests/test_retail_rules.py), [calendar tests](../../tests/test_product_demand_foundation.py), and the ten-CSV pack check explicit status treatment. | Accuracy when a real export mixes returns, partial fulfilment, and exchanges. |
| Missing sale dates | The ten-CSV pack withholds forecasts when export coverage is unconfirmed; calendar tests preserve unknown dates instead of treating them as zero. | Whether actual retailer exports cover every open day and distinguish true zero sales from missing records. |
| Stockouts | The ten-CSV pack withholds a forecast without stockout confirmation; calendar tests mark known stockout days as censored. | Real stockout logs, lost demand, and the effect on future unit forecasts. The browser does not yet provide a low-friction per-SKU stockout import. |
| Category fallback | [Category tests](../../tests/test_product_demand_category_fallback.py) verify confirmation, compatible units, and non-overlap with product previews. | Independent category forecast accuracy and complete category membership. |
| Policy-document answers | [RAG Phase 1 locked retrieval](rag_phase_1/chroma_locked_test.md) passed; synthetic browser and API tests cover citation verification and abstention. | Phase 2 real-provider locked answer quality and manual failure review; the recent hard-development run was blocked by provider limits. |

## Next forecasting checkpoint

1. Obtain a permissioned, anonymized retailer export with stable SKU, quantity,
   unit, order and status semantics, complete-date evidence, and known stockouts
   or an explicit statement that they were not tracked. Keep raw data local.
2. Run the [independent-business evaluator](../INDEPENDENT_BUSINESS_FORECASTING_EVALUATION.md)
   on the frozen current policy. Report previews, abstentions, MAE, WAPE, bias,
   over- and under-forecast, and skill versus zero by demand pattern. A valid
   inconclusive result is preferable to guessed semantics.
3. If new data motivates a different sparse safeguard, compare bounded
   candidates on development data, predeclare a decision rule, then use a new
   untouched retailer or future-time holdout. The M5 cohorts scored above
   remain evaluation-only. Preserve the preview label until a new gate passes.

The [fictional retailer walkthrough](../../tests/fixtures/retailer_demo/README.md)
is a user-flow check, not independent forecast evidence. The separate RAG Phase
2 locked evaluation remains pending regardless of retailer forecast results.
