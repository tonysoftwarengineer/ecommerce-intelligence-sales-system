import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from api.rag_answer_service import DeterministicFakeAnswerProvider
from scripts.evaluate_rag_answers import (
    _evaluation_conclusion,
    _gate_result,
    _markdown,
    _provider_reason_counts,
    _ProviderPacer,
)
from src.rag.answer_evaluation import (
    AnswerEvaluationCase,
    AnswerEvaluationCorpus,
    GoldClaim,
    answer_release_gates,
    evaluate_grounded_answers,
    evaluate_grounded_answers_with_trace,
    load_answer_evaluation_corpus,
    load_hard_development_suite,
)
from src.rag.answers import AnswerProviderError, ProviderGeneration
from src.rag.chunking import ChunkingConfig, chunk_document
from src.rag.contracts import RetrievalResult, RetrievalStatus, RetrievedEvidence
from src.rag.evaluation import RagEvaluationCorpus, load_evaluation_corpus
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


def test_evaluation_summary_counts_groq_and_gemini_provider_failures() -> None:
    trace = {
        "cases": [
            {"answer": {"reason_codes": ["answer_provider_unavailable", "groq_http_429"]}},
            {"answer": {"reason_codes": ["gemini_http_503"]}},
            {"answer": {"reason_codes": ["generated_answer_failed_verification"]}},
        ]
    }

    assert _provider_reason_counts(trace) == {"gemini_http_503": 1, "groq_http_429": 1}


def test_provider_outages_make_a_real_provider_run_inconclusive() -> None:
    class _Metrics:
        provider_unavailable_count = 1

    gates = {"provider_availability": False, "gold_claim_coverage": False}

    assert _evaluation_conclusion(_Metrics(), gates) == "inconclusive"
    assert (
        _gate_result("provider_availability", False, "inconclusive")
        == "inconclusive (upstream provider failures)"
    )
    assert (
        _gate_result("gold_claim_coverage", False, "inconclusive")
        == "inconclusive (incomplete provider responses)"
    )


def test_provider_pacer_waits_outside_generation() -> None:
    now = [0.0]
    delays = []

    def clock() -> float:
        return now[0]

    def sleeper(seconds: float) -> None:
        delays.append(seconds)
        now[0] += seconds

    paced = _ProviderPacer(minimum_interval_seconds=5, clock=clock, sleeper=sleeper)
    assert paced.wait() == 0
    now[0] += 1
    assert paced.wait() == 4
    assert delays == [4]


EVIDENCE = RetrievedEvidence(
    document_id="test-policy",
    filename="policy.md",
    excerpt="Delivery takes 3 days. Refunds take 5 days.",
    retrieval_score=1.0,
    chunk_id="test-chunk",
    citation="policy.md section 1",
)


class _ScriptedRetrieval:
    """No model or network: returns only explicitly supplied in-scope evidence."""

    def __init__(self, results):
        self.results = results

    def clear(self):
        pass

    def index_document(self, document):
        raise AssertionError("This fixture does not index documents")

    def retrieve(self, owner, analysis, question):
        if owner != "answer-evaluation-owner" or analysis != "answer-evaluation-analysis":
            return _retrieval(())
        return self.results[question]


def _retrieval(evidence, status=None):
    return RetrievalResult(
        status=status
        or (
            RetrievalStatus.EVIDENCE_AVAILABLE
            if evidence
            else RetrievalStatus.INSUFFICIENT_EVIDENCE
        ),
        selected_method="scripted",
        searched_document_count=1,
        searched_chunk_count=1,
        latency_ms=10.0,
        reason_codes=(),
        evidence=evidence,
    )


def _case(case_id="first", passages=("Delivery takes 3 days",), should_abstain=False):
    return AnswerEvaluationCase(
        case_id,
        "development",
        "direct",
        case_id,
        should_abstain,
        tuple(GoldClaim("test-policy", passage) for passage in passages),
    )


class _PayloadProvider:
    name = "fake"
    model = "test"

    def __init__(self, payload, wrapped=False):
        self.payload = payload
        self.wrapped = wrapped
        self.calls = 0

    def generate(self, question, evidence):
        self.calls += 1
        return ProviderGeneration(self.payload) if self.wrapped else self.payload


def _payload(quote="Delivery takes 3 days"):
    return {
        "claims": [
            {
                "claim": "Delivery takes 3 days.",
                "chunk_id": EVIDENCE.chunk_id,
                "supporting_quote": quote,
            }
        ]
    }


def _diagnose(provider, cases=None, results=None, before_provider_call=None):
    cases = cases or (_case(),)
    results = results or {case.question: _retrieval((EVIDENCE,)) for case in cases}
    return evaluate_grounded_answers_with_trace(
        RagEvaluationCorpus(documents=(), cases=()),
        AnswerEvaluationCorpus(cases=cases),
        _ScriptedRetrieval(results),
        provider,
        "development",
        before_provider_call=before_provider_call,
    )


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    "quote,verified", [("Delivery takes 3 days", True), ("invented quote", False)]
)
def test_trace_preserves_payload_and_verified_claims(wrapped, quote, verified):
    payload = _payload(quote)
    metrics, trace = _diagnose(_PayloadProvider(payload, wrapped))
    answer = trace.cases[0]["answer"]
    assert answer["generated_payload"] == payload
    assert len(answer["verified_claims"]) == int(verified)
    assert metrics.gold_claim_coverage == int(verified)
    assert metrics.provider_available_gold_claim_count == 1
    assert metrics.provider_available_gold_claim_coverage == int(verified)
    json.dumps(trace.as_dict())


@pytest.mark.parametrize("payload", [None, {"wrong": "malformed"}, "not JSON"])
def test_malformed_returned_payload_is_retained_and_counted(payload):
    metrics, trace = _diagnose(_PayloadProvider(payload, wrapped=True))
    assert trace.cases[0]["answer"]["generated_payload"] == payload
    assert trace.cases[0]["answer"]["verified_claims"] == []
    assert "verifier_rejection" in trace.cases[0]["failure_reasons"]
    assert metrics.provider_available_gold_claim_count == 1
    assert metrics.provider_available_gold_claim_coverage == 0


def test_nonempty_retrieval_can_still_miss_reference_evidence():
    wrong_document = replace(EVIDENCE, document_id="another-policy")
    metrics, trace = _diagnose(
        _PayloadProvider(_payload()), results={"first": _retrieval((wrong_document,))}
    )
    assert metrics.retrieval_miss_count == 0
    assert metrics.missing_reference_evidence_count == 1
    assert trace.cases[0]["reference_evidence"][0]["evidence_available"] is False
    assert "missing_reference_evidence" in trace.cases[0]["failure_reasons"]


def test_multipart_partial_coverage_diagnoses_answer_wording_not_retrieval():
    metrics, trace = _diagnose(
        _PayloadProvider(_payload()),
        cases=(_case(passages=("Delivery takes 3 days", "Refunds take 5 days")),),
    )
    assert metrics.gold_claim_coverage == 0.5
    assert metrics.missing_reference_evidence_count == 0
    assert metrics.answer_reference_mismatch_count == 1
    assert all(item["evidence_available"] for item in trace.cases[0]["reference_evidence"])
    assert "answer_reference_mismatch" in trace.cases[0]["failure_reasons"]


def test_one_case_can_have_both_missing_evidence_and_answer_mismatch():
    metrics, trace = _diagnose(
        _PayloadProvider(_payload()),
        cases=(_case(passages=("Refunds take 5 days", "unretrieved rule")),),
    )
    assert metrics.missing_reference_evidence_count == 1
    assert metrics.answer_reference_mismatch_count == 1
    assert {"missing_reference_evidence", "answer_reference_mismatch", "missing_gold_claim"} <= set(
        trace.cases[0]["failure_reasons"]
    )


def test_supplemental_coverage_excludes_outages_and_empty_retrieval():
    class _MixedProvider(_PayloadProvider):
        def generate(self, question, evidence):
            if question == "outage":
                raise AnswerProviderError("outage", "groq_http_429")
            return super().generate(question, evidence)

    cases = (
        _case("first"),
        _case("outage", ("Delivery takes 3 days", "Refunds take 5 days")),
        _case("empty"),
        _case("unsupported", (), True),
    )
    results = {
        case.question: _retrieval((EVIDENCE,) if case.case_id in {"first", "outage"} else ())
        for case in cases
    }
    provider = _MixedProvider(_payload(), True)
    metrics, trace = _diagnose(provider, cases, results)
    assert metrics.matched_gold_claim_count == 1
    assert metrics.gold_claim_count == 4
    assert metrics.gold_claim_coverage == 0.25
    assert metrics.provider_available_matched_gold_claim_count == 1
    assert metrics.provider_available_gold_claim_count == 1
    assert metrics.provider_available_gold_claim_coverage == 1.0
    assert metrics.unsupported_abstention_accuracy == 1
    assert metrics.retrieval_miss_count == 1
    assert metrics.provider_unavailable_count == 1
    assert trace.cases[1]["answer"]["generated_payload"] is None
    assert trace.cases[1]["answer"]["verified_claims"] == []
    assert provider.calls == 1  # empty/unsupported do not call the provider


def test_pacing_excluded_from_processing_latency_and_skips_unsupported(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("src.rag.answers.time.perf_counter", lambda: now[0])

    class _TimedProvider(_PayloadProvider):
        def generate(self, question, evidence):
            now[0] += 0.2
            return super().generate(question, evidence)

    def sleep(seconds):
        now[0] += seconds

    pacer = _ProviderPacer(5, clock=lambda: now[0], sleeper=sleep)
    cases = (_case("first"), _case("unsupported", (), True), _case("second"))
    results = {
        case.question: _retrieval(() if case.should_abstain else (EVIDENCE,)) for case in cases
    }
    provider = _TimedProvider(_payload(), True)
    metrics, trace = _diagnose(provider, cases, results, pacer.wait)
    assert provider.calls == 2
    assert metrics.pacing_delay_ms == 4800
    assert metrics.p95_latency_ms == 210
    assert [case["pacing_delay_ms"] for case in trace.cases] == [0, 0, 4800]
    assert [case["processing_latency_ms"] for case in trace.cases] == [210, 10, 210]


def test_report_is_aggregate_only_and_labels_measurement_limits():
    metrics, _ = _diagnose(_PayloadProvider(_payload()))
    report = _markdown(
        {
            "metrics": metrics.as_dict(),
            "release_gates": answer_release_gates(metrics),
            "evaluation_conclusion": "passed",
            "provider": "fake",
            "model": "test",
            "suite": "hard-development",
            "provider_reason_counts": {},
            "private_trace": {
                "question": "private question",
                "key": "private credential",
                "excerpt": EVIDENCE.excerpt,
            },
        }
    )
    for secret in (
        "private question",
        "private credential",
        EVIDENCE.document_id,
        EVIDENCE.chunk_id,
        EVIDENCE.excerpt,
        EVIDENCE.filename,
    ):
        assert secret not in report
    assert "reference-passage matching" in report
    assert "warm-up not established" in report
    assert "(1/1)" in report
