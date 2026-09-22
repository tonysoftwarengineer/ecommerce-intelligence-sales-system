import pandas as pd

from src.generic_sales.analytics import analyze_canonical_sales


def canonical_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_row": [2, 3, 4, 5],
            "order_id": ["A1", "A1", "A2", "A3"],
            "order_date": pd.to_datetime(["2025-01-02", "2025-01-02", "2025-02-04", "2025-02-08"]),
            "customer_id": ["C1", "C1", "C2", "C1"],
            "revenue": [100.0, 50.0, 200.0, -25.0],
            "currency": ["NGN"] * 4,
            "quantity": [2, 1, 4, -1],
            "product_category": ["Shoes", "Socks", "Shoes", "Shoes"],
            "state_or_region": ["Lagos", "Lagos", "Abuja", "Lagos"],
        }
    )


def test_generic_analytics_are_order_grain_safe_and_refund_aware() -> None:
    result = analyze_canonical_sales(canonical_frame())

    expected = {
        "gross_revenue": 350.0,
        "refund_amount": 25.0,
        "net_revenue": 325.0,
        "average_order_value": 108.33,
        "order_count": 3,
        "customer_count": 2,
        "units_sold": 6.0,
    }
    assert {key: result["kpis"][key] for key in expected} == expected
    assert result["revenue_by_month"] == [
        {"month": "2025-01", "revenue": 150.0},
        {"month": "2025-02", "revenue": 175.0},
    ]


def test_generic_analytics_include_only_supported_optional_breakdowns() -> None:
    result = analyze_canonical_sales(canonical_frame())

    assert result["capabilities"] == {
        "category_analysis": True,
        "regional_analysis": True,
        "quantity_analysis": True,
        "refund_analysis": False,
        "payment_analysis": False,
    }
    assert result["top_categories"][0] == {"category": "Shoes", "revenue": 275.0}
    assert result["revenue_by_region"][0] == {"region": "Abuja", "revenue": 200.0}
    assert result["top_customers"][0] == {"customer_id": "C2", "revenue": 200.0}


def test_generic_analytics_do_not_invent_missing_capabilities() -> None:
    frame = canonical_frame().drop(columns=["quantity", "product_category", "state_or_region"])

    result = analyze_canonical_sales(frame)

    assert result["capabilities"] == {
        "category_analysis": False,
        "regional_analysis": False,
        "quantity_analysis": False,
        "refund_analysis": False,
        "payment_analysis": False,
    }
    assert result["kpis"]["units_sold"] is None
    assert result["top_categories"] == []
    assert result["revenue_by_region"] == []


def test_cash_collection_is_unavailable_without_a_mapped_payment_amount() -> None:
    result = analyze_canonical_sales(canonical_frame(), mapped_fields={"payment_status"})

    assert result["kpis"]["net_collected"] is None


def test_cash_collection_uses_payment_amount_when_it_is_explicitly_mapped() -> None:
    frame = canonical_frame().assign(
        payment_amount=[100, 50, 200, -25],
        net_collected=[100, 50, 200, -25],
    )

    result = analyze_canonical_sales(frame, mapped_fields={"payment_amount"})

    assert result["kpis"]["net_collected"] == 325.0


def test_refund_only_trailing_month_stays_in_reporting_but_not_forecast_history() -> None:
    sales_dates = [f"2025-{month:02}-01" for month in range(1, 13)] + ["2025-12-31"]
    frame = pd.DataFrame(
        {
            "order_id": [f"A{month:02}" for month in range(1, 13)] + ["R1"],
            "order_date": pd.to_datetime(sales_dates),
            "recognition_date": pd.to_datetime(sales_dates),
            "refund_date": pd.to_datetime([None] * 12 + ["2026-01-10"]),
            "customer_id": ["C1"] * 13,
            "revenue": [100] * 12 + [-100],
            "recognized_sales": [100] * 12 + [0],
            "refund_amount": [0] * 12 + [100],
            "gross_sales": [100] * 12 + [0],
            "currency": ["NGN"] * 13,
        }
    )

    result = analyze_canonical_sales(frame)

    assert result["revenue_by_month"][-1] == {"month": "2026-01", "revenue": -100.0}
    assert str(result["forecast_series"].index[-1]) == "2025-12"
    assert result["forecast_excluded_adjustment_periods"] == ["2026-01"]
