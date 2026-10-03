"""Process-local, privacy-safe operational metrics for grounded answers."""

from __future__ import annotations

from collections import Counter
from threading import RLock
from typing import Any

from api.analysis_observability import _latency_summary
from src.rag.answers import GroundedAnswerResult


class RagAnswerObservability:
    """Record aggregate provider behavior without retaining user or document content."""

    def __init__(self, max_samples: int = 1_000) -> None:
        if max_samples < 1:
            raise ValueError("max_samples must be at least one")
        self._max_samples = max_samples
        self._lock = RLock()
        self.clear()

    def record_result(
        self,
        result: GroundedAnswerResult,
        provider_attempted: bool,
        cache_hit: bool = False,
    ) -> None:
        with self._lock:
            self._answer_requests += 1
            if cache_hit:
                self._cache_hits += 1
            self._status_counts[result.status.value] += 1
            self._provider_model_counts[_provider_model_key(result.provider, result.model)] += 1
            self._reason_code_counts.update(result.reason_codes)
            self._append(self._latencies, result.latency_ms)
            if not provider_attempted:
                return
            self._provider_backed_attempts += 1
            if result.usage is None:
                self._usage_unavailable_count += 1
                return
            self._append(self._input_tokens, result.usage.input_tokens)
            self._append(self._output_tokens, result.usage.output_tokens)
            self._append(self._total_tokens, result.usage.total_tokens)

    def record_feedback(self, helpful: bool) -> None:
        with self._lock:
            if helpful:
                self._feedback_helpful += 1
            else:
                self._feedback_not_helpful += 1

    def record_rate_limited(self, provider: str, model: str) -> None:
        with self._lock:
            self._answer_requests += 1
            self._rate_limited_requests += 1
            self._status_counts["rate_limited"] += 1
            self._provider_model_counts[_provider_model_key(provider, model)] += 1
            self._reason_code_counts["answer_rate_limited"] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "scope": (
                    "Process-local development metrics. They reset when the API restarts and "
                    "retain no questions, document text, document IDs, guest IDs, or credentials."
                ),
                "answer_requests": self._answer_requests,
                "provider_backed_attempts": self._provider_backed_attempts,
                "rate_limited_requests": self._rate_limited_requests,
                "cache_hits": self._cache_hits,
                "feedback_helpful": self._feedback_helpful,
                "feedback_not_helpful": self._feedback_not_helpful,
                "usage_unavailable_count": self._usage_unavailable_count,
                "latency_ms": _latency_summary(self._latencies),
                "input_tokens": _latency_summary(self._input_tokens),
                "output_tokens": _latency_summary(self._output_tokens),
                "total_tokens": _latency_summary(self._total_tokens),
                "status_counts": dict(sorted(self._status_counts.items())),
                "reason_code_counts": dict(sorted(self._reason_code_counts.items())),
                "provider_model_counts": dict(sorted(self._provider_model_counts.items())),
            }

    def clear(self) -> None:
        with self._lock:
            self._answer_requests = 0
            self._provider_backed_attempts = 0
            self._rate_limited_requests = 0
            self._cache_hits = 0
            self._feedback_helpful = 0
            self._feedback_not_helpful = 0
            self._usage_unavailable_count = 0
            self._latencies: list[float] = []
            self._input_tokens: list[float] = []
            self._output_tokens: list[float] = []
            self._total_tokens: list[float] = []
            self._status_counts: Counter[str] = Counter()
            self._reason_code_counts: Counter[str] = Counter()
            self._provider_model_counts: Counter[str] = Counter()

    def _append(self, samples: list[float], value: float) -> None:
        samples.append(max(0.0, value))
        if len(samples) > self._max_samples:
            samples.pop(0)


def _provider_model_key(provider: str, model: str) -> str:
    return f"{provider}:{model}"
