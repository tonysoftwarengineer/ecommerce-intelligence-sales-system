import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Optional


class UploadNotFoundError(KeyError):
    pass


class UploadExpiredError(KeyError):
    pass


@dataclass(frozen=True)
class TemporaryUpload:
    upload_id: str
    owner_scope_id: str
    filename: str
    contents: bytes
    columns: tuple[str, ...]
    created_at: datetime
    expires_at: datetime


class TemporaryUploadStore:
    """Thread-safe, process-local storage for short-lived uploaded CSV files."""

    def __init__(
        self,
        ttl: timedelta,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("Upload TTL must be positive")

        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._uploads: dict[str, TemporaryUpload] = {}
        self._lock = RLock()

    def create(
        self,
        owner_scope_id: str,
        filename: str,
        contents: bytes,
        columns: Sequence[str],
    ) -> TemporaryUpload:
        now = self._clock()
        upload = TemporaryUpload(
            upload_id=secrets.token_urlsafe(32),
            owner_scope_id=owner_scope_id,
            filename=filename,
            contents=contents,
            columns=tuple(columns),
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._remove_expired(now)
            self._uploads[upload.upload_id] = upload
        return upload

    def get(self, owner_scope_id: str, upload_id: str) -> TemporaryUpload:
        now = self._clock()
        with self._lock:
            upload = self._uploads.get(upload_id)
            if upload is None or upload.owner_scope_id != owner_scope_id:
                raise UploadNotFoundError(upload_id)
            if upload.expires_at <= now:
                del self._uploads[upload_id]
                raise UploadExpiredError(upload_id)
            return upload

    def delete(self, owner_scope_id: str, upload_id: str) -> None:
        with self._lock:
            upload = self._uploads.get(upload_id)
            if upload is None or upload.owner_scope_id != owner_scope_id:
                raise UploadNotFoundError(upload_id)
            del self._uploads[upload_id]

    def cleanup_expired(self) -> int:
        with self._lock:
            return self._remove_expired(self._clock())

    def clear(self) -> None:
        with self._lock:
            self._uploads.clear()

    def _remove_expired(self, now: datetime) -> int:
        expired_ids = [
            upload_id for upload_id, upload in self._uploads.items() if upload.expires_at <= now
        ]
        for upload_id in expired_ids:
            del self._uploads[upload_id]
        return len(expired_ids)
