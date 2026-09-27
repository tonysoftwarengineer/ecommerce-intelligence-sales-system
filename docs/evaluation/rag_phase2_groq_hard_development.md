# RAG Phase 2 Answer Evaluation

- Provider: `groq_rest`
- Model: `openai/gpt-oss-20b`
- Suite: `hard-development`
- Split: `development`
- Cases: 20
- Verifier pass rate: 100.0%
- Unsupported abstention accuracy: 100.0%
- Gold-claim coverage: 28.6%
- Cross-scope leakage count: 0
- p95 latency: 1744.7 ms
- Provider-unavailable cases: 11
- Provider responses: 7
- Provider failure reasons: `groq_http_400`: 1, `groq_http_429`: 10
- Verifier-rejected cases: 0
- Retrieval-miss cases: 0
- Evaluation conclusion: **inconclusive — provider availability prevented complete scoring**

| Release gate | Result |
|---|---|
| verifier pass rate | pass |
| provider availability | inconclusive (upstream provider failures) |
| unsupported abstention | pass |
| gold claim coverage | inconclusive (incomplete provider responses) |
| scope isolation | pass |
| warm p95 latency | pass |

Provider-unavailable cases make this real-provider run inconclusive; they are
not treated as verifier or answer-quality failures. Gold-claim coverage is also
incomplete when a provider fails before producing an answer. One returned answer
also missed an expected gold claim, so there is an observation to review in a
future complete run. A fresh run must repeat the whole suite after the provider
limit resets; it must not combine only later retries with this run.

The grounded-answer feature remains experimental unless every gate passes and
every locked-test failure receives manual review. A deterministic fake-provider
result validates wiring and verification only; it is not a real-provider quality
claim.
