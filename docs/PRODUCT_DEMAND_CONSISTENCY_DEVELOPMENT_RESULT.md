# Forecast-consistency development result

**Date:** 2026-09-17  
**Gate result:** **Failed**  
**Consequence:** Do not spend a fresh cohort on this rule; no live change

## Main idea

Requiring a forecasting method to beat zero in every one of three separate
historical periods was too strict. It removed the known weak sparse forecast,
but it also removed many forecasts that remained useful on subsequent
development-validation weeks.

The rule and advancement conditions were recorded in
[the plan](MILESTONE_11B_6_CONSISTENCY_DEVELOPMENT_PLAN.md) before scoring.

## Results

| Policy | Shown weeks | Coverage | Shown-week WAPE | Skill vs zero |
|---|---:|---:|---:|---:|
| Current control | 247/312 | 79.17% | 44.09% | 55.91% |
| Three-block consistency | 143/312 | 45.83% | 40.35% | 59.65% |

The candidate removed 104 currently permitted forecast-weeks. Those removed
forecasts had 56.14% WAPE but still achieved **43.86% positive skill versus
zero**. The predeclared rule required removed forecasts to have aggregate skill
at or below zero. The advancement gate therefore failed.

The candidate retained no sparse previews, but that safety gain came with large
coverage losses elsewhere:

- delayed-start coverage fell from 100% to 50%;
- intermittent coverage fell from 100% to 50%;
- dense coverage fell from 100% to 83.33%; and
- sparse coverage fell from 16.67% to 0%.

## Real-life interpretation

Imagine a shop forecasting bread, soft drinks, and a special cake. The rule
correctly hides the unreliable cake forecast. But it also hides some bread and
drink forecasts because each had one historical period where zero happened to
win—even though those forecasts were substantially better than zero over the
later validation weeks.

That is safer in one narrow sense, but not a good overall trade-off.

## Decision

Do not advance this exact three-block rule to untouched validation. Do not tune
the block count or size using these results and rescore the same validation
weeks as if they were fresh.

Keep the existing output as **Preview — not decision-ready** and preserve the
known sparse-demand limitation. Better next evidence should come from real or
independent business data and structured context—especially stockouts,
promotions, holidays, closures, and product lifecycle—not repeated threshold
mining on M5.

## Verification

- 65 focused backend checks passed.
- Ruff lint/format and mypy passed for the evaluator.
- Two complete runs produced identical evidence: SHA-256
  `9fb4f2a076ffdaa95b3d2fb29a40bc3679a1763d70daa69b90971228006db417`.
- The live API, frontend, trust policy, and forecasting formulas are unchanged.
- Full generated evidence is in the git-ignored
  `data/public/product_demand_global_consistency_development.json`.

## Next checkpoint

The project should stop trying to derive a universally safe sparse forecast
from the current sales-only M5 evidence. Product-demand remains a transparent,
evaluated preview feature. The next flagship phase can proceed toward the
bounded RAG/explanation prerequisites while independent-business demand evidence
remains a documented release requirement.
