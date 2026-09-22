# Milestone 11B-5: Fresh sparse-abstention validation

**Protocol status:** Locked before scoring  
**Lock date:** 2026-09-17  
**Release status:** Evaluation-only; no live policy change authorized

## Decision being tested

Test explicit abstention as a candidate safeguard: when no more than 10% of a
product's known training days have positive fulfilled-unit demand, do not show
that product's numerical forecast. Do not alter model formulas, model selection,
the existing historical gate, non-sparse behavior, category fallback, or
preview-only wording.

The 10% boundary is an exploratory candidate inherited from the project's M5
sampling strata. It is not an industry standard or an accepted production rule.

## Untouched cohort

- Source: the locally hashed M5 sales and calendar files already documented.
- Exclude all 24 development products and all 48 previously locked products.
- Select 12 different item-store series from each existing descriptive stratum
  using fixed seed `milestone-11b-sparse-abstention-v1` (48 products total).
- Hold out each product's final 13 complete seven-day windows.
- Assert zero overlap with every previously scored development or locked ID.

The data source is not a new business or industry. It is fresh product and
future-time evidence within M5, so it can test this bounded candidate but cannot
approve supported or decision-ready forecasting.

## Leakage controls

For each product:

1. Build the sparse flag, select the method, and apply the current trust gate
   using only history before the 13-week holdout.
2. Freeze the current-policy permission, sparse flag, and selected method for
   all 13 weeks.
3. Reveal one future week at a time; update only the selected method's history.
4. Never rerun approval or model selection from holdout outcomes.

## Policies compared

- **Current control:** unchanged ADR-010 behavior.
- **Sparse abstention candidate:** current control plus withholding every
  training-sparse product preview.

Abstention is not a zero forecast. Withheld opportunities have no numerical
prediction and no accuracy score.

## Predeclared evidence

- Product and opportunity counts, preview coverage, and abstention counts.
- MAE, WAPE, skill versus zero, overforecast, and underforecast error for shown
  forecasts overall and by descriptive stratum/training-sparse group.
- Counterfactual quality of current-control forecasts removed by the candidate.
- Exact source hashes, cohort IDs, overlap assertions, and repeatability hash.

## Bounded gate

The candidate advances to an implementation decision only when all hold:

1. Every non-sparse product has exactly the same permission and selected method
   as the current control.
2. The candidate's shown forecasts beat zero overall and in every descriptive
   stratum that still produces forecasts.
3. Current-control forecasts removed by sparse abstention have aggregate skill
   at or below zero on the untouched holdout. If none were shown by the current
   policy, this condition is inconclusive—not passed.
4. No leakage, identity-overlap, source-integrity, or reproducibility check fails.

This gate asks whether blanket abstention removed demonstrably weak forecasts
without harming retained behavior. It cannot prove that all sparse forecasts
are useless, improve sparse prediction accuracy, or validate the 10% boundary
for another business.

## Outcomes

- **Pass:** discuss whether to accept ADR-012 and implement the bounded rule.
- **Fail:** do not tune using this cohort. Return to development evidence and
  create a new protocol/cohort for any revised candidate.
- **Inconclusive:** retain current preview policy and gather better evidence.

Category accuracy, prediction intervals, business-specific stockout/waste cost,
independent-business validation, RAG, authentication, and deployment remain
separate work.
