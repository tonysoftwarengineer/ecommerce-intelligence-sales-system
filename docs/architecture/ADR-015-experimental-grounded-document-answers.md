# ADR-015: Experimental Grounded Document Answers

**Status:** Accepted (experimental release)  
**Date:** 2026-09-18  
**Deciders:** Project owner

## Context

RAG Phase 1 can retrieve and cite approved business-document excerpts, but it does not answer a user's question. Adding an LLM creates new risks: cross-analysis document leakage, unsupported claims, fabricated citations, prompt injection inside uploaded documents, provider outages, and accidental use of CSV analytics or forecasts.

The portfolio demo has anonymous guests rather than user accounts and durable tenant storage. The answer feature therefore needs a narrow boundary that can be evaluated independently and can fail without affecting the existing analytics dashboard.

## Decision

- Bind each temporary RAG document to both the anonymous guest and one `analysis_id`.
- Preserve Phase 1 retrieval as a separate evidence-only endpoint.
- Generate an answer only after Phase 1 returns eligible evidence.
- Use a provider-neutral interface with a Gemini REST adapter. The API key remains server-side and the model is configurable through `RAG_ANSWER_MODEL`.
- Send the provider only the English question and up to three retrieved excerpts. Uploaded document text is labelled untrusted data and no tools are available.
- Require one to three structured claims. Each claim names a retrieved chunk and includes an exact quote from it.
- Reject the whole generated output when its structure, chunk ownership, citation, or quote cannot be verified deterministically.
- Return a bounded unavailable or insufficient-evidence result with no generated claims when retrieval, the provider, or verification fails.
- Keep the feature labelled experimental until the locked Phase 2 release gates pass.

## Options Considered

### Generate one free-form answer and append sources

This is simpler, but a source list cannot prove which text supports each statement. It also permits uncited summaries and makes deterministic verification weak.

### Generate claim-level structured output and verify every quote

This adds a small amount of schema and verification code, but makes each claim auditable and permits fail-closed behavior. This option was selected.

### Build an autonomous agent with tools

This is outside the current need. It would expand authority, prompt-injection exposure, latency, and evaluation scope without improving the approved-document question-answering goal.

## Consequences

- Two analyses belonging to the same guest cannot share documents accidentally.
- Gemini can phrase claims but cannot calculate sales, query CSV rows, run tools, or override retrieval policy.
- Exact-quote verification provides strong attribution, not proof that a document is factually correct.
- Provider failure does not affect analytics or Phase 1 evidence retrieval.
- Without `GEMINI_API_KEY`, grounded answers are unavailable while document indexing and retrieval remain operational.
- Temporary process-local storage and anonymous cookies remain portfolio limitations, not production tenancy.

## Explicit Non-goals

- CSV reasoning, forecast explanation, recommendations, agent loops, tool execution, account authentication, and durable document storage.
- Changing the frozen Phase 1 chunking, relevance threshold, retrieval method, or reranking policy.
- Claiming production readiness before the independent-business forecasting checkpoint or Phase 2 locked evaluation passes.

## Verification

- Unit tests cover exact quotes, unknown chunks, malformed output, provider failures, and prompt-injection boundaries.
- API tests cover cross-guest and cross-analysis isolation and answer abstention.
- Browser tests use an explicit deterministic fake provider; Gemini evaluation is a separate recorded run.
