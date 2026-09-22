# ADR-008: Product-Demand Baselines, Adaptive Granularity, and Evaluation

**Status:** Accepted  
**Date:** 2026-08-31  
**Deciders:** Project owner

## Context

Milestone 11A established product identity, unit semantics, lifecycle-aware
fulfilled units, per-product readiness, and an auditable product-date calendar.
It deliberately did not produce forecasts.

Before Milestone 11B model code, four remaining decisions were reviewed with the
project owner:

1. whether negative quantities may enter demand training;
2. how product activation and discontinuation are handled without asking users
   to investigate every historical row;
3. whether the user receives daily values or only a seven-day total; and
4. how over-forecasting and under-forecasting are evaluated without evidenced
   business-cost weights.

The system must remain useful for small businesses while avoiding silent data
repair, false daily precision, future leakage, or thresholds tuned to one public
dataset.

## Decision

### Negative quantities

- A negative quantity never enters the `fulfilled_units` training target as
  negative demand.
- The original source row is preserved because the sign may represent a return,
  cancellation, damage, or inventory correction.
- A confirmed pre-fulfilment cancellation contributes zero fulfilled units.
- A confirmed return is tracked separately as returned units and does not erase
  an earlier fulfilled sale.
- A confirmed inventory adjustment is excluded from the demand target and may
  later feed an inventory-specific feature.
- If the meaning is not confirmed, the affected product is unavailable. The
  system groups affected rows by source field and source value rather than asking
  the user to classify every row independently.

### Product active periods

- The first observed sale is the beginning of the **observed sales window**, not
  proof of the product's launch date.
- Dates before the first observed sale are never silently zero-filled.
- A mapped launch date, discontinued date, or catalogue status may establish the
  active period after validation.
- Without catalogue metadata, the interface asks a grouped question such as
  whether all mapped products are currently active, then lets the user identify
  exceptions. “I am not sure” remains valid and restricts affected forecasts.
- A product is not forecast beyond the dataset end unless its current active
  status is supported. The system must not make the user search every historical
  record to establish this.
- The first implementation records the evidence contract and grouped result; it
  does not invent a stale-product threshold.

### Adaptive daily versus seven-day output

- The planning horizon remains the next seven days.
- Confirmed zero-sale days remain zero in evaluation. The system never replaces
  every zero with the average of nonzero selling days.
- Daily and seven-day forecasting are evaluated separately because their errors
  answer different operational questions.
- Daily values are shown only when rolling-origin tests demonstrate stable
  day-level skill. Otherwise the system shows an evaluated seven-day total.
- An average daily planning rate may accompany a seven-day total, but it is
  labelled as an average and never presented as a prediction for each date.
- Sparse and intermittent series receive methods that preserve demand occurrence
  and size information. A Croston/SBA-style candidate may enter the experimental
  comparison only after the simple baseline harness is verified.

### Neutral forecast and separate error directions

- The forecast remains a neutral estimate of expected fulfilled units.
- Overall error, over-forecast units, under-forecast units, and directional bias
  are reported separately.
- MAE in product units is the primary business-readable error.
- RMSSE is the initial scale-independent comparison metric when its denominator
  is defined. Percentage error is not the primary per-product metric because
  intermittent series often contain zero actual values.
- Seven-day total error is reported separately from day-level error.
- Without evidenced waste, stockout, margin, shelf-life, or service-level costs,
  over-forecasting and under-forecasting receive no hidden business weighting.
- A future stocking policy may use asymmetric costs or a conservative service
  level, but that policy remains separate from the neutral forecast.

### Rolling-origin evaluation and selection

- Every evaluation origin trains only on dates before its seven-day test window.
- Test windows advance in non-overlapping seven-day steps for the first
  implementation. The engine retains each fold result rather than only a final
  average.
- Daily candidates and seven-day-total candidates have separate leaderboards.
- Candidate eligibility is based on each method's natural history requirements
  and usable observations, not the monthly-revenue six-month rule.
- The evaluation engine reports results before any production trust threshold is
  accepted. Thresholds are calibrated across deterministic scenarios and more
  than one public dataset.
- Within one leaderboard, the primary scaled error selects the best eligible
  candidate. Lower absolute bias and then lower model complexity are deterministic
  tie-breakers.
- A zero forecast is retained as an evaluation benchmark for intermittent data,
  but it cannot become user-facing merely by exploiting an error metric that
  rewards frequent zeroes.

### Two implementation gates

Milestone 11B is divided into:

1. **11B-1 — Evaluation engine:** contracts, baselines, rolling-origin folds,
   metrics, scenario evaluation, and public-data reports. No API or dashboard
   forecast is added.
2. **11B-2 — Calibrated forecast product:** trust/coverage thresholds, per-product
   daily-versus-weekly policy, API contracts, grouped confirmations, correction
   guidance, and dashboard evidence. This begins only after an explicit review
   of 11B-1 results.

## Options Considered

### Option A: Fill every day from the nonzero-day average

| Dimension | Assessment |
|---|---|
| Simplicity | High |
| Weekly-total bias | Potentially severe |
| Daily realism | Low |
| Intermittent-demand fidelity | Low |

**Pros:** Easy to explain and implement.  
**Cons:** Can multiply a few selling-day quantities across all seven days and
substantially over-forecast demand.

### Option B: Always show a seven-day total

| Dimension | Assessment |
|---|---|
| Reliability | Medium to high |
| Operational usefulness | Medium |
| Complexity | Low |
| Daily preparation support | Low |

**Pros:** Avoids false daily precision.  
**Cons:** Withholds useful day-level information from products that genuinely
have stable weekday patterns.

### Option C: Evidence-selected granularity

| Dimension | Assessment |
|---|---|
| Reliability | High after calibration |
| Operational usefulness | High where evidence supports it |
| Complexity | Medium |
| Auditability | High |

**Pros:** Gives daily detail only when it earns evidence and retains a safe
seven-day fallback.  
**Cons:** Requires two evaluation views, explicit calibration, and more typed
evidence.

## Trade-off Analysis

Option C is accepted. Option A creates false precision and can inflate the total.
Option B is safe but unnecessarily limits products with predictable weekday
patterns. Evidence-selected granularity keeps the operational value while making
uncertainty visible.

The two-gate sequence increases delivery time, but it prevents evaluation policy
from being reverse-engineered around whichever model happens to be implemented
first. It also creates stronger portfolio evidence: the project can show the
baselines, fold-level results, rejected methods, and the reason a forecast is or
is not user-facing.

## Consequences

- Milestone 11B-1 produces an evaluation artifact, not a dashboard feature.
- Daily and seven-day metrics cannot be collapsed into one score.
- Product activity becomes a separate evidence contract from first sale.
- Negative source rows remain auditable without contaminating fulfilled demand.
- Metric edge cases, especially all-zero series and undefined RMSSE denominators,
  require explicit unavailable or benchmark-only states.
- Trust thresholds remain open until cross-scenario evidence is reviewed.
- Stocking recommendations remain out of scope.

## Action Items

1. [x] Define typed evaluation, fold, metric, candidate, and date-preserving
   evaluation-series contracts.
2. [ ] Extend activity evidence without adding per-product confirmation friction.
3. [x] Implement simple daily and seven-day baselines with explicit natural
   history and recent-window exclusion failures.
4. [x] Implement rolling-origin seven-day evaluation with expanding-window,
   non-overlap, future-shock leakage, and retained-exclusion tests.
5. [x] Add zero-safe metrics, RMSSE scale evidence, separate directional errors,
   and shared-fold daily/weekly evaluation-only leaderboards.
6. [ ] Add the intermittent-demand candidate behind the evaluation boundary.
7. [x] Run deterministic scenario, UCI, and M5-sample evaluations. The twelve
   deterministic scenarios and both public-data evaluations completed on
   2026-09-02; findings are recorded without production thresholds.
8. [x] Review result distributions and propose the next trust/granularity gate.
   Step 7 found that exact thresholds are not yet calibrated and recorded the
   required 11B-1 extension in proposed ADR-009.
9. [ ] Approve 11B-2 separately before adding API or dashboard forecasts.

## References

- Hyndman and Athanasopoulos, “Time series cross-validation”:
  https://otexts.com/fpp3/tscv.html
- Hyndman and Athanasopoulos, “Time series of counts”:
  https://otexts.com/fpp3/counts.html
- Makridakis, Spiliotis, and Assimakopoulos, “M5 accuracy competition: Results,
  findings, and conclusions”:
  https://doi.org/10.1016/j.ijforecast.2021.11.013
- AWS, “Handling Missing Values”:
  https://docs.aws.amazon.com/forecast/latest/dg/howitworks-missing-values.html
