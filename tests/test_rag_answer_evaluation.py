import re
from pathlib import Path

from api.rag_answer_service import DeterministicFakeAnswerProvider
from src.rag.answer_evaluation import (
    answer_release_gates,
    evaluate_grounded_answers,
    evaluate_grounded_answers_with_trace,
    load_answer_evaluation_corpus,
    load_hard_development_suite,
)
from src.rag.answers import AnswerProviderError
from src.rag.chunking import ChunkingConfig, chunk_document
from src.rag.evaluation import load_evaluation_corpus
from src.rag.index import TfidfRetrievalIndex
from src.rag.retrieval import EvidenceRetrievalService

FIXTURES = Path(__file__).parent / "fixtures"


def test_answer_corpus_has_separate_required_case_types() -> None:
    corpus = load_answer_evaluation_corpus(FIXTURES / "rag_answer_evaluation" / "cases.json")

    assert corpus.cases_for_split("development")
    assert corpus.cases_for_split("locked_test")
    for split in ("development", "locked_test"):
        case_types = {case.case_type for case in corpus.cases_for_split(split)}
        assert {"unsupported", "prompt_injection", "multi_document"} <= case_types


def test_development_evaluation_measures_grounding_abstention_and_isolation() -> None:
    retrieval_corpus = load_evaluation_corpus(FIXTURES / "rag_evaluation" / "corpus.json")
    answer_corpus = load_answer_evaluation_corpus(FIXTURES / "rag_answer_evaluation" / "cases.json")
    service = EvidenceRetrievalService(
        TfidfRetrievalIndex(),
        chunking=ChunkingConfig(max_tokens=224, overlap_tokens=32),
        relevance_threshold=0.12,
    )

    metrics = evaluate_grounded_answers(
        retrieval_corpus,
        answer_corpus,
        service,
        DeterministicFakeAnswerProvider(),
        "development",
    )

    assert metrics.case_count == 6
    assert metrics.cross_scope_leakage_count == 0
    assert 0.0 <= metrics.gold_claim_coverage <= 1.0
    assert set(answer_release_gates(metrics)) == {
        "verifier_pass_rate",
        "provider_availability",
        "unsupported_abstention",
        "gold_claim_coverage",
        "scope_isolation",
        "warm_p95_latency",
    }


def test_hard_development_suite_is_separate_complete_and_chunkable() -> None:
    suite = load_hard_development_suite(FIXTURES / "rag_answer_hard_development")

    assert len(suite.retrieval_corpus.documents) == 8
    assert len(suite.answer_corpus.cases_for_split("development")) == 20
    case_types = {case.case_type for case in suite.answer_corpus.cases}
    assert {
        "direct",
        "paraphrase",
        "distractor",
        "near_match",
        "multi_document",
        "prompt_injection",
        "unsupported",
    } <= case_types
    for document in suite.retrieval_corpus.documents:
        assert 400 <= len(document.text.split()) <= 750
        assert len(re.findall(r"^#{1,6} ", document.text, re.MULTILINE)) >= 3
        chunks = chunk_document(
            document.as_rag_document(), ChunkingConfig(max_tokens=224, overlap_tokens=32)
        )
        assert len(chunks) > 1
    for case in suite.answer_corpus.cases:
        assert len(case.gold_claims) <= 2
        if case.should_abstain:
            assert case.gold_claims == ()


class _OutageProvider:
    name = "outage"
    model = "test"

    def generate(self, question, evidence):
        raise AnswerProviderError("synthetic provider outage")


def test_development_trace_separates_provider_outages_from_retrieval_misses() -> None:
    retrieval_corpus = load_evaluation_corpus(FIXTURES / "rag_evaluation" / "corpus.json")
    answer_corpus = load_answer_evaluation_corpus(FIXTURES / "rag_answer_evaluation" / "cases.json")
    service = EvidenceRetrievalService(
        TfidfRetrievalIndex(),
        chunking=ChunkingConfig(max_tokens=224, overlap_tokens=32),
        relevance_threshold=0.12,
    )

    metrics, trace = evaluate_grounded_answers_with_trace(
        retrieval_corpus,
        answer_corpus,
        service,
        _OutageProvider(),
        "development",
    )

    # The frozen baseline intentionally contains difficult paraphrases. This
    # deterministic lexical run finds evidence for two supported cases and
    # classifies the remaining supported cases as retrieval misses.
    assert metrics.provider_unavailable_count == 2
    assert metrics.provider_response_count == 0
    assert metrics.verifier_pass_rate is None
    assert metrics.verifier_rejection_count == 0
    assert metrics.retrieval_miss_count == 3
    assert len(trace.cases) == 6
    supported_trace = next(
        case
        for case in trace.cases
        if case["answer"]["reason_codes"] == ["answer_provider_unavailable"]
    )
    assert supported_trace["answer"]["reason_codes"] == ["answer_provider_unavailable"]
    assert supported_trace["answer"]["generated_payload"] is None


class _InvalidOutputProvider:
    name = "invalid-output"
    model = "test"

    def generate(self, question, evidence):
        return {
            "claims": [
                {
                    "claim": "Unsupported statement.",
                    "chunk_id": evidence[0].chunk_id,
                    "supporting_quote": "not an exact quote",
                }
            ]
        }


def test_development_trace_records_verifier_rejection_and_raw_payload() -> None:
    retrieval_corpus = load_evaluation_corpus(FIXTURES / "rag_evaluation" / "corpus.json")
    answer_corpus = load_answer_evaluation_corpus(FIXTURES / "rag_answer_evaluation" / "cases.json")
    service = EvidenceRetrievalService(
        TfidfRetrievalIndex(),
        chunking=ChunkingConfig(max_tokens=224, overlap_tokens=32),
        relevance_threshold=0.12,
    )

    metrics, trace = evaluate_grounded_answers_with_trace(
        retrieval_corpus,
        answer_corpus,
        service,
        _InvalidOutputProvider(),
        "development",
    )

    assert metrics.verifier_rejection_count == 2
    rejected = next(
        case
        for case in trace.cases
        if case["answer"]["reason_codes"] == ["generated_answer_failed_verification"]
    )
    assert rejected["answer"]["reason_codes"] == ["generated_answer_failed_verification"]
    assert (
        rejected["answer"]["generated_payload"]["claims"][0]["supporting_quote"]
        == "not an exact quote"
    )
