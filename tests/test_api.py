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
            report_response = client.get("/api/report")
            forecast_response = client.get("/api/forecast")

    assert report_response.status_code == 200
    assert forecast_response.status_code == 503


def test_partial_months_are_flagged():
    # The 3 dataset-boundary months (collection started/stopped mid-month)
    # must be flagged so the frontend can exclude them from the trend chart,
    # matching what trim_edge_artifacts already does for the forecast.
    with TestClient(api_main.app) as client:
        months = client.get("/api/report").json()["revenue_by_month"]

    flagged = {m["month"] for m in months if m["is_partial"]}
    assert flagged == {"2016-09", "2016-12", "2018-09"}


def test_cors_preflight_allows_localhost_origin():
    with TestClient(api_main.app) as client:
        response = client.options(
            "/api/report",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
