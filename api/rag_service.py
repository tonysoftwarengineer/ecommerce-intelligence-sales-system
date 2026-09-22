from config import (
    RAG_CHUNK_MAX_TOKENS,
    RAG_CHUNK_OVERLAP_TOKENS,
    RAG_EMBEDDING_MODEL,
    RAG_LEXICAL_RERANKING,
    RAG_RELEVANCE_THRESHOLD,
    RAG_RETRIEVAL_BACKEND,
)
from src.rag.chunking import ChunkingConfig
from src.rag.index import ChromaRetrievalIndex, RetrievalIndex, TfidfRetrievalIndex
from src.rag.retrieval import EvidenceRetrievalService


def build_retrieval_service() -> EvidenceRetrievalService:
    index: RetrievalIndex
    if RAG_RETRIEVAL_BACKEND == "chroma":
        index = ChromaRetrievalIndex(model_name=RAG_EMBEDDING_MODEL)
    elif RAG_RETRIEVAL_BACKEND == "tfidf":
        index = TfidfRetrievalIndex()
    else:
        raise ValueError("RAG_RETRIEVAL_BACKEND must be 'tfidf' or 'chroma'")
    return EvidenceRetrievalService(
        index=index,
        chunking=ChunkingConfig(
            max_tokens=RAG_CHUNK_MAX_TOKENS,
            overlap_tokens=RAG_CHUNK_OVERLAP_TOKENS,
        ),
        relevance_threshold=RAG_RELEVANCE_THRESHOLD,
        lexical_reranking=RAG_LEXICAL_RERANKING,
    )


retrieval_service = build_retrieval_service()
