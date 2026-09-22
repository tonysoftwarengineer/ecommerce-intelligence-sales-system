from datetime import datetime, timedelta, timezone

from src.rag.chunking import ChunkingConfig, chunk_document, tokenize
from src.rag.contracts import RagDocument, RagDocumentMetadata, RagDocumentType


def _document(text: str) -> RagDocument:
    now = datetime.now(timezone.utc)
    return RagDocument(
        metadata=RagDocumentMetadata(
            document_id="doc-1",
            owner_scope_id="scope-1",
            analysis_id="analysis-1",
            filename="policy.md",
            document_type=RagDocumentType.POLICY,
            content_hash="hash",
            version=2,
            byte_count=len(text),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        ),
        text=text,
    )


def test_chunks_preserve_headings_and_have_stable_ids() -> None:
    document = _document("# Refunds\n\nRefunds take five days.\n\n## Proof\n\nKeep the receipt.")

    first = chunk_document(document, ChunkingConfig(max_tokens=32, overlap_tokens=4))
    second = chunk_document(document, ChunkingConfig(max_tokens=32, overlap_tokens=4))

    assert [chunk.heading for chunk in first] == ["Refunds", "Proof"]
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_oversized_paragraph_splits_on_sentences_with_bounded_overlap() -> None:
    sentence = "This sentence contains exactly several searchable policy words."
    document = _document("# Rules\n\n" + " ".join([sentence] * 20))

    chunks = chunk_document(document, ChunkingConfig(max_tokens=40, overlap_tokens=6))

    assert len(chunks) > 1
    assert all(len(tokenize(chunk.text)) <= 40 for chunk in chunks)
    assert all(chunk.heading == "Rules" for chunk in chunks)
