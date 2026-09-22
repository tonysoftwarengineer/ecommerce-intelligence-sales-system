# ADR-010: Product-Demand Preview Release Policy

**Status:** Accepted  
**Date:** 2026-09-03  
**Deciders:** Project owner

## Context

Milestone 11B-1 evaluated transparent product-demand baselines with synthetic
scenarios, UCI Online Retail II, and a stratified M5 sample. The accepted ADR-009
extension added a zero-skill gate, SBA/Croston, daily-shape comparison, and
fixed-holdout history-length sensitivity.

The combined evidence shows:

- weekly methods beat zero for all 14 evaluated UCI products and 19 of 24 M5
  products on the full rolling evaluation;
- five M5 products still failed the zero benchmark after adding SBA/Croston;
- daily shape was worse than equal allocation for all 14 UCI products and 20 of
  24 M5 products;
- only two M5 products had positive daily-shape skill in both history halves;
- increasing selection evidence from 3 to 26 folds did not monotonically improve
  M5 holdout performance; and
- only one or two of six sparse M5 products passed depending on history
  checkpoint.

The UCI evaluation also required a documented research-only complete-ledger
assumption for absent dates. Historical public-data performance is useful
evidence, but it is not prospective proof that a forecast is safe for a business
decision.

## Decision

### 1. Approve only a limited-preview weekly state for 11B-2 v1

A product may receive a numeric **limited preview** only when all of these gates
pass:

1. Milestone 11A semantics are safe: product identity, unit, order treatment,
   calendar status, target quantity, and recent activity are resolved.
2. A non-benchmark seven-day-total method wins a fair shared-fold leaderboard.
3. At least 13 shared completed weekly folds exist.
4. The selected method has strictly positive skill against forecasting zero on
   those identical folds.

Thirteen folds are a provisional evidence floor for preview UX, not a universal
forecasting standard or an accuracy guarantee. The experiment did not identify
an empirically optimal fold count.

### 2. Preserve three explicit states

- **Unavailable:** any semantic gate fails, no fair weekly winner exists, fewer
  than 13 shared folds exist, zero evidence is unavailable, or skill against zero
  is not strictly positive. Show no numeric product-demand forecast and explain
  the blocker and correction.
- **Limited preview:** all four gates above pass. Show one seven-day total with
  `Preview — not decision-ready`, the chosen method, plain-English selection
  reason, fold count, benchmark comparison, and relevant limitations.
- **Supported weekly:** no 11B-2 v1 result may receive this state. It remains
  reserved for a separately accepted prospective-validation policy.

A product may be limited preview while another product in the same upload is
unavailable. Portfolio averages cannot override a product-level failure.

### 3. Keep granularity and business action bounded

- Show only a seven-day fulfilled-unit total per eligible product.
- A daily value may be shown only as `weekly total / 7` and labelled **average
  daily planning rate**, never as a date-specific forecast.
- Do not show reorder quantity, ingredient conversion, safety stock, or a claim
  about customers, revenue, unconstrained demand, or lost sales.
- Sparse or intermittent products that pass still receive a plain-English
  limitation that demand timing is irregular.

### 4. Do not invent unsupported accuracy thresholds

- Require skill against zero to be greater than zero; do not invent a 5%, 10%,
  or other margin without business-cost evidence.
- Report overforecasting and underforecasting separately, but do not set a
  universal bias tolerance before waste and stockout costs are known.
- Method changes across subperiods are disclosed as instability evidence, not
  silently converted into a confidence score.

### 5. Require new evidence before `supported weekly`

Supported status requires a future ADR based on:

- a locked or prospective dataset not used to choose this policy;
- sufficient dense, intermittent, sparse, and delayed-start coverage;
- prediction-interval calibration;
- business-informed waste-versus-stockout costs; and
- monitored post-release performance and fallback behavior.

## Options Considered

### Option A: Release supported weekly forecasts now

| Dimension | Assessment |
|---|---|
| Immediate user value | High |
| Evidence fidelity | Low |
| Sparse-demand risk | High |
| False-confidence risk | High |

**Pros:** Delivers decision-ready language immediately.  
**Cons:** Treats retrospective public-data evidence as prospective proof, hides
sparse failures, and requires unsupported confidence thresholds.

### Option B: Release evidence-gated limited previews only

| Dimension | Assessment |
|---|---|
| Immediate user value | Medium |
| Evidence fidelity | High |
| Sparse-demand safety | High |
| Implementation complexity | Medium |

**Pros:** Preserves useful weekly estimates where they beat a trivial benchmark,
keeps warnings honest, and isolates failures per product.  
**Cons:** Provides no decision-ready status and requires users to understand that
preview evidence is not an inventory instruction.

### Option C: Keep every numeric product forecast unavailable

| Dimension | Assessment |
|---|---|
| Immediate user value | Low |
| Evidence fidelity | High |
| Safety | Highest |
| Learning and portfolio value | Medium |

**Pros:** Avoids premature output completely.  
**Cons:** Discards meaningful weekly evidence and prevents a carefully bounded
preview from being evaluated with users.

## Trade-off Analysis

Option B is recommended. Option A overstates what the current evaluation proves.
Option C is safer but unnecessarily discards useful evidence. Option B preserves
the user's earlier decision that previews should remain possible while ensuring
that unsafe semantics and methods that cannot beat zero never produce a numeric
forecast.

The 13-fold floor deliberately balances friction and evidence volume. It is more
defensible than the current three-fold experimental minimum, but it is not
presented as an empirically optimal threshold. Every output remains a preview,
so this provisional floor cannot promote a result to supported status.

## Consequences

- Milestone 11B-1 evidence work is complete once this proposal is accepted or
  revised by the project owner.
- 11B-2 may implement a backend preview contract after acceptance.
- The dashboard cannot show daily product predictions or supported language.
- Some products in one upload may show a preview while others explain why no
  number is available.
- A future model may replace the baselines only by passing the same evidence
  boundaries; model complexity does not bypass trust gates.

## Action Items

1. [x] Project owner accepted Option B on 2026-09-03.
2. [x] Implement typed unavailable/limited-preview/supported contracts. Policy
   version 1 deliberately prevents construction of supported-weekly decisions.
3. [x] Add product-level policy tests at every threshold boundary.
4. [x] Implement one domain orchestration service that generates a future
   seven-day total only after the accepted policy permits it and isolates
   unavailable products.
5. [x] Add an opt-in API response without changing the existing revenue forecast.
6. [x] Add plain-English dashboard presentation and Playwright coverage.
7. [ ] Run a locked end-to-end evaluation before claiming supported weekly use.
