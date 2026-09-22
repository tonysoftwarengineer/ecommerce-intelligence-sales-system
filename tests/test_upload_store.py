from datetime import datetime, timedelta, timezone

import pytest

from api.upload_store import (
    TemporaryUploadStore,
    UploadExpiredError,
    UploadNotFoundError,
)


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def test_upload_store_expires_an_upload_after_fixed_ttl():
    clock = MutableClock()
    store = TemporaryUploadStore(ttl=timedelta(minutes=30), clock=clock)
    upload = store.create("session-a", "sales.csv", b"a,b\n1,2", ["a", "b"])

    clock.now += timedelta(minutes=30)

    with pytest.raises(UploadExpiredError):
        store.get("session-a", upload.upload_id)
    with pytest.raises(UploadNotFoundError):
        store.get("session-a", upload.upload_id)


def test_upload_store_cleanup_removes_only_expired_uploads():
    clock = MutableClock()
    store = TemporaryUploadStore(ttl=timedelta(minutes=30), clock=clock)
    expired_upload = store.create("session-a", "first.csv", b"a\n1", ["a"])

    clock.now += timedelta(minutes=20)
    active_upload = store.create("session-a", "second.csv", b"b\n2", ["b"])
    clock.now += timedelta(minutes=10)

    assert store.cleanup_expired() == 1
    with pytest.raises(UploadNotFoundError):
        store.get("session-a", expired_upload.upload_id)
    assert store.get("session-a", active_upload.upload_id) == active_upload


def test_upload_store_generates_distinct_unpredictable_ids():
    store = TemporaryUploadStore(ttl=timedelta(minutes=30))

    first = store.create("session-a", "first.csv", b"a\n1", ["a"])
    second = store.create("session-a", "second.csv", b"b\n2", ["b"])

    assert first.upload_id != second.upload_id
    assert len(first.upload_id) >= 32
    assert len(second.upload_id) >= 32


def test_upload_store_hides_another_guest_sessions_upload() -> None:
    store = TemporaryUploadStore(ttl=timedelta(minutes=30))
    upload = store.create("session-a", "sales.csv", b"a\n1", ["a"])

    with pytest.raises(UploadNotFoundError):
        store.get("session-b", upload.upload_id)
    with pytest.raises(UploadNotFoundError):
        store.delete("session-b", upload.upload_id)
