from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol


class RagDocumentType(str, Enum):
    POLICY = "policy"
    SUPPLIER_NOTICE = "supplier_notice"
    PRODUCT_CATALOG = "product_catalog"
    OPERATING_CALENDAR = "operating_calendar"
    OTHER_APPROVED = "other_approved"


class RagIndexStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    SUPERSEDED = "superseded"


class RetrievalStatus(str, Enum):
    EVIDENCE_AVAILABLE = "evidence_available"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class RagDocumentMetadata:
    document_id: str
    owner_scope_id: str
    analysis_id: str
    filename: str
    document_type: RagDocumentType
    content_hash: str
    version: int
    byte_count: int
    created_at: datetime
    expires_at: datetime
    index_status: RagIndexStatus = RagIndexStatus.PENDING
    active_for_retrieval: bool = False
    superseded_by_document_id: Optional[str] = None


@dataclass(frozen=True)
class RagDocument:
    metadata: RagDocumentMetadata
    text: str


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    owner_scope_id: str
    analysis_id: str
    document_id: str
    document_version: int
    document_type: RagDocumentType
    filename: str
    heading: Optional[str]
    text: str
    chunk_index: int


class RagDocumentRepository(Protocol):
    """Replaceable boundary: in-memory for the demo, durable storage later."""

    def create(
        self,
        owner_scope_id: str,
        analysis_id: str,
        filename: str,
        document_type: RagDocumentType,
        text: str,
    ) -> RagDocument: ...

    def get(
        self, owner_scope_id: str, analysis_id: str, document_id: str
    ) -> RagDocument: ...

    def list(
        self, owner_scope_id: str, analysis_id: str
    ) -> tuple[RagDocumentMetadata, ...]: ...

    def delete(self, owner_scope_id: str, analysis_id: str, document_id: str) -> None: ...


@dataclass(frozen=True)
class RetrievedEvidence:
    document_id: str
    filename: str
    excerpt: str
    retrieval_score: float
    chunk_id: str = ""
    document_version: int = 1
    document_type: RagDocumentType = RagDocumentType.OTHER_APPROVED
    heading: Optional[str] = None
    citation: str = ""
    rank: int = 1
    method_scores: Mapping[str, float] = field(default_factory=dict)
    rerank_score: Optional[float] = None


@dataclass(frozen=True)
class SearchCandidate:
    chunk: RagChunk
    score: float
    method_scores: Mapping[str, float] = field(default_factory=dict)
    rerank_score: Optional[float] = None


@dataclass(frozen=True)
class RetrievalResult:
    status: RetrievalStatus
    selected_method: str
    searched_document_count: int
    searched_chunk_count: int
    latency_ms: float
    reason_codes: tuple[str, ...]
    evidence: tuple[RetrievedEvidence, ...]
