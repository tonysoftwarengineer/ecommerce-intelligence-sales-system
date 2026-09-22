# DataCo product-demand coverage diagnosis

**Research only.** The source's missing product-days, stockouts, and non-COMPLETE status meanings are unverified. This holdout was already viewed; none of the experiments below is fresh locked validation.

- Source: https://data.mendeley.com/datasets/8gx2fvg2k6/4
- Pinned mirror: https://huggingface.co/datasets/Primebiswa/SupplyChainDataset/resolve/a097d5fb41bafa4f7882d0778ecc5c5d8bd602ed/DataCoSupplyChainDataset1.csv
- Source SHA-256: `4f539ba0a001c084c57a0ec13dd53d60676ed8f7a78e582a53c42181f20d6b30`
- Rows: 180519; COMPLETE: 59491; other statuses: 121028.
- Missing product-days treated as zero only for research: 59003.
- Products skipped before the 13-week comparison: 11.
- Hidden-period COMPLETE-labelled units: 301 in assessed products; 1758 in skipped products.

## Same-denominator counterfactuals

| Research rule | Shown / opportunities | Coverage | Shown positive-sale weeks / positive-sale weeks | WAPE on shown | Skill vs zero on shown | Zero forecasts shown |
|---|---:|---:|---:|---:|---:|---:|
| Accepted preview policy | 299 / 1391 | 21.5% | 0 / 9 | undefined | undefined | 299 |
| Six shared historical weeks (instead of thirteen) | 299 / 1391 | 21.5% | 0 / 9 | undefined | undefined | 299 |
| Ignore zero-skill rejection (unsafe what-if) | 1131 / 1391 | 81.3% | 0 / 9 | undefined | undefined | 1131 |

Coverage alone is not accuracy. WAPE and skill are undefined when the shown weeks contain no positive actual units. Positive-sales-week coverage and over/under-forecast units remain separate checks.

## Coverage and error by demand pattern

| Rule | Pattern | Shown / opportunities | Shown positive-sale weeks | WAPE |
|---|---|---:|---:|---:|
| Accepted preview policy | dense | 117 / 156 | 0 / 4 | undefined |
| Accepted preview policy | intermittent | 104 / 494 | 0 / 4 | undefined |
| Accepted preview policy | sparse | 78 / 741 | 0 / 1 | undefined |
| Six shared historical weeks (instead of thirteen) | dense | 117 / 156 | 0 / 4 | undefined |
| Six shared historical weeks (instead of thirteen) | intermittent | 104 / 494 | 0 / 4 | undefined |
| Six shared historical weeks (instead of thirteen) | sparse | 78 / 741 | 0 / 1 | undefined |
| Ignore zero-skill rejection (unsafe what-if) | dense | 117 / 156 | 0 / 4 | undefined |
| Ignore zero-skill rejection (unsafe what-if) | intermittent | 325 / 494 | 0 / 4 | undefined |
| Ignore zero-skill rejection (unsafe what-if) | sparse | 689 / 741 | 0 / 1 | undefined |

## Why forecasts were withheld

- `insufficient_shared_folds`: 91 weekly opportunities.
- `no_weekly_winner`: 169 weekly opportunities.
- `non_positive_zero_skill`: 832 weekly opportunities.
- Positive-sale weeks without a winner: 9 across 7 products.
- Training calendar days for those products (one count per product): [2, 7, 15, 23, 25, 26, 31].
- Weekly candidate unavailable reasons for those products: {'short_history': 21}.
- Interpretation: the positive-sale opportunities in assessed products belonged to products with only 2–31 calendar days before the holdout. Their methods had no weekly winner, so neither relaxing the 13-week preview floor nor ignoring zero skill produced useful positive-demand coverage.

## Source activity and recency

- before holdout: CANCELED=3551, CLOSED=18892, COMPLETE=57432, ON_HOLD=9478, PAYMENT_REVIEW=1821, PENDING=19525, PENDING_PAYMENT=38505, PROCESSING=21153, SUSPECTED_FRAUD=3929.
- hidden 13 weeks: CANCELED=141, CLOSED=724, COMPLETE=2059, ON_HOLD=326, PAYMENT_REVIEW=72, PENDING=702, PENDING_PAYMENT=1327, PROCESSING=749, SUSPECTED_FRAUD=133.
- Prior completed sale 0 to 7 days: 0 shown, 12 withheld.
- Prior completed sale 29 to 91 days: 142 shown, 281 withheld.
- Prior completed sale 8 to 28 days: 0 shown, 36 withheld.
- Prior completed sale over 91 days: 157 shown, 763 withheld.
- None of the shown forecasts involved a product with a recorded completed sale in the preceding 28 days. This is a research-cohort warning, not proof of product inactivity.

Recency uses only sales known at each forecast origin, never later outcomes. The source-to-calendar checks reconciled every assessed weekly actual with its COMPLETE-labelled source rows. Neither a 70% coverage target nor any counterfactual authorizes weakening the live trust gate. The independent small-retailer validation remains pending.
