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
