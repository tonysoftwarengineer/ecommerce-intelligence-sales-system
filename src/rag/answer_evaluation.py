import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from src.rag.answers import (
    AnswerStatus,
    GroundedAnswerProvider,
    generate_grounded_answer,
)
from src.rag.contracts import RagDocumentType, RetrievedEvidence
from src.rag.evaluation import EvaluationDocument, RagEvaluationCorpus
from src.rag.retrieval import EvidenceRetrievalService


@dataclass(frozen=True)
class GoldClaim:
    document_id: str
    passage: str


@dataclass(frozen=True)
class AnswerEvaluationCase:
    case_id: str
    split: str
    case_type: str
    question: str
    should_abstain: bool
    gold_claims: tuple[GoldClaim, ...]


@dataclass(frozen=True)
class AnswerEvaluationCorpus:
    cases: tuple[AnswerEvaluationCase, ...]

    def cases_for_split(self, split: str) -> tuple[AnswerEvaluationCase, ...]:
        return tuple(case for case in self.cases if case.split == split)


@dataclass(frozen=True)
class HardDevelopmentSuite:
    """A separately versioned answer-quality corpus used only for development."""

    retrieval_corpus: RagEvaluationCorpus
    answer_corpus: AnswerEvaluationCorpus


@dataclass(frozen=True)
class AnswerEvaluationMetrics:
    split: str
    case_count: int
    supported_case_count: int
    unsupported_case_count: int
    verifier_pass_rate: Optional[float]
    unsupported_abstention_accuracy: float
    gold_claim_coverage: float
    cross_scope_leakage_count: int
    p95_latency_ms: float
    provider_unavailable_count: int
    provider_response_count: int
    verifier_rejection_count: int
    retrieval_miss_count: int
    failures: tuple[dict[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AnswerEvaluationTrace:
    """Development-only diagnostics; never produced by the API or dashboard."""

    split: str
    cases: tuple[dict[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def load_answer_evaluation_corpus(path: Path) -> AnswerEvaluationCorpus:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = _parse_answer_cases(payload["cases"])
    _validate_answer_cases(cases, {"development", "locked_test"})
    for split in ("development", "locked_test"):
        split_cases = tuple(case for case in cases if case.split == split)
        if not any(case.should_abstain for case in split_cases):
            raise ValueError(f"{split} requires an unsupported question")
        if not any(case.case_type == "prompt_injection" for case in split_cases):
            raise ValueError(f"{split} requires a prompt-injection question")
        if not any(case.case_type == "multi_document" for case in split_cases):
            raise ValueError(f"{split} requires a multi-document question")
    return AnswerEvaluationCorpus(cases=cases)


def load_hard_development_suite(root: Path) -> HardDevelopmentSuite:
    """Load synthetic Markdown sources without altering frozen Phase 1 fixtures."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    documents = tuple(
        EvaluationDocument(
            document_id=item["document_id"],
            filename=item["filename"],
            document_type=RagDocumentType(item["document_type"]),
            text=(root / item["path"]).read_text(encoding="utf-8"),
        )
        for item in manifest["documents"]
    )
    cases = _parse_answer_cases(manifest["cases"])
    _validate_answer_cases(cases, {"development"})
    if len(documents) != 8:
        raise ValueError("Hard development suite requires exactly eight documents")
    if len({document.document_id for document in documents}) != len(documents):
        raise ValueError("Hard development document IDs must be unique")
    if len(cases) != 20:
        raise ValueError("Hard development suite requires exactly twenty cases")
    types = {case.case_type for case in cases}
    required_types = {
        "direct",
        "paraphrase",
        "distractor",
        "multi_document",
        "prompt_injection",
        "unsupported",
    }
    if not required_types.issubset(types):
        raise ValueError("Hard development suite is missing a required case type")
    if any(len(case.gold_claims) > 2 for case in cases):
        raise ValueError("Hard development cases may require at most two claims")
    document_text = {document.document_id: document.text for document in documents}
    for case in cases:
        if case.should_abstain:
            if case.gold_claims:
                raise ValueError("Unsupported hard-development cases cannot declare gold claims")
            continue
        if not case.gold_claims:
            raise ValueError("Supported hard-development cases require gold claims")
        for gold in case.gold_claims:
            source = document_text.get(gold.document_id)
            if source is None:
                raise ValueError(
                    f"Hard-development case references unknown document: {gold.document_id}"
                )
            if gold.passage not in source:
                raise ValueError(
                    "Hard-development gold passage is absent from "
                    f"{gold.document_id}: {gold.passage!r}"
                )
    return HardDevelopmentSuite(
        retrieval_corpus=RagEvaluationCorpus(documents=documents, cases=()),
        answer_corpus=AnswerEvaluationCorpus(cases=cases),
    )


def _parse_answer_cases(items: list[dict[str, Any]]) -> tuple[AnswerEvaluationCase, ...]:
    return tuple(
        AnswerEvaluationCase(
            case_id=item["case_id"],
            split=item["split"],
            case_type=item["case_type"],
            question=item["question"],
            should_abstain=bool(item["should_abstain"]),
            gold_claims=tuple(
                GoldClaim(document_id=gold["document_id"], passage=gold["passage"])
                for gold in item["gold_claims"]
            ),
        )
        for item in items
    )


def _validate_answer_cases(
    cases: tuple[AnswerEvaluationCase, ...],
    required_splits: set[str],
) -> None:
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Answer evaluation case IDs must be unique")
    if {case.split for case in cases} != required_splits:
        raise ValueError(f"Answer evaluation requires splits: {sorted(required_splits)}")


def evaluate_grounded_answers(
    retrieval_corpus: RagEvaluationCorpus,
    answer_corpus: AnswerEvaluationCorpus,
    service: EvidenceRetrievalService,
    provider: GroundedAnswerProvider,
    split: str,
    owner_scope_id: str = "answer-evaluation-owner",
    analysis_id: str = "answer-evaluation-analysis",
) -> AnswerEvaluationMetrics:
    metrics, _ = _evaluate_grounded_answers(
        retrieval_corpus,
        answer_corpus,
        service,
        provider,
        split,
        owner_scope_id,
        analysis_id,
        False,
    )
    return metrics


def evaluate_grounded_answers_with_trace(
    retrieval_corpus: RagEvaluationCorpus,
    answer_corpus: AnswerEvaluationCorpus,
    service: EvidenceRetrievalService,
    provider: GroundedAnswerProvider,
    split: str,
    owner_scope_id: str = "answer-evaluation-owner",
    analysis_id: str = "answer-evaluation-analysis",
) -> tuple[AnswerEvaluationMetrics, AnswerEvaluationTrace]:
    metrics, trace = _evaluate_grounded_answers(
        retrieval_corpus, answer_corpus, service, provider, split, owner_scope_id, analysis_id, True
    )
    assert trace is not None
    return metrics, trace


class _TracingProvider:
    def __init__(self, provider: GroundedAnswerProvider) -> None:
        self._provider = provider
        self.name = provider.name
        self.model = provider.model
        self.payload: Optional[object] = None

    def reset(self) -> None:
        self.payload = None

    def generate(self, question: str, evidence: tuple[RetrievedEvidence, ...]) -> object:
        self.payload = self._provider.generate(question, evidence)
        return self.payload


def _evaluate_grounded_answers(
    retrieval_corpus: RagEvaluationCorpus,
    answer_corpus: AnswerEvaluationCorpus,
    service: EvidenceRetrievalService,
    provider: GroundedAnswerProvider,
    split: str,
    owner_scope_id: str,
    analysis_id: str,
    capture_trace: bool,
) -> tuple[AnswerEvaluationMetrics, Optional[AnswerEvaluationTrace]]:
    service.clear()
    for document in retrieval_corpus.documents:
        service.index_document(document.as_rag_document(owner_scope_id, analysis_id))

    cases = answer_corpus.cases_for_split(split)
    supported = tuple(case for case in cases if not case.should_abstain)
    unsupported = tuple(case for case in cases if case.should_abstain)
    verified = 0
    provider_responses = 0
    abstained = 0
    found_gold = 0
    provider_unavailable_count = 0
    verifier_rejection_count = 0
    retrieval_miss_count = 0
    total_gold = sum(len(case.gold_claims) for case in supported)
    latencies = []
    failures: list[dict[str, object]] = []
    traces: list[dict[str, object]] = []
    tracing_provider = _TracingProvider(provider) if capture_trace else None
    active_provider = tracing_provider or provider

    for case in cases:
        retrieval = service.retrieve(owner_scope_id, analysis_id, case.question)
        if tracing_provider:
            tracing_provider.reset()
        result = generate_grounded_answer(case.question, retrieval, active_provider)
        latencies.append(result.latency_ms)
        case_failures: list[str] = []
        if case.should_abstain:
            if result.status == AnswerStatus.INSUFFICIENT_EVIDENCE and not result.claims:
                abstained += 1
            else:
                case_failures.append("failed_abstention")
                failures.append({"case_id": case.case_id, "reason": "failed_abstention"})
        elif not retrieval.evidence:
            retrieval_miss_count += 1
            case_failures.append("retrieval_miss")
            failures.append({"case_id": case.case_id, "reason": "retrieval_miss"})
        elif "answer_provider_unavailable" in result.reason_codes:
            provider_unavailable_count += 1
            case_failures.append("provider_unavailable")
            failures.append({"case_id": case.case_id, "reason": "provider_unavailable"})
        else:
            provider_responses += 1
            if "generated_answer_failed_verification" in result.reason_codes:
                verifier_rejection_count += 1
                case_failures.append("verifier_rejection")
                failures.append({"case_id": case.case_id, "reason": "verifier_rejection"})
            elif result.status == AnswerStatus.GROUNDED_ANSWER:
                verified += 1

        case_found = 0
        matched_gold: list[dict[str, str]] = []
        missing_gold: list[dict[str, str]] = []
        for gold in case.gold_claims:
            if any(
                claim.chunk_id == evidence.chunk_id
                and evidence.document_id == gold.document_id
                and gold.passage.lower() in claim.supporting_quote.lower()
                for claim in result.claims
                for evidence in retrieval.evidence
            ):
                case_found += 1
                found_gold += 1
                matched_gold.append(asdict(gold))
            else:
                missing_gold.append(asdict(gold))
        if case_found != len(case.gold_claims):
            case_failures.append("missing_gold_claim")
            failures.append({"case_id": case.case_id, "reason": "missing_gold_claim"})
        if capture_trace:
            traces.append(
                {
                    "case_id": case.case_id,
                    "case_type": case.case_type,
                    "question": case.question,
                    "retrieval": {
                        "status": retrieval.status,
                        "selected_method": retrieval.selected_method,
                        "evidence": [
                            {
                                "document_id": item.document_id,
                                "chunk_id": item.chunk_id,
                                "rank": item.rank,
                            }
                            for item in retrieval.evidence
                        ],
                    },
                    "answer": {
                        "status": result.status,
                        "reason_codes": list(result.reason_codes),
                        "generated_payload": _safe_payload(
                            tracing_provider.payload if tracing_provider else None
                        ),
                    },
                    "matched_gold_claims": matched_gold,
                    "missing_gold_claims": missing_gold,
                    "failure_reasons": case_failures,
                }
            )

    leakage = 0
    for case in cases:
        leakage += len(
            service.retrieve("answer-evaluation-stranger", analysis_id, case.question).evidence
        )
        leakage += len(service.retrieve(owner_scope_id, "another-analysis", case.question).evidence)
    metrics = AnswerEvaluationMetrics(
        split=split,
        case_count=len(cases),
        supported_case_count=len(supported),
        unsupported_case_count=len(unsupported),
        verifier_pass_rate=_ratio_or_none(verified, provider_responses),
        unsupported_abstention_accuracy=_ratio(abstained, len(unsupported)),
        gold_claim_coverage=_ratio(found_gold, total_gold),
        cross_scope_leakage_count=leakage,
        p95_latency_ms=round(_percentile(latencies, 0.95), 3),
        provider_unavailable_count=provider_unavailable_count,
        provider_response_count=provider_responses,
        verifier_rejection_count=verifier_rejection_count,
        retrieval_miss_count=retrieval_miss_count,
        failures=tuple(failures),
    )
    trace = AnswerEvaluationTrace(split=split, cases=tuple(traces)) if capture_trace else None
    return metrics, trace


def answer_release_gates(metrics: AnswerEvaluationMetrics) -> dict[str, bool]:
    return {
        "verifier_pass_rate": metrics.verifier_pass_rate == 1.0,
        "provider_availability": metrics.provider_unavailable_count == 0,
        "unsupported_abstention": metrics.unsupported_abstention_accuracy == 1.0,
        "gold_claim_coverage": metrics.gold_claim_coverage >= 0.90,
        "scope_isolation": metrics.cross_scope_leakage_count == 0,
        "warm_p95_latency": metrics.p95_latency_ms <= 5000.0,
    }


def _safe_payload(payload: object) -> object:
    if payload is None:
        return None
    try:
        json.dumps(payload)
    except (TypeError, ValueError):
        return {"unserializable_payload_type": type(payload).__name__}
    return payload


def _ratio(numerator: float, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def _ratio_or_none(numerator: float, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 4) if denominator else None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int((len(ordered) - 1) * percentile), len(ordered) - 1)
    return ordered[index]
