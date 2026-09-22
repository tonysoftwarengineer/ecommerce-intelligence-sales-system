# RAG Phase 1 Retrieval Evaluation

- Backend: `chroma`
- Split: `development`
- Configuration: `{"candidate_limit": 20, "chunk_max_tokens": 224, "chunk_overlap_tokens": 32, "evidence_limit": 3, "lexical_reranking": false, "relevance_threshold": 0.4}`
- Top-1 source accuracy: `100.0%`
- Top-3 source recall: `100.0%`
- Chunk precision: `70.3%`
- Chunk recall: `100.0%`
- Chunk F1: `82.5%`
- Mean reciprocal rank: `1.000`
- Abstention accuracy: `100.0%`
- Cross-session evidence leakage: `0`
- Latency p50 / p95: `7.489 / 8.179 ms`
- Release gate: `PASS`

## Failures

- None
