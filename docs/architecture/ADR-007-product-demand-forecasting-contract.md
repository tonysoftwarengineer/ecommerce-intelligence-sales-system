# ADR-007: Product-Demand Forecasting Contract and Low-Friction Reliability

**Status:** Accepted  
**Date:** 2026-08-27  
**Last reviewed:** 2026-08-31  
**Deciders:** Project owner

## Context

The existing generic-sales pipeline forecasts monthly revenue for each currency.
The next learning phase will add inventory-oriented demand forecasting without
turning the product into an unbounded system that predicts every available
column. The first operational target is expected units sold for each restockable
product over the next seven days.

Product-level demand introduces ambiguity that total revenue does not have:
product names may not be stable identifiers, quantities may use incompatible
units, absent rows may mean zero sales or missing observations, and stockouts may
hide real customer demand. Asking users to resolve every ambiguity manually would
make the upload workflow too burdensome. Silently resolving those ambiguities
would make the forecast untrustworthy.

## Decision

### Forecast target and horizon

- The primary target is units fulfilled to customers for each restockable
  product/SKU.
- The initial forecast horizon is the next seven days.
- The pipeline uses a daily internal calendar, but user-facing granularity is an
  evaluated capability rather than a promise. A product receives daily values
  only when rolling-origin tests support them; otherwise it receives an evaluated
  seven-day total or an unavailable result.
- Revenue, order count, and other targets may be added later, but each target must
  have its own data requirements, evaluation evidence, trust rules, and fallback.
- The first release forecasts each product across the whole business. Optional
  product-location forecasts require a later capability check and sufficient
  history for every product-location series.

### Product identity

- A stable product/SKU code is the preferred forecasting identity within one
  business catalogue.
- The internal canonical field is `product_id`; the mapping interface may label
  it “Product/SKU code” so the contract is not tied to one source-system term.
- Product names are display metadata, not the default identity.
- When no product code exists, a product name may be used only after consistency
  checks and explicit user confirmation that it uniquely identifies a
  restockable item. The resulting identity confidence is lower.
- The system never silently invents product codes.
- If a trustworthy identity cannot be established, only product-level forecasting
  is unavailable; unrelated valid analytics remain available.

### Quantity and unit of measure

- Every product series has one canonical forecasting unit, such as pieces, packs,
  kilograms, or litres.
- The unit may come from a mapped source column or one explicitly confirmed
  dataset-level default. A default avoids forcing businesses to repeat the same
  unit on every row without allowing the system to guess it.
- Quantities with different units are never added directly.
- Multiple units for one product require an explicit conversion rule, such as
  `1 pack = 10 pieces`, before normalization.
- The system never guesses a conversion factor.
- Products stocked independently at different packaging levels should use
  separate SKU codes.
- A unit conflict restricts only the affected product when other product series
  remain valid.

### Complete internal product calendar

- The pipeline creates a regular internal `product x date` series before model
  training. This is a data structure, not a requirement to show a calendar chart.
- Product-date observations distinguish at least: observed sales, confirmed zero
  sales, business closed, known stockout, and missing/unknown.
- A missing product row may become a confirmed zero only when dataset-wide
  evidence and the user's operating-data confirmation support that interpretation.
- Business-wide gaps remain missing unless the business confirms they were closed
  days.
- Known stockout periods are not treated as proof of zero customer demand.
- Ambiguous periods are excluded or handled by an evaluated missing-data method;
  they are never silently converted to zero.

### Order lifecycle, stockouts, and inventory boundaries

- Orders cancelled before fulfilment contribute zero fulfilled units.
- Units fulfilled and later returned remain part of gross fulfilled demand;
  returned quantities are tracked separately. Refund treatment belongs to the
  financial contract and does not redefine physical product demand.
- A known stockout day records the observed fulfilled quantity and a
  stockout-limited/censored status. The system does not invent unmet demand and
  does not present the observed quantity as proof of total customer interest.
- A negative quantity without an explicitly confirmed cancellation, return, or
  inventory-adjustment meaning restricts the affected product. Its sign is never
  silently converted into fulfilled demand or returned units.
- Sales history without inventory or stockout fields can still support an
  observed-fulfilled-sales forecast. The output must explain that unmet demand
  cannot be measured.
- Reorder quantities remain unavailable without current stock, usable returns,
  supplier lead time, and an explicit stocking policy.
- Product-demand forecasting requires line-item grain, a trustworthy product
  identity, and quantity. The existing order-total revenue mode is ineligible
  because it deliberately deduplicates orders and cannot preserve product units.

### Forecast eligibility and trust

- The existing six-complete-month threshold belongs to the monthly revenue
  forecast and is not reused as a universal product-demand rule.
- Eligibility depends on the number of usable observations, demand frequency,
  missingness, stockout information, model complexity, forecast horizon, and
  rolling-origin out-of-sample performance.
- History thresholds introduced during implementation are explicit product policy,
  not industry standards, and must be justified through evaluation.
- Each product receives its own availability and trust result; one weak product
  must not invalidate every product forecast.
- A bounded set of transparent baseline methods is compared automatically. A more
  complex method is added only if rolling-origin tests demonstrate enough
  improvement to justify its latency and maintenance cost.
- Evaluation reports overall error, over-forecast error, under-forecast error, and
  directional bias separately. Business cost weighting is introduced only when
  its inputs are evidenced.
- Forecasts remain neutral estimates of expected fulfilled demand. A future
  stocking policy may choose a conservative order quantity, but it must not hide
  that policy by biasing the forecast itself.
- When evaluation supports it, the output includes an expected value and a
  prediction interval derived from historical forecast errors. An unsupported
  range is unavailable rather than invented.

### Cold-start products

- A product with no usable sales history may receive a cold-start proxy forecast
  only when the system can form a transparent peer group from structured catalogue
  metadata.
- The initial peer-group evidence may include category, unit of measure, pack size,
  price tier, brand, and other explicitly mapped product attributes.
- The system does not infer similarity from product names alone and does not use an
  LLM to invent a comparable-product relationship.
- A cold-start forecast is visibly labelled as a limited-confidence proxy. It
  identifies the peer-group attributes and existing products that supplied the
  evidence.
- If sufficient structured metadata or comparable products do not exist, the
  product-level forecast is unavailable with a clear explanation.
- Cold-start proxy performance must be evaluated separately from standard
  history-based forecasts before it is considered decision-ready.

### Coherent aggregation and future drivers

- Product forecasts are the first-release source of truth. Category and business
  totals are sums of compatible product forecasts and state their product coverage.
- Quantities with incompatible units are not added into a unit total.
- The first baseline does not require promotion, price, weather, holiday, or other
  future-driver forms.
- Future known drivers use optional structured records with an event type, date
  range, affected scope, and relevant numeric value. Vague free text never changes
  a forecast automatically.
- A future driver changes the forecast only after comparable historical evidence
  demonstrates value and complete values exist for the forecast horizon. Otherwise
  it is shown as context with an explicit “not included” explanation.
- A confirmed planned closure may constrain expected fulfilled sales to zero for
  the closed period without claiming that underlying customer interest is zero.

### Low-friction interaction

- The default interface shows a compact coverage summary, not every product-date
  record.
- The system groups repeated ambiguities and asks dataset-level questions rather
  than requiring confirmation for every day or row.
- Safe mapping suggestions may be automated, but any inference that changes
  forecast meaning requires transparent confirmation.
- Confirmation is requested only when the user can know the answer and the answer
  materially changes forecast meaning. Examples include product-name identity,
  unit conversion, status semantics, export completeness, and planned closures.
- The system does not ask users to guess unmet demand, choose a model, confirm every
  missing day, or supply optional data. It exposes a limitation or restricts the
  affected forecast instead.
- Detailed evidence is progressively disclosed through filters, expandable
  sections, or downloadable correction data.
- A calendar or heatmap is an optional investigation view. Colour is accompanied
  by text or symbols, and confirmed no-sale days are not presented as errors.
- Users may continue to a clearly labelled preview when safe basic analytics are
  available. Only affected forecasts are restricted where possible.
- Ready forecasts are shown first. Limited forecasts have a separate labelled
  section. Unavailable products remain discoverable in a collapsed section, and a
  visible coverage summary reports counts and material exclusions.
- The default view shows only the selected forecast method and a plain-English
  reason. Technical model comparisons remain available as optional evidence.
- Every restriction explains what is missing, why it matters, where to correct it,
  and how to rerun the analysis.
- Editable repair artifacts are correction exports, not the internal canonical
  dataset. Row-level issues preserve original source values and include locations,
  issue codes, and correction instructions. Repeated product-metadata gaps should
  use a one-row-per-product correction template instead of repeating every sales
  row. The user corrects the source or approved supporting template and reruns the
  analysis; the system never silently rewrites business data.

## Options Considered

### Option A: Strict complete-data gate

| Dimension | Assessment |
|---|---|
| Reliability | High when users can satisfy every requirement |
| Usability | Low; blocks small businesses without mature SKU data |
| Implementation complexity | Low to medium |
| Coverage | Low |

**Pros:** Simple forecast eligibility and few ambiguous training values.  
**Cons:** High upload friction and unnecessary loss of valid analytics and valid
product series.

### Option B: Capability-aware guided normalization

| Dimension | Assessment |
|---|---|
| Reliability | High through explicit semantics and per-product gating |
| Usability | Medium to high through grouping and progressive disclosure |
| Implementation complexity | Medium to high |
| Coverage | High with honest fallbacks |

**Pros:** Balances trustworthy training data with a usable preview and isolates
problems to affected products.  
**Cons:** Requires richer contracts, product-level readiness, and careful browser
testing.

### Option C: Permissive silent inference

| Dimension | Assessment |
|---|---|
| Reliability | Low |
| Usability | Superficially high |
| Implementation complexity | Low initially |
| Auditability | Low |

**Pros:** Fastest path from upload to a forecast.  
**Cons:** Can invent identities, mix units, treat stockouts as zero demand, and
produce confident-looking but misleading forecasts.

## Trade-off Analysis

Option B is accepted. It adds contract and interface complexity, but it keeps the
system useful without weakening the evidence boundary. The system automates only
low-risk deductions, groups ambiguity into a small number of confirmations, and
degrades at the smallest safe scope. Forecast restrictions therefore apply to an
affected product or target before they apply to the entire analysis.

The complete calendar belongs in the forecasting pipeline. A visual calendar is
optional because showing every date by default would increase cognitive load and
could falsely portray no-sale days as errors.

## Consequences

- Product identity, units, missingness, and stockout semantics become first-class
  data contracts rather than preprocessing details.
- The mapping workflow will eventually need product code, product name, unit of
  measure, and optional unit-conversion inputs.
- The API will need per-product readiness and forecast evidence.
- Product forecasts can be partially available within one analysis.
- Correction exports remain traceable to source data while the canonical dataset
  remains an internal calculation contract.
- Cold-start support requires a catalogue-metadata contract and a transparent
  peer-group explanation; it cannot rely on name similarity alone.
- Evaluation must cover dense, sparse, intermittent, missing, closed-day, and
  stockout scenarios, plus cold-start proxy scenarios.
- Usability claims require representative user testing; design guidance alone is
  not proof that the workflow is low-friction.

## Implementation Sequence

The first coding slice is a foundation slice, not a forecasting-model release.
It will add backward-compatible mapping fields, typed product-demand contracts,
per-product readiness, deterministic calendar construction, and scenario tests.
It will not yet add forecast values, cold-start proxies, future drivers,
prediction intervals, reorder quantities, API responses, or dashboard sections.

This sequence is deliberate: model evaluation is meaningful only after product
identity, unit semantics, lifecycle treatment, and missing-date states are stable
and tested. The foundation is reviewed at a separate gate before forecast methods
are implemented.

The initial calendar covers each product from its first to last usable observed
date. Extending confirmed zeroes before product introduction or after the last
sale requires explicit product activation/discontinuation evidence; dataset-wide
export completeness alone does not prove that a product was available for sale.

## Action Items

1. [x] Define typed product-demand input and readiness contracts.
2. [x] Audit the current generic CSV mapping and canonical transaction schema.
3. [x] Define product calendar statuses and deterministic classification rules.
4. [ ] Create daily and weekly baseline forecasts with rolling-origin evaluation.
5. [ ] Define per-product trust and unavailable states.
6. [ ] Add grouped coverage confirmation and correction guidance to the workflow.
7. [x] Build scenario datasets for dense, sparse, stockout, missing, and unit-conflict cases.
8. [ ] Run browser usability tests before adding an optional calendar/heatmap view.
9. [ ] Define and evaluate transparent cold-start peer-group rules.
10. [ ] Add correction exports for source-row and product-metadata issues.
11. [x] Review the foundation implementation against the Milestone 11 scenario
    suite before approving any forecasting model.

## Foundation Review Evidence

The UCI Online Retail II profile inspected 1,067,371 transactions and exercised
the foundation over 68,720 rows from the 25 busiest product codes. Eleven of
those products contained negative quantities without cancellation status and
were restricted rather than silently repaired. The source also lacked stockout,
unit, and complete-export evidence, so remaining products stayed limited and
2,174 absent product dates remained unknown. These outcomes support the accepted
evidence boundary and identify negative-adjustment semantics and product active
periods as required design gates before baseline forecasting.

## References

The baseline, adaptive-granularity, and evaluation decisions that refine this
contract are recorded in
`docs/architecture/ADR-008-product-demand-baseline-evaluation.md`.

- AWS, “Predefined Dataset Domains and Dataset Types”:
  https://docs.aws.amazon.com/forecast/latest/dg/howitworks-domains-ds-types.html
- AWS, “Handling Missing Values”:
  https://docs.aws.amazon.com/forecast/latest/dg/howitworks-missing-values.html
- AWS, “Using Item Metadata Datasets”:
  https://docs.aws.amazon.com/forecast/latest/dg/item-metadata-datasets.html
- Hyndman and Athanasopoulos, “Determining what to forecast”:
  https://otexts.com/fpp3/determining-what-to-forecast.html
- Hyndman and Athanasopoulos, “Very long and very short time series”:
  https://otexts.com/fpp3/long-short-ts.html
- Hyndman and Athanasopoulos, “Time series cross-validation”:
  https://otexts.com/fpp3/tscv.html
- Hyndman and Athanasopoulos, “Forecasting hierarchical and grouped time series”:
  https://otexts.com/fpp3/hierarchical.html
- AWS, “Using Related Time Series Datasets”:
  https://docs.aws.amazon.com/forecast/latest/dg/related-time-series-datasets.html
- Google People + AI Guidebook, “Explainability + Trust”:
  https://pair.withgoogle.com/guidebook-v2/chapter/explainability-trust/
- GOV.UK Design System, “Help users to recover from validation errors”:
  https://design-system.service.gov.uk/patterns/validation/
