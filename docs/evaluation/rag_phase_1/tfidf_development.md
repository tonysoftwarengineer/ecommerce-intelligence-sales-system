# RAG Phase 1 Retrieval Evaluation

- Backend: `tfidf`
- Split: `development`
- Configuration: `{"candidate_limit": 20, "chunk_max_tokens": 224, "chunk_overlap_tokens": 32, "evidence_limit": 3, "lexical_reranking": false, "relevance_threshold": 0.05}`
- Top-1 source accuracy: `80.0%`
- Top-3 source recall: `80.8%`
- Chunk precision: `46.7%`
- Chunk recall: `83.3%`
- Chunk F1: `59.8%`
- Mean reciprocal rank: `0.820`
- Abstention accuracy: `100.0%`
- Cross-session evidence leakage: `0`
- Latency p50 / p95: `1.232 / 1.315 ms`
- Release gate: `FAIL`

## Failures

- `dev-refund-exact` — missed_relevant_source; returned []
- `dev-refund-paraphrase` — missed_relevant_source; returned ['loyalty-policy-v1']
- `dev-refund-method` — missed_relevant_source; returned ['payment-policy-v1']
- `dev-points-rate` — missed_relevant_source; returned []
- `dev-multi-christmas-delivery` — missed_relevant_source; returned ['shipping-policy-v1', 'refund-policy-v1', 'shipping-policy-v1']
