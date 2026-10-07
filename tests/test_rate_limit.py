from __future__ import annotations

from api.rate_limit import RateLimiter


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_allows_a_rolling_window_and_reports_retry_after() -> None:
    clock = _Clock()
    limiter = RateLimiter(limit=2, window_seconds=60, clock=clock)

    assert limiter.consume("opaque-guest").allowed is True
    assert limiter.consume("opaque-guest").allowed is True
    blocked = limiter.consume("opaque-guest")

    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 60
    clock.now = 60
    assert limiter.consume("opaque-guest").allowed is True


def test_rate_limiter_periodically_removes_expired_owner_scopes() -> None:
    clock = _Clock()
    limiter = RateLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.consume("expired-guest")
    limiter.consume("active-guest")

    clock.now = 61
    limiter.consume("active-guest")

    assert limiter.cleanup_expired() == 1
    assert limiter.consume("expired-guest").allowed is True
