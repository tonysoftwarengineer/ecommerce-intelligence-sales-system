# Sparse-abstention fresh validation

**Date scored:** 2026-09-17  
**Protocol:** `milestone-11b-5-sparse-abstention-v1`  
**Gate result:** **Failed**  
**Release status:** No live policy change; supported use remains unapproved

## What we tested

The protocol in
[Milestone 11B-5](MILESTONE_11B_5_SPARSE_ABSTENTION_VALIDATION_PLAN.md)
was written before scoring. It selected 48 M5 item-store products—twelve per
descriptive demand stratum—with zero overlap with the 24 development products
or 48 products used in the earlier locked evaluation. Each product's final 13
weeks was hidden while the method, current approval, and training-sparse flag
were frozen.

The candidate added one rule to the current gate: withhold a product forecast
when at most 10% of its known training days had positive demand. It did not
change forecast formulas, non-sparse permissions, category fallback, or UI.

## Results

| Policy | Shown weeks | Coverage | Shown-week WAPE | Skill vs zero |
|---|---:|---:|---:|---:|
| Current control | 507/624 | 81.25% | 30.12% | 69.88% |
| Sparse-abstention candidate | 481/624 | 77.08% | 29.85% | 70.15% |

Eleven of the 48 products met the training-only sparse definition. The existing
gate had already withheld nine of them. The candidate removed the remaining 26
weekly previews from two products. Those removed forecasts had 122.06% WAPE and
-22.06% skill versus zero, so withholding them was directionally useful.

However, the predeclared gate required retained forecasts to beat zero in every
descriptive stratum that produced forecasts. The candidate retained thirteen
weekly forecasts for one product in the sparse stratum. Those forecasts had
125% WAPE and -25% skill versus zero. The gate therefore failed with reason
`candidate_did_not_beat_zero_in_sparse`.

## Real-life interpretation

Imagine a shop labels a special cake as “rarely sold” only when it sells on 10%
or fewer of its recorded days. The rule successfully hides two weak cake
forecasts. Another cake sits just above that cutoff during the history available
at decision time, so the rule lets it through—even though its future behavior is
still sparse and its forecast performs poorly.

For the retained M5 item `HOUSEHOLD_2_204_CA_1_evaluation`:

- historical skill before validation was only about **2.18%**;
- it was not training-sparse under the fixed 10% definition;
- actual sales across the 13 future weeks totalled **3 units**;
- its weekly predictions totalled **0.75 units**, but happened at the wrong times;
- total absolute forecast error was **3.75 units**, versus **3 units** for zero.

The failure is not that abstention is inherently wrong. The tested binary rule
was not sufficient to identify every unstable low-demand case without future
knowledge.

## Why we will not “just raise the percentage”

Changing 10% after observing this cohort would tune the rule to the test data.
This cohort is now evaluation-only. A 12%, 15%, or other revised cutoff would
need development justification, a new written protocol, and another untouched
cohort. Otherwise the apparent improvement would not be trustworthy.

## Gate details

- Non-sparse permissions and selected methods were unchanged: passed.
- Candidate forecasts beat zero overall: passed.
- Retained delayed-start, dense, and intermittent strata beat zero: passed.
- Retained sparse-stratum forecasts beat zero: **failed**.
- Removed training-sparse forecasts were no better than zero: passed.
- Identity overlap and source hash checks: passed.
- Two complete runs produced identical evidence after excluding elapsed time:
  SHA-256 `2c2b442e2f9a6628bb0ca2d0efb0b6c0fa5c908853eb970f2ffc89e1157b414f`.

## Verification and consequence

- 59 focused backend checks passed, including the new policy gate, temporal
  isolation, trust policy, locked evaluation, category fallback, and ten-CSV pack.
- Ruff lint/format and mypy passed for the new evaluator.
- The live API and dashboard remain unchanged.
- Full generated evidence is in the git-ignored
  `data/public/product_demand_sparse_abstention_fresh_validation.json`.

ADR-012 is rejected in its tested form. The next design checkpoint is whether
to test a consistency-based safeguard on development evidence and then under a
new locked protocol, or keep all sparse/unstable results preview-only under the
current policy while gathering independent-business data. No new policy should
be implemented before that decision.
