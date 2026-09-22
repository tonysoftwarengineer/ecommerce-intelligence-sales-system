# ADR-001: Deterministic Recommendation Ranking

**Status:** Accepted  
**Date:** 2026-08-05  
**Deciders:** Project owner

## Context

The Diagnostic Intelligence layer can identify validated sales changes and anomalies. Small-business users need help deciding what to investigate first, but the system does not have causal evidence, profit data, inventory data, or authority to make commercial changes automatically.

## Decision

Attach human-reviewed investigative recommendations to supported findings and rank them with an explicit score:

```text
ranking score = impact + urgency + confidence
```

Each component is scored from 0 to 3. The first release uses percentage movement for impact, business-metric direction for urgency, and the diagnostic confidence label for confidence. Scores map to low, medium, or high priority. `critical` is reserved for a future release with stronger operational-impact evidence.

## Options Considered

### Option A: LLM-generated recommendations

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Ongoing model cost |
| Explainability | Low without additional controls |
| Risk | Higher hallucination and unsupported-action risk |

### Option B: Deterministic rule-based recommendations

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | No model inference cost |
| Explainability | High |
| Risk | Bounded to implemented rules |

## Trade-off Analysis

Option B is narrower and less flexible, but its result is repeatable, testable, and appropriate for a product that has limited business context. Option A will be reconsidered only as an explanation layer after the system has validated analytics, retrieval context, and evaluation coverage.

## Consequences

- Recommendations are investigations, not automatic actions.
- Every recommendation requires human review.
- Unsupported findings receive no recommendation rather than a generic suggestion.
- Later inventory, profit, and retention data can add more specialised rules.

## Action Items

1. [x] Implement transparent ranking and action templates.
2. [x] Add regression tests for ordering and safety.
3. [ ] Expose the ranked recommendations through the API and dashboard.
