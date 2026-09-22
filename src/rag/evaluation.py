import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.rag.contracts import RagDocument, RagDocumentMetadata, RagDocumentType, RagIndexStatus


@dataclass(frozen=True)
class EvaluationDocument:
    document_id: str
    filename: str
    document_type: RagDocumentType
    text: str

    def as_rag_document(
        self,
        owner_scope_id: str = "evaluation-scope",
        analysis_id: str = "evaluation-analysis",
    ) -> RagDocument:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return RagDocument(
            metadata=RagDocumentMetadata(
                document_id=self.document_id,
                owner_scope_id=owner_scope_id,
                analysis_id=analysis_id,
                filename=self.filename,
                document_type=self.document_type,
                content_hash="evaluation",
                version=1,
                byte_count=len(self.text.encode("utf-8")),
                created_at=now,
                expires_at=now + timedelta(days=1),
                index_status=RagIndexStatus.READY,
                active_for_retrieval=True,
            ),
            text=self.text,
        )


@dataclass(frozen=True)
class RequiredEvidence:
    document_id: str
    passage: str


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    split: str
    case_type: str
    question: str
    relevant_document_ids: tuple[str, ...]
    required_evidence: tuple[RequiredEvidence, ...]
    should_abstain: bool
    prompt_injection_case: bool


@dataclass(frozen=True)
class RagEvaluationCorpus:
    documents: tuple[EvaluationDocument, ...]
    cases: tuple[EvaluationCase, ...]

    def cases_for_split(self, split: str) -> tuple[EvaluationCase, ...]:
        return tuple(case for case in self.cases if case.split == split)


def load_evaluation_corpus(path: Path) -> RagEvaluationCorpus:
    """Load and validate the version-controlled retrieval benchmark."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = tuple(
        EvaluationDocument(
            document_id=item["document_id"],
            filename=item["filename"],
            document_type=RagDocumentType(item["document_type"]),
            text=item["text"],
        )
        for item in payload["documents"]
    )
    cases = tuple(
        EvaluationCase(
            case_id=item["case_id"],
            split=item["split"],
            case_type=item["case_type"],
            question=item["question"],
            relevant_document_ids=tuple(item["relevant_document_ids"]),
            required_evidence=tuple(
                RequiredEvidence(
                    document_id=evidence["document_id"],
                    passage=evidence["passage"],
                )
                for evidence in item["required_evidence"]
            ),
            should_abstain=bool(item["should_abstain"]),
            prompt_injection_case=bool(item["prompt_injection_case"]),
        )
        for item in payload["cases"]
    )
    _validate_corpus(documents, cases)
    return RagEvaluationCorpus(documents=documents, cases=cases)


def _validate_corpus(
    documents: tuple[EvaluationDocument, ...],
    cases: tuple[EvaluationCase, ...],
) -> None:
    document_ids = {document.document_id for document in documents}
    if len(document_ids) != len(documents):
        raise ValueError("RAG evaluation document IDs must be unique")
    case_ids = {case.case_id for case in cases}
    if len(case_ids) != len(cases):
        raise ValueError("RAG evaluation case IDs must be unique")
    if {case.split for case in cases} != {"development", "locked_test"}:
        raise ValueError("RAG evaluation corpus requires development and locked_test splits")
    if not any(case.should_abstain for case in cases):
        raise ValueError("RAG evaluation corpus must include an abstention case")
    if not any(case.prompt_injection_case for case in cases):
        raise ValueError("RAG evaluation corpus must include a prompt-injection case")
    for case in cases:
        unknown = set(case.relevant_document_ids) - document_ids
        if unknown:
            raise ValueError(
                f"Evaluation case {case.case_id!r} references unknown documents: {sorted(unknown)}"
            )
        evidence_documents = {evidence.document_id for evidence in case.required_evidence}
        if not evidence_documents.issubset(set(case.relevant_document_ids)):
            raise ValueError(f"Case {case.case_id!r} has evidence for a non-relevant document")
        if case.should_abstain and (case.relevant_document_ids or case.required_evidence):
            raise ValueError("Abstention cases cannot declare supporting evidence")
        if not case.should_abstain and not case.required_evidence:
            raise ValueError("Supported cases must declare required evidence passages")
