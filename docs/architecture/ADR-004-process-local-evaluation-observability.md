# ADR-004: Process-Local Evaluation Observability

**Status:** Accepted  
**Date:** 2026-08-18  
**Deciders:** Project owner

## Context

The system produces conservative diagnostic and forecasting outcomes, but it
previously had no aggregate evidence about how often those outcomes were
available, unavailable because data was insufficient, or safely degraded after
an internal diagnostic failure. It also had no measurement of analysis
latency.

The current application deliberately uses temporary, process-local uploads and
analysis sessions. It has no authentication, durable database, or operational
monitoring service. An observability choice must therefore support learning and
controlled evaluation without creating a misleading production claim or
retaining customer business data.

## Decision

Add a bounded, thread-safe, in-memory metric registry for successfully
completed generic sales analyses. It records only:

- completed analysis count;
- report count per currency, without mixing currencies;
- end-to-end analysis latency in milliseconds;
- comparison and anomaly status counts;
- the percentage of diagnostic reports that were assessed (`available` or
  `no_findings`), rather than unavailable due to a guardrail; and
- forecast status counts and safe diagnostic-processing fallback counts.

The developer-only endpoint `GET /api/v1/observability/analysis-metrics`
returns this aggregate snapshot. It must not be shown in the customer
dashboard. The registry retains no CSV rows, filenames, analysis identifiers,
customer identifiers, or insight text, and it resets on API restart.

User feedback is documented as a future durable, authenticated workflow; it is
not accepted by the current API.

## Options Considered

### Option A: No metrics until deployment

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Low |
| Privacy risk | Low |
| Learning value | Low |

**Pros:** No new code or operational surface.  
**Cons:** We cannot measure whether guardrails frequently make the product
unavailable, or whether a change slowed analysis.

### Option B: Process-local aggregate metrics

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Low |
| Privacy risk | Low |
| Learning value | High for this stage |

**Pros:** Fast feedback, deterministic tests, and no customer data retained.  
**Cons:** Metrics disappear on restart and cannot be trusted as production
monitoring.

### Option C: External monitoring and durable feedback storage now

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Cost | Ongoing |
| Privacy risk | Medium |
| Learning value | High, but premature |

**Pros:** Persistent dashboards, alerts, and real feedback collection.  
**Cons:** Requires a deployment target, authentication, retention policy,
access control, and a production support process that the project does not yet
have.

## Trade-off Analysis

Option B is selected because it fits the current modular-monolith and
temporary-storage architecture. It gives the project a measurable evaluation
loop without treating a local dashboard as production telemetry. The metrics
distinguish an expected `unavailable` outcome from a processing failure, so a
lack of source-data capability is not misrepresented as an application error.

## Consequences

- Evaluation can reveal if common datasets lack the history needed for an
  anomaly or forecast conclusion.
- Performance changes can be compared before and after future features.
- No customer-visible reporting behaviour changes.
- The endpoint must be protected by administrator authentication or removed
  before any public deployment.
- Durable monitoring, alerting, and feedback storage remain explicit future
  work.

## Action Items

1. [x] Add aggregate, bounded analysis metrics with no source-data retention.
2. [x] Add API and unit regression coverage for the metric snapshot.
3. [x] Document the interpretation of availability and latency metrics.
4. [ ] Add authenticated, durable monitoring after the deployment architecture
   is selected.
5. [ ] Add a reviewed customer-feedback workflow after identity and retention
   policies exist.
