# Milestone 11B: Product-Demand Baseline Evaluation Plan

**Status:** Milestone 11B-1 complete; ADR-010 accepted; 11B-2 browser vertical slice complete  
**Date:** 2026-09-02  
**Decision record:** `docs/architecture/ADR-008-product-demand-baseline-evaluation.md`

## 1. Outcome

Build a reproducible backend evaluation engine that determines how simple product
demand methods behave across dense, seasonal, sparse, intermittent, missing, and
censored histories.

Milestone 11B-1 does **not** put a product-demand forecast on the API or dashboard.
Its deliverable is evidence: per-product rolling folds, method comparisons,
directional errors, coverage, limitations, and public-data evaluation reports.

## 2. Learning Objective

This phase teaches the separation between:

- a forecasting algorithm;
- an evaluation design;
- a model-selection rule;
- a trust policy; and
- a user-facing operational decision.

Writing a predictor is the smallest part. The AI-engineering work is defining
what the target means, preventing leakage, measuring failures honestly, and
showing only outputs supported by evidence.

## 3. Accepted Design Inputs

- Target: non-negative observed `fulfilled_units` per product.
- Horizon: seven days.
- Product identity and units: Milestone 11A contracts.
- Negative quantities: excluded from the target unless their confirmed lifecycle
  meaning produces a valid non-negative fulfilled quantity.
- Product start: first observed sale is an observation boundary, not a launch
  claim.
- Product end: a future forecast requires current-active evidence.
- Granularity: daily only when evaluated; otherwise a seven-day total.
- Cost policy: neutral forecast, with over- and under-forecast error reported
  separately.

## 4. Scope of 11B-1

### 4.1 Typed contracts

Create contracts under `src/product_demand/` for:

- evaluation configuration;
- candidate identity and natural eligibility requirements;
- one rolling-origin fold;
- daily and seven-day metrics;
- one candidate evaluation;
- one product evaluation report; and
- explicit unavailable reasons.

No response should use untyped nested dictionaries as its domain contract.

### 4.2 Evaluation-ready series

Create a preparation boundary that:

- accepts only `observed` and `confirmed_zero` target values;
- excludes `missing_unknown` from model training and test truth;
- excludes `stockout_limited` because it is censored fulfilled demand;
- excludes `business_closed` from baseline model evidence in 11B-1;
- preserves dates so a method cannot compress gaps and accidentally change time;
- rejects negative target values; and
- records exactly how many dates were included and excluded by status.

Historical closure handling and planned-closure constraints remain a separate
evaluated capability after the baseline engine is trusted.

### 4.3 Initial candidate set

The bounded first comparison is:

| Candidate | Purpose | User-facing eligibility in 11B-1 |
|---|---|---|
| Zero benchmark | Detect whether another method adds value on very sparse demand | Benchmark only |
| Latest-value naive | Minimal daily baseline | Evaluation only |
| Seasonal-naive-7 | Repeat the previous weekday pattern | Evaluation only |
| Moving average 7 | Recent short daily level | Evaluation only |
| Moving average 28 | Smoother four-week daily level | Evaluation only when history permits |
| Last-week total | Minimal seven-day-total baseline | Evaluation only |
| Mean of last 4 weekly totals | Stable recent weekly level | Evaluation only when history permits |
| SBA/Croston expected rate | Intermittent occurrence-and-size candidate | Evaluation only; implemented in extension Step 9 |

The user's proposed nonzero-day average may be represented as a diagnostic
benchmark to demonstrate its total inflation risk, but it is never an eligible
default forecast.

No tree model, neural network, AutoML system, weather feature, holiday feature,
promotion input, or external model service enters 11B-1.

### 4.4 Rolling-origin evaluation

- Forecast exactly seven future dates at each origin.
- Train only on dates before the origin.
- Advance origins in seven-day steps initially, avoiding overlapping test windows.
- Retain fold-level predictions, actuals, dates, and exclusions.
- Evaluate candidates only when their natural history requirements are met.
- Keep minimum-history and minimum-fold settings configurable and visibly marked
  as experimental product policy.
- Do not use the final seven-day holdout to tune thresholds and then report it as
  independent evidence.

### 4.5 Metrics

For each eligible candidate, calculate:

- MAE in product units;
- RMSE in product units;
- RMSSE when the naive-scale denominator is defined;
- seven-day-total absolute error;
- total over-forecast units;
- total under-forecast units;
- signed bias and mean bias;
- number of over-, under-, and exact predictions;
- fold count and evaluated-date count; and
- failure/unavailable reasons.

WAPE may be reported for a portfolio aggregate whose total actual demand is
nonzero, but it is not the primary per-product selector.

### 4.6 Selection evidence

11B-1 may identify the lowest-error candidate in each leaderboard, but the result
is labelled `evaluation_only`.

- Daily and seven-day winners are separate.
- RMSSE is the initial primary comparison when defined.
- If RMSSE is undefined, the report preserves that fact and uses an explicitly
  documented fallback comparison; it never substitutes zero silently.
- Lower absolute bias and then lower complexity break exact metric ties.
- The zero benchmark cannot become the selected user-facing method.
- No daily-versus-weekly trust threshold is accepted until scenario and public
  evaluation distributions are reviewed.

## 5. Implementation Order

### Step 1 — Contract and invariant tests — complete 2026-08-31

Write failing tests for typed results, non-negative targets, excluded calendar
statuses, deterministic output, and source immutability.

Implemented in `src/product_demand/evaluation_contracts.py` and
`src/product_demand/evaluation_series.py`. The boundary retains every calendar
date, includes only observed and confirmed-zero targets, and represents closures,
stockouts, and unknown dates as explicit exclusions rather than compressed time
or invented zeroes. Verification: all 195 non-integration backend tests passed
(4 deselected), with Ruff and mypy clean.

**Learning question:** What must be true for every model, regardless of its
formula?

### Step 2 — Baseline functions — complete 2026-08-31

Implement pure predictors with explicit minimum-history errors. Keep methods
stateless and dependency-light.

Implemented seven bounded candidates in `src/product_demand/baselines.py`: zero
benchmark, latest value, seasonal naive 7, moving averages 7 and 28, last-week
total, and mean of four weekly totals. Each formula uses its required recent
calendar window, fails explicitly when that window contains excluded dates, and
returns an immutable seven-date forecast. SBA/Croston remains deferred until the
rolling evaluation harness passes. Verification: all 215 non-integration backend
tests passed (4 deselected), with Ruff and mypy clean.

**Learning question:** Why can a simple baseline be more valuable than an
advanced model during system development?

### Step 3 — Rolling-origin engine — complete 2026-08-31

Generate seven-day folds without future leakage and retain fold evidence.

Implemented in `src/product_demand/rolling_evaluation.py` with expanding training
windows and non-overlapping seven-day test windows. Each completed fold retains
its training boundary, forecast dates, predictions, and actuals. A fold blocked
by an unknown, closure, stockout, or required-history issue is retained separately
with its phase, affected dates, statuses, and reason. Candidate-level availability
requires the configured experimental minimum fold count. Verification: all 224
non-integration backend tests passed (4 deselected), with Ruff and mypy clean.

**Learning question:** Why is random train/test splitting invalid for forecasting?

### Step 4 — Metrics and leaderboard — complete 2026-08-31

Calculate zero-safe, unit-readable, directional, and horizon-total metrics. Add
deterministic selection evidence without production trust labels.

Implemented in `src/product_demand/metrics.py`. Daily evidence includes MAE,
RMSE, RMSSE with its adjacent-pair scale evidence, overforecast units,
underforecast units, signed/mean bias, and direction counts. Weekly evidence
measures the same operational direction around seven-day totals. RMSSE remains
undefined when its naive scale is absent or zero; the complete daily leaderboard
then falls back to MAE with an explicit explanation. Candidates are ranked only
on shared historical test weeks, preventing a method that skipped difficult
folds from gaining an unfair comparison. The zero benchmark remains visible but
cannot become the winner. All winners remain `evaluation_only`. Verification:
all 233 non-integration backend tests passed (4 deselected), with Ruff and mypy
clean.

**Learning question:** How can one aggregate accuracy score hide an operationally
dangerous bias?

### Step 5 — Scenario evaluation pack — complete 2026-09-02

Run every method over known synthetic patterns and record expected winners,
limitations, and failure modes.

Implemented twelve typed, deterministic scenarios in
`src/product_demand/scenario_pack.py`, a reproducible JSON report command in
`scripts/evaluate_product_demand_scenarios.py`, and behavioral assertions in
`tests/test_product_demand_scenario_pack.py`. All twelve declared expectations
passed. The pack covers stable, seasonal, level-shift, intermittent, all-zero,
short-history, unknown-gap, stockout, activity, product-isolation, inflated
nonzero-average, and opposite-bias behavior. Expected winners are asserted only
where mathematically unambiguous. The report is recorded in
`docs/PRODUCT_DEMAND_SCENARIO_EVALUATION.md`. Verification: all 242
non-integration backend tests passed (4 deselected), with Ruff and mypy clean.

**Learning question:** Are we measuring general forecasting behaviour or merely
matching one CSV?

### Step 6 — Public-data evaluation — complete 2026-09-02

Run the engine on a documented UCI subset and an M5 sample. Keep dataset-specific
adapters outside the domain predictors.

Implemented deterministic adapters and aggregate evidence reporting in
`src/product_demand/public_data_evaluation.py`, with the reproducible command in
`scripts/evaluate_product_demand_public_data.py` and behavioral tests in
`tests/test_product_demand_public_data_evaluation.py`. The UCI evaluation keeps a
strict unknown-date safety view beside a labelled research-only complete-ledger
view; 14 of the 25 busiest selected products evaluated, while 11 remained
unavailable because quantity semantics were unsafe. The M5 evaluation sampled
24 item-store series across delayed-start, sparse, intermittent, and dense
patterns and trimmed 6,040 pre-first-sale zero days. Every prepared product beat
the zero benchmark. Full results and limitations are recorded in
`docs/PRODUCT_DEMAND_PUBLIC_DATA_EVALUATION.md`. No production threshold or
user-facing forecast was accepted.

**Learning question:** Which assumptions fail when clean fixtures meet real data?

### Step 7 — 11B-1 review gate — evidence complete 2026-09-02

Review distributions, coverage, latency, method stability, and directional
errors. Propose—not retroactively tune—11B-2 thresholds and user-facing policy.

Implemented typed review evidence in `src/product_demand/evaluation_review.py`
and the reproducible command in
`scripts/review_product_demand_public_evidence.py`. The review found no
date-varying daily winner, 14 of 38 daily RMSSE values above 1, and only 18 of 38
products with the same early/recent daily winner. Weekly evidence was stronger,
but five of six sparse M5 products were worse than zero on seven-day-total MAE.
The current three-fold minimum also remains uncalibrated because every public
product had at least 57 folds. Findings are recorded in
`docs/PRODUCT_DEMAND_EVIDENCE_REVIEW.md`. ADR-009 proposes an 11B-1 extension;
11B-2 remains unapproved pending completion of that extension.

### Step 8 — Explicit weekly zero-skill gate — complete 2026-09-02

Accepted ADR-009 Option B and implemented a typed, per-product weekly evidence
gate in `src/product_demand/trust_gate.py`. The gate compares the selected
non-benchmark weekly method with forecasting zero on the exact same historical
weeks. It passes only when benchmark-relative skill is strictly positive. A
perfect zero benchmark, a tie, worse performance, missing benchmark evidence,
or no fair weekly winner cannot pass.

Passing this gate is deliberately labelled necessary but insufficient: it does
not assign a supported forecast or authorize dashboard output. Failing products
receive a plain-English instruction not to show a numeric forecast. Re-running
the public review produced 14 passes and no failures for UCI, and 19 passes with
5 failures for M5. The five M5 failures remain visible individually rather than
being hidden by portfolio averages. Verification: 262 non-integration backend
tests passed (4 deselected), with Ruff, formatting, mypy, and diff checks clean.

**Learning question:** Why must choosing the best available method remain
separate from deciding whether that method is good enough to use?

### Step 9 — SBA/Croston intermittent-demand candidate — complete 2026-09-02

Implemented a pure seven-day-total SBA/Croston candidate behind the existing
baseline and rolling-origin boundaries. It separately smooths positive demand
sizes and inter-demand intervals with a fixed 0.1 parameter, applies the 0.95 SBA
bias correction, and never emits date-specific predictions. The fixed parameters
match the documented reference implementation and were not optimized against
the project datasets.

The candidate requires at least 28 calendar days and an unbroken included
calendar because compressing an unknown, closed, or stockout-limited date would
change the event intervals. All-zero complete history returns a zero estimate,
which still cannot pass the zero-skill gate. Dedicated tests cover the formula,
all-zero history, excluded dates, rolling integration, and future leakage.

The public-data rerun selected SBA/Croston for 11 of 14 UCI products and 8 of 24
M5 products. It did not rescue any of the five M5 zero-gate failures. One sparse
failure improved from -23.3% to -18.9% skill versus zero but remained blocked.
The rerun also revealed that lower total error came with weaker UCI subperiod
stability and higher bias, so no production approval was inferred. Verification:
266 non-integration backend tests passed (4 deselected), with Ruff, formatting,
mypy, and diff checks clean.

**Learning question:** Why should a new method remain in the candidate set when
it wins some products but does not solve every sparse-demand failure?

### Step 10 — Flat-allocation daily-shape comparison — complete 2026-09-02

Implemented an evaluation-only daily-shape layer that keeps the selected weekly
total fixed. It compares an equal seven-day allocation with each eligible
date-varying candidate after rescaling that candidate's proportions to the same
weekly total. This reconciliation prevents weekly-level accuracy from being
mistaken for evidence that the daily pattern is useful.

Tests cover exact weekly-total preservation, a hand-built seasonal case,
flat-only unavailability, missing weekly winners, deterministic repeatability,
input immutability, and portfolio serialization. The public review evaluated all
14 UCI and 24 M5 products. The seasonal shape was worse than flat for every UCI
product and for 20 of 24 M5 products. Only two M5 products showed positive skill
in both history halves. Daily forecasts therefore remain unapproved; the next
extension is history-length sensitivity. Verification: 271 non-integration
backend tests passed (4 deselected), with Ruff, formatting, mypy, and diff checks
clean.

**Learning question:** Why must a daily model beat an equal allocation after the
weekly total is fixed before we describe its values as date-specific forecasts?

### Step 11 — History-length sensitivity — complete 2026-09-03

Implemented a typed fixed-holdout experiment for 3, 6, 13, and 26 completed
weekly selection folds. Each checkpoint selects a non-benchmark weekly method
using only the immediately preceding folds, then evaluates that fixed choice on
the same later 13 folds against forecasting zero. This separates model selection
from validation and prevents different test periods from confounding the
history-length comparison.

All 14 UCI products passed the holdout zero gate at every checkpoint, with
median skill between 59.81% and 62.43%. M5 did not improve monotonically: 17 to
19 of 24 products passed depending on checkpoint, and median skill ranged from
17.05% to 27.08%. Sparse M5 remained unsafe: only one or two of six products
passed, and median skill remained negative even at 26 folds.

The result rejects completed-fold count as a sufficient universal trust rule.
History is an evidence prerequisite, but positive unseen performance and demand
pattern must also participate in the final policy. Dedicated tests cover fixed
holdout isolation, future leakage, insufficient folds, missing zero evidence,
perfect-zero behavior, determinism, and stratified serialization.
Verification: 277 non-integration backend tests passed (4 deselected), with
Ruff, formatting, mypy, and diff checks clean.

**Learning question:** Why can six months of backtest history still be
insufficient for a sparse product while three folds work for a dense product?

### Step 12 — Final trust-policy proposal — accepted 2026-09-03

Re-ran and reviewed the combined zero-gate, SBA/Croston, daily-shape, and
history-sensitivity evidence. ADR-010 proposes Option B: implement only an
evidence-gated limited preview in 11B-2 v1. Safe semantics, a fair weekly winner,
at least 13 shared folds, and strictly positive skill against zero are all
required before showing one numeric seven-day total. Supported weekly and
date-specific forecasts remain unavailable.

The project owner accepted Option B on 2026-09-03. The 13-fold floor is
explicitly provisional. It is a minimum evidence guardrail for preview UX, not
an empirically optimal history length or an accuracy guarantee. No skill-margin
or bias threshold is invented because the project has no validated
waste-versus-stockout cost model.

11B-2 Step 1 then implemented the accepted typed product-level policy in
`src/product_demand/trust_policy.py`. The contract permits only unavailable or
limited-preview decisions, retains data and policy reasons, and prevents a
supported-weekly state in policy version 1. Boundary tests cover exactly 13
folds, one fold below the boundary, unsafe semantics, zero-gate failure, missing
benchmark evidence, product identity isolation, and serialized output.
Verification: 288 non-integration backend tests passed (4 deselected), with
Ruff, formatting, mypy, and diff checks clean.

**Learning question:** Why is a preview release boundary different from proving
that a forecast is safe for inventory decisions?

### 11B-2 Step 2 — Domain orchestration — complete 2026-09-03

Implemented `src/product_demand/service.py` as the single domain flow connecting
readiness, calendar construction, evaluation-series preparation, rolling
candidate evaluation, zero-skill gating, preview policy, and final future
forecast generation. The future forecast is calculated only after the policy
allows it and contains one seven-day total with an explicitly labelled average
daily planning rate—not seven date-specific predictions.

Products remain isolated. A short-history or unsafe product cannot block an
eligible product in the same dataset. If the selected method cannot safely use
the latest history, such as a recent excluded closure date, the allowed preview
is downgraded to unavailable instead of crashing or returning a stale number.

Six service integration tests cover complete preview, mixed eligibility,
semantic failure without fake evaluation, final forecast downgrade, globally
ineligible order-total mode, determinism, and input immutability. Verification:
294 non-integration backend tests passed (4 deselected), with Ruff, formatting,
mypy, and diff checks clean.

**Learning question:** Why should model selection and final forecast generation
remain separate stages even when they use the same selected method?

### 11B-2 Step 3 — Opt-in API and dashboard vertical slice — complete 2026-09-03

Added `POST /api/v1/analyses/{analysis_id}/product-demand` as an opt-in boundary
over an existing cleaned analysis session. This keeps the monthly revenue
forecast contract unchanged and avoids running product-level rolling evaluation
for every sales analysis. The typed request carries explicit daily-coverage,
stockout, identity, unit, and closure assumptions. The typed response exposes
only the chosen method, benchmark evidence, one seven-day total, its labelled
average daily planning rate, warnings, and unavailable reasons.

The React dashboard now provides a separately labelled experimental section.
Unavailable products are collapsed and revealed in batches so a large catalogue
does not overwhelm the main dashboard. Seven API integration tests and a fourth
Playwright journey cover eligible preview, missing confirmations, mixed product
outcomes, source-quality blocking, order-total ineligibility, structured stockout
identity, and the complete browser upload-to-preview flow. Verification: 301
non-integration backend tests passed (4 deselected), all four Playwright journeys
passed, and backend/frontend lint, formatting, typing, and production build were
clean.

**Learning question:** Why should a computationally heavier forecast with extra
business assumptions be an opt-in analysis endpoint rather than an automatic
field in every revenue response?

## 6. Test Strategy

### Unit and invariant coverage

Every candidate and metric must test:

- minimum eligible history;
- all-zero history;
- intermittent zero-heavy history;
- non-negative output;
- exact seven-date horizon;
- deterministic repeatability;
- no input mutation; and
- known hand-calculated predictions or metrics.

Every calendar status and unavailable reason must have at least one behavioural
test. Every predictor must have at least one test proving it cannot read beyond
the supplied training window.

### Integration coverage

- Calendar result to evaluation-ready series.
- Evaluation-ready series to all eligible candidates.
- Fold evidence to metrics and leaderboards.
- Partial portfolio where some products evaluate and others remain unavailable.
- Existing monthly revenue forecast remains unchanged.

### Scenario pack

At minimum, include:

1. stable daily level;
2. strong weekday seasonality;
3. recent upward level shift;
4. intermittent demand with many confirmed zeroes;
5. all-zero active product;
6. short history;
7. unknown internal gap;
8. stockout-censored period;
9. discontinued or unconfirmed-active product;
10. one invalid product alongside valid products;
11. nonzero-day-average inflation case; and
12. equal overall error with opposite over/under bias.

Each scenario declares the expected eligible methods and invariants before model
implementation. Expected winners are asserted only where the pattern makes one
unambiguous; otherwise the test asserts correct evidence and availability.

### Public-data coverage

- UCI Online Retail II challenges lifecycle and negative-quantity semantics.
- An M5 sample challenges intermittent daily SKU series, delayed product starts,
  and scaled metrics.
- Neither dataset defines universal thresholds.
- Results include sample-selection logic, product coverage, exclusions, latency,
  and metric distributions.

### E2E boundary

No new Playwright journey was required for 11B-1 because it added no API or
dashboard feature. 11B-2 now has a browser journey covering grouped
confirmations, the seven-day total, the explicitly averaged daily planning rate,
the preview warning, and the plain-English method explanation. API tests cover
mixed and unavailable product states.

## 7. Non-Functional Requirements

- Deterministic results for identical input and configuration.
- No future leakage.
- No mutation of canonical or calendar inputs.
- Per-product failure isolation.
- Bounded candidate set and transparent computational cost.
- Latency measured separately for preparation, evaluation, and serialization.
- No raw customer identifiers or transaction rows in aggregate evaluation
  telemetry.
- Reproducible dataset versions and scenario seeds.

11B-1 records latency distributions; it does not invent a production SLO before
deployment conditions and expected catalogue size are known.

## 8. Explicitly Deferred

- Supported-use trust thresholds; ADR-010 now proposes a preview-only boundary.
- Supported-use product-demand output and date-specific forecasts.
- Prediction intervals.
- Cost-weighted stocking policy and reorder quantities.
- Weather, holidays, promotions, and price features.
- Cold-start peer products.
- Product-location forecasts.
- Advanced ML and deep learning.

## 9. Exit Criteria

11B-1 is complete only when:

- typed contracts and pure baselines are documented and tested;
- rolling folds prove there is no future leakage;
- metric edge cases are explicit;
- every scenario produces its declared evidence;
- UCI and M5-sample reports are reproducible;
- existing revenue and diagnostic regression suites remain green;
- lint, format, type, and proportional browser checks pass;
- model coverage and latency are reported; and
- an explicit review accepts or revises the proposed 11B-2 trust and granularity
  rules.

## 10. Confidence

- Evaluation architecture: high, approximately 94%.
- Initial bounded candidate set: high as a baseline harness, approximately 90%.
- Preview boundary: accepted in ADR-010 and implemented end to end.
- Supported-use thresholds: intentionally deferred until locked or prospective
  evidence and business-cost requirements exist.
- Future business value: cannot be established from forecast accuracy alone;
  operational validation remains a later requirement.
