"""Regression checks for the manually usable ten-CSV evaluation pack."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import analysis_store, upload_store
from scripts.evaluate_product_demand_csv_pack import run_case, scenarios


@pytest.fixture
def client():
    upload_store.clear()
    analysis_store.clear()
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    upload_store.clear()
    analysis_store.clear()


@pytest.mark.parametrize("case", scenarios(), ids=lambda case: case.name)
def test_csv_pack_expected_outcome(client, case):
    assert run_case(client, case)["expectations_passed"]


def test_large_cancelled_orders_do_not_change_fulfilled_demand(client):
    case = scenarios()[2]
    with_cancellations = run_case(client, case)
    without_cancellations = run_case(
        client, replace(case, rows=[r for r in case.rows if r["order_status"] == "Completed"])
    )
    first = with_cancellations["demand"]["products"][0]
    second = without_cancellations["demand"]["products"][0]
    assert first["forecast"] == second["forecast"]
    assert first["evidence"] == second["evidence"]
    assert first["selected_method"] == second["selected_method"]
    assert with_cancellations["net_revenue_ngn"] == without_cancellations["net_revenue_ngn"]


def test_category_pack_does_not_bypass_category_confirmation(client):
    case = scenarios()[3]
    result = run_case(
        client,
        replace(case, expected_categories=0, assumptions={"confirm_product_categories": False}),
    )
    assert "category_confirmation_required" in result["demand"]["category_dataset_reason_codes"]
