from collections.abc import Iterable
from dataclasses import asdict, dataclass
from statistics import median

from src.rag.contracts import RetrievalStatus
from src.rag.evaluation import EvaluationCase, RagEvaluationCorpus
from src.rag.retrieval import EvidenceRetrievalService


@dataclass(frozen=True)
class RetrievalFailure:
    case_id: str
    reason: str
    returned_document_ids: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalMetrics:
    split: str
    case_count: int
    supported_case_count: int
    unsupported_case_count: int
    top1_source_accuracy: float
    top3_source_recall: float
    chunk_precision: float
    chunk_recall: float
    chunk_f1: float
    mean_reciprocal_rank: float
    abstention_accuracy: float
    cross_session_leakage_count: int
    p50_latency_ms: float
    p95_latency_ms: float
    failures: tuple[RetrievalFailure, ...]

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_retrieval(
    corpus: RagEvaluationCorpus,
    service: EvidenceRetrievalService,
    split: str,
    owner_scope_id: str = "evaluation-scope",
    analysis_id: str = "evaluation-analysis",
) -> RetrievalMetrics:
    service.clear()
    for document in corpus.documents:
        service.index_document(document.as_rag_document(owner_scope_id, analysis_id))

    cases = corpus.cases_for_split(split)
    supported = [case for case in cases if not case.should_abstain]
    unsupported = [case for case in cases if case.should_abstain]
    top1_hits = 0
    relevant_retrieved = 0
    relevant_total = 0
    reciprocal_ranks = []
    true_positive_chunks = 0
    returned_chunks = 0
    required_passages_found = 0
    required_passages_total = 0
    abstentions = 0
    latencies = []
    failures = []

    for case in cases:
        result = service.retrieve(owner_scope_id, analysis_id, case.question)
        latencies.append(result.latency_ms)
        returned_ids = tuple(item.document_id for item in result.evidence)
        if case.should_abstain:
            if result.status == RetrievalStatus.INSUFFICIENT_EVIDENCE and not result.evidence:
                abstentions += 1
            else:
                failures.append(RetrievalFailure(case.case_id, "failed_abstention", returned_ids))
            continue

        relevant = set(case.relevant_document_ids)
        relevant_total += len(relevant)
        relevant_retrieved += len(relevant & set(returned_ids[:3]))
        if returned_ids and returned_ids[0] in relevant:
            top1_hits += 1
        rank = next(
            (
                position
                for position, value in enumerate(returned_ids, 1)
                if value in relevant
            ),
            0,
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)

        returned_chunks += len(result.evidence)
        for item in result.evidence:
            if _is_relevant_chunk(case, item.document_id, item.excerpt):
                true_positive_chunks += 1
        required_passages_total += len(case.required_evidence)
        for required in case.required_evidence:
            if any(
                item.document_id == required.document_id
                and required.passage.lower() in item.excerpt.lower()
                for item in result.evidence
            ):
                required_passages_found += 1

        missing_documents = relevant - set(returned_ids[:3])
        if missing_documents:
            failures.append(RetrievalFailure(case.case_id, "missed_relevant_source", returned_ids))
        elif not all(
            any(
                item.document_id == required.document_id
                and required.passage.lower() in item.excerpt.lower()
                for item in result.evidence
            )
            for required in case.required_evidence
        ):
            failures.append(RetrievalFailure(case.case_id, "missed_required_passage", returned_ids))

    cross_session_leakage_count = sum(
        len(service.retrieve("evaluation-stranger", analysis_id, case.question).evidence)
        for case in cases
    )
    precision = _ratio(true_positive_chunks, returned_chunks)
    recall = _ratio(required_passages_found, required_passages_total)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return RetrievalMetrics(
        split=split,
        case_count=len(cases),
        supported_case_count=len(supported),
        unsupported_case_count=len(unsupported),
        top1_source_accuracy=_ratio(top1_hits, len(supported)),
        top3_source_recall=_ratio(relevant_retrieved, relevant_total),
        chunk_precision=precision,
        chunk_recall=recall,
        chunk_f1=round(f1, 4),
        mean_reciprocal_rank=_ratio(sum(reciprocal_ranks), len(reciprocal_ranks)),
        abstention_accuracy=_ratio(abstentions, len(unsupported)),
        cross_session_leakage_count=cross_session_leakage_count,
        p50_latency_ms=round(median(latencies), 3) if latencies else 0.0,
        p95_latency_ms=round(_percentile(latencies, 0.95), 3) if latencies else 0.0,
        failures=tuple(failures),
    )


def release_gates(metrics: RetrievalMetrics) -> dict[str, bool]:
    return {
        "top1_source_accuracy": metrics.top1_source_accuracy >= 0.80,
        "top3_source_recall": metrics.top3_source_recall >= 0.90,
        "abstention_accuracy": metrics.abstention_accuracy >= 0.90,
        "cross_session_isolation": metrics.cross_session_leakage_count == 0,
        "warm_p95_latency": metrics.p95_latency_ms <= 500.0,
    }


def _is_relevant_chunk(case: EvaluationCase, document_id: str, excerpt: str) -> bool:
    return any(
        required.document_id == document_id
        and required.passage.lower() in excerpt.lower()
        for required in case.required_evidence
    )


def _ratio(numerator: float, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def _percentile(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * quantile))))
    return ordered[index]
