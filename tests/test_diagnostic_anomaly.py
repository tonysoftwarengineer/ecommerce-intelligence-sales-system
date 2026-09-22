import pandas as pd

from src.diagnostics.anomaly import build_monthly_anomaly_report
from src.diagnostics.contracts import DiagnosticStatus


def _frame(values: list[float], start: str = "2026-01") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_id": [f"O{index}" for index in range(len(values))],
            "order_date": [
                period.start_time
                for period in pd.period_range(start, periods=len(values), freq="M")
            ],
            "recognized_sales": values,
            "currency": "NGN",
        }
    )


def test_anomaly_report_flags_latest_sales_outlier() -> None:
    report = build_monthly_anomaly_report(
        _frame([100, 100, 100, 100, 100, 100, 300]),
        latest_period_complete=True,
    )

    assert report.status is DiagnosticStatus.AVAILABLE
    sales_insight = next(
        insight for insight in report.insights if insight.id == "anomaly_recognized_sales"
    )
    assert sales_insight.title == "Unusually high recognized sales detected"
    assert sales_insight.evidence[0].baseline_value == 100.0
    assert sales_insight.evidence[0].current_value == 300.0
    assert sales_insight.evidence[0].percent_change == 200.0


def test_stable_history_has_explicit_no_findings_status() -> None:
    report = build_monthly_anomaly_report(
        _frame([100, 100, 100, 100, 100, 100, 100]),
        latest_period_complete=True,
    )

    assert report.status is DiagnosticStatus.NO_FINDINGS
    assert report.insights == ()
    assert report.unavailable_capabilities == ()


def test_insufficient_history_explains_required_baseline() -> None:
    report = build_monthly_anomaly_report(
        _frame([100, 100, 100, 100, 100, 100]),
        latest_period_complete=True,
    )

    assert report.status is DiagnosticStatus.UNAVAILABLE
    assert report.unavailable_capabilities[0].code == "insufficient_anomaly_history"
    assert "six prior complete months" in report.unavailable_capabilities[0].message


def test_incomplete_latest_period_preserves_exclusion_and_history_limitations() -> None:
    report = build_monthly_anomaly_report(
        _frame([100, 100, 100, 100, 100, 100, 300]),
        latest_period_complete=False,
    )

    assert report.status is DiagnosticStatus.UNAVAILABLE
    assert [limitation.code for limitation in report.unavailable_capabilities] == [
        "latest_period_excluded",
        "insufficient_anomaly_history",
    ]


def test_missing_months_are_not_treated_as_zero_sales() -> None:
    frame = _frame([100, 100, 100, 100, 100, 100, 100, 300])
    frame = frame.drop(index=3)

    report = build_monthly_anomaly_report(frame, latest_period_complete=True)

    assert report.status is DiagnosticStatus.UNAVAILABLE
    assert report.unavailable_capabilities[0].code == "non_contiguous_anomaly_history"


def test_anomaly_insight_explains_that_it_is_not_causal() -> None:
    report = build_monthly_anomaly_report(
        _frame([100, 100, 100, 100, 100, 100, 300]),
        latest_period_complete=True,
    )

    sales_insight = next(
        insight for insight in report.insights if insight.id == "anomaly_recognized_sales"
    )
    assert sales_insight.limitations[0].code == "non_causal_finding"
