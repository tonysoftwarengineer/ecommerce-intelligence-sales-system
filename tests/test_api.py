from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.routes import analysis_observability, analysis_store, upload_store
from api.upload_store import UploadExpiredError


@pytest.fixture(autouse=True)
def clear_temporary_uploads():
    upload_store.clear()
    analysis_store.clear()
    analysis_observability.clear()
    yield
    upload_store.clear()
    analysis_store.clear()
    analysis_observability.clear()


def upload_csv(client: TestClient, csv: str) -> str:
    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": ("sales.csv", csv, "text/csv")},
    )
    assert response.status_code == 200
    return response.json()["upload_id"]


def row_total_request(upload_id: str) -> dict:
    return {
        "upload_id": upload_id,
        "mapping": {
            "order_id": "Invoice",
            "order_date": "Date",
            "customer_id": "Customer",
            "revenue": "Total",
        },
        "revenue_mode": "row_total",
        "negative_revenue_policy": "invalid",
        "date_format": "%Y-%m-%d",
        "currency": "USD",
        "assume_all_completed": True,
    }


def test_csv_preview_upload_returns_dataset_shape_and_sample_rows():
    client = TestClient(api_main.app)
    csv = "\n".join(
        [
            "Order ID,Date,Customer,Total",
            "A1001,2024-01-01,C001,150.75",
            "A1002,2024-01-02,C002,200.00",
            "A1003,2024-01-03,C003,50.25",
            "A1004,2024-01-04,C004,10.00",
            "A1005,2024-01-05,C005,70.00",
            "A1006,2024-01-06,C006,90.00",
        ]
    )

    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": ("sales.csv", csv, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["upload_id"]
    assert body["expires_at"]
    assert body["filename"] == "sales.csv"
    assert body["row_count"] == 6
    assert body["column_count"] == 4
    assert body["columns"] == ["Order ID", "Date", "Customer", "Total"]
    assert body["dtypes"]["Total"] == "float64"
    assert len(body["sample_rows"]) == 5
    assert body["sample_rows"][0]["Order ID"] == "A1001"
    assert body["sample_rows"][0]["Total"] == "150.75"


def test_csv_preview_rejects_non_csv_upload():
    client = TestClient(api_main.app)

    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": ("sales.txt", "Order ID,Total\nA1001,150.75", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must be a CSV"


def test_csv_preview_preserves_leading_zero_identifiers_in_samples():
    client = TestClient(api_main.app)

    response = client.post(
        "/api/v1/uploads/preview",
        files={
            "file": (
                "sales.csv",
                "Invoice,Customer,Total\n001,0007,100",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    row = response.json()["sample_rows"][0]
    assert row["Invoice"] == "001"
    assert row["Customer"] == "0007"


def test_csv_preview_masks_direct_personal_identifiers():
    client = TestClient(api_main.app)

    response = client.post(
        "/api/v1/uploads/preview",
        files={
            "file": (
                "sales.csv",
                "CustomerName,CustomerEmail,ProductName\nAda Lovelace,ada@example.com,Mouse",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    row = response.json()["sample_rows"][0]
    assert row["CustomerName"] == "A*** L***"
    assert row["CustomerEmail"] == "a***@example.com"
    assert row["ProductName"] == "Mouse"


def test_mapping_suggestions_recommend_price_times_quantity_for_currency_suffixed_headers():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "OrderID,OrderLineID,OrderDate,CustomerID,UnitPriceNGN,Quantity,LineDiscountNGN,CustomerState,RevenueRecognitionDate,ShippingFeeNGN\n"
        "A1,L1,2025-01-01,C1,100,2,5,Lagos,2025-01-01,10",
    )

    response = client.post(
        "/api/v1/uploads/mapping-suggestions",
        json={"upload_id": upload_id, "revenue_mode": "row_total"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommended_revenue_mode"] == "unit_price_times_quantity"
    assert body["mapping"] == {
        "order_id": "OrderID",
        "order_date": "OrderDate",
        "customer_id": "CustomerID",
        "unit_price": "UnitPriceNGN",
        "quantity": "Quantity",
        "line_item_id": "OrderLineID",
        "discount": "LineDiscountNGN",
        "state_or_region": "CustomerState",
        "recognition_date": "RevenueRecognitionDate",
        "shipping_amount": "ShippingFeeNGN",
    }


def test_mapping_suggestions_explain_optional_reported_total_reconciliation():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "OrderID,OrderDate,CustomerID,UnitPrice,Quantity,TotalAmount\nA1,2025-01-01,C1,100,2,190",
    )

    response = client.post(
        "/api/v1/uploads/mapping-suggestions",
        json={"upload_id": upload_id, "revenue_mode": "row_total"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommended_revenue_mode"] == "unit_price_times_quantity"
    assert "revenue" not in body["mapping"]
    assert any("TotalAmount looks like a reported total" in warning for warning in body["warnings"])


def test_distinct_values_reads_all_rows_and_reports_blanks():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Order,Status\n1,Completed\n2,Pending\n3,Completed\n4,",
    )

    response = client.post(
        "/api/v1/uploads/distinct-values",
        json={"upload_id": upload_id, "columns": ["Status"]},
    )

    assert response.status_code == 200
    assert response.json()["columns"]["Status"] == {
        "values": ["Completed", "Pending"],
        "unique_count": 2,
        "blank_count": 1,
        "truncated": False,
    }


def test_distinct_values_rejects_unknown_columns():
    client = TestClient(api_main.app)
    upload_id = upload_csv(client, "Order,Status\n1,Completed")

    response = client.post(
        "/api/v1/uploads/distinct-values",
        json={"upload_id": upload_id, "columns": ["Missing"]},
    )

    assert response.status_code == 400
    assert "Missing" in response.json()["detail"]


def test_csv_preview_rejects_empty_csv_upload():
    client = TestClient(api_main.app)

    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": ("sales.csv", "", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded CSV is empty"


def test_csv_preview_rejects_unreadable_csv_upload():
    client = TestClient(api_main.app)

    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": ("sales.csv", b"\xff\xfe\x00\x00", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded CSV could not be parsed"


def test_csv_preview_rejects_file_over_configured_size_limit():
    client = TestClient(api_main.app)

    with patch("api.routes.UPLOAD_MAX_BYTES", 10):
        response = client.post(
            "/api/v1/uploads/preview",
            files={"file": ("sales.csv", b"column\n12345", "text/csv")},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Uploaded CSV exceeds the size limit"


def test_schema_mapping_accepts_required_fields_and_warns_about_unmapped_columns():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice No,Sale Date,Client,Amount Paid,Internal Notes\n"
        "A1001,2024-01-01,C001,150.75,Priority customer",
    )

    response = client.post(
        "/api/v1/uploads/validate-mapping",
        json={
            "upload_id": upload_id,
            "mapping": {
                "order_id": "Invoice No",
                "order_date": "Sale Date",
                "customer_id": "Client",
                "revenue": "Amount Paid",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["missing_required_fields"] == []
    assert body["errors"] == []
    assert {
        "quantity",
        "product_id",
        "product_name",
        "unit_of_measure",
    }.issubset(body["optional_fields"])
    assert body["unmapped_columns"] == ["Internal Notes"]
    assert body["warnings"] == ["These columns will be excluded from analysis: Internal Notes"]


def test_schema_mapping_uses_revenue_mode_specific_requirements():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice No,Sale Date,Client,Price,Units\nA1001,2024-01-01,C001,25.00,3",
    )

    response = client.post(
        "/api/v1/uploads/validate-mapping",
        json={
            "upload_id": upload_id,
            "revenue_mode": "unit_price_times_quantity",
            "mapping": {
                "order_id": "Invoice No",
                "order_date": "Sale Date",
                "customer_id": "Client",
                "unit_price": "Price",
                "quantity": "Units",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["required_fields"] == [
        "order_id",
        "order_date",
        "customer_id",
        "unit_price",
        "quantity",
    ]
    assert {
        "revenue",
        "discount",
        "product_id",
        "product_name",
        "unit_of_measure",
        "product_category",
        "state_or_region",
    }.issubset(body["optional_fields"])


def test_schema_mapping_reports_missing_required_field():
    client = TestClient(api_main.app)
    upload_id = upload_csv(client, "Invoice No,Sale Date,Client\nA1001,2024-01-01,C001")

    response = client.post(
        "/api/v1/uploads/validate-mapping",
        json={
            "upload_id": upload_id,
            "mapping": {
                "order_id": "Invoice No",
                "order_date": "Sale Date",
                "customer_id": "Client",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["missing_required_fields"] == ["revenue"]


def test_schema_mapping_reports_unknown_source_column():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice No,Sale Date,Client,Amount Paid\nA1001,2024-01-01,C001,150.75",
    )

    response = client.post(
        "/api/v1/uploads/validate-mapping",
        json={
            "upload_id": upload_id,
            "mapping": {
                "order_id": "Invoice No",
                "order_date": "Sale Date",
                "customer_id": "Client",
                "revenue": "Revenue Total",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["unknown_mapped_columns"] == ["Revenue Total"]


def test_schema_mapping_rejects_reusing_one_column_for_two_meanings():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice No,Sale Date,Client,Amount Paid\nA1001,2024-01-01,C001,150.75",
    )

    response = client.post(
        "/api/v1/uploads/validate-mapping",
        json={
            "upload_id": upload_id,
            "mapping": {
                "order_id": "Invoice No",
                "order_date": "Sale Date",
                "customer_id": "Client",
                "revenue": "Amount Paid",
                "quantity": "Amount Paid",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["duplicate_mapped_columns"] == ["Amount Paid"]


def test_schema_mapping_reports_unsupported_canonical_field():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice No,Sale Date,Client,Amount Paid,Margin\nA1001,2024-01-01,C001,150.75,25.00",
    )

    response = client.post(
        "/api/v1/uploads/validate-mapping",
        json={
            "upload_id": upload_id,
            "mapping": {
                "order_id": "Invoice No",
                "order_date": "Sale Date",
                "customer_id": "Client",
                "revenue": "Amount Paid",
                "profit": "Margin",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["unsupported_fields"] == ["profit"]


def test_data_validation_reports_quarantine_without_silently_dropping_rows():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total\nA001,2025-01-01,C001,100\nA002,not-a-date,C002,50",
    )

    response = client.post(
        "/api/v1/uploads/validate-data",
        json=row_total_request(upload_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_transform"] is True
    assert body["requires_confirmation"] is True
    assert body["total_rows"] == 2
    assert body["valid_rows"] == 1
    assert body["invalid_rows"] == 1
    assert body["issue_counts"] == {"invalid_date": 1}
    assert body["sample_issues"][0]["row_number"] == 3
    assert body["data_quality"]["status"] == "preview"
    assert body["data_quality"]["invalid_row_percentage"] == 50.0
    assert body["data_quality"]["decision_ready"] is False
    assert body["data_quality"]["correction_actions"][0]["source_column"] == "Date"
    assert body["data_quality"]["correction_actions"][0]["sample_row_numbers"] == [3]


def test_transformation_requires_confirmation_then_returns_canonical_and_quarantine_previews():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total\nA001,2025-01-01,C001,100\nA002,not-a-date,C002,50",
    )
    request = row_total_request(upload_id)

    blocked = client.post("/api/v1/uploads/transform", json=request)
    request["confirm_quarantine"] = True
    transformed = client.post("/api/v1/uploads/transform", json=request)

    assert blocked.status_code == 409
    assert transformed.status_code == 200
    body = transformed.json()
    assert body["source_rows"] == 2
    assert body["canonical_rows"] == 1
    assert body["quarantined_rows"] == 1
    assert body["sample_rows"][0]["source_row"] == 2
    assert body["sample_rows"][0]["revenue"] == 100
    assert body["sample_rows"][0]["currency"] == "USD"
    assert body["quarantine_sample"][0]["source_row"] == 3
    assert body["quarantine_sample"][0]["issue_codes"] == ["invalid_date"]


def test_generic_analysis_creates_restorable_capability_aware_session():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total,Category,Region,Units\n"
        "A001,2025-01-01,C001,100,Shoes,Lagos,1\n"
        "A002,2025-02-01,C002,200,Bags,Abuja,2\n"
        "A003,2025-03-01,C001,300,Shoes,Lagos,3\n"
        "A004,2025-04-01,C003,400,Hats,Kano,4\n"
        "A005,2025-05-01,C004,500,Bags,Lagos,5\n"
        "A006,2025-06-01,C005,600,Shoes,Abuja,6",
    )
    request = row_total_request(upload_id)
    request.update(
        {
            "mapping": {
                **request["mapping"],
                "product_category": "Category",
                "state_or_region": "Region",
                "quantity": "Units",
            },
            "latest_period_complete": True,
        }
    )

    response = client.post("/api/v1/uploads/analyze", json=request)

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_id"]
    assert body["currency"] == "USD"
    assert body["kpis"] == {
        "gross_revenue": 2100.0,
        "discount_amount": 0.0,
        "refund_amount": 0.0,
        "net_revenue": 2100.0,
        "pending_value": 0.0,
        "tax_collected": 0.0,
        "shipping_charged": 0.0,
        "chargeback_amount": 0.0,
        "disputed_value": 0.0,
        "net_collected": None,
        "average_order_value": 350.0,
        "order_count": 6,
        "customer_count": 5,
        "units_sold": 21.0,
        "units_returned": None,
    }
    assert body["capabilities"] == {
        "category_analysis": True,
        "regional_analysis": True,
        "quantity_analysis": True,
        "refund_analysis": False,
        "payment_analysis": False,
        "forecasting": True,
    }
    assert body["forecast"]["status"] == "experimental"
    assert body["forecast"]["selected_model"] == "linear_trend"
    assert body["forecast"]["backtest_folds"] == 3
    assert body["forecast"]["trust_level"] == "limited"
    assert len(body["forecast"]["model_evaluations"]) == 3
    assert body["forecast"]["selection_reason"] == (
        "Chosen because it had the lowest mean error among 3 eligible methods across 3 "
        "rolling historical tests."
    )
    assert body["diagnostics"]["comparison"]["status"] == "available"
    assert body["diagnostics"]["comparison"]["insights"][0]["recommended_action"] == {
        "id": "review_latest_sales_change",
        "title": "Review the latest sales change",
        "description": (
            "Validate the order-count and average-order-value contributors before taking action; "
            "this two-period comparison is not a causal finding."
        ),
        "priority": "medium",
        "requires_human_review": True,
        "estimated_impact": None,
        "impact_unit": None,
        "score": {"impact": 2, "urgency": 1, "confidence": 2, "total": 5},
    }
    assert body["diagnostics"]["anomalies"]["status"] == "unavailable"
    assert body["diagnostics"]["anomalies"]["unavailable_capabilities"][0]["code"] == (
        "insufficient_anomaly_history"
    )

    restored = client.get(f"/api/v1/analyses/{body['analysis_id']}")
    assert restored.status_code == 200
    assert restored.json() == body


def test_analysis_observability_reports_aggregate_availability_without_source_data():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total\nA001,2025-01-01,C001,100\nA002,2025-02-01,C002,200",
    )
    request = row_total_request(upload_id)
    request["latest_period_complete"] = True

    analyzed = client.post("/api/v1/uploads/analyze", json=request)
    metrics = client.get("/api/v1/observability/analysis-metrics")

    assert analyzed.status_code == 200
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["analysis_runs"] == 1
    assert body["currency_reports"] == 1
    assert body["latency_ms"]["sample_count"] == 1
    assert body["diagnostics"]["comparison"]["status_counts"] == {"available": 1}
    assert body["diagnostics"]["anomalies"]["status_counts"] == {"unavailable": 1}
    assert body["forecast_status_counts"] == {"unavailable": 1}
    assert "sales.csv" not in body["scope"]


def test_generic_analysis_does_not_invent_unmapped_optional_capabilities():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total,Internal Note\n"
        "A001,2025-01-01,C001,100,Private\n"
        "A002,2025-02-01,C002,200,Private",
    )
    request = row_total_request(upload_id)
    request["latest_period_complete"] = True

    response = client.post("/api/v1/uploads/analyze", json=request)

    assert response.status_code == 200
    body = response.json()
    assert body["capabilities"] == {
        "category_analysis": False,
        "regional_analysis": False,
        "quantity_analysis": False,
        "refund_analysis": False,
        "payment_analysis": False,
        "forecasting": False,
    }
    assert body["kpis"]["units_sold"] is None
    assert body["top_categories"] == []
    assert body["revenue_by_region"] == []
    assert body["forecast"]["status"] == "unavailable"


def test_generic_analysis_applies_confirmed_retail_status_semantics():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total,Status\n"
        "A001,2025-01-01,C001,100,Complete\n"
        "A002,2025-01-02,C002,100,Awaiting\n"
        "A003,2025-01-03,C003,100,Void\n"
        "A004,2025-01-04,C004,100,Sent Back",
    )
    request = row_total_request(upload_id)
    request.update(
        {
            "mapping": {**request["mapping"], "order_status": "Status"},
            "assume_all_completed": False,
            "status_mapping": {
                "Complete": "completed",
                "Awaiting": "pending",
                "Void": "cancelled",
                "Sent Back": "returned",
            },
            "latest_period_complete": True,
        }
    )

    response = client.post("/api/v1/uploads/analyze", json=request)

    assert response.status_code == 200
    kpis = response.json()["kpis"]
    assert kpis["gross_revenue"] == 200.0
    assert kpis["refund_amount"] == 100.0
    assert kpis["net_revenue"] == 100.0
    assert kpis["pending_value"] == 100.0
    assert kpis["order_count"] == 2


def test_generic_analysis_separates_currencies_and_supports_selection():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total,Currency\n"
        "A001,2025-01-01,C001,100,USD\n"
        "A002,2025-01-02,C002,200,NGN",
    )
    request = row_total_request(upload_id)
    request.update(
        {
            "mapping": {**request["mapping"], "currency": "Currency"},
            "latest_period_complete": True,
        }
    )

    analyzed = client.post("/api/v1/uploads/analyze", json=request)
    body = analyzed.json()
    selected = client.get(
        f"/api/v1/analyses/{body['analysis_id']}",
        params={"currency": "USD"},
    )

    assert analyzed.status_code == 200
    assert body["available_currencies"] == ["NGN", "USD"]
    assert body["currency"] == "NGN"
    assert body["kpis"]["net_revenue"] == 200.0
    assert selected.status_code == 200
    assert selected.json()["currency"] == "USD"
    assert selected.json()["kpis"]["net_revenue"] == 100.0


def test_generic_analysis_requires_quarantine_confirmation_and_exports_both_datasets():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total\n001,2025-01-01,0007,100\n002,not-a-date,0008,50",
    )
    request = row_total_request(upload_id)
    request["latest_period_complete"] = True

    blocked = client.post("/api/v1/uploads/analyze", json=request)
    request["confirm_quarantine"] = True
    analyzed = client.post("/api/v1/uploads/analyze", json=request)

    assert blocked.status_code == 409
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["canonical_rows"] == 1
    assert body["quarantined_rows"] == 1
    assert body["data_quality"]["status"] == "preview"
    assert body["data_quality"]["restricted_outputs"] == [
        "forecast",
        "diagnostics",
        "recommendations",
    ]
    assert body["forecast"]["status"] == "unavailable"
    assert "preview-only analysis" in body["forecast"]["trust_message"]
    assert body["diagnostics"]["comparison"]["status"] == "unavailable"
    assert body["diagnostics"]["comparison"]["insights"] == []
    assert body["diagnostics"]["comparison"]["unavailable_capabilities"][0]["code"] == (
        "insufficient_data_quality"
    )

    canonical = client.get(body["downloads"]["canonical_csv"])
    quarantine = client.get(body["downloads"]["quarantine_csv"])
    assert canonical.status_code == 200
    assert 'filename="sales_canonical.csv"' in canonical.headers["content-disposition"]
    assert "2,001,2025-01-01,2025-01-01,0007" in canonical.text
    assert quarantine.status_code == 200
    assert "not-a-date" in quarantine.text
    assert '"[""invalid_date""]"' in quarantine.text


def test_deleted_analysis_session_cannot_be_restored():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total\nA001,2025-01-01,C001,100",
    )
    request = row_total_request(upload_id)
    request["latest_period_complete"] = True
    analysis_id = client.post("/api/v1/uploads/analyze", json=request).json()["analysis_id"]

    deleted = client.delete(f"/api/v1/analyses/{analysis_id}")
    restored = client.get(f"/api/v1/analyses/{analysis_id}")

    assert deleted.status_code == 204
    assert restored.status_code == 404


def test_unit_price_transformation_computes_revenue():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Price,Units\nA001,2025-01-01,C001,12.50,3",
    )

    response = client.post(
        "/api/v1/uploads/transform",
        json={
            "upload_id": upload_id,
            "mapping": {
                "order_id": "Invoice",
                "order_date": "Date",
                "customer_id": "Customer",
                "unit_price": "Price",
                "quantity": "Units",
            },
            "revenue_mode": "unit_price_times_quantity",
            "negative_revenue_policy": "invalid",
            "date_format": "%Y-%m-%d",
            "currency": "NGN",
            "assume_all_completed": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["canonical_rows"] == 1
    assert body["sample_rows"][0]["revenue"] == 37.5
    assert body["sample_rows"][0]["quantity"] == 3


def test_transformation_preserves_leading_zero_identifiers():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total\n001,2025-01-01,0007,100",
    )

    response = client.post(
        "/api/v1/uploads/transform",
        json=row_total_request(upload_id),
    )

    assert response.status_code == 200
    row = response.json()["sample_rows"][0]
    assert row["order_id"] == "001"
    assert row["customer_id"] == "0007"


def test_order_total_transformation_counts_repeated_order_once():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total,Product\n"
        "A001,2025-01-01,C001,150,Shoes\n"
        "A001,2025-01-01,C001,150,Socks",
    )

    request = row_total_request(upload_id)
    request["revenue_mode"] = "order_total"
    response = client.post("/api/v1/uploads/transform", json=request)

    assert response.status_code == 200
    body = response.json()
    assert body["source_rows"] == 2
    assert body["canonical_rows"] == 1
    assert body["sample_rows"][0]["revenue"] == 150


def test_data_validation_rejects_invalid_mapping_before_reading_values():
    client = TestClient(api_main.app)
    upload_id = upload_csv(client, "Invoice,Date,Customer\nA001,2025-01-01,C001")
    request = row_total_request(upload_id)

    response = client.post("/api/v1/uploads/validate-data", json=request)

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "Schema mapping is invalid"


def test_data_validation_rejects_invalid_date_format_directive():
    client = TestClient(api_main.app)
    upload_id = upload_csv(
        client,
        "Invoice,Date,Customer,Total\nA001,2025-01-01,C001,100",
    )
    request = row_total_request(upload_id)
    request["date_format"] = "%Q"

    response = client.post("/api/v1/uploads/validate-data", json=request)

    assert response.status_code == 422
    assert "invalid directive" in response.json()["detail"]


def test_schema_mapping_rejects_unknown_upload_id():
    client = TestClient(api_main.app)

    response = client.post(
        "/api/v1/uploads/validate-mapping",
        json={"upload_id": "does-not-exist", "mapping": {}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Temporary upload not found"


def test_schema_mapping_reports_expired_upload():
    client = TestClient(api_main.app)

    with patch.object(upload_store, "get", side_effect=UploadExpiredError("expired")):
        response = client.post(
            "/api/v1/uploads/validate-mapping",
            json={"upload_id": "expired", "mapping": {}},
        )

    assert response.status_code == 410
    assert response.json()["detail"] == "Temporary upload has expired"


def test_temporary_upload_can_be_deleted_immediately():
    client = TestClient(api_main.app)
    upload_id = upload_csv(client, "Order ID,Date,Customer,Total\nA1,2024-01-01,C1,10")

    delete_response = client.delete(f"/api/v1/uploads/{upload_id}")
    mapping_response = client.post(
        "/api/v1/uploads/validate-mapping",
        json={"upload_id": upload_id, "mapping": {}},
    )

    assert delete_response.status_code == 204
    assert mapping_response.status_code == 404


def test_upload_cors_preflight_allows_post():
    client = TestClient(api_main.app)

    response = client.options(
        "/api/v1/uploads/preview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]


@pytest.mark.integration
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


@pytest.mark.integration
def test_partial_months_are_flagged():
    # The 3 dataset-boundary months (collection started/stopped mid-month)
    # must be flagged so the frontend can exclude them from the trend chart,
    # matching what trim_edge_artifacts already does for the forecast.
    with TestClient(api_main.app) as client:
        months = client.get("/api/v1/report").json()["revenue_by_month"]

    flagged = {m["month"] for m in months if m["is_partial"]}
    assert flagged == {"2016-09", "2016-12", "2018-09"}


@pytest.mark.integration
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


@pytest.mark.integration
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
