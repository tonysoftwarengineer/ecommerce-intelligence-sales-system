import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Optional


@dataclass(frozen=True)
class GuestSession:
    session_id: str
    created_at: datetime
    expires_at: datetime


class GuestSessionStore:
    """Process-local anonymous identities for the frictionless portfolio demo."""

    def __init__(
        self,
        ttl: timedelta,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("Guest-session TTL must be positive")
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sessions: dict[str, GuestSession] = {}
        self._lock = RLock()

    def resolve(self, session_id: Optional[str]) -> tuple[GuestSession, bool]:
        """Return a live session and whether a new cookie must be issued."""
        now = self._clock()
        with self._lock:
            self._remove_expired(now)
            if session_id:
                current = self._sessions.get(session_id)
                if current is not None:
                    return current, False

            created = GuestSession(
                session_id=secrets.token_urlsafe(32),
                created_at=now,
                expires_at=now + self._ttl,
            )
            self._sessions[created.session_id] = created
            return created, True

    def cleanup_expired(self) -> int:
        return len(self.pop_expired())

    def pop_expired(self) -> tuple[GuestSession, ...]:
        with self._lock:
            now = self._clock()
            expired = tuple(
                session for session in self._sessions.values() if session.expires_at <= now
            )
            for session in expired:
                del self._sessions[session.session_id]
            return expired

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _remove_expired(self, now: datetime) -> int:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired:
            del self._sessions[session_id]
        return len(expired)
