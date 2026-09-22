# Sparse-demand policy comparison: development experiment

**Status:** Evaluation-only; no release policy change authorized  
**Date:** 2026-09-15  
**Decision owner:** Project owner, after reviewing the evidence

## Question and constraints

Can a small extra consistency check reduce weak sparse-product previews without
unnecessarily removing useful forecasts? Compare against the unchanged ADR-010
policy and explicit sparse-product abstention. Do not add models, tune on the
previous locked cohort, or enable decision-ready output.

## Protocol recorded before scores

- Reuse exactly the 24 M5 development products recorded in the public evaluation.
  Verify IDs and source hashes; exclude the 48 previously locked products.
- Reserve each development product's final 13 weeks for **development validation**.
  These products and observations have already informed earlier work: this is
  not a new untouched test set and cannot be presented as release proof.
- Select the method and policy permission using only preceding training history.
  Freeze that choice for 13 weekly predictions; the method can consume completed
  weeks as time advances, but the policy cannot inspect future outcomes.
- Define an exploratory sparse flag from **training history only**: at most 10%
  of included daily targets are positive. This is a research threshold inherited
  from descriptive sampling, not a standard or accepted production requirement.
- **Current control:** unchanged historical trust gate.
- **Consistency candidate:** current gate plus, for sparse products, strictly
  positive skill versus zero in each of the most recent three disjoint blocks
  of 13 shared historical weeks. Insufficient blocks or a perfect zero benchmark
  fails this extra check. Non-sparse products retain the current gate.
- **Abstention candidate:** current gate, but withhold all training-sparse products.
- Do not sweep thresholds or change these definitions after seeing results.

## Category fallback is a separate scope

The existing guarded category path is an alternative user experience, not a
replacement product model. A sampled M5 product cohort does not establish complete
category membership for a business. Therefore do not combine unrelated stores or
partial departments and call that a validated category forecast.

Use the ten-CSV category scenario to verify the existing fallback behavior and
confirmation gate. It demonstrates function, not independent category accuracy.
Real category comparison requires complete membership, compatible units, and
separate time-based evaluation. Do not revise ADR-011's overlap rule here.

## Report and trade-offs

Report preview coverage, shown-week MAE/WAPE/skill versus zero, directional error,
and the same evidence split by training-sparse/non-sparse group. Also score the
control forecasts removed by each candidate: this reveals whether a rule removes
helpful forecasts as well as harmful ones. No shown forecasts means accuracy is
undefined, **not** perfect or successful. Do not compare accuracy alone without
coverage: abstaining changes which products are scored.

The extra blocks may over-restrict new products. Historical consistency may still
fail under changing demand. Blanket abstention is simple but removes any useful
sparse predictions. Category fallback loses per-product planning detail.

## Verification plan

| Area | Test type | Required cases |
|---|---|---|
| Consistency arithmetic | Unit | mixed positive blocks, a tie, perfect zero, insufficient weeks |
| Sparse flag | Unit | exact boundary, non-sparse, all zero, unknown targets |
| Approval isolation | Unit | no gate bypass; changing future targets cannot change initial decisions |
| Metrics | Unit | no-preview group has null accuracy; directional errors do not cancel |
| Data lineage | Experiment assertion | exact development IDs/hashes and zero locked overlap |
| Repeatability | Reproduction | identical evidence on two runs |
| Category behavior | Existing regression | passing fallback and missing confirmation |

Next: review findings with the owner; propose an ADR only after the comparison.
Any accepted revision still requires a new protocol and new untouched validation.

## Methodological reference

[Forecasting: Principles and Practice — time-series cross-validation](https://otexts.com/fpp3/tscv.html)
supports training on earlier observations and evaluating future multi-step forecasts.
It does **not** prescribe our exploratory 10% flag or three-block rule.
