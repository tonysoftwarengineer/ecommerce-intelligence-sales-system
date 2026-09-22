# Milestone 11A: Product-Demand Foundation Plan

**Status:** Implemented; foundation review complete  
**Date:** 2026-08-28  
**Decision record:** `docs/architecture/ADR-007-product-demand-forecasting-contract.md`

## 1. Outcome

Build the trustworthy data foundation for a future seven-day product-demand
forecast. This slice ends with tested product identities, quantity semantics,
per-product readiness, and a regular product-date calendar. It does not end with
a forecast on the dashboard.

The prediction target is **observed fulfilled units per product across the whole
business**. It is not latent customer demand when stockouts, missing records, or
unobserved walkaways hide that demand.

## 2. Architecture Challenge Result

The accepted direction is sound, but the pre-implementation challenge produced
the following safeguards and scope corrections.

| Question challenged | Decision after challenge | Reason |
|---|---|---|
| Are fulfilled sales the same as customer demand? | No. Name the target `fulfilled_units` and disclose stockout limitations. | Transaction data cannot reveal customers who wanted an unavailable item. |
| Must every eligible product have a daily forecast? | No. The internal calendar is daily; daily output must earn eligibility through rolling evaluation. | Intermittent products may support a seven-day total but not credible day-by-day values. |
| Can the existing order-total path feed product forecasts? | No. Product forecasting requires line-item product identity and quantity. | Order-total mode deduplicates orders and intentionally loses line-item semantics. |
| Should customer ID be newly required for product forecasting? | No. Preserve existing revenue requirements, but do not make customer identity part of the new forecasting contract. | Product-unit aggregation does not inherently require personal identifiers. |
| Should missing product dates become zero automatically? | No. Zero requires evidence that the export covers normal trading activity; unknown gaps remain unknown. | Silent zero-filling can train the model on invented demand. |
| Should a unit column be mandatory on every row? | No. Accept either a mapped unit or one explicit dataset-level default. | This reduces repetitive CSV work without guessing quantity meaning. |
| Should we implement cold start, events, intervals, and reorder advice now? | No. Defer each to its own evidence gate. | Each adds a separate contract and can make a weak baseline look more capable than it is. |
| Should one global accuracy threshold decide every product? | No. Start with per-product eligibility and report portfolio coverage. | Dense and intermittent products have different evidence and error behaviour. |

## 3. Current-Code Finding

The existing generic pipeline already preserves optional `quantity` and
`product_category`, but it has no canonical product/SKU identity or unit of
measure. Its forecast module predicts monthly revenue, not product units.
Therefore, adding another model first would train on an undefined product grain.

The implementation must remain backward compatible with current revenue upload,
validation, analytics, forecasting, diagnostics, and browser journeys.

## 4. In Scope

### 4.1 Backward-compatible source mapping

- Add optional mappings for `product_id`, `product_name`, and
  `unit_of_measure`.
- Add conservative aliases for common labels such as SKU, StockCode, ItemCode,
  Description, UOM, and Unit.
- Keep `product_id` optional for existing revenue analytics.
- Preserve source values as strings; never coerce a code into a number or remove
  meaningful leading zeroes.

### 4.2 Canonical product-demand contracts

Create typed contracts for:

- product identity and identity confidence;
- canonical quantity and unit;
- order-lifecycle contribution to fulfilled units;
- product-date observation status;
- per-product capability/readiness result; and
- dataset-level assumptions explicitly confirmed by the user.

The likely module boundary is:

```text
src/product_demand/
  contracts.py
  readiness.py
  calendar.py
```

Names may change during implementation if the existing package conventions make
a clearer boundary available; behaviour and tests are the stable contract.

### 4.3 Deterministic readiness

Readiness must identify the smallest affected scope and explain why. Initial
conditions include:

- unavailable when line-item quantity or trustworthy product identity is absent;
- unavailable for the order-total revenue path;
- unavailable for an affected product when units conflict without a conversion;
- limited identity when a confirmed product-name fallback is used;
- stockout-awareness limitation when no inventory or stockout evidence exists;
- no forecasting eligibility threshold yet, because that threshold belongs to
  Milestone 11B evaluation.

### 4.4 Internal daily calendar

Construct one deterministic row per product and date over the usable observation
window. Each row distinguishes:

- observed fulfilled sales;
- confirmed zero sales;
- business closed;
- known stockout/stockout-limited;
- missing or unknown.

The calendar builder must not mutate its input, invent unit conversions, infer
unmet demand, or silently convert an ambiguous gap to zero.

## 5. Explicitly Out of Scope

- Daily or weekly forecast values.
- Forecast model selection or model tuning.
- Cold-start proxy forecasts.
- Prediction intervals.
- Promotions, price changes, weather, holidays, or free-text events.
- Inventory reorder quantities or safety-stock policy.
- Product-location forecasting.
- Product-demand API or dashboard components.
- Editable canonical data or automatic source-file rewriting.

These exclusions keep the first slice reviewable. They are deferred, not
forgotten.

## 6. Implementation Order and Learning Questions

### Step 1 — Write contract tests first

Define examples for valid SKU identity, name fallback, missing identity, default
unit, conflicting units, cancellations, returns, and stockout-limited sales.

**Learning question:** Which facts are business inputs, and which facts may the
system derive safely?

### Step 2 — Extend mapping and canonical preservation

Add the three optional fields without changing existing required mappings.
Confirm that codes retain leading zeroes and that unmapped files behave exactly
as before.

**Learning question:** How do we evolve a schema without breaking existing
clients or making a new feature mandatory?

### Step 3 — Implement per-product readiness

Return typed ready, limited, and unavailable states with reason codes and plain
language. Do not add historical-length or accuracy rules in this slice.

**Learning question:** Why is capability degradation safer than one global
pass/fail result?

### Step 4 — Implement lifecycle-aware fulfilled units

Apply deterministic cancellation and return semantics from ADR-007. Preserve
returned quantity separately from gross fulfilled units.

**Learning question:** Why must the target definition precede model choice?

### Step 5 — Build the complete internal calendar

Aggregate line items to product-date rows, classify gaps using explicit evidence,
and retain unknowns. Verify totals against accepted source rows.

**Learning question:** How can preprocessing introduce label error even when the
forecasting algorithm is correct?

### Step 6 — Run the foundation review gate

Review contracts, invariants, scenario outcomes, regressions, and usability
assumptions. Only then plan Milestone 11B baseline forecasting and rolling-origin
evaluation.

## 7. Test Strategy

### 7.1 Unit and invariant tests

- Product IDs are stable strings and retain leading zeroes.
- No incompatible units are added.
- Pre-fulfilment cancellations contribute zero fulfilled units.
- Fulfilled returns do not erase gross fulfilled demand.
- Stockout-limited observations are never labelled confirmed zero.
- Unknown gaps remain unknown unless an explicit dataset-level rule supports
  zero-filling.
- Product-date totals reconcile to accepted canonical line items.
- Inputs are not mutated.
- The same input and configuration always produce the same output.

### 7.2 Scenario pack

Create small deterministic fixtures for:

1. dense daily SKU sales;
2. intermittent SKU sales;
3. a complete export containing true zero-sale product days;
4. business-wide missing dates;
5. confirmed closures;
6. known stockouts;
7. cancellations and post-fulfilment returns;
8. conflicting pieces and packs;
9. confirmed product-name fallback;
10. order-total input that is valid for revenue but ineligible for product demand.

Each fixture must declare its expected readiness, calendar statuses, and
fulfilled-unit totals before implementation.

### 7.3 Regression tests

- Existing backend tests remain green.
- Existing revenue-only CSVs require no new mapping or confirmation.
- Existing monthly revenue forecast output is unchanged.
- Existing Playwright journeys remain green if frontend code is touched.

### 7.4 Real-world and benchmark evaluation

Testing continues after the foundation and model code; architecture decisions are
revisable when evidence disagrees.

- **First public-data evaluation:** UCI Online Retail II. It contains two years of
  real transactions with product codes, quantities, dates, prices,
  cancellations, and missing values. Use it first to challenge identity,
  lifecycle, scale, and calendar assumptions.
- **Later benchmark:** the M5 retail forecasting data. Use it to test many
  intermittent hierarchical item series and scaled evaluation, not as the first
  parser fixture.
- **Synthetic scenarios:** retain them because public data rarely labels every
  edge case, such as a confirmed closure versus an unknown export gap.
- **Anonymized business data:** add only with permission and documented meaning.
  Use it to test external validity; do not claim universal business validation
  from one dataset.

For Milestone 11B, evaluation will use rolling forecasting origins so every test
window occurs after its training window. Accuracy will be reported overall and
separately for over-forecasting, under-forecasting, and bias. Exact eligibility
thresholds will be proposed only after these distributions are observed.

## 8. Foundation Exit Criteria

Milestone 11A is complete only when:

- all new contracts and reason codes are typed and documented;
- every scenario has a deterministic expected result;
- no ambiguous date is silently changed to zero;
- no incompatible quantity units are combined;
- revenue-only workflows remain backward compatible;
- all relevant unit, integration, lint, type, and regression checks pass;
- the real UCI sample has been profiled through the foundation path; and
- a review explicitly approves or revises the design before forecasting models
  are added.

## 9. Decision Confidence

- **Foundation architecture:** high (about 93%). The boundaries are supported by
  the current code audit and established forecasting evaluation practice.
- **Exact model, cadence, and trust thresholds:** deliberately not yet rated as
  high confidence. They require the Milestone 11B rolling evaluation.
- **Low-friction workflow:** moderate confidence until representative browser and
  user testing is completed.

Confidence is not permanence. Every rule has a testable assumption and a named
review point.

## 10. Evidence Base

- UCI Machine Learning Repository, “Online Retail II”:
  https://archive.ics.uci.edu/dataset/502/online+retail+ii
- Hyndman and Athanasopoulos, “Time series cross-validation”:
  https://otexts.com/fpp3/tscv.html
- Hyndman and Athanasopoulos, “Forecasting hierarchical and grouped time
  series”:
  https://otexts.com/fpp3/hierarchical.html
- Makridakis, Spiliotis, and Assimakopoulos, “M5 accuracy competition: Results,
  findings, and conclusions”:
  https://doi.org/10.1016/j.ijforecast.2021.11.013

## 11. Implementation and Review Record

Completed on 2026-08-28:

- Added optional `product_id`, `product_name`, and `unit_of_measure` mappings to
  line-item-capable revenue modes while preserving existing revenue-only uploads.
- Added typed assumptions, availability states, reason codes, per-product
  readiness, lifecycle-aware fulfilled/returned units, and deterministic daily
  calendar construction under `src/product_demand/`.
- Added conservative product-header suggestions and frontend mapping controls.
- Added deterministic tests for identity, unit conflicts, name fallback,
  order-total ineligibility, zero versus unknown gaps, closures, stockouts,
  cancellations, positive and negative return rows, and per-product degradation.
- Preserved the first-to-last observed date as each product's initial calendar
  window. Product activation/discontinuation evidence must be designed before a
  forecast may assume zeroes outside that window.

### Public-data challenge result

The reusable profiler in `scripts/profile_uci_product_demand.py` was run against
the official two-sheet UCI Online Retail II workbook:

- 1,067,371 source rows and 5,304 distinct product codes were inspected;
- the 25 busiest products contributed 68,720 profiled rows;
- 14 products were correctly `limited` because stockout and complete-export
  evidence were absent;
- 11 products were correctly `unavailable` because negative quantities appeared
  without an explicit cancellation/return meaning;
- 2,174 absent product dates remained `missing_unknown` rather than becoming
  invented zero demand;
- foundation preparation produced 10,066 product-date rows in 3.678 seconds on
  this local development machine; workbook loading took 28.346 seconds and is
  reported separately.

This evidence supports the conservative readiness boundary. It also creates two
mandatory Milestone 11B design questions: how a source represents negative
inventory adjustments/returns, and how the system establishes product active
periods at the end of an export. Neither may be guessed from the public data.

### Verification

- 187 non-integration backend tests passed; 4 integration tests were deselected.
- 3 Playwright Chromium journeys passed.
- Frontend lint and production build passed.
- Ruff lint/format and mypy passed for the changed Python foundation and profiler.
