from datetime import datetime, timedelta, timezone

import pytest

from api.analysis_store import (
    AnalysisExpiredError,
    AnalysisNotFoundError,
    AnalysisSessionStore,
)


def test_analysis_store_expires_sessions_and_does_not_expose_mutable_report() -> None:
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    current = [now]
    store = AnalysisSessionStore(timedelta(minutes=120), clock=lambda: current[0])

    created = store.create("session-a", "sales.csv", {"kpis": {"net_revenue": 100}}, b"data", b"")
    created.report["kpis"]["net_revenue"] = 0

    assert store.get("session-a", created.analysis_id).report["kpis"]["net_revenue"] == 100

    current[0] = now + timedelta(minutes=120)
    with pytest.raises(AnalysisExpiredError):
        store.get("session-a", created.analysis_id)


def test_analysis_store_delete_removes_session() -> None:
    store = AnalysisSessionStore(timedelta(minutes=1))
    created = store.create("session-a", "sales.csv", {}, b"data", b"")

    store.delete("session-a", created.analysis_id)

    with pytest.raises(AnalysisNotFoundError):
        store.get("session-a", created.analysis_id)


def test_analysis_store_hides_another_guest_sessions_analysis() -> None:
    store = AnalysisSessionStore(timedelta(minutes=1))
    created = store.create("session-a", "sales.csv", {}, b"data", b"")

    with pytest.raises(AnalysisNotFoundError):
        store.get("session-b", created.analysis_id)
    with pytest.raises(AnalysisNotFoundError):
        store.delete("session-b", created.analysis_id)
