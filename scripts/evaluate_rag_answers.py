import argparse
import json
from collections import Counter
from pathlib import Path

from api.rag_answer_service import answer_provider
from api.rag_service import build_retrieval_service
from src.rag.answer_evaluation import (
    answer_release_gates,
    evaluate_grounded_answers_with_trace,
    load_answer_evaluation_corpus,
    load_hard_development_suite,
)
from src.rag.evaluation import load_evaluation_corpus

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate verified RAG Phase 2 answers")
    parser.add_argument("--suite", choices=("baseline", "hard-development"), default="baseline")
    parser.add_argument("--split", choices=("development", "locked_test"), default="development")
    parser.add_argument("--confirm-locked-run", action="store_true")
    parser.add_argument(
        "--json-output",
        type=Path,
        default=ROOT / "data" / "private" / "rag_phase2_evaluation.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=ROOT / "docs" / "evaluation" / "rag_phase2_evaluation.md",
    )
    parser.add_argument(
        "--trace-output",
        type=Path,
        help="Ignored local diagnostic trace. Defaults to data/private for development runs.",
    )
    args = parser.parse_args()
    if args.split == "locked_test" and not args.confirm_locked_run:
        parser.error(
            "The locked split requires --confirm-locked-run and must not be used for tuning"
        )
    if args.suite == "hard-development" and args.split != "development":
        parser.error("The hard-development suite supports the development split only")

    if args.suite == "hard-development":
        suite = load_hard_development_suite(
            ROOT / "tests" / "fixtures" / "rag_answer_hard_development"
        )
        retrieval_corpus = suite.retrieval_corpus
        answer_corpus = suite.answer_corpus
    else:
        retrieval_corpus = load_evaluation_corpus(
            ROOT / "tests" / "fixtures" / "rag_evaluation" / "corpus.json"
        )
        answer_corpus = load_answer_evaluation_corpus(
            ROOT / "tests" / "fixtures" / "rag_answer_evaluation" / "cases.json"
        )
    metrics, trace = evaluate_grounded_answers_with_trace(
        retrieval_corpus,
        answer_corpus,
        build_retrieval_service(),
        answer_provider,
        args.split,
    )
    gates = answer_release_gates(metrics)
    payload = {
        "suite": args.suite,
        "provider": answer_provider.name,
        "model": answer_provider.model,
        "metrics": metrics.as_dict(),
        "release_gates": gates,
        "all_release_gates_passed": all(gates.values()),
        "provider_reason_counts": _provider_reason_counts(trace.as_dict()),
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.markdown_output.write_text(_markdown(payload), encoding="utf-8")
    trace_output = args.trace_output
    if trace_output is None and args.split == "development":
        trace_output = ROOT / "data" / "private" / f"rag_phase2_{args.suite}_trace.json"
    if trace_output is not None:
        trace_output.parent.mkdir(parents=True, exist_ok=True)
        trace_output.write_text(json.dumps(trace.as_dict(), indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


def _markdown(payload: dict) -> str:
    metrics = payload["metrics"]
    gates = payload["release_gates"]
    rows = "\n".join(
        f"| {name.replace('_', ' ')} | {'pass' if passed else 'fail'} |"
        for name, passed in gates.items()
    )
    verifier_pass_rate = metrics["verifier_pass_rate"]
    verifier_display = (
        "not assessed (no provider response)"
        if verifier_pass_rate is None
        else f"{verifier_pass_rate:.1%}"
    )
    provider_reasons = payload["provider_reason_counts"]
    provider_reason_display = (
        ", ".join(f"`{reason}`: {count}" for reason, count in provider_reasons.items())
        if provider_reasons
        else "none"
    )
    return f"""# RAG Phase 2 Answer Evaluation

- Provider: `{payload["provider"]}`
- Model: `{payload["model"]}`
- Suite: `{payload["suite"]}`
- Split: `{metrics["split"]}`
- Cases: {metrics["case_count"]}
- Verifier pass rate: {verifier_display}
- Unsupported abstention accuracy: {metrics["unsupported_abstention_accuracy"]:.1%}
- Gold-claim coverage: {metrics["gold_claim_coverage"]:.1%}
- Cross-scope leakage count: {metrics["cross_scope_leakage_count"]}
- p95 latency: {metrics["p95_latency_ms"]:.1f} ms
- Provider-unavailable cases: {metrics["provider_unavailable_count"]}
- Provider responses: {metrics["provider_response_count"]}
- Provider failure reasons: {provider_reason_display}
- Verifier-rejected cases: {metrics["verifier_rejection_count"]}
- Retrieval-miss cases: {metrics["retrieval_miss_count"]}

| Release gate | Result |
|---|---|
{rows}

Provider-unavailable cases make a real-provider run inconclusive; they are not
treated as verifier quality failures. The grounded-answer feature remains
experimental unless every gate passes and every locked-test failure receives
manual review. A deterministic fake-provider result validates wiring and
verification only; it is not a Gemini quality claim.
"""


def _provider_reason_counts(trace: dict) -> dict[str, int]:
    counts = Counter(
        code
        for case in trace["cases"]
        for code in case["answer"]["reason_codes"]
        if code.startswith("gemini_")
    )
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    main()
