# ADR-012: Sparse-Demand Approval Policy Review

**Status:** Rejected — fresh validation gate failed  
**Date:** 2026-09-15  
**Decider:** Project owner

## Context

The frozen policy's locked evaluation failed its sparse-demand stratum gate.
The ten-CSV pack verified correct behavior but did not repair or supersede that
accuracy failure. A bounded development comparison is recorded in
[the results](../PRODUCT_DEMAND_SPARSE_POLICY_COMPARISON.md).

Constraints: preserve safe calendars, numerical authority, preview-only labels,
and category non-overlap. Avoid new models and unvalidated complexity. The
previous locked cohort is evaluation-only; it cannot provide fresh proof again.

## Decision tested and rejected

Explicit training-sparse abstention was selected as the simplest validation
candidate. Its predeclared fresh-cohort gate failed because one retained product
in the descriptive sparse stratum performed worse than zero. No live rule change
is authorized. See
[the validation result](../PRODUCT_DEMAND_SPARSE_ABSTENTION_FRESH_VALIDATION.md).

## Options considered

### Stronger historical consistency

**Complexity:** Medium; three blocks and their evidence requirements.  
**Cost:** Additional evidence processing; no new model calls.  
**Scalability:** Fits the existing evaluation module.  
**Familiarity:** Uses existing shared-fold absolute errors.

**Pros:** Could preserve consistently useful sparse previews.  
**Cons:** No demonstrated retention advantage in this small cohort; exploratory
parameters; extra history requirement; still vulnerable to future demand changes.

### Explicit sparse-product abstention

**Complexity:** Low; a training-only flag and an additional withholding reason.  
**Cost:** Low; no new model or infrastructure.  
**Scalability:** Fits the existing trust decision path.  
**Familiarity:** Extends existing capability-based abstention.

**Pros:** Same measured outcome as consistency here with less logic.  
**Cons:** Removes any useful sparse previews outside this sample. The candidate's
10% positive-day cutoff is exploratory, not an accepted production standard.

### Guarded category fallback

**Complexity:** Existing implementation, separate data/evaluation requirements.  
**Cost:** Additional category evaluation.  
**Scalability:** Reuses current calendar and evaluator.  
**Familiarity:** Already covered by ADR-011 and functional tests.

**Pros:** Can offer a broader combined planning estimate where individually weak
products have stronger aggregate history.  
**Cons:** Cannot specify a product split; incomplete membership or incompatible
units blocks it. Comparative category accuracy remains unmeasured here.

## Trade-off analysis

Both evaluated product safeguards removed the same thirteen weak development
forecasts and retained all non-sparse previews. Simplicity favors explicit
abstention as a candidate, not as a proven universal solution. Either policy
could hide valuable forecasts on a different population. Category fallback is a
separate output scope and must earn its own evidence.

## Consequences

- The tested 10% binary rule will not be implemented.
- The fresh cohort is now evaluation-only and cannot validate a revised cutoff.
- Existing category checks, current preview policy, and preview-only status remain.
- No decision-ready forecasting or autonomous action is enabled.

## Action items

1. [x] Owner selected explicit sparse abstention for fresh evaluation.
2. [x] Protocol and training-only definition were locked before scoring.
3. [x] Candidate was evaluated on 48 new disjoint M5 products.
4. [x] Reject the tested candidate after its predeclared gate failed.
5. [ ] Decide whether to test consistency evidence or retain the current preview policy.
6. [ ] Declare another new protocol before scoring any revised candidate.
7. [ ] Separately validate category accuracy and address RAG prerequisites later.
