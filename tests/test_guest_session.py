from datetime import datetime, timedelta, timezone

from api.guest_session import GuestSessionStore


def test_guest_session_store_reuses_a_live_session_and_rotates_an_expired_one() -> None:
    current = [datetime(2026, 9, 17, tzinfo=timezone.utc)]
    store = GuestSessionStore(timedelta(minutes=30), clock=lambda: current[0])

    first, first_created = store.resolve(None)
    reused, reused_created = store.resolve(first.session_id)

    assert first_created is True
    assert reused_created is False
    assert reused == first

    current[0] += timedelta(minutes=30)
    rotated, rotated_created = store.resolve(first.session_id)
    assert rotated_created is True
    assert rotated.session_id != first.session_id
