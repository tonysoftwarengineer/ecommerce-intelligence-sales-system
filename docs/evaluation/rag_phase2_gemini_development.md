# RAG Phase 2 Answer Evaluation

- Provider: `gemini_rest`
- Model: `gemini-3.6-flash`
- Split: `development`
- Cases: 6
- Verifier pass rate: 0.0%
- Unsupported abstention accuracy: 100.0%
- Gold-claim coverage: 0.0%
- Cross-scope leakage count: 0
- p95 latency: 11.4 ms

| Release gate | Result |
|---|---|
| verifier pass rate | fail |
| unsupported abstention | pass |
| gold claim coverage | fail |
| scope isolation | pass |
| warm p95 latency | pass |

The grounded-answer feature remains experimental unless every gate passes and
every locked-test failure receives manual review. A deterministic fake-provider
result validates wiring and verification only; it is not a Gemini quality claim.
