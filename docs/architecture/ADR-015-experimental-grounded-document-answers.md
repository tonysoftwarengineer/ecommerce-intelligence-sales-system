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
- Use a provider-neutral interface with Gemini and Groq REST adapters. The selected provider's API key remains server-side and the model is configurable through `RAG_ANSWER_MODEL`. Groq is an explicit local selection using `openai/gpt-oss-20b`; there is no automatic provider fallback.
- Send the provider only the English question and up to three retrieved excerpts. Uploaded document text is labelled untrusted data and no tools are available.
- Require one to three structured claims. Each claim names a retrieved chunk and includes an exact quote from it.
- Reject the whole generated output when its structure, chunk ownership, citation, or quote cannot be verified deterministically.
- Return a bounded unavailable or insufficient-evidence result with no generated claims when retrieval, the provider, or verification fails.
- Cap each provider response at a configurable 1,024 generated tokens by default. Record only
  aggregate usage and latency locally; never retain questions, excerpts, document IDs, guest IDs,
  or credentials in answer observability.
- Limit each anonymous guest to six provider-backed answer attempts per rolling minute. Retrieve
  first, so insufficient-evidence questions consume no provider budget. A local limit returns HTTP
  429 and a retry time; provider outages return a friendly unavailable result without automatic
  retry, provider fallback, or retriever fallback.
- Cap provider-backed answers app-wide per UTC day (`RAG_ANSWER_DAILY_BUDGET`, default 100), since
  the per-guest limit is cookie-keyed and resets when a client discards its cookie. A spent budget
  returns an unavailable result with reason `daily_answer_budget_exhausted` and calls no provider.
- Cache verified answers in process memory (LRU, 256 entries, 24 h). The key hashes the question,
  instructions, provider, model, output cap, and the retrieved excerpts and citations, with
  per-upload chunk IDs replaced by positions, so the same question about an identical document is
  answered once. Cached answers are remapped to the current chunk IDs and re-verified with the
  same exact-quote check; unverified answers are never cached. A hit spends no budget or rate limit.
  Cache entries track their source document IDs. Deleting, superseding, or expiring a source evicts
  its related answers, including a shared entry used by another guest. Periodic cleanup also
  removes entries past their cache lifetime or whose sources are no longer active.
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
- The selected provider can phrase claims but cannot calculate sales, query CSV rows, run tools, or override retrieval policy.
- Exact-quote verification provides strong attribution, not proof that a document is factually correct.
- Provider failure does not affect analytics or Phase 1 evidence retrieval.
- Without the selected provider's key, grounded answers are unavailable while document indexing and retrieval remain operational.
- The local observability endpoint, rate limiter, daily budget, and answer cache are
  process-local portfolio controls that reset on restart, not a production distributed quota,
  billing, or operations system. Evaluations call providers directly and bypass the cache, so
  they measure the model rather than replaying earlier answers.
- Temporary process-local storage and anonymous cookies remain portfolio limitations, not production tenancy.

## Explicit Non-goals

- CSV reasoning, forecast explanation, recommendations, agent loops, tool execution, account authentication, and durable document storage.
- Changing the frozen Phase 1 chunking, relevance threshold, retrieval method, or reranking policy.
- Claiming production readiness before the independent-business forecasting checkpoint or Phase 2 locked evaluation passes.

## Verification

- Unit tests cover exact quotes, unknown chunks, malformed output, provider failures, and prompt-injection boundaries.
- API tests cover cross-guest and cross-analysis isolation and answer abstention.
- Browser tests use an explicit deterministic fake provider; each real-provider evaluation is a separate recorded run.
