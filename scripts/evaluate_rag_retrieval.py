"""Run the retrieval benchmark without generating any business answer."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.rag.chunking import ChunkingConfig
from src.rag.evaluation import load_evaluation_corpus
from src.rag.index import ChromaRetrievalIndex, TfidfRetrievalIndex
from src.rag.metrics import RetrievalMetrics, evaluate_retrieval, release_gates
from src.rag.retrieval import EvidenceRetrievalService

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "tests" / "fixtures" / "rag_evaluation" / "corpus.json"
DEFAULT_REPORT_DIR = ROOT / "docs" / "evaluation" / "rag_phase_1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("tfidf", "chroma"), required=True)
    parser.add_argument("--split", choices=("development", "locked_test"), required=True)
    parser.add_argument("--select-development", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    return parser.parse_args()


def make_service(
    backend: str,
    chunk_size: int,
    threshold: float,
    rerank: bool,
) -> EvidenceRetrievalService:
    index = (
        ChromaRetrievalIndex("all-MiniLM-L6-v2")
        if backend == "chroma"
        else TfidfRetrievalIndex()
    )
    return EvidenceRetrievalService(
        index=index,
        chunking=ChunkingConfig(max_tokens=chunk_size, overlap_tokens=32),
        relevance_threshold=threshold,
        candidate_limit=20,
        evidence_limit=3,
        lexical_reranking=rerank,
    )


def select_development(backend: str):
    corpus = load_evaluation_corpus(CORPUS_PATH)
    thresholds = (
        (0.20, 0.30, 0.40, 0.50, 0.60, 0.70)
        if backend == "chroma"
        else (0.05, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30)
    )
    candidates = []
    for chunk_size in (128, 192, 224):
        for threshold in thresholds:
            baseline = evaluate_retrieval(
                corpus,
                make_service(backend, chunk_size, threshold, False),
                "development",
            )
            candidates.append((chunk_size, threshold, False, baseline))
            reranked = evaluate_retrieval(
                corpus,
                make_service(backend, chunk_size, threshold, True),
                "development",
            )
            if (
                reranked.top1_source_accuracy > baseline.top1_source_accuracy
                or reranked.chunk_precision > baseline.chunk_precision
            ) and reranked.top3_source_recall >= baseline.top3_source_recall:
                candidates.append((chunk_size, threshold, True, reranked))
    return max(candidates, key=lambda item: _selection_key(item[3]))


def _selection_key(metrics: RetrievalMetrics) -> tuple:
    return (
        metrics.top3_source_recall,
        metrics.top1_source_accuracy,
        metrics.abstention_accuracy,
        metrics.chunk_precision,
        metrics.chunk_f1,
        -metrics.p95_latency_ms,
    )


def write_report(
    output_dir: Path,
    backend: str,
    split: str,
    configuration: dict,
    metrics: RetrievalMetrics,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "backend": backend,
        "split": split,
        "configuration": configuration,
        "metrics": metrics.as_dict(),
        "release_gates": release_gates(metrics),
        "overall_release_gate_passed": all(release_gates(metrics).values()),
    }
    stem = f"{backend}_{split}"
    (output_dir / f"{stem}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    rows = [
        "# RAG Phase 1 Retrieval Evaluation",
        "",
        f"- Backend: `{backend}`",
        f"- Split: `{split}`",
        f"- Configuration: `{json.dumps(configuration, sort_keys=True)}`",
        f"- Top-1 source accuracy: `{metrics.top1_source_accuracy:.1%}`",
        f"- Top-3 source recall: `{metrics.top3_source_recall:.1%}`",
        f"- Chunk precision: `{metrics.chunk_precision:.1%}`",
        f"- Chunk recall: `{metrics.chunk_recall:.1%}`",
        f"- Chunk F1: `{metrics.chunk_f1:.1%}`",
        f"- Mean reciprocal rank: `{metrics.mean_reciprocal_rank:.3f}`",
        f"- Abstention accuracy: `{metrics.abstention_accuracy:.1%}`",
        f"- Cross-session evidence leakage: `{metrics.cross_session_leakage_count}`",
        f"- Latency p50 / p95: `{metrics.p50_latency_ms:.3f} / {metrics.p95_latency_ms:.3f} ms`",
        f"- Release gate: `{'PASS' if all(release_gates(metrics).values()) else 'FAIL'}`",
        "",
        "## Failures",
        "",
    ]
    rows.extend(
        f"- `{failure.case_id}` — {failure.reason}; returned {list(failure.returned_document_ids)}"
        for failure in metrics.failures
    )
    if not metrics.failures:
        rows.append("- None")
    (output_dir / f"{stem}.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    corpus = load_evaluation_corpus(CORPUS_PATH)
    if args.select_development:
        if args.split != "development":
            raise SystemExit("--select-development can only run on the development split")
        chunk_size, threshold, rerank, metrics = select_development(args.backend)
        configuration = {
            "chunk_max_tokens": chunk_size,
            "chunk_overlap_tokens": 32,
            "relevance_threshold": threshold,
            "candidate_limit": 20,
            "evidence_limit": 3,
            "lexical_reranking": rerank,
        }
        frozen_path = args.output_dir / f"{args.backend}_frozen_config.json"
        frozen_path.parent.mkdir(parents=True, exist_ok=True)
        frozen_path.write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
    else:
        if args.config is None:
            raise SystemExit("--config is required unless --select-development is used")
        configuration = json.loads(args.config.read_text(encoding="utf-8"))
        service = make_service(
            args.backend,
            int(configuration["chunk_max_tokens"]),
            float(configuration["relevance_threshold"]),
            bool(configuration["lexical_reranking"]),
        )
        metrics = evaluate_retrieval(corpus, service, args.split)
    write_report(args.output_dir, args.backend, args.split, configuration, metrics)
    print(json.dumps({"configuration": configuration, "metrics": asdict(metrics)}, indent=2))


if __name__ == "__main__":
    main()
