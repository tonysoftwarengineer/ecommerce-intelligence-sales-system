import re
import time
from typing import Optional

from src.rag.chunking import ChunkingConfig, chunk_document
from src.rag.contracts import (
    RagDocument,
    RetrievalResult,
    RetrievalStatus,
    RetrievedEvidence,
    SearchCandidate,
)
from src.rag.index import IndexUnavailableError, RetrievalIndex

WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class EvidenceRetrievalService:
    def __init__(
        self,
        index: RetrievalIndex,
        chunking: Optional[ChunkingConfig] = None,
        relevance_threshold: float = 0.12,
        candidate_limit: int = 20,
        evidence_limit: int = 3,
        lexical_reranking: bool = False,
    ) -> None:
        self.index = index
        self.chunking = chunking or ChunkingConfig()
        self.relevance_threshold = relevance_threshold
        self.candidate_limit = candidate_limit
        self.evidence_limit = evidence_limit
        self.lexical_reranking = lexical_reranking
        self._chunks_by_scope: dict[str, dict[str, tuple]] = {}
        self._owner_by_scope: dict[str, str] = {}

    @property
    def selected_method(self) -> str:
        return self.index.name + ("_lexical_coverage" if self.lexical_reranking else "")

    def index_document(self, document: RagDocument) -> tuple:
        chunks = chunk_document(document, self.chunking)
        if not chunks:
            raise ValueError("The document contains no searchable paragraphs")
        scope_id = _retrieval_scope_id(
            document.metadata.owner_scope_id, document.metadata.analysis_id
        )
        self.index.add(scope_id, chunks)
        scope = self._chunks_by_scope.setdefault(scope_id, {})
        self._owner_by_scope[scope_id] = document.metadata.owner_scope_id
        scope[document.metadata.document_id] = chunks
        return chunks

    def delete_document(
        self, owner_scope_id: str, analysis_id: str, document_id: str
    ) -> None:
        scope_id = _retrieval_scope_id(owner_scope_id, analysis_id)
        self.index.delete_document(scope_id, document_id)
        scope = self._chunks_by_scope.get(scope_id)
        if scope is not None:
            scope.pop(document_id, None)

    def drop_scope(self, owner_scope_id: str, analysis_id: str) -> None:
        scope_id = _retrieval_scope_id(owner_scope_id, analysis_id)
        self.index.drop_scope(scope_id)
        self._chunks_by_scope.pop(scope_id, None)
        self._owner_by_scope.pop(scope_id, None)

    def drop_owner(self, owner_scope_id: str) -> None:
        scope_ids = tuple(
            scope_id
            for scope_id, owner in self._owner_by_scope.items()
            if owner == owner_scope_id
        )
        for scope_id in scope_ids:
            self.index.drop_scope(scope_id)
            self._chunks_by_scope.pop(scope_id, None)
            self._owner_by_scope.pop(scope_id, None)

    def clear(self) -> None:
        self.index.clear()
        self._chunks_by_scope.clear()
        self._owner_by_scope.clear()

    def retrieve(
        self, owner_scope_id: str, analysis_id: str, question: str
    ) -> RetrievalResult:
        started = time.perf_counter()
        scope_id = _retrieval_scope_id(owner_scope_id, analysis_id)
        scope = self._chunks_by_scope.get(scope_id, {})
        searched_document_count = len(scope)
        searched_chunk_count = sum(len(chunks) for chunks in scope.values())
        if searched_chunk_count == 0:
            return self._result(
                RetrievalStatus.INSUFFICIENT_EVIDENCE,
                started,
                searched_document_count,
                searched_chunk_count,
                ("no_active_documents",),
            )

        try:
            candidates = self.index.search(
                scope_id, question, limit=self.candidate_limit
            )
        except IndexUnavailableError:
            return self._result(
                RetrievalStatus.UNAVAILABLE,
                started,
                searched_document_count,
                searched_chunk_count,
                ("retrieval_index_unavailable",),
            )

        gated = tuple(item for item in candidates if item.score >= self.relevance_threshold)
        if not gated:
            return self._result(
                RetrievalStatus.INSUFFICIENT_EVIDENCE,
                started,
                searched_document_count,
                searched_chunk_count,
                ("no_candidate_passed_relevance_gate",),
            )
        ranked = self._rerank(question, gated) if self.lexical_reranking else gated
        selected = _deduplicate_and_diversify(question, ranked, self.evidence_limit)
        evidence = tuple(
            RetrievedEvidence(
                chunk_id=item.chunk.chunk_id,
                document_id=item.chunk.document_id,
                document_version=item.chunk.document_version,
                document_type=item.chunk.document_type,
                filename=item.chunk.filename,
                heading=item.chunk.heading,
                excerpt=item.chunk.text,
                citation=_citation(
                    item.chunk.filename,
                    item.chunk.document_version,
                    item.chunk.heading,
                    item.chunk.chunk_index,
                ),
                rank=rank,
                retrieval_score=item.score,
                method_scores=item.method_scores,
                rerank_score=item.rerank_score,
            )
            for rank, item in enumerate(selected, start=1)
        )
        return self._result(
            RetrievalStatus.EVIDENCE_AVAILABLE,
            started,
            searched_document_count,
            searched_chunk_count,
            (),
            evidence,
        )

    def _rerank(
        self, question: str, candidates: tuple[SearchCandidate, ...]
    ) -> tuple[SearchCandidate, ...]:
        query_terms = _meaningful_terms(question)
        scored = []
        for candidate in candidates:
            chunk_terms = _meaningful_terms(candidate.chunk.text)
            coverage = len(query_terms & chunk_terms) / max(len(query_terms), 1)
            scored.append(
                SearchCandidate(
                    chunk=candidate.chunk,
                    score=candidate.score,
                    method_scores=candidate.method_scores,
                    rerank_score=coverage,
                )
            )
        return tuple(
            item
            for _, item in sorted(
                enumerate(scored),
                key=lambda pair: (
                    -float(pair[1].rerank_score or 0.0),
                    -pair[1].score,
                    pair[0],
                ),
            )
        )

    def _result(
        self,
        status: RetrievalStatus,
        started: float,
        searched_document_count: int,
        searched_chunk_count: int,
        reason_codes: tuple[str, ...],
        evidence: tuple[RetrievedEvidence, ...] = (),
    ) -> RetrievalResult:
        return RetrievalResult(
            status=status,
            selected_method=self.selected_method,
            searched_document_count=searched_document_count,
            searched_chunk_count=searched_chunk_count,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            reason_codes=reason_codes,
            evidence=evidence,
        )


def _meaningful_terms(text: str) -> set[str]:
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for",
        "from", "how", "i", "in", "is", "it", "of", "on", "or", "the", "to",
        "was", "what", "when", "where", "which", "who", "why", "will", "with",
    }
    return {value.lower() for value in WORD_PATTERN.findall(text) if value.lower() not in stopwords}


def _deduplicate_and_diversify(
    question: str, candidates: tuple[SearchCandidate, ...], limit: int
) -> tuple[SearchCandidate, ...]:
    selected = []
    fingerprints: list[set[str]] = []
    selected_documents = set()
    query_terms = _meaningful_terms(question)
    covered_query_terms: set[str] = set()
    for candidate in candidates:
        if candidate.chunk.document_id in selected_documents:
            continue
        fingerprint = _meaningful_terms(candidate.chunk.text)
        if any(_jaccard(fingerprint, existing) >= 0.9 for existing in fingerprints):
            continue
        selected.append(candidate)
        fingerprints.append(fingerprint)
        selected_documents.add(candidate.chunk.document_id)
        covered_query_terms.update(query_terms & fingerprint)
        if len(selected) == limit:
            break
    if len(selected) < limit:
        for candidate in candidates:
            if candidate in selected:
                continue
            fingerprint = _meaningful_terms(candidate.chunk.text)
            if any(_jaccard(fingerprint, existing) >= 0.9 for existing in fingerprints):
                continue
            new_query_terms = (query_terms & fingerprint) - covered_query_terms
            identifier_terms = {
                term for term in new_query_terms if any(char.isdigit() for char in term)
            }
            if len(new_query_terms) < 2 and not identifier_terms:
                continue
            selected.append(candidate)
            fingerprints.append(fingerprint)
            covered_query_terms.update(new_query_terms)
            if len(selected) == limit:
                break
    return tuple(selected)


def _retrieval_scope_id(owner_scope_id: str, analysis_id: str) -> str:
    return f"{owner_scope_id}:{analysis_id}"


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _citation(
    filename: str,
    document_version: int,
    heading: Optional[str],
    chunk_index: int,
) -> str:
    location = f" § {heading}" if heading else ""
    return f"{filename} v{document_version}{location} · chunk {chunk_index + 1}"
