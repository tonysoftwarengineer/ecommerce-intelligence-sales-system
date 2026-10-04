# ADR-017: Retire the Olist demo implementation

**Status:** Accepted
**Date:** 2026-10-04
**Decider:** Project owner

## Context

Olist supplied an early research dataset, console report, charts, a revenue-trend
experiment, and customer segmentation. The portfolio product now serves a
different workflow: a visitor uploads their own sales CSV (or chooses a clearly
fictional retailer sample), confirms its meaning, and sees validated analysis.
Stage A removed the live Olist API endpoints and startup download. The remaining
Olist-only pipeline, API response shapes, frontend view, and dependencies are
unreachable but still increase maintenance and make the product boundary unclear.

## Decision

Remove the Olist-only implementation, its root console entry point `main.py`,
its tests, unused API response types, and the `kagglehub`/`matplotlib` dependencies.
The root entry point imported only the retired pipeline and had no live consumers.
Keep a short, explicitly historical
summary of its research results in the README; those results do not validate
the current retailer workflow or forecasts. Remove the unused `integration`
test marker and run the full backend suite in CI.

Keep the generic CSV upload/validation, financial analytics, product-demand,
diagnostics, and RAG code unchanged. Retain `scikit-learn` for the live TF-IDF
retrieval baseline and `openpyxl` for offline product-demand evaluation. Keep
the dataframe preview/CSV serializers and shared frontend chart components
used by the live dashboard.

## Options considered

| Option | Maintenance | Product clarity | Research access |
|---|---|---|---|
| Keep unreachable Olist code | Ongoing dependency and test burden | Ambiguous | Executable in this repo |
| Archive it separately | Lower burden here, extra repository maintenance | Clear | Executable elsewhere |
| Remove it and retain historical evidence (chosen) | Lowest burden here | Clear | Published results remain, code is available in Git history |

## Trade-offs and consequences

- The live customer workflow and its trust gates do not change.
- The old Olist console and chart experiments will no longer run from the
  current tree; a researcher can inspect earlier commits if needed.
- Historical benchmark numbers must never be presented as current-product
  release evidence.
- A fresh Python 3.12 dependency resolution and complete regression checks
  are required because removing top-level packages can change transitive pins.
- The frontend redesign remains a separate phase; unused Olist styles in
  `App.css` are intentionally left for that work.

## Verification

- Confirm no live imports or calls to retired modules/endpoints remain.
- Run backend lint, format, mypy, and full pytest; frontend type-check,
  lint, build, and isolated Playwright journeys.
- Verify the exact dependency lock and audit result before committing.
