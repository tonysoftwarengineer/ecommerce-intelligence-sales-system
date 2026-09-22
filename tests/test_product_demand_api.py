from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.routes import analysis_store
from api.serializers import dataframe_to_csv_bytes
from config import GUEST_SESSION_COOKIE


@pytest.fixture(autouse=True)
def clear_analysis_sessions():
    analysis_store.clear()
    api_main.guest_session_store.clear()
    yield
    analysis_store.clear()
    api_main.guest_session_store.clear()


def _canonical_row(
    product_id: str,
    day: date,
    quantity: int = 3,
    *,
    category: str | None = None,
) -> dict[str, object]:
    row = {
        "source_row": 2,
        "order_id": f"{product_id}-{day.isoformat()}",
        "order_date": pd.Timestamp(day),
        "recognition_date": pd.Timestamp(day),
        "customer_id": "customer",
        "currency": "USD",
        "order_status": "completed",
        "quantity": Decimal(quantity),
        "returned_quantity": None,
        "product_id": product_id,
        "product_name": f"Product {product_id}",
        "unit_of_measure": "piece",
    }
    if category is not None:
        row["product_category"] = category
    return row


def _daily_rows(product_id: str, days: int, quantity: int = 3) -> list[dict[str, object]]:
    start = date(2025, 1, 1)
    return [
        _canonical_row(product_id, start + timedelta(days=offset), quantity)
        for offset in range(days)
    ]


def _analysis_id(
    client: TestClient,
    rows: list[dict[str, object]],
    *,
    revenue_mode: str = "row_total",
    decision_ready: bool = True,
) -> str:
    guest_session, _ = api_main.guest_session_store.resolve(None)
    client.cookies.set(GUEST_SESSION_COOKIE, guest_session.session_id)
    session = analysis_store.create(
        owner_scope_id=guest_session.session_id,
        filename="sales.csv",
        report={
            "revenue_mode": revenue_mode,
            "data_quality": {
                "decision_ready": decision_ready,
                "message": (
                    "Every source row passed validation."
                    if decision_ready
                    else "Too many source rows were rejected; correct the CSV first."
                ),
            },
            "currency_reports": {"USD": {}},
        },
        canonical_csv=dataframe_to_csv_bytes(pd.DataFrame(rows)),
        quarantine_csv=b"",
    )
    return session.analysis_id


def _confirmed_assumptions() -> dict[str, object]:
    return {
        "export_covers_all_open_days": True,
        "stockout_tracking_complete": True,
    }


def test_product_demand_endpoint_returns_one_evidence_gated_weekly_preview() -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis_id(client, _daily_rows("0007", 119))

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/product-demand",
        json=_confirmed_assumptions(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "preview_available"
    assert body["target"] == "fulfilled_units"
    assert body["horizon_days"] == 7
    assert body["supported_use_approved"] is False
    assert body["preview_product_count"] == 1
    assert body["unavailable_product_count"] == 0
    assert body["preview_category_count"] == 0
    assert body["categories"] == []
    assert body["category_dataset_explanations"] == []
    assert body["unresolved_row_count"] == 0

    product = body["products"][0]
    assert product["product_id"] == "0007"
    assert product["trust_state"] == "limited_preview"
    assert product["numeric_forecast_allowed"] is True
    assert product["selected_method"]
    assert product["selected_method_name"]
    assert "beat forecasting zero" in product["selection_reason"]
    assert product["evidence"]["shared_test_weeks"] == 13
    assert product["evidence"]["minimum_required_test_weeks"] == 13
    assert product["evidence"]["benchmark"] == "zero"
    assert product["evidence"]["benchmark_passed"] is True
    assert product["forecast"]["total_units"] == 21.0
    assert product["forecast"]["average_daily_planning_rate"] == 3.0
    assert len(product["forecast"]["forecast_dates"]) == 7
    assert product["forecast"]["daily_predictions_provided"] is False
    assert "not decision-ready" in product["warning"]


def test_product_demand_endpoint_hides_number_when_confirmations_are_missing() -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis_id(client, _daily_rows("A", 119))

    response = client.post(f"/api/v1/analyses/{analysis_id}/product-demand", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    product = body["products"][0]
    assert product["trust_state"] == "unavailable"
    assert product["numeric_forecast_allowed"] is False
    assert product["forecast"] is None
    assert product["selected_method"] is None
    assert product["selection_reason"] is None
    assert set(product["data_reason_codes"]) == {
        "stockout_data_unavailable",
        "incomplete_daily_coverage",
    }
    assert "Correct the listed data issue" in product["explanations"][-1]


def test_product_demand_endpoint_isolates_short_products() -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis_id(client, [*_daily_rows("A", 119), *_daily_rows("B", 35)])

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/product-demand",
        json=_confirmed_assumptions(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial_preview"
    assert body["preview_product_count"] == 1
    assert body["unavailable_product_count"] == 1
    products = {product["product_id"]: product for product in body["products"]}
    assert products["A"]["forecast"]["total_units"] == 21.0
    assert products["B"]["forecast"] is None
    assert products["B"]["policy_reason_codes"] == ["no_weekly_winner"]


def test_product_demand_endpoint_respects_global_source_data_quality_gate() -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis_id(client, _daily_rows("A", 119), decision_ready=False)

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/product-demand",
        json=_confirmed_assumptions(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["products"] == []
    assert body["dataset_reason_codes"] == ["insufficient_data_quality"]
    assert "correct the CSV" in body["dataset_explanations"][0]


def test_product_demand_endpoint_keeps_order_total_mode_unavailable() -> None:
    client = TestClient(api_main.app)
    analysis_id = _analysis_id(client, _daily_rows("A", 119), revenue_mode="order_total")

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/product-demand",
        json=_confirmed_assumptions(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["products"] == []
    assert body["dataset_reason_codes"] == ["order_total_ineligible"]


def test_product_demand_endpoint_accepts_structured_stockout_identity() -> None:
    client = TestClient(api_main.app)
    rows = _daily_rows("A", 126)
    analysis_id = _analysis_id(client, rows)

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/product-demand",
        json={
            **_confirmed_assumptions(),
            "stockout_dates": [
                {
                    "identity_source": "product_id",
                    "identity_value": "A",
                    "dates": ["2025-05-06"],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["products"][0]["forecast"] is None
    assert body["products"][0]["policy_reason_codes"] == ["final_forecast_unavailable"]


def test_product_demand_endpoint_returns_analysis_lookup_errors() -> None:
    client = TestClient(api_main.app)

    response = client.post(
        "/api/v1/analyses/does-not-exist/product-demand",
        json=_confirmed_assumptions(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Analysis session not found"


def test_product_demand_endpoint_returns_a_category_level_fallback() -> None:
    client = TestClient(api_main.app)
    start = date(2025, 1, 1)
    rows = [
        _canonical_row(
            "A" if week % 2 == 0 else "B",
            start + timedelta(days=week * 7),
            quantity=7,
            category="Meal Kits",
        )
        for week in range(20)
    ]
    analysis_id = _analysis_id(client, rows)

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/product-demand",
        json={**_confirmed_assumptions(), "confirm_product_categories": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial_preview"
    assert body["preview_product_count"] == 0
    assert body["preview_category_count"] == 1
    assert body["unavailable_category_count"] == 0
    category = body["categories"][0]
    assert category["category_name"] == "Meal Kits"
    assert category["product_count"] == 2
    assert category["forecast"]["total_units"] == 7.0
    assert category["forecast"]["average_daily_planning_rate"] == 1.0
    assert category["evidence"]["shared_test_weeks"] >= 13
    assert category["evidence"]["benchmark_passed"] is True
    assert "not allocate" in category["warning"]
