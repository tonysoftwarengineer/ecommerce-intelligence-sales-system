import pytest

from api.analysis_observability import AnalysisObservability


def _report(
    comparison_status: str,
    anomaly_status: str,
    forecast_status: str,
    *,
    anomaly_processing_error: bool = False,
) -> dict:
    return {
        "diagnostics": {
            "comparison": {"status": comparison_status, "unavailable_capabilities": []},
            "anomalies": {
                "status": anomaly_status,
                "unavailable_capabilities": (
                    [{"code": "diagnostic_processing_error"}] if anomaly_processing_error else []
                ),
            },
        },
        "forecast": {"status": forecast_status},
    }


def test_observability_summarizes_latency_and_diagnostic_availability() -> None:
    observability = AnalysisObservability()
    observability.record_completed(
        0.010,
        {"NGN": _report("available", "no_findings", "available")},
    )
    observability.record_completed(
        0.030,
        {"USD": _report("unavailable", "unavailable", "unavailable")},
    )

    snapshot = observability.snapshot()

    assert snapshot["analysis_runs"] == 2
    assert snapshot["currency_reports"] == 2
    assert snapshot["latency_ms"] == {
        "sample_count": 2,
        "average": 20.0,
        "p50": 20.0,
        "p95": 30.0,
        "maximum": 30.0,
    }
    assert snapshot["diagnostics"]["comparison"] == {
        "section_reports": 2,
        "assessed_reports": 1,
        "unavailable_reports": 1,
        "assessed_percent": 50.0,
        "processing_error_count": 0,
        "status_counts": {"available": 1, "unavailable": 1},
    }
    assert snapshot["diagnostics"]["anomalies"]["status_counts"] == {
        "no_findings": 1,
        "unavailable": 1,
    }
    assert snapshot["forecast_status_counts"] == {"available": 1, "unavailable": 1}


def test_observability_counts_safe_diagnostic_processing_fallbacks() -> None:
    observability = AnalysisObservability()
    observability.record_completed(
        0.001,
        {
            "NGN": _report(
                "available",
                "unavailable",
                "available",
                anomaly_processing_error=True,
            )
        },
    )

    assert observability.snapshot()["diagnostics"]["anomalies"]["processing_error_count"] == 1


def test_observability_requires_a_positive_latency_sample_limit() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        AnalysisObservability(max_latency_samples=0)
