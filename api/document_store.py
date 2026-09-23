import hashlib
import secrets
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Optional

from src.rag.contracts import (
    RagDocument,
    RagDocumentMetadata,
    RagDocumentType,
    RagIndexStatus,
)


class DocumentNotFoundError(KeyError):
    pass


class DocumentExpiredError(KeyError):
    pass


class TemporaryDocumentStore:
    """Thread-safe, process-local RAG documents scoped by guest and analysis."""

    def __init__(
        self,
        ttl: timedelta,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("Document TTL must be positive")
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._documents: dict[str, RagDocument] = {}
        self._lock = RLock()

    def create(
        self,
        owner_scope_id: str,
        analysis_id: str,
        filename: str,
        document_type: RagDocumentType,
        text: str,
    ) -> RagDocument:
        now = self._clock()
        encoded = text.encode("utf-8")
        with self._lock:
            self._remove_expired(now)
            version = 1 + max(
                (
                    document.metadata.version
                    for document in self._documents.values()
                    if document.metadata.owner_scope_id == owner_scope_id
                    and document.metadata.analysis_id == analysis_id
                    and document.metadata.filename == filename
                ),
                default=0,
            )
            metadata = RagDocumentMetadata(
                document_id=secrets.token_urlsafe(32),
                owner_scope_id=owner_scope_id,
                analysis_id=analysis_id,
                filename=filename,
                document_type=document_type,
                content_hash=hashlib.sha256(encoded).hexdigest(),
                version=version,
                byte_count=len(encoded),
                created_at=now,
                expires_at=now + self._ttl,
            )
            document = RagDocument(metadata=metadata, text=text)
            self._documents[metadata.document_id] = document
            return document

    def get(self, owner_scope_id: str, analysis_id: str, document_id: str) -> RagDocument:
        now = self._clock()
        with self._lock:
            document = self._documents.get(document_id)
            if (
                document is None
                or document.metadata.owner_scope_id != owner_scope_id
                or document.metadata.analysis_id != analysis_id
            ):
                raise DocumentNotFoundError(document_id)
            if document.metadata.expires_at <= now:
                del self._documents[document_id]
                raise DocumentExpiredError(document_id)
            return document

    def list(self, owner_scope_id: str, analysis_id: str) -> tuple[RagDocumentMetadata, ...]:
        now = self._clock()
        with self._lock:
            self._remove_expired(now)
            return tuple(
                sorted(
                    (
                        document.metadata
                        for document in self._documents.values()
                        if document.metadata.owner_scope_id == owner_scope_id
                        and document.metadata.analysis_id == analysis_id
                    ),
                    key=lambda metadata: (metadata.created_at, metadata.document_id),
                )
            )

    def active_documents(self, owner_scope_id: str, analysis_id: str) -> tuple[RagDocument, ...]:
        now = self._clock()
        with self._lock:
            self._remove_expired(now)
            return tuple(
                document
                for document in self._documents.values()
                if document.metadata.owner_scope_id == owner_scope_id
                and document.metadata.analysis_id == analysis_id
                and document.metadata.active_for_retrieval
                and document.metadata.index_status == RagIndexStatus.READY
            )

    def activate(
        self, owner_scope_id: str, analysis_id: str, document_id: str
    ) -> tuple[RagDocument, ...]:
        """Atomically mark a newly indexed version active and supersede its predecessors."""
        with self._lock:
            candidate = self._documents.get(document_id)
            if (
                candidate is None
                or candidate.metadata.owner_scope_id != owner_scope_id
                or candidate.metadata.analysis_id != analysis_id
            ):
                raise DocumentNotFoundError(document_id)
            superseded = []
            for existing_id, existing in tuple(self._documents.items()):
                metadata = existing.metadata
                if (
                    existing_id != document_id
                    and metadata.owner_scope_id == owner_scope_id
                    and metadata.analysis_id == analysis_id
                    and metadata.filename == candidate.metadata.filename
                    and metadata.active_for_retrieval
                ):
                    updated = replace(
                        metadata,
                        index_status=RagIndexStatus.SUPERSEDED,
                        active_for_retrieval=False,
                        superseded_by_document_id=document_id,
                    )
                    superseded_document = replace(existing, metadata=updated)
                    self._documents[existing_id] = superseded_document
                    superseded.append(superseded_document)
            active = replace(
                candidate,
                metadata=replace(
                    candidate.metadata,
                    index_status=RagIndexStatus.READY,
                    active_for_retrieval=True,
                    superseded_by_document_id=None,
                ),
            )
            self._documents[document_id] = active
            return tuple(superseded)

    def delete(self, owner_scope_id: str, analysis_id: str, document_id: str) -> None:
        with self._lock:
            document = self._documents.get(document_id)
            if (
                document is None
                or document.metadata.owner_scope_id != owner_scope_id
                or document.metadata.analysis_id != analysis_id
            ):
                raise DocumentNotFoundError(document_id)
            del self._documents[document_id]

    def pop_analysis(self, owner_scope_id: str, analysis_id: str) -> tuple[RagDocument, ...]:
        with self._lock:
            documents = tuple(
                document
                for document in self._documents.values()
                if document.metadata.owner_scope_id == owner_scope_id
                and document.metadata.analysis_id == analysis_id
            )
            for document in documents:
                del self._documents[document.metadata.document_id]
            return documents

    def pop_owner(self, owner_scope_id: str) -> tuple[RagDocument, ...]:
        with self._lock:
            documents = tuple(
                document
                for document in self._documents.values()
                if document.metadata.owner_scope_id == owner_scope_id
            )
            for document in documents:
                del self._documents[document.metadata.document_id]
            return documents

    def cleanup_expired(self) -> int:
        with self._lock:
            return self._remove_expired(self._clock())

    def pop_expired(self) -> tuple[RagDocument, ...]:
        with self._lock:
            now = self._clock()
            expired = tuple(
                document
                for document in self._documents.values()
                if document.metadata.expires_at <= now
            )
            for document in expired:
                del self._documents[document.metadata.document_id]
            return expired

    def clear(self) -> None:
        with self._lock:
            self._documents.clear()

    def _remove_expired(self, now: datetime) -> int:
        expired = [
            document_id
            for document_id, document in self._documents.items()
            if document.metadata.expires_at <= now
        ]
        for document_id in expired:
            del self._documents[document_id]
        return len(expired)
