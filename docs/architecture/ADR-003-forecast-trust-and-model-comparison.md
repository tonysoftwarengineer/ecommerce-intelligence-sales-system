# ADR-003: Forecast Trust and Model Comparison

**Status:** Accepted  
**Date:** 2026-08-18  
**Deciders:** Project owner

## Context

The product already backtests several transparent forecasting methods and
selects the method with the lowest mean absolute error. Previously, the
dashboard showed only the winning method and its metrics. A small-business
user could not verify what was compared, understand why that method won, or
judge whether the forecast should influence a business decision.

The product must remain explainable, inexpensive to run, and conservative:
forecast accuracy is evidence about past tests, not a guarantee of future
sales.

## Decision

Return the eligible model evaluations in the saved analysis response, along
with a deterministic selection reason and a conservative trust assessment.

The dashboard shows the chosen model, every evaluated method's mean error and
WAPE, the reason for the selection, and a trust label. The label considers
both historical error and evidence sufficiency:

- **Limited:** 6–11 complete months; exploration only.
- **Exploratory:** enough history to test, but high error or weak evidence.
- **Moderate:** at least 12 complete months, six rolling tests, and WAPE at or
  below 25%.
- **Strong:** at least 24 complete months, six rolling tests, annual
  seasonality eligible, and WAPE at or below 10%.
- **Unavailable:** the forecast safety requirements were not met.

## Options Considered

### Option A: Show only the winning model and its error

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Low |
| Scalability | High |
| Team familiarity | High |

**Pros:** Compact dashboard and smallest API payload.  
**Cons:** Users cannot audit the choice and may mistake the winner for the
only method.

### Option B: Return a transparent comparison and rule-based trust label

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Low |
| Scalability | High for the current small candidate set |
| Team familiarity | High |

**Pros:** Auditable selection, understandable limitations, no opaque model.  
**Cons:** More dashboard information and thresholds that need periodic review.

### Option C: Use an LLM to score forecast trust

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Ongoing |
| Scalability | Dependent on provider |
| Team familiarity | Medium |

**Pros:** Flexible natural-language explanations.  
**Cons:** Non-deterministic, harder to test, and unsuitable as the source of a
numeric reliability decision.

## Trade-off Analysis

Option B is selected. The current candidate set is deliberately small, so its
comparison payload is tiny. Deterministic thresholds make the label testable
and prevent an LLM from overstating certainty. The UI uses progressive
disclosure: the trust label and explanation appear first, while the comparison
table provides the audit detail.

## Consequences

- Users can see that the system compares methods instead of assuming one.
- A 23.5% WAPE can be presented as moderate only when history and test-fold
  requirements are also met; it is never presented as a guarantee.
- Thresholds are product policy, not universal forecasting standards, and must
  be revisited with real customer-data evaluations.
- Adding more forecasting models later requires only another evaluation row,
  not a dashboard redesign.

## Action Items

1. [x] Add typed model-evaluation, selection-reason, and trust fields.
2. [x] Render the comparison and conservative trust message.
3. [ ] Add real-business forecast evaluation before treating thresholds as
   production policy.
