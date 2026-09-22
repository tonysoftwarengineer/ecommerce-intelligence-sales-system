from datetime import datetime, timedelta, timezone

import pytest

from api.document_store import DocumentNotFoundError, TemporaryDocumentStore
from src.rag.contracts import RagDocumentType, RagIndexStatus


def test_document_store_versions_same_filename_inside_one_analysis() -> None:
    store = TemporaryDocumentStore(timedelta(minutes=30))

    first = store.create("session-a", "analysis-a", "policy.md", RagDocumentType.POLICY, "First")
    second = store.create("session-a", "analysis-a", "policy.md", RagDocumentType.POLICY, "Second")
    other = store.create("session-a", "analysis-b", "policy.md", RagDocumentType.POLICY, "Other")

    assert first.metadata.version == 1
    assert second.metadata.version == 2
    assert other.metadata.version == 1
    assert first.metadata.content_hash != second.metadata.content_hash


def test_document_store_lists_and_reads_only_the_owning_analysis() -> None:
    store = TemporaryDocumentStore(timedelta(minutes=30))
    document = store.create(
        "session-a", "analysis-a", "policy.md", RagDocumentType.POLICY, "Evidence"
    )

    assert store.get("session-a", "analysis-a", document.metadata.document_id) == document
    assert store.list("session-a", "analysis-a") == (document.metadata,)
    assert store.list("session-a", "analysis-b") == ()
    with pytest.raises(DocumentNotFoundError):
        store.get("session-a", "analysis-b", document.metadata.document_id)
    with pytest.raises(DocumentNotFoundError):
        store.delete("session-b", "analysis-a", document.metadata.document_id)


def test_document_store_removes_expired_documents() -> None:
    current = [datetime(2026, 9, 17, tzinfo=timezone.utc)]
    store = TemporaryDocumentStore(timedelta(minutes=30), clock=lambda: current[0])
    store.create("session-a", "analysis-a", "policy.md", RagDocumentType.POLICY, "Evidence")

    current[0] += timedelta(minutes=30)

    assert store.cleanup_expired() == 1
    assert store.list("session-a", "analysis-a") == ()


def test_activating_latest_version_supersedes_but_retains_old_metadata() -> None:
    store = TemporaryDocumentStore(timedelta(minutes=30))
    first = store.create("session-a", "analysis-a", "policy.md", RagDocumentType.POLICY, "First")
    store.activate("session-a", "analysis-a", first.metadata.document_id)
    second = store.create("session-a", "analysis-a", "policy.md", RagDocumentType.POLICY, "Second")

    superseded = store.activate("session-a", "analysis-a", second.metadata.document_id)

    assert [item.metadata.document_id for item in superseded] == [first.metadata.document_id]
    listed = {item.document_id: item for item in store.list("session-a", "analysis-a")}
    assert listed[first.metadata.document_id].index_status == RagIndexStatus.SUPERSEDED
    assert listed[first.metadata.document_id].active_for_retrieval is False
    assert listed[second.metadata.document_id].index_status == RagIndexStatus.READY
    assert listed[second.metadata.document_id].active_for_retrieval is True
    assert len(store.active_documents("session-a", "analysis-a")) == 1
