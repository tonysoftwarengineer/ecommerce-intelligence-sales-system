import pytest
from fastapi.testclient import TestClient

import api.main as api_main
import api.routes as routes
from api.rag_service import retrieval_service as default_retrieval_service
from api.routes import analysis_store, document_store, upload_store
from src.rag.index import IndexUnavailableError, RetrievalIndex, TfidfRetrievalIndex
from src.rag.retrieval import EvidenceRetrievalService


@pytest.fixture(autouse=True)
def clear_state(monkeypatch):
    monkeypatch.setattr(routes, "retrieval_service", default_retrieval_service)
    upload_store.clear()
    analysis_store.clear()
    document_store.clear()
    default_retrieval_service.clear()
    api_main.guest_session_store.clear()
    yield
    upload_store.clear()
    analysis_store.clear()
    document_store.clear()
    default_retrieval_service.clear()
    api_main.guest_session_store.clear()


def _analysis(client: TestClient) -> str:
    client.get("/api/v1/health")
    owner_scope_id = client.cookies.get("ei_guest_session")
    assert owner_scope_id
    session = analysis_store.create(
        owner_scope_id=owner_scope_id,
        filename="sales.csv",
        report={},
        canonical_csv=b"",
        quarantine_csv=b"",
    )
    return session.analysis_id


def _upload(
    client: TestClient,
    analysis_id: str,
    text: str,
    filename: str = "policy.md",
) -> dict:
    response = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/documents",
        data={"document_type": "policy"},
        files={"file": (filename, text, "text/markdown")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_retrieval_api_returns_typed_evidence_and_honest_abstention() -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis(client)
    created = _upload(
        client,
        analysis_id,
        "# Delivery\nStandard Lagos delivery takes 2 to 4 business days.",
        "shipping.md",
    )

    found = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/retrieve",
        json={"question": "How long does standard Lagos delivery take?"},
    )
    unsupported = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/retrieve",
        json={"question": "Which television advert caused profit to rise?"},
    )

    assert found.status_code == 200
    body = found.json()
    assert body["status"] == "evidence_available"
    assert body["search_scope"] == "active_latest_documents_in_anonymous_guest_analysis"
    assert body["evidence"][0]["document_id"] == created["document_id"]
    assert body["evidence"][0]["untrusted_data"] is True
    assert body["evidence"][0]["citation"].startswith("shipping.md v1 § Delivery")
    assert unsupported.json()["status"] == "insufficient_evidence"
    assert unsupported.json()["evidence"] == []


def test_latest_version_is_the_only_searchable_version() -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis(client)
    first = _upload(client, analysis_id, "# Refunds\nThe refund window is 14 days.")
    second = _upload(client, analysis_id, "# Refunds\nThe refund window is 21 days.")

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/retrieve",
        json={"question": "What is the refund window?"},
    )
    listed = client.get(f"/api/v1/analyses/{analysis_id}/rag/documents").json()["documents"]

    assert response.json()["evidence"][0]["document_id"] == second["document_id"]
    assert "21 days" in response.json()["evidence"][0]["excerpt"]
    by_id = {item["document_id"]: item for item in listed}
    assert by_id[first["document_id"]]["index_status"] == "superseded"
    assert by_id[first["document_id"]]["active_for_retrieval"] is False


def test_failed_reindex_rolls_back_and_preserves_previous_active_version(monkeypatch) -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis(client)
    service = EvidenceRetrievalService(_FailingContentIndex())
    monkeypatch.setattr(routes, "retrieval_service", service)
    first = _upload(client, analysis_id, "# Refunds\nThe refund window is 14 days.")

    failed = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/documents",
        data={"document_type": "policy"},
        files={"file": ("policy.md", "# Refunds\nBROKEN INDEX CONTENT", "text/markdown")},
    )
    retrieval = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/retrieve",
        json={"question": "What is the refund window?"},
    )

    assert failed.status_code == 503
    assert retrieval.json()["evidence"][0]["document_id"] == first["document_id"]
    listed = client.get(f"/api/v1/analyses/{analysis_id}/rag/documents").json()["documents"]
    assert len(listed) == 1
    assert listed[0]["active_for_retrieval"] is True


def test_deleting_document_removes_its_searchable_chunks() -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis(client)
    document = _upload(client, analysis_id, "# Refunds\nThe refund window is 14 days.")

    assert (
        client.delete(
            f"/api/v1/analyses/{analysis_id}/rag/documents/{document['document_id']}"
        ).status_code
        == 204
    )
    response = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/retrieve",
        json={"question": "What is the refund window?"},
    )

    assert response.json()["status"] == "insufficient_evidence"
    assert response.json()["searched_chunk_count"] == 0


def test_another_guest_gets_404_for_valid_analysis_and_document_ids() -> None:
    owner = TestClient(api_main.app)
    stranger = TestClient(api_main.app)
    analysis_id = _analysis(owner)
    document = _upload(owner, analysis_id, "Private supplier code is BLUE-77.")

    retrieval = stranger.post(
        f"/api/v1/analyses/{analysis_id}/rag/retrieve",
        json={"question": "What is the private supplier code?"},
    )
    answer = stranger.post(
        f"/api/v1/analyses/{analysis_id}/rag/answer",
        json={"question": "What is the private supplier code?"},
    )
    deletion = stranger.delete(
        f"/api/v1/analyses/{analysis_id}/rag/documents/{document['document_id']}"
    )

    assert retrieval.status_code == 404
    assert answer.status_code == 404
    assert deletion.status_code == 404


def test_same_guest_cannot_access_document_through_another_analysis() -> None:
    client = TestClient(api_main.app)
    first_analysis = _analysis(client)
    second_analysis = _analysis(client)
    document = _upload(client, first_analysis, "Private supplier code is BLUE-77.")

    hidden_delete = client.delete(
        f"/api/v1/analyses/{second_analysis}/rag/documents/{document['document_id']}"
    )
    hidden_retrieval = client.post(
        f"/api/v1/analyses/{second_analysis}/rag/retrieve",
        json={"question": "What is the private supplier code?"},
    )

    assert hidden_delete.status_code == 404
    assert hidden_retrieval.json()["status"] == "insufficient_evidence"
    assert hidden_retrieval.json()["searched_document_count"] == 0


def test_analysis_and_guest_cleanup_remove_documents_and_indexed_chunks() -> None:
    client = TestClient(api_main.app)
    first_analysis = _analysis(client)
    second_analysis = _analysis(client)
    _upload(client, first_analysis, "Private supplier code is BLUE-77.")
    _upload(client, second_analysis, "Refund requests are accepted for 14 days.")
    owner_scope_id = client.cookies.get("ei_guest_session")
    assert owner_scope_id

    assert client.delete(f"/api/v1/analyses/{first_analysis}").status_code == 204
    first_result = default_retrieval_service.retrieve(
        owner_scope_id, first_analysis, "What is the private supplier code?"
    )
    assert first_result.searched_chunk_count == 0
    assert document_store.list(owner_scope_id, first_analysis) == ()

    assert routes.delete_owner_rag_scopes(owner_scope_id) == 1
    second_result = default_retrieval_service.retrieve(
        owner_scope_id, second_analysis, "How long are refunds accepted?"
    )
    assert second_result.searched_chunk_count == 0
    assert document_store.list(owner_scope_id, second_analysis) == ()


def test_grounded_answer_returns_only_verified_claims(monkeypatch) -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis(client)
    _upload(
        client,
        analysis_id,
        "# Delivery\nStandard Lagos delivery takes 2 to 4 business days.",
        "shipping.md",
    )
    monkeypatch.setattr(routes, "answer_provider", _ExactQuoteProvider())

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/answer",
        json={"question": "How long does standard Lagos delivery take?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "grounded_answer"
    assert body["claims"][0]["supporting_quote"] in body["evidence"][0]["excerpt"]
    assert body["claims"][0]["citation"] == body["evidence"][0]["citation"]


def test_answer_abstains_before_provider_and_bounds_invalid_output(monkeypatch) -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis(client)
    provider = _InvalidProvider()
    monkeypatch.setattr(routes, "answer_provider", provider)
    monkeypatch.setattr(
        routes,
        "retrieval_service",
        EvidenceRetrievalService(TfidfRetrievalIndex(), relevance_threshold=0.0),
    )

    no_documents = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/answer",
        json={"question": "What is the refund window?"},
    )
    assert no_documents.json()["status"] == "insufficient_evidence"
    assert no_documents.json()["claims"] == []
    assert provider.call_count == 0

    _upload(client, analysis_id, "# Refunds\nRefund requests are accepted for 14 days.")
    invalid = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/answer",
        json={"question": "How long are refunds accepted?"},
    )
    assert invalid.json()["status"] == "unavailable"
    assert invalid.json()["claims"] == []
    assert invalid.json()["reason_codes"] == ["generated_answer_failed_verification"]


def test_no_document_invalid_question_and_index_unavailable_outcomes(monkeypatch) -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis(client)

    no_documents = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/retrieve",
        json={"question": "What is the refund policy?"},
    )
    invalid = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/retrieve",
        json={"question": "天气如何？"},
    )

    assert no_documents.json()["reason_codes"] == ["no_active_documents"]
    assert invalid.status_code == 422

    unavailable_service = EvidenceRetrievalService(_SearchUnavailableIndex())
    monkeypatch.setattr(routes, "retrieval_service", unavailable_service)
    _upload(client, analysis_id, "# Refunds\nRefund requests are accepted for 14 days.")
    unavailable = client.post(
        f"/api/v1/analyses/{analysis_id}/rag/retrieve",
        json={"question": "How long are refunds accepted?"},
    )
    assert unavailable.json()["status"] == "unavailable"
    assert unavailable.json()["reason_codes"] == ["retrieval_index_unavailable"]


class _SearchUnavailableIndex(RetrievalIndex):
    name = "unavailable_test_index"

    def __init__(self) -> None:
        self._delegate = TfidfRetrievalIndex()

    def add(self, owner_scope_id, chunks) -> None:
        self._delegate.add(owner_scope_id, chunks)

    def search(self, owner_scope_id, question, limit):
        raise IndexUnavailableError("test outage")

    def delete_document(self, owner_scope_id, document_id) -> None:
        self._delegate.delete_document(owner_scope_id, document_id)

    def drop_scope(self, owner_scope_id) -> None:
        self._delegate.drop_scope(owner_scope_id)

    def clear(self) -> None:
        self._delegate.clear()


class _FailingContentIndex(TfidfRetrievalIndex):
    def add(self, owner_scope_id, chunks) -> None:
        if any("BROKEN INDEX CONTENT" in chunk.text for chunk in chunks):
            raise IndexUnavailableError("synthetic index failure")
        super().add(owner_scope_id, chunks)


class _ExactQuoteProvider:
    name = "fake"
    model = "deterministic-test-provider"

    def generate(self, question, evidence):
        quote = "Standard Lagos delivery takes 2 to 4 business days."
        return {
            "claims": [
                {
                    "claim": "Standard Lagos delivery takes two to four business days.",
                    "chunk_id": evidence[0].chunk_id,
                    "supporting_quote": quote,
                }
            ]
        }


class _InvalidProvider:
    name = "fake"
    model = "deterministic-test-provider"

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, question, evidence):
        self.call_count += 1
        return {
            "claims": [
                {
                    "claim": "This was invented.",
                    "chunk_id": evidence[0].chunk_id,
                    "supporting_quote": "This quote is not in the evidence.",
                }
            ]
        }
