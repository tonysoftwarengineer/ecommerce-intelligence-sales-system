from __future__ import annotations

from api.rag_answer_observability import RagAnswerObservability
from api.rag_answer_rate_limit import RagAnswerRateLimiter
from src.rag.answers import AnswerStatus, AnswerTokenUsage, GroundedAnswerResult
from src.rag.contracts import RetrievalResult, RetrievalStatus


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _result(usage: AnswerTokenUsage | None = None) -> GroundedAnswerResult:
    retrieval = RetrievalResult(
        status=RetrievalStatus.EVIDENCE_AVAILABLE,
        selected_method="chroma_minilm",
        searched_document_count=1,
        searched_chunk_count=2,
        latency_ms=3.0,
        reason_codes=(),
        evidence=(),
    )
    return GroundedAnswerResult(
        status=AnswerStatus.GROUNDED_ANSWER,
        provider="groq_rest",
        model="openai/gpt-oss-20b",
        latency_ms=12.0,
        reason_codes=(),
        claims=(),
        retrieval=retrieval,
        usage=usage,
    )


def test_rate_limiter_allows_a_rolling_window_and_reports_retry_after() -> None:
    clock = _Clock()
    limiter = RagAnswerRateLimiter(limit=2, window_seconds=60, clock=clock)

    assert limiter.consume("opaque-guest").allowed is True
    assert limiter.consume("opaque-guest").allowed is True
    blocked = limiter.consume("opaque-guest")

    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 60
    clock.now = 60
    assert limiter.consume("opaque-guest").allowed is True


def test_rate_limiter_periodically_removes_expired_owner_scopes() -> None:
    clock = _Clock()
    limiter = RagAnswerRateLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.consume("expired-guest")
    limiter.consume("active-guest")

    clock.now = 61
    limiter.consume("active-guest")

    assert limiter.cleanup_expired() == 1
    assert limiter.consume("expired-guest").allowed is True


def test_observability_aggregates_usage_without_retaining_content() -> None:
    observability = RagAnswerObservability()
    observability.record_result(
        _result(AnswerTokenUsage(input_tokens=21, output_tokens=9, total_tokens=30)),
        provider_attempted=True,
    )
    observability.record_result(_result(), provider_attempted=True)
    observability.record_rate_limited("groq_rest", "openai/gpt-oss-20b")

    snapshot = observability.snapshot()

    assert snapshot["answer_requests"] == 3
    assert snapshot["provider_backed_attempts"] == 2
    assert snapshot["rate_limited_requests"] == 1
    assert snapshot["usage_unavailable_count"] == 1
    assert snapshot["total_tokens"]["maximum"] == 30
    assert snapshot["reason_code_counts"] == {"answer_rate_limited": 1}
    rendered = str(snapshot)
    assert "customer refund question" not in rendered.lower()
    assert "private-policy.md" not in rendered.lower()
    assert "opaque-guest" not in rendered


def test_answer_cache_evicts_least_recently_used_and_expires_entries() -> None:
    from api.rag_answer_cache import RagAnswerCache

    clock = _Clock()
    cache = RagAnswerCache(max_entries=2, ttl_seconds=60, clock=clock)
    cache.put("a", {"claims": []})
    cache.put("b", {"claims": []})
    assert cache.get("a") is not None
    cache.put("c", {"claims": []})

    assert cache.get("b") is None
    assert cache.get("a") is not None
    assert cache.get("c") is not None

    clock.now = 60.0
    assert cache.get("a") is None
    assert len(cache) == 1


def test_daily_budget_is_app_wide_and_resets_at_utc_midnight() -> None:
    from datetime import datetime, timedelta, timezone

    from api.rag_answer_rate_limit import RagAnswerDailyBudget

    now = [datetime(2026, 10, 3, 23, 59, tzinfo=timezone.utc)]
    budget = RagAnswerDailyBudget(limit=2, clock=lambda: now[0])

    assert budget.consume() is True
    assert budget.consume() is True
    assert budget.consume() is False
    assert budget.remaining() == 0

    now[0] += timedelta(minutes=2)
    assert budget.remaining() == 2
    assert budget.consume() is True


def test_cache_key_ignores_per_upload_chunk_ids_but_not_content() -> None:
    import dataclasses

    from api.rag_answer_cache import answer_cache_key, from_portable, to_portable
    from src.rag.contracts import RetrievedEvidence

    fields = {f.name for f in dataclasses.fields(RetrievedEvidence)}
    base = {name: None for name in fields}
    base.update(chunk_id="upload-1-chunk", citation="shipping.md v1 · chunk 1", excerpt="Two days.")
    first = (RetrievedEvidence(**base),)
    same_text = (dataclasses.replace(first[0], chunk_id="upload-2-chunk"),)
    other_text = (dataclasses.replace(first[0], excerpt="Three days."),)

    key = answer_cache_key("p", "m", 1024, "How long?", first)
    assert answer_cache_key("p", "m", 1024, "How long?", same_text) == key
    assert answer_cache_key("p", "m", 1024, "How long?", other_text) != key
    assert answer_cache_key("p", "m", 1024, "How fast?", first) != key

    payload = {"claims": [{"claim": "x", "chunk_id": "upload-1-chunk", "supporting_quote": "q"}]}
    portable = to_portable(payload, first)
    assert portable["claims"][0]["chunk_id"] == "evidence-1"
    assert payload["claims"][0]["chunk_id"] == "upload-1-chunk"
    replayed = from_portable(portable, same_text)
    assert replayed["claims"][0]["chunk_id"] == "upload-2-chunk"
