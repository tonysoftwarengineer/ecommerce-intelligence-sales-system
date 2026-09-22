# DataCo public-data blind holdout

**Research-only.** This is a real-world supply-chain source, not a permissioned small online retailer or an approved forecast for operational use.

- Publisher: https://data.mendeley.com/datasets/8gx2fvg2k6/4
- Pinned public mirror: https://huggingface.co/datasets/Primebiswa/SupplyChainDataset/resolve/a097d5fb41bafa4f7882d0778ecc5c5d8bd602ed/DataCoSupplyChainDataset1.csv
- Download SHA-256: `4f539ba0a001c084c57a0ec13dd53d60676ed8f7a78e582a53c42181f20d6b30`
- Publisher/mirror byte identity: unverified.
- Target: units on rows labelled `COMPLETE`; other order statuses are not guessed.
- All later 13 weeks were hidden when selecting each product's method; each next week was predicted before its actual values were revealed.

## Source and holdout counts

- Source rows: 180519
- `COMPLETE` rows: 59491
- Other-status rows: 121028
- Products considered: 118
- Products skipped for insufficient or unsafe holdout: 11
- Weekly opportunities: 1391
- Previews shown: 299
- Honest abstentions: 1092
- Shown weeks with positive actual units: 0
- Abstained weeks with positive actual units: 9
- Actual units in shown weeks: 0
- Actual units in abstained weeks: 301
- Actual units in skipped products: 1758

## Accuracy on shown research forecasts

- WAPE: not defined (no positive actual units in shown weeks)
- Skill versus predicting zero: not defined (zero benchmark also made no error in shown weeks)
- Over-forecast units: 0
- Under-forecast units: 0
- Within-source research gate: inconclusive

## Interpretation

No shown week had positive actual units. Exact zero matches do not demonstrate predictive skill; nonzero predictions are overforecasts. Positive completed-label units fell in abstained or skipped scopes. Absent product-days are treated as zero **only for this research view**. The source does not establish open-day completeness, stockout tracking, or the business meaning of other final-looking statuses. Therefore the live product's strict trust rules would withhold a decision-ready demand forecast, regardless of this score. The independent-small-retailer checkpoint remains pending.
