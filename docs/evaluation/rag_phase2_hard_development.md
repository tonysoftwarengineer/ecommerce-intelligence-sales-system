# RAG Phase 2 Answer Evaluation

- Provider: `gemini_rest`
- Model: `gemini-3.6-flash`
- Suite: `hard-development`
- Split: `development`
- Cases: 20
- Verifier pass rate: not assessed (no provider response)
- Unsupported abstention accuracy: 100.0%
- Gold-claim coverage: 0.0%
- Cross-scope leakage count: 0
- p95 latency: 809.1 ms
- Provider-unavailable cases: 18
- Provider responses: 0
- Provider failure reasons: `gemini_http_429`: 18
- Verifier-rejected cases: 0
- Retrieval-miss cases: 0

| Release gate | Result |
|---|---|
| verifier pass rate | pass |
| provider availability | fail |
| unsupported abstention | pass |
| gold claim coverage | fail |
| scope isolation | pass |
| warm p95 latency | pass |

Provider-unavailable cases make a real-provider run inconclusive; they are not
treated as verifier quality failures. The grounded-answer feature remains
experimental unless every gate passes and every locked-test failure receives
manual review. A deterministic fake-provider result validates wiring and
verification only; it is not a Gemini quality claim.
