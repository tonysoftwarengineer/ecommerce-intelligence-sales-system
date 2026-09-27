"""Small process-local provider budget for experimental grounded answers."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from math import ceil
from threading import RLock
from typing import Callable


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RagAnswerRateLimiter:
    """Limit provider-backed requests per opaque guest scope, without storing content."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least one")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock or time.monotonic
        self._attempts: dict[str, deque[float]] = {}
        self._lock = RLock()

    def consume(self, owner_scope_id: str) -> RateLimitDecision:
        now = self._clock()
        with self._lock:
            attempts = self._attempts.setdefault(owner_scope_id, deque())
            self._purge(attempts, now)
            if len(attempts) >= self._limit:
                retry_after = max(1, ceil(self._window_seconds - (now - attempts[0])))
                return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
            attempts.append(now)
            return RateLimitDecision(allowed=True)

    def drop_owner(self, owner_scope_id: str) -> None:
        with self._lock:
            self._attempts.pop(owner_scope_id, None)

    def cleanup_expired(self) -> int:
        """Drop inactive scopes once their rolling window has elapsed."""
        now = self._clock()
        with self._lock:
            expired_owners = []
            for owner_scope_id, attempts in self._attempts.items():
                self._purge(attempts, now)
                if not attempts:
                    expired_owners.append(owner_scope_id)
            for owner_scope_id in expired_owners:
                del self._attempts[owner_scope_id]
            return len(expired_owners)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()

    def _purge(self, attempts: deque[float], now: float) -> None:
        while attempts and now - attempts[0] >= self._window_seconds:
            attempts.popleft()
