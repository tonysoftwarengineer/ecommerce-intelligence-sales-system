# Milestone 11B-3: Guarded Category Fallback

**Status:** Implementation complete; preview-only validation remains  
**Decision:** ADR-011

## Objective

Show one evidence-gated category-level seven-day demand preview when every
product in that category is individually unavailable, without manufacturing
product forecasts or changing the current preview trust policy.

## Loop 1: Design and contracts

- Add explicit category confirmation to product-demand assumptions.
- Prepare categories only from mapped canonical category values.
- Reject ambiguous product-category identity, fewer than two products,
  semantically unsafe members, and incompatible units.
- Keep product and category results typed and separately labelled.

## Loop 2: Minimal vertical slice

- Aggregate safe product calendars into one category calendar.
- Reuse the weekly baseline evaluator, zero benchmark, and trust policy.
- Add category results to the existing opt-in endpoint.
- Add one dashboard confirmation and category fallback presentation.

## Loop 3: Verification

- Products fail while category passes.
- Product passes, so category fallback is suppressed.
- Missing confirmation or category data produces correction guidance.
- Conflicting categories, too few products, and incompatible units show no
  numeric category forecast.
- API contract and browser journey preserve the preview warning and forecast
  level.
- Run the full backend and browser suites, lint, formatting, typing, and build.

## Deferred deliberately

- AI-generated category assignments.
- Allocating a category forecast to individual products.
- Whole-business operational demand.
- Simultaneous multi-level forecasts and reconciliation.
- Supported or decision-ready forecasting language.
