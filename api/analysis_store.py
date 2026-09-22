import copy
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Optional


class AnalysisNotFoundError(KeyError):
    pass


class AnalysisExpiredError(KeyError):
    pass


@dataclass(frozen=True)
class AnalysisSession:
    analysis_id: str
    owner_scope_id: str
    filename: str
    report: dict[str, Any]
    canonical_csv: bytes
    quarantine_csv: bytes
    created_at: datetime
    expires_at: datetime


class AnalysisSessionStore:
    """Thread-safe, process-local storage for short-lived analysis results."""

    def __init__(
        self,
        ttl: timedelta,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("Analysis TTL must be positive")

        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sessions: dict[str, AnalysisSession] = {}
        self._lock = RLock()

    def create(
        self,
        owner_scope_id: str,
        filename: str,
        report: dict[str, Any],
        canonical_csv: bytes,
        quarantine_csv: bytes,
    ) -> AnalysisSession:
        now = self._clock()
        session = AnalysisSession(
            analysis_id=secrets.token_urlsafe(32),
            owner_scope_id=owner_scope_id,
            filename=filename,
            report=copy.deepcopy(report),
            canonical_csv=canonical_csv,
            quarantine_csv=quarantine_csv,
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._remove_expired(now)
            self._sessions[session.analysis_id] = session
        return self._copy_session(session)

    def get(self, owner_scope_id: str, analysis_id: str) -> AnalysisSession:
        now = self._clock()
        with self._lock:
            session = self._sessions.get(analysis_id)
            if session is None or session.owner_scope_id != owner_scope_id:
                raise AnalysisNotFoundError(analysis_id)
            if session.expires_at <= now:
                del self._sessions[analysis_id]
                raise AnalysisExpiredError(analysis_id)
            return self._copy_session(session)

    def delete(self, owner_scope_id: str, analysis_id: str) -> None:
        with self._lock:
            session = self._sessions.get(analysis_id)
            if session is None or session.owner_scope_id != owner_scope_id:
                raise AnalysisNotFoundError(analysis_id)
            del self._sessions[analysis_id]

    def cleanup_expired(self) -> int:
        return len(self.pop_expired())

    def pop_expired(self) -> tuple[AnalysisSession, ...]:
        with self._lock:
            now = self._clock()
            expired = tuple(
                session for session in self._sessions.values() if session.expires_at <= now
            )
            for session in expired:
                del self._sessions[session.analysis_id]
            return tuple(self._copy_session(session) for session in expired)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _remove_expired(self, now: datetime) -> int:
        expired_ids = [
            analysis_id
            for analysis_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for analysis_id in expired_ids:
            del self._sessions[analysis_id]
        return len(expired_ids)

    @staticmethod
    def _copy_session(session: AnalysisSession) -> AnalysisSession:
        return AnalysisSession(
            analysis_id=session.analysis_id,
            owner_scope_id=session.owner_scope_id,
            filename=session.filename,
            report=copy.deepcopy(session.report),
            canonical_csv=session.canonical_csv,
            quarantine_csv=session.quarantine_csv,
            created_at=session.created_at,
            expires_at=session.expires_at,
        )
