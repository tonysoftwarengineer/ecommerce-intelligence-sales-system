from unittest.mock import patch

from fastapi.testclient import TestClient

import api.main as api_main


def test_report_endpoint_survives_forecast_failure():
    # Patched where it's *used* (api.main), not where it's defined
    # (src.models.forecast) -- standard mocking practice. TestClient as a
    # context manager genuinely runs the real lifespan hook, including a
    # real build_dataset() call -- only forecasting is faked, nothing else.
    with patch("api.main.forecast_linear_trend", side_effect=RuntimeError("boom")):
        with TestClient(api_main.app) as client:
            report_response = client.get("/api/v1/report")
            forecast_response = client.get("/api/v1/forecast")

    assert report_response.status_code == 200
    assert forecast_response.status_code == 503


def test_partial_months_are_flagged():
    # The 3 dataset-boundary months (collection started/stopped mid-month)
    # must be flagged so the frontend can exclude them from the trend chart,
    # matching what trim_edge_artifacts already does for the forecast.
    with TestClient(api_main.app) as client:
        months = client.get("/api/v1/report").json()["revenue_by_month"]

    flagged = {m["month"] for m in months if m["is_partial"]}
    assert flagged == {"2016-09", "2016-12", "2018-09"}


def test_segments_endpoint_summarises_by_default():
    # Shipping all ~94k per-customer rows made this response ~12MB while the
    # dashboard only ever read the 4-row summary. Guard against regressing.
    with TestClient(api_main.app) as client:
        default = client.get("/api/v1/segments")
        detailed = client.get("/api/v1/segments?include_customers=true")

    summary = default.json()
    assert summary["segments"] == []
    assert len(summary["segment_counts"]) == 4
    assert len(default.content) < 2_000

    assert len(detailed.json()["segments"]) > 1_000


def test_cors_preflight_allows_localhost_origin():
    with TestClient(api_main.app) as client:
        response = client.options(
            "/api/v1/report",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
