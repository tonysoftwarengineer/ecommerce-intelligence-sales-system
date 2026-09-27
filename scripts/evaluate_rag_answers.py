import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

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
    parser.add_argument(
        "--minimum-provider-interval-seconds",
        type=float,
        default=0.0,
        help="Minimum delay between provider calls; use for real-provider development runs.",
    )
    args = parser.parse_args()
    if args.split == "locked_test" and not args.confirm_locked_run:
        parser.error(
            "The locked split requires --confirm-locked-run and must not be used for tuning"
        )
    if args.suite == "hard-development" and args.split != "development":
        parser.error("The hard-development suite supports the development split only")
    if args.minimum_provider_interval_seconds < 0:
        parser.error("--minimum-provider-interval-seconds cannot be negative")
    trace_output = args.trace_output
    if trace_output is None and args.split == "development":
        trace_output = ROOT / "data" / "private" / f"rag_phase2_{args.suite}_trace.json"
    if trace_output is not None and ROOT / "data" / "private" not in trace_output.resolve().parents:
        parser.error("--trace-output must be under ignored data/private/")

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
    provider = answer_provider
    pacer = _ProviderPacer(args.minimum_provider_interval_seconds)
    metrics, trace = evaluate_grounded_answers_with_trace(
        retrieval_corpus,
        answer_corpus,
        build_retrieval_service(),
        provider,
        args.split,
        before_provider_call=pacer.wait,
    )
    gates = answer_release_gates(metrics)
    conclusion = _evaluation_conclusion(metrics, gates)
    payload = {
        "suite": args.suite,
        "provider": provider.name,
        "model": provider.model,
        "metrics": metrics.as_dict(),
        "release_gates": gates,
        "all_release_gates_passed": all(gates.values()),
        "evaluation_conclusion": conclusion,
        "provider_reason_counts": _provider_reason_counts(trace.as_dict()),
        "latency_measurement": (
            "retrieval + generation + verification; pacing excluded; warm-up not established"
        ),
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.markdown_output.write_text(_markdown(payload), encoding="utf-8")
    if trace_output is not None:
        trace_output.parent.mkdir(parents=True, exist_ok=True)
        trace_output.write_text(json.dumps(trace.as_dict(), indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


def _markdown(payload: dict) -> str:
    metrics = payload["metrics"]
    gates = payload["release_gates"]
    conclusion = payload["evaluation_conclusion"]
    gate_labels = {"warm_p95_latency": "processing p95 latency (legacy key: warm_p95_latency)"}
    rows = "\n".join(
        f"| {gate_labels.get(name, name.replace('_', ' '))} | "
        f"{_gate_result(name, passed, conclusion)} |"
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
    conclusion_text = {
        "passed": "passed",
        "failed": "failed",
        "inconclusive": "inconclusive — provider availability prevented complete scoring",
    }[conclusion]
    available_coverage = metrics["provider_available_gold_claim_coverage"]
    available_display = (
        "not assessed" if available_coverage is None else f"{available_coverage:.1%}"
    )
    full_count = f"{metrics['matched_gold_claim_count']}/{metrics['gold_claim_count']}"
    full_coverage = f"{metrics['gold_claim_coverage']:.1%}"
    available_count = (
        f"{metrics['provider_available_matched_gold_claim_count']}/"
        f"{metrics['provider_available_gold_claim_count']}"
    )
    return f"""# RAG Phase 2 Answer Evaluation

- Provider: `{payload["provider"]}`
- Model: `{payload["model"]}`
- Suite: `{payload["suite"]}`
- Split: `{metrics["split"]}`
- Cases: {metrics["case_count"]}
- Verifier pass rate: {verifier_display}
- Unsupported abstention accuracy: {metrics["unsupported_abstention_accuracy"]:.1%}
- Gold-claim coverage (reference-passage matching): {full_coverage} ({full_count})
- Supplemental provider-available coverage: {available_display} ({available_count})
- Cross-scope leakage count: {metrics["cross_scope_leakage_count"]}
- Processing p95 latency: {metrics["p95_latency_ms"]:.1f} ms
- Latency scope: retrieval + generation + verification; pacing excluded; warm-up not established
- Total intentional pacing delay: {metrics["pacing_delay_ms"]:.1f} ms
- Provider-unavailable cases: {metrics["provider_unavailable_count"]}
- Provider responses: {metrics["provider_response_count"]}
- Provider failure reasons: {provider_reason_display}
- Verifier-rejected cases: {metrics["verifier_rejection_count"]}
- Empty-retrieval cases (legacy retrieval_miss_count): {metrics["retrieval_miss_count"]}
- Cases missing reference evidence: {metrics["missing_reference_evidence_count"]}
- Answer/reference mismatches with evidence present: {metrics["answer_reference_mismatch_count"]}
- Evaluation conclusion: **{conclusion_text}**

| Release gate | Result |
|---|---|
{rows}

Provider-unavailable cases make a real-provider run inconclusive; they are not
treated as verifier or answer-quality failures. Gold-claim coverage is also
incomplete when a provider fails before producing an answer. A fresh run must
repeat the whole suite after the provider limit resets; it must not combine only
the later retries with this run. The grounded-answer feature remains
experimental unless every gate passes and every locked-test failure receives
manual review. A deterministic fake-provider result validates wiring and
verification only; it is not a real-provider quality claim.

Coverage checks reference passages inside cited support quotes, not semantic
answer completeness. Supplemental coverage includes supported cases with a
returned payload (including verifier rejections); provider-unavailable and
empty-retrieval cases are excluded. It never replaces full-suite coverage or
release gates. Diagnostic categories can overlap. The legacy warm_p95_latency
gate keeps its five-second threshold, but this run does not establish warm-up.
"""


def _evaluation_conclusion(metrics, gates: dict[str, bool]) -> str:
    """Classify a run without mislabelling upstream availability as quality failure."""
    if metrics.provider_unavailable_count:
        return "inconclusive"
    return "passed" if all(gates.values()) else "failed"


def _gate_result(name: str, passed: bool, conclusion: str) -> str:
    if conclusion == "inconclusive":
        if name == "provider_availability":
            return "inconclusive (upstream provider failures)"
        if name == "gold_claim_coverage":
            return "inconclusive (incomplete provider responses)"
    return "pass" if passed else "fail"


def _provider_reason_counts(trace: dict) -> dict[str, int]:
    provider_reason_prefixes = ("gemini_", "groq_")
    counts = Counter(
        code
        for case in trace["cases"]
        for code in case["answer"]["reason_codes"]
        if code.startswith(provider_reason_prefixes)
    )
    return dict(sorted(counts.items()))


class _ProviderPacer:
    """Wait before timed answer generation, never inside the provider wrapper."""

    def __init__(
        self,
        minimum_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._minimum_interval_seconds = minimum_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._last_call_started: Optional[float] = None

    def wait(self) -> float:
        started = self._clock()
        if self._last_call_started is not None:
            remaining = self._minimum_interval_seconds - (self._clock() - self._last_call_started)
            if remaining > 0:
                self._sleeper(remaining)
        self._last_call_started = self._clock()
        return max(0.0, self._last_call_started - started)


if __name__ == "__main__":
    main()
