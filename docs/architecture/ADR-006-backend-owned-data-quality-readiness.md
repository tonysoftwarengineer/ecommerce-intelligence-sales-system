# ADR-006: Backend-Owned Data-Quality Readiness

**Status:** Accepted  
**Date:** 2026-08-27  
**Deciders:** Project owner

## Context

The sales pipeline already validates every mapped source row, quarantines invalid
rows, preserves machine-readable issue reasons, and requires explicit consent
before continuing with a partially valid dataset. It does not yet distinguish a
small amount of rejected data from a dataset where so much data was rejected that
forecasts, diagnostics, and recommendations could mislead the user.

The product must still allow a user to explore the dashboard when valid rows
remain. At the same time, a warning in only the React interface would not protect
other API consumers and would allow low-trust decision-support outputs to be
calculated and exposed elsewhere.

## Decision

The backend owns a deterministic data-quality readiness policy:

- fewer than 5% invalid source rows: `normal`;
- 5% to under 20% invalid source rows: `caution`;
- 20% or more invalid source rows: `preview`;
- no transformable rows or another blocking validation error: `blocked`.

`normal` and `caution` analyses remain decision-ready. `preview` analyses expose
basic analytics over accepted rows but skip forecasting and diagnostic execution.
Recommendations are also unavailable because they are produced only from a valid
diagnostic report. The API returns explicit unavailable states and the shared
data-quality reason rather than calculating and hiding these outputs in the UI.

The data-quality report is typed and included in both validation and saved-analysis
responses. It contains the invalid-row percentage, status, decision readiness,
restricted outputs, a user-facing message, and deterministic repair actions grouped
by source column and validation issue. Repair actions identify affected row counts,
sample CSV row numbers, and correction instructions. The quarantine CSV remains the
complete row-level audit artifact.

The first version deliberately uses invalid source-row percentage because it is
available for every supported CSV. Affected-order share and financial value at risk
may be added only when those fields can be measured reliably; the system must not
guess financial impact from invalid monetary values.

## Options Considered

### Option A: Frontend-only warning

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Consistency | Low; other API clients can disagree |
| Safety | Low; restricted outputs are still calculated |
| Testability | UI-focused |

**Pros:** Small change and quick visual feedback.  
**Cons:** Treats reliability as presentation, duplicates policy across clients, and
does not protect the API contract.

### Option B: Backend-owned readiness with computation gating

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Consistency | High; one policy for every client |
| Safety | High; low-trust decision outputs do not execute |
| Testability | Domain, API, and browser coverage |

**Pros:** One auditable rule, explicit API states, and no hidden low-trust outputs.  
**Cons:** Expands the response contract and requires coordinated backend and frontend
changes.

### Option C: Block every partially invalid dataset

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Usability | Low for exploration and correction |
| Safety | High but unnecessarily restrictive |
| Testability | Simple |

**Pros:** No analysis is shown from incomplete data.  
**Cons:** Prevents useful previews and gives users less help understanding how to
correct their exports.

## Trade-off Analysis

Option B adds contract and orchestration work, but it preserves the product's
central trust boundary: analytical readiness is a backend fact, not a visual hint.
Allowing basic preview analytics balances exploration with safety. Deterministic
repair guidance uses evidence the validator already produced and avoids adding an
LLM to a task that requires exact, reproducible instructions.

The initial percentage thresholds are product policy, not universal statistical
truths. They must be revisited after evaluation against representative real exports.

## Consequences

- Every client receives the same readiness decision and correction evidence.
- Preview dashboards remain useful for exploration without presenting forecasts or
  recommendations as trustworthy.
- Observability records explicit unavailable decision-support states.
- The API response becomes larger but remains bounded and contains no additional CSV
  values.
- Future order-impact or value-at-risk signals can extend the policy without changing
  its ownership boundary.

## Action Items

1. [x] Add typed domain contracts and deterministic data-quality assessment.
2. [x] Include the report in validation and saved-analysis API responses.
3. [x] Gate forecast and diagnostic execution for Preview Mode.
4. [x] Render Preview Mode and guided correction in the React workflow.
5. [x] Add threshold, API, and Playwright regression coverage.
6. [ ] Re-evaluate thresholds with representative anonymized business exports.
