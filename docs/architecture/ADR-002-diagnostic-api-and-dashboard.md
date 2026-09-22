# ADR-002: Diagnostic API and Dashboard Integration

**Status:** Accepted  
**Date:** 2026-08-05  
**Deciders:** Project owner

## Context

Diagnostic comparison, anomaly detection, and recommendation ranking are now deterministic domain capabilities. Users need to see their evidence, limitations, and required human review in the existing business-analysis workspace. A comparison may be available while anomaly detection is unavailable because it requires more history.

## Decision

Add two independent diagnostic sections to the existing generic analysis response:

- `diagnostics.comparison`
- `diagnostics.anomalies`

Each section includes its own status, insights, evidence, limitations, and optional ranked recommendation. The dashboard renders both sections directly below the core KPI cards.

## Options Considered

### Option A: A separate diagnostics endpoint

**Pros:** Smaller initial analysis response; independently refreshable.  
**Cons:** Adds a client-side request waterfall and can leave the dashboard with mismatched analysis and diagnostic versions.

### Option B: Include diagnostics in the saved analysis response

**Pros:** One consistent analysis snapshot; no extra client request; diagnostics persist with the session.  
**Cons:** Larger response payload.

## Trade-off Analysis

The diagnostic payload is small compared with the existing analysis response. Keeping it in the same saved analysis snapshot prevents version mismatches and avoids a browser request waterfall. Separate endpoints can be reconsidered when diagnostics become long-running or independently refreshable.

## Consequences

- Core analytics remains available if a diagnostic subsection fails.
- The API serializes domain contracts explicitly, preventing framework-specific objects from leaking into responses.
- The dashboard distinguishes `available`, `no_findings`, and `unavailable` rather than treating every empty result as an error.
- Recommendations visibly require human review.

## Action Items

1. [x] Add typed API and frontend contracts.
2. [x] Render diagnostic evidence, limitations, and recommendations.
3. [x] Add API regression coverage.
4. [x] Add focused Playwright browser end-to-end coverage for the upload, validation,
   quarantine, diagnostic, and forecast-evidence journey.
