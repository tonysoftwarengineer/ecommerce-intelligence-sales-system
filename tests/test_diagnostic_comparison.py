import pandas as pd
import pytest

from src.diagnostics.comparison import build_latest_complete_period_revenue_report


def _canonical_sales(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).assign(currency="NGN")


def test_revenue_comparison_decomposes_change_exactly() -> None:
    report = build_latest_complete_period_revenue_report(
        _canonical_sales(
            [
                {"order_id": "J1", "order_date": "2026-06-02", "recognized_sales": 100},
                {"order_id": "J2", "order_date": "2026-06-04", "recognized_sales": 100},
                {"order_id": "L1", "order_date": "2026-07-02", "recognized_sales": 150},
                {"order_id": "L2", "order_date": "2026-07-04", "recognized_sales": 150},
                {"order_id": "L3", "order_date": "2026-07-06", "recognized_sales": 150},
            ]
        ),
        latest_period_complete=True,
    )

    insight = report.insights[0]
    assert insight.title == "Recognized sales increased by 125.0%"
    assert insight.comparison_period is not None
    assert insight.comparison_period.baseline_label == "2026-06"
    assert insight.comparison_period.current_label == "2026-07"
    assert insight.evidence[0].metric == "recognized_sales"
    assert insight.evidence[0].absolute_change == 250.0
    assert insight.evidence[1].current_value == 3.0
    assert insight.evidence[2].current_value == 150.0
    assert [contributor.contribution_value for contributor in insight.contributors] == [
        125.0,
        125.0,
    ]
    assert sum(contributor.contribution_value for contributor in insight.contributors) == 250.0


def test_refund_only_rows_do_not_change_completed_order_decomposition() -> None:
    report = build_latest_complete_period_revenue_report(
        _canonical_sales(
            [
                {
                    "order_id": "J1",
                    "order_date": "2026-06-02",
                    "recognized_sales": 100,
                    "revenue": 100,
                },
                {
                    "order_id": "R1",
                    "order_date": "2026-06-10",
                    "recognized_sales": 0,
                    "revenue": -100,
                },
                {
                    "order_id": "L1",
                    "order_date": "2026-07-02",
                    "recognized_sales": 200,
                    "revenue": 200,
                },
            ]
        ),
        latest_period_complete=True,
    )

    insight = report.insights[0]
    assert insight.evidence[0].baseline_value == 100.0
    assert insight.evidence[1].baseline_value == 1.0


def test_incomplete_latest_month_is_excluded() -> None:
    report = build_latest_complete_period_revenue_report(
        _canonical_sales(
            [
                {"order_id": "M1", "order_date": "2026-05-02", "recognized_sales": 100},
                {"order_id": "J1", "order_date": "2026-06-02", "recognized_sales": 200},
                {"order_id": "L1", "order_date": "2026-07-02", "recognized_sales": 300},
            ]
        ),
        latest_period_complete=False,
    )

    insight = report.insights[0]
    assert insight.comparison_period is not None
    assert insight.comparison_period.baseline_label == "2026-05"
    assert insight.comparison_period.current_label == "2026-06"
    assert insight.limitations[0].code == "latest_period_excluded"


def test_incomplete_latest_month_explains_why_comparison_is_unavailable() -> None:
    report = build_latest_complete_period_revenue_report(
        _canonical_sales(
            [
                {"order_id": "J1", "order_date": "2026-06-02", "recognized_sales": 100},
                {"order_id": "L1", "order_date": "2026-07-02", "recognized_sales": 200},
            ]
        ),
        latest_period_complete=False,
    )

    assert report.insights == ()
    assert [limitation.code for limitation in report.unavailable_capabilities] == [
        "latest_period_excluded",
        "insufficient_complete_periods",
    ]
    assert (
        "2026-07 was excluded because it is incomplete"
        in report.unavailable_capabilities[0].message
    )
    assert "at least two complete months" in report.unavailable_capabilities[1].message


def test_missing_months_disable_comparison_instead_of_assuming_zero_sales() -> None:
    report = build_latest_complete_period_revenue_report(
        _canonical_sales(
            [
                {"order_id": "J1", "order_date": "2026-01-02", "recognized_sales": 100},
                {"order_id": "M1", "order_date": "2026-03-02", "recognized_sales": 200},
            ]
        ),
        latest_period_complete=True,
    )

    assert report.insights == ()
    assert report.unavailable_capabilities[0].code == "non_contiguous_periods"


def test_recognition_date_controls_revenue_month() -> None:
    report = build_latest_complete_period_revenue_report(
        _canonical_sales(
            [
                {
                    "order_id": "J1",
                    "order_date": "2026-05-30",
                    "recognition_date": "2026-06-01",
                    "recognized_sales": 100,
                },
                {
                    "order_id": "L1",
                    "order_date": "2026-06-30",
                    "recognition_date": "2026-07-01",
                    "recognized_sales": 200,
                },
            ]
        ),
        latest_period_complete=True,
    )

    insight = report.insights[0]
    assert insight.comparison_period is not None
    assert insight.comparison_period.baseline_label == "2026-06"
    assert insight.comparison_period.current_label == "2026-07"


def test_multiple_currencies_are_rejected() -> None:
    frame = _canonical_sales(
        [
            {"order_id": "J1", "order_date": "2026-06-02", "recognized_sales": 100},
            {"order_id": "L1", "order_date": "2026-07-02", "recognized_sales": 200},
        ]
    )
    frame.loc[1, "currency"] = "USD"

    with pytest.raises(ValueError, match="exactly one currency"):
        build_latest_complete_period_revenue_report(frame, latest_period_complete=True)
