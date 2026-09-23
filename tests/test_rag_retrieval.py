from datetime import timedelta

from api.document_store import TemporaryDocumentStore
from src.rag.chunking import ChunkingConfig
from src.rag.contracts import RagDocumentType, RetrievalStatus
from src.rag.index import ChromaRetrievalIndex, TfidfRetrievalIndex
from src.rag.retrieval import EvidenceRetrievalService

ANALYSIS_ID = "analysis-a"


def _service(threshold: float = 0.12) -> EvidenceRetrievalService:
    return EvidenceRetrievalService(
        TfidfRetrievalIndex(),
        chunking=ChunkingConfig(max_tokens=128, overlap_tokens=32),
        relevance_threshold=threshold,
    )


def test_retrieval_returns_diverse_cited_evidence_and_abstains_honestly() -> None:
    store = TemporaryDocumentStore(timedelta(hours=1))
    service = _service()
    refund = store.create(
        "guest-a",
        ANALYSIS_ID,
        "refund.md",
        RagDocumentType.POLICY,
        "# Refunds\nRefunds are allowed within 14 days with a receipt.",
    )
    shipping = store.create(
        "guest-a",
        ANALYSIS_ID,
        "shipping.md",
        RagDocumentType.POLICY,
        "# Shipping\nStandard Lagos delivery takes 2 to 4 business days.",
    )
    service.index_document(refund)
    service.index_document(shipping)

    found = service.retrieve("guest-a", ANALYSIS_ID, "How long does Lagos delivery take?")
    unsupported = service.retrieve(
        "guest-a", ANALYSIS_ID, "Which television advert caused our profit?"
    )

    assert found.status == RetrievalStatus.EVIDENCE_AVAILABLE
    assert found.evidence[0].filename == "shipping.md"
    assert found.evidence[0].citation.startswith("shipping.md v1 § Shipping")
    assert unsupported.status == RetrievalStatus.INSUFFICIENT_EVIDENCE
    assert unsupported.evidence == ()


def test_focused_sku_question_does_not_add_unrelated_catalog_chunk() -> None:
    store = TemporaryDocumentStore(timedelta(hours=1))
    service = _service()
    catalog = store.create(
        "guest-a",
        ANALYSIS_ID,
        "menu.md",
        RagDocumentType.PRODUCT_CATALOG,
        (
            "# Prepared meals\nSKU FOOD-002 is Jollof Rice, sold by the portion.\n\n"
            "# Drinks\nSKU DRINK-001 is Chapman, sold by the bottle."
        ),
    )
    service.index_document(catalog)

    result = service.retrieve("guest-a", ANALYSIS_ID, "Which menu item is SKU FOOD-002?")

    assert result.status == RetrievalStatus.EVIDENCE_AVAILABLE
    assert len(result.evidence) == 1
    assert "FOOD-002" in result.evidence[0].excerpt
    assert "DRINK-001" not in result.evidence[0].excerpt


def test_multi_part_question_keeps_distinct_document_evidence() -> None:
    store = TemporaryDocumentStore(timedelta(hours=1))
    service = _service(threshold=0.0)
    refund = store.create(
        "guest-a",
        ANALYSIS_ID,
        "refund.md",
        RagDocumentType.POLICY,
        "# Refunds\nRefund requests are accepted within 14 calendar days.",
    )
    shipping = store.create(
        "guest-a",
        ANALYSIS_ID,
        "shipping.md",
        RagDocumentType.POLICY,
        "# Shipping\nStandard delivery takes 2 to 4 business days.",
    )
    service.index_document(refund)
    service.index_document(shipping)

    result = service.retrieve(
        "guest-a",
        ANALYSIS_ID,
        "What is the refund request window and how long does standard delivery take?",
    )

    assert result.status == RetrievalStatus.EVIDENCE_AVAILABLE
    assert {item.filename for item in result.evidence} == {"refund.md", "shipping.md"}


def test_retrieval_never_searches_another_scope() -> None:
    store = TemporaryDocumentStore(timedelta(hours=1))
    service = _service()
    secret = store.create(
        "guest-a",
        ANALYSIS_ID,
        "private.md",
        RagDocumentType.OTHER_APPROVED,
        "The private supplier code is BLUE-77.",
    )
    service.index_document(secret)

    result = service.retrieve("guest-b", ANALYSIS_ID, "What is the private supplier code?")

    assert result.status == RetrievalStatus.INSUFFICIENT_EVIDENCE
    assert result.searched_document_count == 0
    assert result.evidence == ()


def test_guest_collection_name_is_hashed_and_does_not_expose_session_id() -> None:
    session_id = "sensitive-guest-session-token"

    name = ChromaRetrievalIndex.collection_name(session_id)

    assert name.startswith("analysis_")
    assert session_id not in name
    assert name == ChromaRetrievalIndex.collection_name(session_id)


def test_dropping_scope_removes_all_searchable_state() -> None:
    store = TemporaryDocumentStore(timedelta(hours=1))
    service = _service()
    document = store.create(
        "guest-a",
        ANALYSIS_ID,
        "policy.md",
        RagDocumentType.POLICY,
        "Refund requests are accepted for 14 days.",
    )
    service.index_document(document)

    service.drop_scope("guest-a", ANALYSIS_ID)
    result = service.retrieve("guest-a", ANALYSIS_ID, "How long are refunds accepted?")

    assert result.status == RetrievalStatus.INSUFFICIENT_EVIDENCE
    assert result.searched_chunk_count == 0
