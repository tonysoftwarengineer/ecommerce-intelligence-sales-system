# ADR-009: Product-Demand Trust and Granularity Gate

**Status:** Accepted  
**Date:** 2026-09-02  
**Deciders:** Project owner

## Context

Milestone 11A defined safe product-demand semantics. Milestone 11B-1 built and
tested transparent baselines with rolling-origin evaluation, directional errors,
synthetic scenarios, UCI Online Retail II, and M5.

Step 7 reviewed 38 public product series. The review found useful weekly evidence
for UCI and most M5 products, but also found that:

- all selected daily methods repeated a flat value across seven dates;
- 14 products had daily RMSSE above 1;
- only 18 retained the same best daily method across early and recent history;
- five of six sparse M5 products had weekly error worse than forecasting zero;
- the three-fold engine minimum was not tested by public series, whose minimum
  was 57 folds; and
- the approved intermittent-demand candidate remains unimplemented.

The system must avoid false daily precision and must not expose a weekly forecast
that fails a trivial zero benchmark. At the same time, blocking every forecast
would discard useful evidence from products where simple weekly methods were
materially better than zero.

## Decision

### 1. Do not approve daily product forecasts for 11B-2 v1

- The first user-facing product-demand output, when eligible, is a seven-day
  total.
- An average daily planning rate may be shown only when labelled as an average,
  not as seven separate date predictions.
- Per-date forecasts remain deferred until a date-varying candidate demonstrates
  out-of-sample skill over a flat allocation of the weekly total and remains
  stable across historical subperiods.

### 2. Do not approve a universal weekly forecast yet

Before 11B-2, add a bounded 11B-1 extension:

1. Add the zero forecast as an explicit seven-day-total benchmark and skill gate.
   It remains benchmark-only and cannot silently become the user-facing method.
2. Implement and evaluate an SBA/Croston expected-rate candidate for sparse and
   intermittent products.
3. Compare daily-shape methods against a flat `weekly_total / 7` allocation so
   daily precision must add measurable value.
4. Run history-length sensitivity at several completed-fold counts. These are
   experiment points, not preselected trust thresholds.
5. Re-run scenario, UCI, and M5 reviews before accepting production policy.

### 3. Preserve three explicit trust states

- **Unavailable:** target semantics, product identity, units, recent activity,
  or evaluation truth are unsafe. Show no numeric forecast; explain the blocker
  and how to correct the data.
- **Limited preview:** semantics are valid and a non-benchmark method shows
  positive shared-fold skill, but history, stability, bias, or coverage has not
  passed an accepted supported-use policy. A seven-day estimate may be shown only
  with a strong `Preview — not decision-ready` warning and adjacent evidence.
- **Supported weekly:** reserved for a later accepted threshold policy after the
  extension above. No current code assigns this state.

Sparse products whose weekly candidate does not beat zero remain unavailable for
a numeric forecast, not merely low confidence.

### 4. Keep forecast and stocking decisions separate

- The forecast remains a neutral estimate of observed fulfilled units.
- Waste, stockout, margin, shelf-life, and service-level costs remain outside
  model selection until supported by business evidence.
- Reorder quantities, safety stock, and ingredient conversion remain deferred.

## Options Considered

### Option A: Release evidence-selected daily forecasts now

| Dimension | Assessment |
|---|---|
| User detail | High |
| Evidence fidelity | Low |
| False-precision risk | High |
| Additional work | Low |

**Pros:** Immediately provides date-level numbers.  
**Cons:** Every public winner was flat within the week, daily RMSSE failed for
14 products, and method stability was weak.

### Option B: Extend evaluation, then release evidence-gated weekly totals

| Dimension | Assessment |
|---|---|
| User detail | Medium |
| Evidence fidelity | High |
| Sparse-demand safety | High after extension |
| Additional work | Medium |

**Pros:** Preserves useful planning value, avoids false daily precision, and
forces sparse methods to beat meaningful benchmarks.  
**Cons:** Delays the dashboard feature and requires another evaluation cycle.

### Option C: Block every forecast until an advanced ML model exists

| Dimension | Assessment |
|---|---|
| Safety | High |
| Learning value | Low to medium |
| Evidence use | Low |
| Delivery delay | High |

**Pros:** Avoids releasing an underdeveloped forecast.  
**Cons:** Ignores strong simple-baseline evidence and wrongly treats complexity
as a prerequisite for quality.

## Trade-off Analysis

Option B is recommended. Option A offers detail that the evaluated methods do
not actually produce. Option C confuses model sophistication with reliability.
Option B keeps the project evidence-led: weekly value is retained where earned,
while sparse and daily outputs remain behind explicit tests.

No exact minimum fold count, bias percentage, or skill margin is accepted in
this ADR. The current data does not calibrate those values. They must be proposed
after the history-length and intermittent-demand extension, not chosen to make
the current methods pass.

## Consequences

- Milestone 11B-2 remains unapproved.
- The next coding work remains backend evaluation, not dashboard development.
- Flat averages cannot be presented as date-specific forecasts.
- Sparse demand gets a method appropriate to occurrence-and-size behavior before
  user-facing output.
- The project gains a stronger portfolio narrative: a public-data review rejected
  premature UI delivery and changed the architecture based on measured failure.

## Action Items

1. [x] Project owner accepted Option B on 2026-09-02.
2. [x] Add a weekly zero benchmark and benchmark-relative skill evidence. The
   typed gate compares the selected method and zero on identical historical
   weeks, passes only on strictly positive skill, and explicitly says that a
   pass is necessary but not full forecast approval.
3. [x] Implement and test SBA/Croston behind the existing candidate boundary.
   The fixed-parameter weekly candidate won 11 UCI and 8 M5 products, but did
   not convert any of the five M5 zero-gate failures into passes.
4. [x] Add flat-allocation daily-shape comparison. Holding the selected weekly
   total constant, the date-varying candidate was worse than flat for all 14 UCI
   products and 20 of 24 M5 products; only two M5 products had positive skill
   in both history halves. Daily output remains unapproved.
5. [x] Run history-length sensitivity experiments. Fixed 13-fold holdout results
   at 3, 6, 13, and 26 selection folds were not monotonic. UCI passed throughout,
   while only one or two of six sparse M5 products passed. Fold count alone is
   not accepted as a sufficient trust rule.
6. [x] Re-run the full evidence review and propose the bounded preview policy in
   ADR-010. No supported-use threshold is claimed from retrospective evidence.
7. [x] Approve the preview-only 11B-2 boundary through accepted ADR-010. API and
   dashboard implementation remain separate action items.
