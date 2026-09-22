# ADR-011: Guarded Category-Demand Fallback

**Status:** Accepted  
**Date:** 2026-09-08  
**Deciders:** Project owner

## Context

The product-demand preview correctly withholds numbers for sparse products that
cannot beat the zero-demand benchmark. The restaurant evaluation demonstrated a
real limitation: every individual menu item can be too intermittent even when a
broader product category has regular demand.

A broader forecast must not be presented as an individual-product forecast. It
must also avoid independent product and category numbers that contradict each
other. Forecast reconciliation is the standard solution when forecasts are
shown at several levels, but it is unnecessary complexity for the first
fallback experiment.

## Decision

Add an opt-in, fallback-only category preview to the existing product-demand
endpoint and dashboard.

A category is eligible for evaluation only when:

1. the uploaded canonical data contains a mapped product-category field;
2. the user confirms the product-to-category assignments in one bulk action;
3. the category contains at least two distinct, resolved products;
4. every product belongs to exactly one category;
5. all category members have safe product semantics and one compatible unit of
   measure; and
6. none of the category's products has an eligible product-level preview.

An eligible category reuses the existing seven-day baseline leaderboard,
rolling-origin evaluation, thirteen-shared-fold evidence floor, and strictly
positive skill-versus-zero gate. A passing result remains a limited preview.
It predicts only the category total and is never divided among products.

If any product in a category has a product-level preview, the category fallback
is omitted. This keeps version one fallback-only and avoids presenting
unreconciled forecasts at two levels. Whole-business operational demand,
AI-generated category labels, product allocation, and multi-level forecast
reconciliation remain out of scope.

## Options Considered

### Option A: Keep every sparse product unavailable

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Safety | Highest |
| Usefulness on sparse portfolios | Low |

**Pros:** No additional forecast interpretation.  
**Cons:** Discards potentially stable category-level evidence.

### Option B: Add guarded fallback-only category previews

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Safety | High |
| Reuse of existing evidence pipeline | High |

**Pros:** Adds useful aggregate evidence without inventing product allocations
or showing conflicting levels.  
**Cons:** A category forecast is intentionally hidden when any member product
already has an eligible preview.

### Option C: Show independently generated product and category forecasts

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Coherence | Low |
| User confusion risk | High |

**Pros:** Shows more numbers.  
**Cons:** Product forecasts may not sum to category forecasts.

### Option D: Implement full forecast reconciliation now

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Coherence | High |
| Current evidence need | Unproven |

**Pros:** Can support consistent forecasts at several hierarchy levels.  
**Cons:** Expands modelling, evaluation, and explanation scope before the simple
fallback has been validated.

## Trade-off Analysis

Option B is accepted. It is the smallest change that addresses sparse product
portfolios while preserving the existing trust boundary. Option A remains the
behavior when category evidence is unsafe. Option C is misleading without
reconciliation. Option D is deferred until fallback evaluation demonstrates
that simultaneous multi-level forecasts are valuable.

## Consequences

- Category fallback is optional and requires explicit user confirmation.
- Existing product previews and the revenue forecast remain unchanged.
- Category and product numbers are not shown together for the same category.
- Missing, conflicting, or incompatible category data produces explanations,
  not guessed repairs.
- A future ADR is required before AI category inference, top-down allocation,
  or reconciled multi-level forecasting.

## Action Items

1. [x] Add typed category preparation and result contracts.
2. [x] Reuse the existing evaluation and trust gates for eligible categories.
3. [x] Extend the API response without changing existing product fields.
4. [x] Add a bulk category-confirmation control and category cards.
5. [x] Add focused domain, API, and browser tests.
6. [ ] Evaluate the fallback on locked and varied datasets before changing its
       preview-only status.
