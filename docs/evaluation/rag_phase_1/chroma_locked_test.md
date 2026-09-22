# RAG Phase 1 Retrieval Evaluation

- Backend: `chroma`
- Split: `locked_test`
- Configuration: `{"candidate_limit": 20, "chunk_max_tokens": 224, "chunk_overlap_tokens": 32, "evidence_limit": 3, "lexical_reranking": false, "relevance_threshold": 0.4}`
- Top-1 source accuracy: `93.8%`
- Top-3 source recall: `94.1%`
- Chunk precision: `76.2%`
- Chunk recall: `94.7%`
- Chunk F1: `84.5%`
- Mean reciprocal rank: `0.938`
- Abstention accuracy: `100.0%`
- Cross-session evidence leakage: `0`
- Latency p50 / p95: `7.623 / 8.482 ms`
- Release gate: `PASS`

## Failures

- `lock-branches` — missed_relevant_source; returned []
