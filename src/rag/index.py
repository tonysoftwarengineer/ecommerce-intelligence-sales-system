import hashlib
from abc import ABC, abstractmethod
from threading import RLock
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.rag.contracts import RagChunk, SearchCandidate


class IndexUnavailableError(RuntimeError):
    pass


class RetrievalIndex(ABC):
    name: str

    @abstractmethod
    def add(self, scope_id: str, chunks: tuple[RagChunk, ...]) -> None: ...

    @abstractmethod
    def search(self, scope_id: str, question: str, limit: int) -> tuple[SearchCandidate, ...]: ...

    @abstractmethod
    def delete_document(self, scope_id: str, document_id: str) -> None: ...

    @abstractmethod
    def drop_scope(self, scope_id: str) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...


class TfidfRetrievalIndex(RetrievalIndex):
    """Deterministic lexical baseline and ordinary-test backend."""

    name = "tfidf"

    def __init__(self) -> None:
        self._chunks: dict[str, dict[str, RagChunk]] = {}
        self._lock = RLock()

    def add(self, scope_id: str, chunks: tuple[RagChunk, ...]) -> None:
        with self._lock:
            scope = self._chunks.setdefault(scope_id, {})
            scope.update({chunk.chunk_id: chunk for chunk in chunks})

    def search(self, scope_id: str, question: str, limit: int) -> tuple[SearchCandidate, ...]:
        with self._lock:
            chunks = tuple(self._chunks.get(scope_id, {}).values())
        if not chunks:
            return ()
        corpus = [chunk.text for chunk in chunks]
        try:
            vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
            matrix = vectorizer.fit_transform((*corpus, question))
        except ValueError:
            return ()
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        ranked = sorted(zip(chunks, scores), key=lambda item: (-float(item[1]), item[0].chunk_id))[
            :limit
        ]
        return tuple(
            SearchCandidate(
                chunk=chunk,
                score=float(score),
                method_scores={self.name: float(score)},
            )
            for chunk, score in ranked
        )

    def delete_document(self, scope_id: str, document_id: str) -> None:
        with self._lock:
            scope = self._chunks.get(scope_id)
            if scope is None:
                return
            self._chunks[scope_id] = {
                chunk_id: chunk
                for chunk_id, chunk in scope.items()
                if chunk.document_id != document_id
            }

    def drop_scope(self, scope_id: str) -> None:
        with self._lock:
            self._chunks.pop(scope_id, None)

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()


class ChromaRetrievalIndex(RetrievalIndex):
    """Lazy local MiniLM/Chroma index with one hashed collection per guest."""

    name = "chroma_minilm"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._client: Any = None
        self._embedding_function = None
        self._collection_names: set[str] = set()
        self._lock = RLock()

    def _ensure_runtime(self):
        if self._client is not None:
            return
        try:
            import chromadb
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

            self._client = chromadb.EphemeralClient()
            self._embedding_function = SentenceTransformerEmbeddingFunction(
                model_name=self._model_name,
                normalize_embeddings=True,
            )
        except Exception as exc:
            raise IndexUnavailableError(
                "The local semantic retrieval model is unavailable"
            ) from exc

    @staticmethod
    def collection_name(scope_id: str) -> str:
        digest = hashlib.sha256(scope_id.encode("utf-8")).hexdigest()
        return f"analysis_{digest[:40]}"

    def _collection(self, scope_id: str):
        self._ensure_runtime()
        name = self.collection_name(scope_id)
        try:
            collection = self._client.get_or_create_collection(
                name=name,
                embedding_function=self._embedding_function,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            raise IndexUnavailableError("The semantic evidence index is unavailable") from exc
        self._collection_names.add(name)
        return collection

    def add(self, scope_id: str, chunks: tuple[RagChunk, ...]) -> None:
        if not chunks:
            raise ValueError("A document must produce at least one searchable chunk")
        collection = self._collection(scope_id)
        try:
            collection.upsert(
                ids=[chunk.chunk_id for chunk in chunks],
                documents=[chunk.text for chunk in chunks],
                metadatas=[
                    {
                        "owner_scope_id": chunk.owner_scope_id,
                        "analysis_id": chunk.analysis_id,
                        "retrieval_scope_id": scope_id,
                        "document_id": chunk.document_id,
                        "document_version": chunk.document_version,
                        "document_type": chunk.document_type.value,
                        "filename": chunk.filename,
                        "heading": chunk.heading or "",
                        "chunk_index": chunk.chunk_index,
                    }
                    for chunk in chunks
                ],
            )
        except Exception as exc:
            raise IndexUnavailableError("The document could not be indexed") from exc

    def search(self, scope_id: str, question: str, limit: int) -> tuple[SearchCandidate, ...]:
        collection = self._collection(scope_id)
        if collection.count() == 0:
            return ()
        try:
            result = collection.query(
                query_texts=[question],
                n_results=min(limit, collection.count()),
                where={"retrieval_scope_id": scope_id},
                include=["documents", "metadatas", "distances"],
            )
            ids = result["ids"][0]
            texts = result["documents"][0]
            metadata = result["metadatas"][0]
            distances = result["distances"][0]
        except Exception as exc:
            raise IndexUnavailableError(
                "The semantic evidence index could not be searched"
            ) from exc

        candidates = []
        for chunk_id, text, item, distance in zip(ids, texts, metadata, distances):
            score = max(0.0, 1.0 - float(distance))
            chunk = RagChunk(
                chunk_id=str(chunk_id),
                owner_scope_id=str(item["owner_scope_id"]),
                analysis_id=str(item["analysis_id"]),
                document_id=str(item["document_id"]),
                document_version=int(item["document_version"]),
                document_type=_document_type(str(item["document_type"])),
                filename=str(item["filename"]),
                heading=str(item["heading"]) or None,
                text=str(text),
                chunk_index=int(item["chunk_index"]),
            )
            candidates.append(
                SearchCandidate(chunk=chunk, score=score, method_scores={self.name: score})
            )
        return tuple(candidates)

    def delete_document(self, scope_id: str, document_id: str) -> None:
        try:
            self._collection(scope_id).delete(
                where={
                    "$and": [
                        {"retrieval_scope_id": scope_id},
                        {"document_id": document_id},
                    ]
                }
            )
        except IndexUnavailableError:
            raise
        except Exception as exc:
            raise IndexUnavailableError("Indexed document cleanup failed") from exc

    def drop_scope(self, scope_id: str) -> None:
        if self._client is None:
            return
        name = self.collection_name(scope_id)
        try:
            self._client.delete_collection(name)
        except Exception:
            pass
        self._collection_names.discard(name)

    def clear(self) -> None:
        if self._client is None:
            return
        for name in tuple(self._collection_names):
            try:
                self._client.delete_collection(name)
            except Exception:
                pass
        self._collection_names.clear()


def _document_type(value: str):
    from src.rag.contracts import RagDocumentType

    return RagDocumentType(value)
