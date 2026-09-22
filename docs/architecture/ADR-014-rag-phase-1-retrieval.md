# ADR-014: Use Evaluated MiniLM and Ephemeral Chroma for Phase 1 Retrieval

**Status:** Accepted  
**Date:** 2026-09-17  
**Decider:** Project owner

## Context

RAG Phase 1 must find verifiable passages in approved temporary documents
without generating an answer. The portfolio demo needs semantic paraphrase
handling, honest abstention, zero cross-session leakage, and warm p95 latency at
or below 500 ms. Ordinary CI must remain deterministic and must not download a
model.

The release gates were fixed before the locked test: at least 80% Top-1 source
accuracy, 90% Top-3 source recall, 90% unsupported-question abstention, no
cross-session leakage, and warm-query p95 at or below 500 ms.

## Decision

Use `all-MiniLM-L6-v2` through `sentence-transformers==5.1.2` and an ephemeral
`chromadb==1.5.9` collection whose name is derived from a SHA-256 retrieval-scope
hash. Every chunk also stores the owner and analysis scope as metadata. Search only the active
latest version of each filename.

Use heading/paragraph-aware chunks with a frozen 224-token maximum and 32-token
overlap. Retrieve at most 20 candidates, apply a frozen cosine-similarity gate of
0.40, remove near-duplicates, prefer source diversity, and return at most three
untrusted evidence excerpts. Return `insufficient_evidence` with no excerpts when
no candidate passes.

Keep TF-IDF as the transparent lexical baseline and ordinary-test backend. Use
deterministic fakes/TF-IDF for unit, API, and browser tests; run the real MiniLM
and Chroma benchmark separately. Do not add reciprocal-rank fusion because the
selected semantic baseline had no development retrieval failures. Do not retain
the lexical-coverage reranker because it did not improve the selected baseline.

## Options Considered

### Option A: TF-IDF only

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Explainability | High |
| Paraphrase retrieval | Limited |
| Development Top-3 recall | 80.8% — failed |
| Warm p95 latency | 1.315 ms |

**Pros:** Fast, deterministic, cheap, and easy to debug.  
**Cons:** Missed semantic paraphrases and failed the predeclared recall gate.

### Option B: MiniLM with ephemeral Chroma

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Explainability | Medium; source excerpts remain inspectable |
| Paraphrase retrieval | Strong |
| Locked Top-1 / Top-3 | 93.75% / 94.12% |
| Locked warm p95 latency | 8.482 ms |

**Pros:** Passed every locked release gate with large latency headroom.  
**Cons:** Adds model size, cold-start cost, and a local model dependency.

### Option C: Hybrid fusion and lexical reranking

| Dimension | Assessment |
|---|---|
| Complexity | Medium-high |
| Potential recall | High when baselines make complementary errors |
| Current evidence | No demonstrated need |
| Debuggability | Lower than one selected method |

**Pros:** Can combine semantic and exact lexical strengths.  
**Cons:** Adds scoring and tuning complexity without evidence of a development
gain because MiniLM/Chroma already reached 100% development Top-1 and Top-3.

## Trade-off Analysis

Option B is the smallest method that passed the fixed quality and latency gates.
Option A remains valuable as a baseline and deterministic test double but is not
the released retrieval method. Option C is deferred until a future development
set demonstrates complementary retrieval errors; it will not be added merely to
make the architecture look more sophisticated.

## Consequences

- The first semantic query has a model cold-start cost; later queries use the
  cached model.
- Deployment packaging must pre-download the pinned model.
- A semantic-index failure returns a bounded `unavailable` result and does not
  affect sales analytics.
- The locked test has one recorded miss (`lock-branches`); the configuration was
  not changed after examining that result.
- Passing retrieval gates authorizes the evidence-search capability, not the
  quality of generated answers. Experimental Phase 2 answers are governed
  separately by ADR-015.

## Action Items

1. [x] Add 15 synthetic documents and 50 labelled development/locked questions.
2. [x] Implement stable chunking, latest-version indexing, relevance gating,
   duplicate removal, diversity, and abstention.
3. [x] Add guest-owned retrieval API and dashboard evidence panel.
4. [x] Save JSON and Markdown development and locked-test reports.
5. [x] Add deterministic CI/API/browser coverage and real-model evaluation.
6. [x] Add an API image definition that pre-downloads the pinned embedding model.
7. [ ] Run the independent-business forecasting evidence checkpoint.
8. [x] Add experimental Phase 2 grounded answers without using or approving
   forecast outputs; keep the Phase 2 locked quality gate separate and pending.
