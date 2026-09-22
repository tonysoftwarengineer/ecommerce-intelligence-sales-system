# Milestone 8: Evaluation and Observability

## Outcome

This milestone makes the project measurable. The system can now be evaluated
across known business scenarios, protected from regression by tests, and
observed in local development without retaining customer CSV data.

It does **not** claim production monitoring or real-business validation.

On 2026-08-18, a manual browser smoke check confirmed that the existing
restaurant analysis still renders diagnostic evidence, forecast trust, model
comparison, and friendly limitation states after this backend addition.

Three automated Playwright Chromium journeys now also verify the complete
browser-to-API path: a rich successful analysis, explicit invalid-row
quarantine, and honest unavailable states for limited history and missing
optional fields.

## What is being evaluated

| Layer | Evidence | What it protects |
|---|---|---|
| Anomaly detector | Ten deterministic, cross-industry synthetic scenarios | Expected alerts, expected no-findings results, and safe unavailable states |
| Generic CSV pipeline | Fifteen realistic end-to-end CSV scenarios | Mapping, validation, quarantine, financial rules, currencies, analytics, and forecasts |
| API contract | FastAPI integration tests | Upload-to-dashboard response behaviour and saved analysis restoration |
| Forecasting | Rolling-backtest unit tests | Method selection, trust labels, limited-history fallback, and missing-month protection |
| Observability | Aggregate metric tests and an internal endpoint | Diagnostic availability, safe fallback count, and analysis latency |
| Browser journey | Three Playwright Chromium tests | Upload, mapping, rule confirmation, validation, quarantine consent, dashboard evidence, and friendly fallbacks |

The synthetic scenarios are controlled learning tests. They do not prove that
the product is accurate for ten real businesses. Real anonymized data and
reviewer feedback are the next level of evidence.

## New local scorecard

After at least one successful analysis, inspect the aggregate snapshot:

```bash
curl http://localhost:8000/api/v1/observability/analysis-metrics
```

The scorecard records no CSV contents, filenames, customer IDs, analysis IDs,
or insight text. It resets when the API restarts.

## Browser end-to-end tests

Install the Chromium test browser once and run the suite from `frontend/`:

```bash
npx playwright install chromium
npm run test:e2e
```

Playwright starts isolated local API and frontend servers when needed. The API
uses the generic-sales routes without loading the unrelated Olist demonstration
dataset. On failure, local ignored artifact folders preserve a screenshot,
trace, and screen recording for debugging.

### How to read it

- **analysis_runs**: successful uploads that reached a saved analysis result.
- **currency_reports**: independent reports produced. A mixed-currency upload
  produces more than one report because the system must never add unlike
  currencies together.
- **latency_ms**: average, median (p50), p95, and maximum processing time from
  the start of the analysis endpoint to its prepared response. It is a local
  development signal, not an internet performance SLA.
- **assessed_reports**: diagnostic reports that produced a valid assessment:
  either a finding (`available`) or a valid result with no finding
  (`no_findings`).
- **unavailable_reports**: reports deliberately withheld because required
  history or data is missing. This is usually a guardrail, not a system error.
- **processing_error_count**: a diagnostic section hit an unexpected internal
  error and returned its friendly safe fallback. This should remain zero.

## Feedback design for a later production phase

The current project must not add a public feedback endpoint yet: it has no
user identity, durable database, or retention policy. When those foundations
exist, a reviewer feedback record should contain:

- a non-sensitive analysis/report reference;
- the diagnostic section and insight type being reviewed;
- the reviewer judgment: `supported`, `false_positive`, `missed_issue`, or
  `insufficient_evidence`;
- an optional explanation; and
- review timestamp and product version.

This feedback would let us calculate false-alert rate, missed-alert rate, and
the data conditions that commonly make a diagnostic unavailable. It must be
reviewed by a human; it must never automatically retrain rules or change
financial outputs.

## Remaining milestone gaps

- Run the evaluation pack against real, anonymized business exports after
  customer permission and data-handling rules are in place.
- Add accessibility and additional-browser coverage when the supported browser
  and accessibility policy is defined.
- Move metrics behind administrator authentication and durable monitoring when
  deployment architecture is chosen.
