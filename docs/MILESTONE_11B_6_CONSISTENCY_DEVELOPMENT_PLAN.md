# Milestone 11B-6: Forecast-consistency development comparison

**Status:** Protocol recorded before scoring  
**Date:** 2026-09-17  
**Release status:** Development experiment only; no live policy change

## Main idea

A forecasting method should not qualify merely because one unusually successful
period makes its overall historical average look good. Test an additional rule:
the selected method must beat zero separately in each of the three most recent
non-overlapping blocks of 13 shared historical test weeks.

## Scope and fixed rule

- Reuse the 24 previously scored M5 development products only.
- Preserve the current data-safety rules, model formulas, model selection,
  minimum 13 shared weeks, and overall positive-skill requirement.
- Apply the additional consistency check to **every product**, not only products
  below a sparsity cutoff. This avoids another binary sparse threshold.
- Each block compares the selected method and zero on exactly the same weeks.
- Every block must have positive skill. A tie, a perfect zero benchmark, or fewer
  than 39 shared weeks causes abstention.
- Hold out each product's final 13 weeks for development validation, exactly as
  in the earlier development comparison. This is not fresh evidence.
- Do not change the three-block definition after scores are viewed.

## Evidence and advancement conditions

Report coverage, MAE, WAPE, skill versus zero, and directional errors for current
and retained forecasts. Separately score forecasts removed by the consistency
rule.

Advance the rule to a fresh protocol only if:

1. retained forecasts beat zero overall and in every descriptive stratum that
   still has shown forecasts;
2. forecasts removed by the rule have aggregate skill at or below zero;
3. the rule never adds a forecast that the current gate withheld; and
4. the result and checks reproduce exactly.

No minimum coverage threshold is invented. Coverage loss remains a visible
trade-off. If no forecast remains, accuracy is undefined and the result is
inconclusive—not successful.

## Stopping rule

If consistency removes forecasts that still add value, do not immediately tune
the number or size of blocks. Record the failure and retain the current
preview-only policy while seeking better evidence, such as independent-business
data, structured stockouts, promotions, holidays, and product lifecycle context.

Category fallback accuracy and RAG remain separate work.
