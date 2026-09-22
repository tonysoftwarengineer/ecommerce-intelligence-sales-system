"""End-to-end trust tests for realistic small-business CSV shapes.

Each scenario enters through the upload API as CSV bytes. Expected financial
totals are calculated from the fixture's stated business rules rather than from
the implementation under test.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from io import StringIO
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.routes import analysis_store, upload_store


@pytest.fixture(autouse=True)
def clear_temporary_sessions():
    upload_store.clear()
    analysis_store.clear()
    yield
    upload_store.clear()
    analysis_store.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(api_main.app)


def _csv(rows: Sequence[Mapping[str, object]]) -> str:
    assert rows
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _month(offset: int, start: str = "2024-01", date_format: str = "%Y-%m-%d") -> str:
    period = pd.Period(start, freq="M") + offset
    return period.start_time.strftime(date_format)


def _upload(client: TestClient, rows: Sequence[Mapping[str, object]], filename: str) -> str:
    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": (filename, _csv(rows), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["upload_id"]


def _request(
    upload_id: str,
    mapping: dict[str, str],
    *,
    revenue_mode: str = "row_total",
    date_format: str = "%Y-%m-%d",
    currency: str = "USD",
    **overrides: Any,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "upload_id": upload_id,
        "mapping": mapping,
        "revenue_mode": revenue_mode,
        "negative_revenue_policy": "invalid",
        "date_format": date_format,
        "currency": currency,
        "assume_all_completed": True,
        "status_mapping": {},
        "payment_status_mapping": {},
        "discount_type": "none",
        "discount_scope": "per_line",
        "order_discount_allocation": "unallocated",
        "revenue_mismatch_policy": "warn",
        "mismatch_tolerance": 0.01,
        "refund_tax_treatment": None,
    }
    request.update(overrides)
    return request


def _validate(client: TestClient, request: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/v1/uploads/validate-data", json=request)
    assert response.status_code == 200, response.text
    return response.json()


def _analyze(
    client: TestClient,
    request: dict[str, Any],
    *,
    confirm_quarantine: bool = False,
    latest_period_complete: bool = True,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/uploads/analyze",
        json={
            **request,
            "confirm_quarantine": confirm_quarantine,
            "latest_period_complete": latest_period_complete,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_scenario_01_clean_item_level_24_months(client: TestClient) -> None:
    rows = [
        {
            "OrderID": f"O-{index + 1:03}",
            "OrderDate": _month(index),
            "CustomerID": f"C-{index % 5:02}",
            "UnitPrice": 10 + index,
            "Quantity": 2,
            "Category": "",
            "Region": "Lagos",
        }
        for index in range(24)
    ]
    upload_id = _upload(client, rows, "clean_item_sales_24_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "OrderID",
            "order_date": "OrderDate",
            "customer_id": "CustomerID",
            "unit_price": "UnitPrice",
            "quantity": "Quantity",
            "product_category": "Category",
            "state_or_region": "Region",
        },
        revenue_mode="unit_price_times_quantity",
    )

    result = _analyze(client, request)

    assert result["kpis"]["net_revenue"] == 1032
    assert result["kpis"]["order_count"] == 24
    assert result["forecast"]["history_periods"] == 24
    assert result["forecast"]["status"] == "available"
    assert result["top_categories"] == [{"category": "Uncategorized", "revenue": 1032}]


def test_scenario_02_row_totals_9_months(client: TestClient) -> None:
    rows = [
        {
            "Invoice": f"INV-{index + 1}",
            "SaleDate": _month(index, "2025-01"),
            "Buyer": f"B-{index % 3}",
            "FinalAmount": 100 + index * 10,
        }
        for index in range(9)
    ]
    upload_id = _upload(client, rows, "final_amount_sales_9_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Invoice",
            "order_date": "SaleDate",
            "customer_id": "Buyer",
            "revenue": "FinalAmount",
        },
    )

    result = _analyze(client, request)

    assert result["kpis"]["net_revenue"] == 1260
    assert result["kpis"]["average_order_value"] == 140
    assert result["forecast"]["status"] == "experimental"
    assert result["forecast"]["horizon"] == 1


def test_scenario_03_repeated_order_totals_detect_conflicting_order_status(
    client: TestClient,
) -> None:
    rows: list[dict[str, object]] = []
    for index in range(15):
        total = 200 + index * 5
        statuses = ("Delivered", "Shipped") if index == 14 else ("Delivered", "Delivered")
        for line, status in enumerate(statuses, start=1):
            rows.append(
                {
                    "OrderNumber": f"ORD-{index + 1}",
                    "LineID": line,
                    "OrderDate": _month(index, "2024-01"),
                    "CustomerID": f"C-{index % 4}",
                    "OrderTotal": total,
                    "FulfillmentStatus": status,
                }
            )
    upload_id = _upload(client, rows, "repeated_order_totals_15_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "OrderNumber",
            "order_date": "OrderDate",
            "customer_id": "CustomerID",
            "revenue": "OrderTotal",
            "order_status": "FulfillmentStatus",
        },
        revenue_mode="order_total",
        assume_all_completed=False,
        status_mapping={"Delivered": "completed", "Shipped": "pending"},
    )

    validation = _validate(client, request)

    assert validation["invalid_rows"] == 2
    assert validation["issue_counts"] == {"order_conflict": 2}
    result = _analyze(client, request, confirm_quarantine=True)
    assert result["canonical_rows"] == 14
    assert result["kpis"]["net_revenue"] == sum(200 + index * 5 for index in range(14))


def test_scenario_04_fixed_line_discounts_12_months(client: TestClient) -> None:
    rows = [
        {
            "Order": f"O-{index}",
            "Date": _month(index),
            "Customer": f"C-{index % 3}",
            "Price": 50,
            "Qty": 2,
            "DiscountAmount": 10,
        }
        for index in range(12)
    ]
    upload_id = _upload(client, rows, "fixed_discount_sales_12_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "order_date": "Date",
            "customer_id": "Customer",
            "unit_price": "Price",
            "quantity": "Qty",
            "discount": "DiscountAmount",
        },
        revenue_mode="unit_price_times_quantity",
        discount_type="fixed",
    )

    result = _analyze(client, request)

    assert result["kpis"]["gross_revenue"] == 1200
    assert result["kpis"]["discount_amount"] == 120
    assert result["kpis"]["net_revenue"] == 1080


def test_scenario_05_percentage_line_discounts_6_months(client: TestClient) -> None:
    rows = [
        {
            "Order": f"O-{index}",
            "Date": _month(index),
            "Customer": f"C-{index}",
            "Price": 100,
            "Quantity": 2,
            "DiscountPercent": 10,
        }
        for index in range(6)
    ]
    upload_id = _upload(client, rows, "percentage_discount_sales_6_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "order_date": "Date",
            "customer_id": "Customer",
            "unit_price": "Price",
            "quantity": "Quantity",
            "discount": "DiscountPercent",
        },
        revenue_mode="unit_price_times_quantity",
        discount_type="percentage",
    )

    result = _analyze(client, request)

    assert result["kpis"]["gross_revenue"] == 1200
    assert result["kpis"]["discount_amount"] == 120
    assert result["kpis"]["net_revenue"] == 1080
    assert result["forecast"]["status"] == "experimental"


def test_scenario_06_percentage_discount_over_entire_order_18_months(
    client: TestClient,
) -> None:
    rows: list[dict[str, object]] = []
    for index in range(18):
        for line, price in enumerate((60, 40), start=1):
            rows.append(
                {
                    "Order": f"O-{index}",
                    "Line": line,
                    "Date": _month(index),
                    "Customer": f"C-{index % 4}",
                    "Price": price,
                    "Quantity": 1,
                    "OrderDiscountPercent": 10,
                }
            )
    upload_id = _upload(client, rows, "whole_order_percentage_discount_18_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "line_item_id": "Line",
            "order_date": "Date",
            "customer_id": "Customer",
            "unit_price": "Price",
            "quantity": "Quantity",
            "discount": "OrderDiscountPercent",
        },
        revenue_mode="unit_price_times_quantity",
        discount_type="percentage",
        discount_scope="entire_order",
        order_discount_allocation="proportional",
    )

    validation = _validate(client, request)
    assert validation["invalid_rows"] == 0
    result = _analyze(client, request)
    assert result["kpis"]["gross_revenue"] == 1800
    assert result["kpis"]["discount_amount"] == 180
    assert result["kpis"]["net_revenue"] == 1620


def test_scenario_07_completed_pending_cancelled_and_returned_orders(
    client: TestClient,
) -> None:
    statuses = [
        ("Delivered", 100),
        ("Processing", 80),
        ("Cancelled", 60),
        ("Returned", 40),
        ("Delivered", 50),
        ("Processing", 30),
        ("Cancelled", 20),
        ("Returned", 10),
    ]
    rows = [
        {
            "Order": f"O-{index}",
            "Date": _month(index),
            "Customer": f"C-{index}",
            "Total": total,
            "Status": status,
        }
        for index, (status, total) in enumerate(statuses)
    ]
    upload_id = _upload(client, rows, "mixed_status_sales_8_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "order_date": "Date",
            "customer_id": "Customer",
            "revenue": "Total",
            "order_status": "Status",
        },
        assume_all_completed=False,
        status_mapping={
            "Delivered": "completed",
            "Processing": "pending",
            "Cancelled": "cancelled",
            "Returned": "returned",
        },
    )

    result = _analyze(client, request)

    assert result["kpis"]["gross_revenue"] == 200
    assert result["kpis"]["refund_amount"] == 50
    assert result["kpis"]["net_revenue"] == 150
    assert result["kpis"]["pending_value"] == 110
    assert result["kpis"]["order_count"] == 4


def test_scenario_08_unknown_status_is_visible_and_quarantined(client: TestClient) -> None:
    rows = [
        {
            "Order": f"O-{index}",
            "Date": _month(index),
            "Customer": f"C-{index}",
            "Total": 200 if index == 6 else 100,
            "Status": "Mystery" if index == 6 else "Delivered",
        }
        for index in range(7)
    ]
    upload_id = _upload(client, rows, "unknown_status_sales_7_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "order_date": "Date",
            "customer_id": "Customer",
            "revenue": "Total",
            "order_status": "Status",
        },
        assume_all_completed=False,
        status_mapping={"Delivered": "completed"},
    )

    validation = _validate(client, request)

    assert validation["invalid_rows"] == 1
    assert validation["issue_counts"] == {"unknown_status": 1}
    assert validation["requires_confirmation"] is True
    result = _analyze(client, request, confirm_quarantine=True)
    assert result["quarantined_rows"] == 1
    assert result["kpis"]["net_revenue"] == 600


def test_scenario_09_refund_including_tax_keeps_tax_and_shipping_separate(
    client: TestClient,
) -> None:
    rows = [
        {
            "Order": f"O-{index}",
            "Date": _month(index),
            "Customer": f"C-{index % 4}",
            "Total": 100,
            "Tax": 10,
            "Shipping": 5,
            "Refund": 110 if index == 13 else 0,
            "RefundDate": _month(index) if index == 13 else "",
            "Status": "Returned" if index == 13 else "Delivered",
        }
        for index in range(14)
    ]
    upload_id = _upload(client, rows, "refund_tax_shipping_sales_14_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "order_date": "Date",
            "customer_id": "Customer",
            "revenue": "Total",
            "tax_amount": "Tax",
            "shipping_amount": "Shipping",
            "refund_amount": "Refund",
            "refund_date": "RefundDate",
            "order_status": "Status",
        },
        assume_all_completed=False,
        status_mapping={"Delivered": "completed", "Returned": "returned"},
        refund_tax_treatment="includes_tax",
    )

    result = _analyze(client, request)

    assert result["kpis"]["gross_revenue"] == 1400
    assert result["kpis"]["refund_amount"] == 100
    assert result["kpis"]["net_revenue"] == 1300
    assert result["kpis"]["tax_collected"] == 130
    assert result["kpis"]["shipping_charged"] == 70


def test_scenario_10_exact_duplicate_and_negative_refund_are_auditable(
    client: TestClient,
) -> None:
    rows = [
        {
            "Order": f"O-{index}",
            "Date": _month(index),
            "Customer": f"C-{index}",
            "Total": 100,
        }
        for index in range(10)
    ]
    rows.append({"Order": "R-1", "Date": _month(10), "Customer": "C-1", "Total": -25})
    rows.append(dict(rows[0]))
    upload_id = _upload(client, rows, "duplicate_and_refund_sales_11_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "order_date": "Date",
            "customer_id": "Customer",
            "revenue": "Total",
        },
        negative_revenue_policy="refunds",
    )

    validation = _validate(client, request)

    assert validation["invalid_rows"] == 1
    assert validation["issue_counts"] == {"exact_duplicate": 1}
    assert "1 row(s) contain negative revenue" in " ".join(validation["warnings"])
    result = _analyze(client, request, confirm_quarantine=True)
    assert result["canonical_rows"] == 11
    assert result["kpis"]["gross_revenue"] == 1000
    assert result["kpis"]["refund_amount"] == 25
    assert result["kpis"]["net_revenue"] == 975


def test_scenario_11_invalid_dates_and_numbers_are_quarantined(client: TestClient) -> None:
    rows = [
        {
            "Order": f"O-{index}",
            "Date": "not-a-date" if index == 9 else _month(index),
            "Customer": f"C-{index}",
            "Total": "not-money" if index == 10 else 100,
        }
        for index in range(11)
    ]
    upload_id = _upload(client, rows, "invalid_values_sales_11_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "order_date": "Date",
            "customer_id": "Customer",
            "revenue": "Total",
        },
    )

    validation = _validate(client, request)

    assert validation["invalid_rows"] == 2
    assert validation["issue_counts"] == {"invalid_date": 1, "invalid_number": 1}
    result = _analyze(client, request, confirm_quarantine=True)
    assert result["kpis"]["net_revenue"] == 900


def test_scenario_12_common_retail_headers_receive_explainable_suggestions(
    client: TestClient,
) -> None:
    rows = [
        {
            "Order Number": f"O-{index}",
            "Transaction Date": _month(index),
            "Client Code": f"C-{index % 5}",
            "Selling Price": 25,
            "Units Sold": 2,
            "Merchandise Department": "Accessories",
            "Sales Territory": "North",
        }
        for index in range(16)
    ]
    upload_id = _upload(client, rows, "retail_export_headers_16_months.csv")

    response = client.post(
        "/api/v1/uploads/mapping-suggestions",
        json={"upload_id": upload_id, "revenue_mode": "row_total"},
    )

    assert response.status_code == 200
    suggestions = response.json()
    assert suggestions["recommended_revenue_mode"] == "unit_price_times_quantity"
    assert suggestions["mapping"] == {
        "order_id": "Order Number",
        "order_date": "Transaction Date",
        "customer_id": "Client Code",
        "unit_price": "Selling Price",
        "quantity": "Units Sold",
        "product_category": "Merchandise Department",
        "state_or_region": "Sales Territory",
    }
    assert all(candidate["reason"] for candidate in suggestions["candidates"])


def test_mapping_suggestions_recognize_product_identity_name_and_unit(
    client: TestClient,
) -> None:
    upload_id = _upload(
        client,
        [
            {
                "InvoiceNo": "A-1",
                "InvoiceDate": "2025-01-01",
                "CustomerID": "C-1",
                "TotalAmount": 10,
                "StockCode": "0007",
                "Description": "Blue Mug",
                "UOM": "piece",
            }
        ],
        "product_headers.csv",
    )

    response = client.post(
        "/api/v1/uploads/mapping-suggestions",
        json={"upload_id": upload_id, "revenue_mode": "row_total"},
    )

    assert response.status_code == 200
    suggestions = response.json()
    assert suggestions["mapping"]["product_id"] == "StockCode"
    assert suggestions["mapping"]["product_name"] == "Description"
    assert suggestions["mapping"]["unit_of_measure"] == "UOM"


def test_scenario_13_day_first_dates_13_months(client: TestClient) -> None:
    rows = [
        {
            "Invoice": f"I-{index}",
            "Date": _month(index, date_format="%d/%m/%Y"),
            "Customer": f"C-{index % 4}",
            "Total": 75,
        }
        for index in range(13)
    ]
    upload_id = _upload(client, rows, "day_first_sales_13_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Invoice",
            "order_date": "Date",
            "customer_id": "Customer",
            "revenue": "Total",
        },
        date_format="%d/%m/%Y",
    )

    result = _analyze(client, request)

    assert result["kpis"]["net_revenue"] == 975
    assert result["forecast"]["history_periods"] == 13
    assert result["forecast"]["status"] == "available"


def test_scenario_14_missing_month_blocks_forecast_but_not_reporting(
    client: TestClient,
) -> None:
    month_offsets = [0, 1, 3, 4, 5, 6, 7, 8]
    rows = [
        {
            "Order": f"O-{index}",
            "Date": _month(month_offset),
            "Customer": f"C-{index}",
            "Total": 100,
        }
        for index, month_offset in enumerate(month_offsets)
    ]
    upload_id = _upload(client, rows, "sales_with_missing_month_9_month_span.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "order_date": "Date",
            "customer_id": "Customer",
            "revenue": "Total",
        },
    )

    result = _analyze(client, request)

    assert result["kpis"]["net_revenue"] == 800
    assert result["forecast"]["status"] == "unavailable"
    assert any("2024-03" in limitation for limitation in result["forecast"]["limitations"])


def test_scenario_15_multiple_currencies_are_never_summed_together(
    client: TestClient,
) -> None:
    rows: list[dict[str, object]] = []
    for index in range(12):
        rows.extend(
            [
                {
                    "Order": f"USD-{index}",
                    "Date": _month(index),
                    "Customer": f"US-{index % 3}",
                    "Total": 100,
                    "Currency": "USD",
                },
                {
                    "Order": f"NGN-{index}",
                    "Date": _month(index),
                    "Customer": f"NG-{index % 3}",
                    "Total": 1000,
                    "Currency": "NGN",
                },
            ]
        )
    upload_id = _upload(client, rows, "multi_currency_sales_12_months.csv")
    request = _request(
        upload_id,
        {
            "order_id": "Order",
            "order_date": "Date",
            "customer_id": "Customer",
            "revenue": "Total",
            "currency": "Currency",
        },
        currency="USD",
    )

    result = _analyze(client, request)

    assert result["available_currencies"] == ["NGN", "USD"]
    assert result["currency"] == "NGN"
    assert result["kpis"]["net_revenue"] == 12000
    usd_response = client.get(
        f"/api/v1/analyses/{result['analysis_id']}",
        params={"currency": "USD"},
    )
    assert usd_response.status_code == 200
    assert usd_response.json()["kpis"]["net_revenue"] == 1200
